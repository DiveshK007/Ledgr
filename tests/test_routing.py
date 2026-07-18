"""
Tests that the planner routes free-text queries to the right specialist
agent. Needs a live Ollama + Gemma (auto-skips otherwise, see conftest.py).

    pytest tests/test_routing.py -v
"""

import pytest
from conftest import OLLAMA_AVAILABLE
import planner

pytestmark = pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not running locally")

CASES = [
    ("which cement supplier should I go with, I have three quotes", "supplier"),
    ("who should I follow up with for payment this week", "collections"),
    ("what should I do with the tomatoes before they go bad", "pricing"),
    ("what will my revenue look like over the next two weeks", "forecasting"),
    ("a customer wants to order 200 bags of cement, should I take it", "operations"),
]


@pytest.mark.parametrize("query,expected_category", CASES)
def test_planner_routes_to_expected_agent(query, expected_category):
    category = planner.classify(query)
    assert category == expected_category, f"expected '{expected_category}' for {query!r}, got '{category}'"
