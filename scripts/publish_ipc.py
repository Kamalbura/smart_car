#!/usr/bin/env python3
"""Publish a single JSON payload to the ZMQ IPC bus.

This is a small operator/debug helper for the Pi stack.

Examples:
  # Trigger TTS via orchestrator (safe: no nav intent)
  python scripts/publish_ipc.py --channel upstream --topic llm.response --json '{"text":"hello"}'

  # Simulate wakeword event (orchestrator will pause vision + start STT)
  python scripts/publish_ipc.py --channel upstream --topic ww.detected --json '{"keyword":"hey genny","confidence":0.95}'
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_config
from src.core.ipc import make_publisher, publish_json


TOPIC_MAP = {
    "ww.detected": b"ww.detected",
    "stt.transcription": b"stt.transcription",
    "llm.request": b"llm.request",
    "llm.response": b"llm.response",
    "tts.speak": b"tts.speak",
    "visn.object": b"visn.object",
    "nav.command": b"nav.command",
    "cmd.listen.start": b"cmd.listen.start",
    "cmd.listen.stop": b"cmd.listen.stop",
    "cmd.pause.vision": b"cmd.pause.vision",
    "display.state": b"display.state",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish one IPC message")
    ap.add_argument("--config", default="config/system.yaml")
    ap.add_argument("--channel", choices=("upstream", "downstream"), default="upstream")
    ap.add_argument("--topic", required=True, help="Topic string (e.g. llm.response)")
    payload_group = ap.add_mutually_exclusive_group(required=True)
    payload_group.add_argument("--json", help="JSON payload")
    payload_group.add_argument("--json-file", help="Path to a file containing JSON payload")
    ap.add_argument("--sleep", type=float, default=0.2, help="Sleep after connect (PUB/SUB warmup)")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    topic = TOPIC_MAP.get(args.topic, args.topic.encode("utf-8"))

    pub = make_publisher(cfg, channel=args.channel, bind=False)
    time.sleep(max(0.0, float(args.sleep)))

    if args.json_file:
        payload_text = Path(args.json_file).read_text(encoding="utf-8")
    else:
        payload_text = args.json
    payload = json.loads(payload_text)
    publish_json(pub, topic, payload)
    print(f"sent {args.channel}:{args.topic} {payload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
