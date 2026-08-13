#!/usr/bin/env bash
set -euo pipefail

# Fetch a faster-whisper model into third_party directory using the STT venv.
# Usage: ./scripts/fetch_whisper_fast_model.sh tiny.en [download_root]

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${PROJECT_ROOT}/.venvs/stte/bin/python"
MODEL_NAME="${1:-tiny.en}"
DOWNLOAD_ROOT="${2:-${PROJECT_ROOT}/third_party/whisper-fast}"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "STT venv python not found at ${VENV_PY}" >&2
  exit 1
fi

mkdir -p "${DOWNLOAD_ROOT}"

"${VENV_PY}" - <<'PY' "${MODEL_NAME}" "${DOWNLOAD_ROOT}"
import sys
from pathlib import Path

model_name = sys.argv[1]
download_root = sys.argv[2]

try:
    from faster_whisper import WhisperModel
except Exception as e:
    print("ERROR: faster-whisper is not installed in the STT venv.", file=sys.stderr)
    print("Please add it to requirements-stte.txt and install.", file=sys.stderr)
    sys.exit(2)

print(f"Downloading model '{model_name}' to '{download_root}'...")
WhisperModel(model_name, device="cpu", compute_type="int8", download_root=download_root)
print("Done.")
PY

echo "Model cached under: ${DOWNLOAD_ROOT}"
