---
name: run_integration_suite
description: Execute end-to-end tests.
---

# Run Integration Suite

The final exam for the car.

## When to use
- Before declaring a feature "Done".
- Phase 7 (Reporting).

## Step-by-Step Instructions
1. **Prepare Environment**: Ensure all services are up.
2. **Execute**:
   ```bash
   ./run_e2e_test.sh
   ```
   or
   ```bash
   python3 tools/e2e_voice_test.py
   ```
3. **Record Results**:
   - Pass/Fail status.
   - Logs of the test run.

## Verification Checklist
- [ ] Test harness ran to completion.
- [ ] Zero critical failures.

## Rules & Constraints
- Real-world tests (mic/speaker) require a quiet room.
