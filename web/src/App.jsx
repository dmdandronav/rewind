import { useEffect, useState } from "react";
import { api } from "./api.js";
import Timeline from "./components/Timeline.jsx";
import Inspector from "./components/Inspector.jsx";
import { divergenceIndex } from "./lib/events.js";

export default function App() {
  const [origin, setOrigin] = useState(null); // {session, events}
  const [fork, setFork] = useState(null); // {session, events, outcome}
  const [selected, setSelected] = useState(null);
  const [forking, setForking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadDemo() {
    setLoading(true);
    setError("");
    setFork(null);
    setSelected(null);
    try {
      const data = await api.seedDemo();
      setOrigin(data);
    } catch (e) {
      setError(String(e.message ?? e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDemo();
  }, []);

  async function handleFork(seq, editedPayload) {
    if (!origin) return;
    setForking(true);
    setError("");
    try {
      const data = await api.fork(origin.session.id, seq, editedPayload);
      setFork(data);
    } catch (e) {
      setError(String(e.message ?? e));
    } finally {
      setForking(false);
    }
  }

  const divergeAt = fork ? divergenceIndex(origin.events, fork.events) : -1;
  const originOutcome = outcomeOf(origin);
  const forkOutcome = fork ? fork.outcome : null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">⟲</span>
          <div>
            <h1>REWIND</h1>
            <p>time-travel debugger for LLM agents</p>
          </div>
        </div>
        <button className="ghost-btn" onClick={loadDemo} disabled={loading}>
          {loading ? "seeding…" : "↺ new demo run"}
        </button>
      </header>

      {error && <div className="banner banner--error">{error}</div>}

      <p className="lede">
        This agent tries to book a flight and <strong>fails</strong> — the seat
        lookup comes back empty. Scrub to the <code>get_seats</code> step, edit a
        seat into the result, and <strong>fork</strong>. The replay reuses every
        recorded step up to your edit, then goes live — booking the seat and
        finishing, while the original stays failed.
      </p>

      <div className="stage">
        <section className="pane">
          {origin && (
            <Timeline
              title="original run"
              tone="origin"
              events={origin.events}
              selectedSeq={selected?.seq}
              onSelect={setSelected}
            />
          )}
          {originOutcome && <OutcomeChip outcome={originOutcome} />}
        </section>

        <section className="pane pane--inspector">
          <Inspector event={selected} onFork={handleFork} forking={forking} />
        </section>

        <section className="pane">
          {fork ? (
            <>
              <Timeline
                title="fork (replayed)"
                tone="fork"
                events={fork.events}
                selectedSeq={null}
                divergeAt={divergeAt}
              />
              {forkOutcome && <OutcomeChip outcome={forkOutcome} />}
            </>
          ) : (
            <div className="pane__placeholder">
              <p>No fork yet.</p>
              <p className="muted">Select the <code>get_seats</code> result, add a seat, and fork to compare here.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function outcomeOf(run) {
  if (!run) return null;
  const ev = [...run.events].reverse().find((e) => e.type === "outcome");
  return ev?.payload?.status ?? null;
}

function OutcomeChip({ outcome }) {
  const ok = outcome === "done";
  return (
    <div className={`outcome-chip ${ok ? "outcome-chip--ok" : "outcome-chip--fail"}`}>
      {ok ? "booking confirmed ✓" : "run failed ✕"}
    </div>
  );
}
