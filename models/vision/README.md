# Vision models

Weights are **not** committed to this repository. Put them here yourself.

Expected files, matching `vision:` in `config/system.yaml`:

| File | Config key | Required |
|---|---|---|
| `yolo11n.onnx` | `vision.model_path_onnx` | yes, for the `onnx` backend |
| `coco_labels.txt` | `vision.label_path` | yes |
| `yolo11n.param` / `yolo11n.bin` | `vision.model_path_ncnn_*` | only for `backend: ncnn` |

## Licensing — read before you redistribute

**YOLO11 weights are AGPL-3.0**, and Ultralytics applies that license to the
weights themselves, not just to their Python package. Running them through ONNX
Runtime avoids linking the AGPL library, but it does **not** change the license
on the weights.

What that means in practice:

- Using them yourself, privately, on your own robot: fine.
- Publishing a product or a network service built on them: AGPL-3.0 obligations
  attach, including source disclosure to users of that service.
- Committing the `.onnx` file into an Apache-2.0 repository: don't. That is
  exactly why this directory ships a README instead of a model.

This project's own source is Apache-2.0 (see `LICENSE`). The vision weights are
a runtime dependency you supply, under whatever license you obtain them.

If you need a fully permissive stack, swap the default for an Apache-2.0 or
MIT-licensed detector and re-benchmark on the Pi — accuracy will differ.

## Fetching yolo11n.onnx

The repo has a helper:

```bash
./scripts/fetch_yolo_onnx.sh
```

It pulls from Ultralytics' release assets:

```
https://github.com/ultralytics/assets/releases/download/v8.1.0/yolo11n.onnx
```

To do it by hand:

```bash
mkdir -p models/vision
curl -L -o models/vision/yolo11n.onnx \
  https://github.com/ultralytics/assets/releases/download/v8.1.0/yolo11n.onnx
```

Or export it yourself from PyTorch weights, which lets you pin the input size
to match `vision.input_size` (`[640, 640]`):

```bash
pip install ultralytics          # AGPL-3.0 — build tooling only, not shipped
yolo export model=yolo11n.pt format=onnx imgsz=640 opset=12
mv yolo11n.onnx models/vision/
```

Note that `ultralytics` and `torch` are **not** in any `requirements/*.txt` on
purpose — nothing at runtime imports them. `src/vision/detector.py` uses
`onnxruntime` (MIT) only. Install them in a throwaway environment for the export
and keep them out of `.venvs/visn`.

## COCO labels

80 class names, one per line, in the standard COCO order that matches the
model's output indices:

```bash
curl -L -o models/vision/coco_labels.txt \
  https://raw.githubusercontent.com/amikelive/coco-labels/master/coco-labels-2014_2017.txt
```

Verify you got 80 lines, or every detection will be mislabelled:

```bash
wc -l models/vision/coco_labels.txt   # expect 80
```

## Checking it works

```bash
python -m src.vision.pi_inference --image test.jpg --backend onnx
```

Vision ships **disabled** (`vision.default_mode: off`), so the camera is not
opened until something enables it. Turn it on for a session with:

```bash
curl -X POST http://127.0.0.1:8770/intent \
  -H 'Content-Type: application/json' \
  -d '{"intent":"enable_vision"}'
```
