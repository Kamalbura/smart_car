# Known Unknowns

## Document Information

| Attribute | Value |
|-----------|-------|
| Document | 12_known_unknowns.md |
| Version | 1.0 |
| Last Updated | 2026-02-01 |

---

## Overview

This document explicitly catalogs facts that could not be verified during the analysis, areas of uncertainty, and items requiring further investigation. This transparency is essential for accurate documentation.

---

## Categories

| Category | Description |
|----------|-------------|
| 🔴 **Unverifiable** | Cannot be determined without additional access |
| 🟡 **Inferred** | Deduced from context but not directly observed |
| 🟢 **Verified** | Directly observed during analysis |

---

## ESP32 Firmware

### Unknown: Exact Firmware Source Code

| Aspect | Status |
|--------|--------|
| Source file location | 🔴 Not found in repository |
| Arduino sketch name | 🔴 Unknown |
| Build configuration | 🔴 Unknown |
| Flash procedure | 🔴 Not documented |

**What we know**:
- ESP32 responds to UART commands
- Sensor data format observed in logs
- Motor control works as expected

**What we don't know**:
- Complete command set
- All response codes
- Internal state machine
- Calibration values

### Unknown: Pin Mapping Verification

| Aspect | Status |
|--------|--------|
| Motor pins | 🟡 Inferred from common L298N usage |
| Sensor pins | 🟡 Inferred from standard HC-SR04 setup |
| Actual GPIO assignments | 🔴 Not verified |

---

## Hardware Configuration

### Unknown: Exact Robot Hardware

| Aspect | Status |
|--------|--------|
| Chassis model | 🔴 Unknown |
| Motor specifications | 🔴 Unknown |
| Battery capacity | 🔴 Unknown |
| Wheel diameter | 🔴 Unknown |

### Unknown: Camera Model

| Aspect | Status |
|--------|--------|
| Pi Camera version | 🟡 Assumed v2 (common) |
| Actual resolution | 🟡 Configured as 640x480 |
| Physical mounting | 🔴 Unknown |

### Unknown: Audio Hardware

| Aspect | Status |
|--------|--------|
| Microphone model | 🔴 Unknown |
| Speaker model | 🔴 Unknown |
| ALSA device names | 🔴 Not queried |

---

## Configuration Values

### Unknown: Actual Production Config

| Aspect | Status |
|--------|--------|
| Wakeword sensitivity | 🟢 Verified: 0.5 |
| LLM temperature | 🟢 Verified: 0.7 |
| Vision confidence | 🟢 Verified: 0.5 |
| Collision distances | 🟡 Assumed 20/40cm |

### Unknown: Environment Variables

| Variable | Status |
|----------|--------|
| AZURE_SPEECH_KEY | 🔴 Not exposed (security) |
| AZURE_OPENAI_API_KEY | 🔴 Not exposed (security) |
| PICOVOICE_ACCESS_KEY | 🔴 Not exposed (security) |

---

## Code Divergence

### Unknown: Which Version is Authoritative

| File | PC | Pi | Authoritative |
|------|----|----|---------------|
| orchestrator.py | Modified | Modified (+580/-418) | 🔴 Unknown |
| remote_interface.py | Modified | Modified (+503/-403) | 🔴 Unknown |
| motor_bridge.py | Modified | Modified (+615/-670) | 🔴 Unknown |

**Question**: Which version represents the intended production code?

### Unknown: Uncommitted Changes Purpose

The Pi has substantial uncommitted changes. We observed:
- More lines added than PC
- Changes span multiple files
- No commit messages to explain purpose

**Possible reasons**:
- Active development on Pi
- Debug modifications
- Feature in progress
- Forgotten commits

---

## Runtime Behavior

### Unknown: Full Error Handling

| Scenario | Known Behavior |
|----------|----------------|
| STT timeout | 🟡 Returns to IDLE (inferred) |
| LLM API error | 🔴 Unknown recovery |
| ESP32 disconnect | 🔴 Unknown behavior |
| Camera failure | 🔴 Unknown handling |

### Unknown: Concurrent Operation

| Scenario | Status |
|----------|--------|
| Multiple mobile clients | 🔴 Behavior unknown |
| Voice + mobile simultaneous | 🔴 Priority unknown |
| Service restart during operation | 🔴 State recovery unknown |

---

## System Prompt

### Unknown: Full LLM System Prompt

The LLM system prompt was not fully extracted. We know:
- It defines robot persona
- It specifies available actions
- It requires JSON response format

We don't know:
- Complete text
- Safety constraints
- Edge case handling
- Persona details

---

## Mobile App

### Unknown: Complete Feature Set

