# Project Overview

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | 01_project_overview.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## What is Smart Car?

**Smart Car** is a voice-driven, sensor-aware mobile robot system designed for operator-grade supervision and control. It combines:

- **Voice interaction** via wakeword detection and speech recognition
- **Computer vision** using YOLO object detection
- **Motor control** through an ESP32 microcontroller
- **Remote supervision** via a private Android application
- **AI-powered responses** using cloud LLM services

The system operates on a Raspberry Pi 4 as the central orchestrator, communicating with an ESP32 for motor and sensor control, and exposing a private HTTP API for mobile app integration.

---

## System Identity

| Property | Value |
|----------|-------|
| Project Name | smart_car |
| Primary Language | Python 3.11 / 3.13 |
| Mobile App | Kotlin (Android) |
| Embedded Firmware | C++ (Arduino/ESP32) |
| Runtime Platform | Raspberry Pi 4 (Debian/Raspbian) |
| VPN | Tailscale |
| Pi Tailscale IP | 100.111.13.60 |

---

## Core Capabilities

### 1. Voice Interaction

The robot responds to voice commands through a multi-stage pipeline:

| Stage | Technology | Evidence |
|-------|------------|----------|
| Wakeword Detection | Picovoice Porcupine | `config/system.yaml → wakeword.engine: porcupine` |
| Trigger Phrase | "Hey Robo" | `config/system.yaml → wakeword.keywords: ["hey robo"]` |
| Speech-to-Text | Azure Speech / Faster Whisper | `config/system.yaml → stt.engine: azure_speech` |
| Language Model | Azure OpenAI | `config/system.yaml → llm.engine: azure_openai` |
| Text-to-Speech | Azure TTS | `systemd/tts.service → src.tts.azure_tts_runner` |

**Source**: `src/audio/voice_service.py`, `src/llm/azure_openai_runner.py`, `src/tts/azure_tts_runner.py`

### 2. Computer Vision

The robot performs real-time object detection:

| Feature | Implementation | Evidence |
|---------|----------------|----------|
| Model | YOLO11n | `config/system.yaml → vision.model_path_onnx` |
| Backend | ONNX Runtime | `config/system.yaml → vision.backend: onnx` |
| Camera | Picamera2 or OpenCV | `src/vision/vision_runner.py` |
| Streaming | MJPEG over HTTP | `/stream/mjpeg` endpoint |
| Inference Rate | Target 15 FPS | `config/system.yaml → vision.target_fps: 15` |

**Source**: `src/vision/vision_runner.py`, `src/vision/detector.py`

### 3. Motor Control

The robot executes physical movement commands:

| Command | UART Token | Evidence |
|---------|------------|----------|
| Forward | `FORWARD` | `config/system.yaml → nav.commands.forward` |
| Backward | `BACKWARD` | `config/system.yaml → nav.commands.backward` |
| Left | `LEFT` | `config/system.yaml → nav.commands.left` |
| Right | `RIGHT` | `config/system.yaml → nav.commands.right` |
| Stop | `STOP` | `config/system.yaml → nav.commands.stop` |
| Scan | `SCAN` | `config/system.yaml → nav.commands.scan` |

**Source**: `src/uart/motor_bridge.py`, `src/uart/esp-code.ino`

### 4. Remote Supervision

An Android application provides operator control:

| Feature | Implementation | Evidence |
|---------|----------------|----------|
| Connection | HTTP over Tailscale VPN | `config/system.yaml → remote_interface` |
| Port | 8770 | `config/system.yaml → remote_interface.port: 8770` |
| Telemetry | Polling `/status` and `/telemetry` | `RobotApi.kt` |
| Commands | POST `/intent` | `RobotApi.kt → postIntent()` |
| Video | MJPEG stream | `/stream/mjpeg` |

**Source**: `src/remote/remote_interface.py`, `mobile_app/`

### 5. Collision Avoidance

The ESP32 provides hardware-level safety:

| Feature | Threshold | Evidence |
|---------|-----------|----------|
| Emergency Stop Distance | 10 cm | `esp-code.ino → STOP_DISTANCE_CM` |
| Warning Zone | 20 cm | `esp-code.ino → WARNING_DISTANCE_CM` |
| Sensors | 3× Ultrasonic (HC-SR04) | `esp-code.ino → S1, S2, S3` |
| Response | Block forward motion | `esp-code.ino → handleCommand()` |

**Source**: `src/uart/esp-code.ino`

---

## Orchestrator State Machine

The system operates through a central finite state machine:

| Phase | Description | LED Color |
|-------|-------------|-----------|
| IDLE | Waiting for wakeword | Dim cyan breathing |
| LISTENING | Capturing user speech | Bright blue sweep |
| THINKING | LLM processing | Pink pulse |
| SPEAKING | Playing TTS audio | Dark green chase |
| ERROR | System error | Red blink |

