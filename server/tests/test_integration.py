"""End-to-end: seed a failing run, edit the past, fork, and watch it succeed.

This is the test that pins down the product's core claim, entirely offline via
the deterministic mock upstream.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from rewind.app import create_app
from rewind.store import EventStore
from rewind.upstream import MockUpstream


@pytest.fixture
def client() -> TestClient:
    app = create_app(store=EventStore(":memory:"), upstream=MockUpstream())
    return TestClient(app)


def _seat_result_seq(events: list[dict]) -> int:
    for e in events:
        if e["type"] == "tool_result" and e["payload"]["name"] == "get_seats":
            return e["seq"]
    raise AssertionError("no get_seats tool_result in timeline")


def test_original_demo_run_fails_at_booking(client: TestClient) -> None:
    seeded = client.post("/api/demo/seed").json()
    outcomes = [e for e in seeded["events"] if e["type"] == "outcome"]
    assert outcomes and outcomes[-1]["payload"]["status"] == "failed"
    # It failed specifically because get_seats returned nothing.
    seats = [e for e in seeded["events"] if e["type"] == "tool_result"
             and e["payload"]["name"] == "get_seats"]
    assert json.loads(seats[0]["payload"]["result"])["seats"] == []


def test_editing_seats_and_forking_succeeds(client: TestClient) -> None:
    seeded = client.post("/api/demo/seed").json()
    session_id = seeded["session"]["id"]
    seq = _seat_result_seq(seeded["events"])

    edited = {"name": "get_seats", "result": json.dumps({"flight": "UA100", "seats": ["12A", "12B"]})}
    forked = client.post(
        f"/api/sessions/{session_id}/fork",
        json={"fork_seq": seq, "edited_payload": edited},
    ).json()

    # The fork now books a seat and finishes successfully.
    assert forked["outcome"] == "done"
    tool_calls = [e for e in forked["events"] if e["type"] == "tool_call"]
    assert any(tc["payload"]["name"] == "book_seat" for tc in tool_calls)


def test_fork_leaves_parent_failed(client: TestClient) -> None:
    seeded = client.post("/api/demo/seed").json()
    session_id = seeded["session"]["id"]
    seq = _seat_result_seq(seeded["events"])
    client.post(
        f"/api/sessions/{session_id}/fork",
        json={"fork_seq": seq,
              "edited_payload": {"name": "get_seats", "result": json.dumps({"seats": ["1A"]})}},
    )
    # Re-reading the parent: still the original failing timeline.
    parent = client.get(f"/api/sessions/{session_id}/events").json()
    outcomes = [e for e in parent["events"] if e["type"] == "outcome"]
    assert outcomes[-1]["payload"]["status"] == "failed"


def test_proxy_records_into_named_session(client: TestClient) -> None:
    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Rewind-Session": "sess-xyz"},
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    events = client.get("/api/sessions/sess-xyz/events").json()["events"]
    assert [e["type"] for e in events] == ["request", "response"]


def test_fork_out_of_range_is_400(client: TestClient) -> None:
    seeded = client.post("/api/demo/seed").json()
    session_id = seeded["session"]["id"]
    resp = client.post(f"/api/sessions/{session_id}/fork", json={"fork_seq": 999})
    assert resp.status_code == 400


def test_events_for_unknown_session_is_404(client: TestClient) -> None:
    assert client.get("/api/sessions/nope/events").status_code == 404
