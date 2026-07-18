"""
The Forecasting Agent's orchestration loop. Deliberately simpler shape than
the other three agents — no perceive/retrieve step, because the entire
point of this agent is that Gemma does NOT reason freely over raw numbers;
it must call forecast_revenue (a real linear-trend + seasonality model, see
tools.py) and interpret that output rather than estimating revenue itself.

This is the "hybrid LLM + classical model" piece called out in the build
plan as the most technically distinct part of the whole system — protect
time for this one if things get tight.

Run directly for a quick manual test against seeded sales history:
    python agent/forecasting_agent.py 14
"""

import sys
import json

from llm_client import chat
from prompts import FORECASTING_AGENT_SYSTEM_PROMPT
import tools


def reason_and_act(business_name: str, business_id: int, horizon_days: int) -> dict:
    messages = [
        {"role": "system", "content": FORECASTING_AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"The owner of {business_name} wants a revenue outlook for the next "
                f"{horizon_days} days. Call forecast_revenue with business_id={business_id} "
                f"and horizon_days={horizon_days}, then explain the result in plain "
                "language: expected total, the trend direction, which days look "
                "strongest/weakest and why, and how much to trust this forecast."
            ),
        },
    ]

    response = chat(messages, tools=tools.TOOL_SCHEMA)

    tool_calls = response["message"].get("tool_calls", [])
    forecast_result = None
    while tool_calls:
        messages.append(response["message"])
        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"]["arguments"]
            if fn_name == "forecast_revenue":
                forecast_result = tools.forecast_revenue(**fn_args)
                result = forecast_result
            else:
                result = {"error": f"unknown tool {fn_name}"}
            messages.append({"role": "tool", "content": json.dumps(result)})
        response = chat(messages, tools=tools.TOOL_SCHEMA)
        tool_calls = response["message"].get("tool_calls", [])

    final_answer = response["message"]["content"]

    tools.log_decision(
        business_id=business_id,
        agent_name="forecasting",
        subject_ids=[],
        reasoning=final_answer,
        details={"forecast_result": forecast_result},
    )

    return {
        "recommendation": final_answer,
        "forecast_result": forecast_result,
    }


def run(business_name: str, _attachments: list[str] | None = None, business_id: int = 1,
        horizon_days: int = 14) -> dict:
    # `_attachments` kept for planner interface consistency, unused here.
    print("Reasoning (forecast_revenue will be called by Gemma)...")
    result = reason_and_act(business_name, business_id, horizon_days)

    print("\n--- FORECAST ---\n")
    print(result["recommendation"])
    return result


if __name__ == "__main__":
    horizon = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    run(business_name="Sharma Cement Traders", horizon_days=horizon)
