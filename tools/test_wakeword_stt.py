#!/usr/bin/env python3
"""Test complete flow: Wakeword → Capture → STT with scipy resampling."""
import sys
import os
import time
import wave
import tempfile
import ctypes
import math
import numpy as np

# Suppress ALSA errors
try:
    ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(
        None, ctypes.c_char_p, ctypes.c_int,
        ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
    )
    def py_error_handler(filename, line, function, err, fmt):
        pass
    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    asound = ctypes.cdll.LoadLibrary("libasound.so.2")
    asound.snd_lib_error_set_handler(c_error_handler)
except Exception:
    pass

import pyaudio
from scipy import signal
import pvporcupine

# Configuration
HW_RATE = 48000
TARGET_RATE = 16000
SENSITIVITY = 0.7
SILENCE_THRESHOLD = 0.25  # RMS threshold for silence (calibrated from actual mic)
SILENCE_DURATION_MS = 800  # Stop after 0.8s of silence
MAX_CAPTURE_SECONDS = 8.0
MIN_CAPTURE_SECONDS = 0.5

print("=== COMPLETE VOICE FLOW TEST ===", flush=True)
print(f"Wakeword sensitivity: {SENSITIVITY}", flush=True)
print(f"Silence threshold: {SILENCE_THRESHOLD}", flush=True)
print(f"Resampling: {HW_RATE}Hz → {TARGET_RATE}Hz (scipy)", flush=True)
print("", flush=True)

# Load config for access key
sys.path.insert(0, "/home/dev/smart_car")
from src.core.config_loader import load_config
from pathlib import Path
cfg = load_config(Path("/home/dev/smart_car/config/system.yaml"))
ACCESS_KEY = cfg.get("wakeword", {}).get("access_key", "")
MODEL_PATH = "/home/dev/smart_car/models/wakeword/hey_robo.ppn"

# Initialize Porcupine
print("Initializing Porcupine...", flush=True)
porcupine = pvporcupine.create(
    access_key=ACCESS_KEY,
    keyword_paths=[MODEL_PATH],
    sensitivities=[SENSITIVITY],
)
FRAME_LENGTH = porcupine.frame_length
HW_CHUNK = int(FRAME_LENGTH * HW_RATE / TARGET_RATE)
print(f"Porcupine ready (frame_length={FRAME_LENGTH})", flush=True)

# Initialize faster-whisper
print("Loading faster-whisper model (tiny.en)...", flush=True)
from faster_whisper import WhisperModel
stt_model = WhisperModel(
    "tiny.en",
    device="cpu",
    compute_type="int8",
    download_root="/home/dev/smart_car/third_party/whisper-fast",
)
print("STT model ready!", flush=True)

# Initialize PyAudio
pa = pyaudio.PyAudio()

# Find USB device
found_device = None
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0 and "USB" in info["name"]:
        found_device = i
        break

if found_device is None:
    print("ERROR: No USB input device!", flush=True)
    sys.exit(1)

print(f"Audio device ready (index {found_device})", flush=True)

# Open stream
stream = pa.open(
    rate=HW_RATE,
    channels=1,
    format=pyaudio.paInt16,
    input=True,
    input_device_index=found_device,
    frames_per_buffer=HW_CHUNK,
)

def calc_rms(samples):
    """Calculate RMS amplitude (0.0 to 1.0)."""
    if len(samples) == 0:
        return 0.0
    energy = np.mean(samples.astype(np.float32) ** 2)
    return min(1.0, math.sqrt(energy) / 32768.0)

def resample_chunk(hw_samples, target_len):
    """Resample using scipy (high quality)."""
    resampled = signal.resample(hw_samples.astype(np.float32), target_len)
    return np.clip(resampled, -32768, 32767).astype(np.int16)

