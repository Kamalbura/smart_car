#!/usr/bin/env bash
set -euo pipefail

# Simple end-to-end smoke test in simulation mode for the AudioManager
# + wakeword + STT wrapper path. This script does not require real
# hardware and is intended for developer use only.

cd "$(dirname "$0")/.."

LOG_DIR="logs"
RUN_DIR="run"
mkdir -p "$LOG_DIR" "$RUN_DIR"

# Start AudioManager (sim skeleton)
source .venvs/stte/bin/activate
python -m src.audio.audio_manager --config config/system.yaml \
  > "$LOG_DIR/audio_manager_sim.log" 2>&1 &
echo $! > "$RUN_DIR/audio_manager_sim.pid"

# Give it a moment to bind sockets
sleep 1

# Start wakeword in sim mode
python -m src.wakeword.porcupine_runner --config config/system.yaml --sim \
  > "$LOG_DIR/wakeword_am_sim.log" 2>&1 &
echo $! > "$RUN_DIR/wakeword_am_sim.pid"

# Start STT wrapper in sim mode
python -m src.stt.stt_wrapper_runner --config config/system.yaml --sim \
  > "$LOG_DIR/stt_wrapper_sim.log" 2>&1 &
echo $! > "$RUN_DIR/stt_wrapper_sim.pid"

# Give processes a little time to initialize
sleep 1

echo "e2e_audio_wakeword_stt.sh: processes started (sim mode). Check logs/ for details."