#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
import argparse

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_config
from src.core.ipc import make_publisher, TOPIC_CMD_TTS_SPEAK, publish_json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--text', required=True, help='Text to speak')
    ap.add_argument(
        '--burst-ms',
        type=int,
        default=1000,
        help='Publish duration in milliseconds (helps avoid PUB/SUB timing drops)',
    )
    args = ap.parse_args()
    cfg = load_config(Path('config/system.yaml'))
    # Publish to UPSTREAM so orchestrator receives and forwards to TTS
    pub = make_publisher(cfg, channel='upstream')

    payload = {'text': args.text}

    # ZMQ PUB/SUB drops messages until subscriptions propagate.
    import time

    end = time.time() + (max(0, args.burst_ms) / 1000.0)
    sent = 0
    while True:
        publish_json(pub, TOPIC_CMD_TTS_SPEAK, payload)
        sent += 1
        if time.time() >= end:
            break
        time.sleep(0.05)

    print('sent TTS:', args.text, f'(x{sent})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
