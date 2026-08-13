#!/usr/bin/env python3
"""Simple wrapper to run the Pi inference module from the repo's scripts.

Usage:
  ./scripts/run_pi_inference.py --backend tflite --model models/yolov5n.tflite --img 320
"""
from __future__ import annotations

import argparse
import sys

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--backend", choices=("tflite", "onnx", "opencv"), default="tflite")
    p.add_argument("--model", required=True)
    p.add_argument("--img", type=int, default=640)
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--labels", type=str, default="models/vision/coco_labels.txt")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--iou", type=float, default=0.45)
    p.add_argument("--picam2", action="store_true")
    p.add_argument("--picam-width", type=int, default=832)
    p.add_argument("--picam-height", type=int, default=468)
    p.add_argument("--picam-fps", type=int, default=12)
    p.add_argument("--no-display", action="store_true")
    args = p.parse_args()
    # Defer to module to keep this script small
    from src.vision.pi_inference import main as pi_main

    # Build argv for the module
    sys.argv = [
        sys.argv[0],
        "--backend",
        args.backend,
        "--model",
        args.model,
        "--img",
        str(args.img),
        "--camera",
        str(args.camera),
        "--conf",
        str(args.conf),
        "--iou",
        str(args.iou),
        "--picam-width",
        str(args.picam_width),
        "--picam-height",
        str(args.picam_height),
        "--picam-fps",
        str(args.picam_fps),
    ]
    if args.labels:
        sys.argv.extend(["--labels", args.labels])
    if args.picam2:
        sys.argv.append("--picam2")
    if args.no_display:
        sys.argv.append("--no-display")
    pi_main()
