# GQ Terminal

A Python library and command-line interface for [GQ GMC geiger counters](https://www.gqelectronicsllc.com/),
implementing the [GQ-RFC1201 protocol](https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt).

Primary development and testing is on the **GMC-600**. The library is designed
to also work with the GMC-280, GMC-300, GMC-320, and GMC-500 series, but
those are not regularly verified — bug reports welcome.

## Installation

```bash
pip install gq-terminal
```

## Quick start

### Python API

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

The context manager raises `GMCError` on connection failure. Outside a
`with` block, call `gmc.connect()` and check the boolean return.

### Command line

```bash
gq-terminal info --port /dev/ttyUSB0
gq-terminal info --port /dev/ttyUSB0 --verbose

gq-terminal monitor --port /dev/ttyUSB0 --duration 60
gq-terminal log     --port /dev/ttyUSB0 --interval 60 --output radiation.csv

gq-terminal config read --port /dev/ttyUSB0
gq-terminal history --port /dev/ttyUSB0 --address 0 --length 1024

gq-terminal --help
gq-terminal monitor --help
```

You can also invoke the CLI as a module: `python -m gq_terminal info ...`.

## Supported commands

Implements all 26 commands defined by GQ-RFC1201:

| Category | Methods |
| --- | --- |
| Basic | `get_version`, `get_cpm`, `get_battery_voltage`, `get_serial_number` |
| Real-time | `start_heartbeat`, `stop_heartbeat`, `read_heartbeat` |
| Environment | `get_temperature`, `get_gyroscope` (GMC-320 Re.3.01+) |
| Real-time clock | `get_datetime`, `set_datetime` (GMC-280/300 Re.3.00+) |
| Memory | `get_history_data`, `get_config`, `write_config`, `erase_config`, `update_config` |
| Device control | `send_key`, `power_off`, `power_on`, `reboot`, `factory_reset` |

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
(`sudo usermod -a -G dialout $USER`) and log out / back in.

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
pip install -e ".[dev]"
pytest
```

## Citing

If you use this software in research, please cite it. A `CITATION.cff` is
included in the repository, and tagged releases are archived on Zenodo with
DOIs — see the badge on the GitHub repository.

## License

MIT — see [LICENSE](LICENSE).
