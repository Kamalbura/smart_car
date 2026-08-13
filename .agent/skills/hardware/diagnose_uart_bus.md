---
name: diagnose_uart_bus
description: Verify serial communication with ESP32/Motor Controller.
---

# Diagnose UART Bus

Ensures the nervous system (spinal cord) to motors is intact.

## When to use
- When motors do not respond.
- When telemetry is missing.

## Step-by-Step Instructions
1. **Identify Port**: Usually `/dev/ttyS0` or `/dev/serial0` on Pi.
2. **Loopback Test** (if jumpered):
   - Send bytes, expect same bytes back.
3. **Live Test**:
   ```bash
   python3 tools/uart_dump_esp32.py
   ```
   - Watch for heartbeat packets.

## Verification Checklist
- [ ] Port is accessible (permission rw).
- [ ] Baud rate matches (typically 115200).
- [ ] Valid headers received (e.g., `0xAA 0x55`).

## Rules & Constraints
- Do not flood the bus; respect the protocol timing.
