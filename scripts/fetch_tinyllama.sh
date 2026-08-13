#!/usr/bin/env bash
set -euo pipefail

DEST="${DEST:-/opt/models/llama}"
URL="${URL:-https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf}"
NAME="${NAME:-tinyllama-1.1b-q4_k_m.gguf}"

sudo mkdir -p "$DEST"
sudo curl -fL "$URL" -o "$DEST/$NAME"
echo "Downloaded TinyLlama GGUF to $DEST/$NAME"