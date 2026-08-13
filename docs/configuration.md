# Configuration reference

`config/system.yaml` is the single source of runtime settings. Environment
variables are expanded with `${ENV:NAME}`, and `${PROJECT_ROOT}` resolves to
the repository root.

**Read the dead-keys section first.** Nineteen keys in this file are read by
nothing. Several look load-bearing and are not, which has cost real debugging
time — changing them appears to do nothing because it does nothing.

---

## Dead keys

Verified by grepping every reader in `src/`. These are inert:

| Key | Reality |
|---|---|
| `audio.use_unified_pipeline` | **Reads as the most important flag in the file and is inert.** No code selects a pipeline from it. `voice-pipeline.service` hardcodes `src.audio.voice_service`; the "unified" modules are retired. |
| `audio.use_audio_manager` | The AudioManager was removed. |
| `audio.control_endpoint` | REQ/REP endpoint for a service that does not exist. |
| `audio.mic_device_node` | Used by the unit's `ExecStartPre` fuser line, not by Python. |
| `audio.preferred_device_substring` | `voice_service` matches the literal `"USB"` instead. |
| `audio.hw_sample_rate` | `voice_service` hardcodes 48000. |
| `audio.hw_buffer_ms`, `wakeword_frame_ms`, `stt_chunk_ms` | Never read. |
| `audio.speaker_device` | No consumer anywhere. |
| `wakeword.sim_mode`, `.fallback_engine`, `.stte_venv` | Never read. |
| `stt.runner_venv` | Never read; venvs come from the systemd units. |
| `display.spi_bus`, `.spi_device`, `.rotation`, `.resolution` | `face_fb` writes to `/dev/fb0` and takes rotation from the unit's `--rotate` flag. |
| `llm.assistant_name` | The name is baked into the prompt template. |

Deleting them would be honest. They are left in place so this table can explain
them, because silently removing config that someone believes is live is its own
kind of trap.

---

## `ipc`

| Key | Default | Effect |
|---|---|---|
| `upstream` | `tcp://127.0.0.1:6010` | Workers → orchestrator. The orchestrator **binds a SUB** here. |
| `downstream` | `tcp://127.0.0.1:6011` | Orchestrator → workers. It **binds a PUB** here. |

Overridden per process by `IPC_UPSTREAM` / `IPC_DOWNSTREAM`, which is how the
Docker topology points services at `orchestrator:6010` instead of loopback.

Do not point a second SUB at `upstream` — see the topology rule in
[architecture.md](architecture.md).

## `orchestrator`

| Key | Default | Effect |
|---|---|---|
| `auto_trigger_enabled` | `false` | Start listening after an idle period. Off because it triggers on background noise. |
| `auto_trigger_interval` | `60.0` | Idle seconds before auto-trigger. |

## `stt`

| Key | Default | Effect |
|---|---|---|
| `engine` | `azure_speech` | Selects the engine **inside `voice_service`**, not a separate process. |
| `timeout_seconds` | `90.0` | LISTENING watchdog. Exceeded → spoken feedback, back to IDLE. |
| `min_confidence` | `0.3` | Transcripts below this are rejected rather than acted on. |
| `silence_threshold` | `0.25` | RMS below which audio counts as silence. |
| `silence_duration_ms` | `800` | Silence needed to end capture. |
| `max_capture_seconds` | `15` | Hard cap on one utterance. |

## `llm`

| Key | Default | Effect |
|---|---|---|
| `engine` | `azure_openai` | Advisory; the running module is fixed by the systemd unit. |
| `timeout_seconds` | `45.0` | **THINKING watchdog.** On expiry the motors stop and the FSM releases. Without it one hung call left the robot permanently deaf. |
| `request_timeout_s` | `20.0` | HTTP timeout inside the runner. Must be well below the watchdog, or a reply arrives after the turn was abandoned. |
| `azure_temperature` | `1.0` | Pinned to 1 because Azure reasoning deployments reject anything else. Override only for a standard chat model. |
| `max_completion_tokens` | `320` | Was 160, which truncated JSON mid-string routinely. |
| `memory_max_turns` | `10` | Conversation turns retained. |
| `conversation_timeout_s` | `120` | Inactivity after which the conversation resets. |

## `tts`

| Key | Default | Effect |
|---|---|---|
| `timeout_seconds` | `60.0` | **SPEAKING watchdog.** Must exceed the longest utterance, because `done` only arrives after playback finishes. |
| `azure.voice` | `en-US-JennyNeural` | |
| `playback_device` | `plughw:3,0` | Read by the retired Piper runner only; the Azure runner uses the ALSA default. |

## `vision`

| Key | Default | Effect |
|---|---|---|
| `default_mode` | `off` | `off`, `on_no_stream`, or `on_with_stream`. Off means the camera is never opened until requested. Note YAML parses bare `off` as boolean false, which is handled. |
| `model_path_onnx` | — | See [models/vision/README.md](../models/vision/README.md). Weights are not committed. |
| `label_path` | — | Must be exactly 80 lines in COCO order or every detection is mislabelled. |
| `confidence` | `0.25` | Detection threshold. |
| `iou` | `0.45` | NMS overlap threshold. |
| `input_size` | `[640, 640]` | Must match the exported model. |
| `target_fps` | `15` | Aspirational — real throughput on a Pi is nearer 1 fps. |

## `nav`

| Key | Default | Effect |
|---|---|---|
| `uart_device` | `/dev/serial0` | Code default is `/dev/ttyAMA0`; config wins. |
| `baud_rate` | `115200` | Must match the firmware. |
| `timeout` | `1.0` | Serial read/write timeout. |
| `sensor_max_age_s` | `1.0` | Telemetry older than this refuses forward motion. At 20 Hz that is 20 missed frames. |
| `commands` | see file | Direction → ASCII token map for the **legacy** protocol. |

## `remote_interface`

| Key | Default | Effect |
|---|---|---|
| `bind_host` | `0.0.0.0` | Behind Caddy this should be internal-only; the container does not publish it. |
| `port` | `8770` | |
| `allowed_cidrs` | loopback + `100.64.0.0/10` | Source-IP allowlist. **Bypassed entirely when `REMOTE_AUTH_TOKEN` is set**, and meaningless behind NAT. Fails closed if empty or unparseable. |
| `session_timeout_s` | `15.0` | Remote session expiry. The app must poll faster than this or controls stay disabled. |

---

## Environment

Set in `.env`, never in this file. Every systemd unit requires `.env` to exist.

| Variable | Needed by |
|---|---|
| `AZURE_OPENAI_API_KEY`, `_ENDPOINT`, `_DEPLOYMENT` | llm |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | voice-pipeline, tts |
| `PV_ACCESS_KEY` | voice-pipeline (wakeword) |
| `REMOTE_AUTH_TOKEN` | remote-interface — optional, strongly recommended |
| `IPC_UPSTREAM`, `IPC_DOWNSTREAM` | overrides the `ipc` block |
| `LOG_STDOUT`, `LOG_LEVEL` | all services |

## Local overrides

`config/system.local.json` is loaded on top of `system.yaml` if present. Note
that the committed example describes a Vosk + phi-3 + yolov5 stack that no
longer exists anywhere in the code.
