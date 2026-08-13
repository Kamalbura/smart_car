#!/usr/bin/env python3
"""Fetch Piper ONNX models for selected voices."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Tuple

VOICES_JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"
BASE_RESOLVE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", "/home/dev/project_root"))
DEFAULT_DEST = Path("/opt/models/piper")
DEFAULT_LOG = PROJECT_ROOT / "logs" / "setup.log"


def load_catalogue() -> Dict[str, Dict]:
    request = urllib.request.Request(VOICES_JSON_URL, headers={"User-Agent": "piper-model-fetcher/1.0"})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def select_files(metadata: Dict[str, Dict]) -> Iterable[str]:
    files = metadata.get("files", {})
    for path in files:
        if path.endswith(('.onnx', '.onnx.json')):
            yield path


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "piper-model-fetcher/1.0"})
    with urllib.request.urlopen(request) as response, destination.open("wb") as handle:
        handle.write(response.read())


def log(message: str, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def fetch_voice(voice: str, catalogue: Dict[str, Dict], dest_root: Path, log_path: Path) -> Tuple[str, Tuple[Path, ...]]:
    if voice not in catalogue:
        raise KeyError(f"Voice {voice} not found in catalogue")
    files = tuple(select_files(catalogue[voice]))
    if not files:
        raise RuntimeError(f"No downloadable files for {voice}")
    saved_files = []
    for rel_path in files:
        encoded = urllib.parse.quote(rel_path, safe="/")
        url = urllib.parse.urljoin(BASE_RESOLVE_URL, encoded)
        target_path = dest_root / Path(rel_path).name
        if target_path.exists():
            log(f"Skipping existing file {target_path}", log_path)
            saved_files.append(target_path)
            continue
        log(f"Downloading {voice} file {url} -> {target_path}", log_path)
        try:
            download(url, target_path)
        except urllib.error.URLError as exc:  # pragma: no cover
            raise RuntimeError(f"Failed to download {url}: {exc}") from exc
        saved_files.append(target_path)
    return voice, tuple(saved_files)


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(description="Fetch Piper ONNX models for selected voices.")
    parser.add_argument("voices", nargs="+", help="Voice keys, e.g. en_US-amy-medium")
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="Destination directory for models")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="Setup log path")
    args = parser.parse_args(argv)

    catalogue = load_catalogue()
    args.dest.mkdir(parents=True, exist_ok=True)

    for voice in args.voices:
        voice = voice.strip()
        if not voice:
            continue
        try:
            _, files = fetch_voice(voice, catalogue, args.dest, args.log)
        except Exception as exc:  # pragma: no cover
            log(f"Error fetching {voice}: {exc}", args.log)
            print(f"Failed to fetch {voice}: {exc}", file=sys.stderr)
            return 1
        print(f"Fetched {voice} ->")
        for file_path in files:
            print(f"  {file_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
