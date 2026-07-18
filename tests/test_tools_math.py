"""
Pure math tests for the deterministic tool functions. Deliberately no
Ollama dependency here — these are exactly the parts of the system that
CAN be tested with a real pass/fail, since they're arithmetic, not model
output. Run these on their own with:

    pytest tests/test_tools_math.py -v
"""

import tools


def test_effective_cost_narrows_the_raw_price_gap():
    # A reliable supplier at a higher sticker price vs. a cheaper but
    # unreliable one -- the effective-cost adjustment (payment terms
    # credit + delivery risk penalty) should narrow the raw price gap,
    # not just mirror the sticker price difference.
    reliable = tools.calculate_effective_cost(
        unit_price=420, quantity=50, payment_terms_days=15, delivery_days=2, on_time_rate=0.95
    )
    cheap_unreliable = tools.calculate_effective_cost(
        unit_price=390, quantity=50, payment_terms_days=0, delivery_days=4, on_time_rate=0.60
    )
    reliable_premium = reliable["effective_cost"] - cheap_unreliable["effective_cost"]
    raw_price_gap = (420 - 390) * 50
    assert reliable_premium < raw_price_gap


def test_effective_cost_handles_zero_quantity_safely():
    result = tools.calculate_effective_cost(unit_price=100, quantity=0, payment_terms_days=10, delivery_days=2)
    assert result["base_cost"] == 0
    assert result["effective_cost"] == 0


def test_urgency_score_scales_with_amount_and_overdue_days():
    small_recent = tools.calculate_urgency_score(amount_due=500, days_overdue=5)
    large_overdue = tools.calculate_urgency_score(amount_due=40000, days_overdue=40)
    assert large_overdue["baseline_urgency_score"] > small_recent["baseline_urgency_score"]


def test_markdown_scenarios_deeper_discount_sells_more_units():
    result = tools.calculate_markdown_scenarios(cost_price=15, normal_sell_price=25, quantity=20, days_until_spoilage=2)
    by_discount = {s["discount_pct"]: s for s in result["scenarios"]}
    assert by_discount[50]["estimated_units_sold"] > by_discount[0]["estimated_units_sold"]


def test_markdown_scenarios_profit_accounts_for_full_inventory_cost():
    result = tools.calculate_markdown_scenarios(cost_price=15, normal_sell_price=25, quantity=20, days_until_spoilage=2)
    total_cost = 15 * 20
    for s in result["scenarios"]:
        implied = s["estimated_revenue"] - total_cost
        assert abs(s["estimated_profit"] - implied) < 0.01


def test_order_feasibility_flags_shortfall_against_seeded_commitments():
    # Cement: 200 on hand, 120 already committed to Lakshmi Constructions
    # (see db/seed_data.py) -> 80 genuinely available. Requesting 150
    # should be flagged infeasible with a shortfall of 70, not silently
    # approved.
    result = tools.check_order_feasibility(product_name="Cement", requested_quantity=150)
    assert result["available_stock"] == 80
    assert result["can_fulfill"] is False
    assert result["shortfall"] == 70


def test_order_feasibility_flags_loss_making_discount():
    # Cement cost=380, sell=430. A 90% discount drops the price well below
    # cost -- profit_per_unit should be negative, and the tool shouldn't
    # hide that.
    result = tools.check_order_feasibility(product_name="Cement", requested_quantity=50, requested_discount_pct=90)
    assert result["profit_per_unit"] < 0


def test_order_feasibility_unknown_product_returns_error_not_a_guess():
    result = tools.check_order_feasibility(product_name="Unobtainium", requested_quantity=10)
    assert "error" in result


def test_forecast_revenue_low_confidence_with_no_history():
    # business_id 999 has no seeded sales_history rows.
    result = tools.forecast_revenue(business_id=999, horizon_days=7)
    assert result["confidence"] == "low"


def test_forecast_revenue_returns_requested_horizon_length():
    result = tools.forecast_revenue(business_id=1, horizon_days=10)
    assert result["confidence"] in ("medium", "high")
    assert len(result["daily_forecast"]) == 10
    assert result["total_forecast_revenue"] > 0
