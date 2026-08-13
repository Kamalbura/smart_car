"""Basic smoke tests for the vision inference helpers."""
from __future__ import annotations

import numpy as np
import sys

# Provide a lightweight fake `cv2` for test environments where OpenCV isn't installed.
try:
    import cv2  # noqa: F401
except Exception:
    import types

    cv2 = types.SimpleNamespace()

    def _resize(img, size):
        # very small nearest-neighbour resize implemented with numpy
        h, w = img.shape[:2]
        nh, nw = size
        ys = (np.linspace(0, h, nh, endpoint=False)).astype(int)
        xs = (np.linspace(0, w, nw, endpoint=False)).astype(int)
        out = img[ys[:, None], xs[None, :]]
        return out

    def _cvtcolor(img, code):
        # only support BGR->RGB
        return img[..., ::-1]

    cv2.resize = _resize
    cv2.cvtColor = _cvtcolor
    cv2.COLOR_BGR2RGB = 0
    sys.modules["cv2"] = cv2


def test_preprocess_shape_and_dtype():
    # create a dummy BGR image 480x640
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    from src.vision.pi_inference import preprocess

    out = preprocess(img, img_size=320)
    assert out.shape == (1, 3, 320, 320)
    assert out.dtype == np.float32


def test_load_model_invalid_backend():
    from src.vision.pi_inference import load_model
    try:
        load_model("not-a-backend", "models/does_not_exist.tflite")
    except ValueError:
        return
    raise AssertionError("load_model should raise ValueError for unsupported backend")
