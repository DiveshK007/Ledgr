"""
Seeds a demo SQLite DB for the Supplier Agent.

Run once before demoing:
    python db/seed_data.py

Creates one demo business ("Sharma Cement Traders") with a supplier history
that has a deliberate contrast built in — one supplier is cheap but
unreliable, one is pricier but rock-solid — so the agent's reasoning has
something real to weigh, not just a lowest-price sort.
"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "saathi.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def seed():
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    cur = conn.cursor()

    # Wipe existing demo rows so this script is safely re-runnable.
    for table in ("decision_log", "quote", "supplier", "ledger_entry", "customer",
                  "inventory_snapshot", "commitment", "product", "sales_history", "business"):
        cur.execute(f"DELETE FROM {table}")

    cur.execute(
        "INSERT INTO business (id, name, owner_name, city, trade_type) VALUES (?,?,?,?,?)",
        (1, "Sharma Cement Traders", "Ramesh Sharma", "Bengaluru", "cement retailer"),
    )

    suppliers = [
        # id, business_id, name, contact, avg_delay, on_time_rate, quality_issues, total_orders, notes
        (1, 1, "Balaji Building Materials", "+91-98xxxxxx01", 0.5, 0.95, 0, 22,
         "Reliable for 3 years. Slightly pricier but never late during festival season."),
        (2, 1, "Krishna Cement Suppliers", "+91-98xxxxxx02", 4.2, 0.60, 3, 15,
         "Cheapest quotes but delivery has slipped 3-5 days on 4 of last 15 orders. "
         "Two quality complaints on bag sealing last year."),
        (3, 1, "New Bengaluru Traders", "+91-98xxxxxx03", 0.0, 1.0, 0, 2,
         "New supplier, only 2 orders so far, both on time. Not enough history to trust fully yet."),
    ]
    cur.executemany(
        "INSERT INTO supplier (id, business_id, name, contact_info, avg_delivery_delay_days, "
        "on_time_rate, quality_issue_count, total_orders, notes) VALUES (?,?,?,?,?,?,?,?,?)",
        suppliers,
    )

    customers = [
        # id, business_id, name, contact, preferred_language, relationship_notes
        (1, 1, "Manjunath Stores", "+91-99xxxxxx11", "Kannada",
         "Regular for 5 years, never defaulted. Runs a small hardware shop nearby."),
        (2, 1, "Farooq Traders", "+91-99xxxxxx12", "English",
         "Newer customer, 8 months. Tends to pay in one lump sum after his own "
         "customers settle up, not on a fixed schedule."),
        (3, 1, "Lakshmi Constructions", "+91-99xxxxxx13", "Kannada",
         "Large contractor, big orders. Slow payer historically but always eventually pays in full."),
        (4, 1, "Rahul Enterprises", "+91-99xxxxxx14", "English",
         "New customer, first order. No history yet."),
    ]
    cur.executemany(
        "INSERT INTO customer (id, business_id, name, contact_info, preferred_language, "
        "relationship_notes) VALUES (?,?,?,?,?,?)",
        customers,
    )

    ledger_entries = [
        # id, business_id, customer_id, customer_name_raw, amount_due, transaction_date,
        # days_overdue, status_notes
        (1, 1, 1, "Manjunath Stores", 3200, "2026-06-20", 26,
         "Said he'll pay after his own Diwali stock clears. Been reliable every year."),
        (2, 1, 2, "Farooq Traders", 1800, "2026-07-01", 15,
         "Already sent one reminder two weeks ago, no response since."),
        (3, 1, 3, "Lakshmi Constructions", 42000, "2026-06-10", 36,
         "Large order, typical for them to run 30-45 days late. No response to first reminder yet."),
        (4, 1, 4, "Rahul Enterprises", 900, "2026-07-10", 6,
         "First order, small amount, too early to read into the delay."),
    ]
    cur.executemany(
        "INSERT INTO ledger_entry (id, business_id, customer_id, customer_name_raw, amount_due, "
        "transaction_date, days_overdue, status_notes) VALUES (?,?,?,?,?,?,?,?)",
        ledger_entries,
    )

    # Sharma Cement Traders also runs a small perishable side-counter (common
    # for general/hardware shops in India to diversify) — gives the Pricing
    # Agent two items with different urgency levels to reason over.
    products = [
        # id, business_id, name, category, unit, cost_price, normal_sell_price, perishable
        (1, 1, "Tomatoes", "vegetables", "kg", 15, 25, 1),
        (2, 1, "Bread loaves", "bakery", "unit", 20, 35, 1),
        (3, 1, "Cement", "building materials", "bag", 380, 430, 0),
    ]
    cur.executemany(
        "INSERT INTO product (id, business_id, name, category, unit, cost_price, "
        "normal_sell_price, perishable) VALUES (?,?,?,?,?,?,?,?)",
        products,
    )

    inventory_snapshots = [
        # id, business_id, product_id, quantity_on_hand, days_until_spoilage, snapshot_date, notes
        (1, 1, 1, 20, 2, "2026-07-16", "Starting to soften, need to move fast."),
        (2, 1, 2, 15, 1, "2026-07-16", "Baked yesterday, sell today or discard."),
        (3, 1, 3, 200, None, "2026-07-16", "Stable stock, no urgency."),
    ]
    cur.executemany(
        "INSERT INTO inventory_snapshot (id, business_id, product_id, quantity_on_hand, "
        "days_until_spoilage, snapshot_date, notes) VALUES (?,?,?,?,?,?,?)",
        inventory_snapshots,
    )

    # Ties back to the Lakshmi Constructions ledger entry — 120 of the 200
    # cement bags on hand are already spoken for, so the Operational
    # Planning Agent has something real to weigh a new order against.
    commitments = [
        # id, business_id, product_id, description, quantity_committed, due_date
        (1, 1, 3, "Lakshmi Constructions site delivery", 120, "2026-07-20"),
    ]
    cur.executemany(
        "INSERT INTO commitment (id, business_id, product_id, description, "
        "quantity_committed, due_date) VALUES (?,?,?,?,?,?)",
        commitments,
    )

    # 90 days of synthetic daily revenue for the Forecasting Agent: weekly
    # seasonality (weekends run ~30% higher), a mild upward trend, a 3-day
    # festival spike ~9 days before "today," and random noise — enough
    # structure for a real trend+seasonality model to actually find something.
    random.seed(42)
    today = datetime(2026, 7, 15)
    base_revenue = 8000
    trend_growth_total = 0.15
    n_days = 90

    sales_rows = []
    for i in range(n_days, 0, -1):
        day = today - timedelta(days=i)
        day_index = n_days - i
        trend_factor = 1 + trend_growth_total * (day_index / n_days)
        weekend_factor = 1.3 if day.weekday() in (5, 6) else 1.0
        festival_boost = 1.6 if 8 <= i <= 10 else 1.0
        noise = random.uniform(0.9, 1.1)
        revenue = round(base_revenue * trend_factor * weekend_factor * festival_boost * noise, 2)
        sales_rows.append((1, day.strftime("%Y-%m-%d"), revenue))

    cur.executemany(
        "INSERT INTO sales_history (business_id, sale_date, revenue) VALUES (?,?,?)",
        sales_rows,
    )

    conn.commit()
    conn.close()
    print(f"Seeded demo data at {DB_PATH}")


if __name__ == "__main__":
    seed()
