"""
Pure math tests for check_cash_flow — no Ollama, same philosophy as
test_tools_math.py: this is the deterministic core of the Cash Flow Agent,
so it gets real pass/fail coverage. Runs in well under a second.

    pytest tests/test_cash_flow_math.py -v

Cash-flow model under test (see tools.check_cash_flow docstring):
  - cash IN  = forecast_revenue()'s daily output, day by day
  - cash OUT = only the optional one-off `pending_expense` (applied up front)
  - receivables are the LEVER (no collection-date guessing), not auto cash-in
  - `commitment` rows are NOT payables (no supplier-payable table exists)
"""

import tools


def test_cash_flow_healthy_stays_positive_through_window():
    # (a) Seeded business, no one-off expense: forecast revenue only ever
    # adds to the position, so it can never dip below zero.
    result = tools.check_cash_flow(business_id=1, window_days=14)
    assert result["goes_negative"] is False
    assert result["shortfall_amount"] == 0.0
    assert result["negative_date"] is None
    assert result["largest_lever"] is None
    assert result["confidence"] in ("medium", "high")
    assert len(result["daily_projection"]) == 14


def test_cash_flow_shortfall_surfaces_receivable_that_covers_the_gap():
    # (b) A one-off Rs 30,000 supplier payment lands before the window's
    # forecasted revenue can cover it -> the position goes negative, and the
    # largest outstanding receivable (Lakshmi Constructions, ledger id 3,
    # Rs 42,000 in the seed) is surfaced as the lever that closes the gap.
    result = tools.check_cash_flow(business_id=1, window_days=14, pending_expense=30000)
    assert result["goes_negative"] is True
    assert result["negative_date"] is not None
    assert 0 < result["shortfall_amount"] <= 30000
    lever = result["largest_lever"]
    assert lever is not None
    assert lever["type"] == "receivable"
    assert lever["ledger_entry_id"] == 3          # Lakshmi Constructions
    assert lever["amount"] == 42000
    assert lever["covers_shortfall"] is True       # 42,000 >= shortfall


def test_cash_flow_shortfall_too_large_for_any_single_receivable():
    # (c, reframed) Original stress-case (c) — "shortfall purely from a
    # forecasted slow patch with no near-term payables" — is NOT realizable
    # under the agreed model: with pending_expense=0 and forecast revenue
    # always >= 0 the position is monotonically non-decreasing and can never
    # go negative (a slow patch only lowers growth). This substitute case is
    # both realizable and distinct: a Rs 5,00,000 payment dwarfs the biggest
    # single receivable, so the lever is still surfaced but honestly reports
    # it does NOT fully cover the gap.
    result = tools.check_cash_flow(business_id=1, window_days=14, pending_expense=500000)
    assert result["goes_negative"] is True
    assert result["shortfall_amount"] > 42000
    lever = result["largest_lever"]
    assert lever is not None
    assert lever["ledger_entry_id"] == 3           # still the largest receivable
    assert lever["covers_shortfall"] is False      # 42,000 < shortfall


def test_cash_flow_no_history_degrades_honestly():
    # (d) business_id 999 has no seeded sales_history, so forecast_revenue is
    # low-confidence. check_cash_flow must NOT fabricate a projection on top
    # of that — it reports low confidence and a null cash-flow verdict.
    result = tools.check_cash_flow(business_id=999, window_days=14)
    assert result["goes_negative"] is None
    assert result["confidence"] == "low"
    assert result["largest_lever"] is None
    assert "reason" in result
