#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_config
from src.stt.azure_speech_runner import _import_speech_sdk, _extract_confidence


def main() -> None:
    parser = argparse.ArgumentParser(description="One-off Azure STT test on a WAV file")
    parser.add_argument("--wav-path", required=True, help="Path to a WAV file to transcribe")
    parser.add_argument("--config", default="config/system.yaml", help="Path to system config")
    parser.add_argument("--region", help="Azure speech region override")
    parser.add_argument("--endpoint", help="Custom endpoint URL override")
    parser.add_argument("--language", help="Language/locale override (e.g. en-US)")
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    wav_path = Path(args.wav_path).expanduser()
    if not wav_path.exists():
        raise FileNotFoundError(wav_path)

    cfg = load_config(Path(args.config))
    stt_cfg = cfg.get("stt", {})
    engines_cfg = (stt_cfg.get("engines") or {}).get("azure_speech", {})

    # Prefer config, then environment variables
    speech_key = engines_cfg.get("key") or os.environ.get("AZURE_SPEECH_KEY")
    region = args.region or engines_cfg.get("region") or os.environ.get("AZURE_SPEECH_REGION")
    endpoint = args.endpoint or engines_cfg.get("endpoint") or os.environ.get("AZURE_SPEECH_ENDPOINT")
    language = args.language or engines_cfg.get("language") or stt_cfg.get("language", "en-US")

    min_conf = float(args.min_confidence)

    if not speech_key:
        raise RuntimeError(
            "Azure Speech key not configured (set stt.engines.azure_speech.key or AZURE_SPEECH_KEY)"
        )
    if not region and not endpoint:
        raise RuntimeError(
            "Azure Speech region/endpoint not configured (set stt.engines.azure_speech.region or AZURE_SPEECH_REGION/AZURE_SPEECH_ENDPOINT)"
        )

    speechsdk = _import_speech_sdk()
    if endpoint:
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, endpoint=endpoint)
    else:
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=region)
    speech_config.speech_recognition_language = language

    audio_config = speechsdk.audio.AudioConfig(filename=str(wav_path))
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    loop_start = time.time()
    result = recognizer.recognize_once_async().get()

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        text = (result.text or "").strip()
        confidence = _extract_confidence(speechsdk, result) or 0.9
        if not text:
            payload = {
                "timestamp": int(time.time()),
                "text": "",
                "confidence": 0.0,
                "language": language,
                "durations_ms": {"total": int((time.time() - loop_start) * 1000)},
                "error": "Empty transcription",
            }
            print(json.dumps(payload, indent=2))
            return
        if confidence < min_conf:
            payload = {
                "timestamp": int(time.time()),
                "text": text,
                "confidence": float(confidence),
                "language": language,
                "durations_ms": {"total": int((time.time() - loop_start) * 1000)},
                "warning": f"Confidence {confidence:.2f} below minimum {min_conf:.2f}",
            }
            print(json.dumps(payload, indent=2))
            return
        total_ms = int((time.time() - loop_start) * 1000)
        payload = {
            "timestamp": int(time.time()),
            "text": text,
            "confidence": float(confidence),
            "language": language,
            "durations_ms": {"total": total_ms},
        }
        print(json.dumps(payload, indent=2))
        if args.debug:
            print(f"[azure-stt-wav] Recognized in {total_ms} ms")
        return

    if result.reason == speechsdk.ResultReason.NoMatch:
        payload = {
            "timestamp": int(time.time()),
            "text": "",
            "confidence": 0.0,
            "language": language,
            "error": f"NoMatch: {result.no_match_details}",
        }
        print(json.dumps(payload, indent=2))
        return

    if result.reason == speechsdk.ResultReason.Canceled:
        cancellation = result.cancellation_details
        payload = {
            "timestamp": int(time.time()),
            "text": "",
            "confidence": 0.0,
            "language": language,
            "error": f"Canceled: {cancellation.reason}",
            "error_details": getattr(cancellation, "error_details", None),
        }
        print(json.dumps(payload, indent=2))
        return

    payload = {
        "timestamp": int(time.time()),
        "text": "",
        "confidence": 0.0,
        "language": language,
        "error": f"Unexpected result reason: {result.reason}",
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
