#!/usr/bin/env python3
"""Live wakeword detection loop with LED feedback using sounddevice."""
import os
import sys
import time
sys.path.insert(0, '/home/dev/smart_car')

import numpy as np
import sounddevice as sd
import pvporcupine

# Try LED
try:
    import board
    import neopixel
    pixels = neopixel.NeoPixel(board.D12, 8, brightness=0.3, auto_write=True)
    HAS_LED = True
    print('LED ring initialized')
except Exception as e:
    HAS_LED = False
    print(f'LED not available: {e}')

def set_led(r, g, b):
    if HAS_LED:
        pixels.fill((r, g, b))

def flash_led(r, g, b, times=3):
    if HAS_LED:
        for _ in range(times):
            pixels.fill((r, g, b))
            time.sleep(0.1)
            pixels.fill((0, 0, 0))
            time.sleep(0.1)

def resample(samples, src_rate, dst_rate, dst_len):
    """Simple linear resampling."""
    if src_rate == dst_rate:
        return samples
    x_src = np.linspace(0, 1, len(samples), endpoint=False)
    x_dst = np.linspace(0, 1, dst_len, endpoint=False)
    return np.interp(x_dst, x_src, samples.astype(np.float32)).astype(np.int16)

access_key = os.environ.get('PV_ACCESS_KEY', '')
if not access_key:
    print('ERROR: PV_ACCESS_KEY not set!')
    sys.exit(1)

model_path = '/home/dev/smart_car/models/wakeword/hey_robo.ppn'
print(f'Loading Porcupine...')

porcupine = pvporcupine.create(
    access_key=access_key,
    keyword_paths=[model_path],
    sensitivities=[0.75]
)
print(f'Porcupine ready: frame={porcupine.frame_length}, rate={porcupine.sample_rate}')

# Hardware rate (USB mic supports 48kHz)
HW_RATE = 48000
TARGET_RATE = porcupine.sample_rate  # 16000
hw_frame_len = int(porcupine.frame_length * HW_RATE / TARGET_RATE)  # 1536

# Find USB device
print('Available devices:')
devices = sd.query_devices()
usb_device = None
for i, dev in enumerate(devices):
    if dev['max_input_channels'] > 0:
        print(f'  {i}: {dev["name"]} ({dev["max_input_channels"]} in)')
        if 'USB Audio Device' in dev['name'] and dev['max_input_channels'] > 0:
            usb_device = i

if usb_device is None:
    # Fallback to device 1 (usually USB Audio)
    usb_device = 1
    print(f'Using fallback device: {usb_device}')
else:
    print(f'Using USB device: {usb_device}')

print('')
print('=' * 50)
print('  LISTENING FOR "HEY ROBO"')
print('  Say it multiple times!')
print('  Ctrl+C to stop')
print('=' * 50)

set_led(0, 0, 30)
count = 0

try:
    with sd.InputStream(samplerate=HW_RATE, channels=1, dtype='int16',
                        device=usb_device, blocksize=hw_frame_len) as stream:
        print(f'Stream opened: {HW_RATE}Hz mono')
        while True:
            # Read audio
            audio, overflowed = stream.read(hw_frame_len)
            hw_samples = audio.flatten()
            
            # Resample to 16kHz
            samples = resample(hw_samples, HW_RATE, TARGET_RATE, porcupine.frame_length)
            
            # Process with Porcupine
            result = porcupine.process(samples.tolist())
            if result >= 0:
                count += 1
                ts = time.strftime('%H:%M:%S')
                print(f'[{ts}] 🎤 WAKEWORD DETECTED! #{count}')
                flash_led(0, 255, 0, times=3)
                set_led(0, 0, 30)

except KeyboardInterrupt:
    print(f'\nTotal detections: {count}')
finally:
    porcupine.delete()
    if HAS_LED:
        pixels.fill((0, 0, 0))
    print('Done!')
