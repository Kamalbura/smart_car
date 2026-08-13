"""Centralized logging factory using rotating file handlers."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def get_logger(name: str, *, log_path: Path, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_path, maxBytes=1_048_576, backupCount=5)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
