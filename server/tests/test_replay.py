"""Tests for the deterministic replay controller."""

from __future__ import annotations

from rewind.fingerprint import fingerprint_request
from rewind.models import EventType
from rewind.replay import ReplayController
from rewind.store import EventStore


def _record_call(store: EventStore, session_id: str, request: dict, response: dict) -> None:
    """Record one model call (REQUEST + RESPONSE) into a session."""
    store.append_event(
        session_id,
        EventType.REQUEST,
        request,
        request_fingerprint=fingerprint_request(request),
    )
    store.append_event(session_id, EventType.RESPONSE, response)


def test_identical_prefix_is_fully_reused() -> None:
    store = EventStore(":memory:")
    parent = store.create_session("parent")
    r1 = {"messages": [{"role": "user", "content": "a"}]}
    r2 = {"messages": [{"role": "user", "content": "b"}]}
    _record_call(store, parent.id, r1, {"choices": [{"message": {"content": "resp1"}}]})
    _record_call(store, parent.id, r2, {"choices": [{"message": {"content": "resp2"}}]})

    ctrl = ReplayController(store, parent.id)
    d1 = ctrl.decide(fingerprint_request(r1))
    d2 = ctrl.decide(fingerprint_request(r2))

    assert d1.reuse and d1.recorded_response["choices"][0]["message"]["content"] == "resp1"
    assert d2.reuse and d2.recorded_response["choices"][0]["message"]["content"] == "resp2"


def test_divergence_stops_reuse_from_that_point() -> None:
    store = EventStore(":memory:")
    parent = store.create_session("parent")
    r1 = {"messages": [{"role": "user", "content": "a"}]}
    r2 = {"messages": [{"role": "user", "content": "b"}]}
    _record_call(store, parent.id, r1, {"choices": [{"message": {"content": "resp1"}}]})
    _record_call(store, parent.id, r2, {"choices": [{"message": {"content": "resp2"}}]})

    ctrl = ReplayController(store, parent.id)
    # First call matches → reuse.
    assert ctrl.decide(fingerprint_request(r1)).reuse is True
    # Second call has an edited/different request → diverge, go live.
    edited = {"messages": [{"role": "user", "content": "EDITED"}]}
    d2 = ctrl.decide(fingerprint_request(edited))
    assert d2.reuse is False and d2.diverged is True


def test_everything_after_divergence_is_live_even_if_it_matches() -> None:
    store = EventStore(":memory:")
    parent = store.create_session("parent")
    r1 = {"messages": [{"role": "user", "content": "a"}]}
    r2 = {"messages": [{"role": "user", "content": "b"}]}
    r3 = {"messages": [{"role": "user", "content": "c"}]}
    for r in (r1, r2, r3):
        _record_call(store, parent.id, r, {"choices": [{"message": {"content": "x"}}]})

    ctrl = ReplayController(store, parent.id)
    ctrl.decide(fingerprint_request(r1))                      # reuse
    ctrl.decide(fingerprint_request({"messages": [{"x": 1}]}))  # diverge
    # Even though r3 would match the parent, once diverged we never reuse again.
    assert ctrl.decide(fingerprint_request(r3)).reuse is False


def test_fork_longer_than_parent_goes_live() -> None:
    store = EventStore(":memory:")
    parent = store.create_session("parent")
    r1 = {"messages": [{"role": "user", "content": "a"}]}
    _record_call(store, parent.id, r1, {"choices": [{"message": {"content": "resp1"}}]})

    ctrl = ReplayController(store, parent.id)
    assert ctrl.decide(fingerprint_request(r1)).reuse is True
    # Parent had only one call; the fork's second call has nothing to reuse.
    assert ctrl.decide(fingerprint_request(r1)).reuse is False
