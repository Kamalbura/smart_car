#!/usr/bin/env python3
"""UART control CLI for the ESP32 motor controller.

Modes:
    - Single: send one command and exit
    - Sequence: send a list with dwell spacing
    - Interactive: REPL to type commands in real time

Command aliases:
    f=FORWARD, b=BACKWARD, l=LEFT, r=RIGHT, s=STOP, st=STATUS
    servo:<angle> passes through (0-180)
    seq:<comma-separated> sends a sequence with dwell seconds between.

Examples:
    python tools/uart_cli.py --device /dev/ttyS0 --cmd f
    python tools/uart_cli.py --cmd seq:f,b,l,r,stop --dwell 1.5
    python tools/uart_cli.py --interactive

Prints ACK/DATA lines after each send.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import List

try:
    import serial  # type: ignore
except Exception as exc:  # pragma: no cover
    print(f"pyserial is required: {exc}", file=sys.stderr)
    sys.exit(1)

ALIASES = {
    "f": "FORWARD",
    "b": "BACKWARD",
    "l": "LEFT",
    "r": "RIGHT",
    "s": "STOP",
    "stop": "STOP",
    "st": "STATUS",
}


def normalize(token: str) -> str:
    t = token.strip()
    if t.lower().startswith("servo:"):
        return f"SERVO:{t.split(':',1)[1]}"
    if t.lower().startswith("seq:"):
        return f"SEQ:{t.split(':',1)[1]}"
    return ALIASES.get(t.lower(), t.upper())


def send_once(ser: "serial.Serial", cmd: str, read_s: float) -> None:
    ser.write((cmd + "\n").encode())
    ser.flush()
    print(f"TX {cmd}")
    end = time.time() + max(read_s, 0)
    while time.time() < end:
        line = ser.readline().decode("utf-8", "replace").strip()
        if line:
            print(f"RX {line}")


def run_sequence(ser: "serial.Serial", seq: List[str], dwell: float, read_s: float) -> None:
    for token in seq:
        cmd = normalize(token)
        if cmd.startswith("SEQ:"):
            continue  # nested seq not supported
        send_once(ser, cmd, read_s)
        time.sleep(max(dwell, 0))


def run_repl(ser: "serial.Serial", read_s: float) -> None:
    print("Interactive mode. Commands: f/b/l/r/s(st)/servo:90/seq:...; 'quit' to exit.")
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if raw.lower() in {"quit", "exit"}:
            break
        cmd_norm = normalize(raw)
        if cmd_norm.startswith("SEQ:"):
            tokens = [t for t in cmd_norm.split(":", 1)[1].split(",") if t]
            run_sequence(ser, tokens, dwell=0.0, read_s=read_s)
        else:
            send_once(ser, cmd_norm, read_s)


def main() -> None:
    ap = argparse.ArgumentParser(description="UART control CLI for ESP32 robot")
    ap.add_argument("--device", default="/dev/ttyS0", help="Serial device path")
    ap.add_argument("--baud", type=int, default=115200, help="Baud rate")
    ap.add_argument("--timeout", type=float, default=1.0, help="Serial timeout")
    ap.add_argument("--cmd", help="Command token or seq:<list>")
    ap.add_argument("--dwell", type=float, default=1.0, help="Seconds between sequence commands")
    ap.add_argument("--read", type=float, default=0.6, help="Seconds to read after each send")
    ap.add_argument("--interactive", action="store_true", help="Run in interactive mode (REPL)")
    args = ap.parse_args()

    try:
        ser = serial.Serial(port=args.device, baudrate=args.baud, timeout=args.timeout, write_timeout=args.timeout)
    except Exception as exc:  # pragma: no cover
        print(f"Failed to open {args.device}: {exc}", file=sys.stderr)
        sys.exit(1)

    ser.reset_input_buffer()

    if args.interactive:
        run_repl(ser, args.read)
    elif args.cmd:
        cmd_norm = normalize(args.cmd)
        if cmd_norm.startswith("SEQ:"):
            tokens = [t for t in cmd_norm.split(":",1)[1].split(",") if t]
            run_sequence(ser, tokens, args.dwell, args.read)
        else:
            send_once(ser, cmd_norm, args.read)
    else:
        print("--cmd is required unless --interactive is set", file=sys.stderr)
        sys.exit(2)

    ser.close()


if __name__ == "__main__":
    main()
