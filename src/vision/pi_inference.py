"""Lightweight camera inference helper supporting TFLite, ONNX, and OpenCV DNN backends.

This module provides a minimal abstraction to load a model, preprocess frames,
run inference, and perform basic postprocessing. Postprocessing for YOLO-style
outputs is intentionally left minimal so it can be adapted to the specific
export used (Ultralytics export shapes vary).

Designed to be conservative with imports so the main repo stays lightweight.
"""
from __future__ import annotations

import time
import argparse
import numpy as np
import cv2
from pathlib import Path
from typing import Any, Tuple, List, Optional


def _try_import_tflite():
    try:
        import tflite_runtime.interpreter as tflite
    except Exception:
        try:
            from tensorflow.lite import Interpreter as tflite  # type: ignore
        except Exception:
            tflite = None
    return tflite


def load_model(backend: str, model_path: str):
    """Load model for chosen backend. Returns a backend-specific handle.

    backend: 'tflite' | 'onnx' | 'opencv'
    """
    backend = backend.lower()
    if backend == "tflite":
        tflite = _try_import_tflite()
        if tflite is None:
            raise RuntimeError("TFLite runtime not available; install tflite-runtime or tensorflow")
        interpreter = tflite.Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        return {"type": "tflite", "interp": interpreter}

    if backend == "onnx":
        try:
            import onnxruntime as ort
        except Exception:
            raise RuntimeError("onnxruntime not available; install onnxruntime for this backend")
        sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        return {"type": "onnx", "sess": sess}

    if backend == "opencv":
        net = cv2.dnn.readNet(model_path)
        return {"type": "opencv", "net": net}

    raise ValueError(f"Unsupported backend: {backend}")


def preprocess(frame: np.ndarray, img_size: int = 640) -> np.ndarray:
    """Resize and normalize a BGR frame to model input.

    Returns a float32 numpy array shaped (1,3,IMG,IMG) with values 0-1.
    """
    h, w = frame.shape[:2]
    resized = cv2.resize(frame, (img_size, img_size))
    img = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))
    img = np.expand_dims(img, 0)
    return img


