#!/usr/bin/env python3
"""Minimal camera test script using OpenCV.

Stops any running vision service (already done separately), then
opens /dev/video0 (or a user-specified index) and grabs a few
frames to confirm that the camera can be read from *core* without
any other services using it.
"""

from __future__ import annotations

import argparse
import time

import cv2


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple camera reader")
    parser.add_argument("--index", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--frames", type=int, default=20, help="Number of frames to grab")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.index)
    if not cap.isOpened():
        print(f"ERROR: Could not open camera index {args.index}")
        return

    print(f"Opened camera index {args.index}; grabbing {args.frames} frames...")
    ok_count = 0

    for i in range(args.frames):
        ok, frame = cap.read()
        if not ok or frame is None:
            print(f"Frame {i}: FAILED to read")
        else:
            h, w = frame.shape[:2]
            ok_count += 1
            print(f"Frame {i}: OK ({w}x{h})")
        time.sleep(0.05)

    cap.release()
    print(f"Done. Successful frames: {ok_count}/{args.frames}")


if __name__ == "__main__":
    main()
