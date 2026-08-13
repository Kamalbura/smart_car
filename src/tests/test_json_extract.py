"""Cases the old find("{")/rfind("}") slice got wrong.

Each of these is reachable from a real model reply, and several were reachable
from the deployed configuration in particular: max_completion_tokens was low
enough that a JSON envelope wrapping a sentence of prose was routinely cut off
mid-string.
"""
from __future__ import annotations

from src.core.json_extract import extract_json_object


def test_plain_object():
    assert extract_json_object('{"speak": "hello", "direction": "stop"}') == {
        "speak": "hello",
        "direction": "stop",
    }


def test_object_wrapped_in_prose():
    raw = 'Sure! Here you go: {"speak": "hello"} Let me know if you need more.'
    assert extract_json_object(raw) == {"speak": "hello"}


def test_markdown_fenced_object():
    raw = '```json\n{"speak": "hello", "direction": "left"}\n```'
    assert extract_json_object(raw) == {"speak": "hello", "direction": "left"}


def test_two_objects_returns_the_first():
    # The old slice spanned from the first { to the LAST }, producing invalid
    # JSON and discarding a perfectly good first object.
    raw = '{"speak": "ok", "direction": "stop"} note: {"debug": 1}'
    assert extract_json_object(raw) == {"speak": "ok", "direction": "stop"}


def test_braces_inside_string_do_not_terminate_the_object():
    raw = '{"speak": "use {} braces", "direction": "stop"}'
    assert extract_json_object(raw) == {"speak": "use {} braces", "direction": "stop"}


def test_escaped_quote_inside_string():
    raw = '{"speak": "he said \\"hi\\"", "direction": "stop"}'
    assert extract_json_object(raw)["speak"] == 'he said "hi"'


def test_truncated_object_yields_empty_dict():
    # Guaranteed by any output token cap. Must NOT return a partial dict, and
    # must not raise.
    raw = '{"speak": "Turning left, then I will scan the'
    assert extract_json_object(raw) == {}


def test_top_level_array_yields_empty_dict():
    assert extract_json_object('["stop"]') == {}


def test_nested_object_is_preserved():
    raw = '{"speak": "ok", "meta": {"conf": 0.9}}'
    assert extract_json_object(raw) == {"speak": "ok", "meta": {"conf": 0.9}}


def test_no_json_at_all():
    assert extract_json_object("I'm not sure what you mean.") == {}


def test_empty_and_whitespace():
    assert extract_json_object("") == {}
    assert extract_json_object("   \n ") == {}
