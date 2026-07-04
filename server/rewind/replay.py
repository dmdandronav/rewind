"""Deterministic replay of a forked timeline.

When a session is forked and replayed, REWIND must decide, for each model call
the agent makes, whether it can reuse the response the *parent* recorded or must
go to the upstream fresh. The rule:

    Walk the fork and the parent in lockstep by seq. As long as the fork's
    REQUEST at a given step fingerprints identically to the parent's REQUEST at
    that step, the parent's recorded RESPONSE is byte-for-byte valid — reuse it.
    The first step whose fingerprint differs is the *divergence point*; from
    there on every call goes live.

This is what makes replay honest with a real, nondeterministic model: the
unchanged prefix is served from the log (so it can't drift), and only the
consequences of your edit are recomputed. With the deterministic
:class:`~rewind.upstream.MockUpstream`, "live" is itself reproducible, so the
whole thing runs offline.

:class:`ReplayController` is deliberately pure/stateless-per-call so it can be
unit-tested without a server or a live agent.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Event, EventType
from .store import EventStore


@dataclass
class ReplayDecision:
    """Outcome of asking "should this request reuse a recorded response?"."""

    reuse: bool
    #: The recorded response payload to serve, when ``reuse`` is True.
    recorded_response: dict | None = None
    #: True once we've passed the divergence point (all further calls are live).
    diverged: bool = False


class ReplayController:
    """Decides reuse-vs-live for each model call during a fork replay.

    Construct one per fork session. Feed it each outgoing request (in order) via
    :meth:`decide`; it compares against the parent timeline and returns whether
    to serve the recorded response.
    """

    def __init__(self, store: EventStore, parent_session_id: str) -> None:
        self._parent_requests = _request_response_pairs(store, parent_session_id)
        self._call_index = 0
        self._diverged = False

    def decide(self, request_fingerprint: str) -> ReplayDecision:
        """Decide how to serve the agent's next model call.

        Called once per REQUEST the replaying agent makes, in order.
        """
        idx = self._call_index
        self._call_index += 1

        if self._diverged or idx >= len(self._parent_requests):
            # Past divergence, or the fork ran longer than the parent → live.
            self._diverged = True
            return ReplayDecision(reuse=False, diverged=True)

        parent_fp, parent_response = self._parent_requests[idx]
        if parent_fp == request_fingerprint:
            return ReplayDecision(reuse=True, recorded_response=parent_response)

        # First mismatch: this is the divergence point. Go live from here.
        self._diverged = True
        return ReplayDecision(reuse=False, diverged=True)


def _request_response_pairs(
    store: EventStore, session_id: str
) -> list[tuple[str | None, dict]]:
    """Extract ordered (request_fingerprint, response_payload) pairs.

    Each model call in a timeline is a REQUEST event immediately followed (in
    seq order, allowing tool events in between) by the RESPONSE it produced.
    """
    events = store.get_events(session_id)
    pairs: list[tuple[str | None, dict]] = []
    pending_fp: str | None = None
    pending_seen = False
    for ev in events:
        if ev.type == EventType.REQUEST:
            pending_fp = ev.request_fingerprint
            pending_seen = True
        elif ev.type == EventType.RESPONSE and pending_seen:
            pairs.append((pending_fp, ev.payload))
            pending_seen = False
            pending_fp = None
    return pairs
