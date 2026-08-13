#!/usr/bin/env python3
"""Test runner for best_voice_pipeline."""
import sys
sys.path.insert(0, '/home/dev/smart_car')

print("Importing module...", flush=True)
from src.audio.best_voice_pipeline import BestVoicePipeline, VoiceConfig
print("Import OK!", flush=True)

import os
from pathlib import Path
from src.core.config_loader import load_config

PROJECT_ROOT = Path('/home/dev/smart_car')
config_path = PROJECT_ROOT / 'config/system.yaml'
raw_config = load_config(config_path)
ww_cfg = raw_config.get('wakeword', {}) or {}

access_key = ww_cfg.get('access_key') or os.environ.get('PV_ACCESS_KEY', '')
model_path = Path(ww_cfg.get('model', ''))

print(f"Access key: {access_key[:20]}...", flush=True)
print(f"Model: {model_path}", flush=True)
print(f"Model exists: {model_path.exists()}", flush=True)

config = VoiceConfig(
    hw_sample_rate=48000,
    target_sample_rate=16000,
    device_index=None,  # Auto-detect
    pv_access_key=access_key,
    wakeword_model=model_path,
    wakeword_sensitivity=0.7,
    stt_model='tiny.en',
    silence_threshold=0.25,
    silence_duration_ms=800,
)
print("Config created!", flush=True)

pipeline = BestVoicePipeline(config, config_path)
print("Pipeline instance created!", flush=True)

if not pipeline.start():
    print("Failed to start pipeline!", flush=True)
    sys.exit(1)

print("Pipeline started! Say HEY ROBO...", flush=True)
try:
    pipeline.run()
finally:
    pipeline.stop()
