#!/usr/bin/env python3
"""Kawaii-style face UI for the Waveshare 3.5" TFT.

Port of the reference Pi implementation, adjusted for this repo and
this device. The main change is that the default framebuffer is now
``/dev/fb0`` (our ILI9486 panel), instead of ``/dev/fb1``.

Rendering is done into an off-screen ``pygame.Surface`` and then copied
directly into the framebuffer using RGB565 via ``mmap``. This avoids
depending on SDL's ``fbcon`` backend, matching how the reference Pi
implementation talked to the TFT.
"""

from __future__ import annotations

import argparse
import json
import math
import mmap
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import pygame
import zmq

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_config
from src.core.ipc import TOPIC_DISPLAY_STATE, TOPIC_DISPLAY_TEXT, make_subscriber


# Default to the SPI framebuffer + touchscreen; callers can override before import.
os.environ.setdefault("SDL_FBDEV", "/dev/fb0")
os.environ.setdefault("SDL_MOUSEDEV", "/dev/input/event0")
os.environ.setdefault("SDL_MOUSEDRV", "TSLIB")
# This UI doesn't need audio, but SDL/pygame will try to initialize it by default.
# On systems where the default ALSA device is shared with TTS, this can block audio playback.
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUSH_PINK = (255, 192, 203)


# Our device's TFT is on fb0 (fb_ili9486)
DEFAULT_FB = "/dev/fb0"


# runtime adjustable appearance
BLUSH_SCALE_ADJUST = 1.0
EYE_SCALE_ADJUST = 1.0
SOLID_EYES = False
MOUTH_SCALE_ADJUST = 0.9


def _read_fb_geometry(fbdev: str) -> tuple[int, int, int]:
    """Return ``(width, height, stride)`` for the framebuffer.

    Uses sysfs if available, otherwise falls back to 480x320 RGB565.
    """

    fb_path = Path(fbdev)
    base = Path("/sys/class/graphics") / fb_path.name
    width = 480
    height = 320
    stride = width * 2

    try:
        with (base / "virtual_size").open() as f:
            raw = f.read().strip()
        parts = raw.split(",")
        if len(parts) == 2:
            width = int(parts[0])
            height = int(parts[1])
    except Exception:
        pass

    try:
        with (base / "stride").open() as f:
            stride = int(f.read().strip())
    except Exception:
        stride = width * 2

    return width, height, stride


def _surface_to_rgb565(surface: pygame.Surface) -> np.ndarray:
    arr = pygame.surfarray.array3d(surface)
    frame = np.transpose(arr, (1, 0, 2)).astype(np.uint16)
    r = frame[:, :, 0]
    g = frame[:, :, 1]
    b = frame[:, :, 2]
    packed = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return packed.astype("<u2", copy=False)


def _ellipsize_text(text: str, font: pygame.font.Font, max_width: int) -> str:
    if not text:
        return ""
    text = text.strip()
    if font.size(text)[0] <= max_width:
        return text
    ellipsis = "…"
    while text and font.size(text + ellipsis)[0] > max_width:
        text = text[:-1]
    return text + ellipsis


class FramebufferWriter:
    def __init__(self, fbdev: str, *, rotate: int = 0):
        self.fbdev = Path(fbdev)
        self.width, self.height, self.stride = _read_fb_geometry(fbdev)
        self.rotate = rotate % 360
        self.size = self.stride * self.height
        self._file = self.fbdev.open("r+b", buffering=0)
        self._mmap = mmap.mmap(self._file.fileno(), self.size, mmap.MAP_SHARED, mmap.PROT_WRITE)

    def close(self) -> None:
        try:
            self._mmap.close()
        finally:
            self._file.close()

    def write_surface(self, surface: pygame.Surface) -> None:
        if self.rotate:
            rotated = pygame.transform.rotate(surface, self.rotate)
            if rotated.get_size() != (self.width, self.height):
                rotated = pygame.transform.smoothscale(rotated, (self.width, self.height))
            target = rotated
        else:
            target = surface

        rgb565 = _surface_to_rgb565(target)
        data = rgb565.tobytes()
        if self.stride == self.width * 2:
            self._mmap.seek(0)
            self._mmap.write(data)
        else:
            row_bytes = self.width * 2
            idx = 0
            for y in range(self.height):
                start = y * self.stride
                end = start + row_bytes
                chunk = data[idx : idx + row_bytes]
                self._mmap[start:end] = chunk
                idx += row_bytes
        self._mmap.flush()


