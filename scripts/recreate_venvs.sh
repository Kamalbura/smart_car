#!/usr/bin/env bash
# Recreate project virtual environments using python3.11 just installed.
set -euo pipefail

ROOT="${ROOT:-$HOME/projects/pi-assistant}"
PY_BIN="${PY_BIN:-/usr/local/bin/python3.11}"
VENV_DIR="$ROOT/.venvs"
LOG="$ROOT/logs/setup.log"
UPDATE="$ROOT/update.txt"

TS_UTC() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
TS_IST() { TZ=Asia/Kolkata date +"%Y-%m-%d %H:%M:%S %Z"; }
log() { mkdir -p "$ROOT/logs"; printf "%s [venvs] %s\n" "$(TS_UTC)" "$1" | tee -a "$LOG"; }
update() { mkdir -p "$(dirname "$UPDATE")"; printf "%s - %s\n" "$(TS_IST)" "$1" >> "$UPDATE"; }

require_py() {
  if [[ ! -x "$PY_BIN" ]]; then
    echo "python3.11 not found at $PY_BIN" >&2
    exit 1
  fi
}

create_env() {
  local name="$1"; shift
  local req_file="$1"; shift
  local env_path="$VENV_DIR/$name"
  rm -rf "$env_path"
  "$PY_BIN" -m venv "$env_path"
  # shellcheck disable=SC1091
  source "$env_path/bin/activate"
  python -m pip install --upgrade pip
  if [[ -f "$req_file" ]]; then
    pip install -r "$req_file"
  fi
  deactivate
  log "Created venv $name using $("$env_path/bin/python" -V 2>&1)"
}

main() {
  require_py
  mkdir -p "$VENV_DIR"
  # Core/shared requirements
  req_core="$ROOT/requirements.txt"
  req_stte="${REQ_STTE:-$ROOT/requirements-stte.txt}"
  req_ttse="${REQ_TTSE:-$ROOT/requirements-ttse.txt}"
  req_llme="${REQ_LLME:-$ROOT/requirements-llme.txt}"
  req_visn="${REQ_VISN:-$ROOT/requirements-visn.txt}"
  req_dise="${REQ_DISE:-$ROOT/requirements-dise.txt}"

  create_env core "$req_core"
  # Optional specialized envs (use env-specific requirements if present, else core)
  create_env stte "$(test -f "$req_stte" && echo "$req_stte" || echo "$req_core")"
  create_env ttse "$(test -f "$req_ttse" && echo "$req_ttse" || echo "$req_core")"
  create_env llme "$(test -f "$req_llme" && echo "$req_llme" || echo "$req_core")"
  create_env visn "$(test -f "$req_visn" && echo "$req_visn" || echo "$req_core")"
  create_env dise "$(test -f "$req_dise" && echo "$req_dise" || echo "$req_core")"
  update "Recreated venvs under $VENV_DIR using python3.11"
}
main "$@"
