**Vision - Raspberry Pi Integration**

- **Purpose:** Run lightweight object detection on Raspberry Pi using YOLO exports (TFLite/ONNX/OpenCV).
- **Recommended models:** `yolov5n` (320 or 640), or pruned/quantized variants for better FPS.
- **Files added:** `src/vision/pi_inference.py`, `scripts/run_pi_inference.py`, `tools/rep_dataset.py`, `tools/convert_quantize.md`, `requirements-visn.txt`.
- **Quick start:**

  1. Export/convert a model into `models/`, e.g. `models/yolov5n.tflite`.
  2. Install dependencies (see `requirements-visn.txt`). Prefer `tflite-runtime` wheel on Pi.
  3. Run:

  ```bash
  ./scripts/run_pi_inference.py --backend tflite --model models/yolov5n.tflite --img 320
  ```

- **Notes:** Postprocessing is export-specific. The `postprocess_raw` function in `src/vision/pi_inference.py` is a placeholder — adapt it to the export shape (Ultralytics export provides documentation/examples).
