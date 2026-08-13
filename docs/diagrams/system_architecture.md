# System Architecture Diagram

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | diagrams/system_architecture.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

This diagram shows the complete system architecture of the smart_car robot, including all hardware layers, software components, and communication paths.

---

## Full System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           ANDROID MOBILE APP                                                │
│                                                                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │
│   │  Dashboard  │    │   Vision    │    │  Telemetry  │    │    Logs     │    │  Settings   │              │
│   │    Tab      │    │    Tab      │    │    Tab      │    │    Tab      │    │    Tab      │              │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └──────┬──────┘              │
│          │                  │                  │                  │                  │                      │
│          └──────────────────┴──────────────────┴──────────────────┴──────────────────┘                      │
│                                                │                                                             │
│                                    ┌───────────┴───────────┐                                                │
│                                    │      AppViewModel     │                                                │
│                                    └───────────┬───────────┘                                                │
│                                                │                                                             │
│                                    ┌───────────┴───────────┐                                                │
│                                    │   RobotRepository     │                                                │
│                                    │   (Retrofit/OkHttp)   │                                                │
│                                    └───────────┬───────────┘                                                │
│                                                │                                                             │
└────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┘
                                                 │
                                        HTTP (Tailscale VPN)
                                      100.111.13.60:8770
                                                 │
┌────────────────────────────────────────────────┼────────────────────────────────────────────────────────────┐
│                                   RASPBERRY PI 4                                                            │
│                                                │                                                            │
│  ┌─────────────────────────────────────────────┴─────────────────────────────────────────────────────────┐  │
│  │                                    remote-interface                                                    │  │
│  │                                      Port 8770                                                         │  │
│  │                                                                                                        │  │
│  │   /health     /status     /telemetry     /intent     /stream/mjpeg                                    │  │
│  └───────────────────────────────────────────┬───────────────────────────────────────────────────────────┘  │
│                                              │                                                              │
│                                         ZeroMQ IPC                                                          │
│                                              │                                                              │
│  ┌───────────────────────────────────────────┴───────────────────────────────────────────────────────────┐  │
│  │                                       ORCHESTRATOR                                                     │  │
│  │                                    (Central FSM Hub)                                                   │  │
│  │                                                                                                        │  │
│  │   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐                                         │  │
│  │   │  IDLE   │────►│LISTENING│────►│THINKING │────►│SPEAKING │                                         │  │
│  │   └────┬────┘     └─────────┘     └─────────┘     └────┬────┘                                         │  │
│  │        │                                               │                                               │  │
│  │        └───────────────────────────────────────────────┘                                               │  │
│  │                                                                                                        │  │
│  │   SUB (bind :6010)                               PUB (bind :6011)                                     │  │
│  └───────────────────────────────────────────┬───────────────────────────────────────────────────────────┘  │
│                                              │                                                              │
│         ┌────────────────────────────────────┼────────────────────────────────────────┐                     │
│         │                                    │                                        │                     │
│         ▼                                    ▼                                        ▼                     │
│  ┌─────────────────┐              ┌─────────────────┐                      ┌─────────────────┐             │
│  │  voice-pipeline │              │      uart       │                      │     vision      │             │
│  │                 │              │  (motor_bridge) │                      │                 │             │
│  │ ┌─────────────┐ │              │                 │                      │ ┌─────────────┐ │             │
│  │ │  Porcupine  │ │              │                 │                      │ │  Picamera2  │ │             │
│  │ │  (Wakeword) │ │              │                 │                      │ └──────┬──────┘ │             │
│  │ └──────┬──────┘ │              │                 │                      │        │        │             │
│  │        │        │              │                 │                      │        ▼        │             │
│  │        ▼        │              │                 │                      │ ┌─────────────┐ │             │
│  │ ┌─────────────┐ │              │                 │                      │ │   YOLOv8    │ │             │
│  │ │  Azure STT  │ │              │                 │                      │ │  Inference  │ │             │
│  │ └─────────────┘ │              │                 │                      │ └─────────────┘ │             │
│  │                 │              │                 │                      │                 │             │
│  │ venv-stte       │              │                 │                      │ venv-visn-py313 │             │
│  └─────────────────┘              └────────┬────────┘                      └─────────────────┘             │
│                                            │                                                                │
│  ┌─────────────────┐              ┌─────────────────┐                      ┌─────────────────┐             │
│  │       llm       │              │     display     │                      │    led-ring     │             │
│  │                 │              │                 │                      │                 │             │
│  │ ┌─────────────┐ │              │ ┌─────────────┐ │                      │ ┌─────────────┐ │             │
│  │ │Azure OpenAI │ │              │ │  Waveshare  │ │                      │ │  NeoPixel   │ │             │
│  │ │   GPT-4o    │ │              │ │    OLED     │ │                      │ │   WS2812B   │ │             │
│  │ └─────────────┘ │              │ └─────────────┘ │                      │ └─────────────┘ │             │
│  │                 │              │                 │                      │                 │             │
│  │ venv-llme       │              │                 │                      │                 │             │
│  └─────────────────┘              └─────────────────┘                      └─────────────────┘             │
│                                                                                                            │
│  ┌─────────────────┐                                                                                       │
│  │       tts       │                                                                                       │
│  │                 │                                                                                       │
│  │ ┌─────────────┐ │                                                                                       │
│  │ │  Azure TTS  │ │                                                                                       │
│  │ │JennyNeural  │ │                                                                                       │
│  │ └─────────────┘ │                                                                                       │
│  │                 │                                                                                       │
│  │ venv-ttse       │                                                                                       │
│  └─────────────────┘                                                                                       │
│                                                                                                            │
└────────────────────────────────────────────────┬───────────────────────────────────────────────────────────┘
                                                 │
                                         UART (USB Serial)
                                          /dev/ttyUSB0
                                           115200 baud
                                                 │
