"""Ensure each module exposes its primary entrypoints."""
from __future__ import annotations

from pathlib import Path

from src.tools.test_discovery import list_modules


def test_module_inits_exist() -> None:
    src_root = Path(__file__).resolve().parents[1]
    modules = list_modules(src_root)
    assert modules, "Expected module folders with __init__.py"
    names = {m.name for m in modules}
    expected = {"stt", "tts", "llm", "vision", "ui", "core", "tools"}
    assert expected.issubset(names)
