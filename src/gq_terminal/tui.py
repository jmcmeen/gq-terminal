"""Optional Textual dashboard for live GMC monitoring.

This module is imported lazily by the ``tui`` CLI subcommand so that
``textual`` stays an *optional* dependency — importing ``gq_terminal`` never
pulls it in. Install it with ``pip install 'gq-terminal[tui]'``.

Like ``cli.py``, this is a UI layer: it renders to the terminal. All device
communication still goes through :class:`~gq_terminal.interface.GMCInterface`,
and the blocking serial calls are dispatched to threads with
``asyncio.to_thread`` so they never stall the event loop.
"""

import asyncio
import time
from collections import deque
from datetime import datetime
from typing import NamedTuple

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Digits, Footer, Header, Sparkline, Static

from . import __version__
from .interface import Calibration, GMCError, GMCInterface

# Each entry is a single logical line so the modal wraps it to its own width
# (no hard-coded breaks); blank lines separate entries; terms are colored.
_GLOSSARY = (
    "[b $accent]CPS[/] — Counts per second. Ionizing events the tube "
    "registers each second.\n\n"
    "[b $accent]CPM[/] — Counts per minute. The same events summed over a "
    "minute (less noisy).\n\n"
    "[b $accent]µSv/h[/] — Microsieverts per hour. An estimated dose-equivalent "
    "rate, derived from CPM using the tube's calibration.\n\n"
    "[b $accent]mR/h[/] — Milliroentgens per hour. An exposure rate; shown "
    "here as µSv/h ÷ 10.\n\n"
    "[b $warning]Note[/] — Dose rates (µSv/h, mR/h) are derived from CPM via "
    "calibration and depend on the tube and the source. They are not certified "
    "measurements."
)

_ABOUT = (
    f"[b $accent]GQ Terminal[/]  v{__version__}\n\n"
    "A small, scriptable Python library, CLI, and TUI for GQ GMC geiger "
    "counters, speaking the GQ-RFC1201 protocol over a serial port.\n\n"
    "Not affiliated with GQ Electronics, and not a certified instrument — do "
    "not use its readings for safety, regulatory, or medical decisions.\n\n"
    "https://github.com/jmcmeen/gq-terminal"
)


class _InfoModal(ModalScreen[None]):
    """A simple centered modal showing a title and a block of text."""

    BINDINGS = [("escape,enter,q,space", "dismiss", "Close")]

    CSS = """
    _InfoModal {
        align: center middle;
    }
    #modal-box {
        width: 72;
        max-width: 90%;
        height: auto;
        max-height: 90%;
        border: round $success;
        background: $surface;
        padding: 1 2;
    }
    #modal-title { text-style: bold; width: 100%; text-align: center; }
    #modal-scroll { height: auto; max-height: 20; }
    #modal-body { padding: 1 0; width: 100%; }
    #modal-hint { color: $text-muted; width: 100%; text-align: center; }
    """

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-box"):
            yield Static(self._title, id="modal-title")
            with VerticalScroll(id="modal-scroll"):
                yield Static(self._body, id="modal-body")
            yield Static("Esc to close", id="modal-hint")


class _SlowReading(NamedTuple):
    """Values read together on the slow-refresh tick (heartbeat paused)."""

    cpm: int
    voltage: float
    temperature: float | None
    device_time: datetime | None
    gyro: tuple[int, int, int] | None


# CPM and battery voltage change slowly; refresh them this often (seconds)
# rather than every display tick. Matches the cadence used by `monitor` in the
# CLI. The heartbeat must be paused to read them, so we keep it infrequent.
_SLOW_REFRESH_SECONDS = 5.0

# Floor aligns with the 0.5s adjustment step so the interval stays on a clean
# grid (…1.0, 0.5) instead of drifting to values like 0.6 after hitting bottom.
_MIN_INTERVAL = 0.5
_MAX_INTERVAL = 60.0

# Below this, flag the battery as low (matches the CLI's LOW_BATTERY_VOLTS).
_LOW_BATTERY_VOLTS = 3.0

# The first heartbeat packets after starting the stream are often junk (0s while
# the device settles), which made the graph flash and clear. Discard this many
# initial CPS samples before recording or plotting anything.
_WARMUP_SAMPLES = 3

# Data points retained per series for the sparkline. The widget buckets these
# into its (narrower) width, so a larger value shows a wider time window
# "smooshed" together (a longer trend) rather than rolling off quickly. At the
# default 1s interval this spans ~10 minutes; the window scales with the
# chosen interval.
_HISTORY_LEN = 600


