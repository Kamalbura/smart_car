#!/usr/bin/env bash
set -euo pipefail

DEST="${DEST:-/opt/models/yolo}"
URL="${URL:-https://github.com/ultralytics/assets/releases/download/v8.1.0/yolo11n.onnx}"
NAME="${NAME:-yolo11n.onnx}"

sudo mkdir -p "$DEST"
sudo curl -fL "$URL" -o "$DEST/$NAME"
echo "Downloaded YOLO11n ONNX to $DEST/$NAME"