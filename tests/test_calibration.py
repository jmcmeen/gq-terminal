"""Tests for CPM→dose calibration parsing and conversion.

The config byte offsets these exercise are reverse-engineered (see
``parse_calibration``); these tests pin the *parsing logic* against synthetic
bytes we control, not the real-device layout.
"""

import struct

import pytest

from gq_terminal import Calibration, GMCInterface, parse_calibration

# A typical ~0.0065 µSv/h-per-CPM tube calibration (three points).
_POINTS = [(60, 0.39), (240, 1.56), (1000, 6.5)]


def _config_with_calibration(points, order: str = ">") -> bytes:
    buf = bytearray(512)
    for off, (cpm, usv) in zip((8, 14, 20), points, strict=False):
        buf[off : off + 2] = int(cpm).to_bytes(2, "big")
        buf[off + 2 : off + 6] = struct.pack(f"{order}f", usv)
    return bytes(buf)


def test_parse_calibration_big_endian() -> None:
    cal = parse_calibration(_config_with_calibration(_POINTS, ">"))
    assert cal is not None
    assert len(cal.points) == 3
    assert cal.points[0][0] == 60.0
    assert cal.cpm_to_usv(60) == pytest.approx(0.39, rel=1e-4)


def test_parse_calibration_falls_back_to_little_endian() -> None:
    # Packed little-endian; big-endian reading would be implausible, so the
    # parser should detect and prefer the little-endian interpretation.
    cal = parse_calibration(_config_with_calibration(_POINTS, "<"))
    assert cal is not None
    assert cal.cpm_to_usv(240) == pytest.approx(1.56, rel=1e-4)


def test_parse_calibration_rejects_garbage() -> None:
    assert parse_calibration(bytes(512)) is None  # all zeros → no points
    assert parse_calibration(b"\x00\x01") is None  # too short


def test_parse_calibration_rejects_implausible_factor() -> None:
    # 1 µSv/h at 1 CPM is a factor of 1.0 — outside the plausible range.
    assert parse_calibration(_config_with_calibration([(1, 1.0)])) is None


def test_calibration_interpolates_through_origin() -> None:
    cal = Calibration([(60, 0.39), (240, 1.56)])
    assert cal.cpm_to_usv(0) == pytest.approx(0.0)
    assert cal.cpm_to_usv(30) == pytest.approx(0.195)
    assert cal.cpm_to_usv(150) == pytest.approx(0.975)


def test_calibration_extrapolates_past_last_point() -> None:
    cal = Calibration([(240, 1.56), (1000, 6.5)])
    assert cal.cpm_to_usv(2000) == pytest.approx(13.0, rel=1e-4)


def test_calibration_mr_is_usv_over_ten() -> None:
    cal = Calibration.from_factor(0.0065)
    assert cal.cpm_to_mr(100) == pytest.approx(cal.cpm_to_usv(100) / 10.0)


def test_from_factor_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        Calibration.from_factor(0)


def test_get_calibration_reads_and_caches_config(
    gmc: GMCInterface, fake_serial
) -> None:
    fake_serial.add_handler(b"<GETCFG>>", _config_with_calibration(_POINTS))
    cal = gmc.get_calibration()
    assert cal is not None and cal.cpm_to_usv(60) == pytest.approx(0.39, rel=1e-4)

    gmc.get_calibration()
    writes = sum(1 for w in fake_serial.writes if w == b"<GETCFG>>")
    assert writes == 1, "config (and parsed calibration) should be cached"


def test_explicit_calibration_overrides_device(gmc: GMCInterface, fake_serial) -> None:
    gmc._calibration_override = Calibration.from_factor(0.01)
    assert gmc.get_calibration().cpm_to_usv(100) == pytest.approx(1.0)
    # Override must not touch the device config.
    assert not any(w == b"<GETCFG>>" for w in fake_serial.writes)


def test_get_dose_usv_and_mr(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<GETVER>>", b"GMC-600+Re 2.22")
    fake_serial.add_handler(b"<GETCPM>>", struct.pack(">I", 100))
    gmc._calibration_override = Calibration.from_factor(0.0065)
    assert gmc.get_dose_usv() == pytest.approx(0.65)
    assert gmc.get_dose_mr() == pytest.approx(0.065)


def test_get_dose_usv_none_without_calibration(gmc: GMCInterface, fake_serial) -> None:
    fake_serial.add_handler(b"<GETCFG>>", bytes(512))  # no calibration present
    assert gmc.get_dose_usv() is None
