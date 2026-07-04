"""REWIND FastAPI app: recording proxy + timeline/fork API.

Endpoints:

* ``POST /v1/chat/completions`` — the recording proxy. Point your agent's base
  URL here; every call is logged into the session named by the
  ``X-Rewind-Session`` header before being forwarded to the upstream.
* ``GET  /api/sessions`` / ``GET /api/sessions/{id}/events`` — read a timeline.
* ``POST /api/sessions/{id}/fork`` — fork at a seq with an optional edit and
  replay the bundled demo agent from the divergence point.
* ``POST /api/demo/seed`` — create a fresh failing demo run to play with.

State (store + upstream) hangs off ``app.state`` so tests can swap in an
in-memory store and the deterministic mock upstream.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from demo_agent.flight_agent import FlightAgent
from .driver import replay_fork, run_loop
from .fingerprint import fingerprint_request
from .models import EventType
from .store import EventStore
from .upstream import HttpUpstream, MockUpstream, Upstream


def _build_upstream() -> Upstream:
    base = os.environ.get("REWIND_UPSTREAM_BASE_URL")
    if base:
        return HttpUpstream(base, api_key=os.environ.get("REWIND_UPSTREAM_API_KEY"))
    return MockUpstream()


def create_app(store: EventStore | None = None, upstream: Upstream | None = None) -> FastAPI:
    app = FastAPI(title="REWIND", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.store = store or EventStore(os.environ.get("REWIND_DB", ":memory:"))
    app.state.upstream = upstream or _build_upstream()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # -- recording proxy -----------------------------------------------------

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> dict[str, Any]:
        body = await request.json()
        session_id = request.headers.get("X-Rewind-Session")
        store: EventStore = app.state.store
        if not session_id:
            session_id = store.create_session("proxy run").id
        elif store.get_session(session_id) is None:
            store.create_session("proxy run", session_id=session_id)

        store.append_event(
            session_id, EventType.REQUEST, body,
            request_fingerprint=fingerprint_request(body),
        )
        response = app.state.upstream.complete(body)
        store.append_event(session_id, EventType.RESPONSE, response)
        return response

    # -- timeline API --------------------------------------------------------

    @app.get("/api/sessions")
    def list_sessions() -> list[dict[str, Any]]:
        return [_session_dict(s) for s in app.state.store.list_sessions()]

    @app.get("/api/sessions/{session_id}/events")
    def get_events(session_id: str) -> dict[str, Any]:
        store: EventStore = app.state.store
        if store.get_session(session_id) is None:
            raise HTTPException(404, f"unknown session: {session_id}")
        return {
            "session": _session_dict(store.get_session(session_id)),
            "events": [_event_dict(e) for e in store.get_events(session_id)],
        }

    # -- fork + replay -------------------------------------------------------

    @app.post("/api/sessions/{session_id}/fork")
    def fork(session_id: str, body: ForkRequest) -> dict[str, Any]:
        store: EventStore = app.state.store
        if store.get_session(session_id) is None:
            raise HTTPException(404, f"unknown session: {session_id}")
        try:
            forked = store.fork_session(
                session_id,
                body.fork_seq,
                edited_payload=body.edited_payload,
                label=body.label,
            )
        except IndexError as exc:
            raise HTTPException(400, str(exc)) from exc

        outcome = replay_fork(
            store, app.state.upstream, FlightAgent(), forked.id, session_id
        )
        return {
            "session": _session_dict(forked),
            "outcome": outcome,
            "events": [_event_dict(e) for e in store.get_events(forked.id)],
        }

    # -- demo seeding --------------------------------------------------------

    @app.post("/api/demo/seed")
    def seed_demo() -> dict[str, Any]:
        """Create a fresh failing demo run and return its session."""
        store: EventStore = app.state.store
        agent = FlightAgent()
        session = store.create_session("Flight booking (demo)")
        run_loop(
            store,
            session.id,
            agent,
            app.state.upstream.complete,
            agent.initial_messages(),
        )
        return {
            "session": _session_dict(session),
            "events": [_event_dict(e) for e in store.get_events(session.id)],
        }

    return app


class ForkRequest(BaseModel):
    fork_seq: int
    edited_payload: dict[str, Any] | None = None
    label: str | None = None


def _session_dict(s: Any) -> dict[str, Any]:
    return {
        "id": s.id,
        "label": s.label,
        "created_at": s.created_at,
        "parent_session_id": s.parent_session_id,
        "forked_at_seq": s.forked_at_seq,
    }


def _event_dict(e: Any) -> dict[str, Any]:
    return {
        "id": e.id,
        "seq": e.seq,
        "type": e.type.value,
        "payload": e.payload,
        "ts": e.ts,
        "request_fingerprint": e.request_fingerprint,
    }


#: Module-level app for ``uvicorn rewind.app:app``.
app = create_app()
