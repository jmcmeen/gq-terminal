# Disclaimers

These notes back the short disclaimer at the top of the [README](README.md).

## ⚠️ Not a certified instrument

GQ GMC counters are hobbyist devices and this library is unaffiliated with GQ
Electronics. **Do not use values from this software for safety-, regulatory-,
or medical-decision-making.** Counts and rates depend on calibration, geometry,
isotope, and instrument health — verifying any of that is the user's
responsibility. The MIT license disclaims all warranty; the same applies to
readings.

Dose rates (µSv/h, mR/h) are **derived** from CPM via a tube-specific
calibration, not measured. They are only as good as that calibration and are
not certified.

## 🔬 Hardware coverage

The only configuration verified end-to-end against a physical device is
**GMC-600+ firmware Re.2.22**. The GMC-280, GMC-300, GMC-320, GMC-500 series,
and other GMC-600 firmware revisions *should* work — the library auto-detects
the family and adjusts the protocol accordingly — but those code paths are
exercised only by the test suite, not against real hardware. If you have one of
these and it works (or doesn't), please open an issue with the output of
`python tools/diagnose.py`.

The reverse-engineered config offsets used to read the device's stored
calibration are likewise unverified beyond the GMC-600+; confirm them with
`tools/diagnose.py` against your counter's on-screen calibration menu before
relying on derived dose rates.

## 📡 Protocol is a moving target

GQ Electronics ships firmware revisions that diverge from the
[GQ-RFC1201](https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt) spec
without updating the document (we know of at least: 15-byte GETVER on Re.2.22,
512-byte GETCFG on 500/600/800-series, 4-byte CPM on the same). If your device
returns unexpected data, run `python tools/diagnose.py --port <port>` and
attach the output to a bug report.
