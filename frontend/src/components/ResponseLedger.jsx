import { useEffect, useRef, useState } from "react";

// Reveals the agent's recommendation as if being written in, ink by ink —
// same idea as the mockup's typewriter, just re-triggered any time a new
// response comes in (keyed off `text` via the effect dependency).

export default function ResponseLedger({ category, text, error }) {
  const [shown, setShown] = useState("");
  const [done, setDone] = useState(false);
  const timeoutRef = useRef(null);

  useEffect(() => {
    setShown("");
    setDone(false);
    if (timeoutRef.current) clearTimeout(timeoutRef.current);

    const full = error || text || "";
    if (!full) return;

    let i = 0;
    function tick() {
      i += 1;
      setShown(full.slice(0, i));
      if (i < full.length) {
        timeoutRef.current = setTimeout(tick, 12);
      } else {
        setDone(true);
      }
    }
    timeoutRef.current = setTimeout(tick, 200);

    return () => clearTimeout(timeoutRef.current);
  }, [text, error]);

  if (!text && !error) return null;

  return (
    <div className="ledger-row">
      <div className="col-a">{category || "ledgr"}</div>
      <div className={`col-b ink${error ? " error" : ""}`}>
        {shown}
        {!done && <span className="cursor" />}
      </div>
    </div>
  );
}
