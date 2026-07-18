"""
The Cash Flow Agent's orchestration loop. Same deliberately-simple shape as
forecasting_agent.py — no free perceive/retrieve over raw numbers, because the
whole point is that Gemma does NOT estimate cash flow itself: it must call
check_cash_flow (a real deterministic projection, see tools.py) and interpret
that output.

It only drafts an owner alert (via CASH_FLOW_ALERT_PROMPT_TEMPLATE) when the
projection actually goes negative — a healthy position doesn't get a
manufactured alarm. The decision is logged like every other agent, so it shows
up in the existing trust panel with no new UI work.

Run directly for a quick manual test against seeded data:
    python agent/cash_flow_agent.py 14           # 14-day outlook, no expense
    python agent/cash_flow_agent.py 14 15000     # can I afford a Rs 15,000 payment?
"""

import sys
import json

from llm_client import chat
from prompts import CASH_FLOW_AGENT_SYSTEM_PROMPT
import tools


def reason_and_act(business_name: str, business_id: int, window_days: int,
                   pending_expense: float = 0.0) -> dict:
    expense_clause = (
        f" The owner is specifically asking whether they can afford a one-off "
        f"expense of Rs {pending_expense:.0f}."
        if pending_expense else ""
    )
    messages = [
        {"role": "system", "content": CASH_FLOW_AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"The owner of {business_name} wants to know whether their cash position "
                f"is healthy over the next {window_days} days.{expense_clause} Call "
                f"check_cash_flow with business_id={business_id}, window_days={window_days}, "
                f"and pending_expense={pending_expense}, then explain in plain language "
                "whether they stay cash-positive — and if not, when the shortfall hits, "
                "what's driving it, and which receivable (if any) covers it."
            ),
        },
    ]

    response = chat(messages, tools=tools.TOOL_SCHEMA)

    tool_calls = response["message"].get("tool_calls", [])
    cash_flow_result = None
    while tool_calls:
        messages.append(response["message"])
        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"]["arguments"]
            if fn_name == "check_cash_flow":
                cash_flow_result = tools.check_cash_flow(**fn_args)
                result = cash_flow_result
            else:
                result = {"error": f"unknown tool {fn_name}"}
            messages.append({"role": "tool", "content": json.dumps(result)})
        response = chat(messages, tools=tools.TOOL_SCHEMA)
        tool_calls = response["message"].get("tool_calls", [])

    final_answer = response["message"]["content"]

    # Same empty-content guard as the pricing agent: a longer tool-calling
    # exchange can leave the final turn empty, so re-ask once without tools to
    # force the written assessment rather than shipping nothing.
    if not final_answer.strip():
        messages.append({
            "role": "user",
            "content": (
                "Using the check_cash_flow numbers already computed above, now write "
                "your plain-language cash-flow assessment for the owner."
            ),
        })
        final_answer = chat(messages)["message"]["content"]

    # Draft an owner alert ONLY when the projection actually goes negative.
    drafted_messages = {}
    subject_ids = []
    if cash_flow_result and cash_flow_result.get("goes_negative"):
        parts = [
            f"projected to go cash-negative on {cash_flow_result.get('negative_date')}",
            f"short by about Rs {cash_flow_result.get('shortfall_amount')}",
        ]
        lever = cash_flow_result.get("largest_lever")
        if lever:
            subject_ids = [lever["ledger_entry_id"]]
            if lever.get("covers_shortfall"):
                parts.append(
                    f"chasing {lever['customer_name']} "
                    f"(Rs {lever['amount']:.0f} outstanding) would cover it"
                )
            else:
                parts.append(
                    f"no single receivable covers it; the largest is "
                    f"{lever['customer_name']} at Rs {lever['amount']:.0f}"
                )
        summary = "; ".join(parts)
        drafted_messages["owner_alert"] = tools.draft_cash_flow_alert(business_name, summary)

    tools.log_decision(
        business_id=business_id,
        agent_name="cash_flow",
        subject_ids=subject_ids,
        reasoning=final_answer,
        details={"cash_flow_result": cash_flow_result},
        drafted_messages=drafted_messages or None,
    )

    return {
        "recommendation": final_answer,
        "cash_flow_result": cash_flow_result,
        "drafted_messages": drafted_messages or None,
    }


def run(business_name: str, _attachments: list[str] | None = None, business_id: int = 1,
        window_days: int = 14, pending_expense: float = 0.0) -> dict:
    # `_attachments` kept for planner interface consistency, unused here.
    print("Reasoning (check_cash_flow will be called by Gemma)...")
    result = reason_and_act(business_name, business_id, window_days, pending_expense)

    print("\n--- CASH FLOW ---\n")
    print(result["recommendation"])
    if result.get("drafted_messages"):
        print("\n--- DRAFTED ALERT ---\n")
        print(result["drafted_messages"].get("owner_alert", ""))
    return result


if __name__ == "__main__":
    window = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    expense = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    run(business_name="Sharma Cement Traders", window_days=window, pending_expense=expense)
