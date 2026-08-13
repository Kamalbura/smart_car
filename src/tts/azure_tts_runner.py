"""Azure Text-to-Speech runner

Subscribes to TOPIC_TTS on the downstream bus and speaks using Azure Speech
Service. Defaults to Indian male voice `hi-IN-NeerajNeural`. Minimal
dependencies: `azure-cognitiveservices-speech` and an audio playback tool if
using local playback (aplay).

Environment:
  - AZURE_SPEECH_KEY: Azure Speech subscription key
  - AZURE_SPEECH_REGION: Azure region (e.g., centralindia)

Config (optional overrides via config/system.yaml under `tts.azure`):
  tts:
    azure:
      voice: hi-IN-NeerajNeural
      region: ${ENV:AZURE_SPEECH_REGION}
      key: ${ENV:AZURE_SPEECH_KEY}
      output: speakers   # speakers|wav
      wav_path: ./run/tts_out.wav

Usage:
  python -m src.tts.azure_tts_runner
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import azure.cognitiveservices.speech as speechsdk  # type: ignore
except Exception as exc:  # pragma: no cover
    speechsdk = None  # type: ignore

from src.core.config_loader import load_config
from src.core.ipc import TOPIC_TTS, make_subscriber, make_publisher, publish_json
from src.core.logging_setup import get_logger


def _get_tts_cfg(cfg: dict) -> dict:
    tts_cfg = cfg.get("tts", {}) or {}
    azure_cfg = tts_cfg.get("azure", {}) or {}
    return {
        "voice": azure_cfg.get("voice", "hi-IN-NeerajNeural"),
        "region": azure_cfg.get("region") or cfg.get("stt", {}).get("engines", {}).get("azure_speech", {}).get("region"),
        "key": azure_cfg.get("key") or cfg.get("stt", {}).get("engines", {}).get("azure_speech", {}).get("key"),
        "output": azure_cfg.get("output", "speakers"),  # speakers|wav
        "wav_path": azure_cfg.get("wav_path", "run/tts_out.wav"),
    }


def _speak_text_speakers(text: str, voice: str, region: str, key: str, logger) -> bool:
    if speechsdk is None:
        logger.error("azure-cognitiveservices-speech not installed")
        return False
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice
    audio_config = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    try:
        result = synthesizer.speak_text_async(text).get()
    except Exception as exc:
        logger.error("Azure TTS exception: %s", exc)
        return False
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return True
    if result.reason == speechsdk.ResultReason.Canceled:
        cancellation = result.cancellation_details
        logger.error("Azure TTS canceled: %s", cancellation.reason)
        if cancellation.error_details:
            logger.error("Azure TTS error details: %s", cancellation.error_details)
        return False
    logger.error("Azure TTS failed: %s", getattr(result, "error_details", "unknown"))
    return False


def _speak_text_wav(text: str, voice: str, region: str, key: str, wav_path: Path, logger) -> bool:
    if speechsdk is None:
        logger.error("azure-cognitiveservices-speech not installed")
        return False
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice
    audio_config = speechsdk.audio.AudioOutputConfig(filename=str(wav_path))
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    try:
        result = synthesizer.speak_text_async(text).get()
    except Exception as exc:
        logger.error("Azure TTS exception: %s", exc)
        return False
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return True
    if result.reason == speechsdk.ResultReason.Canceled:
        cancellation = result.cancellation_details
        logger.error("Azure TTS canceled: %s", cancellation.reason)
        if cancellation.error_details:
            logger.error("Azure TTS error details: %s", cancellation.error_details)
        return False
    logger.error("Azure TTS failed: %s", getattr(result, "error_details", "unknown"))
    return False


def run() -> None:
    cfg = load_config(Path("config/system.yaml"))
    logger = get_logger("tts.azure", Path(cfg.get("logs", {}).get("directory", "logs")))
    tts = _get_tts_cfg(cfg)

    voice = tts.get("voice")
    region = tts.get("region")
    key = tts.get("key")
    output = (tts.get("output") or "speakers").lower()
    wav_path = Path(tts.get("wav_path", "run/tts_out.wav"))

    if not key or not region:
        logger.error("Azure Speech credentials missing: set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION or configure tts.azure in system.yaml")
        sys.exit(1)

    sub = make_subscriber(cfg, topic=TOPIC_TTS, channel="downstream")
    pub = make_publisher(cfg, channel="upstream")
    logger.info("Azure TTS listening on %s (voice=%s, output=%s)", TOPIC_TTS, voice, output)

    while True:
        try:
            _topic, raw = sub.recv_multipart()
            msg = json.loads(raw)
            text = str(msg.get("text", "")).strip()
            if not text:
                continue
        except Exception as e:  # noqa: BLE001
            logger.error("Invalid TTS payload: %s", e)
            continue

        logger.info("Speaking %d chars via Azure (%s)", len(text), voice)
        ok = False
        if output == "speakers":
            ok = _speak_text_speakers(text, voice, region, key, logger)
        elif output == "wav":
            ok = _speak_text_wav(text, voice, region, key, wav_path, logger)
        else:
            logger.error("Unsupported output mode: %s", output)

        publish_json(pub, TOPIC_TTS, {"done": bool(ok)})


if __name__ == "__main__":
    run()
