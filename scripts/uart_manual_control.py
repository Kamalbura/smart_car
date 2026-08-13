#!/usr/bin/env python3
"""Manual UART control: f/b/l/r/s + telemetry read.

Keys:
  f = forward
  b = backward
  l = left
  r = right
  s = stop
  q = quit (sends STOP)
"""
from __future__ import annotations

import sys
import threading
import time
import tty
import termios

try:
    import serial  # type: ignore
except Exception as exc:  # pragma: no cover
    print(f"pyserial not available: {exc}")
    raise SystemExit(1)

DEVICE = "/dev/serial0"
BAUD = 115200

COMMANDS = {
    "f": "FORWARD",
    "b": "BACKWARD",
    "l": "LEFT",
    "r": "RIGHT",
    "s": "STOP",
}


def telemetry_reader(ser: serial.Serial, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            line = ser.readline()
        except Exception:
            break
        if line:
            text = line.decode(errors="ignore").strip()
            if text:
                print(f"[RX] {text}")


def main() -> None:
    try:
        ser = serial.Serial(DEVICE, baudrate=BAUD, timeout=0.2)
    except Exception as exc:  # pragma: no cover
        print(f"Failed to open {DEVICE}: {exc}")
        raise SystemExit(1)

    stop_event = threading.Event()
    reader = threading.Thread(target=telemetry_reader, args=(ser, stop_event), daemon=True)
    reader.start()

    print("UART manual control ready.")
    print("Press f/b/l/r/s to send commands, q to quit.")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = sys.stdin.read(1)
            if not ch:
                time.sleep(0.05)
                continue
            ch = ch.lower()
            if ch == "q":
                ser.write(b"STOP\n")
                print("[TX] STOP")
                break
            cmd = COMMANDS.get(ch)
            if cmd:
                ser.write((cmd + "\n").encode())
                print(f"[TX] {cmd}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        stop_event.set()
        try:
            ser.write(b"STOP\n")
        except Exception:
            pass
        ser.close()


if __name__ == "__main__":
    main()
