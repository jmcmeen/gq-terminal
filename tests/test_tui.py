"""Tests for the optional Textual dashboard.

Skipped entirely if Textual isn't installed (it's an optional `tui` extra).
The device is driven through the same FakeSerial fixture as the protocol tests.
"""

import struct

import pytest

pytest.importorskip("textual")

from textual.widgets import Digits, Sparkline, Static  # noqa: E402

from gq_terminal import Calibration, GMCInterface  # noqa: E402
from gq_terminal.tui import (  # noqa: E402
    _WARMUP_SAMPLES,
    GMCMonitorApp,
    _InfoModal,
)


def _register_gmc600(fake) -> None:
    """Script a GMC-600-family device (15-byte GETVER, 4-byte CPM)."""
    fake.add_handler(rb"<GETVER>>", b"GMC-600+Re 2.22")
    fake.add_handler(rb"<GETSERIAL>>", bytes.fromhex("00112233445566"))
    fake.add_handler(rb"<GETCPM>>", struct.pack(">I", 123))
    fake.add_handler(rb"<GETVOLT>>", b"4.3v\x00")
    fake.add_handler(rb"<HEARTBEAT0>>", b"")
    fake.add_handler(rb"<HEARTBEAT1>>", b"")


async def test_loads_device_info_and_starts_heartbeat(
    gmc: GMCInterface, fake_serial
) -> None:
    _register_gmc600(fake_serial)
    app = GMCMonitorApp(gmc, interval=60.0)
    async with app.run_test():
        assert "GMC-600+Re 2.22" in app.query_one("#device-model", Static).content
        assert "00112233445566" in app.query_one("#device-serial", Static).content
        assert gmc.heartbeat_active


async def test_tick_displays_drained_cps_samples(
    gmc: GMCInterface, fake_serial
) -> None:
    _register_gmc600(fake_serial)
    app = GMCMonitorApp(gmc, interval=60.0)  # large interval: no auto-tick races
    async with app.run_test():
        app._warmup_remaining = 0  # skip settling discard for this assertion
        fake_serial.queue_bytes(struct.pack(">I", 5))
        fake_serial.queue_bytes(struct.pack(">I", 9))
        await app._tick()

        # Most recent sample shown big; both samples folded into the stats.
        assert app.query_one("#cps", Digits).value == "9"
        stats = app.query_one("#stats", Static).content
        assert "Samples: 2" in stats
        assert "Max CPS: 9" in stats

        # CPM is a large readout fetched on the slow refresh (fires on first tick).
        assert app.query_one("#cpm", Digits).value == "123"

        # Status box cells (battery + sensors), not the stats line.
        assert "4.3" in app.query_one("#battery", Static).content
        assert "Temperature: N/A" in app.query_one("#temp", Static).content
        assert "Battery" not in app.query_one("#stats", Static).content

        # No calibration available (no config handler) → dose readouts show "--".
        assert app.query_one("#usv", Digits).value == "--"
        assert app.query_one("#mr", Digits).value == "--"

        # The graph defaults to CPM (one point recorded; not yet rendered —
        # the sparkline waits for >= 2 points to avoid a full-block flash).
        assert list(app._cpm_history) == [123]
        assert app.query_one("#graph", Sparkline).data == []
        assert "CPM" in str(app.query_one("#graph-box").border_title)

        # The legend (on the Trend border) shows the range.
        legend = str(app.query_one("#graph-box").border_subtitle)
        assert "low 123" in legend
        assert "high 123" in legend


async def test_graph_toggles_between_cpm_and_cps(
    gmc: GMCInterface, fake_serial
) -> None:
    _register_gmc600(fake_serial)
    app = GMCMonitorApp(gmc, interval=60.0)
    async with app.run_test() as pilot:
        app._warmup_remaining = 0
        fake_serial.queue_bytes(struct.pack(">I", 5))
        fake_serial.queue_bytes(struct.pack(">I", 9))
        await app._tick()

        # Defaults to CPM (single point held back from rendering).
        assert app.graph_metric == "CPM"
        assert list(app._cpm_history) == [123]

        await pilot.press("g")
        assert app.graph_metric == "CPS"
        assert list(app._cps_history) == [5, 9]
        assert list(app.query_one("#graph", Sparkline).data) == [5, 9]
        assert "CPS" in str(app.query_one("#graph-box").border_title)

        await pilot.press("g")
        assert app.graph_metric == "CPM"
        assert list(app._cpm_history) == [123]


