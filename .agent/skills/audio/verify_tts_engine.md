---
name: verify_tts_engine
description: Test the Text-to-Speech engine (Piper/Azure).
---

# Verify TTS Engine

Ensures the voice of the car is working.

## When to use
- System start.
- When the car is silent.

## Step-by-Step Instructions
1. **Activate Environment**: `ttse`.
2. **Run Test**:
   - Use `tools/test_tts_direct.py`.
   - Command:
     ```bash
     python3 tools/test_tts_direct.py "Hello world, systems online."
     ```
3. **Listen/Verify**:
   - If on Pi: Check audio output.
   - If headless: Check generated `.wav` file size > 0.

## Verification Checklist
- [ ] Audio file generated.
- [ ] No ALSA/PulseAudio errors in log.

## Rules & Constraints
- Respect the "busy" flag; do not interrupt ongoing speech unless urgent.
