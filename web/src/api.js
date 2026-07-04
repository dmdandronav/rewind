// Thin API client for the REWIND backend.

async function json(res) {
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export const api = {
  seedDemo: () => fetch("/api/demo/seed", { method: "POST" }).then(json),

  listSessions: () => fetch("/api/sessions").then(json),

  getEvents: (sessionId) =>
    fetch(`/api/sessions/${sessionId}/events`).then(json),

  fork: (sessionId, forkSeq, editedPayload) =>
    fetch(`/api/sessions/${sessionId}/fork`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fork_seq: forkSeq, edited_payload: editedPayload }),
    }).then(json),
};