async def test_dose_line_with_calibration(gmc: GMCInterface, fake_serial) -> None:
    _register_gmc600(fake_serial)
    gmc._calibration_override = Calibration.from_factor(0.0065)
    app = GMCMonitorApp(gmc, interval=60.0)
    async with app.run_test():
        app._warmup_remaining = 0
        fake_serial.queue_bytes(struct.pack(">I", 100))
        await app._tick()  # slow refresh reads CPM=123, derives the dose
        # Big readouts: µSv/h = 123*0.0065 = 0.7995 → "0.80"; mR/h = /10 → "0.080".
        assert app.query_one("#usv", Digits).value == "0.80"
        assert app.query_one("#mr", Digits).value == "0.080"


async def test_glossary_and_about_modals(gmc: GMCInterface, fake_serial) -> None:
    _register_gmc600(fake_serial)
    app = GMCMonitorApp(gmc, interval=60.0)
    async with app.run_test() as pilot:
        await pilot.press("question_mark")
        assert isinstance(app.screen, _InfoModal)
        assert app.screen.query_one("#modal-title", Static).content == "Glossary"
        await pilot.press("escape")
        assert not isinstance(app.screen, _InfoModal)

        await pilot.press("a")
        assert isinstance(app.screen, _InfoModal)
        assert app.screen.query_one("#modal-title", Static).content == "About"
        await pilot.press("escape")
        assert not isinstance(app.screen, _InfoModal)


async def test_readout_trend_coloring(gmc: GMCInterface, fake_serial) -> None:
    _register_gmc600(fake_serial)
    gmc._calibration_override = Calibration.from_factor(0.0065)
    app = GMCMonitorApp(gmc, interval=60.0)
    async with app.run_test():
        app._warmup_remaining = 0
        fake_serial.queue_bytes(struct.pack(">I", 5))
        await app._tick()  # CPM 0 -> 123 is a rise
        assert app.query_one("#cpm", Digits).has_class("rising")
        assert app.query_one("#usv", Digits).has_class("rising")

        app._apply_trend(-1)  # a drop flips to falling
        cpm = app.query_one("#cpm", Digits)
        assert cpm.has_class("falling") and not cpm.has_class("rising")


async def test_warmup_discards_initial_samples(gmc: GMCInterface, fake_serial) -> None:
    _register_gmc600(fake_serial)
    app = GMCMonitorApp(gmc, interval=60.0)
    async with app.run_test():
        # The first _WARMUP_SAMPLES heartbeat packets (often junk 0s) are dropped.
        for _ in range(_WARMUP_SAMPLES):
            fake_serial.queue_bytes(struct.pack(">I", 0))
        await app._tick()
        assert app.query_one("#cps", Digits).value == "0"
        assert "Samples: 0" in app.query_one("#stats", Static).content

        # Real samples after warmup are recorded normally.
        fake_serial.queue_bytes(struct.pack(">I", 7))
        await app._tick()
        assert app.query_one("#cps", Digits).value == "7"
        assert "Samples: 1" in app.query_one("#stats", Static).content


async def test_interval_keys_adjust_and_clamp(gmc: GMCInterface, fake_serial) -> None:
    _register_gmc600(fake_serial)
    app = GMCMonitorApp(gmc, interval=1.0)
    async with app.run_test() as pilot:
        await pilot.press("minus")
        assert app.interval == pytest.approx(1.5)
        await pilot.press("plus")
        assert app.interval == pytest.approx(1.0)

        # Clamps at the lower bound, staying on the 0.5s grid.
        for _ in range(5):
            await pilot.press("plus")
        assert app.interval == pytest.approx(0.5)

        label = app.query_one("#interval-label", Static).content
        assert "0.5s" in label


def test_init_clamps_out_of_range_interval(gmc: GMCInterface) -> None:
    assert GMCMonitorApp(gmc, interval=999.0).interval == pytest.approx(60.0)
    assert GMCMonitorApp(gmc, interval=0.0).interval == pytest.approx(0.5)
