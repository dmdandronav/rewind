"""The agent loop, shared by live recording and fork replay.

There is exactly one loop implementation here so that a replayed run steps
through precisely the same logic a live run did — the only difference is where
model responses come from (upstream vs. reused recording). Keeping it single-
sourced is what lets us claim the replay is faithful.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .agent import Agent
from .fingerprint import fingerprint_request
from .models import Event, EventType
from .replay import ReplayController
from .store import EventStore
from .upstream import Upstream

#: A model call: takes a request body, returns a completion. Lets the loop stay
#: agnostic about whether the response is live or a reused recording.
ModelCall = Callable[[dict[str, Any]], dict[str, Any]]

#: Guard against a runaway agent looping forever during replay.
_MAX_STEPS = 25


def run_loop(
    store: EventStore,
    session_id: str,
    agent: Agent,
    model_call: ModelCall,
    messages: list[dict[str, Any]],
) -> str:
    """Drive the agent loop, recording every step into ``session_id``.

    Returns the terminal outcome status ("done" or "failed"). ``model_call`` is
    injected so the same loop serves both live runs (call the upstream) and
    replays (reuse recorded responses until divergence).
    """
    for _ in range(_MAX_STEPS):
        request = agent.build_request(messages)
        store.append_event(
            session_id,
            EventType.REQUEST,
            request,
            request_fingerprint=fingerprint_request(request),
        )
        response = model_call(request)
        store.append_event(session_id, EventType.RESPONSE, response)

        message = response["choices"][0]["message"]
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            status = "failed" if "FAIL" in (message.get("content") or "").upper() else "done"
            store.append_event(
                session_id,
                EventType.OUTCOME,
                {"status": status, "content": message.get("content")},
            )
            return status

        call = tool_calls[0]
        name = call["function"]["name"]
        arguments = json.loads(call["function"]["arguments"])
        store.append_event(
            session_id, EventType.TOOL_CALL, {"name": name, "arguments": arguments}
        )
        result = agent.execute_tool(name, arguments)
        store.append_event(
            session_id, EventType.TOOL_RESULT, {"name": name, "result": json.dumps(result)}
        )
        messages.append({"role": "tool", "name": name, "content": json.dumps(result)})

    store.append_event(
        session_id, EventType.OUTCOME, {"status": "failed", "content": "max steps exceeded"}
    )
    return "failed"


def reconstruct_messages(events: list[Event]) -> list[dict[str, Any]]:
    """Rebuild the running message list from a timeline's events.

    Folding typed events back into messages is what lets an *edited* TOOL_RESULT
    flow into the replayed context: the edit changed the event payload, so the
    reconstructed conversation carries the edit forward automatically.
    """
    messages: list[dict[str, Any]] = []
    for ev in events:
        if ev.type == EventType.REQUEST and not messages:
            messages.extend(ev.payload.get("messages", []))
        elif ev.type == EventType.RESPONSE:
            messages.append(ev.payload["choices"][0]["message"])
        elif ev.type == EventType.TOOL_RESULT:
            messages.append(
                {"role": "tool", "name": ev.payload["name"], "content": ev.payload["result"]}
            )
    return messages


def replay_fork(
    store: EventStore,
    upstream: Upstream,
    agent: Agent,
    fork_session_id: str,
    parent_session_id: str,
) -> str:
    """Replay a forked session from its divergence point.

    The fork already contains the copied (and possibly edited) prefix. We rebuild
    the message list from that prefix, then continue the loop. A
    :class:`ReplayController` serves the parent's recorded responses while the
    fork's requests still fingerprint-match, and falls through to the live
    upstream once the edit makes them diverge.
    """
    prefix = store.get_events(fork_session_id)
    messages = reconstruct_messages(prefix)

    # The fork already contains the prefix's model calls, so the controller must
    # resume comparing against the parent timeline just past them.
    already_made = sum(1 for e in prefix if e.type == EventType.REQUEST)
    controller = ReplayController(store, parent_session_id, start_index=already_made)

    def model_call(request: dict[str, Any]) -> dict[str, Any]:
        decision = controller.decide(fingerprint_request(request))
        if decision.reuse and decision.recorded_response is not None:
            return decision.recorded_response
        return upstream.complete(request)

    return run_loop(store, fork_session_id, agent, model_call, messages)
