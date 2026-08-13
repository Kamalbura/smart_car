#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
VENV_PATH="$PROJECT_ROOT/.venvs/llme"
PYTHON_BIN="$VENV_PATH/bin/python"
MODEL_DIR="$PROJECT_ROOT/models/llm"
MODEL_DEST="tinyllama-1.1b-chat.Q4_K_M.gguf"
REPO_ID="TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF"
REPO_FILE="tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
EXPECTED_SHA256="9fecc3b3cd76bba89d504f29b616eedf7da85b96540e490ca5824d3f7d2776a0"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing llm virtualenv at $VENV_PATH" >&2
  exit 1
fi

mkdir -p "$MODEL_DIR"

export REPO_ID REPO_FILE EXPECTED_SHA256 MODEL_DIR MODEL_DEST

"$PYTHON_BIN" - <<'PY'
import hashlib
import os
import shutil
from pathlib import Path
from huggingface_hub import hf_hub_download

repo_id = os.environ["REPO_ID"]
repo_file = os.environ["REPO_FILE"]
expected = os.environ["EXPECTED_SHA256"]
model_dir = Path(os.environ["MODEL_DIR"])
dest_name = os.environ["MODEL_DEST"]
dest_path = model_dir / dest_name

downloaded = hf_hub_download(repo_id=repo_id, filename=repo_file, repo_type="model")
sha256 = hashlib.sha256(Path(downloaded).read_bytes()).hexdigest()
if sha256 != expected:
    raise SystemExit(f"Checksum mismatch: expected {expected}, got {sha256}")

tmp_dest = dest_path.with_suffix(dest_path.suffix + ".tmp")
if tmp_dest.exists():
    tmp_dest.unlink()
shutil.copy2(downloaded, tmp_dest)
tmp_dest.replace(dest_path)
print(f"Model saved to {dest_path} (sha256={sha256})")
PY
