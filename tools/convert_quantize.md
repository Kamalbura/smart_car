# YOLOv5 -> ONNX -> TFLite -> EdgeTPU (notes)

1) Clone YOLOv5 / Ultralytics and install deps:

```bash
git clone https://github.com/ultralytics/yolov5.git
cd yolov5
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2) Export to ONNX and TFLite (Ultralytics has `export.py`):

```bash
python export.py --weights yolov5n.pt --img 320 --batch 1 --device cpu --include onnx,tflite
```

3) Optionally simplify ONNX:

```bash
pip install onnxsim
python -m onnxsim model.onnx model-sim.onnx --input-shape "1,3,320,320"
```

4) Convert ONNX -> SavedModel -> TFLite (if you need more control):
- use `onnx-tf` to convert ONNX to TensorFlow SavedModel, then use `tf.lite.TFLiteConverter` with a representative dataset.

5) Quantize to int8 with a representative dataset (example):

See `tools/rep_dataset.py` to prepare `rep_images/` then use a short Python script that loads the saved_model and provides a generator of uint8 images for `converter.representative_dataset`.

6) Compile for EdgeTPU (on x86/arm host with edgetpu_compiler installed):

```bash
edgetpu_compiler model_quant.tflite
```

7) Test the produced model on a sample image locally (use TFLite interpreter or ONNX runtime) and compare outputs with the PyTorch model to ensure parity.
