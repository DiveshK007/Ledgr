// Thin wrapper around the Flask API. Requests go through Vite's dev proxy
// (see vite.config.js), so these are always relative /api/... paths —
// no hardcoded host, works the same in dev and once built.

export async function fetchAgents() {
  const res = await fetch("/api/agents");
  if (!res.ok) throw new Error("Failed to load agents");
  return (await res.json()).agents;
}

export async function askLedgr(query, imageFiles = []) {
  let res;
  if (imageFiles.length > 0) {
    const form = new FormData();
    form.append("query", query);
    imageFiles.forEach((f) => form.append("images", f));
    res = await fetch("/api/ask", { method: "POST", body: form });
  } else {
    res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
  }
  return await res.json(); // backend returns structured errors too, let caller decide
}

export async function askLedgrVoice(audioBlob) {
  const form = new FormData();
  form.append("audio", audioBlob, "recording.webm");
  const res = await fetch("/api/ask-voice", { method: "POST", body: form });
  return await res.json();
}

export async function fetchTrustPanel(limit = 20) {
  const res = await fetch(`/api/trust-panel?limit=${limit}`);
  if (!res.ok) throw new Error("Failed to load trust panel");
  return (await res.json()).decisions;
}
