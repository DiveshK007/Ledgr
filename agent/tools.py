"""
Tool functions the Supplier Agent can call mid-reasoning, plus their schema
definitions for Ollama's function-calling. This is what makes it an agent
rather than a single prompt->answer call: Gemma decides when to call these,
based on what it's trying to figure out.

Two of these (calculate_effective_cost) are deliberately NOT LLM calls —
real arithmetic, not a model guessing numbers. Gemma orchestrates the tool;
the tool does the math.
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "saathi.db")


def _conn():
    return sqlite3.connect(DB_PATH)


def lookup_supplier_history(supplier_name: str) -> dict:
    """
    Fuzzy-matches a supplier name extracted from a photo against known
    suppliers in the local DB and returns their reliability history.
    Falls back to a clear "no history" signal for unknown suppliers instead
    of pretending they're neutral/safe.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, avg_delivery_delay_days, on_time_rate, "
        "quality_issue_count, total_orders, notes FROM supplier "
        "WHERE lower(name) LIKE ?",
        (f"%{supplier_name.lower().split()[0]}%",),
    )
    row = cur.fetchone()
    conn.close()

    if row is None:
        return {
            "known_supplier": False,
            "supplier_name": supplier_name,
            "note": "No transaction history with this supplier. Treat as unproven — "
            "flag this explicitly rather than assuming average reliability.",
        }

    return {
        "known_supplier": True,
        "supplier_id": row[0],
        "supplier_name": row[1],
        "avg_delivery_delay_days": row[2],
        "on_time_rate": row[3],
        "quality_issue_count": row[4],
        "total_orders": row[5],
        "notes": row[6],
    }


def calculate_effective_cost(
    unit_price: float,
    quantity: float,
    payment_terms_days: int,
    delivery_days: int,
    on_time_rate: float = 1.0,
) -> dict:
    """
    Real arithmetic, not an LLM guess. Produces an "effective cost" that
    factors in:
      - base cost (price x quantity)
      - a small time-value-of-money credit for longer payment terms
        (money you get to hold onto longer is worth something)
      - a delivery-risk penalty scaled by how unreliable the supplier's
        on-time rate has historically been

    The constants below are intentionally simple and explainable — a judge
    (or the shop owner) should be able to sanity-check this by hand, not
    have to trust a black box.
    """
    base_cost = unit_price * quantity

    # Assume a ~12% annual cost of capital; longer payment terms are worth
    # holding onto cash for. This is a small, explainable adjustment, not a
    # precision finance model.
    daily_capital_rate = 0.12 / 365
    payment_terms_credit = base_cost * daily_capital_rate * payment_terms_days

    # Penalize unreliable delivery: each 10% below a perfect on-time rate
    # adds a 1.5% risk premium to the effective cost, to represent the real
    # cost of production delays / lost sales from late stock.
    unreliability = max(0.0, 1.0 - on_time_rate)
    delivery_risk_penalty = base_cost * (unreliability * 0.15)

    effective_cost = base_cost - payment_terms_credit + delivery_risk_penalty

    return {
        "base_cost": round(base_cost, 2),
        "payment_terms_credit": round(payment_terms_credit, 2),
        "delivery_risk_penalty": round(delivery_risk_penalty, 2),
        "effective_cost": round(effective_cost, 2),
        "delivery_days_quoted": delivery_days,
    }


def draft_counter_offer(business_name: str, supplier_name: str, ask: str, language: str = "English") -> str:
    """
    Calls the LLM specifically for the drafting sub-task, using the
    counter-offer template. Kept as its own tool (rather than inline in the
    main reasoning call) so it's independently testable and swappable.
    """
    from llm_client import chat
    from prompts import COUNTER_OFFER_PROMPT_TEMPLATE

    prompt = COUNTER_OFFER_PROMPT_TEMPLATE.format(
        business_name=business_name, supplier_name=supplier_name, ask=ask, language=language
    )
    response = chat([{"role": "user", "content": prompt}])
    return response["message"]["content"]


