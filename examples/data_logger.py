#!/usr/bin/env python3
"""Simple CSV data-logging example.

For richer logging (status indicators, automatic filenames), use the bundled
CLI instead: ``gq-terminal log --port /dev/ttyUSB0 --interval 60``.
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

from gq_terminal import GMCError, GMCInterface


def main() -> int:
    parser = argparse.ArgumentParser(description="GMC CSV data logger")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument(
        "--interval", type=float, default=60.0, help="Seconds between samples"
    )
    parser.add_argument("--output", default=None, help="CSV output path")
    args = parser.parse_args()

    out = Path(
        args.output
        or f"radiation_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    with out.open("w", newline="") as f:
        csv.writer(f).writerow(["timestamp", "cpm", "battery_voltage", "temperature"])

    try:
        with GMCInterface(args.port, args.baudrate) as gmc:
            print(f"Connected to {gmc.get_version()}")
            print(f"Logging to {out} every {args.interval}s (Ctrl+C to stop)\n")
            try:
                while True:
                    iter_start = time.time()
                    row = [
                        datetime.now().isoformat(),
                        gmc.get_cpm(),
                        f"{gmc.get_battery_voltage():.2f}",
                    ]
                    temp = gmc.get_temperature()
                    row.append(f"{temp:.1f}" if temp is not None else "")
                    with out.open("a", newline="") as f:
                        csv.writer(f).writerow(row)
                    print(f"  {row[0]}  CPM={row[1]}  V={row[2]}")
                    elapsed = time.time() - iter_start
                    if elapsed < args.interval:
                        time.sleep(args.interval - elapsed)
            except KeyboardInterrupt:
                print("\nStopped")
    except GMCError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
