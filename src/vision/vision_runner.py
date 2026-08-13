from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import zmq

from src.core.config_loader import load_config
from src.core.ipc import (
    TOPIC_CMD_PAUSE_VISION,
    TOPIC_CMD_VISN_CAPTURE,
    TOPIC_CMD_VISION_MODE,
    TOPIC_VISN,
    TOPIC_VISN_CAPTURED,
    TOPIC_VISN_FRAME,
    make_publisher,
    make_subscriber,
    publish_json,
)
from src.core.logging_setup import get_logger
from src.vision.detector import Detection, VisionConfig
from src.vision.pipeline import VisionPipeline


logger = get_logger("vision.runner", Path("logs"))


class LatestFrameGrabber(threading.Thread):
    """Threaded camera capture that always provides the latest frame.
    
    This pattern prevents frame lag by:
    1. Running capture in a dedicated thread
    2. Discarding old frames continuously
    3. Only keeping the most recent frame for inference
    
    Without this, OpenCV's internal buffer fills up and you process
    stale frames (seconds old) instead of live video.
    """
    
    def __init__(
        self,
        camera_index: int,
        target_fps: float = 15.0,
        *,
        use_picam2: bool = True,
        picam_width: int = 832,
        picam_height: int = 468,
        picam_fps: int = 12,
    ) -> None:
        super().__init__(daemon=True, name="FrameGrabber")
        self.camera_index = camera_index
        self.target_fps = max(1.0, target_fps)
        self.frame_interval = 1.0 / self.target_fps

        self.cap: Optional[cv2.VideoCapture] = None
        self.picam2 = None
        self._backend = "cv2"
        self.backend = "cv2"
        self._opened = False

        if use_picam2:
            try:
                from picamera2 import Picamera2  # type: ignore
                picam2 = Picamera2()
                video_config = picam2.create_video_configuration(
                    main={"size": (picam_width, picam_height), "format": "RGB888"},
                    controls={"FrameRate": picam_fps},
                )
                picam2.configure(video_config)
                picam2.start()
                self.picam2 = picam2
                self._backend = "picam2"
                self.backend = "picam2"
                self._opened = True
            except Exception:
                self.picam2 = None

        if not self._opened:
            self.cap = cv2.VideoCapture(camera_index)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffer
            self._opened = self.cap.isOpened()
            self.backend = "cv2"
        
        # Thread-safe frame storage
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_time: float = 0.0
        self._frame_count: int = 0
        
        # Control
        self._stop_event = threading.Event()
        if not self._opened:
            logger.error("Camera open failed (backend=%s, index=%s)", self._backend, camera_index)
    
    def run(self) -> None:
        """Continuously capture frames, keeping only the latest."""
        last_time = 0.0
        
        while not self._stop_event.is_set():
            now = time.perf_counter()
            
            # Rate limiting
            if now - last_time < self.frame_interval:
                time.sleep(0.001)
                continue
            
            # Capture frame
            frame = None
            if self._backend == "picam2" and self.picam2 is not None:
                frame_rgb = self.picam2.capture_array()
                if frame_rgb is not None:
                    frame = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            elif self.cap is not None:
                ret, captured = self.cap.read()
                if ret:
                    frame = captured
            if frame is None:
                time.sleep(0.01)
                continue
            
            # Store latest frame
            with self._lock:
                self._latest_frame = frame
                self._frame_time = now
                self._frame_count += 1
            
            last_time = now
    
    def get_frame(self) -> tuple[Optional[np.ndarray], float]:
        """Get the latest frame and its capture time.
        
        Returns:
            (frame, timestamp) or (None, 0.0) if no frame available
        """
        with self._lock:
            if self._latest_frame is None:
                return None, 0.0
            return self._latest_frame.copy(), self._frame_time
    
    def get_frame_count(self) -> int:
        """Get total frames captured."""
        with self._lock:
            return self._frame_count
    
    def is_opened(self) -> bool:
        """Check if camera was successfully opened."""
        return self._opened
    
    def stop(self) -> None:
        """Stop capture and release camera."""
        self._stop_event.set()
        if self.cap:
            self.cap.release()
        if self.picam2 is not None:
            try:
                self.picam2.stop()
                self.picam2.close()
            except Exception:
                pass
        self.join(timeout=2.0)
        self._opened = False
        if not self.is_alive():
            self.cap = None


