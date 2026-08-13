#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <voice-key> [text...]" >&2
    echo "Example: $0 en_US-amy-medium \"Hello from Amy\"" >&2
    exit 1
fi

VOICE_KEY="$1"
shift || true

if [[ $# -gt 0 ]]; then
    TEXT="$*"
else
    TEXT="This is a Piper test for voice ${VOICE_KEY}."
fi

MODEL_PATH="/opt/models/piper/${VOICE_KEY}.onnx"
if [[ ! -f "${MODEL_PATH}" ]]; then
    echo "Model not found: ${MODEL_PATH}" >&2
    exit 2
fi

PIPER_BIN="${PIPER_BIN:-/home/dev/project_root/.venvs/ttse/bin/piper}"
if [[ ! -x "$PIPER_BIN" ]]; then
    if command -v piper >/dev/null 2>&1; then
        PIPER_BIN="$(command -v piper)"
    else
        echo "piper binary not found. Install Piper or set PIPER_BIN to the desired executable." >&2
        exit 3
    fi
fi

APLAY_BIN="${APLAY_BIN:-aplay}"
if ! command -v "${APLAY_BIN}" >/dev/null 2>&1; then
    echo "${APLAY_BIN} not found. Install alsa-utils or set APLAY_BIN to the playback command." >&2
    exit 4
fi
APLAY_DEVICE="${APLAY_DEVICE:-}"

TMP_WAV="$(mktemp --suffix=.wav)"
cleanup() {
    rm -f "${TMP_WAV}"
}
trap cleanup EXIT INT TERM

echo "Saying: ${TEXT}" >&2

"${PIPER_BIN}" -m "${MODEL_PATH}" -f "${TMP_WAV}" <<<"${TEXT}"
if [[ -n "${APLAY_DEVICE}" ]]; then
    "${APLAY_BIN}" -D "${APLAY_DEVICE}" -q "${TMP_WAV}"
else
    "${APLAY_BIN}" -q "${TMP_WAV}"
fi
