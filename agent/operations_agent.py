"""
The Operational Planning Agent's orchestration loop: "a customer wants to
place a bulk order — can we actually fulfill it, and is it worth taking?"

Same hybrid philosophy as Pricing and Forecasting: Gemma must call
check_order_feasibility (real arithmetic against stock, existing
commitments, and margin) rather than reasoning about feasibility/profit
from instinct.

Note on the planner interface: unlike the other four agents, this one needs
structured order details (product, quantity, discount ask) that don't come
from a photo or a flat DB snapshot — they come from whatever the owner is
telling the agent about a specific incoming order. For P0 this is passed
directly as arguments; wiring the planner to extract these fields from a
free-text query is a small follow-up (a short Gemma call that parses the
query into product_name/requested_quantity/requested_discount_pct before
handing off here) rather than a re-architecture.

Run directly for a quick manual test against seeded stock/commitments:
    python agent/operations_agent.py
"""

import json

from llm_client import chat
from prompts import OPERATIONS_AGENT_SYSTEM_PROMPT
import tools


def reason_and_act(business_name: str, product_name: str, requested_quantity: float,
                    requested_discount_pct: float = 0.0) -> dict:
    messages = [
        {"role": "system", "content": OPERATIONS_AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"A customer wants to order {requested_quantity} units of '{product_name}' "
                f"from {business_name}, asking for a {requested_discount_pct}% discount. "
                "Call check_order_feasibility first, then decide whether to accept, "
                "negotiate, or decline — and explain why using the actual numbers."
            ),
        },
    ]

    response = chat(messages, tools=tools.TOOL_SCHEMA)

    tool_calls = response["message"].get("tool_calls", [])
    feasibility_result = None
    while tool_calls:
        messages.append(response["message"])
        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"]["arguments"]
            if fn_name == "check_order_feasibility":
                feasibility_result = tools.check_order_feasibility(**fn_args)
                result = feasibility_result
            else:
                result = {"error": f"unknown tool {fn_name}"}
            messages.append({"role": "tool", "content": json.dumps(result)})
        response = chat(messages, tools=tools.TOOL_SCHEMA)
        tool_calls = response["message"].get("tool_calls", [])

    final_answer = response["message"]["content"]

    tools.log_decision(
        business_id=1,  # TODO: pass real business_id through once multi-business support exists
        agent_name="operations",
        subject_ids=[],
        reasoning=final_answer,
        details={"feasibility_result": feasibility_result, "product_name": product_name,
                 "requested_quantity": requested_quantity},
    )

    return {
        "recommendation": final_answer,
        "feasibility_result": feasibility_result,
    }


def run(business_name: str, _attachments: list[str] | None = None,
        product_name: str = "Cement", requested_quantity: float = 150,
        requested_discount_pct: float = 5.0) -> dict:
    # `_attachments` kept for planner interface consistency, unused here.
    # Defaults model a plausible incoming order for the demo business —
    # swap these for real parsed values once query-parsing is wired up.
    print("Reasoning (check_order_feasibility will be called by Gemma)...")
    result = reason_and_act(business_name, product_name, requested_quantity, requested_discount_pct)

    print("\n--- ORDER DECISION ---\n")
    print(result["recommendation"])
    return result


if __name__ == "__main__":
    run(business_name="Sharma Cement Traders")