class MockDetector:
    """Deterministic detector used when running tests without a real model."""

    def load(self) -> None:  # pragma: no cover - trivial
        return

    def detect(self, frame: np.ndarray) -> list[Detection]:
        height, width = frame.shape[:2]
        bbox = (width // 4, height // 4, width * 3 // 4, height * 3 // 4)
        return [Detection(label="mock-object", confidence=0.99, bbox=bbox)]


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        label = f"{det.label}:{det.confidence:.2f}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, label, (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return frame


def publish_detections(pub_sock, detections: list[Detection], ts: float, request_id: str | None = None) -> None:
    if not detections:
        payload = {"label": "none", "bbox": [0, 0, 0, 0], "confidence": 0.0, "ts": ts}
        if request_id:
            payload["request_id"] = request_id
        publish_json(pub_sock, TOPIC_VISN, payload)
        return
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        payload = {"label": det.label, "bbox": [x1, y1, x2, y2], "confidence": det.confidence, "ts": ts}
        if request_id:
            payload["request_id"] = request_id
        publish_json(pub_sock, TOPIC_VISN, payload)


def _coerce_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    return Path(path_value).expanduser()


def build_vision_config(raw_cfg: dict) -> VisionConfig:
    model_path = _coerce_path(raw_cfg.get("model_path_onnx")) or Path("models/vision/yolo11n.onnx")
    return VisionConfig(
        model_path=model_path,
        backend=raw_cfg.get("backend", "onnx"),
        input_size=tuple(raw_cfg.get("input_size", [640, 640])),
        confidence=float(raw_cfg.get("confidence", 0.25)),
        iou=float(raw_cfg.get("iou", 0.45)),
        label_path=_coerce_path(raw_cfg.get("label_path"))
        or Path(raw_cfg.get("label_map", ""))
        if raw_cfg.get("label_map")
        else None,
    )


def _generate_test_frame(width: int = 640, height: int = 480) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.rectangle(frame, (50, 50), (width - 50, height - 50), (0, 128, 255), 3)
    cv2.putText(frame, "vision test", (60, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    return frame


def _normalize_vision_mode(raw: str | bool | None) -> str:
    if raw is None:
        return "off"
    if isinstance(raw, bool):
        return "off" if raw is False else "on_no_stream"
    value = str(raw).strip().lower()
    if value in {"off", "false", "0", "disabled"}:
        return "off"
    if value in {"on_with_stream", "with_stream", "stream"}:
        return "on_with_stream"
    return "on_no_stream"


def run():
    parser = argparse.ArgumentParser(description="YOLO-based vision runner")
    parser.add_argument("--config", default="config/system.yaml")
    parser.add_argument("--camera-index", type=int, default=None)
    parser.add_argument("--show", action="store_true", help="Display detections locally")
    parser.add_argument("--image", type=str, help="Run inference on a single image path", default=None)
    parser.add_argument("--test", action="store_true", help="Run a synthetic frame test instead of opening the camera")
    parser.add_argument("--max-frames", type=int, default=None, help="Exit after processing N frames")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    vis_cfg = cfg.get("vision", {})
    camera_index = args.camera_index if args.camera_index is not None else int(vis_cfg.get("camera_index", 0))

    vision_config = build_vision_config(vis_cfg)
    pipeline = VisionPipeline(vision_config)
    mock_mode = False
    try:
        pipeline.bootstrap()
    except FileNotFoundError as exc:
        if args.test or args.image:
            logger.warning("Vision model missing (%s). Using mock detector for test mode.", exc)
            pipeline.detector = MockDetector()
            mock_mode = True
        else:
            logger.error("Vision bootstrap failed: %s", exc)
            return
    except Exception as exc:  # pragma: no cover - defensive logging
        if args.test or args.image:
            logger.warning("Vision bootstrap failed (%s). Using mock detector for test mode.", exc)
            pipeline.detector = MockDetector()
            mock_mode = True
        else:
            logger.exception("Vision bootstrap failed")
            return

    if args.test or args.image:
        frame = _generate_test_frame()
        if args.image:
            img_path = Path(args.image)
            if not img_path.exists():
                logger.error("Image %s not found", img_path)
                return
            frame = cv2.imread(str(img_path))
            if frame is None:
                logger.error("Failed to read image %s", img_path)
                return
        detections = pipeline.infer_once(frame)
        summary = [f"{d.label}:{d.confidence:.2f}" for d in detections]
        logger.info("Test detections (%s mode): %s", "mock" if mock_mode else "yolo", summary)
        if args.show:
            cv2.imshow("vision-test", draw_detections(frame.copy(), detections))
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        return

    pub = make_publisher(cfg, channel="upstream")
    ctrl_sub = make_subscriber(cfg, topic=TOPIC_CMD_PAUSE_VISION, channel="downstream")
    ctrl_sub.setsockopt(zmq.SUBSCRIBE, TOPIC_CMD_VISN_CAPTURE)
    ctrl_sub.setsockopt(zmq.SUBSCRIBE, TOPIC_CMD_VISION_MODE)
    poller = zmq.Poller()
    poller.register(ctrl_sub, zmq.POLLIN)

    paused = False
    capture_once = False
    capture_request_id: Optional[str] = None
    capture_save = False
    forced_capture_mode = False
    stream_enabled = False
    vision_mode = _normalize_vision_mode(vis_cfg.get("default_mode", "off"))
    frame_counter = 0
    
    # Use threaded frame grabber for latest-frame pattern
    target_fps = float(vis_cfg.get("target_fps", 15.0))
    stream_fps = float(vis_cfg.get("stream_fps", target_fps))
    grabber: Optional[LatestFrameGrabber] = None
    use_picam2 = bool(vis_cfg.get("use_picam2", True))
    picam_width = int(vis_cfg.get("picam2_width", 832))
    picam_height = int(vis_cfg.get("picam2_height", 468))
    picam_fps = int(vis_cfg.get("picam2_fps", 12))
    capture_root = _coerce_path(vis_cfg.get("capture_root")) or Path("captured")
    capture_session_id = str(vis_cfg.get("capture_session_id", "")) or time.strftime("%Y%m%d_%H%M%S")
    capture_dir = capture_root / capture_session_id
    capture_counter = 0

    def _ensure_grabber() -> bool:
        nonlocal grabber
        if grabber is not None:
            return True
        grabber = LatestFrameGrabber(
            camera_index,
            target_fps=target_fps,
            use_picam2=use_picam2,
            picam_width=picam_width,
            picam_height=picam_height,
            picam_fps=picam_fps,
        )
        if not grabber.is_opened():
            logger.error("Cannot open camera index %s", camera_index)
            grabber = None
            return False
        grabber.start()
        logger.info("Started threaded frame grabber (%s) at %.1f FPS", grabber.backend, target_fps)
        return True

    def _stop_grabber() -> None:
        nonlocal grabber
        if grabber is None:
            return
        grabber.stop()
        grabber = None
        logger.info("Stopped camera grabber")
    
    # Inference rate limiting
    min_inference_interval = 1.0 / target_fps
    last_inference_time = 0.0
    stream_interval = 1.0 / max(1.0, stream_fps)
    last_stream_time = 0.0

    def _publish_stream_frame(frame: np.ndarray) -> None:
        nonlocal last_stream_time
        now = time.perf_counter()
        if (now - last_stream_time) < stream_interval:
            return
        success, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if not success:
            return
        pub.send_multipart([TOPIC_VISN_FRAME, encoded.tobytes()])
        last_stream_time = now

    def _save_capture_async(frame: np.ndarray, request_id: Optional[str]) -> None:
        nonlocal capture_counter
        capture_counter += 1
        ts_ms = int(time.time() * 1000)
        capture_dir.mkdir(parents=True, exist_ok=True)
        token = request_id or f"{capture_counter:04d}"
        filename = f"frame_{token}_{ts_ms}.jpg"
        path = capture_dir / filename

        def _writer() -> None:
            try:
                cv2.imwrite(str(path), frame)
                publish_json(pub, TOPIC_VISN_CAPTURED, {
                    "path": str(path),
                    "timestamp": ts_ms,
                    "request_id": request_id,
                })
                logger.info("Saved capture to %s", path)
            except Exception as exc:
                logger.error("Capture save failed: %s", exc)

        threading.Thread(target=_writer, daemon=True).start()

    try:
        while True:
            if args.max_frames is not None and frame_counter >= args.max_frames:
                logger.info("Reached max frame budget (%s), exiting", args.max_frames)
                break

            # Command check
            poll_timeout = 0
            if vision_mode == "off" and not capture_once:
                poll_timeout = 500
            socks = dict(poller.poll(timeout=poll_timeout))
            if ctrl_sub in socks:
                try:
                    topic, raw = ctrl_sub.recv_multipart(zmq.NOBLOCK)
                    msg = json.loads(raw)
                    if topic == TOPIC_CMD_PAUSE_VISION:
                        paused = bool(msg.get("pause", False))
                        logger.info("Vision paused=%s", paused)
                    elif topic == TOPIC_CMD_VISN_CAPTURE:
                        capture_once = True
                        capture_request_id = msg.get("request_id")
                        capture_save = bool(msg.get("save", False)) or (msg.get("purpose") == "capture_frame")
                        logger.info("Vision capture requested (id=%s, save=%s)", capture_request_id, capture_save)
                        if vision_mode == "off":
                            vision_mode = "on_no_stream"
                            forced_capture_mode = True
                            logger.info("Vision mode forced ON for capture request")
                    elif topic == TOPIC_CMD_VISION_MODE:
                        mode = _normalize_vision_mode(msg.get("mode", ""))
                        vision_mode = mode
                        stream_enabled = (mode == "on_with_stream")
                        logger.info("Vision mode set to %s", vision_mode)
                except zmq.Again:
                    pass
                except json.JSONDecodeError as exc:
                    logger.error("Vision command decode error: %s", exc)

            if vision_mode == "off" and not capture_once:
                _stop_grabber()
                continue

            if not _ensure_grabber():
                time.sleep(0.1)
                continue

            force_capture = capture_once
            if paused and not force_capture:
                time.sleep(0.01)
                continue

            # Rate limit inference
            now = time.perf_counter()
            if not force_capture and (now - last_inference_time) < min_inference_interval:
                time.sleep(0.001)
                continue

            # Get latest frame (non-blocking, returns most recent)
            if grabber is None:
                time.sleep(0.01)
                continue
            frame, frame_time = grabber.get_frame()
            if frame is None:
                time.sleep(0.005)
                continue
            
            # Skip if frame is too old (stale data protection)
            frame_age = now - frame_time
            if frame_age > 0.5 and not force_capture:  # Skip frames older than 500ms
                logger.debug("Skipping stale frame (age=%.3fs)", frame_age)
                continue

            detections = pipeline.infer_once(frame)
            ts = time.time()
            publish_detections(pub, detections, ts, request_id=capture_request_id if force_capture else None)
            if frame_counter % 50 == 0:
                logger.info("Vision tick frame=%s dets=%s mode=%s", frame_counter, len(detections), vision_mode)

            if stream_enabled and not paused:
                _publish_stream_frame(frame)
            
            if force_capture:
                capture_once = False
                if capture_save:
                    _save_capture_async(frame.copy(), capture_request_id)
                    capture_save = False
                capture_request_id = None
                if forced_capture_mode:
                    vision_mode = "off"
                    stream_enabled = False
                    forced_capture_mode = False
            
            frame_counter += 1
            last_inference_time = now

            if args.show:
                vis = draw_detections(frame.copy(), detections)
                cv2.imshow("vision", vis)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        _stop_grabber()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    run()
