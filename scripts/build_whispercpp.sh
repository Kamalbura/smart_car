#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT:-/home/dev/project_root}"
THIRD_PARTY_DIR="$ROOT_DIR/third_party"
WHISPER_DIR="$THIRD_PARTY_DIR/whisper.cpp"
LOG_FILE="$ROOT_DIR/logs/setup.log"
REPO_URL="https://github.com/ggerganov/whisper.cpp.git"

mkdir -p "$ROOT_DIR/logs" "$THIRD_PARTY_DIR"

log(){
  local msg="$1"
  printf "%s [build_whispercpp] %s\n" "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$msg" | tee -a "$LOG_FILE"
}

log "Starting whisper.cpp build"
if [[ ! -d "$WHISPER_DIR/.git" ]]; then
  log "Cloning whisper.cpp into $WHISPER_DIR"
  git clone --depth=1 "$REPO_URL" "$WHISPER_DIR"
else
  log "Updating existing whisper.cpp checkout"
  git -C "$WHISPER_DIR" fetch --depth=1 origin master
  git -C "$WHISPER_DIR" reset --hard origin/master
fi

log "Configuring CMake project"
cmake -S "$WHISPER_DIR" -B "$WHISPER_DIR/build" -DCMAKE_BUILD_TYPE=Release > >(tee -a "$LOG_FILE")
log "Building whisper.cpp binaries"
cmake --build "$WHISPER_DIR/build" -j"$(nproc)" > >(tee -a "$LOG_FILE")

BIN_SRC="$WHISPER_DIR/build/bin/main"
BIN_DST="$WHISPER_DIR/main"
if [[ -f "$BIN_SRC" ]]; then
  cp "$BIN_SRC" "$BIN_DST"
  chmod +x "$BIN_DST"
  log "main binary ready at $BIN_DST"
else
  log "ERROR: expected binary $BIN_SRC missing"
  exit 1
fi

log "whisper.cpp build complete"