"""Core domain types for the REWIND event log.

An agent run is modeled as an ordered sequence of immutable *events*. Each event
is one observable step in the loop — a request the agent sent to the model, the
response that came back, or a tool call/result the agent recorded. Events are
append-only: nothing is ever mutated in place. Editing history is done by
*forking* a session into a new one (see ``store.fork_session``), which is what
keeps replays honest.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """The kind of step an event represents."""

    #: The agent sent a completion request to the model (payload = request body).
    REQUEST = "request"
    #: The model returned a completion (payload = response body).
    RESPONSE = "response"
    #: The agent invoked a tool (payload = {"name", "arguments"}).
    TOOL_CALL = "tool_call"
    #: A tool produced a result the agent fed back in (payload = {"name", "result"}).
    TOOL_RESULT = "tool_result"
    #: A terminal marker for the run (payload = {"status": "done"|"failed", ...}).
    OUTCOME = "outcome"


@dataclass(frozen=True)
class Event:
    """One immutable step in an agent timeline.

    ``seq`` is the 0-based position within a session and is unique per session.
    ``request_fingerprint`` is set on REQUEST events and is what deterministic
    replay compares against to decide whether a recorded response can be reused
    (see ``store.fork_session`` / ``replay``).
    """

    id: str
    session_id: str
    seq: int
    type: EventType
    payload: dict[str, Any]
    ts: float = field(default_factory=time.time)
    request_fingerprint: str | None = None

    def with_payload(self, payload: dict[str, Any]) -> "Event":
        """Return a copy with a new payload (used when applying an edit on fork).

        The original is never mutated — this returns a new frozen instance, which
        is the whole point of an append-only log.
        """
        return Event(
            id=self.id,
            session_id=self.session_id,
            seq=self.seq,
            type=self.type,
            payload=payload,
            ts=self.ts,
            request_fingerprint=self.request_fingerprint,
        )


@dataclass(frozen=True)
class Session:
    """A single agent run (or a fork of one)."""

    id: str
    label: str
    created_at: float = field(default_factory=time.time)
    #: For forks: the session this was branched from, else None.
    parent_session_id: str | None = None
    #: For forks: the seq at which the branch diverged, else None.
    forked_at_seq: int | None = None
