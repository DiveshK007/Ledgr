import { useEffect, useState } from "react";
import AgentTabs from "./components/AgentTabs";
import Console from "./components/Console";
import ResponseLedger from "./components/ResponseLedger";
import TrustPanel from "./components/TrustPanel";
import { askLedgr, askLedgrVoice, fetchAgents } from "./api";

const FALLBACK_AGENTS = [
  { key: "supplier", label: "Supplier", seal: "01" },
  { key: "collections", label: "Collections", seal: "02" },
  { key: "pricing", label: "Pricing", seal: "03" },
  { key: "forecasting", label: "Forecasting", seal: "04" },
  { key: "operations", label: "Operations", seal: "05" },
];

export default function App() {
  const [agents, setAgents] = useState(FALLBACK_AGENTS);
  const [loading, setLoading] = useState(false);
  const [lastResult, setLastResult] = useState(null);
  const [trustRefreshKey, setTrustRefreshKey] = useState(0);

  useEffect(() => {
    fetchAgents()
      .then(setAgents)
      .catch(() => setAgents(FALLBACK_AGENTS)); // backend not up yet — keep the tabs rendering regardless
  }, []);

  async function handleAsk(query, files) {
    setLoading(true);
    setLastResult(null);
    try {
      const result = await askLedgr(query, files);
      setLastResult(result);
      setTrustRefreshKey((k) => k + 1); // a new decision was just logged, refresh the panel
    } catch (e) {
      setLastResult({ category: null, error: "Couldn't reach Ledgr's backend. Is app.py running?" });
    } finally {
      setLoading(false);
    }
  }

  async function handleAskVoice(audioBlob) {
    setLoading(true);
    setLastResult(null);
    try {
      const result = await askLedgrVoice(audioBlob);
      setLastResult(result);
      setTrustRefreshKey((k) => k + 1);
    } catch (e) {
      setLastResult({ category: null, error: "Couldn't reach Ledgr's backend. Is app.py running?" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="margin-rule" />
      <div className="paper-grain" />
      <div className="wrap">
        <div className="letterhead">
          <div className="brand">
            <div className="stamp">
              LEDGR
              <br />
              ON-DEVICE
            </div>
            <div className="brand-text">
              <div className="name">Ledgr</div>
              <div className="tag">Business ledger &amp; advisor</div>
            </div>
          </div>
          <div className="date-mark">
            Bengaluru AI Sprint
            <br />
            18 Jul 2026
          </div>
        </div>

        <h1>
          Every decision, <span className="underline">written down</span> and explained.
        </h1>
        <p className="sub">
          Five agents keep the books, chase the dues, and mind the stock &mdash; all reasoning right
          here on the page, not hidden in a black box.
        </p>

        <AgentTabs agents={agents} activeKey={lastResult?.category} />

        <Console onAsk={handleAsk} onAskVoice={handleAskVoice} loading={loading} />

        {lastResult?.transcript && (
          <p style={{ fontFamily: "'Courier Prime', monospace", fontSize: "12px", color: "#8a7657", marginTop: "10px" }}>
            heard: &ldquo;{lastResult.transcript}&rdquo;
          </p>
        )}

        <ResponseLedger
          category={lastResult?.category}
          text={lastResult?.recommendation}
          error={lastResult?.error}
        />

        {lastResult?.audio_url && (
          <audio controls autoPlay src={lastResult.audio_url} style={{ marginTop: "10px", width: "100%" }} />
        )}

        {lastResult?.camera_warnings && (
          <div style={{ marginTop: "12px", fontFamily: "'Courier Prime', monospace", fontSize: "12px", color: "#a3392f" }}>
            {lastResult.camera_warnings.map((w, i) => (
              <div key={i}>&#9888; {w}</div>
            ))}
          </div>
        )}

        <TrustPanel refreshKey={trustRefreshKey} />
      </div>
    </>
  );
}
