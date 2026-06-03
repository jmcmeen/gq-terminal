# Contributing to gq-terminal

Thanks for your interest! This is a small, focused library for talking to GQ
GMC Geiger counters over serial. Contributions are welcome — bug reports,
hardware test reports, and pull requests alike.

It's a **scientific instrument library**, so correctness matters more than
features: a subtle parsing bug produces silently-wrong radiation readings.
Please read these notes before opening a non-trivial PR. (Contributors working
with an AI assistant: the deeper conventions live in [CLAUDE.md](CLAUDE.md).)

## Development setup

This project uses [uv](https://docs.astral.sh/uv/) and a `Makefile`:

```bash
git clone https://github.com/jmcmeen/gq-terminal
cd gq-terminal
make dev        # install with dev + TUI extras into .venv/
make check      # lint + typecheck + test — run this before pushing
```

Plain pip works too if you don't want uv: `pip install -e ".[dev,tui]"`.

Useful targets: `make test`, `make test-cov`, `make lint`, `make format`
(auto-fix), `make typecheck`, `make build`, `make help`.

## Ground rules

- **No hardware required.** Tests use the `FakeSerial` fixture in
  `tests/conftest.py`, which scripts device responses. Don't add tests that
  need a real counter. If you need a new device behavior, add a handler.
- **Test the wire bytes, not just return values.** Protocol parameters are
  raw bytes per GQ-RFC1201 (not ASCII hex). For any protocol change, assert the
  exact bytes sent, e.g. `fake_serial.writes[-1] == b"<CMD" + bytes([...]) + b">>"`.
  Most protocol bugs are "encoded the params wrong," not "returned False."
- **Mind the firmware families.** The GMC-500/600/800 family diverges from the
  published spec (15-byte GETVER, 4-byte CPM, 512-byte GETCFG, …). Fixed-width
  reads use `_send(..., n)`; variable/firmware-dependent reads use
  `_drain_response(...)`. Add a regression test when you fix a quirk.
- **Library code doesn't print.** Errors raise `GMCError` (or a subclass); use
  `logger.exception(...)` for diagnostics. Only the CLI/TUI layers write to the
  screen.
- **Don't weaken the safety posture.** The disclaimer (see
  [DISCLAIMERS.md](DISCLAIMERS.md)) is load-bearing: this is not a certified
  instrument. Don't add language anywhere that reads as a calibration or
  accuracy guarantee ("accurate readings", "reliable measurements", a
  "certified" mode, etc.). Derived values like µSv/h must stay clearly marked
  as derived, not measured.
- **Keep it small.** Don't restructure for theoretical reuse, swap the build
  backend (hatchling stays), or bundle the third-party GQ-RFC1201 spec (link to
  it instead).

## Style

- `ruff` + `black`, line length 88 (both enforced in CI; `make format` fixes).
- Target Python **3.10+**; `X | None` / `tuple[int, int]` work natively. Don't
  add `from __future__ import annotations`.
- Default to no comments; write one only when the *why* is non-obvious. Every
  public method on `GMCInterface` gets a docstring (note any firmware-dependent
  return shapes).

## Pull requests

1. Branch off `main`.
2. Make the change, add tests, and run `make check` until it's green.
3. Update `CHANGELOG.md` (Keep a Changelog format), and the README if it's
   user-facing.
4. If you added a public name to `GMCInterface`/the package, add it to
   `__all__`, document it, and changelog it.
5. Open the PR describing what changed and why. CI runs the test matrix + lint
   on Linux/macOS/Windows.

Please don't bypass failing pre-commit/CI checks (`--no-verify`); they almost
always point at a real problem.

## Reporting hardware results

Only the GMC-600+ (Re.2.22) is verified end-to-end against real hardware. If
you have another GMC model, please open an issue with the output of
`python tools/diagnose.py --port <port>` — especially if a reading looks wrong.
That diagnostic dumps raw bytes (with BE/LE interpretations) and the parsed
calibration, which is exactly what's needed to confirm or fix a firmware quirk.

## License

By contributing, you agree your contributions are licensed under the project's
[MIT License](LICENSE).
