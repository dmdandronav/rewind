# How REWIND replays deterministically

The product promise is that a fork replays *faithfully*: the part of the run
before your edit is reproduced exactly, and only the consequences of the edit are
recomputed. This note explains the mechanism.

## The timeline is the source of truth

Every run is an append-only list of typed events (`REQUEST`, `RESPONSE`,
`TOOL_CALL`, `TOOL_RESULT`, `OUTCOME`). Nothing is ever mutated. "Editing the
past" is not an update — it is a **fork**: the prefix `0..fork_seq` is copied into
a new session, with your edit applied to the event at `fork_seq`
(`store.fork_session`). The parent is never touched, so the original failing run
is always still there to compare against.

## Reconstructing context from events

To continue the loop after a fork, REWIND rebuilds the agent's message list by
folding the copied events back into messages (`driver.reconstruct_messages`):

- the first `REQUEST` seeds the initial user message(s),
- each `RESPONSE` contributes the assistant message,
- each `TOOL_RESULT` contributes a tool message.

Because your edit changed a `TOOL_RESULT` payload, the reconstructed context now
carries the edited value forward automatically — no special-casing.

## Reuse until divergence, then go live

Replay then continues the **same** agent loop used for live runs
(`driver.run_loop`) — there is only one loop, so a replay steps through identical
logic. The one difference is where model responses come from, decided by
`ReplayController`:

1. It holds the parent's ordered `(request_fingerprint, response)` pairs.
2. For each model call the replay makes, it compares the call's fingerprint to
   the parent's at the same index.
   - **Match** → serve the parent's recorded response verbatim. No model call.
   - **Mismatch** → this is the divergence point. Call the upstream live, and
     every call from here on is live too (we never re-sync after diverging).

A request fingerprint is a hash of the canonicalized request body with volatile
fields (`stream`, `user`, `metadata`) stripped (`fingerprint.py`), so identical
logical calls match regardless of key ordering.

## Why this is honest with a real model

With a real, nondeterministic API, you can't just "re-run and hope." REWIND
doesn't: the unchanged prefix is served from the log, so it cannot drift, and
only the branch after your edit hits the model. You are looking at the genuine
recorded past plus the genuine consequences of one change — not a fresh run that
happened to differ.

## Why the demo needs no API key

The bundled `MockUpstream` is a pure function of the request (`upstream.py`): the
same messages always yield the same completion. So "going live" after divergence
is itself reproducible, which makes the whole flow — and the test suite —
deterministic and offline. Point `REWIND_UPSTREAM_BASE_URL` at a real endpoint to
swap in live traffic; the replay logic is identical.

## Where it stops

- Reuse is prefix-only: once diverged, we don't attempt to re-align later matching
  calls (that would risk stitching together incompatible contexts).
- Tool *execution* after the divergence point runs fresh via the agent's tools;
  only model responses are reused. Tools are expected to be effect-free in replay
  (the demo's are). Side-effecting tools should be stubbed for replay — a
  documented stretch goal.
