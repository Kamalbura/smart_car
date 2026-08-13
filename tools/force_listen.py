#!/usr/bin/env python3
"""Manual trigger to force listening mode via cmd.listen.start."""
from __future__ import annotations

import json
import time
import zmq
from pathlib import Path

from src.core.config_loader import load_config


def main() -> None:
    cfg = load_config(Path("config/system.yaml"))
    downstream = cfg.get("ipc", {}).get("downstream", "tcp://127.0.0.1:6011")

    ctx = zmq.Context.instance()
    pub = ctx.socket(zmq.PUB)
    pub.connect(downstream)
    # Allow SUBs to subscribe
    time.sleep(0.3)

    payload = {"start": True, "source": "manual_trigger"}
    pub.send_multipart([b"cmd.listen.start", json.dumps(payload).encode("utf-8")])
    print(f"Sent cmd.listen.start to {downstream}: {payload}")


if __name__ == "__main__":
    main()
