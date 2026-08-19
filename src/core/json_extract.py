"""Tolerant JSON extraction from language-model output.

Models are asked for a bare JSON object and reliably return it wrapped in
prose, fenced in markdown, followed by a second object, or truncated by a
token cap. This replaces the naive slice that three runners each carried an
identical copy of::

    start = raw.find("{")
    end = raw.rfind("}")
    json.loads(raw[start : end + 1])

which mis-parsed every one of those cases -- most damagingly by spanning two
objects and discarding a perfectly good first one.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterator

_FENCE_PREFIXES = ("```json", "```JSON", "```")


def extract_json_object(raw: str) -> Dict[str, Any]:
    """Return the first complete JSON object in ``raw``, or ``{}``."""
    if not raw:
        return {}
    text = _strip_fences(raw.strip())

    # Fast path: the whole payload is already valid JSON.
    try:
        whole = json.loads(text)
    except ValueError:
        pass
    else:
        return whole if isinstance(whole, dict) else {}

    for candidate in _balanced_objects(text):
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _strip_fences(text: str) -> str:
    for prefix in _FENCE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _balanced_objects(text: str) -> Iterator[str]:
    """Yield substrings that look like complete top-level JSON objects.

    String literals and escapes are tracked so that a brace inside a string
    value cannot terminate the object early -- e.g. a reply of
    ``{"speak": "use {} braces"}`` must survive.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield text[start : index + 1]
                    start = -1
 # Copyright 2026 Kamal Bura
 # SPDX-License-Identifier: Apache-2.0
