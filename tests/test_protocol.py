"""Protocol-level tests verifying GQ-RFC1201 byte framing.

These confirm that parameters are sent as raw bytes (not ASCII hex), as the
spec requires, and that fixed-length responses parse back to the expected
Python types.
"""

import re
import struct
from datetime import datetime

import pytest

from gq_terminal import GMCError, GMCInterface


def test_get_version_decodes_ascii(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<GETVER>>", b"GMC-600  2.42  ")
    assert gmc.get_version() == "GMC-600  2.42"


def test_get_version_handles_15_byte_firmware(gmc: GMCInterface, fake_serial) -> None:
    """Regression: GMC-600+ Re.2.22 returns 15 bytes for GETVER.

    The original GQ-RFC1201 spec says 14. Reading exactly 14 would leave the
    trailing byte (the second '2' in "2.22") in the buffer, corrupting every
    subsequent command's response.
    """
    fake_serial.add_handler(b"<GETVER>>", b"GMC-600+Re 2.22")
    assert gmc.get_version() == "GMC-600+Re 2.22"
    assert fake_serial.in_waiting == 0, "GETVER must not leave bytes in the buffer"


def test_get_version_is_cached(gmc: GMCInterface, fake_serial) -> None:
    """Subsequent calls must not re-issue GETVER (it would be a wasted round-trip)."""
    fake_serial.add_handler(b"<GETVER>>", b"GMC-600+Re 2.22")
    gmc.get_version()
    write_count = sum(1 for w in fake_serial.writes if w == b"<GETVER>>")
    gmc.get_version()
    gmc.get_version()
    new_write_count = sum(1 for w in fake_serial.writes if w == b"<GETVER>>")
    assert new_write_count == write_count, "GETVER should be cached"


def test_get_config_handles_512_byte_firmware(gmc: GMCInterface, fake_serial) -> None:
    """Regression: GMC-500/600/800 firmware returns 512 bytes for GETCFG, not 256."""
    payload = bytes(range(256)) * 2
    fake_serial.add_handler(b"<GETCFG>>", payload)
    assert gmc.get_config() == payload
    assert fake_serial.in_waiting == 0


def test_get_cpm_legacy_2byte(gmc: GMCInterface, fake_serial) -> None:
    # GMC-300 family: GETVER prefix doesn't match 500/600/800, response is 2 bytes.
    fake_serial.add_handler(b"<GETVER>>", b"GMC-300Re 2.10")
    fake_serial.add_handler(b"<GETCPM>>", b"\x00\x1c")
    assert gmc.get_cpm() == 28


def test_get_cpm_modern_4byte(gmc: GMCInterface, fake_serial) -> None:
    """Regression: GMC-500/600/800 return CPM as 4 bytes (32-bit big-endian).

    Reading only 2 bytes leaves the rest in the buffer and corrupts every
    subsequent command's response.
    """
    fake_serial.add_handler(b"<GETVER>>", b"GMC-600+Re 2.2")
    fake_serial.add_handler(b"<GETCPM>>", b"\x00\x00\x01\x00")  # 256 CPM
    assert gmc.get_cpm() == 256


def test_get_cpm_modern_4byte_no_leftover_bytes(gmc: GMCInterface, fake_serial) -> None:
    """After GETCPM on a 600-series device, the input buffer must be empty."""
    fake_serial.add_handler(b"<GETVER>>", b"GMC-600+Re 2.2")
    fake_serial.add_handler(b"<GETCPM>>", b"\x00\x00\x00\x2a")
    assert gmc.get_cpm() == 42
    assert fake_serial.in_waiting == 0, "stale bytes would corrupt the next command"


def test_get_battery_voltage_byte_form(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<GETVOLT>>", bytes([62]))  # 6.2 V
    assert gmc.get_battery_voltage() == pytest.approx(6.2)


def test_get_battery_voltage_ascii_form(gmc: GMCInterface, fake_serial) -> None:
    # GMC-500/600 firmware variant returns ASCII like "4.5v"
    fake_serial.add_handler(b"<GETVOLT>>", b"4.5v\x00")
    assert gmc.get_battery_voltage() == pytest.approx(4.5)


def test_get_serial_returns_hex(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<GETSERIAL>>", bytes.fromhex("a1b2c3d4e5f600"))
    assert gmc.get_serial_number() == "a1b2c3d4e5f600"


def test_get_temperature_positive(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<GETTEMP>>", bytes([21, 5, 0, 0xAA]))
    assert gmc.get_temperature() == pytest.approx(21.5)


def test_get_temperature_negative(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<GETTEMP>>", bytes([3, 2, 1, 0xAA]))
    assert gmc.get_temperature() == pytest.approx(-3.2)


def test_get_gyroscope(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(
        b"<GETGYRO>>",
        struct.pack(">HHH", 100, 200, 300) + b"\xaa",
    )
    assert gmc.get_gyroscope() == (100, 200, 300)


def test_get_datetime(gmc: GMCInterface, fake_serial) -> None:
    # YY MM DD HH MM SS + 0xAA terminator
    fake_serial.add_handler(b"<GETDATETIME>>", bytes([26, 5, 11, 14, 30, 45, 0xAA]))
    assert gmc.get_datetime() == datetime(2026, 5, 11, 14, 30, 45)


def test_get_datetime_invalid_returns_none(gmc: GMCInterface, fake_serial) -> None:
    # Month 13 is invalid; spec-noncompliant device should not crash the client.
    fake_serial.add_handler(b"<GETDATETIME>>", bytes([26, 13, 11, 0, 0, 0, 0xAA]))
    assert gmc.get_datetime() is None


def test_set_datetime_sends_raw_bytes(gmc: GMCInterface, fake_serial) -> None:
    """Regression test: GQ-RFC1201 parameters must be raw bytes, not ASCII hex."""
    fake_serial.add_handler(re.compile(rb"<SETDATETIME......>>", re.DOTALL), b"\xaa")
    assert gmc.set_datetime(datetime(2026, 5, 11, 14, 30, 45)) is True
    sent = fake_serial.writes[-1]
    # Expect raw bytes 0x1A 0x05 0x0B 0x0E 0x1E 0x2D, NOT ASCII "1a050b0e1e2d"
    assert sent == b"<SETDATETIME" + bytes([26, 5, 11, 14, 30, 45]) + b">>"


def test_write_config_sends_raw_bytes(gmc: GMCInterface, fake_serial) -> None:
    """Regression test: GQ-RFC1201 parameters must be raw bytes, not ASCII hex."""
    fake_serial.add_handler(re.compile(rb"<WCFG..>>", re.DOTALL), b"\xaa")
    assert gmc.write_config(0x42, 0xFF) is True
    assert fake_serial.writes[-1] == b"<WCFG" + bytes([0x42, 0xFF]) + b">>"


def test_write_config_rejects_out_of_range(gmc: GMCInterface) -> None:
    with pytest.raises(ValueError):
        gmc.write_config(256, 0)
    with pytest.raises(ValueError):
        gmc.write_config(0, 256)


def test_get_history_sends_raw_bytes(gmc: GMCInterface, fake_serial) -> None:
    """Regression test: GQ-RFC1201 parameters must be raw bytes, not ASCII hex."""
    fake_serial.add_handler(re.compile(rb"<SPIR.....>>", re.DOTALL), b"\x00" * 16)
    gmc.get_history_data(address=0x010203, length=16)
    assert (
        fake_serial.writes[-1]
        == b"<SPIR" + bytes([0x01, 0x02, 0x03, 0x00, 0x10]) + b">>"
    )


def test_get_history_rejects_oversize(gmc: GMCInterface) -> None:
    with pytest.raises(ValueError):
        gmc.get_history_data(0, 5000)


def test_erase_config_acks(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<ECFG>>", b"\xaa")
    assert gmc.erase_config() is True


def test_factory_reset_requires_confirm(gmc: GMCInterface) -> None:
    with pytest.raises(GMCError):
        gmc.factory_reset()


def test_factory_reset_with_confirm(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<FACTORYRESET>>", b"\xaa")
    assert gmc.factory_reset(confirm=True) is True


def test_send_key_validates_range(gmc: GMCInterface) -> None:
    with pytest.raises(ValueError):
        gmc.send_key(4)


def test_send_key_uses_ascii_form(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(re.compile(rb"<KEY[0-3]>>"), b"")
    gmc.send_key(2)
    assert fake_serial.writes[-1] == b"<KEY2>>"


def test_heartbeat_flushes_buffer_on_start(gmc: GMCInterface, fake_serial) -> None:
    """start_heartbeat should clear any pre-existing buffered bytes."""
    fake_serial.add_handler(b"<GETVER>>", b"GMC-300Re 2.10")
    fake_serial.add_handler(b"<HEARTBEAT1>>", b"")
    # Warm the width cache so the queued "stale" bytes aren't consumed by GETVER.
    gmc._cpm_response_width()
    fake_serial.queue_bytes(b"stale-data")
    gmc.start_heartbeat()
    assert fake_serial.in_waiting == 0


def test_read_heartbeat_legacy_masks_top_two_bits(
    gmc: GMCInterface, fake_serial
) -> None:
    fake_serial.add_handler(b"<GETVER>>", b"GMC-300Re 2.10")
    fake_serial.add_handler(b"<HEARTBEAT1>>", b"")
    gmc.start_heartbeat()
    fake_serial.queue_bytes(b"\xff\xff")  # top bits should be masked off
    assert gmc.read_heartbeat() == 0x3FFF


def test_read_heartbeat_modern_4byte(gmc: GMCInterface, fake_serial) -> None:
    """GMC-500/600/800 stream 4-byte CPS packets in heartbeat mode."""
    fake_serial.add_handler(b"<GETVER>>", b"GMC-600+Re 2.2")
    fake_serial.add_handler(b"<HEARTBEAT1>>", b"")
    gmc.start_heartbeat()
    fake_serial.queue_bytes(b"\x00\x00\x01\x00")
    assert gmc.read_heartbeat() == 256


def test_read_heartbeat_returns_none_when_no_data(
    gmc: GMCInterface, fake_serial
) -> None:
    fake_serial.add_handler(b"<GETVER>>", b"GMC-300Re 2.10")
    fake_serial.add_handler(b"<HEARTBEAT1>>", b"")
    gmc.start_heartbeat()
    assert gmc.read_heartbeat() is None


def test_short_read_raises(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<GETVER>>", b"GMC-300Re 2.10")
    fake_serial.add_handler(b"<GETCPM>>", b"\x00")  # device only returns 1 of 2 bytes
    with pytest.raises(GMCError):
        gmc.get_cpm()


def test_context_manager_disconnects(fake_serial) -> None:
    with GMCInterface("FAKE") as gmc:
        assert gmc.serial_conn is not None
        assert gmc.serial_conn.is_open
    assert fake_serial.is_open is False
