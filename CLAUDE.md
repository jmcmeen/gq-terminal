# CLAUDE.md

Working notes for Claude (and humans) collaborating on this repository. Read
this before making non-trivial changes.

## What this project is

A Python library and CLI for talking to GQ GMC geiger counters over a serial
port using the [GQ-RFC1201](https://www.gqelectronicsllc.com/download/GQ-RFC1201.txt)
protocol. Released on PyPI as `gq-terminal` and archived on Zenodo (each
GitHub release mints a DOI).

It is a **scientific instrument library**. Two consequences:

1. **Correctness matters more than features.** A subtle parsing bug in
   `get_cpm` produces silently-wrong radiation readings, which is bad. Prefer
   careful, narrow changes over broad refactors; add a regression test for
   every protocol-encoding fix.
2. **Citability matters.** Behavior of a tagged release is treated as
   archival. Don't quietly change semantics of public methods after a
   release — bump the version and changelog the break.

## Repository layout

```
src/gq_terminal/        # importable package
  __init__.py           # re-exports public API; reads version via importlib.metadata
  __main__.py           # `python -m gq_terminal` entry point
  interface.py          # GMCInterface — the protocol implementation
  cli.py                # click-based command-line interface
tests/                  # pytest suite, no hardware required
  conftest.py           # FakeSerial fixture (scripts device responses)
  test_protocol.py      # protocol byte-framing and parsing regression tests
  test_cli.py           # click CliRunner smoke tests
examples/               # standalone scripts; not shipped in the wheel
.github/workflows/      # CI (test matrix + lint + build) and PyPI publish
pyproject.toml          # hatchling build, ruff/black/mypy/pytest config
uv.lock                 # locked dev environment (commit this)
Makefile                # `make dev`, `make test`, `make check`, `make build`
CITATION.cff            # citation metadata (read by Zenodo + GitHub)
.zenodo.json            # Zenodo deposit metadata
CHANGELOG.md            # Keep a Changelog format
```

## Invariants (don't break these)

### Protocol layer (`interface.py`)

- **Parameters are raw bytes, not ASCII hex.** GQ-RFC1201 §"Command format"
  says "All parameters of command are true value in hexadecimal" — meaning
  raw byte values. `SETDATETIME`, `WCFG`, and `SPIR` were broken in early
  drafts of this code because the params were sent as ASCII digits. If you
  add a new command that takes parameters, send raw bytes (use `bytes([...])`
  or `struct.pack`), and add a regression test asserting the exact wire bytes.
- **GQ-RFC1201 documents the GMC-280/300 family; the 500/600/800 family
  diverges silently.** Known divergences (all verified on a GMC-600+ Re.2.22):
  | Command | Spec | 500/600/800 firmware |
  | --- | --- | --- |
  | GETVER  | 14 bytes ASCII | 15 bytes (e.g. `GMC-600+Re 2.22`) |
  | GETCPM  | 2 bytes BE uint16 | 4 bytes BE uint32 |
  | GETVOLT | 1 byte × 10 V | 5-byte ASCII (`b"4.3v\x00"`) |
  | GETCFG  | 256 bytes | 512 bytes |
  | HEARTBEAT stream | 2-byte packets | 4-byte packets |

  Fixed-width reads use `_send(..., n)`. Variable-width reads use
  `_drain_response(...)`, which polls `in_waiting` until it stops growing.
  **Anything firmware-dependent uses the drain path.**
- **Family detection** runs on first call to `_cpm_response_width()`, which
  caches the result. It also triggers via `start_heartbeat()` so the stream
  reader doesn't need to query GETVER mid-stream. Detection is purely on the
  GETVER hardware-model prefix (`GMC-500` / `GMC-600` / `GMC-800` → 4-byte
  family; everything else → 2-byte family).
- **Heartbeat mode corrupts the input buffer.** After `HEARTBEAT1`, the
  device streams 2- or 4-byte CPS packets every second (width matches GETCPM).
  Always `reset_input_buffer()` after sending `HEARTBEAT0`, and before sending
  any non-heartbeat command. `start_heartbeat` / `stop_heartbeat` already do this.
- **Library code does not print.** Errors raise `GMCError` (or subclass).
  `logger.exception(...)` for diagnostics. The CLI is the only layer that
  writes to stdout/stderr.
- **`factory_reset()`, `erase_config()`, `power_off()` are destructive.**
  `factory_reset` requires `confirm=True`. Don't add new destructive methods
  without a similar guard.

### Public API (`__init__.py`)

`GMCInterface`, `GMCError`, `GMCNotConnectedError`, and `__version__` are
the four public names. Adding a new public symbol means:
1. Add it to `__all__` in `__init__.py`.
2. Document it in README.
3. Mention it in the next CHANGELOG entry.

Renaming or removing any of those four is a breaking change → minor-version
bump while pre-1.0, major after.

### CLI (`cli.py`)

- Every subcommand takes `--port`, `--baudrate`, `--timeout` via the
  `common_options` decorator. Don't define these inline.
- Errors from the library are caught at the subcommand boundary and printed
  in red via `click.style(..., fg="red")`. Don't let `GMCError` propagate
  out of click — it produces an ugly traceback for users.
- `click.echo(color=...)` takes a *boolean* (force on/off), not a color
  name. Use `click.style(text, fg="...")` for colored text.

### Tests

- **No real hardware in CI.** Use the `FakeSerial` fixture from
  `conftest.py`. If you need a new device behavior, add a handler to it.
- **Test wire bytes, not just return values.** Protocol regression tests
  should assert `fake_serial.writes[-1] == b"<CMD" + bytes([...]) + b">>"`,
  not just that the high-level method returned `True`.
- The pyserial `loop://` URL was considered but rejected — it can't script
  the request→response semantics this protocol needs.

## Working agreements

### Dependency management

- `uv` is the source of truth. `make dev` (= `uv sync --extra dev`) bootstraps
  the venv at `.venv/`. `uv.lock` is committed.
- pyproject.toml uses static `version = "..."` (read at runtime via
  `importlib.metadata`). When bumping, change exactly one place
  (`pyproject.toml`) and update `CITATION.cff` and `CHANGELOG.md` to match.
- `pip install -e ".[dev]"` still works as a fallback for users without uv.

### Style

- `ruff` + `black`, line length 88. Both run in CI; pre-commit hooks would
  be welcome.
- Runtime target is Python 3.10+; `X | None` and `tuple[int, int]` work
  natively. Don't add `from __future__ import annotations` — it's unnecessary
  here and just adds noise.
- Default to no comments. Write a comment only when the *why* is non-obvious
  (a hidden constraint, a workaround for a device quirk, a subtle invariant).
  Don't comment what the code does — names should carry that.
- No docstrings on every helper, but every public method on `GMCInterface`
  gets one. Document non-obvious return-shape quirks (e.g. firmware-dependent
  response formats).

### When you fix a protocol bug

1. Add a regression test in `tests/test_protocol.py` that asserts the exact
   wire bytes, named `test_<method>_sends_raw_bytes` (or similar).
2. Add a Fixed entry to `CHANGELOG.md`. If the bug shipped, also call it out
   in the README troubleshooting section so users know which versions to
   upgrade past.
3. The bug is almost never "the library returned `False` instead of `True`."
   It's almost always "the library encoded params wrong, so the device
   silently rejected the command." Read the bytes, not the return value.

### When you add a new command

1. Look it up in the RFC (fetch the spec from gqelectronicsllc.com — we don't
   bundle it). Note the response length and any firmware-version gating.
2. Add the method to `GMCInterface`.
   - Parameters → raw bytes (`bytes([...])` or `struct.pack`).
   - Fixed-length response → `self._send(self._wrap("CMDNAME", params), n)`.
   - Variable / firmware-dependent length → `self._drain_response(...)`.
3. Add a test scripting the FakeSerial response and asserting the parse.
4. If it's user-facing, add a CLI subcommand (or extend `info`).
5. Update README's "Supported commands" table and CHANGELOG.

### Debugging firmware quirks

Use `tools/diagnose.py` to dump raw bytes from each command, with BE and LE
interpretations for the numeric ones. This is how we found the GETVER-15-bytes
and GETCFG-512-bytes divergences on the GMC-600+. If a parsed value looks
wrong, run the diagnostic first — the answer is almost always "the device sent
N bytes but we read N-1" or "the device used BE but we assumed LE" (or vice
versa). Add a regression test the moment you confirm the cause.

