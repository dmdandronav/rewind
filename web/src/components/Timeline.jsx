import { meta, summarize } from "../lib/events.js";

// A vertical, scrubbable list of timeline steps. `divergeAt` highlights the row
// where a compared fork first differs from this timeline.
export default function Timeline({ title, events, selectedSeq, onSelect, divergeAt = -1, tone = "origin" }) {
  return (
    <div className={`timeline timeline--${tone}`}>
      <header className="timeline__head">
        <span className="timeline__title">{title}</span>
        <span className="timeline__count">{events.length} steps</span>
      </header>
      <ol className="timeline__list">
        {events.map((ev, i) => {
          const m = meta(ev);
          const isSel = ev.seq === selectedSeq;
          const isDiverge = i === divergeAt;
          const outcomeClass =
            ev.type === "outcome" ? `row--${ev.payload?.status ?? "done"}` : "";
          return (
            <li key={ev.id}>
              {isDiverge && <div className="diverge-marker">▲ diverges here</div>}
              <button
                className={`row ${m.kind} ${isSel ? "row--sel" : ""} ${outcomeClass}`}
                onClick={() => onSelect?.(ev)}
              >
                <span className="row__seq">{ev.seq}</span>
                <span className="row__glyph">{m.glyph}</span>
                <span className="row__body">
                  <span className="row__label">{m.label}</span>
                  <span className="row__summary">{summarize(ev)}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
