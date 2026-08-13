# Services reference

One entry per deployed process. What it does, what it talks to, how it fails,
and how to tell whether it is working.

Derived from `deploy/systemd/*.service` and the source. If a module is not
listed here it is not running — see the dead-code note at the end.

---

## orchestrator

`src.core.orchestrator` · the only process that binds the bus

The state machine and the message router. Owns the conversation phase, decides
when the robot speaks and moves, and relays worker events downstream so other
services can see them.

| | |
|---|---|
| Subscribes | everything on `upstream` (it binds the SUB) |
| Publishes | `cmd.listen.*`, `cmd.pause.vision`, `cmd.vision.mode`, `cmd.visn.capture`, `llm.request`, `tts.speak`, `nav.command`, `display.state`, `display.text`, `remote.event`, `remote.session` |
| Relays | `visn.object`, `visn.capture`, `visn.frame`, `esp32.raw`, `llm.response` |
| Config | `orchestrator.*`, `stt.timeout_seconds`, `stt.min_confidence`, `llm.timeout_seconds`, `tts.timeout_seconds`, `vision.default_mode`, `remote_interface.session_timeout_s` |

**Fails by:** losing all state on restart. Phase returns to IDLE, the obstacle
latch clears, `vision_mode` resets to the config default — and it does **not**
publish a stop, so a moving robot keeps moving. A malformed payload can no
longer kill it; handlers are wrapped and a fault drops to ERROR with the motors
stopped.

**Check it:** `journalctl -fu orchestrator` should show `PHASE:` transitions on
every interaction. Silence during a conversation means it is wedged or deaf.

---

## voice-pipeline

`src.audio.voice_service` · wakeword + STT in one process

Holds the single microphone handle. Porcupine runs continuously; on detection
it captures until silence and sends the audio to Azure Speech.

Wakeword and STT are deliberately not separate processes — two of them
contending for one ALSA capture device is a failure no amount of retry logic
fixes.

| | |
|---|---|
| Subscribes | `cmd.listen.start`, `cmd.listen.stop` |
| Publishes | `ww.detected`, `stt.transcription` |
| Config | `stt.engine`, `stt.silence_threshold`, `stt.silence_duration_ms`, `stt.max_capture_seconds`, `wakeword.sensitivity`, `wakeword.model` |

**Fails by:** ⚠ not reopening a microphone that disappears. It logs and retries
against the dead stream forever, so the process stays alive and systemd never
restarts it. The Azure call also has no timeout, so a stalled TLS connection
hangs the whole single-threaded service. Both are known gaps.

**Check it:** say the wakeword; the LED ring should flash green within ~200 ms.
If it does not, this service is the first suspect.

---

## llm

`src.llm.azure_openai_runner` · Azure OpenAI

Builds the prompt from conversation memory plus the world-context snapshot,
calls Azure, extracts JSON tolerantly, and publishes the reply.

| | |
|---|---|
| Subscribes | `llm.request` |
| Publishes | `llm.response` (echoes `request_id`) |
| Config | `llm.timeout_seconds`, `llm.request_timeout_s`, `llm.azure_temperature`, `llm.max_completion_tokens`, `llm.memory_max_turns`, `llm.conversation_timeout_s` |
| Environment | `AZURE_OPENAI_API_KEY`, `_ENDPOINT`, `_DEPLOYMENT`, `_API_VERSION` |

**Fails by:** refusing to start without credentials, loudly and clearly
(`AZURE_OPENAI_API_KEY not configured`). A provider error produces a safe
spoken apology rather than reading the exception aloud. A response that arrives
after the orchestrator's 45 s watchdog is discarded on `request_id` mismatch.

---

## tts

`src.tts.azure_tts_runner` · Azure Speech synthesis

| | |
|---|---|
| Subscribes | `tts.speak` |
| Publishes | `tts.speak` with `started` / `done` |
| Config | `tts.azure.voice`, `tts.timeout_seconds` |

**Fails by:** ⚠ publishing `done: false` on failure, which the orchestrator
discards — so a failed synthesis costs a mandatory 60 s stall until the
SPEAKING watchdog fires. It also never publishes `started`, so the LED never
enters the speaking state.

---

## vision

`src.vision.vision_runner` · camera and YOLO11n

