#!/usr/bin/env python3
"""Configure ALSA dsnoop/dmix devices for the smart car audio stack.

The script discovers the primary USB microphone and speaker, then
writes a ~/.asoundrc that exposes:

    pcm.smartcar_capture -> dsnoop on the USB mic at 16 kHz mono
    pcm.smartcar_playback -> dmix on the USB speaker
    pcm.!default -> asym wrapper (capture/playback)

This lets the wakeword and STT services open the "default" ALSA device
simultaneously with zero contention.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import pyaudio
except ImportError as exc:  # pragma: no cover - tooling dependency
    raise SystemExit("PyAudio is required for setup_audio_hw.py") from exc


@dataclass
class ALSADevice:
    card: int
    device: int
    name: str


CARD_LINE = re.compile(r"card (\d+): ([^\[]+)\[([^\]]+)\], device (\d+): ([^\[]+)\[([^\]]+)\]")


def _run_cmd(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command {' '.join(cmd)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _parse_alsa_devices(output: str, keyword: str) -> Optional[ALSADevice]:
    keyword_lower = keyword.lower()
    for line in output.splitlines():
        match = CARD_LINE.search(line)
        if not match:
            continue
        card = int(match.group(1))
        long_name = match.group(3).strip()
        device = int(match.group(4))
        if keyword_lower in long_name.lower():
            return ALSADevice(card=card, device=device, name=long_name)
    return None


def _find_pyaudio_device(pa: pyaudio.PyAudio, keyword: str, *, is_input: bool) -> Optional[int]:
    keyword_lower = keyword.lower()
    for idx in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(idx)
        channels = info["maxInputChannels" if is_input else "maxOutputChannels"]
        if channels <= 0:
            continue
        if keyword_lower in info["name"].lower():
            return idx
    return None


def _render_asoundrc(capture: ALSADevice, playback: ALSADevice, *, capture_rate: int) -> str:
    return f"""
pcm.smartcar_capture {{
    type dsnoop
    ipc_key 2048
    slave {{
        pcm "hw:{capture.card},{capture.device}"
        channels 1
        rate {capture_rate}
        format S16_LE
    }}
}}

pcm.smartcar_playback {{
    type dmix
    ipc_key 2049
    slave {{
        pcm "hw:{playback.card},{playback.device}"
        channels 2
        rate 48000
        format S16_LE
    }}
}}

pcm.smartcar {{
    type asym
    playback.pcm "smartcar_playback"
    capture.pcm "smartcar_capture"
}}

pcm.!default pcm.smartcar
ctl.!default {{
    type hw
    card {playback.card}
}}
""".strip() + "\n"


def write_asoundrc(content: str) -> Path:
    dst = Path.home() / ".asoundrc"
    if dst.exists():
        backup = dst.with_suffix(".backup")
        dst.replace(backup)
        print(f"Existing {dst} backed up to {backup}")
    dst.write_text(content)
    return dst


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ~/.asoundrc with dsnoop/dmix devices")
    parser.add_argument("--keyword", default="USB Audio", help="Substring to match for both mic and speaker")
    parser.add_argument("--capture-keyword", default=None, help="Override mic substring")
    parser.add_argument("--playback-keyword", default=None, help="Override speaker substring")
    parser.add_argument("--rate", type=int, default=16000, help="Capture sample rate for dsnoop")
    args = parser.parse_args()

    mic_key = args.capture_keyword or args.keyword
    spk_key = args.playback_keyword or args.keyword

    print("Scanning ALSA devices via arecord/aplay ...")
    arecord_out = _run_cmd(["arecord", "-l"])
    aplay_out = _run_cmd(["aplay", "-l"])

    capture_dev = _parse_alsa_devices(arecord_out, mic_key)
    playback_dev = _parse_alsa_devices(aplay_out, spk_key)

    if not capture_dev:
        raise SystemExit(f"Could not locate capture device containing '{mic_key}'")
    if not playback_dev:
        raise SystemExit(f"Could not locate playback device containing '{spk_key}'")

    pa = pyaudio.PyAudio()
    try:
        mic_index = _find_pyaudio_device(pa, mic_key, is_input=True)
        spk_index = _find_pyaudio_device(pa, spk_key, is_input=False)
    finally:
        pa.terminate()

    print(f"Capture device: card {capture_dev.card}, device {capture_dev.device}, name={capture_dev.name}")
    print(f"Playback device: card {playback_dev.card}, device {playback_dev.device}, name={playback_dev.name}")
    if mic_index is not None:
        print(f"PyAudio capture index suggestion: {mic_index}")
    if spk_index is not None:
        print(f"PyAudio playback index suggestion: {spk_index}")

    content = _render_asoundrc(capture_dev, playback_dev, capture_rate=args.rate)
    dst = write_asoundrc(content)
    print(f"Wrote ALSA configuration to {dst}. Restart audio services or log out/in to apply.")


if __name__ == "__main__":
    main()