def log_decision(business_id: int, agent_name: str, subject_ids: list[int],
                  reasoning: str, details: dict, drafted_messages: dict | None = None) -> None:
    """
    Persists a decision + reasoning so the trust panel can show it later.
    Shared across all specialist agents — pass whatever ids were being
    decided on (quote ids, ledger entry ids, ...) and an agent-specific
    details dict.
    """
    conn = _conn()
    conn.execute(
        "INSERT INTO decision_log (business_id, agent_name, subject_ids, "
        "reasoning, details_json, drafted_messages_json, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            business_id,
            agent_name,
            ",".join(str(s) for s in subject_ids),
            reasoning,
            json.dumps(details),
            json.dumps(drafted_messages or {}),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


# --- Collections Agent tools ------------------------------------------------

def get_ledger_snapshot(business_id: int) -> list[dict]:
    """
    Returns every open ledger entry for the business, joined with whatever
    customer relationship notes exist. This is the Collections Agent's main
    grounding source — the free-text notes are exactly the unstructured
    human context a spreadsheet sort can't use but Gemma can reason over.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT le.id, le.customer_name_raw, le.amount_due, le.days_overdue,
               le.status_notes, c.name, c.relationship_notes, c.preferred_language
        FROM ledger_entry le
        LEFT JOIN customer c ON le.customer_id = c.id
        WHERE le.business_id = ?
        ORDER BY le.days_overdue DESC
        """,
        (business_id,),
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "ledger_entry_id": r[0],
            "customer_name": r[5] or r[1],
            "amount_due": r[2],
            "days_overdue": r[3],
            "status_notes": r[4],
            "relationship_notes": r[6],
            "preferred_language": r[7] or "English",
        }
        for r in rows
    ]


def calculate_urgency_score(amount_due: float, days_overdue: int) -> dict:
    """
    Real arithmetic baseline, same philosophy as calculate_effective_cost:
    give Gemma a real number to anchor on, but it's explicitly a BASELINE —
    the system prompt tells Gemma to adjust this using relationship_notes
    and status_notes, not treat it as the final answer. A pure formula
    would rank a struggling loyal customer the same as a flaky new one;
    that's exactly the judgment call this tool intentionally leaves open.
    """
    # Normalize: amount matters, but overdue time compounds risk of never
    # collecting at all, so it's weighted slightly heavier.
    baseline_score = (amount_due * 0.4) + (days_overdue * amount_due * 0.01)
    return {
        "baseline_urgency_score": round(baseline_score, 2),
        "note": "This is a baseline only — weigh it against relationship_notes "
        "and status_notes before deciding who to actually chase first.",
    }


def draft_reminder_message(business_name: str, customer_name: str, amount_due: float,
                            approach: str, language: str = "English") -> str:
    """
    Calls the LLM for the drafting sub-task. `approach` should be a short
    instruction from the reasoning step, e.g. "soft nudge, mention we value
    the long relationship" or "firmer tone, second reminder, propose a
    partial payment plan".
    """
    from llm_client import chat
    from prompts import REMINDER_MESSAGE_PROMPT_TEMPLATE

    prompt = REMINDER_MESSAGE_PROMPT_TEMPLATE.format(
        business_name=business_name, customer_name=customer_name,
        amount_due=amount_due, approach=approach, language=language,
    )
    response = chat([{"role": "user", "content": prompt}])
    return response["message"]["content"]


# --- Pricing Agent tools -----------------------------------------------------

def get_inventory_snapshot(business_id: int) -> list[dict]:
    """
    Returns the latest inventory snapshot per product, joined with product
    pricing info. Filters to perishables with a spoilage window set — the
    Pricing Agent (P0) is scoped to the "about to spoil" decision, not
    general SKU pricing.

    "Latest" matters now that camera-based grounding can insert a fresh
    snapshot on top of the seeded one — the subquery picks the
    highest-id (most recent) row per product so a new camera read
    supersedes the manually seeded baseline instead of both showing up.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.id, p.id, p.name, p.category, p.unit, p.cost_price, p.normal_sell_price,
               s.quantity_on_hand, s.days_until_spoilage, s.notes
        FROM inventory_snapshot s
        JOIN product p ON s.product_id = p.id
        WHERE s.business_id = ? AND p.perishable = 1
          AND s.id = (
              SELECT MAX(s2.id) FROM inventory_snapshot s2
              WHERE s2.product_id = s.product_id AND s2.business_id = s.business_id
          )
        ORDER BY s.days_until_spoilage ASC
        """,
        (business_id,),
    )
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "snapshot_id": r[0],
            "product_id": r[1],
            "product_name": r[2],
            "category": r[3],
            "unit": r[4],
            "cost_price": r[5],
            "normal_sell_price": r[6],
            "quantity_on_hand": r[7],
            "days_until_spoilage": r[8],
            "notes": r[9],
        }
        for r in rows
    ]


