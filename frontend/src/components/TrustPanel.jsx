import { useEffect, useState } from "react";
import { fetchTrustPanel } from "../api";

// Reads straight from decision_log via /api/trust-panel — every
// recommendation Ledgr has ever made, with the reasoning and evidence
// behind it. Each agent's `details_json` shape differs (quotes vs ledger
// entries vs forecasts vs feasibility checks), so this stays generic and
// lets the reasoning text carry the summary, with raw evidence available
// on expand rather than trying to force one column layout on five
// different data shapes.

export default function TrustPanel({ refreshKey }) {
  const [decisions, setDecisions] = useState([]);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    fetchTrustPanel()
      .then(setDecisions)
      .catch((e) => setLoadError(e.message));
  }, [refreshKey]);

  return (
    <div className="trust">
      <div className="trust-title">Ledger of decisions &mdash; nothing hidden</div>
      {loadError && <div className="trust-empty">Couldn't load trust panel: {loadError}</div>}
      {!loadError && decisions.length === 0 && (
        <div className="trust-empty">Nothing logged yet &mdash; ask Ledgr something first.</div>
      )}
      {decisions.map((d) => (
        <details key={d.id}>
          <summary className="trust-row" style={{ cursor: "pointer" }}>
            <span className="check">&#10003;</span>
            <div>
              <span className="agent-name">{d.agent_name}</span> &mdash;{" "}
              {d.reasoning ? d.reasoning.slice(0, 90) + (d.reasoning.length > 90 ? "..." : "") : "no reasoning logged"}
            </div>
            <div className="timestamp">{formatTimestamp(d.created_at)}</div>
          </summary>
          <div style={{ padding: "8px 0 16px 44px", fontFamily: "'Kalam', cursive", fontSize: "14px" }}>
            <p>{d.reasoning}</p>
            <details style={{ marginTop: "8px" }}>
              <summary style={{ fontFamily: "'Courier Prime', monospace", fontSize: "11px", color: "#8a7657", cursor: "pointer" }}>
                evidence used
              </summary>
              <pre
                style={{
                  fontFamily: "'Courier Prime', monospace",
                  fontSize: "11px",
                  whiteSpace: "pre-wrap",
                  background: "rgba(43,33,23,0.04)",
                  padding: "10px",
                  marginTop: "6px",
                }}
              >
                {formatJson(d.details_json)}
              </pre>
            </details>
          </div>
        </details>
      ))}
    </div>
  );
}

function formatTimestamp(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function formatJson(raw) {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw || "";
  }
}
