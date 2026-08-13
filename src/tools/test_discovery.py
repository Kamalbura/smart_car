"""Utility that collects module names for pytest auto-generation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(slots=True)
class ModuleInfo:
    name: str
    path: Path


def list_modules(src_root: Path) -> List[ModuleInfo]:
    modules = []
    for child in src_root.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            modules.append(ModuleInfo(name=child.name, path=child))
    return modules
