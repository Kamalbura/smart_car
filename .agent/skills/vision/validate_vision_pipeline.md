---
name: validate_vision_pipeline
description: Ensure cameras and models are functioning.
---

# Validate Vision Pipeline

Ensures the eyes of the car are open.

## When to use
- Startup.
- When object detection seems stuck.

## Step-by-Step Instructions
1. **Activate Environment**: `visn`.
2. **Test Hardware**:
   ```bash
   python3 tools/capture_cameras.py
   ```
   (Verify images are saved).
3. **Test Inference**:
   ```bash
   python3 src/vision/pi_inference.py --test-image img1.jpg
   ```
   (Verify bounding boxes are returned).

## Verification Checklist
- [ ] Camera opens without "Resource busy".
- [ ] Model loads (tflite/onnx).
- [ ] Inference time < 200ms (Pi 4) / < 50ms (Pi 5).

## Rules & Constraints
- Release camera resources immediately after testing.
