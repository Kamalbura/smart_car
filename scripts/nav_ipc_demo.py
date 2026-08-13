#!/usr/bin/env python3
"""Publish navigation commands over IPC for 2s each.

This drives the existing UART bridge (`motor_bridge.py` or `bridge.py`) which
subscribes to `nav.command` on the downstream bus. Use this when you want to
exercise the full stack without opening serial directly in this script.

Sequence: forward -> left -> right -> backward -> stop

Usage:
  python scripts/nav_ipc_demo.py [--speed 80] [--duration 2.0]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import sys
from pathlib import Path as _Path

# Ensure project root is on sys.path for "src" imports when run directly
PROJECT_ROOT = _Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_config
from src.core.ipc import TOPIC_NAV, make_publisher, publish_json

SEQUENCE = [
    ("forward", 80),
    ("left", 70),
    ("right", 70),
    ("backward", 75),
    ("stop", 0),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="IPC nav publisher demo")
    ap.add_argument("--speed", type=int, default=None, help="Override speed percent")
    ap.add_argument("--duration", type=float, default=2.0, help="Duration per movement in seconds")
    args = ap.parse_args()

    cfg = load_config(Path("config/system.yaml"))
    pub = make_publisher(cfg, channel="downstream")

    for direction, default_speed in SEQUENCE:
        speed = args.speed if args.speed is not None else default_speed
        payload = {
            "direction": direction,
            "speed": speed,
            "duration_ms": int(args.duration * 1000) if direction != "stop" else 0,
        }
        publish_json(pub, TOPIC_NAV, payload)
        print(f"sent NAV: {payload}")
        # Wait for movement duration; UART bridge will also read RX in background
        time.sleep(args.duration)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
