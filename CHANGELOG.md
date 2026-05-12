# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — Unreleased

Initial public release.

### Supported Python versions
- Python **3.10+**. Earlier versions (3.8, 3.9) are past their upstream EOL
  and are not supported.

### Hardware tested
- **GMC-600+ Re.2.22** — `get_version`, `get_serial_number`,
  `get_battery_voltage`, `get_cpm`, `get_temperature`, `get_gyroscope`,
  `get_datetime`, `get_config`, `get_history_data`, and `set_datetime`
  verified end-to-end against a live device.

### Features
- Full implementation of the 26 commands defined by [GQ-RFC1201](https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt).
- Python API via `GMCInterface`, usable as a context manager
  (`with GMCInterface(port) as gmc: ...`).
- Command-line interface with `info`, `monitor`, `log`, `history`, `key`, and
  `config` subcommands.
- Real-time CPS monitoring via heartbeat mode; CSV logging.
- Test suite using a fake serial backend — no hardware required to run.

### Implementation notes
- Protocol parameters (`set_datetime`, `write_config`, `get_history_data`) are
  sent as raw bytes per the GQ-RFC1201 spec.
- Library code does not print to stdout; communication errors raise `GMCError`.
- `factory_reset()` requires `confirm=True` to prevent accidental wipes.
- `start_heartbeat` / `stop_heartbeat` flush the input buffer so subsequent
  commands aren't corrupted by residual stream bytes.
- `get_serial_number` returns the 7-byte serial as a lowercase hex string.

#### Firmware-dependent response handling

GQ-RFC1201 was written for the GMC-280/300 series; the GMC-500/600/800 family
diverged from the published spec without updating it. This release accommodates
both:

- **GETVER** length is 14 bytes per spec, but 15 on at least GMC-600+ Re.2.22.
  Drained dynamically and cached.
- **GETCPM** is 2 bytes (big-endian uint16) on GMC-280/300/320 and 4 bytes
  (big-endian uint32) on GMC-500/600/800. Family auto-detected from GETVER.
- **Heartbeat CPS** packets follow the same width as GETCPM.
- **GETVOLT** is 1 raw byte (value × 10 V) on legacy firmware, or a 5-byte
  ASCII string like `b"4.3v\x00"` on the 500/600 series. Drained dynamically.
- **GETCFG** is 256 bytes per spec, but 512 on GMC-500/600/800 firmware.
  Drained dynamically.
