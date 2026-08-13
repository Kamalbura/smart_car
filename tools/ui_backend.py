"""Minimal backend for Tk monitor (skeleton).

Subscribes to system health topics over ZeroMQ and prints updates. This
can be extended to expose a local HTTP or Unix-socket API for richer UIs.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import zmq

from src.core.config_loader import load_config
from src.core.ipc import make_subscriber
from src.core.logging_setup import get_logger


def _health_loop(cfg_path: Path) -> None:
    cfg = load_config(cfg_path)
    log_dir = Path(cfg.get("logs", {}).get("directory", "logs"))
    if not log_dir.is_absolute():
        root = Path(os.environ.get("PROJECT_ROOT", ".")).resolve()
        log_dir = root / log_dir
    logger = get_logger("ui.backend", log_dir)

    sub = make_subscriber(cfg, channel="upstream")
    logger.info("UI backend listening for health events on upstream bus")

    while True:
        try:
            topic, data = sub.recv_multipart()
        except KeyboardInterrupt:
            logger.info("UI backend interrupted; exiting")
            break
        try:
            payload: Any = json.loads(data)
        except Exception:
            continue
        if b"health" in topic:
            logger.info("HEALTH %s: %s", topic.decode("utf-8", "ignore"), payload)


def main() -> None:
    cfg_path = Path("config/system.yaml")
    t = threading.Thread(target=_health_loop, args=(cfg_path,), daemon=False)
    t.start()
    t.join()


if __name__ == "__main__":
    main()
