#!/usr/bin/env python3
"""Minimal example: connect to a GMC device and print its status."""

import argparse
import sys

from gq_terminal import GMCError, GMCInterface


def main() -> int:
    parser = argparse.ArgumentParser(description="GMC basic info readout")
    parser.add_argument(
        "--port", required=True, help="Serial port (e.g., COM3, /dev/ttyUSB0)"
    )
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()

    try:
        with GMCInterface(args.port, args.baudrate) as gmc:
            print(f"Model/Version : {gmc.get_version()}")
            print(f"Serial Number : {gmc.get_serial_number()}")
            print(f"Battery       : {gmc.get_battery_voltage():.2f} V")
            print(f"Current CPM   : {gmc.get_cpm()}")

            temp = gmc.get_temperature()
            if temp is not None:
                print(f"Temperature   : {temp:.1f} C")

            dt = gmc.get_datetime()
            if dt is not None:
                print(f"Device Time   : {dt}")
    except GMCError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
