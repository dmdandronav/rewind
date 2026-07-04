# REWIND

**A time-travel debugger for LLM agents.** Point your agent at REWIND instead of
the model API. REWIND records every message, tool call, and tool result as an
immutable event log — then lets you scrub the agent's timeline, edit any past
state, and **fork a deterministic replay** from that point. Two timelines run
side by side from the divergence, so you get a git-diff of agent *behavior*.

> Runs with **zero API keys** out of the box. A built-in mock upstream replays
> canned completions so the whole thing — proxy, event log, fork/replay, UI — is
> demoable and testable offline. Point it at a real Anthropic/OpenAI-compatible
> endpoint when you want live traffic.

---

## The 30-second demo

An agent booking flights fails at step 9. You drag the timeline scrubber back to
step 5, see the tool result that poisoned everything, edit one JSON field inline,
and hit **Fork**. The right pane replays from step 5 and succeeds while the left
pane still shows the original failure — a side-by-side diff of what the agent did
versus what it *would* have done.

```
 ORIGINAL (session a1)              FORK (session a1→f2, edited @ step 5)
 ─────────────────────              ───────────────────────────────────
 5  tool: get_seats → []       ⟶    5  tool: get_seats → ["12A","12B"]   ← edited
 6  llm: "no seats, abort"     ⟶    6  llm: "booking 12A"
 7  llm: FAIL                  ⟶    7  tool: book_seat → ok
                                    8  llm: DONE ✓
```

## Why it exists

Agent runs are non-deterministic and opaque. When step 9 breaks, the cause is
usually a bad tool result at step 5 — but you can't rewind to check without
re-running the whole thing and hoping it fails the same way. REWIND makes the
run a replayable artifact: every event is recorded, any past state is editable,
and a fork replays *deterministically* (recorded steps are served from the log;
only the branch after your edit hits the model fresh).

## Architecture

```
your agent ──HTTP──▶  REWIND proxy  ──▶  upstream (mock or real model API)
                          │
                          ▼
                   SQLite event log  ◀──  Timeline API  ◀──  React scrubber UI
                   (immutable, append-only)                  (scrub · edit · fork · compare)
```

- **`server/`** — FastAPI. A transparent, OpenAI/Anthropic-compatible proxy that
  records every request/response as an append-only event, plus the timeline +
  fork/replay API. SQLite storage, no external services.
- **`web/`** — React + Vite timeline scrubber with two-pane branch compare.
- **`demo_agent/`** — a self-contained flight-booking agent that runs against the
  mock upstream, so `git clone` → `demo` shows the whole loop with no keys.

## Quick start

```bash
# 1. Backend (Python 3.11+)
cd server
pip install -e ".[dev]"
uvicorn rewind.app:app --reload            # proxy + API on :8000, mock upstream by default

# 2. Run the demo agent against the proxy (new terminal, no API key needed)
python -m demo_agent.book_flight

# 3. Frontend
cd web && npm install && npm run dev        # timeline UI on :5173
```

Open http://localhost:5173, pick the demo session, scrub to the failing step,
edit the tool result, and fork.

### Pointing at a real model

Set the upstream to any OpenAI/Anthropic-compatible base URL:

```bash
export REWIND_UPSTREAM_BASE_URL=https://api.anthropic.com
export REWIND_UPSTREAM_API_KEY=sk-...      # kept server-side, never logged
uvicorn rewind.app:app --reload
```

Then point your agent's base URL at `http://localhost:8000`.

## How the fork/replay is deterministic

Each event stores the exact upstream request and the response it produced. When
you fork at step *N* with an edited state:

1. Events `0..N` are copied into the new session (the edit is applied at *N*).
2. Replay walks forward. For each agent step whose request bytes are unchanged
   from the original, REWIND serves the **recorded** response — no model call.
3. The first step whose input differs (because your edit changed downstream
   context) is sent to the upstream fresh, and everything after it is live.

So the unchanged prefix is bit-for-bit identical and only the consequences of
your edit are recomputed. See [`docs/DETERMINISM.md`](docs/DETERMINISM.md).

## Project status

Built as a hackathon flagship. Core loop (record → scrub → edit → fork → compare)
is the focus; see [issues](https://github.com/dmdandronav/rewind/issues) for
stretch goals (streaming passthrough, multi-agent sessions, trace export).

## License

MIT — see [LICENSE](LICENSE).
