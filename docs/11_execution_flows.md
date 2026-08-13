# Execution Flows

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | 11_execution_flows.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

This document provides detailed sequence diagrams for the major execution flows in the smart_car system. Each flow is documented with Mermaid diagrams showing the complete data path from trigger to completion.

---

## 1. Voice Command Flow

### Description

User speaks a wake word, gives a voice command, and the robot responds with both speech and motion.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant M as Microphone
    participant VP as voice-pipeline
    participant O as orchestrator
    participant LLM as llm
    participant TTS as tts
    participant UART as uart
    participant ESP as ESP32
    participant D as display
    participant L as led-ring

    Note over O: Phase: IDLE
    L->>L: Blue slow pulse

    U->>M: "Hey Robo"
    M->>VP: Audio frames
    VP->>VP: Porcupine detect
    VP->>O: ww.detected (6010)
    
    Note over O: Phase: LISTENING
    O->>D: display.state: "listening"
    O->>L: display.state: "listening"
    L->>L: Green fast pulse
    
    U->>M: "Move forward"
    M->>VP: Speech audio
    VP->>VP: Azure STT
    VP->>O: stt.transcription (6010)
    Note right of VP: {"text": "move forward", "confidence": 0.95}
    
    Note over O: Phase: THINKING
    O->>D: display.state: "thinking"
    O->>L: display.state: "thinking"
    L->>L: Yellow spin
    
    O->>LLM: llm.request (6011)
    Note right of O: {"text": "move forward", "direction": "stopped", "world_context": {...}}
    
    LLM->>LLM: Azure OpenAI GPT-4o
    LLM->>O: llm.response (6010)
    Note right of LLM: {"speak": "Moving forward now", "direction": "forward"}
    
    Note over O: Phase: SPEAKING
    O->>D: display.state: "speaking"
    O->>L: display.state: "speaking"
    L->>L: Purple solid
    
    par TTS and Motor
        O->>TTS: tts.speak (6011)
        Note right of O: {"text": "Moving forward now"}
        O->>UART: nav.command (6011)
        Note right of O: {"direction": "forward"}
    end
    
    TTS->>TTS: Azure TTS synthesis
    TTS->>U: "Moving forward now" (audio)
    TTS->>O: tts.speak (6010)
    Note right of TTS: {"done": true}
    
    UART->>ESP: "FORWARD\n" (serial)
    ESP->>ESP: Motor control
    ESP->>UART: "ACK:FORWARD:OK\n"
    ESP->>UART: "DATA:S1:50,S2:45,..."
    UART->>O: esp32.raw (6010)
    
    Note over O: Phase: IDLE
    O->>D: display.state: "idle"
    O->>L: display.state: "idle"
    L->>L: Blue slow pulse
```

### Timing Estimates

| Step | Duration |
|------|----------|
| Wakeword detection | 100ms |
| STT recognition | 1-3s |
| LLM inference | 1-3s |
| TTS synthesis | 500ms-1s |
| Motor start | 50ms |
| **Total** | 3-8s |

---

## 2. Mobile App Control Flow

### Description

User taps a direction button in the Android app, which sends an intent to the Pi to control the robot.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant A as Android App
    participant VM as ViewModel
    participant R as Repository
    participant RI as remote-interface
    participant O as orchestrator
    participant UART as uart
    participant ESP as ESP32

    U->>A: Tap Forward button
    A->>VM: sendIntent("start")
    VM->>R: POST /intent
    
    R->>RI: HTTP POST /intent
    Note right of R: {"intent": "start"}
    
    RI->>RI: Validate intent
    RI->>RI: Touch session
    RI->>O: remote.intent (6010)
    Note right of RI: {"intent": "start", "source": "remote_app"}
    
    RI->>R: HTTP 202 Accepted
    R->>VM: Success
    VM->>A: Update UI
    
    O->>O: Map intent to direction
    Note over O: "start" → "forward"
    
    O->>UART: nav.command (6011)
    Note right of O: {"direction": "forward"}
    
    UART->>ESP: "FORWARD\n" (serial)
    ESP->>ESP: Motor control
    ESP->>UART: "ACK:FORWARD:OK\n"
    
    loop Every 100ms
        ESP->>UART: "DATA:S1:50,S2:45,..."
        UART->>O: esp32.raw (6010)
        O->>RI: (telemetry update)
    end
    
    loop Every 1s
        A->>RI: GET /status
        RI->>A: Telemetry JSON
        A->>U: Update dashboard
    end
```

### Intent to Direction Mapping

| Intent | Direction |
|--------|-----------|
| start | forward |
| stop | stopped |
| left | left |
| right | right |

---

## 3. Vision Detection Flow

### Description

