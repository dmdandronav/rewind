"""The bundled flight-booking agent.

Its tools are deliberately simple and, crucially, the ``get_seats`` tool returns
*no seats* for the scripted flight — which is what makes the original run fail at
booking time. That failure is the thing you rewind and fix in the demo: edit the
recorded ``get_seats`` result to contain a seat, fork, and the replay books it.

Implements :class:`rewind.agent.Agent` so the server can re-drive it during a
one-click fork replay.
"""

from __future__ import annotations

from typing import Any

#: The goal the demo agent is launched with.
DEMO_GOAL = "Book me a flight from SFO to JFK next Friday."


class FlightAgent:
    model = "rewind-demo/flight-planner"

    def build_request(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        return {"model": self.model, "messages": messages, "temperature": 0}

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "search_flights":
            return {"flights": ["UA100", "DL204"]}
        if name == "get_seats":
            # The bug the demo is about: the scripted flight comes back full.
            return {"flight": arguments.get("flight"), "seats": []}
        if name == "book_seat":
            return {"status": "confirmed", "seat": arguments.get("seat")}
        return {"error": f"unknown tool: {name}"}

    def initial_messages(self) -> list[dict[str, Any]]:
        return [{"role": "user", "content": DEMO_GOAL}]
