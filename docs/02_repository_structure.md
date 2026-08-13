# Repository Structure

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | 02_repository_structure.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

The smart_car repository is a monorepo containing:

- Python services for Raspberry Pi
- Android application (Kotlin)
- ESP32 firmware (C++)
- Configuration files
- Systemd service definitions
- Documentation and scripts

The same repository is deployed to both the development PC (Windows) and the Raspberry Pi (production).

---

## Top-Level Directory Structure

```
smart_car/
├── src/                    # Python source code (Pi runtime)
├── mobile_app/             # Android application
├── config/                 # Configuration files
├── systemd/                # Service unit files
├── scripts/                # Utility and setup scripts
├── models/                 # ML models (wakeword, vision, TTS)
├── docs/                   # Legacy documentation
├── book/                   # Technical book/manual source
├── reports/                # Generated analysis reports
├── tools/                  # Development tools
├── third_party/            # External dependencies
├── logs/                   # Runtime logs (Pi only)
├── .venvs/                 # Python virtual environments (Pi only)
├── .env                    # Environment secrets (not committed)
├── requirements*.txt       # Python dependencies
└── README.md               # Project readme
```

---

## Source Directory (`src/`)

The `src/` directory contains all Python modules that run on the Raspberry Pi.

### Module Overview

| Directory | Purpose | Primary Entry Point | Runtime |
|-----------|---------|---------------------|---------|
| `src/core/` | Central orchestration and IPC | `orchestrator.py` | Pi |
| `src/remote/` | HTTP supervision API | `remote_interface.py` | Pi |
| `src/uart/` | ESP32 UART bridge | `motor_bridge.py` | Pi |
| `src/vision/` | Camera and YOLO inference | `vision_runner.py` | Pi |
| `src/audio/` | Wakeword and STT pipeline | `voice_service.py` | Pi |
| `src/llm/` | LLM integration | `azure_openai_runner.py` | Pi |
| `src/tts/` | Text-to-speech | `azure_tts_runner.py` | Pi |
| `src/stt/` | Speech-to-text engines | (library, used by audio) | Pi |
| `src/ui/` | Display rendering | `face_fb.py` | Pi |
| `src/piled/` | LED ring control | `led_ring_service.py` | Pi |
| `src/tests/` | Unit and integration tests | — | Dev |
| `src/tools/` | Development utilities | — | Dev |

### Core Module (`src/core/`)

| File | Role | Type |
|------|------|------|
| `orchestrator.py` | Central FSM, event routing, phase management | Service |
| `ipc.py` | ZeroMQ topic constants and socket factory | Library |
| `config_loader.py` | YAML configuration loading with env substitution | Library |
| `logging_setup.py` | Centralized logging configuration | Library |
| `world_context.py` | Aggregates state for LLM context | Library |
| `__init__.py` | Package marker | — |

### Remote Module (`src/remote/`)

| File | Role | Type |
|------|------|------|
| `remote_interface.py` | HTTP server for mobile app, telemetry aggregation | Service |
| `__init__.py` | Package marker | — |

### UART Module (`src/uart/`)

| File | Role | Type |
|------|------|------|
| `motor_bridge.py` | ZMQ-to-UART translator, sensor feedback publisher | Service |
| `bridge.py` | Legacy bridge implementation | Unused |
| `sim_uart.py` | UART simulation for development | Development |
| `esp-code.ino` | ESP32 Arduino firmware source | Firmware |
| `__pycache__/` | Python bytecode cache | Generated |

### Vision Module (`src/vision/`)

| File | Role | Type |
|------|------|------|
| `vision_runner.py` | Vision lifecycle manager, camera control, inference loop | Service |
| `detector.py` | YOLO detection wrapper (ONNX/NCNN) | Library |
| `pipeline.py` | Vision pipeline abstraction | Library |
| `pi_inference.py` | Pi-specific inference utilities | Library |
| `__init__.py` | Package marker | — |

### Audio Module (`src/audio/`)

| File | Role | Type |
|------|------|------|
| `voice_service.py` | Production wakeword + STT pipeline | Service |
| `unified_voice_pipeline.py` | Alternative unified pipeline | Alternative |
| `best_voice_pipeline.py` | Alternative pipeline variant | Alternative |
| `unified_audio.py` | Audio capture with ring buffer | Library |
| `__init__.py` | Package marker | — |

