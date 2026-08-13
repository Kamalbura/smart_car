#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/llm_e2e.log"
CORE_PY="$ROOT_DIR/.venvs/core/bin/python"
LLM_PY="$ROOT_DIR/.venvs/llme/bin/python"
MODEL_PATH="$ROOT_DIR/models/llm/tinyllama-1.1b-chat.Q4_K_M.gguf"
LLM_BIN="$ROOT_DIR/third_party/llama.cpp/bin/llama-server"
PORT=${LLM_E2E_PORT:-8093}
UP="tcp://127.0.0.1:6510"
DOWN="tcp://127.0.0.1:6511"

if [[ ! -x "$CORE_PY" ]]; then
  echo "Missing core python at $CORE_PY" | tee -a "$LOG_FILE"
  exit 1
fi
if [[ ! -x "$LLM_PY" ]]; then
  echo "Missing llm python at $LLM_PY" | tee -a "$LOG_FILE"
  exit 1
fi
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "TinyLlama model missing at $MODEL_PATH" | tee -a "$LOG_FILE"
  exit 1
fi
if [[ ! -x "$LLM_BIN" ]]; then
  echo "llama-server binary missing at $LLM_BIN" | tee -a "$LOG_FILE"
  exit 1
fi

export IPC_UPSTREAM="$UP"
export IPC_DOWNSTREAM="$DOWN"
export STT_ENGINE_DISABLED=1
export PYTHONPATH="$ROOT_DIR"
export LLM_E2E_TTS_LOG="$LOG_DIR/llm_e2e_tts.txt"
rm -f "$LLM_E2E_TTS_LOG"

cleanup() {
  for pid in ${TTS_PID:-} ${LLM_PID:-} ${ORCH_PID:-}; do
    if [[ -n "$pid" ]]; then
      kill "$pid" >/dev/null 2>&1 || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT

cd "$ROOT_DIR"

# Start orchestrator
"$CORE_PY" -m src.core.orchestrator >"$LOG_DIR/orchestrator_llm_e2e.log" 2>&1 &
ORCH_PID=$!
sleep 1

# Start llm runner (spawns llama-server)
"$LLM_PY" src/llm/llm_runner.py --port "$PORT" --host 127.0.0.1 --model "$MODEL_PATH" >"$LOG_DIR/llm_runner_e2e.log" 2>&1 &
LLM_PID=$!

# Start stub TTS listener
"$CORE_PY" - <<'PY' >"$LOG_DIR/tts_stub.log" 2>&1 &
import json
import os
import time
from pathlib import Path
import zmq

up = os.environ["IPC_UPSTREAM"]
down = os.environ["IPC_DOWNSTREAM"]
log_path = Path(os.environ.get("LLM_E2E_TTS_LOG", "logs/llm_e2e_tts.txt"))
ctx = zmq.Context.instance()
sub = ctx.socket(zmq.SUB)
sub.connect(down)
sub.setsockopt(zmq.SUBSCRIBE, b"tts.speak")
pub = ctx.socket(zmq.PUB)
pub.connect(up)
poller = zmq.Poller()
poller.register(sub, zmq.POLLIN)
deadline = time.time() + 30
while time.time() < deadline:
    events = dict(poller.poll(500))
    if sub in events:
        topic, data = sub.recv_multipart()
        msg = json.loads(data)
        text = msg.get("text", "").strip()
        log_path.write_text(text)
        pub.send_multipart([topic, json.dumps({"done": True, "timestamp": int(time.time())}).encode("utf-8")])
        break
else:
    raise SystemExit("TTS stub timed out waiting for text")
PY
TTS_PID=$!

sleep 5  # allow services to come up

# Send wakeword and STT transcription
"$CORE_PY" - <<'PY'
import json
import os
import time
import zmq

ctx = zmq.Context.instance()
pub = ctx.socket(zmq.PUB)
pub.connect(os.environ["IPC_UPSTREAM"])
time.sleep(0.5)

def send(topic, payload):
    pub.send_multipart([topic, json.dumps(payload).encode("utf-8")])

send(b"ww.detected", {"timestamp": int(time.time()), "keyword": "robo", "confidence": 0.99})
time.sleep(0.5)
send(b"stt.transcription", {"timestamp": int(time.time()), "text": "What is 2+2?", "confidence": 0.95, "language": "en"})
PY

wait "$TTS_PID"

if [[ ! -s "$LLM_E2E_TTS_LOG" ]]; then
  echo "TTS stub did not capture any text" | tee -a "$LOG_FILE"
  exit 1
fi
if ! grep -qi "4" "$LLM_E2E_TTS_LOG"; then
  echo "LLM response missing expected answer" | tee -a "$LOG_FILE"
  exit 1
fi

echo "LLM e2e pipeline test passed" | tee -a "$LOG_FILE"
