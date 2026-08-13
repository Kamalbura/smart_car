#!/usr/bin/env python3
"""Test audio capture with scipy resampling - record 10s, save, playback."""
import sys
import os
import wave
import time
import ctypes
import numpy as np

# Suppress ALSA errors before importing PyAudio
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

# Configuration
HW_RATE = 48000       # USB mic native rate
TARGET_RATE = 16000   # Porcupine/Whisper rate
DEVICE_INDEX = None   # Use default or find USB device
DURATION = 10         # seconds to record
CHUNK_MS = 30         # chunk duration

hw_chunk = int(HW_RATE * CHUNK_MS / 1000)      # 1440 samples
target_chunk = int(TARGET_RATE * CHUNK_MS / 1000)  # 480 samples

print(f"=== AUDIO RESAMPLE TEST ===", flush=True)
print(f"Recording {DURATION}s at {HW_RATE}Hz, resampling to {TARGET_RATE}Hz", flush=True)
print(f"HW chunk: {hw_chunk} samples, Target chunk: {target_chunk} samples", flush=True)

# Initialize PyAudio
pa = pyaudio.PyAudio()

# Find USB Audio device
found_device = None
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0 and "USB" in info["name"]:
        found_device = i
        print(f"Found USB input device at index {i}: {info['name']}", flush=True)
        break

if found_device is None:
    # Fallback: use any input device
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            found_device = i
            print(f"Using input device at index {i}: {info['name']}", flush=True)
            break

if found_device is None:
    print("ERROR: No input device found!", flush=True)
    pa.terminate()
    sys.exit(1)

# Show device info
info = pa.get_device_info_by_index(found_device)
print(f"Device: {info['name']}", flush=True)
print(f"Max input channels: {info['maxInputChannels']}", flush=True)
print(f"Default sample rate: {info['defaultSampleRate']}", flush=True)

# Open stream
stream = pa.open(
    rate=HW_RATE,
    channels=1,
    format=pyaudio.paInt16,
    input=True,
    input_device_index=found_device,
    frames_per_buffer=hw_chunk,
)

print("", flush=True)
print("🎤 Recording... SPEAK NOW! Say 'hey robo' multiple times!", flush=True)
print("", flush=True)

all_samples = []
start = time.time()
chunks = 0

while time.time() - start < DURATION:
    # Read from mic
    data = stream.read(hw_chunk, exception_on_overflow=False)
    hw_samples = np.frombuffer(data, dtype=np.int16)
    
    # High quality resample using scipy (FFT-based)
    resampled_float = signal.resample(hw_samples.astype(np.float32), target_chunk)
    resampled_int16 = np.clip(resampled_float, -32768, 32767).astype(np.int16)
    
    all_samples.append(resampled_int16)
    chunks += 1
    
    # Progress indicator
    if chunks % 33 == 0:  # ~1 second
        elapsed = time.time() - start
        print(f"  {elapsed:.0f}s recorded...", flush=True)

stream.stop_stream()
stream.close()
pa.terminate()

print("", flush=True)
print("Recording complete!", flush=True)

# Concatenate all samples
audio = np.concatenate(all_samples)
print(f"Total samples: {len(audio)} ({len(audio)/TARGET_RATE:.1f}s at {TARGET_RATE}Hz)", flush=True)

# Check audio levels
rms = np.sqrt(np.mean(audio.astype(np.float32) ** 2))
peak = np.max(np.abs(audio))
print(f"Audio stats: RMS={rms:.0f}, Peak={peak}, Peak dB={20*np.log10(peak/32768):.1f}dB", flush=True)

# Save to WAV file
wav_path = "/tmp/resampled_test.wav"
with wave.open(wav_path, "wb") as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)  # 16-bit
    wf.setframerate(TARGET_RATE)
    wf.writeframes(audio.tobytes())

file_size = os.path.getsize(wav_path)
print(f"Saved to {wav_path} ({file_size} bytes)", flush=True)
print("", flush=True)
print("=== Now playing back - listen for your voice! ===", flush=True)