### LLM Module (`src/llm/`)

| File | Role | Type |
|------|------|------|
| `azure_openai_runner.py` | Azure OpenAI API integration | Service |
| `gemini_runner.py` | Google Gemini API integration | Alternative |
| `local_llm_runner.py` | Local LLM (llama.cpp) integration | Alternative |
| `conversation_memory.py` | Conversation history management | Library |
| `__init__.py` | Package marker | — |

### TTS Module (`src/tts/`)

| File | Role | Type |
|------|------|------|
| `azure_tts_runner.py` | Azure Speech TTS integration | Service |
| `piper_runner.py` | Local Piper TTS integration | Alternative |
| `__init__.py` | Package marker | — |

### STT Module (`src/stt/`)

| File | Role | Type |
|------|------|------|
| `azure_speech_runner.py` | Azure Speech STT integration | Library |
| `faster_whisper_runner.py` | Faster Whisper local STT | Library |
| `engine.py` | STT engine abstraction | Library |
| `__init__.py` | Package marker | — |

### UI Module (`src/ui/`)

| File | Role | Type |
|------|------|------|
| `face_fb.py` | Kawaii face renderer for TFT framebuffer | Service |
| `display_runner.py` | Alternative display implementation | Alternative |
| `tft_smiley_test.py` | Display testing utility | Development |
| `__init__.py` | Package marker | — |

### LED Module (`src/piled/`)

| File | Role | Type |
|------|------|------|
| `led_ring_service.py` | NeoPixel LED ring status indicator | Service |
| `led_ring_service.py.bak` | Backup of previous version | Backup |

---

## Mobile Application (`mobile_app/`)

The Android application is located in `mobile_app/` with standard Gradle structure.

### Directory Structure

```
mobile_app/
├── app/
│   └── src/
│       └── main/
│           ├── java/com/smartcar/supervision/
│           │   ├── MainActivity.kt
│           │   ├── data/
│           │   │   ├── Models.kt
│           │   │   ├── RobotApi.kt
│           │   │   ├── RobotRepository.kt
│           │   │   ├── SettingsStore.kt
│           │   │   └── IntentModels.kt
│           │   └── ui/
│           │       ├── AppState.kt
│           │       ├── AppViewModel.kt
│           │       ├── AppLog.kt
│           │       └── screens/
│           │           ├── MainScreen.kt
│           │           ├── StreamingCard.kt
│           │           ├── TelemetryCard.kt
│           │           ├── TelemetryPlaceholder.kt
│           │           └── IntentList.kt
│           ├── res/
│           └── AndroidManifest.xml
├── gradle/
├── build.gradle.kts
├── settings.gradle.kts
└── gradlew / gradlew.bat
```

### Key Source Files

| File | Purpose |
|------|---------|
| `MainActivity.kt` | Application entry point |
| `MainScreen.kt` | Primary UI with 5-tab navigation |
| `AppViewModel.kt` | MVVM ViewModel, state management, polling |
| `RobotRepository.kt` | Network layer, HTTP calls |
| `RobotApi.kt` | Retrofit interface definitions |
| `Models.kt` | Data classes for API responses |
| `AppState.kt` | UI state definitions |
| `SettingsStore.kt` | Persistent settings storage |

---

## Configuration (`config/`)

| File | Purpose |
|------|---------|
| `system.yaml` | Primary system configuration |
| `logging.yaml` | Logging configuration |
| `settings.yaml` | Additional settings |
| `settings.json` | JSON format settings |
| `config.json` | Legacy JSON configuration |
| `system.local.json` | Local overrides |

### Primary Configuration

`config/system.yaml` is the authoritative configuration file. See [06_configuration_reference.md](06_configuration_reference.md) for detailed breakdown.

---

## Systemd Services (`systemd/`)

