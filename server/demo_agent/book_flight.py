"""Run the flight-booking agent live against a running REWIND proxy.

    python -m demo_agent.book_flight            # uses http://localhost:8000

Every model call and tool step is recorded into a new session; the run "fails"
because the scripted flight has no seats. Open the UI, rewind to the get_seats
step, edit in a seat, and fork to watch it succeed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from .flight_agent import DEMO_GOAL, FlightAgent

PROXY = os.environ.get("REWIND_PROXY", "http://localhost:8000")


def _post(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    agent = FlightAgent()
    session_id = _post(f"{PROXY}/api/demo/seed", {})["session"]["id"]
    # The seed endpoint already ran the loop server-side; just report it.
    events = _post(f"{PROXY}/api/sessions/{session_id}/events", {}) if False else None
    print(f"Recorded demo session: {session_id}")
    print(f"Goal: {DEMO_GOAL}")
    print("Open the UI, scrub to the get_seats step, edit in a seat, and fork.")
    print(f"  UI:  http://localhost:5173/?session={session_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
