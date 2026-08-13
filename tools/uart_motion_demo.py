#!/usr/bin/env python3
"""Send a short motion sequence to the ESP32 motor controller over UART.

Sequence (each ~2s by default): FORWARD -> BACKWARD -> LEFT -> RIGHT -> STOP.
Captures and prints any responses (ACK/DATA/STATUS) while running.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Iterable

try:
    import serial  # type: ignore
except Exception as exc:  # pragma: no cover
    print(f"pyserial is required: {exc}", file=sys.stderr)
    sys.exit(1)


COMMANDS = ["FORWARD", "BACKWARD", "LEFT", "RIGHT", "STOP"]


def send_and_listen(ser: "serial.Serial", cmd: str, dwell: float) -> None:
    ser.write((cmd + "\n").encode())
    ser.flush()
    print(f"TX {cmd}")
    end = time.time() + dwell
    while time.time() < end:
        line = ser.readline().decode("utf-8", "replace").strip()
        if line:
            print(f"RX {line}")
        time.sleep(0.05)


def run_sequence(device: str, baud: int, timeout: float, dwell: float) -> None:
    try:
        ser = serial.Serial(port=device, baudrate=baud, timeout=timeout, write_timeout=timeout)
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"Failed to open {device}: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        for cmd in COMMANDS:
            send_and_listen(ser, cmd, dwell)
    finally:
        ser.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="UART motion demo sequence")
    ap.add_argument("--device", default="/dev/ttyAMA0", help="Serial device path")
    ap.add_argument("--baud", type=int, default=115200, help="Baud rate")
    ap.add_argument("--timeout", type=float, default=1.0, help="Serial timeout")
    ap.add_argument("--dwell", type=float, default=2.0, help="Seconds to hold each command")
    args = ap.parse_args()

    run_sequence(args.device, args.baud, args.timeout, max(args.dwell, 0))


if __name__ == "__main__":
    main()
