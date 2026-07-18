// Five ledger-index tabs. `activeKey` is set from whichever `category`
// came back on the last /api/ask response — this is a real signal, not
// decorative, since the backend's planner actually decided it.

export default function AgentTabs({ agents, activeKey }) {
  return (
    <div className="ledger-tabs">
      {agents.map((a) => (
        <div key={a.key} className={`tab${a.key === activeKey ? " active" : ""}`}>
          <div className="seal">{a.seal}</div>
          <div className="label">{a.label}</div>
        </div>
      ))}
    </div>
  );
}
