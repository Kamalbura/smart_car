"""ZeroMQ IPC helpers and topic constants."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import zmq
import zmq.asyncio


# Topics (always bytes for consistency)
TOPIC_WW_DETECTED = b"ww.detected"
TOPIC_STT = b"stt.transcription"
TOPIC_LLM_REQ = b"llm.request"
TOPIC_LLM_RESP = b"llm.response"
TOPIC_TTS = b"tts.speak"
TOPIC_VISN = b"visn.object"
TOPIC_VISN_FRAME = b"visn.frame"
TOPIC_VISN_CAPTURED = b"visn.capture"
TOPIC_NAV = b"nav.command"
TOPIC_CMD_PAUSE_VISION = b"cmd.pause.vision"
TOPIC_CMD_VISN_CAPTURE = b"cmd.visn.capture"
TOPIC_ESP = b"esp32.raw"
TOPIC_HEALTH = b"system.health"
TOPIC_CMD_LISTEN_START = b"cmd.listen.start"
TOPIC_CMD_LISTEN_STOP = b"cmd.listen.stop"
TOPIC_CMD_TTS_SPEAK = b"cmd.tts.speak"
TOPIC_CMD_VISION_MODE = b"cmd.vision.mode"

# Remote supervision topics
TOPIC_REMOTE_INTENT = b"remote.intent"
TOPIC_REMOTE_SESSION = b"remote.session"
TOPIC_REMOTE_EVENT = b"remote.event"

# Display state topics
TOPIC_DISPLAY_STATE = b"display.state"  # Current UI state (idle, listening, thinking, speaking)
TOPIC_DISPLAY_TEXT = b"display.text"    # Text to show on display
TOPIC_DISPLAY_NAV = b"display.nav"      # Navigation visualization


# How long close()/term() may block trying to flush queued messages.
# ZeroMQ's default is -1 (block forever), which makes every service hang on
# shutdown whenever its peer is down: systemd then falls through
# TimeoutStopSec to SIGKILL and skips all cleanup. A short non-zero linger
# still lets a final message drain on an orderly stop.
DEFAULT_LINGER_MS = int(os.environ.get("IPC_LINGER_MS", "250"))


def _ctx(async_mode: bool = False) -> zmq.Context:
    """Get ZMQ context (async or sync)."""
    if async_mode:
        return zmq.asyncio.Context.instance()
    return zmq.Context.instance()


def _ipc_addrs(config: Dict[str, Any]) -> tuple[str, str]:
    ipc_cfg = config.get("ipc", {}) if config else {}
    upstream = os.environ.get("IPC_UPSTREAM", ipc_cfg.get("upstream", "tcp://127.0.0.1:6010"))
    downstream = os.environ.get("IPC_DOWNSTREAM", ipc_cfg.get("downstream", "tcp://127.0.0.1:6011"))
    return upstream, downstream


def make_publisher(
    config: Dict[str, Any], 
    *, 
    channel: str = "upstream", 
    bind: bool = False,
    context: Optional[zmq.Context] = None
) -> zmq.Socket:
    """Create a PUB socket.
    
    Args:
        config: System configuration dict
        channel: 'upstream' or 'downstream'
        bind: If True, bind; otherwise connect
        context: Optional ZMQ context (for async usage)
    """
    upstream, downstream = _ipc_addrs(config)
    addr = upstream if channel == "upstream" else downstream
    ctx = context or _ctx()
    sock = ctx.socket(zmq.PUB)
    sock.setsockopt(zmq.LINGER, DEFAULT_LINGER_MS)
    (sock.bind if bind else sock.connect)(addr)
    return sock


def make_subscriber(
    config: Dict[str, Any],
    *,
    topic: bytes = b"",
    channel: str = "upstream",
    bind: bool = False,
    context: Optional[zmq.Context] = None
) -> zmq.Socket:
    """Create a SUB socket.
    
    Args:
        config: System configuration dict
        topic: Topic to subscribe to (empty = all)
        channel: 'upstream' or 'downstream'
        bind: If True, bind; otherwise connect
        context: Optional ZMQ context (for async usage)
    """
    upstream, downstream = _ipc_addrs(config)
    addr = upstream if channel == "upstream" else downstream
    ctx = context or _ctx()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.LINGER, DEFAULT_LINGER_MS)
    sock.setsockopt(zmq.SUBSCRIBE, topic)
    (sock.bind if bind else sock.connect)(addr)
    return sock


def publish_json(sock: zmq.Socket, topic: bytes, payload: Dict[str, Any]) -> None:
    """Publish a JSON payload on a topic."""
    sock.send_multipart([topic, json.dumps(payload).encode("utf-8")])
 # Copyright 2026 Kamal Bura
 # SPDX-License-Identifier: Apache-2.0