| Feature | Status |
|---------|--------|
| 5 tabs observed | 🟢 Verified |
| All intents documented | 🟡 Main intents known |
| Error handling | 🟡 Basic handling observed |
| Offline mode | 🔴 Behavior unknown |

### Unknown: Build and Release

| Aspect | Status |
|--------|--------|
| Package name | 🟢 com.example.smartcar |
| Signed APK | 🔴 Unknown |
| Play Store status | 🔴 Unknown |
| Target devices | 🔴 Unknown |

---

## Logging and Telemetry

### Unknown: Log Retention

| Aspect | Status |
|--------|--------|
| Max file size | 🟢 10MB configured |
| Backup count | 🟢 5 files |
| Total retention period | 🔴 Depends on activity |

### Unknown: Remote Logging

| Aspect | Status |
|--------|--------|
| Cloud logging | 🔴 Not observed |
| Crash reporting | 🔴 Not observed |
| Analytics | 🔴 Not observed |

---

## Security

### Unknown: API Authentication

| Aspect | Status |
|--------|--------|
| HTTP authentication | 🔴 None observed |
| Token mechanism | 🔴 Not present |
| Rate limiting | 🔴 Not observed |

### Unknown: Network Exposure

| Port | Local | VPN | Internet |
|------|-------|-----|----------|
| 8770 | Yes | Yes (Tailscale) | 🔴 Unknown |
| 6010/6011 | Localhost only | N/A | N/A |

---

## Performance

### Unknown: Resource Limits

| Metric | Status |
|--------|--------|
| CPU usage per service | 🔴 Not measured |
| Memory usage per service | 🔴 Not measured |
| GPU usage (vision) | 🔴 Not measured |
| Latency benchmarks | 🔴 Not measured |

### Unknown: Thermal Behavior

| Aspect | Status |
|--------|--------|
| Temperature under load | 🔴 Not measured |
| Throttling behavior | 🔴 Unknown |
| Cooling solution | 🔴 Unknown |

---

## Future Development

### Unknown: Roadmap

| Aspect | Status |
|--------|--------|
| Planned features | 🔴 Not documented |
| Known issues list | 🔴 Not found |
| Version history | 🔴 Not tracked |

---

## Items Requiring Investigation

### High Priority

1. **Resolve code divergence**: Determine authoritative version of modified files
2. **Document ESP32 firmware**: Locate or recreate firmware source
3. **Verify pin mappings**: Confirm actual GPIO assignments
4. **Complete LLM system prompt**: Extract and document full prompt

### Medium Priority

5. **Test error scenarios**: Document recovery behavior
6. **Measure performance**: CPU, memory, latency metrics
7. **Document concurrent access**: Multiple client behavior
8. **Security audit**: API authentication, network exposure

### Low Priority

9. **Hardware inventory**: Complete physical specifications
10. **Build documentation**: APK signing, release process
11. **Logging strategy**: Long-term retention, cloud options
12. **Version history**: Create changelog

---

## How to Resolve

### For Code Divergence

```bash
# On Pi
cd /home/pi/smart_car
git diff HEAD > /tmp/pi_changes.patch

# Copy to PC and analyze
scp pi@100.111.13.60:/tmp/pi_changes.patch .
```

### For ESP32 Firmware

1. Check if firmware exists outside repository
2. Use `minicom` or `screen` to explore command set
3. Document all observed responses

### For Performance Metrics

```bash
# On Pi during operation
htop  # CPU/Memory
vcgencmd measure_temp  # Temperature
```

---

## Documentation Confidence

| Document | Confidence | Reason |
|----------|------------|--------|
| 01_project_overview.md | High | Direct observation |
| 02_repository_structure.md | High | File listing verified |
| 03_runtime_architecture.md | High | SSH inspection |
| 04_ipc_and_data_flow.md | High | Code analysis |
| 05_services_reference.md | Medium | Some inference |
| 06_configuration_reference.md | High | Config file read |
| 07_mobile_app_integration.md | High | Code analysis |
| 08_embedded_esp32_layer.md | Low | Mostly inferred |
| 09_deployment_and_operations.md | Medium | Partial verification |
| 10_git_and_sync_model.md | High | Git status observed |
| 11_execution_flows.md | Medium | Logical inference |
| 12_known_unknowns.md | N/A | Meta document |

---

## Version Control

This document should be updated when:
- An unknown becomes known
- New unknowns are discovered
- Confidence levels change

**Last Review**: 2026-02-01
**Next Review**: Upon significant discovery

---

## References

| Document | Purpose |
|----------|---------|
| All documentation | Cross-reference for gaps |
