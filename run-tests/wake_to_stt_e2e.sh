#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$ROOT_DIR/logs/setup.log"
CORE_PYTHON="$ROOT_DIR/.venvs/core/bin/python"

if [[ ! -x "$CORE_PYTHON" ]]; then
  echo "Missing core virtualenv at $CORE_PYTHON" | tee -a "$LOG_FILE"
  exit 1
fi

log(){
  local msg="$1"
  printf "%s [wake_to_stt_e2e] %s\n" "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$msg" | tee -a "$LOG_FILE"
}

export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR}"

log "Executing wakeword→STT→LLM orchestration tests"
cd "$ROOT_DIR"
"$CORE_PYTHON" -m pytest src/tests/test_wakeword_sim.py src/tests/test_stt_sim.py src/tests/test_orchestrator_flow.py -q
log "Wake→STT e2e tests completed"
