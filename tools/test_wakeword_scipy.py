#!/usr/bin/env python3
"""Test wakeword detection with scipy-resampled audio."""
import sys
import os
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
import pvporcupine

# Configuration
HW_RATE = 48000       # USB mic native rate
TARGET_RATE = 16000   # Porcupine rate
DURATION = 30         # seconds to run test
SENSITIVITY = 0.7     # Wakeword sensitivity

# Porcupine config
ACCESS_KEY = os.environ.get("PV_ACCESS_KEY", "")
MODEL_PATH = "/home/dev/smart_car/models/wakeword/hey_robo.ppn"

print("=== WAKEWORD DETECTION TEST ===", flush=True)
print(f"Duration: {DURATION}s", flush=True)
print(f"Sensitivity: {SENSITIVITY}", flush=True)
print(f"Resampling: {HW_RATE}Hz → {TARGET_RATE}Hz (scipy)", flush=True)

# Initialize Porcupine
if not ACCESS_KEY:
    # Try loading from config
    sys.path.insert(0, "/home/dev/smart_car")
    from src.core.config_loader import load_config
    from pathlib import Path
    cfg = load_config(Path("/home/dev/smart_car/config/system.yaml"))
    ACCESS_KEY = cfg.get("wakeword", {}).get("access_key", "")

print(f"Access key: {ACCESS_KEY[:20]}..." if ACCESS_KEY else "ERROR: No access key!", flush=True)

porcupine = pvporcupine.create(
    access_key=ACCESS_KEY,
    keyword_paths=[MODEL_PATH],
    sensitivities=[SENSITIVITY],
)

FRAME_LENGTH = porcupine.frame_length  # 512 samples
print(f"Porcupine frame_length: {FRAME_LENGTH}", flush=True)
print(f"Porcupine sample_rate: {porcupine.sample_rate}", flush=True)

# Calculate chunk sizes
# We need to read enough HW samples to get FRAME_LENGTH target samples after resampling
# ratio = 48000/16000 = 3, so we need 3*512 = 1536 HW samples
RESAMPLE_RATIO = HW_RATE / TARGET_RATE
HW_CHUNK = int(FRAME_LENGTH * RESAMPLE_RATIO)

print(f"HW chunk size: {HW_CHUNK} samples ({HW_CHUNK/HW_RATE*1000:.1f}ms)", flush=True)

# Initialize PyAudio
pa = pyaudio.PyAudio()

# Find USB Audio device
found_device = None
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0 and "USB" in info["name"]:
        found_device = i
        print(f"Using device {i}: {info['name']}", flush=True)
        break

if found_device is None:
    print("ERROR: No USB input device found!", flush=True)
    sys.exit(1)

# Open stream
stream = pa.open(
    rate=HW_RATE,
    channels=1,
    format=pyaudio.paInt16,
    input=True,
    input_device_index=found_device,
    frames_per_buffer=HW_CHUNK,
)

print("", flush=True)
print("🎤 Listening for 'HEY ROBO'...", flush=True)
print("   Say it multiple times to test detection!", flush=True)
print("", flush=True)

# Detection loop
start_time = time.time()
detections = 0
frames_processed = 0

try:
    while time.time() - start_time < DURATION:
        # Read from mic
        data = stream.read(HW_CHUNK, exception_on_overflow=False)
        hw_samples = np.frombuffer(data, dtype=np.int16)
        
        # High quality resample using scipy (FFT-based)
        resampled_float = signal.resample(hw_samples.astype(np.float32), FRAME_LENGTH)
        resampled_int16 = np.clip(resampled_float, -32768, 32767).astype(np.int16)
        
        # Process with Porcupine
        result = porcupine.process(resampled_int16.tolist())
        frames_processed += 1
        
        if result >= 0:
            detections += 1
            elapsed = time.time() - start_time
            print(f"", flush=True)
            print(f"🎯 WAKEWORD DETECTED #{detections} at {elapsed:.1f}s!", flush=True)
            print(f"", flush=True)
        
        # Progress indicator every 5 seconds
        elapsed = time.time() - start_time
        if frames_processed % 156 == 0:  # ~5 seconds (512/16000 * 156 ≈ 5s)
            print(f"  [{elapsed:.0f}s] Listening... (detections so far: {detections})", flush=True)

except KeyboardInterrupt:
    print("\nInterrupted by user", flush=True)

finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
    porcupine.delete()

print("", flush=True)
print("=== RESULTS ===", flush=True)
print(f"Duration: {time.time() - start_time:.1f}s", flush=True)
print(f"Frames processed: {frames_processed}", flush=True)
print(f"Total detections: {detections}", flush=True)
print("", flush=True)

if detections == 0:
    print("⚠️  No detections! Try:", flush=True)
    print("   - Speaking louder/clearer", flush=True)
    print("   - Moving closer to mic", flush=True)
    print("   - Increasing sensitivity", flush=True)
else:
    print(f"✅ Wakeword detection working! ({detections} detections)", flush=True)
