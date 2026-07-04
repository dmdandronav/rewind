"""Tests for the append-only event store and fork semantics."""

from __future__ import annotations

import pytest

from rewind.models import EventType
from rewind.store import EventStore


@pytest.fixture
def store() -> EventStore:
    return EventStore(":memory:")


def test_append_assigns_gapless_seqs(store: EventStore) -> None:
    s = store.create_session("run")
    for i in range(3):
        store.append_event(s.id, EventType.REQUEST, {"i": i})
    seqs = [e.seq for e in store.get_events(s.id)]
    assert seqs == [0, 1, 2]


def test_append_to_unknown_session_raises(store: EventStore) -> None:
    with pytest.raises(KeyError):
        store.append_event("nope", EventType.REQUEST, {})


def test_events_returned_in_seq_order(store: EventStore) -> None:
    s = store.create_session("run")
    store.append_event(s.id, EventType.REQUEST, {"step": "a"})
    store.append_event(s.id, EventType.RESPONSE, {"step": "b"})
    types = [e.type for e in store.get_events(s.id)]
    assert types == [EventType.REQUEST, EventType.RESPONSE]


def test_fork_copies_prefix_and_leaves_parent_untouched(store: EventStore) -> None:
    s = store.create_session("original")
    for i in range(5):
        store.append_event(s.id, EventType.REQUEST, {"i": i})

    fork = store.fork_session(s.id, fork_seq=2)

    # Fork has exactly the prefix 0..2.
    assert [e.seq for e in store.get_events(fork.id)] == [0, 1, 2]
    # Parent is fully intact.
    assert [e.seq for e in store.get_events(s.id)] == [0, 1, 2, 3, 4]
    assert fork.parent_session_id == s.id
    assert fork.forked_at_seq == 2


def test_fork_applies_edit_at_fork_point_only(store: EventStore) -> None:
    s = store.create_session("original")
    for i in range(4):
        store.append_event(s.id, EventType.TOOL_RESULT, {"result": i})

    fork = store.fork_session(
        s.id, fork_seq=1, edited_payload={"result": "EDITED"}
    )

    fork_events = store.get_events(fork.id)
    assert fork_events[0].payload == {"result": 0}       # untouched
    assert fork_events[1].payload == {"result": "EDITED"}  # the edit
    # Parent's seq 1 is unchanged — append-only guarantee.
    assert store.get_events(s.id)[1].payload == {"result": 1}


def test_fork_out_of_range_raises(store: EventStore) -> None:
    s = store.create_session("original")
    store.append_event(s.id, EventType.REQUEST, {})
    with pytest.raises(IndexError):
        store.fork_session(s.id, fork_seq=9)


def test_immutability_with_payload_returns_new_instance(store: EventStore) -> None:
    s = store.create_session("run")
    ev = store.append_event(s.id, EventType.REQUEST, {"a": 1})
    updated = ev.with_payload({"a": 2})
    assert ev.payload == {"a": 1}         # original frozen instance unchanged
    assert updated.payload == {"a": 2}
    assert updated.id == ev.id
