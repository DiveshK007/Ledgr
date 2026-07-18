"""
Scenario tests -- the rigor check called out in the build plan: does each
agent degrade honestly on edge cases, or does it just agree with whatever
it's asked? Needs a live Ollama + Gemma (auto-skips otherwise).

These assert on keyword presence in the model's free-text output rather
than exact matches, since LLM phrasing varies run to run -- that's a real
limitation of testing generated text, not a bug in the tests. It's still
a meaningfully stronger signal than no testing at all, and the honest
thing to do is say so rather than pretend these are as precise as the
math tests in test_tools_math.py.

    pytest tests/test_scenarios.py -v
"""

import pytest
from conftest import OLLAMA_AVAILABLE
import collections_agent
import operations_agent
import pricing_agent

pytestmark = pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not running locally")


def test_collections_agent_runs_end_to_end_on_seeded_data():
    result = collections_agent.run(business_name="Sharma Cement Traders")
    assert "recommendation" in result
    assert len(result["recommendation"]) > 20


def test_operations_agent_honestly_flags_infeasible_order():
    # 150 units requested against only 80 genuinely available (per seeded
    # commitments) -- the agent should say so, not approve it to be agreeable.
    result = operations_agent.run(
        business_name="Sharma Cement Traders",
        product_name="Cement",
        requested_quantity=150,
    )
    text = result["recommendation"].lower()
    shortfall_language = ["short", "insufficient", "cannot", "can't", "not enough", "unable", "80"]
    assert any(w in text for w in shortfall_language), (
        f"expected the agent to flag the stock shortfall, got: {result['recommendation'][:200]}"
    )


def test_operations_agent_does_not_wave_through_a_loss_making_discount():
    # 90% off cement (cost 380, sell 430) is a guaranteed loss -- the agent
    # should flag this, not accept the order just to close the sale.
    result = operations_agent.run(
        business_name="Sharma Cement Traders",
        product_name="Cement",
        requested_quantity=50,
        requested_discount_pct=90,
    )
    text = result["recommendation"].lower()
    loss_language = ["loss", "not profitable", "unprofitable", "lose money", "decline", "negative", "below cost"]
    assert any(w in text for w in loss_language), (
        f"expected the agent to flag the loss-making discount, got: {result['recommendation'][:200]}"
    )


def test_pricing_agent_runs_end_to_end_on_seeded_perishables():
    result = pricing_agent.run(business_name="Sharma Cement Traders")
    assert "recommendation" in result
    assert len(result["recommendation"]) > 20
