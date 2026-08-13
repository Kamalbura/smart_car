"""Structural invariants of the IPC topology.

These are static checks over the source rather than runtime tests, because the
failure they guard against is invisible at runtime: the socket connects, the
logs look healthy, and no message is ever delivered.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO = SRC.parent

_MAKE_SUBSCRIBER = re.compile(r"make_subscriber\((?P<args>[^)]*)\)", re.S)


def _sources():
    for path in SRC.rglob("*.py"):
        if "tests" in path.parts:
            continue
        # ipc.py declares the helpers themselves; its `channel="upstream"`
        # default is a signature, not a call site.
        if path.name == "ipc.py":
            continue
        yield path


def test_no_module_subscribes_to_upstream_by_connecting():
    """A SUB that connects to the bound upstream SUB receives nothing, ever.

    `upstream` is bound by the orchestrator's SUB socket. A second SUB that
    connects to it forms a SUB-to-SUB pairing, which ZMTP refuses: it retries
    the handshake every few seconds forever and delivers zero messages, with no
    error surfaced to either side.

    Measured against libzmq 4.3.5 -- the bound SUB received 18/20 messages
    while a SUB connecting to the same address received 0/20.

    This silently disabled the entire world-context feature (every llm.request
    carried null vision and null sensors) and most of the remote interface's
    telemetry. To consume an upstream event from another process, add the topic
    to the orchestrator's `forwarded` set and subscribe downstream instead.
    """
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _MAKE_SUBSCRIBER.finditer(text):
            args = match.group("args")
            if '"upstream"' not in args and "'upstream'" not in args:
                continue
            if "bind=True" in args:
                continue  # the orchestrator itself, which is correct
            line = text[: match.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(REPO)}:{line}")

    assert not offenders, (
        "These SUB sockets connect to the bound upstream SUB and will receive "
        "nothing: " + ", ".join(offenders)
    )


def test_only_the_orchestrator_binds():
    """Two binders on one address means the second process crash-loops.

    systemd sets Restart=on-failure with StartLimitIntervalSec=0, so a second
    binder produces an unbounded restart loop rather than a visible failure.
    """
    binders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "bind=True" in text:
            binders.append(path.relative_to(REPO).as_posix())

    assert binders == ["src/core/orchestrator.py"], (
        f"unexpected binder(s): {binders}"
    )
