"""Shared pytest setup.

Every service loads its configuration with a *relative* path --
``load_config(Path("config/system.yaml"))`` -- so the whole suite silently
depends on the current working directory being the repository root. Running
``pytest`` from anywhere else used to fail at config load with a
FileNotFoundError that pointed at the config rather than at the real cause.

Pinning the directory here is the smaller fix. The larger one is to resolve
config paths relative to the package rather than the process, which is worth
doing but touches every runner.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True, scope="session")
def run_from_repo_root():
    previous = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        yield REPO_ROOT
    finally:
        os.chdir(previous)