# Expression tuning (relative offsets so everything scales with the screen).
STATE_RULES: dict[str, dict[str, object]] = {
    "BASE": {
        "pupil": (0.0, 0.0),
        "mouth": "soft_smile",
        "blush": 1.0,
        "inner_alpha": 0,
        # slightly smaller default eye size
        "eye_scale": 0.95,
        "highlight": "simple",
        "solid_blush": True,
        # use the global BLUSH_PINK constant for a softer pink
        "blush_color": BLUSH_PINK,
    },
    "HAPPY": {
        "pupil": (0.0, -0.15),
        "mouth": "beam",
        "blush": 1.4,
        "inner_color": (45, 45, 45),
        "inner_alpha": 235,
    },
    "LISTENING": {
        "pupil": (0.0, -0.3),
        "mouth": "soft_smile",
        "blush": 1.1,
        "inner_color": (38, 38, 38),
        "inner_alpha": 215,
    },
    "SPEAKING": {
        "pupil": (0.0, 0.0),
        "mouth": "talk",
        "blush": 1.2,
        "inner_color": (36, 36, 36),
        "inner_alpha": 230,
    },
    "SURPRISED": {
        "pupil": (0.0, -0.05),
        "mouth": "o",
        "blush": 0.6,
        "eye_scale": 1.05,
        "inner_color": (230, 230, 230),
        "inner_alpha": 255,
    },
    "CURIOUS": {
        "pupil": (-0.35, -0.1),
        "mouth": "soft_smile",
        "blush": 1.0,
        "inner_color": (45, 45, 45),
        "inner_alpha": 225,
    },
    "SAD": {
        "pupil": (0.0, 0.25),
        "mouth": "sad",
        "blush": 0.4,
        "inner_color": (32, 32, 32),
        "inner_alpha": 210,
    },
    "LOOK_LEFT": {
        "pupil": (-0.6, -0.05),
        "mouth": "soft_smile",
        "blush": 0.9,
        "inner_color": (40, 40, 40),
        "inner_alpha": 220,
    },
    "LOOK_RIGHT": {
        "pupil": (0.6, -0.05),
        "mouth": "soft_smile",
        "blush": 0.9,
        "inner_color": (40, 40, 40),
        "inner_alpha": 220,
    },
    "LOOK_UP": {
        "pupil": (0.0, -0.6),
        "mouth": "soft_smile",
        "blush": 0.9,
        "inner_color": (38, 38, 38),
        "inner_alpha": 220,
    },
    "LOOK_DOWN": {
        "pupil": (0.0, 0.6),
        "mouth": "flat",
        "blush": 0.7,
        "inner_color": (35, 35, 35),
        "inner_alpha": 210,
    },
    "SLEEP": {
        "eye_open": 0.0,
        "mouth": "flat",
        "blush": 0.5,
        "inner_alpha": 0,
    },
    "EXCITED": {
        "pupil": (0.0, -0.1),
        "mouth": "beam",
        "blush": 1.6,
        "eye_scale": 1.05,
        "inner_color": (45, 45, 45),
        "inner_alpha": 200,
        "highlight": "rotating",
        "highlight_speed": 220,
    },
}


current_state = "BASE"


def _swap_color(col: tuple[int, int, int], swap: bool) -> tuple[int, int, int]:
    if not swap:
        return col
    return (col[2], col[1], col[0])


