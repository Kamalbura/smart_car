#!/usr/bin/env python3
"""Enumerate cameras and capture a single frame from each.

This script scans /dev/video* devices, attempts to open each index
with OpenCV, grabs one frame, and saves any successful captures as
PNG files in the current directory (e.g. camera_0.png).

Use the vision virtualenv (which has OpenCV installed):

    . .venvs/visn/bin/activate
    python tools/capture_cameras.py
"""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
from typing import List

import cv2


def _list_video_indices(max_index: int | None = None) -> List[int]:
    """Return a sorted list of candidate camera indices.

    We look at /dev/video* to find existing device nodes, then map
    them back to integer indices. Optionally clamp to max_index.
    """

    paths = sorted(glob.glob("/dev/video*"))
    indices: set[int] = set()
    for p in paths:
        name = os.path.basename(p)
        # expect videoN
        if name.startswith("video") and name[5:].isdigit():
            idx = int(name[5:])
            indices.add(idx)
    if max_index is not None:
        indices = {i for i in indices if i <= max_index}
    return sorted(indices)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe cameras and capture one frame each")
    parser.add_argument(
        "--max-index",
        type=int,
        default=None,
        help="Optional maximum camera index to probe (defaults to all /dev/video* indices)",
    )
    parser.add_argument(
        "--frames-to-try",
        type=int,
        default=5,
        help="Number of read attempts per camera before giving up",
    )
    args = parser.parse_args()

    indices = _list_video_indices(args.max_index)
    if not indices:
        print("No /dev/video* devices found.")
        return

    print(f"Found candidate video indices: {indices}")

    out_dir = Path.cwd()
    success_any = False

    for idx in indices:
        print(f"\n[Camera {idx}] Opening...")
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            print(f"  ERROR: Could not open camera index {idx}")
            continue

        frame = None
        ok = False
        for attempt in range(args.frames_to_try):
            ok, frame = cap.read()
            if ok and frame is not None:
                print(f"  Frame {attempt}: OK ({frame.shape[1]}x{frame.shape[0]})")
                break
            else:
                print(f"  Frame {attempt}: FAILED to read")

        cap.release()

        if not ok or frame is None:
            print(f"  Giving up on camera {idx} after {args.frames_to_try} attempts.")
            continue

        out_path = out_dir / f"camera_{idx}.png"
        if cv2.imwrite(str(out_path), frame):
            print(f"  Saved snapshot to {out_path}")
            success_any = True
        else:
            print(f"  ERROR: Failed to write image to {out_path}")

    if not success_any:
        print("\nNo cameras produced a valid frame.")
    else:
        print("\nDone. At least one camera produced a saved frame.")


if __name__ == "__main__":
    main()
