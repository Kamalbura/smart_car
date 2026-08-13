# Smart Car System Documentation

## Document Index

**Version**: 1.0  
**Generated**: February 1, 2026  
**Classification**: Internal Engineering Documentation

---

## Purpose

This documentation provides a complete, authoritative reference for the **smart_car** robotics system. It is derived from direct inspection of:

- Source code repositories
- Configuration files
- Systemd service definitions
- Runtime process observations
- Network port analysis
- Log file examination
- Git repository state

Every statement in this documentation is traceable to observed evidence. Where evidence is insufficient, uncertainties are explicitly marked.

---

## Target Audience

| Audience | Primary Use |
|----------|-------------|
| **New Engineers** | System onboarding, understanding architecture and data flows |
| **Operators** | Deployment procedures, troubleshooting, service management |
| **Auditors** | Security review, compliance verification, architecture assessment |
| **Maintainers** | Long-term system evolution, dependency tracking |

---

## Document Structure

| File | Contents |
|------|----------|
| [01_project_overview.md](01_project_overview.md) | What the system is, what it does, and explicit non-goals |
| [02_repository_structure.md](02_repository_structure.md) | Directory layout, module breakdown, platform mapping |
| [03_runtime_architecture.md](03_runtime_architecture.md) | Process model, service isolation, hardware interfaces |
| [04_ipc_and_data_flow.md](04_ipc_and_data_flow.md) | ZeroMQ buses, topic taxonomy, protocol boundaries |
| [05_services_reference.md](05_services_reference.md) | Detailed reference for each systemd service |
| [06_configuration_reference.md](06_configuration_reference.md) | system.yaml breakdown, environment variables |
| [07_mobile_app_integration.md](07_mobile_app_integration.md) | Android app architecture, API contracts |
| [08_embedded_esp32_layer.md](08_embedded_esp32_layer.md) | ESP32 firmware, UART protocol, sensor handling |
| [09_deployment_and_operations.md](09_deployment_and_operations.md) | Boot sequence, health checks, operational procedures |
| [10_git_and_sync_model.md](10_git_and_sync_model.md) | Repository synchronization between PC and Pi |
| [11_execution_flows.md](11_execution_flows.md) | End-to-end sequence diagrams for major operations |
| [12_known_unknowns.md](12_known_unknowns.md) | Explicit list of undeterminable facts |

### Diagrams

| Diagram | Contents |
|---------|----------|
| [diagrams/system_architecture.md](diagrams/system_architecture.md) | High-level system component diagram |
| [diagrams/ipc_bus_flow.md](diagrams/ipc_bus_flow.md) | ZeroMQ topic flow visualization |
| [diagrams/service_startup_sequence.md](diagrams/service_startup_sequence.md) | Boot and dependency ordering |
| [diagrams/voice_to_action_pipeline.md](diagrams/voice_to_action_pipeline.md) | Wakeword through motor execution |

---

## How to Use This Documentation

### For Onboarding

1. Start with [01_project_overview.md](01_project_overview.md) to understand system purpose
2. Read [03_runtime_architecture.md](03_runtime_architecture.md) for the execution model
3. Study [05_services_reference.md](05_services_reference.md) to understand each component
4. Review [11_execution_flows.md](11_execution_flows.md) to see how components interact

### For Operations

1. Reference [09_deployment_and_operations.md](09_deployment_and_operations.md) for procedures
2. Use [05_services_reference.md](05_services_reference.md) for service-specific details
3. Consult [06_configuration_reference.md](06_configuration_reference.md) for tuning

### For Development

1. Review [02_repository_structure.md](02_repository_structure.md) for code organization
2. Study [04_ipc_and_data_flow.md](04_ipc_and_data_flow.md) for integration points
3. Reference [07_mobile_app_integration.md](07_mobile_app_integration.md) for API contracts

---

## Documentation Conventions

### Evidence Markers

Throughout this documentation:

- **Code references** are formatted as: `src/module/file.py`
- **Configuration references** use: `config/system.yaml → section.key`
- **Service references** use: `servicename.service`
- **Runtime observations** are marked with: `[Observed]`

### Uncertainty Notation

When information cannot be verified:

> **Not determinable from current evidence.**

This indicates that the statement requires additional investigation or access.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-01 | System Analysis | Initial documentation generation |

---

## Quick Reference

### Key Network Endpoints

| Endpoint | Port | Protocol | Purpose |
|----------|------|----------|---------|
| ZMQ Upstream | 6010 | TCP | Module → Orchestrator events |
| ZMQ Downstream | 6011 | TCP | Orchestrator → Module commands |
| Remote Interface | 8770 | HTTP | Mobile app supervision API |

### Key File Locations (Raspberry Pi)

| Path | Purpose |
|------|---------|
| `/home/dev/smart_car/` | Project root |
| `/home/dev/smart_car/config/system.yaml` | Primary configuration |
| `/home/dev/smart_car/.env` | Environment secrets |
| `/home/dev/smart_car/logs/` | Runtime logs |
| `/home/dev/smart_car/.venvs/` | Python virtual environments |

### Service Quick Reference

| Service | Entry Point | Status |
|---------|-------------|--------|
| orchestrator.service | `src.core.orchestrator` | Central FSM |
| remote-interface.service | `src.remote.remote_interface` | HTTP API |
| uart.service | `src.uart.motor_bridge` | ESP32 bridge |
| vision.service | `src.vision.vision_runner` | YOLO inference |
| llm.service | `src.llm.azure_openai_runner` | LLM processing |
| tts.service | `src.tts.azure_tts_runner` | Speech synthesis |
| voice-pipeline.service | `src.audio.voice_service` | Wakeword + STT |
| display.service | `src.ui.face_fb` | TFT display |
| led-ring.service | `src.piled.led_ring_service` | Status LEDs |
