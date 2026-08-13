#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_BIN="$ROOT_DIR/.venvs/stte/bin/python"
LOG_FILE="$ROOT_DIR/logs/setup.log"
TEST_FILE="src/tests/test_stt_sim.py"

if [[ ! -x "$VENV_BIN" ]]; then
  echo "Missing STT virtualenv at $VENV_BIN" | tee -a "$LOG_FILE"
  exit 1
fi

export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR}"

log(){
  local msg="$1"
  printf "%s [test_whisper_stt] %s\n" "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$msg" | tee -a "$LOG_FILE"
}

log "Running pytest $TEST_FILE"
cd "$ROOT_DIR"
"$VENV_BIN" -m pytest "$TEST_FILE" -q
log "STT simulation tests passed"
