#!/usr/bin/env python3
"""Real-time CPS monitoring example using heartbeat mode."""

import argparse
import sys
import time
from datetime import datetime

from gq_terminal import GMCError, GMCInterface


def main() -> int:
    parser = argparse.ArgumentParser(description="GMC real-time monitor")
    parser.add_argument("--port", required=True)
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()

    try:
        with GMCInterface(args.port, args.baudrate) as gmc:
            print(f"Connected to {gmc.get_version()}")
            print("Press Ctrl+C to stop\n")
            print(f"{'Time':<10}{'CPS':>6}")
            print("-" * 20)

            gmc.start_heartbeat()
            try:
                while True:
                    cps = gmc.read_heartbeat()
                    if cps is not None:
                        print(f"{datetime.now().strftime('%H:%M:%S'):<10}{cps:>6}")
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nStopping...")
            finally:
                gmc.stop_heartbeat()
    except GMCError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