### When you cut a release

1. Update `version` in `pyproject.toml` and `CITATION.cff`.
2. Move the Unreleased CHANGELOG section under a dated heading.
3. `make check` and `make build`; confirm `twine check dist/*` is clean.
4. Tag `vX.Y.Z` on `main` and create a GitHub Release. The
   `publish.yml` workflow does the PyPI upload via trusted publishing.
5. Zenodo auto-mints a DOI from the GitHub Release; update the README badge
   if needed.

## Things to avoid

- **Don't restructure for theoretical reuse.** The library is small. A second
  `GMCInterface` implementation is not coming. If you're tempted to extract a
  `Protocol` ABC, don't.
- **Don't bundle the GQ-RFC1201 spec file.** It's third-party copyrighted.
  Link to the official URL instead.
- **Don't add a logging handler in library code.** We get `logger` and call
  `.exception()`; the application configures handlers.
- **Don't introduce a new build backend.** `hatchling` is fine. Anything else
  (poetry, setuptools, flit) is churn.
- **Don't add dev-only files to the wheel.** Examples and tests are sdist-only
  via `[tool.hatch.build.targets.sdist] include`.
- **Don't `--no-verify` past pre-commit / CI failures.** They almost always
  point at a real problem.

## Useful commands

```bash
make help            # list all targets
make dev             # uv sync --extra dev
make test            # pytest
make test-cov        # pytest with coverage
make lint            # ruff + black --check
make format          # auto-fix
make typecheck       # mypy
make check           # lint + typecheck + test
make build           # build sdist + wheel
make clean           # remove build/test artifacts

uv run python -m gq_terminal info --port /dev/ttyUSB0   # exercise the CLI
uv run pytest -k protocol -v                            # narrow test run
uv run pytest --pdb                                     # drop into debugger on failure
```