def transcribe(audio_samples):
    """Transcribe audio using faster-whisper."""
    # Write to temp WAV
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    
    try:
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TARGET_RATE)
            wf.writeframes(audio_samples.tobytes())
        
        start = time.time()
        segments, info = stt_model.transcribe(
            wav_path,
            language="en",
            beam_size=1,
            vad_filter=True,
        )
        
        text_parts = []
        logprobs = []
        for seg in segments:
            text_parts.append(seg.text.strip() if seg.text else "")
            if seg.avg_logprob is not None:
                logprobs.append(seg.avg_logprob)
        
        text = " ".join(p for p in text_parts if p)
        
        if logprobs:
            confidence = max(0.0, min(1.0, math.exp(sum(logprobs) / len(logprobs))))
        else:
            confidence = 0.8 if text else 0.0
        
        whisper_ms = int((time.time() - start) * 1000)
        return text, confidence, whisper_ms
    
    finally:
        try:
            os.unlink(wav_path)
        except:
            pass

print("", flush=True)
print("=" * 50, flush=True)
print("🎤 Ready! Say 'HEY ROBO' then speak your command.", flush=True)
print("   Test will run 3 complete cycles.", flush=True)
print("=" * 50, flush=True)
print("", flush=True)

# Main loop - run 3 cycles
cycles = 0
max_cycles = 3

try:
    while cycles < max_cycles:
        print(f"[Cycle {cycles+1}/{max_cycles}] Listening for wakeword...", flush=True)
        
        # PHASE 1: Wait for wakeword
        while True:
            data = stream.read(HW_CHUNK, exception_on_overflow=False)
            hw_samples = np.frombuffer(data, dtype=np.int16)
            resampled = resample_chunk(hw_samples, FRAME_LENGTH)
            
            result = porcupine.process(resampled.tolist())
            if result >= 0:
                print("", flush=True)
                print("🎯 WAKEWORD DETECTED! Listening for your command...", flush=True)
                break
        
        # PHASE 2: Capture audio until silence
        capture_buffer = []
        capture_start = time.time()
        silence_frames = 0
        chunk_ms = FRAME_LENGTH / TARGET_RATE * 1000
        silence_frames_needed = int(SILENCE_DURATION_MS / chunk_ms)
        
        print("   (Speak now, I'll stop when you pause)", flush=True)
        
        while True:
            data = stream.read(HW_CHUNK, exception_on_overflow=False)
            hw_samples = np.frombuffer(data, dtype=np.int16)
            resampled = resample_chunk(hw_samples, FRAME_LENGTH)
            
            capture_buffer.append(resampled)
            
            elapsed = time.time() - capture_start
            
            # Check max duration
            if elapsed >= MAX_CAPTURE_SECONDS:
                print(f"   (Max duration {MAX_CAPTURE_SECONDS}s reached)", flush=True)
                break
            
            # Silence detection
            rms = calc_rms(resampled)
            if rms < SILENCE_THRESHOLD:
                silence_frames += 1
                if silence_frames >= silence_frames_needed and elapsed >= MIN_CAPTURE_SECONDS:
                    print(f"   (Silence detected after {elapsed:.1f}s)", flush=True)
                    break
            else:
                silence_frames = 0
        
        # PHASE 3: Transcribe
        capture_ms = int((time.time() - capture_start) * 1000)
        audio = np.concatenate(capture_buffer)
        
        print(f"   Captured {len(audio)/TARGET_RATE:.1f}s of audio, transcribing...", flush=True)
        
        text, confidence, whisper_ms = transcribe(audio)
        
        print("", flush=True)
        print(f"📝 TRANSCRIPTION: \"{text}\"", flush=True)
        print(f"   Confidence: {confidence:.2f}", flush=True)
        print(f"   Timings: capture={capture_ms}ms, whisper={whisper_ms}ms", flush=True)
        print("", flush=True)
        
        cycles += 1

except KeyboardInterrupt:
    print("\nInterrupted by user", flush=True)

finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
    porcupine.delete()

print("=" * 50, flush=True)
print("✅ Test complete!", flush=True)
print("=" * 50, flush=True)
