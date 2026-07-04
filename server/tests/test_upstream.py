"""Tests for the deterministic mock upstream (the demo 'model')."""

from __future__ import annotations

import json

from rewind.upstream import MockUpstream


def _tool_msg(name: str, payload: dict) -> dict:
    return {"role": "tool", "name": name, "content": json.dumps(payload)}


def test_cold_start_searches_flights() -> None:
    up = MockUpstream()
    resp = up.complete({"messages": [{"role": "user", "content": "book me SFO->JFK"}]})
    call = resp["choices"][0]["message"]["tool_calls"][0]["function"]
    assert call["name"] == "search_flights"


def test_after_search_gets_seats_for_first_flight() -> None:
    up = MockUpstream()
    msgs = [
        {"role": "user", "content": "book me a flight"},
        _tool_msg("search_flights", {"flights": ["UA100", "UA200"]}),
    ]
    resp = up.complete({"messages": msgs})
    call = resp["choices"][0]["message"]["tool_calls"][0]["function"]
    assert call["name"] == "get_seats"
    assert json.loads(call["arguments"])["flight"] == "UA100"


def test_no_seats_fails() -> None:
    up = MockUpstream()
    msgs = [
        {"role": "user", "content": "book"},
        _tool_msg("search_flights", {"flights": ["UA100"]}),
        _tool_msg("get_seats", {"seats": []}),
    ]
    resp = up.complete({"messages": msgs})
    assert "FAILED" in resp["choices"][0]["message"]["content"]


def test_seats_available_books_first_seat() -> None:
    up = MockUpstream()
    msgs = [
        {"role": "user", "content": "book"},
        _tool_msg("search_flights", {"flights": ["UA100"]}),
        _tool_msg("get_seats", {"seats": ["12A", "12B"]}),
    ]
    resp = up.complete({"messages": msgs})
    call = resp["choices"][0]["message"]["tool_calls"][0]["function"]
    assert call["name"] == "book_seat"
    assert json.loads(call["arguments"])["seat"] == "12A"


def test_deterministic_same_input_same_output() -> None:
    up = MockUpstream()
    req = {"messages": [{"role": "user", "content": "hello"}]}
    assert up.complete(req) == up.complete(req)


def test_the_edit_flips_failure_to_success() -> None:
    """The core demo claim: editing the seat result changes the next action."""
    up = MockUpstream()
    base = [
        {"role": "user", "content": "book"},
        _tool_msg("search_flights", {"flights": ["UA100"]}),
    ]
    failed = up.complete({"messages": base + [_tool_msg("get_seats", {"seats": []})]})
    fixed = up.complete({"messages": base + [_tool_msg("get_seats", {"seats": ["9C"]})]})

    assert "FAILED" in failed["choices"][0]["message"]["content"]
    assert fixed["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "book_seat"
