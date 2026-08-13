#!/usr/bin/env bash
set -euo pipefail

VOICE_URL="${VOICE_URL:-https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/en_US-amy-medium.onnx}"
DEST="${DEST:-/opt/models/piper}"
NAME="${NAME:-en_US-amy-medium.onnx}"

sudo mkdir -p "$DEST"
sudo curl -fL "$VOICE_URL" -o "$DEST/$NAME"
echo "Downloaded voice to $DEST/$NAME"