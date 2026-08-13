"""Generate a small representative dataset for TFLite int8 quantization.

Usage:
  python tools/rep_dataset.py --src path/to/images --out rep_images --count 100 --size 320

This script copies/resizes images into a folder suitable for use by a
representative dataset generator.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from PIL import Image


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--size", type=int, default=320)
    args = p.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    files = list(src.glob("**/*.[jp][pn]g"))
    if not files:
        print("No images found in source")
        return

    for i, f in enumerate(files[: args.count]):
        im = Image.open(f).convert("RGB")
        im = im.resize((args.size, args.size), Image.ANTIALIAS)
        im.save(out / f"rep_{i:04d}.jpg", quality=90)


if __name__ == "__main__":
    main()
