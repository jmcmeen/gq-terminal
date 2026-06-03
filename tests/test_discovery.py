"""Tests for serial-port discovery (discover_ports / find_gmc_port)."""

import re
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from gq_terminal import discover_ports, find_gmc_port
from gq_terminal.cli import main

CH340 = (0x1A86, 0x7523)


def _port(device: str, vid: int | None, pid: int | None, desc: str = ""):
    """Build a stand-in for serial.tools.list_ports_common.ListPortInfo."""
    return SimpleNamespace(device=device, vid=vid, pid=pid, description=desc)


@pytest.fixture
def fake_comports(monkeypatch):
    """Patch serial.tools.list_ports.comports to return a scripted port list."""

    def _set(ports: list) -> None:
        monkeypatch.setattr("gq_terminal.interface.list_ports.comports", lambda: ports)

    return _set


def test_discover_ports_ranks_known_chip_first(fake_comports):
    fake_comports(
        [
            _port("/dev/ttyS0", None, None, "builtin"),
            _port("/dev/ttyUSB0", *CH340, "USB Serial"),
        ]
    )
    result = discover_ports()
    assert [p.device for p in result] == ["/dev/ttyUSB0", "/dev/ttyS0"]
    assert result[0].likely_gmc is True
    assert result[1].likely_gmc is False


def test_discover_ports_stable_within_group(fake_comports):
    # Two non-candidate ports keep their enumeration order.
    fake_comports(
        [
            _port("/dev/ttyS1", None, None),
            _port("/dev/ttyS0", None, None),
        ]
    )
    assert [p.device for p in discover_ports()] == ["/dev/ttyS1", "/dev/ttyS0"]


def test_find_gmc_port_probes_candidate_and_matches(fake_comports, fake_serial):
    fake_serial.add_handler(re.compile(rb"<GETVER>>"), b"GMC-600+Re 2.22")
    fake_comports([_port("/dev/ttyUSB0", *CH340, "USB Serial")])
    assert find_gmc_port() == "/dev/ttyUSB0"


def test_find_gmc_port_skips_non_gmc_reply(fake_comports, fake_serial):
    fake_serial.add_handler(re.compile(rb"<GETVER>>"), b"not-a-geiger-counter")
    fake_comports([_port("/dev/ttyUSB0", *CH340, "USB Serial")])
    assert find_gmc_port() is None


def test_find_gmc_port_ignores_unlikely_ports_by_default(fake_comports):
    # A non-USB port is never opened (no serial patching needed); if it were
    # probed this would raise rather than return None.
    fake_comports([_port("/dev/ttyS0", None, None, "builtin")])
    assert find_gmc_port() is None


def test_find_gmc_port_probe_all_probes_unlikely_port(fake_comports, fake_serial):
    # probe_all=True opts into probing ports not flagged likely_gmc.
    fake_serial.add_handler(re.compile(rb"<GETVER>>"), b"GMC-320Re 3.01")
    fake_comports([_port("/dev/ttyS0", None, None, "builtin")])
    assert find_gmc_port() is None  # default skips the unlikely port
    assert find_gmc_port(probe_all=True) == "/dev/ttyS0"


def test_ports_command_flags_likely_gmc(fake_comports):
    fake_comports([_port("/dev/ttyUSB0", *CH340, "USB Serial")])
    result = CliRunner().invoke(main, ["ports"])
    assert result.exit_code == 0
    assert "/dev/ttyUSB0" in result.output
    assert "1a86:7523" in result.output
    assert "likely GMC" in result.output
