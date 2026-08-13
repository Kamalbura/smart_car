---
name: verify_ipc_integrity
description: specific skill to check ZMQ sockets and message flow integrity across subsystems.
---

# Verify IPC Integrity

This skill ensures the nervous system of the smart_car (ZMQ IPC) is functioning correctly.

## When to use
- At system boot/initialization.
- When an agent reports "timeout" or "no response".
- Before running complex cross-agent workflows.

## Step-by-Step Instructions
1. **Locate IPC script**: Use `src/core/ipc.py` or `tools/test_ipc_integration.py` as reference.
2. **Run Diagnostic**:
   - Execute the test script:
     ```bash
     python3 tools/test_ipc_integration.py
     ```
   - OR manually check socket files:
     ```bash
     ls -l /tmp/zmq*
     ```
3. **Analyze Output**:
   - Look for "PASS" or "CONNECTED".
   - Identify which topic/socket failed (e.g., "camera_frames" vs "voice_commands").

## Verification Checklist
- [ ] All ZMQ endpoints in /tmp/ exist.
- [ ] Test script returns 0.
- [ ] Subsystems confirm receipt of "ping" if applicable.

## Rules & Constraints
- Do NOT assume IPC is broken just because one message failed. Check the broker first.
- Ensure the virtual environment (`core`) is active before running Python scripts.