Off by default (`vision.default_mode: off`); the camera is not opened until
something enables it.

| | |
|---|---|
| Subscribes | `cmd.pause.vision`, `cmd.vision.mode`, `cmd.visn.capture` |
| Publishes | `visn.object` (one message **per detection**), `visn.frame`, `visn.capture` |
| Config | `vision.model_path_onnx`, `vision.label_path`, `vision.confidence`, `vision.iou`, `vision.input_size`, `vision.target_fps`, `vision.default_mode` |

**Fails by:** ⚠ a 100 % CPU busy-loop if the camera is unplugged mid-run — the
grabber thread dies, the last frame stays cached, and the consumer spins on a
stale-frame `continue` with no sleep. A failed open also leaks a
`VideoCapture` per retry.

**Check it:** enable via `POST /intent {"intent":"enable_vision"}`, then watch
for `visn.object` traffic.

---

## uart

`src.uart.motor_bridge` · the serial link

Translates `nav.command` into bytes and parses telemetry back.

| | |
|---|---|
| Subscribes | `nav.command` |
| Publishes | `esp32.raw` at 20 Hz |
| Config | `nav.uart_device`, `nav.baud_rate`, `nav.timeout`, `nav.commands`, `nav.sensor_max_age_s` |

Applies an **advisory** forward gate: no telemetry, stale telemetry (>1 s), or
all-sensors-invalid each refuse forward. The MCU is the real authority.

**Fails by:** dropping every `nav.command` published while it restarts, with no
indication at either end. ⚠ Still speaks the legacy ASCII protocol — see the
migration note in `architecture.md`.

---

## remote-interface

`src.remote.remote_interface` · HTTP API for the app

| | |
|---|---|
| Subscribes | `esp32.raw`, `llm.response`, `remote.event`, `display.*`, `visn.*`, `tts.speak`, `system.health` — all **downstream** |
| Publishes | `remote.intent`, `remote.session` |
| Routes | `GET /status /telemetry /health /logs /stream/mjpeg`, `POST /intent` |
| Config | `remote_interface.bind_host`, `.port`, `.allowed_cidrs`, `.session_timeout_s` |
| Environment | `REMOTE_AUTH_TOKEN` |

Marks the remote session active on `/status`, `/telemetry` and `/intent` — but
not `/health`, so health polling alone does not keep a session alive. Sessions
expire after 15 s, which is why the app polls at 1 s.

**Check it:** `curl -H "Authorization: Bearer $TOKEN" http://pi:8770/status`.
`/health` needs no token by design.

---

## display

`src.ui.face_fb` · Waveshare 3.5" panel

Writes RGB565 directly to `/dev/fb0` via `mmap`. No SDL, no X.

| | |
|---|---|
| Subscribes | `display.state`, `display.text` |
| Config | none that is actually read — `display.rotation`, `.spi_bus`, `.spi_device` are dead keys; rotation comes from the unit's `--rotate` flag |

---

## led-ring

`src.piled.led_ring_service` · 8× WS2812B on GPIO12

**Runs as root**, and must: NeoPixel bit-bang timing needs direct hardware
access. The only unit that does.

| | |
|---|---|
| Subscribes | `display.state`, `system.health` |
| Config | none — pin, count and brightness come from argparse defaults (D12 / 8 / 0.25) |

**Fails by:** staying lit on `systemctl stop`. Its cleanup only runs on
Ctrl-C, not SIGTERM.

---

## Not running

Present in the tree but started by nothing. Retired copies live in `dump/`.

| Module | Superseded by |
|---|---|
| `src/audio/unified_voice_pipeline.py`, `unified_audio.py`, `best_voice_pipeline.py` | `voice_service.py` |
| `src/stt/*_runner.py`, `src/stt/engine.py` | STT runs in-process in `voice_service` |
| `src/llm/gemini_runner.py`, `local_llm_runner.py` | `azure_openai_runner.py` |
| `src/tts/piper_runner.py` | `azure_tts_runner.py` |
| `src/uart/bridge.py`, `sim_uart.py` | `motor_bridge.py` |
| `src/ui/display_runner.py` | `face_fb.py` |

`config.audio.use_unified_pipeline: true` is read by nothing and does not
select any of the above. See [configuration.md](configuration.md).
