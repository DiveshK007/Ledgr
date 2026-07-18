# Ledgr frontend

Vite + React, plain CSS (no Tailwind/component library) — kept deliberately
light on dependencies so `npm install` doesn't become a hackathon-day risk.
Implements the ledger-paper theme as real components instead of the static
mockup HTML file: cream ruled paper, red ledger-margin rule, slab serif +
handwritten type, five agents as numbered index tabs, an ask box styled as
a literal ledger entry line, a typewriter-style reveal for responses, and a
trust panel reading straight from the backend's decision log.

## Setup

```bash
npm install
npm run dev
```

Opens on http://localhost:5173. Requires the backend running first:

```bash
# in the saathi/ root, separate terminal
python app.py
```

Vite's dev server proxies `/api/*` to `http://localhost:5000` (see
`vite.config.js`), so there's no CORS friction and no hardcoded backend URL
anywhere in the frontend code.

## Structure

```
frontend/
  index.html
  vite.config.js
  package.json
  src/
    main.jsx           # entry point
    App.jsx             # page layout, owns the "last result" + agent state
    api.js               # fetch wrappers for /api/ask, /api/trust-panel, /api/agents
    styles.css            # the ledger-paper theme, all of it
    components/
      AgentTabs.jsx        # five index tabs; active one reflects the real routed category
      Console.jsx           # the ask box (text + optional photo attachments)
      ResponseLedger.jsx     # typewriter reveal of the agent's recommendation
      TrustPanel.jsx          # reasoning + evidence per decision, expandable
```

## What's not wired up yet

- **Loading state polish** — `Console` shows "Thinking..." on the button
  during a request, but there's no dedicated loading animation for slower
  local inference. Worth adding once real latency on the demo machine is
  known — a good loading state matters more than it sounds, since it's the
  only thing covering for Ollama's response time live on stage.
- **Photo preview** — attached images aren't previewed before submit, just
  counted ("2 photo(s)"). Fine for now; nice-to-have before the actual demo.
- **Mobile packaging** — this is a responsive web app, not the installable
  offline mobile app from the P2 stretch goals. That's a separate, later
  step (see `saathi_build_plan.md`).
