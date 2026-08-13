#!/usr/bin/env python3
"""Analyze RMS levels in recorded audio to calibrate silence detection."""
import numpy as np
import wave
import sys

wav_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/resampled_test.wav"

with wave.open(wav_path, "rb") as wf:
    data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    rate = wf.getframerate()

print(f"Analyzing {wav_path}")
print(f"Sample rate: {rate}Hz, Duration: {len(data)/rate:.1f}s")
print()

chunk_size = 512  # Same as Porcupine frame
chunk_duration_ms = chunk_size / rate * 1000

print(f"Chunk size: {chunk_size} samples ({chunk_duration_ms:.1f}ms)")
print()

rms_values = []
for i in range(len(data) // chunk_size):
    chunk = data[i * chunk_size:(i + 1) * chunk_size]
    rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) / 32768.0
    rms_values.append(rms)

rms_array = np.array(rms_values)

print(f"RMS Statistics:")
print(f"  Min:    {rms_array.min():.4f}")
print(f"  Max:    {rms_array.max():.4f}")
print(f"  Mean:   {rms_array.mean():.4f}")
print(f"  Median: {np.median(rms_array):.4f}")
print(f"  Std:    {rms_array.std():.4f}")
print()

# Find percentiles
print(f"Percentiles:")
for p in [5, 10, 25, 50, 75, 90, 95]:
    print(f"  {p}%: {np.percentile(rms_array, p):.4f}")
print()

# Suggest threshold
noise_floor = np.percentile(rms_array, 10)
suggested = noise_floor * 1.5
print(f"Suggested silence threshold: {suggested:.4f}")
print(f"(Based on 10th percentile {noise_floor:.4f} * 1.5)")
