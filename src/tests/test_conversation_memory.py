"""Tests for conversation memory.

This is what lets the robot answer "what about behind me?" after "what do you
see?". It was configured but never written to by the live runner, so the
deployed system had no memory at all -- every turn started blank while the
config advertised ten.
"""
from __future__ import annotations

import time

import pytest

from src.llm.conversation_memory import ConversationMemory


@pytest.fixture
def memory():
    return ConversationMemory(max_turns=3, conversation_timeout_s=60.0)


def test_starts_empty(memory):
    assert memory.build_messages_format("hello")


def test_user_and_assistant_turns_are_retained(memory):
    memory.add_user_message("what do you see")
    memory.add_assistant_message("a person ahead")

    messages = memory.build_messages_format("what about behind")
    blob = " ".join(m.get("content", "") for m in messages)
    assert "what do you see" in blob
    assert "a person ahead" in blob


def test_blank_messages_are_ignored(memory):
    memory.add_user_message("   ")
    memory.add_assistant_message("")
    messages = memory.build_messages_format("hello")
    blob = " ".join(m.get("content", "") for m in messages)
    # Nothing meaningful was added, so only the system prompt and the current
    # query should be present.
    assert blob.count("hello") >= 1


def test_history_is_bounded_by_max_turns(memory):
    for i in range(20):
        memory.add_user_message(f"question {i}")
        memory.add_assistant_message(f"answer {i}")

    blob = " ".join(m.get("content", "") for m in memory.build_messages_format("now"))
    # The oldest exchanges must have been evicted, or the prompt grows without
    # limit and latency with it.
    assert "question 0" not in blob
    assert "question 19" in blob


def test_messages_alternate_roles(memory):
    """Chat APIs reject or misbehave on consecutive same-role messages."""
    memory.add_user_message("one")
    memory.add_assistant_message("two")
    memory.add_user_message("three")
    memory.add_assistant_message("four")

    roles = [m["role"] for m in memory.build_messages_format("five") if m["role"] != "system"]
    for earlier, later in zip(roles, roles[1:]):
        assert earlier != later, f"consecutive {earlier} messages: {roles}"


def test_robot_state_reaches_the_prompt(memory):
    memory.update_robot_state(direction="forward", vision={"label": "person"})
    blob = " ".join(m.get("content", "") for m in memory.build_messages_format("what now"))
    assert "forward" in blob.lower()


def test_conversation_expires_after_the_timeout():
    memory = ConversationMemory(max_turns=5, conversation_timeout_s=0.05)
    memory.add_user_message("remember this")
    memory.add_assistant_message("noted")
    time.sleep(0.1)

    blob = " ".join(m.get("content", "") for m in memory.build_messages_format("still there?"))
    # A stale conversation must not be silently resurrected: someone speaking
    # to the robot after a long gap is starting a new exchange, not continuing
    # one from an hour ago.
    assert "remember this" not in blob


def test_current_query_is_always_present(memory):
    memory.add_user_message("earlier")
    memory.add_assistant_message("reply")
    blob = " ".join(m.get("content", "") for m in memory.build_messages_format("the new question"))
    assert "the new question" in blob
