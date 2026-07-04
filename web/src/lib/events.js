// Presentation helpers for timeline events.

const TYPE_META = {
  request: { glyph: "→", kind: "req", label: "model request" },
  response: { glyph: "←", kind: "res", label: "model response" },
  tool_call: { glyph: "⚙", kind: "call", label: "tool call" },
  tool_result: { glyph: "⟵", kind: "result", label: "tool result" },
  outcome: { glyph: "◆", kind: "outcome", label: "outcome" },
};

export function meta(event) {
  return TYPE_META[event.type] ?? { glyph: "•", kind: "misc", label: event.type };
}

// A short human summary of what a step did, for the timeline row.
export function summarize(event) {
  const p = event.payload ?? {};
  switch (event.type) {
    case "request":
      return `${p.model ?? "model"} · ${(p.messages ?? []).length} msgs`;
    case "response": {
      const msg = p.choices?.[0]?.message ?? {};
      if (msg.tool_calls?.length) return `calls ${msg.tool_calls[0].function.name}`;
      return truncate(msg.content ?? "");
    }
    case "tool_call":
      return `${p.name}(${JSON.stringify(p.arguments ?? {})})`;
    case "tool_result":
      return `${p.name} → ${truncate(p.result ?? "")}`;
    case "outcome":
      return p.status === "done" ? "DONE ✓" : `${(p.status ?? "").toUpperCase()} — ${truncate(p.content ?? "")}`;
    default:
      return "";
  }
}

// tool_result payloads are the editable ones (that's what you rewind and change).
export function isEditable(event) {
  return event.type === "tool_result";
}

// Align two timelines by seq and mark the first index where they diverge.
export function divergenceIndex(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    if (JSON.stringify(a[i].payload) !== JSON.stringify(b[i].payload)) return i;
  }
  return a.length === b.length ? -1 : n;
}

function truncate(s, max = 48) {
  const str = String(s);
  return str.length > max ? `${str.slice(0, max)}…` : str;
}
