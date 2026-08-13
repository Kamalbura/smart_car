#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODEL_DIR="$ROOT_DIR/models/whisper"
MODEL_NAME="tiny.en-q5_1.gguf"
MODEL_URL="${MODEL_URL:-https://huggingface.co/ggerganov/whisper.cpp/resolve/main/gguf/tiny.en-q5_1.gguf}"
CHECKSUM_URL="${CHECKSUM_URL:-${MODEL_URL}.sha256}"
EXPECTED_SHA256="${EXPECTED_SHA256:-}"
LOG_FILE="$ROOT_DIR/logs/setup.log"

mkdir -p "$MODEL_DIR" "$ROOT_DIR/logs"

log(){
  local msg="$1"
  printf "%s [fetch_whisper_model] %s\n" "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$msg" | tee -a "$LOG_FILE"
}

TMP_FILE="$MODEL_DIR/$MODEL_NAME.partial"
DEST_FILE="$MODEL_DIR/$MODEL_NAME"

log "Downloading $MODEL_NAME"
curl -fL "$MODEL_URL" -o "$TMP_FILE"

if [[ -n "$EXPECTED_SHA256" ]]; then
  echo "$EXPECTED_SHA256  $TMP_FILE" | sha256sum -c -
elif curl -fsL "$CHECKSUM_URL" -o "$TMP_FILE.sha256"; then
  if grep -q " " "$TMP_FILE.sha256"; then
    sed -i "s#  .*#  $TMP_FILE#" "$TMP_FILE.sha256"
  else
    HASH_VAL="$(cat "$TMP_FILE.sha256")"
    echo "$HASH_VAL  $TMP_FILE" > "$TMP_FILE.sha256"
  fi
  sha256sum -c "$TMP_FILE.sha256"
else
  log "No checksum available (set EXPECTED_SHA256 or CHECKSUM_URL). Aborting."
  rm -f "$TMP_FILE" "$TMP_FILE.sha256"
  exit 1
fi

mv "$TMP_FILE" "$DEST_FILE"
rm -f "$TMP_FILE.sha256"
log "Model stored at $DEST_FILE"