def calculate_markdown_scenarios(cost_price: float, normal_sell_price: float,
                                  quantity: float, days_until_spoilage: int) -> dict:
    """
    Real arithmetic, not an LLM guess. Models the actual tradeoff a shop
    owner is weighing: hold at full price and risk losing unsold stock
    entirely, or discount now to move it faster.

    Sell-through-rate model is a deliberately simple, explainable heuristic:
      - base sell-through at full price starts at 40%
      - each 10% discount adds ~8 points of sell-through
      - the closer spoilage is, the more urgency boosts sell-through too
        (a visible "must go today" markdown moves stock faster)
    These constants are estimates meant to be sanity-checked by eye, not a
    precision model — swap in real historical sell-through data if/when
    you have it.
    """
    urgency_factor = max(0.1, 1.0 - (days_until_spoilage / 7))

    scenarios = []
    for discount_pct in (0, 10, 20, 30, 40, 50):
        price = normal_sell_price * (1 - discount_pct / 100)
        sell_through_rate = min(
            1.0, 0.40 + (discount_pct / 100) * 0.8 + urgency_factor * 0.15
        )
        units_sold = quantity * sell_through_rate
        units_wasted = quantity - units_sold
        revenue = units_sold * price
        total_cost = quantity * cost_price
        profit = revenue - total_cost

        scenarios.append(
            {
                "discount_pct": discount_pct,
                "price_per_unit": round(price, 2),
                "estimated_units_sold": round(units_sold, 1),
                "estimated_units_wasted": round(units_wasted, 1),
                "estimated_revenue": round(revenue, 2),
                "estimated_profit": round(profit, 2),
            }
        )

    return {
        "urgency_factor": round(urgency_factor, 2),
        "scenarios": scenarios,
        "note": "estimated_profit already subtracts full inventory cost, so a "
        "positive number even at a deep discount usually beats risking total spoilage.",
    }


def draft_markdown_announcement(business_name: str, product_name: str, discount_pct: float,
                                 language: str = "English") -> str:
    """Calls the LLM for the announcement-drafting sub-task."""
    from llm_client import chat
    from prompts import MARKDOWN_ANNOUNCEMENT_PROMPT_TEMPLATE

    prompt = MARKDOWN_ANNOUNCEMENT_PROMPT_TEMPLATE.format(
        business_name=business_name, product_name=product_name,
        discount_pct=discount_pct, language=language,
    )
    response = chat([{"role": "user", "content": prompt}])
    return response["message"]["content"]


# --- Forecasting Agent tools -------------------------------------------------

