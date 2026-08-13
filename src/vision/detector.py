"""YOLO-based object detection helpers used by the vision runner."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import cv2
import numpy as np

from . import pi_inference


DEFAULT_COCO80_LABELS: Sequence[str] = (
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
)


@dataclass(slots=True)
class VisionConfig:
    model_path: Path
    backend: str = "onnx"
    input_size: Tuple[int, int] = (640, 640)
    confidence: float = 0.25
    iou: float = 0.45
    label_path: Path | None = None


@dataclass(slots=True)
class Detection:
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]


class YOLODetector:
    """Lightweight YOLO decoder using OpenCV DNN."""

    def __init__(self, config: VisionConfig) -> None:
        self.config = config
        self.net = None
        self.sess = None
        self.input_name: str | None = None
        self.backend: str = config.backend.lower()
        self.labels: List[str] = []

    def load(self) -> None:
        backend = self.config.backend.lower()
        if not self.config.model_path.exists():
            raise FileNotFoundError(f"YOLO weight not found: {self.config.model_path}")
        if backend in {"onnx", "onnxruntime"}:
            try:
                import onnxruntime as ort  # type: ignore
            except Exception:
                ort = None
            if ort is not None:
                handle = pi_inference.load_model("onnx", str(self.config.model_path))
                self.sess = handle["sess"]
                self.input_name = self.sess.get_inputs()[0].name
                self.backend = "onnxruntime"
            else:
                self.net = cv2.dnn.readNetFromONNX(str(self.config.model_path))
                self.backend = "opencv"
        elif backend == "opencv":
            self.net = cv2.dnn.readNetFromONNX(str(self.config.model_path))
            self.backend = "opencv"
        else:
            raise NotImplementedError(f"Unsupported vision backend: {backend}")
        self.labels = self._load_labels()

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if self.backend == "onnxruntime":
            if self.sess is None or self.input_name is None:
                raise RuntimeError("Detector not bootstrapped. Call load() before detect().")
            input_size = self.config.input_size
            img_size = int(input_size[0])
            inp = pi_inference.preprocess(frame, img_size=img_size)
            outputs = self.sess.run(None, {self.input_name: inp.astype(np.float32)})
            dets = pi_inference.postprocess_raw(
                outputs,
                frame.shape,
                img_size,
                "onnx",
                self.labels,
                self.config.confidence,
                self.config.iou,
            )
            parsed: List[Detection] = []
            for det in dets:
                if not all(k in det for k in ("x", "y", "w", "h", "label", "conf")):
                    continue
                x, y, w, h = int(det["x"]), int(det["y"]), int(det["w"]), int(det["h"])
                parsed.append(Detection(label=str(det["label"]), confidence=float(det["conf"]), bbox=(x, y, x + w, y + h)))
            return parsed

        if self.net is None:
            raise RuntimeError("Detector not bootstrapped. Call load() before detect().")

        blob = cv2.dnn.blobFromImage(
            frame,
            scalefactor=1 / 255.0,
            size=self.config.input_size,
            swapRB=True,
            crop=False,
        )
        self.net.setInput(blob)
        outputs = self.net.forward()
        return self._decode(outputs, frame.shape[:2])

    def _decode(self, outputs: np.ndarray, frame_shape: Tuple[int, int]) -> List[Detection]:
        frame_h, frame_w = frame_shape
        out = outputs[0] if isinstance(outputs, (list, tuple)) else outputs
        out = np.squeeze(out)
        if out.ndim == 1:
            out = np.expand_dims(out, axis=0)

        boxes: List[Tuple[int, int, int, int]] = []
        scores: List[float] = []
        labels: List[int] = []
        input_w, input_h = self.config.input_size

        for row in out:
            obj_conf = float(row[4])
            if obj_conf < self.config.confidence:
                continue
            cls_scores = row[5:]
            cls_id = int(np.argmax(cls_scores))
            cls_conf = float(cls_scores[cls_id]) * obj_conf
            if cls_conf < self.config.confidence:
                continue
            cx, cy, w, h = row[0:4]
            x1 = int((cx - w / 2) * frame_w / input_w)
            y1 = int((cy - h / 2) * frame_h / input_h)
            box_w = int(w * frame_w / input_w)
            box_h = int(h * frame_h / input_h)
            boxes.append([x1, y1, box_w, box_h])
            scores.append(cls_conf)
            labels.append(cls_id)

        detections: List[Detection] = []
        if not boxes:
            return detections

        indices = cv2.dnn.NMSBoxes(boxes, scores, self.config.confidence, self.config.iou)
        if len(indices) == 0:
            return detections

        for idx in np.array(indices).reshape(-1):
            x, y, w, h = boxes[idx]
            x2 = x + w
            y2 = y + h
            label_idx = labels[idx]
            label = self.labels[label_idx] if label_idx < len(self.labels) else str(label_idx)
            detections.append(Detection(label=label, confidence=scores[idx], bbox=(x, y, x2, y2)))
        return detections

    def _load_labels(self) -> List[str]:
        if self.config.label_path and self.config.label_path.exists():
            text = self.config.label_path.read_text(encoding="utf-8").strip().splitlines()
            labels = [line.strip() for line in text if line.strip()]
            if labels:
                return labels
        return list(DEFAULT_COCO80_LABELS)
