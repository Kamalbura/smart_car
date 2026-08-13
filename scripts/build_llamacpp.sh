#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/home/dev/project_root}"
DEST="$ROOT/third_party/llama.cpp"
LOG="$ROOT/logs/setup.log"

mkdir -p "$ROOT/logs" "$ROOT/third_party"
echo "$(date -u +%FT%TZ) [build] llama.cpp: starting" | tee -a "$LOG"

if [[ ! -d "$DEST" ]]; then
  git clone --depth=1 https://github.com/ggerganov/llama.cpp "$DEST"
else
  (cd "$DEST" && git pull --ff-only)
fi

cd "$DEST"
make -j"$(nproc)"
echo "$(date -u +%FT%TZ) [build] llama.cpp: built main at $DEST/main" | tee -a "$LOG"