#!/usr/bin/env python3
from __future__ import annotations

"""Helper: say "Hi Cherry" via the existing TTS pipeline.

This publishes a TTS message on the downstream bus. Ensure a TTS runner
is active (e.g., Piper at src/tts/piper_runner.py) and your USB audio
device is the default ALSA output (aplay).

Usage:
  source .venvs/core/bin/activate
  python3 scripts/say_hi_cherry.py
"""

import sys
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_config
from src.core.ipc import make_publisher, TOPIC_TTS, publish_json


def main() -> int:
    cfg = load_config(Path("config/system.yaml"))
    pub = make_publisher(cfg, channel="downstream")
    text = "Hi Cherry"
    publish_json(pub, TOPIC_TTS, {"text": text})
    print("sent TTS:", text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
