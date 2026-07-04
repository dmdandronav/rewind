import { useEffect, useState } from "react";
import { isEditable, meta } from "../lib/events.js";

// Inspects the selected event. For editable (tool_result) steps it exposes the
// payload as text and a Fork button — that's the "edit the past and branch" move.
export default function Inspector({ event, onFork, forking }) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (event) setDraft(JSON.stringify(event.payload, null, 2));
    setError("");
  }, [event]);

  if (!event) {
    return (
      <aside className="inspector inspector--empty">
        <p>Select a step to inspect it. Pick a <em>tool result</em> to rewind, edit, and fork.</p>
      </aside>
    );
  }

  const editable = isEditable(event);

  function handleFork() {
    let parsed;
    try {
      parsed = JSON.parse(draft);
    } catch (e) {
      setError("Payload is not valid JSON.");
      return;
    }
    onFork(event.seq, parsed);
  }

  return (
    <aside className="inspector">
      <header className="inspector__head">
        <span className="inspector__type">{meta(event).label}</span>
        <span className="inspector__seq">step {event.seq}</span>
      </header>

      {editable ? (
        <>
          <label className="inspector__hint">Edit this recorded result, then fork:</label>
          <textarea
            className="inspector__editor"
            value={draft}
            spellCheck={false}
            onChange={(e) => setDraft(e.target.value)}
          />
          {error && <p className="inspector__error">{error}</p>}
          <button className="fork-btn" onClick={handleFork} disabled={forking}>
            {forking ? "Forking & replaying…" : "⑃ Fork from here"}
          </button>
        </>
      ) : (
        <pre className="inspector__view">{JSON.stringify(event.payload, null, 2)}</pre>
      )}
    </aside>
  );
}
