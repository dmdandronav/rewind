"""Model upstreams the proxy can forward to.

Two implementations:

* :class:`MockUpstream` — a tiny deterministic "model" that plays the bundled
  flight-booking scenario. It is a *pure function of the request*, which is what
  makes the whole demo (and the test suite) reproducible with no API keys and no
  network. Given the same messages it always returns the same completion.
* :class:`HttpUpstream` — forwards to any OpenAI/Anthropic-compatible endpoint.

Both satisfy the same :class:`Upstream` protocol, so the proxy neither knows nor
cares which one is behind it.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

import httpx


@runtime_checkable
class Upstream(Protocol):
    """Anything that can turn a chat-completion request into a response."""

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        ...


def _last_user_or_tool(messages: list[dict[str, Any]]) -> str:
    """Return the text content of the most recent user/tool message."""
    for msg in reversed(messages):
        if msg.get("role") in ("user", "tool"):
            content = msg.get("content", "")
            return content if isinstance(content, str) else json.dumps(content)
    return ""


def _assistant_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Shape an assistant message that calls a tool (OpenAI tool-call schema)."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{name}",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


def _assistant_text(text: str, finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish_reason,
            }
        ]
    }


class MockUpstream:
    """A scripted, deterministic model for the flight-booking demo.

    The "policy" is intentionally simple and legible so the demo is easy to
    reason about on stage:

    1. First turn (a user goal) → call ``search_flights``.
    2. After flight search results → call ``get_seats`` for the first flight.
    3. After seat results:
         * if seats are available → call ``book_seat`` for the first seat,
         * if no seats → give up with a FAILED message.
    4. After a successful booking → emit a DONE message.

    Because step 3 branches on the *content* of the seat result, editing a past
    "no seats" result into "seats available" is exactly what flips a failed run
    into a successful fork — with no randomness anywhere.
    """

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        messages: list[dict[str, Any]] = request.get("messages", [])
        last = _last_user_or_tool(messages)

        # Which tools have already produced results so far?
        tool_names_seen = [
            m.get("name")
            for m in messages
            if m.get("role") == "tool"
        ]

        if "book_seat" in tool_names_seen:
            return _assistant_text("DONE: booking confirmed ✓")

        if "get_seats" in tool_names_seen:
            # Inspect the most recent seat result.
            seats = self._parse_seats(last)
            if seats:
                return _assistant_tool_call("book_seat", {"seat": seats[0]})
            return _assistant_text("FAILED: no seats available, aborting", "stop")

        if "search_flights" in tool_names_seen:
            flight = self._parse_first_flight(last)
            return _assistant_tool_call("get_seats", {"flight": flight})

        # Cold start: the user just stated a goal.
        return _assistant_tool_call("search_flights", {"query": last or "any"})

    @staticmethod
    def _parse_seats(tool_content: str) -> list[str]:
        try:
            data = json.loads(tool_content)
            return list(data.get("seats", []))
        except (json.JSONDecodeError, AttributeError):
            return []

    @staticmethod
    def _parse_first_flight(tool_content: str) -> str:
        try:
            data = json.loads(tool_content)
            flights = data.get("flights", [])
            return flights[0] if flights else "UNKNOWN"
        except (json.JSONDecodeError, AttributeError):
            return "UNKNOWN"


class HttpUpstream:
    """Forwards completion requests to a real model API over HTTP."""

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = httpx.post(
            f"{self._base_url}/v1/chat/completions",
            json=request,
            headers=headers,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()
