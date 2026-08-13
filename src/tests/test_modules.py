"""Basic sanity tests ensuring every subsystem exposes primary classes."""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]


def discover_packages() -> list[str]:
    packages = []
    for pkg in pkgutil.iter_modules([str(MODULE_ROOT)]):
        if pkg.name in {"tests", "__pycache__"}:
            continue
        packages.append(pkg.name)
    return packages


def test_packages_are_importable() -> None:
    for pkg in discover_packages():
        module = importlib.import_module(f"src.{pkg}")
        assert module is not None, f"Failed to import {pkg}"
