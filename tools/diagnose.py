#!/usr/bin/env python3
"""Dump raw bytes returned by each GQ-RFC1201 command, with BE/LE interpretations.

Use this to debug firmware-specific quirks (e.g. byte order for GETCPM on the
500/600 series, response width for GETVOLT). Compare what you see on the
device's LCD against the parsed values printed here.

Usage:
    python tools/diagnose.py --port /dev/ttyUSB0
"""

import argparse
import struct
import sys
import time

from gq_terminal.interface import _CAL_POINT_OFFSETS, GMCInterface, parse_calibration


def show(label: str, data: bytes) -> None:
    print(f"\n{label}")
    print(f"  raw bytes ({len(data)}): {data.hex(' ')}")
    print(f"  as ascii: {data.decode('ascii', errors='replace')!r}")
    if len(data) == 2:
        print(f"  BE uint16: {int.from_bytes(data, 'big')}")
        print(f"  LE uint16: {int.from_bytes(data, 'little')}")
    elif len(data) == 4:
        print(f"  BE uint32: {int.from_bytes(data, 'big')}")
        print(f"  LE uint32: {int.from_bytes(data, 'little')}")


def show_calibration(config: bytes) -> None:
    """Dump the candidate calibration table so offsets can be verified.

    Compare the CPM/µSv-per-point values printed here against the device's
    on-screen calibration menu. If they don't line up, the offsets in
    interface._CAL_POINT_OFFSETS (or the float byte order) need adjusting.
    """
    print("\nCALIBRATION (reverse-engineered offsets — verify against device menu)")
    if not config:
        print("  no config bytes")
        return
    for i, off in enumerate(_CAL_POINT_OFFSETS):
        if off + 6 > len(config):
            print(f"  point {i}: offset {off} out of range (config is {len(config)}B)")
            continue
        cpm = int.from_bytes(config[off : off + 2], "big")
        be = struct.unpack(">f", config[off + 2 : off + 6])[0]
        le = struct.unpack("<f", config[off + 2 : off + 6])[0]
        print(f"  point {i} @ off {off}: CPM(BE16)={cpm}  µSv/h BE={be:.6g} LE={le:.6g}")
    for order, name in ((">", "big-endian"), ("<", "little-endian")):
        cal = parse_calibration(config, float_order=order)
        pts = cal.points if cal else None
        print(f"  parsed ({name} floats): {pts}")


def drain(gmc: GMCInterface, command: bytes, settle: float = 0.2) -> bytes:
    """Send a command, wait, return whatever the device buffered up."""
    assert gmc.serial_conn is not None
    gmc.serial_conn.reset_input_buffer()
    gmc.serial_conn.write(command)
    gmc.serial_conn.flush()
    time.sleep(settle)
    return gmc.serial_conn.read(gmc.serial_conn.in_waiting)


def main() -> int:
    parser = argparse.ArgumentParser(description="GMC raw-byte diagnostic")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()

    gmc = GMCInterface(args.port, args.baudrate)
    if not gmc.connect():
        print(f"Could not open {args.port}", file=sys.stderr)
        return 1
    try:
        show("GETVER     (expect 14 ASCII bytes)", drain(gmc, b"<GETVER>>"))
        show("GETSERIAL  (expect 7 bytes)", drain(gmc, b"<GETSERIAL>>"))
        show("GETVOLT    (1 byte legacy, 5-6 bytes ASCII on 500/600)",
             drain(gmc, b"<GETVOLT>>"))
        show("GETCPM     (2 bytes legacy, 4 bytes on 500/600/800)",
             drain(gmc, b"<GETCPM>>"))
        config = drain(gmc, b"<GETCFG>>", settle=0.5)
        show("GETCFG     (256 bytes)", config)
        show_calibration(config)
        show("GETTEMP    (4 bytes: int, dec, sign, 0xAA)", drain(gmc, b"<GETTEMP>>"))
        show("GETGYRO    (7 bytes: XX YY ZZ + 0xAA)", drain(gmc, b"<GETGYRO>>"))
        show("GETDATETIME (7 bytes: YY MM DD HH MM SS + 0xAA)",
             drain(gmc, b"<GETDATETIME>>"))
    finally:
        gmc.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
