import mmap
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 480, 320
BPP = 16
FB_SIZE = WIDTH * HEIGHT * (BPP // 8)
FONT_PATH = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

def rgb888_to_rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def render_pattern() -> bytes:
    palette = [
        ("RED", (255, 0, 0)),
        ("GREEN", (0, 255, 0)),
        ("BLUE", (0, 0, 255)),
        ("YELLOW", (255, 255, 0)),
        ("CYAN", (0, 255, 255)),
        ("MAGENTA", (255, 0, 255)),
    ]

    img = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(img)
    font = (
        ImageFont.truetype(str(FONT_PATH), 32)
        if FONT_PATH.exists()
        else ImageFont.load_default()
    )

    section_h = HEIGHT // len(palette)
    for idx, (label, color) in enumerate(palette):
        top = idx * section_h
        draw.rectangle([(0, top), (WIDTH, top + section_h)], fill=color)
        bbox = font.getbbox(label)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            (WIDTH - text_w - 20, top + section_h // 2 - text_h // 2),
            label,
            fill=(0, 0, 0) if sum(color) > 360 else (255, 255, 255),
            font=font,
        )

    # Gradient on the right third for contrast response
    grad_left = int(WIDTH * 0.65)
    for x in range(grad_left, WIDTH):
        ratio = (x - grad_left) / (WIDTH - grad_left - 1)
        band_color = (
            int(255 * ratio),
            int(255 * ((1 - abs(0.5 - ratio) * 2))),
            int(255 * (1 - ratio)),
        )
        draw.line([(x, 0), (x, HEIGHT)], fill=band_color)

    buffer = bytearray(FB_SIZE)
    pixels = list(img.getdata())
    for idx, (r, g, b) in enumerate(pixels):
        buffer[idx * 2:(idx * 2) + 2] = rgb888_to_rgb565(r, g, b).to_bytes(2, "little")
    return bytes(buffer)


def main() -> None:
    fbdev = Path(os.getenv("FBDEV", "/dev/fb0"))
    if not fbdev.exists():
        raise FileNotFoundError(f"Missing framebuffer device {fbdev}")

    pattern = render_pattern()
    with fbdev.open("r+b", buffering=0) as fb:
        with mmap.mmap(fb.fileno(), FB_SIZE, mmap.MAP_SHARED, mmap.PROT_WRITE) as mm:
            mm[: len(pattern)] = pattern


if __name__ == "__main__":
    main()
