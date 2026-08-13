# IPC Bus Flow Diagram

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | diagrams/ipc_bus_flow.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

This diagram shows the dual-bus ZeroMQ PUB/SUB architecture and topic flow between all services.

---

## Dual Bus Architecture

```
                                    UPSTREAM BUS (Port 6010)
                                    Module → Orchestrator
                                    
    ┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
    │                                         SUB (bind)                                              │
    │                                                                                                 │
    │                                      ┌─────────────┐                                           │
    │                                      │             │                                           │
    │                                      │             │                                           │
    │         ┌────────────────────────────┤ ORCHESTRATOR├────────────────────────────┐              │
    │         │                            │             │                            │              │
    │         │                            │             │                            │              │
    │         │                            └─────────────┘                            │              │
    │                                      PUB (bind)                                                │
    └─────────────────────────────────────────────────────────────────────────────────────────────────┘
                                    
                                    DOWNSTREAM BUS (Port 6011)
                                    Orchestrator → Modules
```

---

## Complete Topic Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                                          │
│                                           UPSTREAM (6010)                                                │
│                                         ─────────────────►                                               │
│                                                                                                          │
│  ┌─────────────────┐                                                           ┌─────────────────┐       │
│  │ voice-pipeline  │──────── ww.detected ──────────────────────────────────────►│                 │       │
│  │                 │──────── stt.transcription ────────────────────────────────►│                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │      llm        │──────── llm.response ─────────────────────────────────────►│                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │      tts        │──────── tts.speak (done) ─────────────────────────────────►│  ORCHESTRATOR   │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │     vision      │──────── visn.object ──────────────────────────────────────►│                 │       │
│  │                 │──────── visn.frame ───────────────────────────────────────►│                 │       │
│  │                 │──────── visn.capture ─────────────────────────────────────►│                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │      uart       │──────── esp32.raw ────────────────────────────────────────►│                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │remote-interface │──────── remote.intent ────────────────────────────────────►│                 │       │
│  │                 │──────── remote.session ───────────────────────────────────►│                 │       │
│  └─────────────────┘                                                           └─────────────────┘       │
│                                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘


┌──────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                                          │
│                                          DOWNSTREAM (6011)                                               │
│                                        ◄─────────────────                                                │
│                                                                                                          │
│  ┌─────────────────┐                                                           ┌─────────────────┐       │
│  │                 │◄──────── llm.request ──────────────────────────────────────│                 │       │
│  │      llm        │                                                           │                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │                 │◄──────── tts.speak ────────────────────────────────────────│                 │       │
│  │      tts        │                                                           │                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │  ORCHESTRATOR   │       │
│  │                 │◄──────── nav.command ──────────────────────────────────────│                 │       │
│  │      uart       │                                                           │                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │                 │◄──────── cmd.listen.start ─────────────────────────────────│                 │       │
│  │ voice-pipeline  │◄──────── cmd.listen.stop ──────────────────────────────────│                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │                 │◄──────── cmd.pause.vision ─────────────────────────────────│                 │       │
│  │     vision      │◄──────── cmd.vision.mode ──────────────────────────────────│                 │       │
│  │                 │◄──────── cmd.visn.capture ─────────────────────────────────│                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │                 │◄──────── display.state ────────────────────────────────────│                 │       │
│  │     display     │◄──────── display.text ─────────────────────────────────────│                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │                 │◄──────── display.state ────────────────────────────────────│                 │       │
│  │    led-ring     │                                                           │                 │       │
│  └─────────────────┘                                                           │                 │       │
│                                                                                │                 │       │
│  ┌─────────────────┐                                                           │                 │       │
│  │                 │◄──────── display.state ────────────────────────────────────│                 │       │
│  │remote-interface │◄──────── visn.* ───────────────────────────────────────────│                 │       │
│  │                 │◄──────── esp32.raw ────────────────────────────────────────│                 │       │
│  │                 │◄──────── remote.event ─────────────────────────────────────│                 │       │
│  └─────────────────┘                                                           └─────────────────┘       │
│                                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Topic Registry

### Upstream Topics (to Orchestrator)

| Topic | Publisher | Payload Summary |
|-------|-----------|-----------------|
| `ww.detected` | voice-pipeline | `{keyword, timestamp}` |
| `stt.transcription` | voice-pipeline | `{text, confidence, language}` |
| `llm.response` | llm | `{json: {speak, direction}}` |
| `tts.speak` | tts | `{done: true}` |
| `visn.object` | vision | `{label, confidence, bbox}` |
| `visn.frame` | vision | Binary JPEG |
| `visn.capture` | vision | `{frame, ts}` |
| `esp32.raw` | uart | `{s1, s2, s3, mq2, obstacle, ...}` |
| `remote.intent` | remote-interface | `{intent, extras}` |
| `remote.session` | remote-interface | `{active, last_touch}` |

### Downstream Topics (from Orchestrator)

| Topic | Subscriber(s) | Payload Summary |
|-------|---------------|-----------------|
| `llm.request` | llm | `{text, direction, world_context}` |
| `tts.speak` | tts | `{text}` |
| `nav.command` | uart | `{direction}` |
| `cmd.listen.start` | voice-pipeline | `{}` |
| `cmd.listen.stop` | voice-pipeline | `{}` |
| `cmd.pause.vision` | vision | `{paused}` |
| `cmd.vision.mode` | vision | `{mode}` |
| `cmd.visn.capture` | vision | `{}` |
| `display.state` | display, led-ring, remote-interface | `{state, phase}` |
| `display.text` | display, remote-interface | `{text}` |
| `remote.event` | remote-interface | `{event, data}` |

---

## Connection Patterns

### Bind vs Connect

```
ORCHESTRATOR
    │
    ├── SUB.bind(tcp://127.0.0.1:6010)   ◄── All publishers connect here
    │
    └── PUB.bind(tcp://127.0.0.1:6011)   ──► All subscribers connect here


ALL OTHER SERVICES
    │
    ├── PUB.connect(tcp://127.0.0.1:6010)  ──► Upstream to orchestrator
    │
    └── SUB.connect(tcp://127.0.0.1:6011)  ◄── Downstream from orchestrator
```

---

## Message Flow Example

### Voice Command: "Move forward"

```
1. voice-pipeline ──ww.detected──────────► orchestrator
2. orchestrator ───cmd.listen.start──────► voice-pipeline
3. voice-pipeline ──stt.transcription────► orchestrator
4. orchestrator ───llm.request───────────► llm
5. llm ────────────llm.response──────────► orchestrator
6. orchestrator ───tts.speak─────────────► tts
7. orchestrator ───nav.command───────────► uart
8. orchestrator ───display.state─────────► display, led-ring
9. tts ────────────tts.speak (done)──────► orchestrator
```

---

## References

| Document | Purpose |
|----------|---------|
| [04_ipc_and_data_flow.md](../04_ipc_and_data_flow.md) | Full IPC documentation |
| [05_services_reference.md](../05_services_reference.md) | Service details |
