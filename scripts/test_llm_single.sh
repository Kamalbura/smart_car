#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/test_llm_single.log"
MODEL_PATH="$ROOT_DIR/models/llm/tinyllama-1.1b-chat.Q4_K_M.gguf"
SERVER_BIN="$ROOT_DIR/third_party/llama.cpp/bin/llama-server"
PORT=${LLM_TEST_PORT:-8091}
HOST="127.0.0.1"
PYTHON_BIN="$ROOT_DIR/.venvs/llme/bin/python"

mkdir -p "$LOG_DIR"

if [[ ! -x "$SERVER_BIN" ]]; then
  echo "llama-server binary missing at $SERVER_BIN" | tee -a "$LOG_FILE"
  exit 1
fi
if [[ ! -f "$MODEL_PATH" ]]; then
  echo "TinyLlama model missing at $MODEL_PATH" | tee -a "$LOG_FILE"
  exit 1
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing llme virtualenv python at $PYTHON_BIN" | tee -a "$LOG_FILE"
  exit 1
fi

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

"$SERVER_BIN" \
  --model "$MODEL_PATH" \
  --ctx-size 2048 \
  --host "$HOST" \
  --port "$PORT" \
  --threads 4 \
  --n-gpu-layers 0 \
  --temp 0.2 \
  >"$LOG_DIR/llama-server-test.log" 2>&1 &
SERVER_PID=$!

# Wait for server to come online
for _ in {1..30}; do
  if nc -z "$HOST" "$PORT" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! nc -z "$HOST" "$PORT" >/dev/null 2>&1; then
  echo "llama-server failed to start on $HOST:$PORT" | tee -a "$LOG_FILE"
  exit 1
fi

export PYTHONPATH="$ROOT_DIR"
export LLAMA_TEST_HOST="$HOST"
export LLAMA_TEST_PORT="$PORT"
"$PYTHON_BIN" - <<'PY'
import http.client
import json
import os

host = os.environ["LLAMA_TEST_HOST"]
port = int(os.environ["LLAMA_TEST_PORT"])
prompt = "What is 2+2? Give a short answer."
conn = http.client.HTTPConnection(host, port, timeout=60)
body = json.dumps({"prompt": prompt, "n_predict": 64, "stream": False})
conn.request("POST", "/completion", body=body, headers={"Content-Type": "application/json"})
resp = conn.getresponse()
data = resp.read().decode("utf-8")
conn.close()
if resp.status != 200:
    raise SystemExit(f"llama-server HTTP {resp.status}: {data}")
content = json.loads(data).get("content", "")
if isinstance(content, list):
    content = "".join(chunk.get("text", "") for chunk in content)
if "4" not in content:
    raise SystemExit(f"Unexpected response: {content}")
print("llama-server responded:", content.strip())
PY

echo "llama.cpp single-shot test passed" | tee -a "$LOG_FILE"