def _load_labels(path: Optional[str]) -> List[str]:
    if not path:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    return [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _decode_yolo_output(
    outputs: Any,
    frame_shape: Tuple[int, int, int],
    img_size: int,
    labels: List[str],
    conf_thres: float,
    iou_thres: float,
) -> List[dict]:
    if isinstance(outputs, (list, tuple)):
        preds = outputs[0]
    else:
        preds = outputs

    arr = np.array(preds)
    if arr.ndim == 3 and arr.shape[0] == 1:
        arr = arr[0]
    elif arr.ndim == 3 and arr.shape[2] == 84:
        arr = arr.transpose(2, 0, 1)
    if arr.ndim != 2:
        return []
    if arr.shape[0] != 84 and arr.shape[1] == 84:
        arr = arr.T
    if arr.shape[0] != 84:
        return []

    boxes = arr[:4, :]
    scores_all = arr[4:, :]
    class_scores = scores_all.max(axis=0)
    class_ids = scores_all.argmax(axis=0)
    mask = class_scores >= conf_thres
    if not np.any(mask):
        return []

    boxes = boxes[:, mask]
    class_scores = class_scores[mask]
    class_ids = class_ids[mask]

    cx, cy, w, h = boxes
    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2

    scale_x = frame_shape[1] / float(img_size)
    scale_y = frame_shape[0] / float(img_size)
    x1 = np.clip(x1 * scale_x, 0, frame_shape[1] - 1)
    y1 = np.clip(y1 * scale_y, 0, frame_shape[0] - 1)
    x2 = np.clip(x2 * scale_x, 0, frame_shape[1] - 1)
    y2 = np.clip(y2 * scale_y, 0, frame_shape[0] - 1)

    widths = x2 - x1
    heights = y2 - y1
    boxes_xywh = np.stack([x1, y1, widths, heights], axis=1).astype(np.float32)
    scores_list = class_scores.astype(np.float32).tolist()
    boxes_list = boxes_xywh.tolist()
    idxs = cv2.dnn.NMSBoxes(boxes_list, scores_list, conf_thres, iou_thres)
    if idxs is None or len(idxs) == 0:
        return []

    detections: List[dict] = []
    for idx in idxs:
        i = idx[0] if isinstance(idx, (list, tuple, np.ndarray)) else int(idx)
        label_idx = int(class_ids[i])
        name = labels[label_idx] if 0 <= label_idx < len(labels) else f"cls_{label_idx}"
        det = {
            "x": float(x1[i]),
            "y": float(y1[i]),
            "w": float(widths[i]),
            "h": float(heights[i]),
            "label": name,
            "conf": float(class_scores[i]),
        }
        detections.append(det)
    return detections


def postprocess_raw(
    outputs: Any,
    frame_shape: Tuple[int, int, int],
    img_size: int,
    backend: str,
    labels: List[str],
    conf_thres: float,
    iou_thres: float,
) -> List[dict]:
    backend = backend.lower()
    if backend == "onnx":
        dets = _decode_yolo_output(outputs, frame_shape, img_size, labels, conf_thres, iou_thres)
        if dets:
            return dets
    return [{"raw": outputs}]


def run_inference(handle: dict, input_tensor: np.ndarray):
    t = handle["type"]
    if t == "tflite":
        interp = handle["interp"]
        input_details = interp.get_input_details()
        output_details = interp.get_output_details()
        # assume single input
        inp = input_tensor
        # convert to expected dtype
        if input_details[0]["dtype"].name.startswith("uint"):
            inp = (inp * 255).astype(np.uint8)
        else:
            inp = inp.astype(input_details[0]["dtype"])
        interp.set_tensor(input_details[0]["index"], inp)
        interp.invoke()
        outputs = [interp.get_tensor(o["index"]) for o in output_details]
        return outputs

    if t == "onnx":
        sess = handle["sess"]
        input_name = sess.get_inputs()[0].name
        # ONNX Runtime expects NCHW or NHWC depending on the model
        out = sess.run(None, {input_name: input_tensor.astype(np.float32)})
        return out

    if t == "opencv":
        net = handle["net"]
        blob = cv2.dnn.blobFromImage(
            input_tensor[0].transpose(1, 2, 0), scalefactor=1.0, size=(input_tensor.shape[2], input_tensor.shape[3]), mean=(0, 0, 0), swapRB=True, crop=False
        )
        net.setInput(blob)
        out = net.forward()
        return out

    raise RuntimeError("Unsupported backend type in handle")


def _draw_detections(frame: np.ndarray, detections: List[dict]) -> np.ndarray:
    # Placeholder drawing — expect detections to be list of dicts with x,y,w,h,label,conf
    for d in detections:
        if not all(k in d for k in ("x", "y", "w", "h")):
            continue
        x, y, w, h = int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"])
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        label = d.get("label", "obj")
        conf = d.get("conf", 0.0)
        cv2.putText(frame, f"{label}:{conf:.2f}", (x, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return frame


def main():
    parser = argparse.ArgumentParser(description="Run camera inference on Raspberry Pi")
    parser.add_argument("--backend", choices=("tflite", "onnx", "opencv"), default="tflite")
    parser.add_argument("--model", required=True)
    parser.add_argument("--img", type=int, default=640)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--labels", type=str, default="models/vision/coco_labels.txt", help="Optional label file (one label per line)")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold for detections")
    parser.add_argument("--iou", type=float, default=0.45, help="IoU threshold for NMS")
    parser.add_argument("--picam2", action="store_true", help="Capture frames with Picamera2 instead of cv2.VideoCapture")
    parser.add_argument("--picam-width", type=int, default=832, help="Picamera2 frame width")
    parser.add_argument("--picam-height", type=int, default=468, help="Picamera2 frame height")
    parser.add_argument("--picam-fps", type=int, default=12, help="Picamera2 target frame rate")
    parser.add_argument("--no-display", action="store_true", help="Skip cv2.imshow (useful for headless runs)")
    args = parser.parse_args()

    handle = load_model(args.backend, args.model)
    labels = _load_labels(args.labels)

    cap = None
    picam2 = None
    if args.picam2:
        try:
            from picamera2 import Picamera2  # type: ignore
        except Exception as exc:  # pragma: no cover - hardware import
            raise RuntimeError("Picamera2 requested but import failed") from exc
        picam2 = Picamera2()
        video_config = picam2.create_video_configuration(
            main={"size": (args.picam_width, args.picam_height), "format": "RGB888"},
            controls={"FrameRate": args.picam_fps},
        )
        picam2.configure(video_config)
        picam2.start()
    else:
        cap = cv2.VideoCapture(args.camera)
        if not cap.isOpened():
            raise RuntimeError("Could not open camera")

    prev = time.time()
    fps_smooth = None
    frame_count = 0
    try:
        while True:
            if picam2 is not None:
                frame_rgb = picam2.capture_array()
                if frame_rgb is None:
                    continue
                frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            else:
                ret, frame = cap.read()
                if not ret:
                    break
            inp = preprocess(frame, args.img)
            outputs = run_inference(handle, inp)
            dets = postprocess_raw(outputs, frame.shape, args.img, handle["type"], labels, args.conf, args.iou)
            out = _draw_detections(frame, dets)
            now = time.time()
            fps = 1.0 / (now - prev) if now != prev else 0.0
            prev = now
            fps_smooth = fps if fps_smooth is None else (fps_smooth * 0.9 + fps * 0.1)
            frame_count += 1
            if args.no_display:
                label_preview = ", ".join(
                    f"{d.get('label', 'obj')}:{d.get('conf', 0.0):.2f}" for d in dets[:3]
                )
                print(
                    f"[inference] frame={frame_count} dets={len(dets)} fps={fps_smooth:.1f} "
                    f"[{label_preview if label_preview else 'raw'}]"
                )
            cv2.putText(out, f"FPS: {fps_smooth:.1f}", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            if not args.no_display:
                cv2.imshow("inference", out)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        if cap is not None:
            cap.release()
        if picam2 is not None:
            picam2.stop()
        if not args.no_display:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
