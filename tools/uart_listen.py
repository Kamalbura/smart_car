#!/usr/bin/env python3
"""Quick UART listener for ESP32 motor controller.

Reads lines for a short duration to verify wiring and firmware output.
"""
from __future__ import annotations

import argparse
import sys
import time

try:
    import serial  # type: ignore
except Exception as exc:  # pragma: no cover
    print(f"pyserial is required: {exc}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Listen to UART for a few seconds")
    ap.add_argument("--device", default="/dev/ttyAMA0", help="Serial device path")
    ap.add_argument("--baud", type=int, default=115200, help="Baud rate")
    ap.add_argument("--timeout", type=float, default=1.0, help="Read timeout seconds")
    ap.add_argument("--duration", type=float, default=5.0, help="Listen duration seconds")
    args = ap.parse_args()

    try:
        ser = serial.Serial(
            port=args.device,
            baudrate=args.baud,
            timeout=args.timeout,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"Failed to open {args.device}: {exc}", file=sys.stderr)
        sys.exit(1)

    end = time.time() + max(args.duration, 0)
    print(f"Listening on {args.device} @ {args.baud} for {args.duration:.1f}s...")
    try:
        while time.time() < end:
            line = ser.readline().decode("utf-8", "replace").strip()
            if line:
                print(line)
    finally:
        ser.close()


if __name__ == "__main__":
    main()
