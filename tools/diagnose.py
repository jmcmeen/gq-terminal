#!/usr/bin/env python3
"""Dump raw bytes returned by each GQ-RFC1201 command, with BE/LE interpretations.

Use this to debug firmware-specific quirks (e.g. byte order for GETCPM on the
500/600 series, response width for GETVOLT). Compare what you see on the
device's LCD against the parsed values printed here.

Usage:
    python tools/diagnose.py --port /dev/ttyUSB0
"""

import argparse
import sys
import time

from gq_terminal.interface import GMCInterface


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
        show("GETCFG     (256 bytes)", drain(gmc, b"<GETCFG>>", settle=0.5))
        show("GETTEMP    (4 bytes: int, dec, sign, 0xAA)", drain(gmc, b"<GETTEMP>>"))
        show("GETGYRO    (7 bytes: XX YY ZZ + 0xAA)", drain(gmc, b"<GETGYRO>>"))
        show("GETDATETIME (7 bytes: YY MM DD HH MM SS + 0xAA)",
             drain(gmc, b"<GETDATETIME>>"))
    finally:
        gmc.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
