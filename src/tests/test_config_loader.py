"""Smoke tests for the config loader."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.config_loader import ConfigLoader


def test_config_loader_roundtrip(tmp_path: Path) -> None:
    config_path = tmp_path / "settings.yaml"
    config_path.write_text("""
stt:
  backend: whisper_cpp
  model_path: ./models/stt.bin
llm:
  model_path: ./models/llm.gguf
tts:
  voice: demo
  model_path: ./models/tts.onnx
vision:
  model_path: ./models/vision.pt
display: {}
""")
    loader = ConfigLoader(config_path)
    cfg = loader.load()
    assert cfg.stt.backend.value == "whisper_cpp"
    assert cfg.llm.context_tokens == 2048


def test_config_loader_missing(tmp_path: Path) -> None:
    loader = ConfigLoader(tmp_path / "missing.yaml")
    with pytest.raises(FileNotFoundError):
        loader.load()
