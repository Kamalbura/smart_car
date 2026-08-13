# IPC & UART Contract

## ZeroMQ topics
- `ww.detected` → { "timestamp": int, "keyword": "robo", "variant": string, "confidence": float, "source": "porcupine" }
- `stt.transcription` → { "timestamp": int, "text": string, "confidence": float (0-1), "language": "en", "durations_ms": {"capture": int, "whisper": int, "total": int} }
- `llm.request` → { "text": string }
- `llm.response` → { "timestamp": int, "text": string, "tokens": int, "latency_ms": int }
- `tts.speak` → downstream `{ "text": string }`, upstream completion `{ "done": true, "timestamp": int }`
- `visn.object` → { "label": string, "bbox": [int,int,int,int], "confidence": float, "ts": float }
- `cmd.pause.vision` → { "pause": bool }
- `nav.command` → { "direction": "forward"|"backward"|"left"|"right"|"stop" }

## Orchestrator Handling
Upon receiving `ww.detected`, the orchestrator must:
1. Immediately publish `cmd.pause.vision` with `{"pause": true}`.
2. Trigger STT capture (spawns whisper runner and publishes `cmd.listen.start`).
3. On `stt.transcription`, publish `llm.request` with the transcript, stop listening, and keep vision paused.
4. On `llm.response`, emit `nav.command` if needed, forward `text` to `tts.speak`, and resume vision only after a `tts.speak` completion payload (`{"done": true}`) arrives on the upstream bus.

Example `ww.detected`:
```json
{"timestamp": 1763600000, "keyword": "robo", "variant": "hey robo", "confidence": 0.87, "source": "porcupine"}
```

## UART protocol
- Commands: FWD, BWD, LEFT, RIGHT, STOP
- Frame: `<CMD>\n`