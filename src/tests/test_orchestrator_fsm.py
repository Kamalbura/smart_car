"""Unit tests for the orchestrator phase machine.

These run entirely in-process: config loading, IPC sockets and the world
context thread are patched out, so no ports are bound and no hardware, model
or network is required. Contrast with test_orchestrator_flow.py, which drives
a real ZeroMQ pair on fixed ports and cannot run twice concurrently.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Tuple
from unittest import mock

import pytest

from src.core import orchestrator as orch_mod
from src.core.ipc import TOPIC_CMD_LISTEN_START, TOPIC_NAV, TOPIC_TTS
from src.core.orchestrator import Orchestrator, Phase

CONFIG: Dict[str, Any] = {
    "ipc": {"upstream": "tcp://127.0.0.1:1", "downstream": "tcp://127.0.0.1:2"},
    "orchestrator": {"auto_trigger_enabled": False},
    "stt": {"timeout_seconds": 30.0, "min_confidence": 0.3},
    "llm": {"timeout_seconds": 45.0},
    "tts": {"timeout_seconds": 60.0},
    "vision": {"default_mode": "off"},
    "remote_interface": {"session_timeout_s": 15.0},
}


@pytest.fixture
def orch():
    """An Orchestrator with every external dependency mocked out."""
    with mock.patch.object(orch_mod, "load_config", return_value=CONFIG), mock.patch.object(
        orch_mod, "make_publisher"
    ), mock.patch.object(orch_mod, "make_subscriber"), mock.patch.object(
        orch_mod, "WorldContextAggregator"
    ) as world:
        world.return_value.get_snapshot.return_value = {}
        yield Orchestrator()


def published(o: Orchestrator) -> List[Tuple[bytes, Dict[str, Any]]]:
    """Decode everything the orchestrator sent on its command socket."""
    out = []
    for call in o.cmd_pub.send_multipart.call_args_list:
        topic, raw = call.args[0]
        out.append((topic, json.loads(raw)))
    return out


def nav_directions(o: Orchestrator) -> List[str]:
    return [p.get("direction") for topic, p in published(o) if topic == TOPIC_NAV]


# --------------------------------------------------------------------------
# Transition table
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "start,event,expected",
    [
        (Phase.IDLE, "wakeword", Phase.LISTENING),
        (Phase.IDLE, "manual_trigger", Phase.LISTENING),
        (Phase.LISTENING, "stt_valid", Phase.THINKING),
        (Phase.LISTENING, "stt_invalid", Phase.IDLE),
        (Phase.LISTENING, "stt_timeout", Phase.IDLE),
        (Phase.THINKING, "llm_with_speech", Phase.SPEAKING),
        (Phase.THINKING, "llm_no_speech", Phase.IDLE),
        (Phase.THINKING, "llm_timeout", Phase.IDLE),
        (Phase.SPEAKING, "tts_done", Phase.IDLE),
        (Phase.SPEAKING, "tts_timeout", Phase.IDLE),
        (Phase.THINKING, "health_error", Phase.ERROR),
        (Phase.ERROR, "health_ok", Phase.IDLE),
    ],
)
def test_legal_transitions(orch, start, event, expected):
    orch._phase = start
    assert orch._transition(event) is True
    assert orch.phase is expected


@pytest.mark.parametrize(
    "start,event",
    [
        (Phase.IDLE, "tts_done"),
        (Phase.IDLE, "stt_valid"),
        (Phase.SPEAKING, "wakeword"),
        (Phase.LISTENING, "llm_with_speech"),
        (Phase.THINKING, "nonsense_event"),
    ],
)
def test_illegal_transitions_are_refused(orch, start, event):
    orch._phase = start
    assert orch._transition(event) is False
    assert orch.phase is start


# --------------------------------------------------------------------------
# Phase watchdogs. Regression cover for the deadlock where THINKING and
# SPEAKING had no timeout: because every handler early-returns on an
# unexpected phase, a hung LLM or a TTS process that died before publishing
# `done` left the robot permanently deaf to the wakeword.
# --------------------------------------------------------------------------

def test_thinking_timeout_releases_fsm_and_stops_motors(orch):
    orch._phase = Phase.THINKING
    orch._phase_entered_ts = time.time() - (orch.llm_timeout_s + 1)

    orch._check_timeouts()

    assert orch.phase is Phase.IDLE
    assert "stop" in nav_directions(orch)


def test_speaking_timeout_releases_fsm_and_stops_motors(orch):
    orch._phase = Phase.SPEAKING
    orch._phase_entered_ts = time.time() - (orch.tts_timeout_s + 1)

    orch._check_timeouts()

    assert orch.phase is Phase.IDLE
    # _enter_speaking() commands the motors before TTS runs, so abandoning the
    # phase without a stop would leave the robot driving.
    assert nav_directions(orch)[-1] == "stop"


def test_wakeword_still_works_after_llm_timeout(orch):
    """The user-visible symptom: one hung LLM call used to deafen the robot."""
    orch._phase = Phase.THINKING
    orch._phase_entered_ts = time.time() - (orch.llm_timeout_s + 1)
    orch._check_timeouts()

    orch.on_wakeword({"keyword": "hey robo"})

    assert orch.phase is Phase.LISTENING
    assert any(topic == TOPIC_CMD_LISTEN_START for topic, _ in published(orch))


def test_phases_within_timeout_are_left_alone(orch):
    for phase in (Phase.LISTENING, Phase.THINKING, Phase.SPEAKING):
        orch._phase = phase
        orch._phase_entered_ts = time.time()
        orch._check_timeouts()
        assert orch.phase is phase


# --------------------------------------------------------------------------
# Input gating
# --------------------------------------------------------------------------

def test_low_confidence_transcript_is_rejected(orch):
    orch._phase = Phase.LISTENING
    orch.on_stt({"text": "move forward", "confidence": 0.1})

    assert orch.phase is Phase.IDLE
    spoken = [p for topic, p in published(orch) if topic == TOPIC_TTS]
    assert spoken and spoken[-1].get("notification") is True


def test_empty_transcript_is_rejected(orch):
    orch._phase = Phase.LISTENING
    orch.on_stt({"text": "   ", "confidence": 0.99})
    assert orch.phase is Phase.IDLE


def test_valid_transcript_reaches_thinking(orch):
    orch._phase = Phase.LISTENING
    orch.on_stt({"text": "move forward", "confidence": 0.9})
    assert orch.phase is Phase.THINKING


def test_obstacle_blocks_forward_motion(orch):
    orch._esp_obstacle = True
    orch._phase = Phase.THINKING

    orch.on_llm({"json": {"speak": "Going forward", "direction": "forward"}})

    assert "forward" not in nav_directions(orch)
    assert "stop" in nav_directions(orch)


def test_initial_nav_direction_is_a_valid_token(orch):
    """It is sent to the LLM as world state, so it must be in-vocabulary."""
    assert orch._last_nav_direction == orch._normalize_direction(orch._last_nav_direction)


# --------------------------------------------------------------------------
# Remote control authorisation
# --------------------------------------------------------------------------

def test_remote_intent_requires_active_session(orch):
    orch._remote_session_active = False
    orch.on_remote_intent({"source": "remote_app", "intent": "start_motion", "direction": "forward"})
    assert nav_directions(orch) == []


def test_remote_intent_requires_trusted_source(orch):
    orch._remote_session_active = True
    orch.on_remote_intent({"source": "somewhere_else", "intent": "start_motion", "direction": "forward"})
    assert nav_directions(orch) == []


def test_remote_intent_rejects_unknown_direction(orch):
    orch._remote_session_active = True
    orch.on_remote_intent({"source": "remote_app", "intent": "rotate", "direction": "sideways"})
    assert nav_directions(orch) == []


def test_remote_stop_is_accepted(orch):
    orch._remote_session_active = True
    orch.on_remote_intent({"source": "remote_app", "intent": "stop"})
    assert nav_directions(orch) == ["stop"]


def test_assistant_text_accepts_the_shape_the_android_app_actually_sends(orch):
    """The app nests text under `extras`; this handler read the top level.

    Every send was rejected as missing_text while the app displayed
    "accepted", because the HTTP layer 202s before the orchestrator sees the
    message.
    """
    orch._remote_session_active = True
    orch.on_remote_intent(
        {"source": "remote_app", "intent": "assistant_text", "extras": {"text": "what do you see"}}
    )
    assert orch.phase is Phase.THINKING
    assert orch._last_transcript == "what do you see"


def test_assistant_text_still_accepts_a_top_level_field(orch):
    orch._remote_session_active = True
    orch.on_remote_intent(
        {"source": "remote_app", "intent": "assistant_text", "text": "top level"}
    )
    assert orch._last_transcript == "top level"


def test_assistant_text_with_no_text_anywhere_is_rejected(orch):
    orch._remote_session_active = True
    orch.on_remote_intent({"source": "remote_app", "intent": "assistant_text", "extras": {}})
    assert orch.phase is Phase.IDLE
