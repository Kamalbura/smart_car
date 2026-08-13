---
name: configure_audio_hardware
description: Setup microphones and speakers (ALSA/Pulse).
---

# Configure Audio Hardware

Sets the physical stage for audio processing.

## When to use
- Boot time.
- If "Input Overflow" or "No Default Device" errors occur.

## Step-by-Step Instructions
1. **List Devices**:
   ```bash
   python3 tools/list_pyaudio_devices.py
   ```
2. **Select Index**:
   - Identify the ReSpeaker / USB Mic index.
   - identifying the HDMI / Jack / USB Speaker index.
3. **Update Config**:
   - Modify `.env` or `config/audio_config.yaml` with correct indices.

## Verification Checklist
- [ ] Correct device names found.
- [ ] Recording test (`arecord -d 5 test.wav`) plays back clearly.

## Rules & Constraints
- Audio hardware on Linux is fragile; treat with care.
