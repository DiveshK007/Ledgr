# Ledgr — Architecture

Six specialist agents behind one planner, a deterministic math/DB layer that the model is required to call rather than guess through, and a single local model (`gemma4:12b` via Ollama) that never talks to the network. This diagram traces a request from the browser down to SQLite and back.

```mermaid
graph TD
    classDef client fill:#e4ede5,stroke:#3f6b52,color:#1f3a2b
    classDef api fill:#f1e7d3,stroke:#96631e,color:#5c3d10
    classDef planner fill:#f5e6e2,stroke:#a3392f,color:#6b2019
    classDef agent fill:#ffffff,stroke:#6b5a44,color:#241d15
    classDef tool fill:#eef2f7,stroke:#4a6fa5,color:#1c2e44
    classDef model fill:#2b2117,stroke:#2b2117,color:#f3e9d2
    classDef data fill:#ece1c8,stroke:#8a7657,color:#2b2117
    classDef voice fill:#f1e7d3,stroke:#96631e,color:#5c3d10

    UI["React UI — localhost:5173<br/>ask box · six agent tabs · trust panel · mic"]:::client

    subgraph API["Flask API — app.py (127.0.0.1:5000)"]
        ASK["POST /api/ask"]
        VOICE_EP["POST /api/ask-voice"]
        TRUST_EP["GET /api/trust-panel"]
        MISC_EP["GET /api/agents · /api/health"]
    end
    class ASK,VOICE_EP,TRUST_EP,MISC_EP api

    subgraph PLANNER["planner.py"]
        ROUTE["route()<br/>dispatch to specialist"]
        CLASSIFY["classify()<br/>routing prompt → category"]
    end
    class ROUTE,CLASSIFY planner

    subgraph AGENTS["agent/*.py — six specialists<br/>perceive → retrieve → reason (tool-calling) → act"]
        SUP["Supplier"]
        COL["Collections"]
        PRC["Pricing"]
        FCT["Forecasting"]
        OPS["Operations"]
        CSH["Cash Flow"]
    end
    class SUP,COL,PRC,FCT,OPS,CSH agent

    subgraph TOOLS["tools.py — deterministic Python, never an LLM guess"]
        GROUND["grounding reads<br/>lookup_supplier_history · get_ledger_snapshot · get_inventory_snapshot"]
        T1["calculate_effective_cost"]
        T2["calculate_urgency_score"]
        T3["calculate_markdown_scenarios"]
        T4["forecast_revenue"]
        T5["check_order_feasibility"]
        T6["check_cash_flow"]
        CSHDRAFT["draft_cash_flow_alert()<br/>only if shortfall detected"]
        LOG["log_decision()"]
    end
    class GROUND,T1,T2,T3,T4,T5,T6,CSHDRAFT,LOG tool

    OLLAMA["Ollama — local, offline<br/>gemma4:12b · vision + function-calling"]:::model

    subgraph VOICEIO["voice.py — offline"]
        STT["faster-whisper STT"]
        TTS["pyttsx3 TTS"]
    end
    class STT,TTS voice

    DB[("db/saathi.db — SQLite<br/>business · supplier · customer · ledger_entry<br/>product · inventory_snapshot · sales_history<br/>commitment · decision_log")]:::data

    UI --> ASK
    UI --> VOICE_EP
    UI --> TRUST_EP
    UI --> MISC_EP

    ASK --> ROUTE
    VOICE_EP --> STT --> ROUTE
    ROUTE --> CLASSIFY --> OLLAMA
    ROUTE -.order parsing, operations only.-> OLLAMA

    ROUTE --> SUP
    ROUTE --> COL
    ROUTE --> PRC
    ROUTE --> FCT
    ROUTE --> OPS
    ROUTE --> CSH

    SUP --> GROUND
    SUP --> T1
    COL --> GROUND
    COL --> T2
    PRC --> GROUND
    PRC --> T3
    FCT --> T4
    OPS --> T5
    CSH --> T6
    CSH -.internally calls.-> T4

    SUP --> OLLAMA
    COL --> OLLAMA
    PRC --> OLLAMA
    FCT --> OLLAMA
    OPS --> OLLAMA
    CSH --> OLLAMA
    SUP -.vision: quote photos.-> OLLAMA
    PRC -.vision: shelf photos.-> OLLAMA
    CSH --> CSHDRAFT --> OLLAMA

    SUP --> LOG
    COL --> LOG
    PRC --> LOG
    FCT --> LOG
    OPS --> LOG
    CSH --> LOG

    GROUND --> DB
    T4 --> DB
    T5 --> DB
    T6 --> DB
    LOG --> DB
    DB --> TRUST_EP

    VOICE_EP --> TTS --> UI
```

## Reading the diagram

- **One model, two jobs, zero network calls.** Every box that touches `OLLAMA` is talking to a local `gemma4:12b` instance — routing classification, vision extraction, tool-calling reasoning, and message drafting all happen on-device. Nothing here ever leaves the machine.
- **The model never invents a number.** Each agent's calculation runs through a real Python function in `tools.py` — `calculate_effective_cost`, `forecast_revenue`, `check_cash_flow`, etc. — before Gemma is allowed to reason over the result. The model interprets; it doesn't compute.
- **`tools.py` is the only thing that touches SQLite.** Agents and the planner never open a DB connection directly — every grounding read and every write (including `log_decision`) goes through this one module, which is what makes the trust panel a complete, honest audit trail rather than a UI built on top of scattered writes.
- **Cash Flow is the odd one out, on purpose.** It's the only agent with a second, conditional LLM call (`draft_cash_flow_alert`) — it only fires when `check_cash_flow` actually reports a shortfall, so a healthy cash position never manufactures an alert.
- **Voice is a wrapper, not a fork.** `/api/ask-voice` transcribes offline (faster-whisper), then hands the transcript to the exact same `planner.route()` every typed query goes through — there's no separate voice-only logic path to keep in sync.
