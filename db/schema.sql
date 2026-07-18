-- Ledgr: Supplier Agent data schema
-- Lightweight local knowledge graph (SQLite) instead of a flat vector store.
-- Grows into shared schema for Collections/Pricing/Forecasting agents later —
-- keep new agents adding tables here rather than spinning up separate DBs.

CREATE TABLE IF NOT EXISTS business (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    owner_name TEXT,
    city TEXT,
    trade_type TEXT          -- e.g. "cement retailer", "textile trader"
);

CREATE TABLE IF NOT EXISTS supplier (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    name TEXT NOT NULL,
    contact_info TEXT,
    -- Rolling reliability signals, updated after every transaction.
    avg_delivery_delay_days REAL DEFAULT 0,
    on_time_rate REAL DEFAULT 1.0,       -- 0.0 - 1.0
    quality_issue_count INTEGER DEFAULT 0,
    total_orders INTEGER DEFAULT 0,
    notes TEXT                            -- free-text history: "late twice during Diwali rush", etc.
);

CREATE TABLE IF NOT EXISTS quote (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    supplier_id INTEGER REFERENCES supplier(id),   -- NULL until matched to a known supplier
    supplier_name_raw TEXT,                         -- name as extracted from the photo, pre-matching
    item TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT,                                       -- "kg", "bags", "units"
    unit_price REAL NOT NULL,
    payment_terms_days INTEGER DEFAULT 0,            -- 0 = cash on delivery
    delivery_days INTEGER,
    source_image_path TEXT,                          -- photographed/scanned quote slip
    extracted_at TEXT,                                -- ISO timestamp
    raw_extraction_json TEXT                          -- full structured output from Gemma vision, for audit/debug
);

CREATE TABLE IF NOT EXISTS customer (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    name TEXT NOT NULL,
    contact_info TEXT,
    preferred_language TEXT DEFAULT 'English',
    relationship_notes TEXT     -- free-text: "regular for 5 years, never defaulted", etc.
);

CREATE TABLE IF NOT EXISTS ledger_entry (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    customer_id INTEGER REFERENCES customer(id),
    customer_name_raw TEXT,                -- name as extracted from a photographed ledger page, pre-matching
    amount_due REAL NOT NULL,
    transaction_date TEXT,
    days_overdue INTEGER DEFAULT 0,
    status_notes TEXT,                     -- free-text: "said he'll pay after harvest", "already reminded twice, ignored"
    source_image_path TEXT,                -- photographed ledger page, if extracted from one
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS product (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    name TEXT NOT NULL,
    category TEXT,
    unit TEXT,                        -- "kg", "dozen", "litre"
    cost_price REAL NOT NULL,
    normal_sell_price REAL NOT NULL,
    perishable INTEGER DEFAULT 0      -- 0/1 boolean
);

CREATE TABLE IF NOT EXISTS inventory_snapshot (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    product_id INTEGER NOT NULL REFERENCES product(id),
    quantity_on_hand REAL NOT NULL,
    days_until_spoilage INTEGER,      -- NULL for non-perishables
    snapshot_date TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS sales_history (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    sale_date TEXT NOT NULL,     -- ISO date, one row per day
    revenue REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS commitment (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    product_id INTEGER NOT NULL REFERENCES product(id),
    description TEXT,             -- "Lakshmi Constructions site delivery"
    quantity_committed REAL NOT NULL,
    due_date TEXT
);

-- Generalized across all specialist agents so the trust panel can read one
-- table regardless of which agent produced the decision.
CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY,
    business_id INTEGER NOT NULL REFERENCES business(id),
    agent_name TEXT NOT NULL,           -- "supplier", "collections", etc.
    subject_ids TEXT,                    -- comma-separated ids of whatever was being decided on (quotes, ledger entries...)
    reasoning TEXT,                      -- Gemma's explanation, shown in the trust panel
    details_json TEXT,                   -- agent-specific structured payload (cost breakdown, priority ranking, etc.)
    drafted_messages_json TEXT,          -- any drafted outbound messages, keyed by recipient
    created_at TEXT
);