Camera captures frames, vision service runs inference, and detections are published for other services.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant C as Camera
    participant V as vision
    participant O as orchestrator
    participant RI as remote-interface
    participant A as Android App

    loop Continuous at 10 FPS
        C->>V: RGB frame (640x480)
        V->>V: YOLO inference
        
        alt Object detected
            V->>O: visn.object (6010)
            Note right of V: {"label": "person", "confidence": 0.87, "bbox": [...]}
            V->>V: Annotate frame
        end
        
        V->>V: Encode JPEG
        V->>RI: visn.frame (6010)
        Note right of V: Binary JPEG data
    end
    
    O->>O: Update world_context.last_detection
    RI->>RI: Update telemetry state
    RI->>RI: Push to MJPEG stream
    
    A->>RI: GET /stream/mjpeg
    RI->>A: Continuous JPEG frames
```

### Vision Modes

| Mode | Behavior |
|------|----------|
| detection | Continuous inference + annotation |
| capture | Single frame capture on demand |
| off | Camera disabled |

---

## 4. Collision Avoidance Flow

### Description

ESP32 detects obstacle and blocks forward movement. Robot stops and reports status.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant O as orchestrator
    participant UART as uart
    participant ESP as ESP32
    participant S as Ultrasonic Sensors
    participant M as Motors

    O->>UART: nav.command {"direction": "forward"}
    UART->>ESP: "FORWARD\n"
    
    ESP->>S: Measure distance
    S->>ESP: S1:15, S2:12, S3:20
    
    ESP->>ESP: Check safety
    Note over ESP: S2 < MIN_DISTANCE (20cm)
    Note over ESP: OBSTACLE = true
    
    alt Obstacle detected
        ESP->>M: Stop motors
        ESP->>UART: "ACK:FORWARD:BLOCKED:OBSTACLE\n"
    else No obstacle
        ESP->>M: Set motors forward
        ESP->>UART: "ACK:FORWARD:OK\n"
    end
    
    ESP->>UART: "DATA:S1:15,S2:12,S3:20,...,OBSTACLE:1,WARNING:1\n"
    UART->>O: esp32.raw (6010)
    Note right of UART: {"s2": 12, "obstacle": true, "is_safe": false}
    
    O->>O: Update direction state
    O->>O: (Optional) Notify user via TTS
```

### Safety Thresholds

| Zone | Distance | Action |
|------|----------|--------|
| Safe | > 40 cm | Allow movement |
| Warning | 20-40 cm | Block forward (WARNING flag) |
| Obstacle | < 20 cm | Emergency stop (OBSTACLE flag) |

---

## 5. Service Startup Flow

### Description

System boot sequence from power-on to ready state.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant SD as systemd
    participant O as orchestrator
    participant RI as remote-interface
    participant UART as uart
    participant V as vision
    participant VP as voice-pipeline
    participant LLM as llm
    participant TTS as tts
    participant D as display
    participant L as led-ring

    Note over SD: Pi boots, systemd starts
    
    SD->>O: Start orchestrator.service
    O->>O: Load config/system.yaml
    O->>O: Bind ZMQ SUB:6010
    O->>O: Bind ZMQ PUB:6011
    O->>O: Initialize FSM (IDLE)
    
    par Start remaining services
        SD->>RI: Start remote-interface
        SD->>UART: Start uart
        SD->>V: Start vision
        SD->>VP: Start voice-pipeline
        SD->>LLM: Start llm
        SD->>TTS: Start tts
        SD->>D: Start display
        SD->>L: Start led-ring
    end
    
    RI->>O: Connect PUB:6010, SUB:6011
    UART->>O: Connect PUB:6010, SUB:6011
    V->>O: Connect PUB:6010, SUB:6011
    VP->>O: Connect PUB:6010, SUB:6011
    LLM->>O: Connect SUB:6011
    TTS->>O: Connect SUB:6011
    D->>O: Connect SUB:6011
    L->>O: Connect SUB:6011
    
    O->>D: display.state: "idle"
    O->>L: display.state: "idle"
    L->>L: Blue slow pulse
    D->>D: Show "Ready"
    
    Note over O: System ready
    Note over RI: HTTP listening on :8770
    Note over UART: Serial connected to ESP32
    Note over VP: Listening for wakeword
```

### Boot Timeline

| Time | Event |
|------|-------|
| T+0s | Power on |
| T+20s | Linux boots |
| T+30s | Network ready |
| T+35s | orchestrator starts |
| T+40s | All services connected |
| T+45s | System ready |

---

## 6. TTS Playback Flow

### Description

Text-to-speech synthesis and audio playback.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant O as orchestrator
    participant TTS as tts
    participant Azure as Azure TTS API
    participant SDL as SDL2 Audio
    participant SP as Speaker

    O->>TTS: tts.speak (6011)
    Note right of O: {"text": "Hello, I am ready"}
    
    TTS->>TTS: Check cache
    
    alt Cache hit
        TTS->>TTS: Load cached audio
    else Cache miss
        TTS->>Azure: SSML request
        Note right of TTS: POST /cognitiveservices/v1
        Azure->>TTS: Audio stream (MP3)
        TTS->>TTS: Save to cache
    end
    
    TTS->>SDL: Open audio device
    TTS->>SDL: Queue audio buffer
    SDL->>SP: Play audio
    
    loop Until playback complete
        SDL->>TTS: Buffer consumed
    end
    
    TTS->>O: tts.speak (6010)
    Note right of TTS: {"done": true}
```

