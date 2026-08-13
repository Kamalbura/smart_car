---
name: verify_stt_engine
description: Test the Speech-to-Text engine (Faster-Whisper).
---

# Verify STT Engine

Ensures the ears of the car are working.

## When to use
- System start.
- When commands are ignored.

## Step-by-Step Instructions
1. **Activate Environment**: `stte`.
2. **Run Test**:
   - Use `tools/e2e_audio_wakeword_stt.sh` or a focused python script.
   - Example:
     ```bash
     python3 src/stt/faster_whisper_runner.py --test-file resources/mic_test5.wav
     ```
3. **Analyze**:
   - Check load time (should be < 5s on Pi 5).
   - Check transcription accuracy (should match "turn on the lights" etc).

## Verification Checklist
- [ ] Model loads without OOM.
- [ ] Transcription matches expected text.
- [ ] Latency is within acceptable limits.

## Rules & Constraints
- Ensure `stte` venv is active.
- Do not run heavy STT while LLM is generating if RAM is tight.
