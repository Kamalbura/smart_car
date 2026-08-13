#!/usr/bin/env python3
"""Combined Vision + Display Test for Smart Car.

Tests:
1. Camera capture (via Picamera2)
2. YOLO object detection (via ONNX Runtime)
3. TFT display rendering (via pygame/framebuffer)

Usage:
    # From system python (for camera):
    python3 tools/test_vision_display.py --capture-only
    
    # From visn venv (for detection + display):
    source .venvs/visn/bin/activate
    python tools/test_vision_display.py --detect /tmp/camera_frame.npy
    
    # Combined (spawns system python for camera):
    python tools/test_vision_display.py --full
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# COCO 80 class labels for YOLO
COCO_LABELS = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat',
    'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat',
    'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack',
    'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
    'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket',
    'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake',
    'chair', 'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop',
    'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink',
    'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush'
]


def capture_frame_script():
    """Python script to capture frame with Picamera2 (runs in system Python)."""
    return '''
import sys
import time
import numpy as np
from picamera2 import Picamera2

output_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/camera_frame.npy"

picam2 = Picamera2()
config = picam2.create_still_configuration(main={"size": (640, 480), "format": "RGB888"})
picam2.configure(config)
picam2.start()
time.sleep(0.5)
frame = picam2.capture_array()
np.save(output_path, frame)
print(f"CAPTURED:{frame.shape[1]}x{frame.shape[0]}")
picam2.stop()
picam2.close()
'''


def capture_with_system_python(output_path: str = "/tmp/camera_frame.npy") -> bool:
    """Capture frame using system Python (for libcamera/picamera2)."""
    print("📷 Capturing frame with system Python + Picamera2...")
    script = capture_frame_script()
    
    result = subprocess.run(
        ["/usr/bin/python3", "-c", script, output_path],
        capture_output=True, text=True, timeout=15
    )
    
    if result.returncode != 0:
        print(f"   ❌ Capture failed: {result.stderr}")
        return False
    
    for line in result.stdout.strip().split('\n'):
        if line.startswith("CAPTURED:"):
            print(f"   ✅ {line}")
            return True
    
    return Path(output_path).exists()


def detect_objects(frame_path: str, model_path: str = "models/vision/yolo11n.onnx") -> list:
    """Run YOLO detection on a frame."""
    import numpy as np
    import cv2
    import onnxruntime as ort
    
    print(f"🔍 Running YOLO detection...")
    print(f"   Model: {model_path}")
    print(f"   Frame: {frame_path}")
    
    # Load frame
    frame = np.load(frame_path)
    print(f"   Input: {frame.shape}")
    
    # Load model
    sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    input_name = sess.get_inputs()[0].name
    
    # Preprocess
    img = cv2.resize(frame, (640, 640))
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
    img = np.expand_dims(img, axis=0)
    
    # Inference
    start = time.time()
    outputs = sess.run(None, {input_name: img})
    elapsed = time.time() - start
    print(f"   ⏱️  Inference: {elapsed*1000:.0f}ms")
    
    # Parse YOLO11 output: [1, 84, 8400]
    out = outputs[0][0]  # (84, 8400)
    boxes = out[:4, :]   # cx, cy, w, h
    scores = out[4:, :]  # class scores (80 classes)
    
    conf_thresh = 0.25
    detections = []
    
    for i in range(scores.shape[1]):
        class_scores = scores[:, i]
        max_score = float(np.max(class_scores))
        if max_score > conf_thresh:
            class_id = int(np.argmax(class_scores))
            label = COCO_LABELS[class_id] if class_id < len(COCO_LABELS) else f"cls_{class_id}"
            cx, cy, w, h = boxes[:, i]
            # Scale back to original frame coords
            scale_x = frame.shape[1] / 640
            scale_y = frame.shape[0] / 640
            x1 = int((cx - w/2) * scale_x)
            y1 = int((cy - h/2) * scale_y)
            x2 = int((cx + w/2) * scale_x)
            y2 = int((cy + h/2) * scale_y)
            detections.append({
                'label': label,
                'confidence': max_score,
                'bbox': (x1, y1, x2, y2)
            })
    
    # Sort by confidence
    detections.sort(key=lambda x: x['confidence'], reverse=True)
    return detections[:10]


def display_detections_tft(detections: list, fb_device: str = "/dev/fb0"):
    """Render detections to TFT display."""
    import pygame
    import numpy as np
    import mmap
    from struct import pack_into
    
    print(f"🖥️  Rendering to TFT display ({fb_device})...")
    
    # Read framebuffer geometry
    width, height = 480, 320
    try:
        with open(f"/sys/class/graphics/{Path(fb_device).name}/virtual_size") as f:
            parts = f.read().strip().split(',')
            width, height = int(parts[0]), int(parts[1])
    except:
        pass
    
    print(f"   Display: {width}x{height}")
    
    # Create pygame surface (offscreen)
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
    pygame.init()
    surface = pygame.Surface((width, height))
    
    # Draw background
    surface.fill((20, 30, 60))  # Dark blue
    
    # Draw title
    font_large = pygame.font.Font(None, 48)
    font_small = pygame.font.Font(None, 32)
    
    title = font_large.render("Vision Test", True, (255, 255, 255))
    surface.blit(title, (width//2 - title.get_width()//2, 20))
    
    # Draw detections
    y_offset = 80
    if not detections:
        no_det = font_small.render("No objects detected", True, (180, 180, 180))
        surface.blit(no_det, (width//2 - no_det.get_width()//2, height//2))
    else:
        for i, det in enumerate(detections[:5]):
            text = f"{det['label']}: {det['confidence']*100:.1f}%"
            color = (100, 255, 100) if det['confidence'] > 0.5 else (255, 200, 100)
            rendered = font_small.render(text, True, color)
            surface.blit(rendered, (40, y_offset + i * 40))
    
    # Draw timestamp
    ts = font_small.render(time.strftime("%H:%M:%S"), True, (100, 100, 100))
    surface.blit(ts, (width - ts.get_width() - 10, height - 30))
    
    # Convert to RGB565 and write to framebuffer
    arr = pygame.surfarray.array3d(surface)
    frame = np.transpose(arr, (1, 0, 2)).astype(np.uint16)
    r, g, b = frame[:,:,0], frame[:,:,1], frame[:,:,2]
    rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    data = rgb565.astype('<u2').tobytes()
    
    with open(fb_device, 'r+b', buffering=0) as fb:
        fb.write(data)
    
    print(f"   ✅ Display updated")
    pygame.quit()


def run_full_test(args):
    """Run full pipeline: capture -> detect -> display."""
    print("\n" + "="*60)
    print("   VISION + DISPLAY INTEGRATION TEST")
    print("="*60 + "\n")
    
    frame_path = "/tmp/vision_test_frame.npy"
    model_path = args.model
    
    # Step 1: Capture
    if not capture_with_system_python(frame_path):
        print("\n❌ FAILED: Camera capture")
        return False
    
    # Step 2: Detect
    if not Path(model_path).exists():
        print(f"\n❌ FAILED: Model not found at {model_path}")
        return False
    
    detections = detect_objects(frame_path, model_path)
    print(f"\n   Found {len(detections)} object(s):")
    for det in detections[:5]:
        print(f"     • {det['label']:15s} {det['confidence']*100:5.1f}%")
    
    # Step 3: Display
    if args.display:
        display_detections_tft(detections, args.fb)
    
    print("\n" + "="*60)
    print("   ✅ VISION + DISPLAY TEST: PASSED")
    print("="*60 + "\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Vision + Display Test")
    parser.add_argument("--capture-only", action="store_true", help="Only capture frame")
    parser.add_argument("--detect", type=str, help="Run detection on frame file")
    parser.add_argument("--full", action="store_true", help="Run full pipeline")
    parser.add_argument("--model", default="models/vision/yolo11n.onnx", help="YOLO model path")
    parser.add_argument("--fb", default="/dev/fb0", help="Framebuffer device")
    parser.add_argument("--no-display", dest="display", action="store_false", help="Skip display")
    args = parser.parse_args()
    
    if args.capture_only:
        if capture_with_system_python():
            print("✅ Capture successful")
        else:
            print("❌ Capture failed")
            sys.exit(1)
    elif args.detect:
        detections = detect_objects(args.detect, args.model)
        print(f"\nDetections: {len(detections)}")
        for det in detections:
            print(f"  {det['label']}: {det['confidence']*100:.1f}%")
        if args.display:
            display_detections_tft(detections, args.fb)
    elif args.full:
        if not run_full_test(args):
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