**Source**: `src/core/orchestrator.py` lines 1-12 (docstring), `Phase` enum

### State Transitions

| Current State | Event | Next State |
|---------------|-------|------------|
| IDLE | wakeword | LISTENING |
| IDLE | manual_trigger | LISTENING |
| IDLE | manual_text | THINKING |
| LISTENING | stt_valid | THINKING |
| LISTENING | stt_invalid | IDLE |
| LISTENING | stt_timeout | IDLE |
| THINKING | llm_with_speech | SPEAKING |
| THINKING | llm_no_speech | IDLE |
| SPEAKING | tts_done | IDLE |
| Any | health_error | ERROR |
| ERROR | health_ok | IDLE |

**Source**: `src/core/orchestrator.py → Orchestrator.TRANSITIONS`

---

## What Smart Car is NOT

The following are explicit **non-goals** and **out-of-scope** items:

| Non-Goal | Explanation |
|----------|-------------|
| Multi-user system | Single operator only; no user management or authentication |
| Cloud backend | Direct robot-to-app communication; no intermediary servers |
| Public network access | Tailscale VPN only; no public internet exposure |
| Autonomous navigation | Operator-driven; no SLAM, path planning, or autonomous waypoints |
| Commercial product | Engineering/operator tool; not consumer-facing |
| Multi-robot coordination | Single robot instance only |

---

## Technology Stack Summary

### Raspberry Pi (Python)

| Layer | Technology |
|-------|------------|
| Runtime | Python 3.11 (stte, llme, ttse), Python 3.13 (visn) |
| IPC | ZeroMQ (PUB/SUB) |
| HTTP | Python http.server (ThreadingHTTPServer) |
| Vision | OpenCV, Picamera2, ONNX Runtime |
| Audio | PyAudio, scipy (resampling) |
| Wakeword | Picovoice Porcupine |
| STT | Azure Cognitive Services / Faster Whisper |
| LLM | Azure OpenAI (openai SDK) |
| TTS | Azure Cognitive Services Speech |

### Android App (Kotlin)

| Layer | Technology |
|-------|------------|
| UI Framework | Jetpack Compose |
| Architecture | MVVM |
| Networking | Retrofit, OkHttp |
| JSON | Moshi |
| Video | MJPEG custom decoder |

### ESP32 (C++)

| Layer | Technology |
|-------|------------|
| Framework | Arduino |
| Communication | HardwareSerial (UART) |
| Motor Driver | L298N (digital GPIO) |
| Sensors | HC-SR04 Ultrasonic, MQ2 Gas |
| Servo | ESP32Servo library |

---

## System Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                        TAILSCALE VPN                            │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐ │
│  │ Android App │◄──►│  Raspberry Pi   │◄──►│ Developer PC    │ │
│  │ (Operator)  │    │  (Robot Brain)  │    │ (Development)   │ │
│  └─────────────┘    └────────┬────────┘    └─────────────────┘ │
└──────────────────────────────┼──────────────────────────────────┘
                               │ UART
                    ┌──────────▼──────────┐
                    │       ESP32         │
                    │  (Motors/Sensors)   │
                    └─────────────────────┘
```

---

## Key Design Decisions

### 1. Centralized Orchestrator Pattern

All system coordination flows through a single orchestrator service. This provides:
- Single source of truth for system state
- Clear event ordering
- Simplified debugging

**Trade-off**: Single point of failure for coordination logic.

### 2. Dual ZMQ Bus Architecture

Separation of upstream (events) and downstream (commands) buses enables:
- Clear data flow direction
- Simplified subscription patterns
- Reduced coupling between producers and consumers

**Trade-off**: Requires understanding of which bus to use for each message type.

### 3. HTTP for Remote Interface

Using HTTP rather than ZMQ for mobile app communication provides:
- Standard protocol for mobile frameworks
- Easier debugging with standard tools
- Firewall-friendly (single port)

**Trade-off**: Polling-based rather than push; higher latency than direct IPC.

### 4. ESP32 as Safety Layer

Collision avoidance runs on ESP32, not Raspberry Pi:
- Hardware-level protection independent of Pi state
- Lower latency for safety-critical decisions
- Continues working even if Pi software crashes

**Trade-off**: Duplicates some safety logic between Pi and ESP32.

---

## References

| Document | Purpose |
|----------|---------|
| [03_runtime_architecture.md](03_runtime_architecture.md) | Detailed process model |
| [05_services_reference.md](05_services_reference.md) | Service-by-service breakdown |
| [11_execution_flows.md](11_execution_flows.md) | End-to-end sequence diagrams |
