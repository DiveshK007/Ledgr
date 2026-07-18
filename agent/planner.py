"""
Planner / router agent — the actual entry point an owner talks to. Classifies
what they're asking for and dispatches to the right specialist agent.

Currently wired: Supplier Agent.
Stubbed for the rest of the roadmap: Collections, Pricing, Forecasting,
Operational Planning — add each the same way Supplier was built (its own
perceive/retrieve/reason/act loop), then register it in _register_handlers().
"""

import sys

from llm_client import chat, safe_json_parse

ROUTING_PROMPT = """You are the router for Ledgr, an on-device business advisor.
Classify the owner's request into exactly one of these categories, and
respond with ONLY the category name, nothing else:

- supplier     (comparing supplier quotes, choosing a vendor, negotiating with a supplier)
- collections  (chasing customer payments, credit/udhaar reminders)
- pricing      (markdown, discounting, bundle pricing decisions)
- forecasting  (revenue/cashflow projections)
- operations   (whether to accept an order, capacity/profitability questions)
- unclear      (doesn't fit any of the above, or needs clarification)

Owner's request: "{query}"
"""

VALID_CATEGORIES = {"supplier", "collections", "pricing", "forecasting", "operations"}
SPECIALIST_HANDLERS = {}


def _register_handlers():
    """Deferred import to avoid circular imports between planner and agents."""
    import supplier_agent
    import collections_agent
    import pricing_agent
    import forecasting_agent
    import operations_agent
    SPECIALIST_HANDLERS["supplier"] = supplier_agent.run
    SPECIALIST_HANDLERS["collections"] = collections_agent.run
    SPECIALIST_HANDLERS["pricing"] = pricing_agent.run
    SPECIALIST_HANDLERS["forecasting"] = forecasting_agent.run
    SPECIALIST_HANDLERS["operations"] = operations_agent.run
    # All five named specialists from the Track 3 brief are now wired up.


def classify(query: str) -> str:
    response = chat([{"role": "user", "content": ROUTING_PROMPT.format(query=query)}])
    category = response["message"]["content"].strip().lower()
    return category if category in VALID_CATEGORIES else "unclear"


def route(query: str, business_name: str = "Sharma Cement Traders", attachments: list[str] | None = None) -> dict:
    if not SPECIALIST_HANDLERS:
        _register_handlers()

    category = classify(query)
    print(f"[planner] routed '{query[:60]}...' -> {category}")

    if category == "supplier":
        if not attachments:
            return {
                "category": category,
                "error": "Supplier Agent needs photographed quote images to compare. "
                "Ask the owner to attach them.",
            }
        result = SPECIALIST_HANDLERS["supplier"](business_name, attachments)

    elif category == "operations":
        # Unlike the other agents, Operations needs structured order details
        # (product/quantity/discount) that don't live in a photo or a flat
        # DB snapshot — parse them out of the free-text query first.
        from prompts import ORDER_PARSING_PROMPT

        raw = chat([{"role": "user", "content": ORDER_PARSING_PROMPT.format(query=query)}])
        try:
            order_details = safe_json_parse(raw["message"]["content"])
        except (ValueError, KeyError):
            return {
                "category": category,
                "error": "Couldn't parse order details from that message — try including "
                "the product, quantity, and any discount being asked for.",
            }
        result = SPECIALIST_HANDLERS["operations"](
            business_name,
            attachments,
            product_name=order_details.get("product_name", "Cement"),
            requested_quantity=order_details.get("requested_quantity", 100),
            requested_discount_pct=order_details.get("requested_discount_pct", 0),
        )

    elif category in SPECIALIST_HANDLERS:
        result = SPECIALIST_HANDLERS[category](business_name, attachments)

    else:
        return {
            "category": category,
            "error": f"'{category}' isn't wired up yet.",
        }

    result["category"] = category
    return result


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "I got quotes from three cement suppliers, which one should I go with?"
    # For a quick manual test, point this at the sample images once generated:
    result = route(query, attachments=["sample_data/quote1_balaji.png",
                                        "sample_data/quote2_krishna.png",
                                        "sample_data/quote3_newblr.png"])
    print(result)