---

## 7. Session Management Flow

### Description

Mobile app session lifecycle from connection to timeout.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant A as Android App
    participant RI as remote-interface
    participant O as orchestrator

    A->>RI: GET /health
    RI->>A: {"status": "ok"}
    Note over A: Connected
    
    A->>RI: GET /status
    RI->>RI: Create session
    RI->>RI: session_active = true
    RI->>RI: last_session_touch = now()
    RI->>A: Telemetry JSON
    
    loop Every 1s
        A->>RI: GET /status
        RI->>RI: Touch session
        RI->>A: Telemetry JSON
    end
    
    Note over A: App closed / network lost
    
    loop Session monitor (every 10s)
        RI->>RI: Check last_session_touch
        Note over RI: now() - last_session_touch > 300s?
    end
    
    alt Session expired
        RI->>RI: session_active = false
        RI->>O: remote.session {"active": false}
        O->>O: (Optional) Auto-stop motors
    end
```

---

## 8. Error Recovery Flow

### Description

System behavior when a component fails and recovers.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant SD as systemd
    participant S as Service (any)
    participant O as orchestrator

    S->>S: Processing...
    S->>S: Exception raised
    S->>S: Exit with error (code 1)
    
    SD->>SD: Detect service exit
    SD->>SD: Wait RestartSec (3s)
    SD->>S: Restart service
    
    S->>S: Load configuration
    S->>O: Reconnect ZMQ
    S->>S: Resume normal operation
    
    Note over S: Service recovered
```

### Systemd Configuration

```ini
Restart=always
RestartSec=3
```

---

## 9. Frame Capture Flow

### Description

Single frame capture triggered from mobile app.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant A as Android App
    participant RI as remote-interface
    participant O as orchestrator
    participant V as vision

    A->>RI: POST /intent {"intent": "capture"}
    RI->>O: remote.intent (6010)
    RI->>A: HTTP 202 Accepted
    
    O->>V: cmd.visn.capture (6011)
    
    V->>V: Capture next frame
    V->>V: Encode JPEG
    V->>O: visn.capture (6010)
    Note right of V: {"frame": <base64>, "ts": 1769931845}
    
    O->>O: Store in world_context
    
    Note over A: Next /status poll will include capture info
```

---

## 10. Gas Sensor Alert Flow

### Description

MQ2 gas sensor detects high levels and system responds.

### Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant MQ as MQ2 Sensor
    participant ESP as ESP32
    participant UART as uart
    participant O as orchestrator
    participant TTS as tts
    participant U as User

    loop Every 100ms
        ESP->>MQ: Read ADC
        MQ->>ESP: Value (0-4095)
    end
    
    MQ->>ESP: High value (> 1000)
    
    ESP->>UART: "DATA:...,MQ2:1234,...\n"
    UART->>O: esp32.raw (6010)
    Note right of UART: {"mq2": 1234}
    
    O->>O: Check gas threshold
    
    alt High gas level
        O->>TTS: tts.speak (6011)
        Note right of O: {"text": "Warning: Gas detected"}
        TTS->>U: Audio alert
    end
```

---

## Summary Table

| Flow | Trigger | Primary Path | Duration |
|------|---------|--------------|----------|
| Voice Command | Wake word | VP→O→LLM→TTS→UART | 3-8s |
| Mobile Control | Button tap | App→RI→O→UART | 200ms |
| Vision Detection | Continuous | Camera→V→O→RI | 100ms/frame |
| Collision Avoidance | Obstacle | Sensors→ESP→UART→O | 50ms |
| Startup | Boot | systemd→all services | 45s |
| TTS Playback | Command | O→TTS→Azure→Speaker | 1-2s |
| Session | App connect | App→RI polling | Ongoing |
| Error Recovery | Service crash | systemd restart | 3s |
| Frame Capture | Intent | App→RI→O→V | 200ms |
| Gas Alert | Sensor | MQ2→ESP→UART→O→TTS | 500ms |

---

## References

| Document | Purpose |
|----------|---------|
| [04_ipc_and_data_flow.md](04_ipc_and_data_flow.md) | IPC details |
| [05_services_reference.md](05_services_reference.md) | Service specs |
| [diagrams/voice_to_action_pipeline.md](diagrams/voice_to_action_pipeline.md) | Visual diagram |
