"""End-to-end orchestrator flow over real ZeroMQ sockets.

Complements test_orchestrator_fsm.py, which mocks the transport and covers the
state table exhaustively. This one is deliberately slower and less thorough: it
proves messages actually serialise, route and arrive, which mocks cannot.

It binds real ports (6210/6211), so it cannot run concurrently with itself.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

import pytest
import zmq

from src.core.ipc import (
    TOPIC_CMD_LISTEN_START,
    TOPIC_CMD_LISTEN_STOP,
    TOPIC_CMD_PAUSE_VISION,
    TOPIC_DISPLAY_STATE,
    TOPIC_LLM_REQ,
    TOPIC_LLM_RESP,
    TOPIC_STT,
    TOPIC_TTS,
    TOPIC_WW_DETECTED,
)
from src.core.orchestrator import Orchestrator, VisionMode

UPSTREAM = "tcp://127.0.0.1:6210"
DOWNSTREAM = "tcp://127.0.0.1:6211"

_orchestrator: Optional[Orchestrator] = None
_startup_error: Optional[BaseException] = None


def _run_orchestrator() -> None:
    """Run the orchestrator, recording why it died rather than swallowing it.

    The previous version caught bare Exception and passed, so a crash during
    startup surfaced only as a five-second timeout and a misleading assertion
    about missing messages.
    """
    global _orchestrator, _startup_error
    try:
        _orchestrator = Orchestrator()
        _orchestrator.run()
    except BaseException as exc:  # noqa: BLE001 - reported by the test below
        _startup_error = exc


@pytest.fixture(scope="module")
def bus():
    os.environ["IPC_UPSTREAM"] = UPSTREAM
    os.environ["IPC_DOWNSTREAM"] = DOWNSTREAM
    os.environ["STT_ENGINE_DISABLED"] = "1"

    ctx = zmq.Context.instance()
    events = ctx.socket(zmq.PUB)
    events.connect(UPSTREAM)
    commands = ctx.socket(zmq.SUB)
    commands.connect(DOWNSTREAM)
    commands.setsockopt(zmq.SUBSCRIBE, b"")

    threading.Thread(target=_run_orchestrator, daemon=True).start()
    time.sleep(0.5)  # let the orchestrator bind before anything is published

    if _startup_error is not None:
        pytest.fail(f"orchestrator failed to start: {_startup_error!r}")

    yield events, commands

    events.close(0)
    commands.close(0)


def _send(pub, topic: bytes, payload: dict) -> None:
    pub.send_multipart([topic, json.dumps(payload).encode("utf-8")])


def _collect(sub, wanted: set, timeout_s: float = 5.0) -> dict:
    """Gather one payload per wanted topic, or as many as arrive in time."""
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)
    seen: dict = {}
    deadline = time.time() + timeout_s
    while time.time() < deadline and not wanted.issubset(seen.keys()):
        if dict(poller.poll(200)).get(sub):
            topic, data = sub.recv_multipart()
            seen.setdefault(topic, json.loads(data))
    return seen


def test_full_turn_wakeword_to_idle(bus):
    events, commands = bus

    # 1. Wakeword starts listening.
    _send(events, TOPIC_WW_DETECTED, {"keyword": "robo", "confidence": 0.99})
    seen = _collect(commands, {TOPIC_CMD_LISTEN_START})
    assert TOPIC_CMD_LISTEN_START in seen, "no listen.start after wakeword"
    assert seen[TOPIC_CMD_LISTEN_START].get("start") is True

    # cmd.pause.vision is deliberately NOT asserted here. _enter_listening()
    # emits it only when vision_mode != OFF, and the shipped config sets
    # vision.default_mode: off, so with the default configuration no pause is
    # published at all. Asserting it unconditionally is what made this test
    # fail against a perfectly correct orchestrator.
    if _orchestrator is not None and _orchestrator.vision_mode != VisionMode.OFF:
        assert TOPIC_CMD_PAUSE_VISION in seen

    # 2. A confident transcript reaches the LLM and stops listening.
    _send(events, TOPIC_STT, {"text": "Move forward", "confidence": 0.91})
    seen = _collect(commands, {TOPIC_LLM_REQ, TOPIC_CMD_LISTEN_STOP})
    assert seen.get(TOPIC_LLM_REQ, {}).get("text") == "Move forward"
    assert seen.get(TOPIC_CMD_LISTEN_STOP, {}).get("stop") is True
    # Correlation id must be present, or a late reply could answer a later turn.
    assert seen[TOPIC_LLM_REQ].get("request_id")

    # 3. The reply is spoken.
    _send(events, TOPIC_LLM_RESP, {"text": "Moving forward"})
    seen = _collect(commands, {TOPIC_TTS})
    assert seen.get(TOPIC_TTS, {}).get("text") == "Moving forward"

    # 4. Completion returns the machine to IDLE.
    #
    # Vision is NOT expected to resume: _enter_idle() manages the vision
    # lifecycle explicitly and does not auto-resume, so the old
    # "Vision did not resume after TTS completion" assertion described a
    # behaviour the orchestrator no longer has.
    _send(events, TOPIC_TTS, {"done": True})
    deadline = time.time() + 5.0
    poller = zmq.Poller()
    poller.register(commands, zmq.POLLIN)
    back_to_idle = False
    while time.time() < deadline and not back_to_idle:
        if dict(poller.poll(200)).get(commands):
            topic, data = commands.recv_multipart()
            if topic == TOPIC_DISPLAY_STATE:
                if json.loads(data).get("phase") == "IDLE":
                    back_to_idle = True
    assert back_to_idle, "orchestrator did not return to IDLE after tts done"
