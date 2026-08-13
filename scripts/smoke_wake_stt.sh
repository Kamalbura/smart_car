#!/usr/bin/env bash
set -euo pipefail

# Smoke test: wakeword (sim) -> orchestrator -> STT (simulated transcription) -> LLM -> TTS completion.
# This does not invoke real audio; it uses simulation + fabricated events over ZMQ.

ROOT="${PROJECT_ROOT:-/home/dev/project_root}"
export IPC_UPSTREAM="tcp://127.0.0.1:6300"
export IPC_DOWNSTREAM="tcp://127.0.0.1:6301"

python_version() { python -c 'import sys;print(".".join(map(str,sys.version_info[:3])))'; }

echo "[smoke] Python $(python_version)"

echo "[smoke] Starting orchestrator" &
python "$ROOT/src/core/orchestrator.py" &
ORCH_PID=$!
sleep 0.5

echo "[smoke] Trigger wakeword (sim)" &
python "$ROOT/src/wakeword/porcupine_runner.py" --sim --after 0.2 &
WK_PID=$!

sleep 1

echo "[smoke] Publish STT transcription"
python - <<'PY'
import os, json, time, zmq
ctx = zmq.Context.instance()
pub = ctx.socket(zmq.PUB)
pub.connect(os.environ['IPC_UPSTREAM'])
pub.send_multipart([b'stt.transcription', json.dumps({
    'timestamp': int(time.time()),
    'text': 'move forward',
    'confidence': 0.92,
    'language': 'en'
}).encode()])
PY

sleep 0.5
echo "[smoke] Publish LLM response (navigate forward)"
python - <<'PY'
import os, json, time, zmq
ctx = zmq.Context.instance()
pub = ctx.socket(zmq.PUB)
pub.connect(os.environ['IPC_UPSTREAM'])
pub.send_multipart([b'llm.response', json.dumps({
    'json': {'intent': 'navigate', 'slots': {'direction': 'forward'}, 'speak': 'Moving forward'}
}).encode()])
PY

sleep 0.5
echo "[smoke] Publish TTS completion"
python - <<'PY'
import os, json, time, zmq
ctx = zmq.Context.instance()
pub = ctx.socket(zmq.PUB)
pub.connect(os.environ['IPC_UPSTREAM'])
pub.send_multipart([b'tts.speak', json.dumps({'done': True}).encode()])
PY

echo "[smoke] Capture downstream commands"
python - <<'PY'
import os, zmq, time, json
ctx = zmq.Context.instance()
sub = ctx.socket(zmq.SUB)
sub.connect(os.environ['IPC_DOWNSTREAM'])
for t in [b'cmd.pause.vision', b'cmd.listen.start', b'cmd.listen.stop', b'tts.speak', b'nav.command']:
    sub.setsockopt(zmq.SUBSCRIBE, t)
deadline = time.time() + 3
events = []
while time.time() < deadline:
    try:
        topic, data = sub.recv_multipart(flags=zmq.NOBLOCK)
        events.append((topic.decode(), json.loads(data)))
    except zmq.Again:
        time.sleep(0.1)
print('[smoke] downstream events:')
for e in events:
    print('  ', e)
PY

echo "[smoke] Done"
kill $ORCH_PID $WK_PID 2>/dev/null || true
wait 2>/dev/null || true