class GMCMonitorApp(App[None]):
    """Live CPS/CPM dashboard for a connected GMC counter.

    Takes an already-connected :class:`GMCInterface`; starts heartbeat
    streaming on mount and stops it on exit. The owner of the interface is
    responsible for ``disconnect()`` (the CLI does this in a ``finally``).
    """

    CSS = """
    #body { height: 1fr; }
    #info-row { height: auto; padding: 0 2; }
    #device-box {
        width: 1fr;
        height: auto;
        border: round $success;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    #status-box {
        width: 2fr;
        height: auto;
        border: round $success;
        padding: 0 1;
    }
    .status-row { height: auto; }
    .status-row > Static { width: 1fr; }
    #readings-box {
        height: auto;
        border: round $success;
        margin: 0 2;
        padding: 0 1;
    }
    #readouts { height: auto; align: center middle; }
    .readout { width: 1fr; height: auto; align: center middle; }
    .readout-label {
        text-style: bold;
        color: $text-muted;
        width: 100%;
        text-align: center;
    }
    #cps, #cpm, #usv, #mr { text-align: center; }
    #cps { color: $success; }
    #cpm { color: $accent; }
    #usv { color: $warning; }
    #mr { color: $secondary; }
    /* Trend coloring on the slow readouts: warmer when rising vs. the last
       reading, green when falling, base color when steady. Relative change, not
       a certified level. */
    #cpm.rising, #usv.rising, #mr.rising { color: $error; }
    #cpm.falling, #usv.falling, #mr.falling { color: $success; }
    #graph-box {
        height: 1fr;
        min-height: 5;
        border: round $success;
        margin: 0 2;
        padding: 0 1;
    }
    #graph { height: 1fr; min-height: 3; }
    #graph > .sparkline--min-color { color: $success; }
    #graph > .sparkline--max-color { color: $warning; }
    #stats-box {
        height: auto;
        border: round $success;
        margin: 0 2;
        padding: 0 1;
    }
    #stats { height: auto; }
    #interval-label { height: auto; color: $text-muted; padding: 0 2; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("plus,equals_sign,up", "interval(-0.5)", "Faster"),
        ("minus,down", "interval(+0.5)", "Slower"),
        ("g", "toggle_graph", "Graph CPS/CPM"),
        ("question_mark", "glossary", "Glossary"),
        ("a", "about", "About"),
    ]

    interval: reactive[float] = reactive(1.0)
    graph_metric: reactive[str] = reactive("CPM")

    def __init__(self, gmc: GMCInterface, interval: float = 1.0) -> None:
        super().__init__()
        self._gmc = gmc
        self._timer: Timer | None = None
        # Set without firing watch_interval — widgets don't exist yet at init.
        self.set_reactive(
            GMCMonitorApp.interval, max(_MIN_INTERVAL, min(_MAX_INTERVAL, interval))
        )
        # Both series advance one point per tick: CPS per heartbeat sample, CPM
        # carrying the latest value (the device is re-polled every
        # _SLOW_REFRESH_SECONDS, so the CPM line steps between reads).
        self._cps_history: deque[int] = deque(maxlen=_HISTORY_LEN)
        self._cpm_history: deque[int] = deque(maxlen=_HISTORY_LEN)
        self._samples = 0
        self._total = 0
        self._max_cps = 0
        self._min_cps: int | None = None
        self._cpm = 0
        self._voltage: float | None = None
        self._temperature: float | None = None
        self._device_time: datetime | None = None
        self._gyro: tuple[int, int, int] | None = None
        self._calibration: Calibration | None = None
        self._warmup_remaining = _WARMUP_SAMPLES
        self._last_slow = 0.0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # VerticalScroll so a short terminal scrolls instead of clipping content;
        # the graph flexes (height: 1fr) to absorb extra space on a tall one.
        with VerticalScroll(id="body"):
            with Horizontal(id="info-row"):
                with Vertical(id="device-box"):
                    yield Static("Model: —", id="device-model")
                    yield Static("Serial: —", id="device-serial")
                with Vertical(id="status-box"):
                    with Horizontal(classes="status-row"):
                        yield Static("Battery: —", id="battery")
                        yield Static("Temperature: —", id="temp")
                    with Horizontal(classes="status-row"):
                        yield Static("Clock: —", id="clock")
                        yield Static("Gyro: —", id="gyro")
            with Vertical(id="readings-box"):
                with Horizontal(id="readouts"):
                    with Vertical(classes="readout"):
                        yield Static("CPS", classes="readout-label")
                        yield Digits("0", id="cps")
                    with Vertical(classes="readout"):
                        yield Static("CPM", classes="readout-label")
                        yield Digits("0", id="cpm")
                    with Vertical(classes="readout"):
                        yield Static("µSv/h", classes="readout-label")
                        yield Digits("--", id="usv")
                    with Vertical(classes="readout"):
                        yield Static("mR/h", classes="readout-label")
                        yield Digits("--", id="mr")
            with Vertical(id="graph-box"):
                yield Sparkline([], id="graph", summary_function=max)
            with Vertical(id="stats-box"):
                yield Static("", id="stats")
            yield Static("", id="interval-label")
        yield Footer()

    async def on_mount(self) -> None:
        self.title = "GQ Terminal"
        self.query_one("#device-box").border_title = "Device"
        self.query_one("#status-box").border_title = "Status"
        self.query_one("#readings-box").border_title = "Readings"
        self.query_one("#graph-box").border_title = "Trend"
        self.query_one("#stats-box").border_title = "Session"
        self._update_interval_label()
        await self._load_device_info()
        try:
            self._calibration = await asyncio.to_thread(self._gmc.get_calibration)
        except GMCError:
            self._calibration = None
        self._update_dose()
        try:
            await asyncio.to_thread(self._gmc.start_heartbeat)
        except GMCError:
            self.query_one("#stats", Static).update("Could not start heartbeat stream")
        self._timer = self.set_interval(self.interval, self._tick)

    async def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        try:
            await asyncio.to_thread(self._gmc.stop_heartbeat)
        except GMCError:
            pass

    def watch_interval(self, interval: float) -> None:
        # Reschedule the tick timer when the interval changes at runtime.
        if self._timer is not None:
            self._timer.stop()
            self._timer = self.set_interval(interval, self._tick)
        self._update_interval_label()

    def action_interval(self, delta: float) -> None:
        self.interval = max(_MIN_INTERVAL, min(_MAX_INTERVAL, self.interval + delta))

    def action_toggle_graph(self) -> None:
        self.graph_metric = "CPM" if self.graph_metric == "CPS" else "CPS"

    def action_glossary(self) -> None:
        self.push_screen(_InfoModal("Glossary", _GLOSSARY))

    def action_about(self) -> None:
        self.push_screen(_InfoModal("About", _ABOUT))

    def watch_graph_metric(self, metric: str) -> None:
        self._redraw_graph()

    async def _load_device_info(self) -> None:
        try:
            version, serial_num = await asyncio.to_thread(self._read_identity)
        except GMCError:
            version, serial_num = "unknown", "unknown"
        self.sub_title = version
        self.query_one("#device-model", Static).update(f"Model: {version}")
        self.query_one("#device-serial", Static).update(f"Serial: {serial_num}")

    def _read_identity(self) -> tuple[str, str]:
        return self._gmc.get_version(), self._gmc.get_serial_number()

    async def _tick(self) -> None:
        samples = await asyncio.to_thread(self._drain_samples)
        fresh: list[int] = []
        for cps in samples:
            if self._warmup_remaining > 0:
                self._warmup_remaining -= 1  # discard initial settling junk
                continue
            fresh.append(cps)
        for cps in fresh:
            self._samples += 1
            self._total += cps
            self._max_cps = max(self._max_cps, cps)
            self._min_cps = cps if self._min_cps is None else min(self._min_cps, cps)
            self._cps_history.append(cps)
        if fresh:
            self.query_one("#cps", Digits).update(str(fresh[-1]))

        now = time.monotonic()
        if now - self._last_slow >= _SLOW_REFRESH_SECONDS:
            self._last_slow = now
            previous_cpm = self._cpm
            try:
                reading: _SlowReading | None = await asyncio.to_thread(self._read_slow)
            except GMCError:
                reading = None
            if reading is not None:
                self._cpm = reading.cpm
                self._voltage = reading.voltage
                self._temperature = reading.temperature
                self._device_time = reading.device_time
                self._gyro = reading.gyro
            self.query_one("#cpm", Digits).update(str(self._cpm))
            self._update_status()
            self._update_dose()
            self._apply_trend((self._cpm > previous_cpm) - (self._cpm < previous_cpm))

        # Plot one CPM point per tick (at the display interval) using the latest
        # value — the device is only re-polled every _SLOW_REFRESH_SECONDS, so
        # the line steps when a fresh reading lands, but the graph keeps pace
        # with the interval like the CPS graph does.
        self._cpm_history.append(self._cpm)

        self._redraw_graph()
        self._update_stats()

    def _drain_samples(self) -> list[int]:
        out: list[int] = []
        while True:
            cps = self._gmc.read_heartbeat()
            if cps is None:
                break
            out.append(cps)
        return out

    def _read_slow(self) -> _SlowReading:
        # Pause the stream so these replies aren't interleaved with heartbeat
        # packets, then resume it. Temperature/datetime/gyro return None on
        # firmware that doesn't support them.
        self._gmc.stop_heartbeat()
        try:
            return _SlowReading(
                cpm=self._gmc.get_cpm(),
                voltage=self._gmc.get_battery_voltage(),
                temperature=self._gmc.get_temperature(),
                device_time=self._gmc.get_datetime(),
                gyro=self._gmc.get_gyroscope(),
            )
        finally:
            self._gmc.start_heartbeat()

    def _redraw_graph(self) -> None:
        history = self._cpm_history if self.graph_metric == "CPM" else self._cps_history
        data = list(history)
        # Sparkline renders a single point as a full-width block (a jarring
        # "flash"); hold the empty baseline until there are at least two points
        # so the graph eases in cleanly.
        self.query_one("#graph", Sparkline).data = data if len(data) >= 2 else []
        box = self.query_one("#graph-box")
        box.border_title = f"Trend — {self.graph_metric}"
        if history:
            box.border_subtitle = f"low {min(history)} · high {max(history)}"
        else:
            box.border_subtitle = "waiting for data"

    def _update_status(self) -> None:
        # Battery (with low-battery flag) plus the slow sensor reads, as the
        # 2x2 grid in the Status box.
        if self._voltage is None:
            battery = "Battery: —"
        elif self._voltage < _LOW_BATTERY_VOLTS:
            battery = f"[red]Battery: {self._voltage:.2f} V (LOW)[/red]"
        else:
            battery = f"Battery: {self._voltage:.2f} V"
        if self._temperature is not None:
            temp = f"Temperature: {self._temperature:.1f} °C"
        else:
            temp = "Temperature: N/A"
        if self._device_time is not None:
            clock = f"Clock: {self._device_time.strftime('%Y-%m-%d %H:%M:%S')}"
        else:
            clock = "Clock: N/A"
        if self._gyro is not None:
            gyro = f"Gyro: {self._gyro[0]}, {self._gyro[1]}, {self._gyro[2]}"
        else:
            gyro = "Gyro: N/A"
        self.query_one("#battery", Static).update(battery)
        self.query_one("#temp", Static).update(temp)
        self.query_one("#clock", Static).update(clock)
        self.query_one("#gyro", Static).update(gyro)

    def _apply_trend(self, direction: int) -> None:
        # CPM and the dose readouts move together (dose is derived from CPM),
        # so one direction drives all three. CPS is left fixed (too noisy).
        ids = ["#cpm"]
        if self._calibration is not None:
            ids += ["#usv", "#mr"]
        for widget_id in ids:
            widget = self.query_one(widget_id, Digits)
            widget.set_class(direction > 0, "rising")
            widget.set_class(direction < 0, "falling")

    def _update_dose(self) -> None:
        # µSv/h and mR/h are big readouts; "--" when uncalibrated. The
        # derived/not-certified caveat lives in the Glossary modal ("?").
        if self._calibration is None:
            self.query_one("#usv", Digits).update("--")
            self.query_one("#mr", Digits).update("--")
            return
        usv = self._calibration.cpm_to_usv(self._cpm)
        self.query_one("#usv", Digits).update(f"{usv:.2f}")
        self.query_one("#mr", Digits).update(f"{usv / 10.0:.3f}")

    def _update_stats(self) -> None:
        avg = self._total / self._samples if self._samples else 0.0
        min_cps = self._min_cps if self._min_cps is not None else "—"
        self.query_one("#stats", Static).update(
            f"Samples: {self._samples}    Avg CPS: {avg:.2f}    "
            f"Max CPS: {self._max_cps}    Min CPS: {min_cps}    "
            f"Total counts: {self._total}"
        )

    def _update_interval_label(self) -> None:
        self.query_one("#interval-label", Static).update(
            f"Update interval: {self.interval:.1f}s  (+/- to adjust)"
        )


def run_tui(gmc: GMCInterface, interval: float = 1.0) -> None:
    """Launch the dashboard for a connected ``gmc`` and block until the user quits."""
    GMCMonitorApp(gmc, interval).run()
