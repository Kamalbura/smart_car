#!/usr/bin/env python3
"""Render a simple smiley face to the SPI framebuffer (RGB565)."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
from struct import pack_into


def rgb565(r: int, g: int, b: int) -> int:
    """Convert 0-255 RGB values into a 16-bit RGB565 integer."""
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def read_geometry(fb_path: Path) -> tuple[int, int, int]:
    base = Path("/sys/class/graphics") / fb_path.name
    width = 480
    height = 320
    bpp = 16
    try:
        size_text = (base / "virtual_size").read_text().strip()
        w_str, h_str = size_text.split(",")
        width, height = int(w_str), int(h_str)
        bpp = int((base / "bits_per_pixel").read_text().strip())
    except FileNotFoundError:
        pass
    return width, height, bpp


def generate_smiley(width: int, height: int) -> bytearray:
    if width <= 0 or height <= 0:
        raise ValueError("invalid framebuffer geometry")
    buf = bytearray(width * height * 2)
    cx = width // 2
    cy = height // 2
    face_radius = int(min(width, height) * 0.4)
    eye_radius = max(3, face_radius // 8)
    eye_offset_x = face_radius // 2
    eye_offset_y = face_radius // 3
    mouth_radius = int(face_radius * 0.85)
    mouth_center_y = cy + face_radius // 3

    bg = rgb565(5, 5, 25)
    face = rgb565(255, 210, 0)
    eye = rgb565(0, 0, 0)
    highlight = rgb565(255, 255, 255)

    for y in range(height):
        for x in range(width):
            offset = 2 * (y * width + x)
            dx = x - cx
            dy = y - cy
            dist2 = dx * dx + dy * dy
            color = bg
            if dist2 <= face_radius * face_radius:
                color = face
                if dx * dx + dy * dy <= (face_radius // 2) ** 2 and dx < 0 and dy < 0:
                    color = highlight
            ex = x - (cx - eye_offset_x)
            ey = y - (cy - eye_offset_y)
            if ex * ex + ey * ey <= eye_radius * eye_radius:
                color = eye
            ex = x - (cx + eye_offset_x)
            if ex * ex + ey * ey <= eye_radius * eye_radius:
                color = eye
            mouth_dx = x - cx
            mouth_dy = y - mouth_center_y
            mouth_dist = math.hypot(mouth_dx, mouth_dy)
            if y >= mouth_center_y and abs(mouth_dist - mouth_radius) <= 2:
                color = eye
            pack_into("<H", buf, offset, color)
    return buf


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw a smiley face to the framebuffer display")
    parser.add_argument("--fb", default="/dev/fb0", help="Framebuffer device path (default: /dev/fb0)")
    args = parser.parse_args()

    fb_path = Path(args.fb)
    if not fb_path.exists():
        raise FileNotFoundError(f"Framebuffer device not found: {fb_path}")

    width, height, bpp = read_geometry(fb_path)
    if bpp != 16:
        raise RuntimeError(f"Only 16-bit RGB565 framebuffer supported (got {bpp} bpp)")

    frame = generate_smiley(width, height)
    with fb_path.open("r+b", buffering=0) as fb:
        fb.write(frame)


if __name__ == "__main__":
    main()
