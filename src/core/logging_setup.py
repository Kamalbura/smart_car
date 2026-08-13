"""Application-wide logging helpers.

Logs go to stdout *and* to a rotating file. Both matter:

* stdout is the only thing a container runtime can see. With a file handler
  alone and ``propagate = False``, a containerised service produces completely
  empty ``docker logs`` output while running perfectly -- which looks exactly
  like a service that failed to start. Under systemd the same stream is
  captured by journald, so ``journalctl -fu orchestrator`` works too.
* the rotating file survives a container being recreated, and is what the
  remote interface tails to expose recent logs to the Android app.

Set ``LOG_STDOUT=0`` to suppress the stream handler, or ``LOG_LEVEL`` to change
verbosity without touching code.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_FALSEY = {"0", "false", "no", "off"}


def _resolve_level(default: int) -> int:
    raw = os.environ.get("LOG_LEVEL", "").strip().upper()
    if not raw:
        return default
    return getattr(logging, raw, default)


def get_logger(name: str, log_dir: Optional[Path], *, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(_resolve_level(level))
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if os.environ.get("LOG_STDOUT", "1").lower() not in _FALSEY:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    try:
        log_root = log_dir if log_dir is not None else Path("logs")
        log_root.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_root / f"{name}.log", maxBytes=2_000_000, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # A read-only or root-owned log directory is not fatal, but losing all
        # output would be, so make sure at least one handler survives.
        if not logger.handlers:
            fallback = logging.StreamHandler(sys.stderr)
            fallback.setFormatter(formatter)
            logger.addHandler(fallback)

    logger.propagate = False
    return logger
