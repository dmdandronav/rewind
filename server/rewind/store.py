"""Append-only event store backed by SQLite.

The store is the source of truth for every agent timeline. Its invariants:

* Events are **append-only** — ``append_event`` is the only writer, and there is
  no update or delete path for events.
* ``(session_id, seq)`` is unique, so a timeline is a gap-free ordered list.
* Forking never mutates the parent. ``fork_session`` copies the prefix
  ``0..fork_seq`` into a brand-new session, optionally applying one edit at the
  fork point, and returns the new session id for replay to continue from.

Connections are created per-call (SQLite handles this cheaply) so the store is
safe to share across FastAPI's threadpool without a long-lived connection.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .models import Event, EventType, Session

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                 TEXT PRIMARY KEY,
    label              TEXT NOT NULL,
    created_at         REAL NOT NULL,
    parent_session_id  TEXT,
    forked_at_seq      INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id                   TEXT PRIMARY KEY,
    session_id           TEXT NOT NULL REFERENCES sessions(id),
    seq                  INTEGER NOT NULL,
    type                 TEXT NOT NULL,
    payload              TEXT NOT NULL,
    ts                   REAL NOT NULL,
    request_fingerprint  TEXT,
    UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, seq);
"""


class EventStore:
    """SQLite-backed append-only store for sessions and their events."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        # An in-memory DB only survives as long as its connection, so for
        # ``:memory:`` we hold one open connection for the store's lifetime. That
        # connection is shared across FastAPI's threadpool, so it's opened with
        # check_same_thread=False and every use is serialized by ``_lock``.
        self._lock = threading.Lock()
        self._shared: sqlite3.Connection | None = (
            self._connect() if self._db_path == ":memory:" else None
        )
        with self._cursor() as cur:
            cur.executescript(_SCHEMA)

    # -- connection plumbing -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    class _CursorCtx:
        def __init__(self, store: "EventStore") -> None:
            self._store = store
            self._own = store._shared is None
            self._conn = store._shared or store._connect()
            # Only the shared in-memory connection needs cross-thread locking;
            # per-call connections are confined to one thread already.
            self._lock = store._lock if not self._own else None

        def __enter__(self) -> sqlite3.Cursor:
            if self._lock is not None:
                self._lock.acquire()
            return self._conn.cursor()

        def __exit__(self, exc_type, exc, tb) -> None:
            try:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
                if self._own:
                    self._conn.close()
            finally:
                if self._lock is not None:
                    self._lock.release()

    def _cursor(self) -> "EventStore._CursorCtx":
        return EventStore._CursorCtx(self)

    # -- sessions ------------------------------------------------------------

    def create_session(
        self,
        label: str,
        *,
        session_id: str | None = None,
        parent_session_id: str | None = None,
        forked_at_seq: int | None = None,
    ) -> Session:
        """Create and persist a new (possibly forked) session."""
        session = Session(
            id=session_id or uuid.uuid4().hex[:12],
            label=label,
            parent_session_id=parent_session_id,
            forked_at_seq=forked_at_seq,
        )
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (id, label, created_at, parent_session_id, forked_at_seq)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    session.id,
                    session.label,
                    session.created_at,
                    session.parent_session_id,
                    session.forked_at_seq,
                ),
            )
        return session

    def get_session(self, session_id: str) -> Session | None:
        with self._cursor() as cur:
            row = cur.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return _row_to_session(row) if row else None

    def list_sessions(self) -> list[Session]:
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM sessions ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_session(r) for r in rows]

    # -- events --------------------------------------------------------------

    def append_event(
        self,
        session_id: str,
        type: EventType,
        payload: dict[str, Any],
        *,
        request_fingerprint: str | None = None,
    ) -> Event:
        """Append one event to a session's timeline at the next seq.

        This is the ONLY write path for events; there is deliberately no update
        or delete. The next seq is derived from the current max, so callers never
        pick seq numbers themselves.
        """
        if self.get_session(session_id) is None:
            raise KeyError(f"unknown session: {session_id}")
        with self._cursor() as cur:
            row = cur.execute(
                "SELECT COALESCE(MAX(seq) + 1, 0) AS next FROM events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            next_seq = int(row["next"])
            event = Event(
                id=uuid.uuid4().hex[:12],
                session_id=session_id,
                seq=next_seq,
                type=type,
                payload=payload,
                request_fingerprint=request_fingerprint,
            )
            cur.execute(
                "INSERT INTO events (id, session_id, seq, type, payload, ts, request_fingerprint)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.id,
                    event.session_id,
                    event.seq,
                    event.type.value,
                    json.dumps(event.payload),
                    event.ts,
                    event.request_fingerprint,
                ),
            )
        return event

    def get_events(self, session_id: str) -> list[Event]:
        """Return a session's full timeline in seq order."""
        with self._cursor() as cur:
            rows = cur.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    # -- forking -------------------------------------------------------------

    def fork_session(
        self,
        session_id: str,
        fork_seq: int,
        *,
        edited_payload: dict[str, Any] | None = None,
        label: str | None = None,
    ) -> Session:
        """Branch ``session_id`` into a new session sharing events ``0..fork_seq``.

        The prefix is copied verbatim except that, if ``edited_payload`` is given,
        it replaces the payload of the event at ``fork_seq`` — this is the "edit a
        past state" operation. The parent session is left completely untouched.
        Replay (in ``replay.py``) picks up from ``fork_seq + 1``.
        """
        parent = self.get_session(session_id)
        if parent is None:
            raise KeyError(f"unknown session: {session_id}")

        prefix = [e for e in self.get_events(session_id) if e.seq <= fork_seq]
        if not prefix or prefix[-1].seq != fork_seq:
            raise IndexError(f"fork_seq {fork_seq} out of range for session {session_id}")

        fork = self.create_session(
            label=label or f"{parent.label} (fork @{fork_seq})",
            parent_session_id=session_id,
            forked_at_seq=fork_seq,
        )
        for ev in prefix:
            payload = ev.payload
            if edited_payload is not None and ev.seq == fork_seq:
                payload = edited_payload
            self.append_event(
                fork.id,
                ev.type,
                payload,
                request_fingerprint=ev.request_fingerprint,
            )
        return fork


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        label=row["label"],
        created_at=row["created_at"],
        parent_session_id=row["parent_session_id"],
        forked_at_seq=row["forked_at_seq"],
    )


def _row_to_event(row: sqlite3.Row) -> Event:
    return Event(
        id=row["id"],
        session_id=row["session_id"],
        seq=row["seq"],
        type=EventType(row["type"]),
        payload=json.loads(row["payload"]),
        ts=row["ts"],
        request_fingerprint=row["request_fingerprint"],
    )