def _draw_blush(
    screen: pygame.Surface,
    cfunc,
    center: tuple[int, int],
    radius: int,
    strength: float,
    *,
    solid: bool = False,
    override_color: tuple[int, int, int] | None = None,
) -> None:
    alpha = 255 if solid else max(0, min(255, int(95 * strength)))
    if alpha == 0:
        return
    surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    base_color = BLUSH_PINK if override_color is None else override_color
    blush_rgb = cfunc(base_color)
    pygame.draw.circle(surf, (*blush_rgb, alpha), (radius, radius), radius)
    screen.blit(surf, (center[0] - radius, center[1] - radius))


def _draw_highlights(
    screen: pygame.Surface,
    cfunc,
    eye_center: tuple[int, int],
    eye_radius: int,
    style: str = "default",
    angle: float = 0.0,
) -> None:
    """Draw highlights for an eye.

    ``style`` can be ``'simple'``, ``'default'`` or ``'rotating'``.
    ``angle`` (degrees) is used for rotating highlight styles.
    """

    if style == "none":
        return
    if style == "simple":
        highlight_radius = max(4, int(eye_radius * 0.22))
        offset = int(eye_radius * 0.4)
        pygame.draw.circle(
            screen,
            cfunc(WHITE),
            (eye_center[0] - offset, eye_center[1] - offset),
            highlight_radius,
        )
        return

    main_radius = int(eye_radius * 0.42)
    small_radius = max(2, int(eye_radius * 0.18))
    offset = int(eye_radius * 0.45)
    # main white eye area
    pygame.draw.circle(
        screen,
        cfunc(WHITE),
        (eye_center[0] - offset, eye_center[1] - offset),
        main_radius,
    )

    # small stylised highlight: an elongated ellipse rotated by ``angle`` when requested
    if style == "rotating":
        surf_size = max(8, small_radius * 4)
        small = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        # draw an asymmetric ellipse toward the right of the small surf so rotation is visible
        ell_w = max(2, int(surf_size * 0.6))
        ell_h = max(1, int(surf_size * 0.35))
        ell_x = surf_size // 2 + int(small_radius * 0.2)
        ell_y = surf_size // 2 - int(small_radius * 0.2)
        pygame.draw.ellipse(
            small,
            (*cfunc(WHITE), 200),
            (ell_x - ell_w // 2, ell_y - ell_h // 2, ell_w, ell_h),
        )
        rotated = pygame.transform.rotate(small, angle)
        rect = rotated.get_rect(
            center=(
                eye_center[0] + int(eye_radius * 0.25),
                eye_center[1] + int(eye_radius * 0.2),
            )
        )
        screen.blit(rotated, rect.topleft)
        return

    # default: main white + a small soft round highlight
    small = pygame.Surface((small_radius * 2, small_radius * 2), pygame.SRCALPHA)
    pygame.draw.circle(
        small,
        (*cfunc(WHITE), 120),
        (small_radius, small_radius),
        small_radius,
    )
    screen.blit(
        small,
        (
            eye_center[0] + int(eye_radius * 0.25) - small_radius,
            eye_center[1] + int(eye_radius * 0.2) - small_radius,
        ),
    )


def draw_face(
    surface: pygame.Surface,
    state: str,
    *,
    blink: bool = False,
    swap_rb: bool = False,
    bg_color: tuple[int, int, int] = WHITE,
    timestamp: float | None = None,
    overlay_text: str | None = None,
    overlay_font: pygame.font.Font | None = None,
    overlay_height_ratio: float = 0.18,
) -> None:
    width, height = surface.get_width(), surface.get_height()
    now = time.time() if timestamp is None else timestamp
    cfg = STATE_RULES.get(state, STATE_RULES["BASE"])

    c = lambda col: _swap_color(col, swap_rb)
    surface.fill(c(bg_color))

    # base eye radius scaled by configured per-state eye_scale and a global override
    eye_radius = int(
        width
        / 4.8
        * cfg.get("eye_scale", 1.0)
        * globals().get("EYE_SCALE_ADJUST", 1.0)
    )
    eye_pupil_radius = int(eye_radius * 0.42)
    eye_y = int(height * 0.38)
    left_eye_x = int(width * 0.3)
    right_eye_x = int(width * 0.7)

    pupil_offset_x = int(eye_pupil_radius * cfg.get("pupil", (0.0, 0.0))[0])
    pupil_offset_y = int(eye_pupil_radius * cfg.get("pupil", (0.0, 0.0))[1])

    eye_open = cfg.get("eye_open", 1.0)  # type: ignore[arg-type]
    effective_blink = blink or eye_open <= 0.05
    highlight_style = cfg.get("highlight", "default")  # type: ignore[assignment]
    # compute rotating highlight angle when requested
    angle = 0.0
    if highlight_style == "rotating":
        speed = cfg.get("highlight_speed", 90)  # type: ignore[assignment]
        angle = (now * float(speed)) % 360.0

    if effective_blink:
        thickness = max(4, int(eye_radius * 0.22))
        pygame.draw.line(
            surface,
            c(BLACK),
            (left_eye_x - eye_radius, eye_y),
            (left_eye_x + eye_radius, eye_y),
            thickness,
        )
        pygame.draw.line(
            surface,
            c(BLACK),
            (right_eye_x - eye_radius, eye_y),
            (right_eye_x + eye_radius, eye_y),
            thickness,
        )
    else:
        pygame.draw.circle(surface, c(BLACK), (left_eye_x, eye_y), eye_radius)
        pygame.draw.circle(surface, c(BLACK), (right_eye_x, eye_y), eye_radius)

        pupil_pos_left = (left_eye_x + pupil_offset_x, eye_y + pupil_offset_y)
        pupil_pos_right = (right_eye_x + pupil_offset_x, eye_y + pupil_offset_y)

        inner_radius = int(eye_radius * 0.58)
        inner_alpha = int(max(0, min(255, cfg.get("inner_alpha", 220))))  # type: ignore[arg-type]
        # Respect global SOLID_EYES: if solid, don't draw iris/highlights
        if globals().get("SOLID_EYES", False):
            inner_alpha = 0
            highlight_style = "none"

        if inner_alpha > 0:
            iris_surface = pygame.Surface((inner_radius * 2, inner_radius * 2), pygame.SRCALPHA)
            iris_color = c(cfg.get("inner_color", (40, 40, 40)))  # type: ignore[arg-type]
            pygame.draw.circle(
                iris_surface,
                (*iris_color, inner_alpha),
                (inner_radius, inner_radius),
                inner_radius,
            )
            surface.blit(
                iris_surface,
                (pupil_pos_left[0] - inner_radius, pupil_pos_left[1] - inner_radius),
            )
            surface.blit(
                iris_surface,
                (pupil_pos_right[0] - inner_radius, pupil_pos_right[1] - inner_radius),
            )

        if eye_open < 1.0:
            lid_height = int(eye_radius * (1.0 - eye_open) * 1.1)
            lid_rect = (left_eye_x - eye_radius, eye_y - eye_radius, eye_radius * 2, lid_height)
            pygame.draw.rect(surface, c(bg_color), lid_rect)
            lid_rect = (right_eye_x - eye_radius, eye_y - eye_radius, eye_radius * 2, lid_height)
            pygame.draw.rect(surface, c(bg_color), lid_rect)

        _draw_highlights(surface, c, (left_eye_x, eye_y), eye_radius, style=str(highlight_style), angle=angle)
        _draw_highlights(surface, c, (right_eye_x, eye_y), eye_radius, style=str(highlight_style), angle=angle)

    mouth_y = int(height * 0.8)
    mouth_width = int(width * 0.46 * globals().get("MOUTH_SCALE_ADJUST", 1.0))
    mouth_height = int(height * 0.17 * globals().get("MOUTH_SCALE_ADJUST", 1.0))
    mouth_x_center = int(width * 0.5)
    mouth_rect = [
        mouth_x_center - mouth_width // 2,
        mouth_y - mouth_height // 2,
        mouth_width,
        mouth_height,
    ]
    thickness = max(4, int(width * 0.01))

    mouth_style = str(cfg.get("mouth", "soft_smile"))
    if mouth_style == "beam":
        rect = mouth_rect.copy()
        rect[1] -= int(mouth_height * 0.2)
        rect[3] += int(mouth_height * 0.4)
        pygame.draw.arc(
            surface, c(BLACK), rect, math.pi * 0.15, math.pi * 0.85, thickness + 2
        )
    elif mouth_style == "talk":
        points = []
        segments = 6
        for idx in range(segments + 1):
            x = mouth_rect[0] + idx * (mouth_rect[2] / segments)
            wave = abs(math.sin(now * 8 + idx * 0.6))
            y = mouth_y + int(mouth_height * 0.15 * wave) - mouth_height // 5
            points.append((x, y))
        if len(points) > 1:
            pygame.draw.lines(surface, c(BLACK), False, points, thickness + 1)
    elif mouth_style == "o":
        radius = int(mouth_height * 0.45)
        pygame.draw.circle(
            surface, c(BLACK), (mouth_x_center, mouth_y - radius // 4), radius, thickness
        )
    elif mouth_style == "flat":
        start = (mouth_rect[0] + int(mouth_rect[2] * 0.1), mouth_y)
        end = (mouth_rect[0] + int(mouth_rect[2] * 0.9), mouth_y)
        pygame.draw.line(surface, c(BLACK), start, end, thickness)
    elif mouth_style == "sad":
        rect = mouth_rect.copy()
        rect[1] += int(mouth_height * 0.1)
        pygame.draw.arc(
            surface, c(BLACK), rect, math.pi * 1.15, math.pi * 1.85, thickness
        )
    else:  # soft_smile
        rect = mouth_rect.copy()
        rect[1] += int(mouth_height * 0.05)
        pygame.draw.arc(surface, c(BLACK), rect, math.pi, math.pi * 2, thickness)

    blush_radius = int(width * 0.085 * globals().get("BLUSH_SCALE_ADJUST", 1.0))
    left_blush = (
        left_eye_x - int(eye_radius * 0.7),
        eye_y + int(eye_radius * 1.35),
    )
    right_blush = (
        right_eye_x + int(eye_radius * 0.7),
        eye_y + int(eye_radius * 1.35),
    )
    solid_blush = bool(cfg.get("solid_blush", False))
    blush_color = cfg.get("blush_color")  # type: ignore[assignment]
    _draw_blush(
        surface,
        c,
        left_blush,
        blush_radius,
        float(cfg.get("blush", 1.0)),  # type: ignore[arg-type]
        solid=solid_blush,
        override_color=blush_color,  # type: ignore[arg-type]
    )
    _draw_blush(
        surface,
        c,
        right_blush,
        blush_radius,
        float(cfg.get("blush", 1.0)),  # type: ignore[arg-type]
        solid=solid_blush,
        override_color=blush_color,  # type: ignore[arg-type]
    )

    if overlay_text and overlay_font:
        bar_height = int(height * overlay_height_ratio)
        bar_y = height - bar_height
        pygame.draw.rect(surface, c((10, 10, 10)), (0, bar_y, width, bar_height))
        text = _ellipsize_text(overlay_text, overlay_font, width - 16)
        text_surface = overlay_font.render(text, True, c(WHITE))
        text_rect = text_surface.get_rect()
        text_rect.midleft = (8, bar_y + bar_height // 2)
        surface.blit(text_surface, text_rect)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Emoji face for the Waveshare TFT (fb0)."
    )
    parser.add_argument(
        "--swap-rb",
        action="store_true",
        help="Swap red/blue channels for drivers that expect BGR565",
    )
    parser.add_argument(
        "--bg",
        choices=("white", "black"),
        default="white",
        help="Background colour",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Run in a desktop window instead of the framebuffer",
    )
    parser.add_argument(
        "--state",
        default="BASE",
        help=(
            "Initial expression (BASE, HAPPY, LISTENING, SPEAKING, "
            "SURPRISED, CURIOUS, SAD, LOOK_*, SLEEP)"
        ),
    )
    parser.add_argument(
        "--no-blink",
        action="store_true",
        help="Disable automatic blinking",
    )
    parser.add_argument(
        "--rotate",
        type=int,
        choices=(0, 90, 180, 270),
        default=0,
        help="Rotate output clockwise to match mounting",
    )
    parser.add_argument(
        "--fbdev",
        default=DEFAULT_FB,
        help="Framebuffer device for direct rendering (default: /dev/fb0)",
    )
    parser.add_argument(
        "--eye-scale",
        type=float,
        default=1.0,
        help="Global multiplier for eye size (e.g. 0.7 to reduce)",
    )
    parser.add_argument(
        "--mouth-scale",
        type=float,
        default=1.0,
        help="Global multiplier for mouth size (e.g. 0.9 to reduce)",
    )
    parser.add_argument(
        "--blush-scale",
        type=float,
        default=1.0,
        help="Global multiplier for blush size (e.g. 0.8 to reduce)",
    )
    parser.add_argument(
        "--solid-eyes",
        action="store_true",
        help="Draw solid black eyes (no iris/highlights)",
    )

    args = parser.parse_args()

    if args.windowed:
        os.environ.pop("SDL_FBDEV", None)

    pygame.init()
    pygame.font.init()
    try:
        pygame.mixer.quit()
    except Exception:
        pass
    screen: pygame.Surface | None = None
    fb_writer: FramebufferWriter | None = None

    if args.windowed:
        screen = pygame.display.set_mode((480, 320), pygame.NOFRAME)
        pygame.mouse.set_visible(False)
        canvas = screen if args.rotate == 0 else pygame.Surface(screen.get_size()).convert()
    else:
        width, height, _ = _read_fb_geometry(args.fbdev)
        canvas = pygame.Surface((width, height))
        fb_writer = FramebufferWriter(args.fbdev, rotate=args.rotate)

    bg_color = WHITE if args.bg == "white" else BLACK
    # Apply CLI eye-scale, blush-scale and mouth-scale to globals used by draw_face
    globals()["EYE_SCALE_ADJUST"] = max(0.2, float(args.eye_scale))
    globals()["BLUSH_SCALE_ADJUST"] = max(0.2, float(args.blush_scale))
    globals()["SOLID_EYES"] = bool(args.solid_eyes)
    globals()["MOUTH_SCALE_ADJUST"] = max(0.5, float(args.mouth_scale))

    global current_state
    requested = args.state.upper()
    if requested not in STATE_RULES:
        print(f"Unknown state '{args.state}', falling back to BASE")
        requested = "BASE"
    current_state = requested

    overlay_text = ""
    overlay_text_ts = 0.0
    overlay_font = pygame.font.Font(None, max(18, int(canvas.get_height() * 0.08)))

    state_map = {
        "idle": "BASE",
        "listening": "LISTENING",
        "wakeword_detected": "SURPRISED",
        "thinking": "CURIOUS",
        "tts_processing": "SPEAKING",
        "speaking": "SPEAKING",
        "error": "SAD",
    }

    sub = None
    poller = None
    try:
        cfg = load_config(Path("config/system.yaml"))
        sub = make_subscriber(cfg, topic=TOPIC_DISPLAY_STATE, channel="downstream")
        sub.setsockopt(zmq.SUBSCRIBE, TOPIC_DISPLAY_TEXT)
        sub.setsockopt(zmq.RCVTIMEO, 0)
        poller = zmq.Poller()
        poller.register(sub, zmq.POLLIN)
    except Exception as exc:
        print(f"Display IPC unavailable: {exc}")

    print("Face UI running. Press Ctrl+C or ESC to quit.")
    print(
        "States: I=BASE, H=HAPPY, L=LISTENING, S=SPEAKING, O=SURPRISED, "
        "C=CURIOUS, D=SAD, Arrow keys=LOOK, P=SLEEP"
    )

    blink_enabled = not args.no_blink
    blink_active = False
    next_blink = time.time() + random.uniform(3.5, 6.5)
    blink_end = 0.0

    try:
        while True:
            now = time.time()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt
                if event.type == pygame.KEYDOWN:
                    keymap = {
                        pygame.K_i: "BASE",
                        pygame.K_h: "HAPPY",
                        pygame.K_l: "LISTENING",
                        pygame.K_s: "SPEAKING",
                        pygame.K_o: "SURPRISED",
                        pygame.K_c: "CURIOUS",
                        pygame.K_d: "SAD",
                        pygame.K_p: "SLEEP",
                        pygame.K_LEFT: "LOOK_LEFT",
                        pygame.K_RIGHT: "LOOK_RIGHT",
                        pygame.K_UP: "LOOK_UP",
                        pygame.K_DOWN: "LOOK_DOWN",
                    }
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        raise KeyboardInterrupt
                    if event.key in keymap:
                        current_state = keymap[event.key]
                        print(f"State set to {current_state}")
                if event.type == pygame.KEYUP and event.key in (
                    pygame.K_LEFT,
                    pygame.K_RIGHT,
                    pygame.K_UP,
                    pygame.K_DOWN,
                ):
                    current_state = "BASE"

            if poller and sub:
                while True:
                    events = dict(poller.poll(0))
                    if sub not in events:
                        break
                    try:
                        topic, data = sub.recv_multipart()
                        payload = json.loads(data)
                    except Exception:
                        continue
                    if topic == TOPIC_DISPLAY_STATE:
                        requested_state = str(payload.get("state", "")).lower()
                        mapped = state_map.get(requested_state)
                        if mapped:
                            current_state = mapped
                    elif topic == TOPIC_DISPLAY_TEXT:
                        overlay_text = str(payload.get("text", "")).strip()
                        overlay_text_ts = now

            cfg = STATE_RULES.get(current_state, STATE_RULES["BASE"])
            if blink_enabled and cfg.get("eye_open", 1.0) > 0.05:  # type: ignore[operator]
                if not blink_active and now >= next_blink:
                    blink_active = True
                    blink_end = now + 0.16
                elif blink_active and now >= blink_end:
                    blink_active = False
                    next_blink = now + random.uniform(3.5, 6.5)

            draw_face(
                canvas,
                current_state,
                blink=blink_active,
                swap_rb=args.swap_rb,
                bg_color=bg_color,
                timestamp=now,
                overlay_text=overlay_text if now - overlay_text_ts < 8.0 else "",
                overlay_font=overlay_font,
            )

            if fb_writer:
                fb_writer.write_surface(canvas)
            else:
                if args.rotate and canvas is not screen:
                    rotated = pygame.transform.rotate(canvas, args.rotate)
                    if rotated.get_size() != screen.get_size():  # type: ignore[union-attr]
                        rotated = pygame.transform.smoothscale(rotated, screen.get_size())  # type: ignore[union-attr]
                    screen.blit(rotated, (0, 0))  # type: ignore[union-attr]
                elif canvas is not screen:
                    screen.blit(canvas, (0, 0))  # type: ignore[union-attr]
                pygame.display.flip()

            pygame.time.wait(33)
    except KeyboardInterrupt:
        pass
    finally:
        if sub:
            try:
                sub.close(0)
            except Exception:
                pass
        if fb_writer:
            fb_writer.close()
        pygame.quit()


if __name__ == "__main__":
    main()
