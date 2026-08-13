#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venvs/llme"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "llme venv not found at $VENV_DIR" >&2
  exit 1
fi

"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install google-generativeai

echo "google-generativeai installed in $VENV_DIR"
