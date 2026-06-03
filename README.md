# GQ Terminal

[![CI](https://github.com/jmcmeen/gq-terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/jmcmeen/gq-terminal/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gq-terminal.svg)](https://pypi.org/project/gq-terminal/)
[![Python versions](https://img.shields.io/pypi/pyversions/gq-terminal.svg)](https://pypi.org/project/gq-terminal/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/1044659541.svg)](https://doi.org/10.5281/zenodo.20129915)

A Python library and command-line interface for [GQ GMC geiger
counters](https://www.gqelectronicsllc.com/), implementing the [GQ-RFC1201
protocol](https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt). GQ
publishes the protocol and
[encourages third-party software](https://www.gqelectronicsllc.com/comersus/store/download.asp).

> **⚠️  Not a certified instrument.** GQ GMC counters are hobbyist devices and
> this library is unaffiliated with GQ Electronics. **Do not use values from
> this software for safety-, regulatory-, or medical-decision-making.** The MIT
> license disclaims all warranty; the same applies to readings. See
> [DISCLAIMERS.md](DISCLAIMERS.md) for the full safety, hardware-coverage, and
> protocol-compatibility notes.

## Installation

```bash
pip install gq-terminal
```

For the interactive terminal dashboard, install the optional `tui` extra
(pulls in [Textual](https://github.com/Textualize/textual)):

```bash
pip install 'gq-terminal[tui]'
```

## Quick start

Talk to a counter from Python:

```python
from gq_terminal import GMCInterface

with GMCInterface('/dev/ttyUSB0', baudrate=115200) as gmc:
    print(gmc.get_version())              # e.g. "GMC-600  2.42"
    print(gmc.get_serial_number())        # 7-byte serial as hex
    print(f"{gmc.get_battery_voltage():.2f} V")
    print(f"CPM: {gmc.get_cpm()}")

    gmc.start_heartbeat()
    for _ in range(10):
        cps = gmc.read_heartbeat()
        if cps is not None:
            print(f"CPS: {cps}")
    gmc.stop_heartbeat()
```

The context manager raises `GMCError` on connection failure; outside a `with`
block, call `gmc.connect()` and check the boolean return.

Or from the shell:

```bash
gq-terminal info --port /dev/ttyUSB0      # device info + current readings
gq-terminal monitor --port /dev/ttyUSB0   # live readings in the terminal
gq-terminal tui --port /dev/ttyUSB0       # interactive dashboard (needs the 'tui' extra)
```

`--port` is optional — omit it to auto-detect (see [Port discovery](#port-discovery)).
The full set of subcommands is below.

## Command line

```bash
gq-terminal ports                     # list serial ports; likely-GMC ones flagged

gq-terminal info --port /dev/ttyUSB0
gq-terminal info --port /dev/ttyUSB0 --verbose

gq-terminal monitor --port /dev/ttyUSB0 --duration 60
gq-terminal tui     --port /dev/ttyUSB0     # interactive dashboard (needs the 'tui' extra)
gq-terminal log     --port /dev/ttyUSB0 --interval 60 --output radiation.csv

gq-terminal config read --port /dev/ttyUSB0
gq-terminal history --port /dev/ttyUSB0 --address 0 --length 1024

gq-terminal set-time --port /dev/ttyUSB0          # sync device clock to the computer
gq-terminal raw 'GETVER' --port /dev/ttyUSB0      # send a raw protocol command

gq-terminal --help
gq-terminal monitor --help
```

You can also invoke the CLI as a module: `python -m gq_terminal info ...`.

## Terminal dashboard

`gq-terminal tui` opens a live, full-screen dashboard built on
[Textual](https://github.com/Textualize/textual) — large CPS, CPM, µSv/h, and
mR/h readouts, a sparkline graph over time, battery, device
temperature/clock/gyroscope (where supported), and running statistics
(sample count, average/max/min CPS, total counts). The layout reflows: it
scrolls on a short terminal and the graph grows to fill a tall one. Keys: the
update interval is adjustable with `+` / `-`, the graph toggles between CPS and
CPM with `g`, `?` opens a glossary, `a` an about box, and `q` quits. It
requires the optional `tui` extra (`pip install 'gq-terminal[tui]'`); without
it the command prints an install hint and exits.

The dashboard is for live viewing; for durable, long-running capture use
`gq-terminal log`, which streams readings to a CSV file.

```bash
gq-terminal tui                       # auto-detect the port
gq-terminal tui --port /dev/ttyUSB0 --interval 0.5
gq-terminal tui --usv-per-cpm 0.0065  # supply a calibration for the dose readouts
```

## Dose rate (µSv/h, mR/h)

The protocol has no "read dose rate" command — the counter derives µSv/h from
CPM using a tube-specific **calibration**. `gq-terminal` mirrors this: `info`,
`monitor`, and `tui` show µSv/h and mR/h **only when a calibration is
available**. By default it reads the calibration stored on the device; pass
`--usv-per-cpm` (µSv/h per CPM, e.g. `0.0065`) to override it. In Python:

```python
from gq_terminal import GMCInterface, Calibration

# Use the device's stored calibration:
with GMCInterface("/dev/ttyUSB0") as gmc:
    print(gmc.get_dose_usv())   # µSv/h, or None if no calibration
    print(gmc.get_dose_mr())    # mR/h

# Or supply your own calibration explicitly:
with GMCInterface("/dev/ttyUSB0", calibration=Calibration.from_factor(0.0065)) as gmc:
    print(gmc.get_dose_usv())
```

> **⚠️  Dose rates are derived, not measured.** They depend entirely on the
> calibration and the tube, and the device-config offsets used to read the
> stored calibration are reverse-engineered (verify with `tools/diagnose.py`
> against your counter's on-screen calibration menu). This is **not** a
> certified dose — see the safety disclaimer at the top.

## Port discovery

`--port` is optional on every command. Omit it and the device is auto-detected:
the first serial port whose USB chip matches a GMC counter and that answers a
`GETVER` probe. If detection fails, the discovered ports are listed so you can
pass `--port` explicitly, and `gq-terminal ports` lists everything it sees.

```bash
gq-terminal info                      # auto-detect the port
```

The same discovery is available in Python via `discover_ports()` and
`find_gmc_port()`:

```python
from gq_terminal import GMCInterface, find_gmc_port

port = find_gmc_port()                # None if no GMC is found
if port:
    with GMCInterface(port) as gmc:
        print(gmc.get_version())
```

## Supported commands

Implements all 26 commands defined by GQ-RFC1201:

| Category | Methods |
| --- | --- |
| Basic | `get_version`, `get_cpm`, `get_battery_voltage`, `get_serial_number` |
| Dose rate (derived) | `get_calibration`, `get_dose_usv`, `get_dose_mr` (+ `Calibration`, `parse_calibration`) |
| Real-time | `start_heartbeat`, `stop_heartbeat`, `read_heartbeat` |
| Environment | `get_temperature`, `get_gyroscope` (GMC-320 Re.3.01+) |
| Real-time clock | `get_datetime`, `set_datetime` (GMC-280/300 Re.3.00+) |
| Memory | `get_history_data`, `get_config`, `write_config`, `erase_config`, `update_config` |
| Device control | `send_key`, `power_off`, `power_on`, `reboot`, `factory_reset` |
| Diagnostics | `send_raw`, `wrap_command` (exercise the protocol directly) |

## Serial configuration

| Setting | Default |
| --- | --- |
| Baud rate | 115200 (use 57600 for GMC-300 V3.xx and earlier) |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |
| Flow control | None |

## Troubleshooting

**Linux: `Permission denied: /dev/ttyUSB0`** — your user needs access to the
serial device. The portable fix is to add yourself to the `dialout` group
(`sudo usermod -a -G dialout $USER`) and log out / back in. Auto-detection
(`gq-terminal info` with no `--port`, or `find_gmc_port()`) hits the same
permission wall, so fix the group membership first.

**`gq-terminal ports` lists my device but auto-detect doesn't find it** — the
counter has to answer a `GETVER` probe to be auto-selected. Check the baud
rate (`--baudrate 57600` for older GMC-300 firmware) and that nothing else
holds the port open; or just pass `--port` explicitly.

**`Short read: expected N bytes, got 0`** — usually wrong baud rate (try 57600
for older firmware), wrong port, or the device is off. With heartbeat mode
running, do not interleave heartbeat reads with normal commands without first
calling `stop_heartbeat()`.

**Windows: which COM port?** — open Device Manager → Ports (COM & LPT) with
the device plugged in.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management
and a `Makefile` for common tasks.

```bash
git clone https://github.com/jmcmeen/gq-terminal
cd gq-terminal
make dev          # uv sync --extra dev
make test         # run the pytest suite
make check        # lint + typecheck + test (everything CI runs)
make build        # build sdist + wheel into dist/
make help         # list all targets
```

The test suite uses a fake serial backend, so no hardware is required.

If you don't have `uv` and don't want it, plain pip works too:

```bash
pip install -e ".[dev,tui]"
pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions (protocol invariants,
testing the wire bytes, style) before opening a PR.

## Citing

If you use this software in research, please cite it. The concept DOI
[10.5281/zenodo.20129915](https://doi.org/10.5281/zenodo.20129915) always
resolves to the latest release; each tagged release also gets its own
version-specific DOI on the same Zenodo page.

BibTeX:

```bibtex
@software{mcmeen_gq_terminal,
  author       = {McMeen, John},
  title        = {GQ Terminal: a Python interface for GQ GMC geiger counters},
  year         = {2026},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.20129915},
  url          = {https://github.com/jmcmeen/gq-terminal},
  orcid        = {0009-0003-8141-567X}
}
```

A machine-readable [`CITATION.cff`](CITATION.cff) is included in the repository.
GitHub renders a "Cite this repository" button from it.

## License

MIT — see [LICENSE](LICENSE).