def forecast_revenue(business_id: int, horizon_days: int) -> dict:
    """
    Real statistics, not an LLM guess: fits a linear trend over daily
    revenue history via ordinary least squares, then layers on day-of-week
    seasonality computed from the residuals, and projects forward
    horizon_days. Pure Python stdlib — no numpy/pandas dependency, so it
    doesn't add install friction on hackathon day.

    This is intentionally simple (linear trend + weekday seasonality, no
    holiday calendar beyond what naturally shows up in the trend) so it
    stays explainable and debuggable under time pressure. Gemma's job is to
    interpret this output, not to produce its own numbers.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT sale_date, revenue FROM sales_history WHERE business_id = ? ORDER BY sale_date ASC",
        (business_id,),
    )
    rows = cur.fetchall()
    conn.close()

    if len(rows) < 14:
        return {
            "confidence": "low",
            "reason": f"Only {len(rows)} days of history — need at least 14 for a "
            "trustworthy trend. Treat any forecast from this as a rough guess.",
        }

    dates = [datetime.strptime(r[0], "%Y-%m-%d") for r in rows]
    revenues = [r[1] for r in rows]
    n = len(rows)
    xs = list(range(n))  # day index, 0-based

    # Ordinary least squares: revenue ~ a + b * day_index
    sum_x, sum_y = sum(xs), sum(revenues)
    sum_xy = sum(x * y for x, y in zip(xs, revenues))
    sum_xx = sum(x * x for x in xs)
    denom = n * sum_xx - sum_x * sum_x
    b = (n * sum_xy - sum_x * sum_y) / denom if denom else 0.0
    a = (sum_y - b * sum_x) / n

    # Day-of-week seasonality from residual ratios (actual / trend-predicted).
    weekday_ratios: dict[int, list[float]] = {i: [] for i in range(7)}
    for x, date, actual in zip(xs, dates, revenues):
        predicted = a + b * x
        if predicted > 0:
            weekday_ratios[date.weekday()].append(actual / predicted)
    seasonal_factor = {
        wd: (sum(ratios) / len(ratios) if ratios else 1.0)
        for wd, ratios in weekday_ratios.items()
    }

    last_date = dates[-1]
    daily_forecast = []
    for step in range(1, horizon_days + 1):
        future_x = n - 1 + step
        future_date = last_date + timedelta(days=step)
        trend_value = a + b * future_x
        predicted = max(0.0, trend_value * seasonal_factor[future_date.weekday()])
        daily_forecast.append(
            {"date": future_date.strftime("%Y-%m-%d"), "predicted_revenue": round(predicted, 2)}
        )

    total_forecast = sum(d["predicted_revenue"] for d in daily_forecast)
    trend_pct_over_history = ((a + b * (n - 1)) / a - 1) * 100 if a else 0.0

    return {
        "confidence": "medium" if n < 45 else "high",
        "history_days_used": n,
        "daily_trend_slope": round(b, 2),   # revenue change per day
        "trend_growth_over_history_pct": round(trend_pct_over_history, 1),
        "seasonal_factors_by_weekday": {  # 0=Mon ... 6=Sun
            wd: round(f, 2) for wd, f in seasonal_factor.items()
        },
        "horizon_days": horizon_days,
        "total_forecast_revenue": round(total_forecast, 2),
        "daily_forecast": daily_forecast,
    }


# --- Operational Planning Agent tools ----------------------------------------

def check_order_feasibility(product_name: str, requested_quantity: float,
                             requested_discount_pct: float = 0.0) -> dict:
    """
    Real arithmetic, not an LLM guess. Checks current stock against
    existing commitments to see what's actually free to sell, and
    computes true profit at the requested price. Feasibility and
    profitability are reported separately — an order can be feasible to
    fulfill but still a bad idea to accept.
    """
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, cost_price, normal_sell_price FROM product WHERE lower(name) LIKE ?",
        (f"%{product_name.lower()}%",),
    )
    product_row = cur.fetchone()
    if product_row is None:
        conn.close()
        return {"error": f"No product found matching '{product_name}'."}
    product_id, cost_price, normal_sell_price = product_row

    cur.execute(
        "SELECT COALESCE(SUM(quantity_on_hand), 0) FROM inventory_snapshot WHERE product_id = ?",
        (product_id,),
    )
    stock_on_hand = cur.fetchone()[0]

    cur.execute(
        "SELECT COALESCE(SUM(quantity_committed), 0) FROM commitment WHERE product_id = ?",
        (product_id,),
    )
    already_committed = cur.fetchone()[0]
    conn.close()

    available_stock = stock_on_hand - already_committed
    can_fulfill = available_stock >= requested_quantity
    shortfall = max(0.0, requested_quantity - available_stock)

    effective_price = normal_sell_price * (1 - requested_discount_pct / 100)
    profit_per_unit = effective_price - cost_price
    total_profit = profit_per_unit * requested_quantity
    margin_pct = (profit_per_unit / effective_price * 100) if effective_price else 0.0

    return {
        "product_name": product_name,
        "stock_on_hand": stock_on_hand,
        "already_committed": already_committed,
        "available_stock": available_stock,
        "requested_quantity": requested_quantity,
        "can_fulfill": can_fulfill,
        "shortfall": round(shortfall, 2),
        "effective_price_per_unit": round(effective_price, 2),
        "profit_per_unit": round(profit_per_unit, 2),
        "total_profit": round(total_profit, 2),
        "margin_pct": round(margin_pct, 1),
    }


def draft_order_response(business_name: str, decision: str, context: str, language: str = "English") -> str:
    """Calls the LLM for the response-drafting sub-task."""
    from llm_client import chat
    from prompts import ORDER_RESPONSE_PROMPT_TEMPLATE

    prompt = ORDER_RESPONSE_PROMPT_TEMPLATE.format(
        business_name=business_name, decision=decision, context=context, language=language,
    )
    response = chat([{"role": "user", "content": prompt}])
    return response["message"]["content"]


# --- Cash Flow Agent tools ---------------------------------------------------

def check_cash_flow(business_id: int, window_days: int = 14,
                    pending_expense: float = 0.0) -> dict:
    """
    Real arithmetic, not an LLM guess. Projects a daily net cash position
    across `window_days` and reports whether/when it goes negative, how big
    the gap is, and the single receivable that could close it.

    Model — deliberately conservative and honest about what data exists:

      Cash IN  : each day's forecasted revenue from forecast_revenue() (a
                 real trend + seasonality model), passed through day by day.
                 No smoothing, no extra model.

      Cash OUT : the ONLY outflow modeled is `pending_expense`, an optional
                 one-off amount the owner is explicitly asking about
                 ("can I afford a Rs 15,000 supplier payment?"), applied up
                 front (day 1) as the conservative reading of near-term
                 liquidity.

      Receivables (outstanding ledger_entry rows) are NOT auto-counted as
      cash-in. ledger_entry has no due_date — only days_overdue — so there
      is no future date to project a collection from, and inventing one is
      exactly the unverifiable number this project avoids. Instead a
      receivable is used only as the LEVER: if the projection goes negative,
      surface the single outstanding receivable large enough to close the
      gap, so the owner gets a concrete action ("chase Lakshmi
      Constructions - Rs 42,000 covers the shortfall") rather than a guessed
      collection date.

    DOCUMENTED LIMITATION (v1): this schema has no table of scheduled
    supplier payables (money owed OUT, with due dates). `commitment` rows
    are inventory promised to a customer (quantity + due_date) — a future
    cash-IN when the sale completes, NOT a payable — so they are
    deliberately NOT treated as cash-out here. Real recurring/ scheduled
    payables are out of scope until the schema models them; the
    `pending_expense` argument is the honest stand-in for "can I afford this
    specific payment", instead of pretending the DB already tracks it.

    Returns goes_negative, negative_date, shortfall_amount, largest_lever,
    the daily projection, and the underlying forecast confidence.
    """
    forecast = forecast_revenue(business_id, window_days)

    # Honest degradation: no trustworthy forecast -> do not fabricate a
    # cash-flow projection on top of one.
    if forecast.get("confidence") == "low" or "daily_forecast" not in forecast:
        return {
            "goes_negative": None,
            "confidence": "low",
            "reason": forecast.get(
                "reason", "Not enough sales history to project cash flow."
            ),
            "window_days": window_days,
            "pending_expense": round(float(pending_expense), 2),
            "negative_date": None,
            "shortfall_amount": 0.0,
            "largest_lever": None,
        }

    daily = forecast["daily_forecast"]  # [{date, predicted_revenue}, ...]

    # Project net cash FLOW across the window, starting from 0. There is no
    # bank-balance figure in the schema, so this is projected flow (does the
    # window's income cover the outflow), not an absolute balance. The one-off
    # pending_expense is charged on day 1 and offset by that day's forecasted
    # revenue; every later day only adds revenue, so the deepest dip is
    # simply whichever end-of-day running total is lowest. worst starts at 0
    # (not -pending_expense) so a trivially small expense the day's revenue
    # already covers does NOT get flagged as a crunch.
    projection = []
    cumulative = -float(pending_expense)
    worst = 0.0                           # most negative end-of-day position
    negative_date = None
    for d in daily:
        cumulative += d["predicted_revenue"]
        if cumulative < worst:
            worst = cumulative
        if cumulative < 0 and negative_date is None:
            negative_date = d["date"]
        projection.append({
            "date": d["date"],
            "cash_in": d["predicted_revenue"],
            "cumulative_position": round(cumulative, 2),
        })

    goes_negative = worst < 0
    shortfall_amount = round(-worst, 2) if goes_negative else 0.0

    # Receivables lever: the largest single outstanding receivable, and
    # whether it alone covers the gap. No timing assumption is made.
    largest_lever = None
    if goes_negative:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT le.id, COALESCE(c.name, le.customer_name_raw, ''),
                   le.amount_due, le.days_overdue
            FROM ledger_entry le
            LEFT JOIN customer c ON le.customer_id = c.id
            WHERE le.business_id = ?
            ORDER BY le.amount_due DESC
            """,
            (business_id,),
        )
        top = cur.fetchone()
        conn.close()
        if top is not None:
            largest_lever = {
                "type": "receivable",
                "ledger_entry_id": top[0],
                "customer_name": top[1],
                "amount": round(top[2], 2),
                "days_overdue": top[3],
                "covers_shortfall": top[2] >= shortfall_amount,
            }

    return {
        "goes_negative": goes_negative,
        "negative_date": negative_date,
        "shortfall_amount": shortfall_amount,
        "largest_lever": largest_lever,
        "window_days": window_days,
        "pending_expense": round(float(pending_expense), 2),
        "projected_cash_in_total": round(
            sum(d["predicted_revenue"] for d in daily), 2
        ),
        "confidence": forecast.get("confidence"),
        "daily_projection": projection,
        "limitation": "No scheduled supplier payables exist in this schema; only the "
        "optional pending_expense is modeled as cash-out, and receivables are used as a "
        "lever (no collection-date data to auto-count them as cash-in).",
    }


