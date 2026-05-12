"""Shared test fixtures: a fake serial.Serial that scripts device responses."""

import re
from collections.abc import Callable

import pytest

from gq_terminal import GMCInterface


class FakeSerial:
    """Minimal stand-in for serial.Serial that scripts a GMC device.

    Tests register handlers via ``add_handler(regex, response_bytes)``. When
    ``write`` is called with bytes matching a registered regex, the response
    is queued; subsequent ``read`` / ``in_waiting`` access drains it.
    """

    def __init__(self) -> None:
        self.is_open = True
        self._rx = bytearray()
        self._handlers: list[tuple[re.Pattern[bytes], Callable[[bytes], bytes]]] = []
        self.writes: list[bytes] = []

    # --- handler registration (test-side API) ---
    def add_handler(
        self,
        pattern: bytes | re.Pattern[bytes],
        response: bytes | Callable[[bytes], bytes],
    ) -> None:
        regex = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)
        if callable(response):
            self._handlers.append((regex, response))
        else:
            self._handlers.append((regex, lambda _m, r=response: r))

    def queue_bytes(self, data: bytes) -> None:
        """Push bytes onto the read buffer without involving a write."""
        self._rx.extend(data)

    # --- serial.Serial-compatible surface ---
    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        for pattern, handler in self._handlers:
            if pattern.fullmatch(data):
                self._rx.extend(handler(data))
                break
        return len(data)

    def flush(self) -> None:
        pass

    def read(self, n: int = 1) -> bytes:
        chunk = bytes(self._rx[:n])
        del self._rx[:n]
        return chunk

    @property
    def in_waiting(self) -> int:
        return len(self._rx)

    def reset_input_buffer(self) -> None:
        self._rx.clear()

    def close(self) -> None:
        self.is_open = False


@pytest.fixture
def fake_serial(monkeypatch) -> FakeSerial:
    """Patch ``serial.Serial`` so ``GMCInterface.connect`` returns a FakeSerial."""
    fake = FakeSerial()

    def _factory(*_args, **_kwargs) -> FakeSerial:
        return fake

    monkeypatch.setattr("gq_terminal.interface.serial.Serial", _factory)
    return fake


@pytest.fixture
def gmc(fake_serial: FakeSerial) -> GMCInterface:
    """A connected GMCInterface backed by the FakeSerial fixture."""
    iface = GMCInterface("FAKE", 115200, timeout=0.5)
    assert iface.connect()
    return iface
