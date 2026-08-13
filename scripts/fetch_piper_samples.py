#!/usr/bin/env python3
"""Download Piper TTS voice samples without pulling ONNX models."""

import json
import os
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

VOICE_TREE_API = "https://huggingface.co/api/models/rhasspy/piper-voices?expand[]=siblings"
VOICES_JSON_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"
BASE_RESOLVE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

PROJECT_ROOT = Path.home() / "project_root"
SAMPLES_DIR = PROJECT_ROOT / "models" / "piper-samples"
INDEX_PATH = SAMPLES_DIR / "VOICE_INDEX.txt"
LOG_PATH = PROJECT_ROOT / "logs" / "setup.log"


class DownloadError(RuntimeError):
    """Raised when a required download fails."""


def log(message: str) -> None:
    """Append a timestamped message to the setup log."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def fetch_json(url: str) -> Dict:
    """Fetch JSON data from the given URL."""
    request = urllib.request.Request(url, headers={"User-Agent": "piper-sample-fetcher/1.0"})
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def load_voice_catalogue() -> Dict[str, Dict]:
    """Load voice metadata from voices.json."""
    log("Fetching voices.json metadata")
    return fetch_json(VOICES_JSON_URL)


def load_repo_listing() -> List[Dict]:
    """Fetch the repository file listing from the HuggingFace API."""
    log("Fetching repository file listing")
    data = fetch_json(VOICE_TREE_API)
    return data.get("siblings", [])


def build_sample_lookup(siblings: List[Dict]) -> Dict[str, List[str]]:
    """Map directory prefixes to available sample files."""
    lookup: Dict[str, List[str]] = {}
    for entry in siblings:
        path = entry.get("rfilename", "")
        if "/samples/" not in path:
            continue
        if not path.lower().endswith((".mp3", ".wav")):
            continue
        directory = "/".join(path.split("/")[:-2])  # strip trailing /samples/<file>
        lookup.setdefault(directory, []).append(path)
    return lookup


def sample_priority(path: str) -> Tuple[int, str]:
    """Return a priority tuple for selecting the best sample file."""
    lower = path.lower()
    score = 0
    if lower.endswith(".mp3"):
        score += 200
    if "sample" in lower:
        score += 50
    if lower.endswith("speaker_0.mp3"):
        score += 25
    if lower.endswith("speaker_0.wav"):
        score += 5
    return (-score, path)


def pick_sample(base_dir: str, sample_lookup: Dict[str, List[str]]) -> Optional[str]:
    """Select the preferred sample file for a voice."""
    candidates = sample_lookup.get(base_dir, [])
    if not candidates:
        return None
    return sorted(candidates, key=sample_priority)[0]


def sanitize_for_filename(text: str) -> str:
    """Normalise text for use in filenames while preserving intent."""
    normalised = unicodedata.normalize("NFKC", text)
    # Avoid filesystem surprises by stripping path separators
    safe = normalised.replace("/", "-")
    # Collapse whitespace
    safe = " ".join(safe.split())
    return safe


def ensure_dirs() -> None:
    """Ensure that destination directories exist."""
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)


def download_file(url: str, destination: Path) -> None:
    """Download a file to the given destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "piper-sample-fetcher/1.0"})
    try:
        with urllib.request.urlopen(request) as response, destination.open("wb") as handle:
            handle.write(response.read())
    except urllib.error.URLError as exc:  # pragma: no cover - network
        raise DownloadError(f"Failed to download {url}: {exc}") from exc


def convert_wav_to_mp3(source: Path, target: Path) -> None:
    """Convert a WAV file to MP3 using ffmpeg."""
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(source),
        str(target),
    ]
    result = os.spawnvp(os.P_WAIT, "ffmpeg", command)
    if result != 0:
        raise DownloadError(f"ffmpeg conversion failed for {source}")


def main() -> None:
    ensure_dirs()
    voices = load_voice_catalogue()
    siblings = load_repo_listing()
    sample_lookup = build_sample_lookup(siblings)

    log(f"Voices discovered: {len(voices)}")
    results: List[Tuple[str, str, str, Path]] = []

    for voice_name, metadata in sorted(voices.items()):
        language_code = metadata.get("language", {}).get("code", "unknown")
        base_dir = None
        for file_path in metadata.get("files", {}):
            if file_path.endswith(".onnx"):
                base_dir = "/".join(file_path.split("/")[:-1])
                break
        if base_dir is None:
            log(f"Skipping {voice_name}: no ONNX file path located")
            continue
        sample_path = pick_sample(base_dir, sample_lookup)
        if sample_path is None:
            log(f"No sample available for {voice_name}")
            continue

        encoded_path = urllib.parse.quote(sample_path, safe="/")
        source_url = urllib.parse.urljoin(BASE_RESOLVE_URL, encoded_path)
        display_name = sanitize_for_filename(voice_name)
        target_file = SAMPLES_DIR / f"sample-{display_name}.mp3"

        if target_file.exists():
            log(f"Sample already present for {voice_name}, skipping download")
        else:
            log(f"Downloading sample for {voice_name} from {source_url}")
            tmp_suffix = Path(sample_path).suffix.lower()
            if tmp_suffix == ".mp3":
                download_file(source_url, target_file)
            else:
                with tempfile.NamedTemporaryFile(suffix=tmp_suffix, delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    download_file(source_url, tmp_path)
                    log(f"Converting WAV sample to MP3 for {voice_name}")
                    convert_wav_to_mp3(tmp_path, target_file)
                finally:
                    if tmp_path.exists():
                        tmp_path.unlink()
        gender = (
            metadata.get("speaker_gender")
            or metadata.get("speaker", {}).get("gender")
            or "unknown"
        )
        results.append((voice_name, language_code, gender, target_file.resolve()))

    lines = [f"{voice} | {lang} | {gender} | {path}" for voice, lang, gender, path in results]
    INDEX_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    log(f"Voice index written to {INDEX_PATH}")

    print("Voices Found:")
    for voice, *_ in results:
        print(voice)
    print("\nSample Files:")
    for voice, _, _, path in results:
        print(f"{voice}: {path}")


if __name__ == "__main__":
    try:
        main()
    except DownloadError as error:
        log(str(error))
        print(str(error), file=sys.stderr)
        sys.exit(1)
