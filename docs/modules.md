# Module Specifications

## Wakeword (`src/wakeword`)
- `porcupine_runner.py`: Porcupine wakeword using single .ppn model (`hey_robo.ppn`) with access key from `PV_ACCESS_KEY`. Publishes `ww.detected` payload `{timestamp, keyword:"robo", variant:"robo", confidence, source}`. Simulation via `--sim`.

## STT (`src/stt`)
- `engine.py`: Spawns `whisper_runner.py` via `.venvs/stte/bin/python`, ensuring `third_party/whisper.cpp/main` exists and wiring IPC overrides.
- `whisper_runner.py`: Records 16 kHz mono PCM from `arecord` (USB mic `plughw:3,0`), trims on silence, runs whisper.cpp `main` with `tiny.en-q5_1.gguf`, and publishes `stt.transcription` payload `{timestamp, text, confidence, language}`.
- Tooling:
	- `scripts/build_whispercpp.sh`: clones & compiles whisper.cpp into `third_party/whisper.cpp/main`.
	- `scripts/fetch_whisper_model.sh`: downloads `tiny.en-q5_1.gguf` with SHA-256 verification to `models/whisper/`.
	- `scripts/test_whisper_stt.sh`: executes `pytest src/tests/test_stt_sim.py` in the STT venv.

## TTS (`src/tts`)
- `piper_runner.py`: Subscribes to `tts.speak`, runs Piper, pipes to `aplay`, and publishes `{ "done": true }` on `tts.speak` (upstream) when playback completes so the orchestrator can resume vision.

## LLM (`src/llm`)
- `llm_runner.py`: Supervises `third_party/llama.cpp/bin/llama-server`, keeps it alive, POSTs prompts to `/completion`, and publishes `llm.response` payloads `{timestamp,text,tokens,latency_ms}` when requests arrive on `llm.request`.
- `llama_server.py`: Legacy intent-only runner retained for reference.

## Vision (`src/vision`)
- `vision_runner.py`: Captures frames, detects with YOLO ONNX, publishes `visn.object`, handles pause/resume.

## UART (`src/uart`)
- `bridge.py`: Subscribes to `nav.command`, sends UART frames to ESP32.
- `sim_uart.py`: TCP simulator for UART.

## Core (`src/core`)
- `orchestrator.py`: Event loop wiring wakeword → pause vision → start STT → LLM request → nav + TTS → resume vision after TTS completion.
- `ipc.py`: ZMQ topic constants and pub/sub helpers.
- `config_loader.py`: Loads YAML configs.
- `logging_setup.py`: Rotating log setup.

## Tools (`src/tools`)
- `cli.py`: Developer CLI.

## Tests (`src/tests`)
- Unit tests for each module.
