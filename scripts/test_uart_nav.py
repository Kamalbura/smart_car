#!/usr/bin/env python3
"""UART navigation test: send movement commands and dump RX for 5 seconds.

Usage:
    python scripts/test_uart_nav.py [--device /dev/ttyAMA0] [--baud 115200] [--duration 5]
    
This opens the configured UART, sends forward/backward/left/right/stop commands
with brief durations, and prints any ESP32 responses received within the window.

Requires: pyserial
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import serial  # type: ignore
except Exception:
    serial = None

import sys
from pathlib import Path as _PathAlias

# Ensure project root is on sys.path so 'src' package is importable
PROJECT_ROOT = _PathAlias(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_config

DEFAULT_SEQUENCE = [
    ("forward", 100, 800),
    ("left", 80, 600),
    ("right", 80, 600),
    ("backward", 90, 800),
    ("stop", 0, 0),
]


def format_cmd(direction: str, speed: int, duration_ms: int, mapping: dict[str, str]) -> str:
    base = mapping.get(direction, "STOP")
    if direction == "stop" or duration_ms == 0:
        return f"{base}:{max(0, min(100, speed))}\n" if direction != "stop" else f"{base}\n"
    return f"{base}:{max(0, min(100, speed))}:{max(0, duration_ms)}\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="UART nav test")
    ap.add_argument("--device", default=None, help="UART device path override")
    ap.add_argument("--baud", type=int, default=None, help="Baud rate override")
    ap.add_argument("--duration", type=float, default=5.0, help="RX dump duration in seconds")
    args = ap.parse_args()

    if serial is None:
        print("pyserial not installed; install with pip install pyserial", file=sys.stderr)
        return 2

    cfg = load_config(Path("config/system.yaml"))
    nav = cfg.get("nav", {})
    device = args.device or nav.get("uart_device", "/dev/ttyAMA0")
    baud = args.baud or int(nav.get("baud_rate", 115200))
    timeout = float(nav.get("timeout", 1.0))
    mapping = {**{
        "forward": "FWD",
        "backward": "BWD",
        "left": "LEFT",
        "right": "RIGHT",
        "stop": "STOP",
    }, **nav.get("commands", {})}

    print(f"Opening UART {device} @ {baud} baud (timeout {timeout}s)")
    try:
        ser = serial.Serial(port=device, baudrate=baud, timeout=timeout, write_timeout=timeout)
    except Exception as e:
        print(f"Failed to open UART {device}: {e}", file=sys.stderr)
        return 1

    try:
        # Send sequence
        for direction, speed, dur in DEFAULT_SEQUENCE:
            cmd = format_cmd(direction, speed, dur, mapping)
            print(f"TX: {cmd.strip()}")
            ser.write(cmd.encode("utf-8"))
            ser.flush()
            # Small gap between commands
            time.sleep(0.3)

        # Dump RX
        print(f"\nReading RX for {args.duration:.1f}s...")
        end = time.time() + args.duration
        while time.time() < end:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode("utf-8", errors="replace").strip()
                    if line:
                        print(f"RX: {line}")
                else:
                    time.sleep(0.05)
            except Exception as e:
                print(f"UART read error: {e}")
                time.sleep(0.1)

        # Final stop for safety
        ser.write(f"{mapping.get('stop','STOP')}\n".encode("utf-8"))
        ser.flush()
        print("Sent STOP")
        return 0
    finally:
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
