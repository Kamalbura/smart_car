---
name: control_indicators
description: Manage LED Ring / Status Lights.
---

# Control Indicators

Visual feedback for the user.

## When to use
- To signal state changes (Listening, Thinking, Speaking).
- To test GPIO/SPI connection to LED driver.

## Step-by-Step Instructions
1. **Run Test Script**:
   ```bash
   sudo python3 tools/fb_color_test.py
   ```
   or
   ```bash
   sudo python3 tools/led-test.py
   ```
2. **Observe**:
   - Verify all LEDs light up.
   - Verify color correctness (Red vs Green).

## Verification Checklist
- [ ] No "SPI device not found" error.
- [ ] Visual confirmation (requires human or camera).

## Rules & Constraints
- LEDs often require root (`sudo`) if using direct SPI/GPIO memory access.