| File | Service Name | Purpose |
|------|--------------|---------|
| `orchestrator.service` | orchestrator | Central FSM |
| `remote-interface.service` | remote-interface | HTTP API |
| `uart.service` | uart | ESP32 bridge |
| `vision.service` | vision | YOLO inference |
| `llm.service` | llm | LLM processing |
| `tts.service` | tts | Speech synthesis |
| `voice-pipeline.service` | voice-pipeline | Wakeword + STT |
| `display.service` | display | TFT face |
| `led-ring.service` | led-ring | Status LEDs |

---

## Scripts (`scripts/`)

### Build Scripts

| Script | Purpose |
|--------|---------|
| `build_llamacpp.sh` | Build llama.cpp for local LLM |
| `build_python311.sh` | Build Python 3.11 from source |
| `build_whispercpp.sh` | Build whisper.cpp for local STT |

### Model Fetching

| Script | Purpose |
|--------|---------|
| `fetch_llm_model.sh` | Download LLM model files |
| `fetch_piper_models.py` | Download Piper TTS models |
| `fetch_piper_voice.sh` | Download specific Piper voice |
| `fetch_whisper_fast_model.sh` | Download Faster Whisper models |
| `fetch_whisper_model.sh` | Download Whisper models |
| `fetch_yolo_onnx.sh` | Download YOLO ONNX model |
| `fetch_tinyllama.sh` | Download TinyLlama model |

### Utility Scripts

| Script | Purpose |
|--------|---------|
| `run.sh` | General run script |
| `setup_wakeword.sh` | Wakeword model setup |
| `recreate_venvs.sh` | Recreate virtual environments |
| `verify_implementation.sh` | Implementation verification |

### Test Scripts

| Script | Purpose |
|--------|---------|
| `test_uart_nav.py` | UART navigation testing |
| `test_ipc_integration.py` | IPC integration testing |
| `test_wakeword_*.py` | Wakeword testing variants |

---

## Models (`models/`)

| Directory | Contents |
|-----------|----------|
| `models/wakeword/` | Porcupine wakeword models (`.ppn`, `.tflite`) |
| `models/vision/` | YOLO models (`.onnx`, `.param`, `.bin`), COCO labels |
| `models/whisper/` | Whisper models for local STT |
| `models/piper/` | Piper TTS voice models |

---

## Platform Mapping

### What Runs Where

| Component | Developer PC | Raspberry Pi | ESP32 |
|-----------|--------------|--------------|-------|
| `src/` Python modules | Development only | **Runtime** | — |
| `mobile_app/` | Build only | — | — |
| `src/uart/esp-code.ino` | Development | — | **Flashed** |
| `config/` | Reference | **Active** | — |
| `systemd/` | Reference | **Active** | — |
| `models/` | Reference | **Active** | — |
| `.venvs/` | — | **Active** | — |
| `.env` | — | **Active** | — |

### Virtual Environments (Pi Only)

| venv | Python | Used By |
|------|--------|---------|
| `.venvs/stte` | 3.11 | orchestrator, remote-interface, uart, voice-pipeline |
| `.venvs/llme` | 3.11 | llm.service |
| `.venvs/ttse` | 3.11 | tts.service |
| `.venvs/visn-py313` | 3.13 | vision.service, display.service, led-ring.service |
| `.venvs/core` | 3.11 | Development/testing |
| `.venvs/dise` | — | Display experiments |

---

## File Naming Conventions

| Pattern | Meaning |
|---------|---------|
| `*_runner.py` | Long-running service main module |
| `*_service.py` | Alternative service main module |
| `*_bridge.py` | Protocol translation layer |
| `*.ino` | Arduino/ESP32 firmware |
| `*.service` | Systemd unit file |
| `requirements-*.txt` | Per-venv dependencies |

---

## Ignored/Generated Content

The following are generated at runtime and not committed:

| Path | Type |
|------|------|
| `logs/` | Runtime logs |
| `__pycache__/` | Python bytecode |
| `.venvs/` | Virtual environments |
| `*.pyc` | Compiled Python |
| `captured/` | Captured images |
| `run/` | Runtime artifacts |

---

## References

| Document | Purpose |
|----------|---------|
| [05_services_reference.md](05_services_reference.md) | Detailed service documentation |
| [06_configuration_reference.md](06_configuration_reference.md) | Configuration breakdown |
| [08_embedded_esp32_layer.md](08_embedded_esp32_layer.md) | ESP32 firmware details |