def draft_cash_flow_alert(business_name: str, summary: str, language: str = "English") -> str:
    """Calls the LLM for the cash-flow alert drafting sub-task, using the
    already-computed projection summary — kept as its own tool, like the other
    draft_* helpers, so it's independently testable and swappable."""
    from llm_client import chat
    from prompts import CASH_FLOW_ALERT_PROMPT_TEMPLATE

    prompt = CASH_FLOW_ALERT_PROMPT_TEMPLATE.format(
        business_name=business_name, summary=summary, language=language,
    )
    response = chat([{"role": "user", "content": prompt}])
    return response["message"]["content"]


# --- Ollama function-calling schema ---------------------------------------
# Passed to llm_client.chat(tools=TOOL_SCHEMA) so Gemma knows what it can call.

TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "lookup_supplier_history",
            "description": "Look up a supplier's delivery reliability and quality history from past orders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_name": {"type": "string", "description": "Supplier name as extracted from the quote"}
                },
                "required": ["supplier_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_effective_cost",
            "description": "Compute the true effective cost of a quote, factoring in payment terms and delivery reliability, not just sticker price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "unit_price": {"type": "number"},
                    "quantity": {"type": "number"},
                    "payment_terms_days": {"type": "integer"},
                    "delivery_days": {"type": "integer"},
                    "on_time_rate": {"type": "number"},
                },
                "required": ["unit_price", "quantity", "payment_terms_days", "delivery_days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_urgency_score",
            "description": "Compute a baseline urgency score for a ledger entry, to be adjusted using relationship and status notes before deciding who to follow up with.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount_due": {"type": "number"},
                    "days_overdue": {"type": "integer"},
                },
                "required": ["amount_due", "days_overdue"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_markdown_scenarios",
            "description": "Compute real expected revenue/profit at several discount levels for stock at risk of spoiling, to compare against the risk of losing it entirely.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cost_price": {"type": "number"},
                    "normal_sell_price": {"type": "number"},
                    "quantity": {"type": "number"},
                    "days_until_spoilage": {"type": "integer"},
                },
                "required": ["cost_price", "normal_sell_price", "quantity", "days_until_spoilage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_revenue",
            "description": "Produce a real statistical revenue forecast (linear trend + day-of-week seasonality) over a given horizon, based on historical daily sales.",
            "parameters": {
                "type": "object",
                "properties": {
                    "business_id": {"type": "integer"},
                    "horizon_days": {"type": "integer"},
                },
                "required": ["business_id", "horizon_days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_order_feasibility",
            "description": "Check whether a bulk order can be fulfilled given current stock and existing commitments, and compute the real profit at the requested price/discount.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {"type": "string"},
                    "requested_quantity": {"type": "number"},
                    "requested_discount_pct": {"type": "number"},
                },
                "required": ["product_name", "requested_quantity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_cash_flow",
            "description": "Project the business's daily net cash position over a window from forecasted revenue (cash-in) and an optional one-off pending_expense (cash-out), flag whether/when it goes negative, and surface the single outstanding receivable large enough to close any gap.",
            "parameters": {
                "type": "object",
                "properties": {
                    "business_id": {"type": "integer"},
                    "window_days": {"type": "integer"},
                    "pending_expense": {"type": "number", "description": "One-off expense the owner is asking whether they can afford; 0 if none."},
                },
                "required": ["business_id", "window_days"],
            },
        },
    },
]
