#!/usr/bin/env python3
"""Live wakeword detection using arecord pipe."""
import os
import sys
import time
import subprocess
sys.path.insert(0, '/home/dev/smart_car')

import numpy as np
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
print(f'Porcupine: frame={porcupine.frame_length}, rate={porcupine.sample_rate}')

# Start arecord process piping raw audio
# USB mic is hw:3,0, need to record at native rate and we'll resample
DEVICE = 'plughw:3,0'
RATE = 16000  # plughw handles resampling for us
FRAME_SIZE = porcupine.frame_length  # 512 samples

cmd = [
    'arecord',
    '-D', DEVICE,
    '-f', 'S16_LE',
    '-r', str(RATE),
    '-c', '1',
    '-t', 'raw',
    '-'
]

print(f'Starting: {" ".join(cmd)}')
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

print('')
print('=' * 50)
print('  LISTENING FOR "HEY ROBO"')
print('  Say it multiple times!')
print('  Ctrl+C to stop')
print('=' * 50)

set_led(0, 0, 30)
count = 0
bytes_per_frame = FRAME_SIZE * 2  # 16-bit = 2 bytes per sample

try:
    while True:
        # Read one frame of audio
        data = proc.stdout.read(bytes_per_frame)
        if len(data) < bytes_per_frame:
            print('Audio stream ended')
            break
        
        # Convert to int16 array
        samples = np.frombuffer(data, dtype=np.int16)
        
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
    proc.terminate()
    porcupine.delete()
    if HAS_LED:
        pixels.fill((0, 0, 0))
    print('Done!')