┌────────────────────────────────────────────────┼───────────────────────────────────────────────────────────┐
│                                      ESP32 DevKit                                                          │
│                                                │                                                           │
│  ┌─────────────────────────────────────────────┴─────────────────────────────────────────────────────────┐ │
│  │                                    Command Handler                                                     │ │
│  │                                                                                                        │ │
│  │   FORWARD | BACKWARD | LEFT | RIGHT | STOP | SCAN | STATUS | RESET | CLEARBLOCK                      │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                │                    │                    │                                                  │
│                ▼                    ▼                    ▼                                                  │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐                                    │
│  │   Motor Control    │  │  Sensor Reading    │  │   Safety Logic     │                                    │
│  │                    │  │                    │  │                    │                                    │
│  │  L298N x2 Drivers  │  │  HC-SR04 x3 (S1-3) │  │  Collision Avoid   │                                    │
│  │  4x DC Motors      │  │  MQ2 Gas Sensor    │  │  Min: 20cm         │                                    │
│  │  PWM: 0-255        │  │  ADC: 0-4095       │  │  Warn: 40cm        │                                    │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘                                    │
│                                                                                                            │
└────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer Summary

| Layer | Components | Communication |
|-------|------------|---------------|
| Mobile | Android App | HTTP/REST over Tailscale |
| Application | remote-interface | HTTP ↔ ZeroMQ |
| Core | orchestrator | ZeroMQ PUB/SUB hub |
| Services | voice, vision, llm, tts, display, led | ZeroMQ to orchestrator |
| Bridge | uart (motor_bridge) | ZeroMQ ↔ UART |
| Embedded | ESP32 | UART commands |
| Hardware | Motors, Sensors | GPIO/PWM |

---

## Communication Protocols

| Path | Protocol | Format |
|------|----------|--------|
| App → Pi | HTTP/REST | JSON |
| Pi → App | HTTP/REST | JSON, MJPEG |
| Service ↔ Orchestrator | ZeroMQ PUB/SUB | JSON with topic prefix |
| Pi → ESP32 | UART | Plain text commands |
| ESP32 → Pi | UART | Comma-separated data |

---

## Color Legend (For Reference)

When implementing visual diagrams:

| Color | Meaning |
|-------|---------|
| Blue | IDLE state |
| Green | LISTENING state |
| Yellow | THINKING state |
| Purple | SPEAKING state |
| Red | ERROR state |

---

## References

| Document | Purpose |
|----------|---------|
| [03_runtime_architecture.md](../03_runtime_architecture.md) | Detailed runtime info |
| [05_services_reference.md](../05_services_reference.md) | Service specifications |
