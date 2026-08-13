#!/usr/bin/env python3
"""Display expression control tool.

Changes the face expression on the TFT display by:
1. Stopping the display service temporarily
2. Rendering the requested expression
3. Optionally restarting the service

Usage:
    python tools/display_expression.py HAPPY
    python tools/display_expression.py LISTENING --duration 5
    python tools/display_expression.py --cycle  # Cycle through all expressions
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

EXPRESSIONS = [
    "BASE", "HAPPY", "LISTENING", "SPEAKING", "SURPRISED",
    "CURIOUS", "SAD", "LOOK_LEFT", "LOOK_RIGHT", "LOOK_UP",
    "LOOK_DOWN", "SLEEP", "EXCITED"
]

FACE_CMD_BASE = [
    "/usr/bin/python3", "-m", "src.ui.face_fb",
    "--rotate=180", "--swap-rb",
    "--eye-scale=0.75", "--mouth-scale=0.75", "--blush-scale=0.4",
    "--fbdev=/dev/fb0", "--no-blink"
]


def stop_display_service():
    """Stop the systemd display service."""
    subprocess.run(["sudo", "systemctl", "stop", "display.service"], 
                   capture_output=True, check=False)
    time.sleep(0.3)


def start_display_service():
    """Start the systemd display service."""
    subprocess.run(["sudo", "systemctl", "start", "display.service"],
                   capture_output=True, check=False)


def show_expression(expression: str, duration: float = 3.0):
    """Show a specific expression for the given duration."""
    if expression.upper() not in EXPRESSIONS:
        print(f"Unknown expression: {expression}")
        print(f"Available: {', '.join(EXPRESSIONS)}")
        return False
    
    cmd = FACE_CMD_BASE + [f"--state={expression.upper()}"]
    print(f"🎭 Showing: {expression.upper()} for {duration}s")
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd="/home/dev/project_root"
    )
    
    time.sleep(duration)
    proc.terminate()
    proc.wait(timeout=2)
    return True


def cycle_expressions(duration: float = 2.0):
    """Cycle through all expressions."""
    print("🔄 Cycling through all expressions...")
    stop_display_service()
    
    for expr in EXPRESSIONS:
        show_expression(expr, duration)
    
    print("✅ Cycle complete")


def main():
    parser = argparse.ArgumentParser(description="Control TFT display expression")
    parser.add_argument("expression", nargs="?", default=None,
                       help=f"Expression to show: {', '.join(EXPRESSIONS)}")
    parser.add_argument("--duration", "-d", type=float, default=3.0,
                       help="Duration to show expression (default: 3s)")
    parser.add_argument("--cycle", "-c", action="store_true",
                       help="Cycle through all expressions")
    parser.add_argument("--no-restore", action="store_true",
                       help="Don't restart display service after")
    parser.add_argument("--list", "-l", action="store_true",
                       help="List available expressions")
    args = parser.parse_args()
    
    if args.list:
        print("Available expressions:")
        for expr in EXPRESSIONS:
            print(f"  • {expr}")
        return
    
    if args.cycle:
        cycle_expressions(args.duration)
        if not args.no_restore:
            print("🔄 Restarting display service...")
            start_display_service()
        return
    
    if not args.expression:
        parser.print_help()
        return
    
    stop_display_service()
    show_expression(args.expression, args.duration)
    
    if not args.no_restore:
        print("🔄 Restarting display service...")
        start_display_service()
    
    print("✅ Done")


if __name__ == "__main__":
    main()
