from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import List

import numpy as np
import zmq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config_loader import load_config  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Record audio via AudioManager at 16 kHz into a WAV file")
    ap.add_argument("--config", default="config/system.yaml", help="Path to system config YAML")
    ap.add_argument("--seconds", type=float, default=5.0, help="Duration to record in seconds")
    ap.add_argument("--chunk-ms", type=int, default=100, help="Chunk size to request from AudioManager in ms")
    ap.add_argument("--output", default="am_test_16k.wav", help="Output WAV path")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    audio_cfg = cfg.get("audio", {}) or {}
    endpoint = audio_cfg.get("control_endpoint", "tcp://127.0.0.1:6020")

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.REQ)
    sock.connect(endpoint)

    session_id = f"diag-{int(time.time() * 1000)}"

    def rpc(obj: dict) -> dict:
        sock.send_json(obj)
        return sock.recv_json()

    resp = rpc(
        {
            "action": "start_session",
            "session_id": session_id,
            "mode": "stt",
            "target_rate": 16000,
            "channels": 1,
            "max_duration_s": float(args.seconds),
            "priority": 5,
        }
    )
    if not resp.get("ok"):
        print(f"start_session failed: {json.dumps(resp)}", file=sys.stderr)
        return

    print(f"Started AudioManager session {session_id} at 16 kHz for {args.seconds:.1f}s (endpoint={endpoint})")

    chunks: List[np.ndarray] = []
    start = time.time()
    try:
        while True:
            now = time.time()
            if now - start >= args.seconds:
                break
            resp = rpc(
                {
                    "action": "read_chunk",
                    "session_id": session_id,
                    "frames_ms": int(args.chunk_ms),
                }
            )
            if not resp.get("ok"):
                reason = resp.get("reason")
                if reason not in {"no_data", "invalid_frames_ms"}:
                    print(f"read_chunk not ok: {json.dumps(resp)}", file=sys.stderr)
                time.sleep(args.chunk_ms / 1000.0)
                continue
            data_b64 = resp.get("data_b64")
            if not data_b64:
                time.sleep(args.chunk_ms / 1000.0)
                continue
            try:
                pcm = base64.b64decode(data_b64)
            except Exception as exc:
                print(f"base64 decode failed: {exc}", file=sys.stderr)
                break
            samples = np.frombuffer(pcm, dtype=np.int16)
            if samples.size:
                chunks.append(samples)
    finally:
        try:
            rpc({"action": "stop_session", "session_id": session_id})
        except Exception:
            pass

    if not chunks:
        print("No audio captured from AudioManager (all chunks empty)", file=sys.stderr)
        return

    samples_all = np.concatenate(chunks)
    duration = samples_all.size / 16000.0
    peak = float(np.max(np.abs(samples_all))) if samples_all.size else 0.0
    print(f"Captured {samples_all.size} samples (~{duration:.2f}s) peak={peak:.0f}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    import wave

    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(samples_all.astype("<i2").tobytes())

    print(f"Wrote {out_path} (16 kHz mono)")


if __name__ == "__main__":
    main()
