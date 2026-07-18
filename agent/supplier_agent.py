"""
The Supplier Agent's orchestration loop: Perceive -> Retrieve -> Reason (with
tool calls) -> Act. This is the P0 core build — get this working end to end
on real (or realistic mock) data before touching anything else in the build
plan.

Run directly for a quick manual test:
    python agent/supplier_agent.py sample_data/quote1.jpg sample_data/quote2.jpg
"""

import sys
import json

from llm_client import chat, vision_extract, safe_json_parse
from prompts import QUOTE_EXTRACTION_PROMPT, SUPPLIER_AGENT_SYSTEM_PROMPT
import tools


def perceive(image_paths: list[str]) -> list[dict]:
    """Step 1: read each photographed quote into structured data."""
    extracted = []
    for path in image_paths:
        raw = vision_extract(path, QUOTE_EXTRACTION_PROMPT)
        data = safe_json_parse(raw)
        data["source_image_path"] = path
        extracted.append(data)
        if data.get("confidence", 1.0) < 0.6:
            print(f"  [!] Low-confidence extraction on {path}: {data.get('ambiguous_fields')}")
    return extracted


def retrieve(quotes: list[dict]) -> list[dict]:
    """Step 2: ground each quote in the supplier's real history."""
    for q in quotes:
        q["supplier_history"] = tools.lookup_supplier_history(q["supplier_name_raw"])
    return quotes


def reason_and_act(business_name: str, quotes: list[dict]) -> dict:
    """
    Step 3 + 4: hand everything to Gemma with the tool schema available.
    Gemma decides whether/when to call calculate_effective_cost per quote,
    then produces a final recommendation and (if warranted) a counter-offer.

    This is a simplified single-turn tool-calling loop — good enough for the
    hackathon demo. If Gemma requests a tool call, we execute it and feed
    the result back in a second turn.
    """
    context = {
        "business_name": business_name,
        "quotes": quotes,
    }

    messages = [
        {"role": "system", "content": SUPPLIER_AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Here are the supplier quotes to compare, with their history:\n\n"
                f"{json.dumps(context, indent=2)}\n\n"
                "Use calculate_effective_cost on each quote before deciding. "
                "Then recommend one supplier, explain why in plain language, "
                "and state whether a counter-offer is worth drafting."
            ),
        },
    ]

    response = chat(messages, tools=tools.TOOL_SCHEMA)

    # Execute any tool calls Gemma requested, then give it the results.
    tool_calls = response["message"].get("tool_calls", [])
    while tool_calls:
        messages.append(response["message"])
        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"]["arguments"]
            if fn_name == "calculate_effective_cost":
                result = tools.calculate_effective_cost(**fn_args)
            elif fn_name == "lookup_supplier_history":
                result = tools.lookup_supplier_history(**fn_args)
            else:
                result = {"error": f"unknown tool {fn_name}"}
            messages.append({"role": "tool", "content": json.dumps(result)})
        response = chat(messages, tools=tools.TOOL_SCHEMA)
        tool_calls = response["message"].get("tool_calls", [])

    final_answer = response["message"]["content"]

    tools.log_decision(
        business_id=1,  # TODO: pass real business_id through once multi-business support exists
        agent_name="supplier",
        subject_ids=[i for i in range(len(quotes))],  # replace with real quote.id once quotes are persisted to DB
        reasoning=final_answer,
        details={"quotes_considered": quotes},
    )

    return {
        "recommendation": final_answer,
        "quotes_considered": quotes,
    }


def run(business_name: str, image_paths: list[str]) -> dict:
    print("Perceiving quotes...")
    quotes = perceive(image_paths)

    print("Retrieving supplier history...")
    quotes = retrieve(quotes)

    print("Reasoning...")
    result = reason_and_act(business_name, quotes)

    print("\n--- RECOMMENDATION ---\n")
    print(result["recommendation"])
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent/supplier_agent.py <quote_image1> [quote_image2] ...")
        sys.exit(1)
    run(business_name="Sharma Cement Traders", image_paths=sys.argv[1:])
