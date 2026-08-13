#!/usr/bin/env python3
"""Motor test: FORWARD, BACKWARD, LEFT, RIGHT for 10 seconds each."""
import serial
import time

ser = serial.Serial('/dev/ttyS0', 115200, timeout=0.5)
commands = ['FORWARD', 'BACKWARD', 'LEFT', 'RIGHT', 'STOP']

for cmd in commands:
    print(f'TX {cmd}', flush=True)
    ser.write((cmd + '\n').encode())
    ser.flush()
    
    dwell = 10 if cmd != 'STOP' else 2
    end = time.time() + dwell
    while time.time() < end:
        try:
            line = ser.readline().decode('utf-8', 'replace').strip()
            if line and 'ACK' in line:
                print(f'  {line}', flush=True)
        except:
            pass
        time.sleep(0.05)

ser.close()
print('Motor test complete!')
