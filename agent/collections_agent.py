"""
The Collections Agent's orchestration loop: Perceive -> Retrieve -> Reason
(with tool calls) -> Act. Same shape as supplier_agent.py by design — every
new specialist agent should follow this pattern so the planner can treat
them interchangeably.

Two ways to feed it data:
  1. Pass ledger_image_paths — photographed khata/ledger pages get read by
     Gemma vision and upserted into the DB first (the wow-factor path).
  2. Pass nothing — it just reasons over whatever's already seeded/recorded
     in the ledger_entry table (fastest path for dev/testing).

Run directly for a quick manual test against seeded data:
    python agent/collections_agent.py
"""

import sys
import json
from datetime import datetime

from llm_client import chat, vision_extract, safe_json_parse
from prompts import LEDGER_EXTRACTION_PROMPT, COLLECTIONS_AGENT_SYSTEM_PROMPT
import tools


def perceive_from_images(business_id: int, image_paths: list[str]) -> None:
    """Optional step: read photographed ledger pages and insert them as new
    ledger_entry rows. Skip this entirely if you're testing against seeded
    data only."""
    conn = tools._conn()
    for path in image_paths:
        raw = vision_extract(path, LEDGER_EXTRACTION_PROMPT)
        entries = safe_json_parse(raw) if raw.strip().startswith("[") else [safe_json_parse(raw)]
        for e in entries:
            if e.get("confidence", 1.0) < 0.5:
                print(f"  [!] Low-confidence ledger entry from {path}: {e}")
            conn.execute(
                "INSERT INTO ledger_entry (business_id, customer_name_raw, amount_due, "
                "days_overdue, status_notes, source_image_path, extracted_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    business_id,
                    e.get("customer_name_raw", "illegible entry"),
                    e.get("amount_due", 0),
                    e.get("days_overdue", 0),
                    e.get("status_notes", ""),
                    path,
                    datetime.utcnow().isoformat(),
                ),
            )
    conn.commit()
    conn.close()


def retrieve(business_id: int) -> list[dict]:
    """Pull the full ledger snapshot, joined with customer relationship notes."""
    return tools.get_ledger_snapshot(business_id)


def reason_and_act(business_name: str, ledger_snapshot: list[dict]) -> dict:
    """
    Hand the full ledger to Gemma with the urgency-score tool available.
    Gemma is explicitly told (via the system prompt) to treat the baseline
    score as a starting point, not the answer — the actual judgment comes
    from weighing it against relationship_notes and status_notes.
    """
    messages = [
        {"role": "system", "content": COLLECTIONS_AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Here is the full outstanding ledger for the business, with whatever "
                "relationship history exists:\n\n"
                f"{json.dumps(ledger_snapshot, indent=2)}\n\n"
                "Use calculate_urgency_score on each entry as a starting point, then "
                "decide: who should be followed up with this week, in what order, and "
                "with what approach (soft nudge / firm reminder / payment plan offer). "
                "For each one worth following up, draft the actual message in their "
                "preferred language. Explain your reasoning plainly so the owner can "
                "see why you ranked them this way."
            ),
        },
    ]

    response = chat(messages, tools=tools.TOOL_SCHEMA)

    tool_calls = response["message"].get("tool_calls", [])
    while tool_calls:
        messages.append(response["message"])
        for call in tool_calls:
            fn_name = call["function"]["name"]
            fn_args = call["function"]["arguments"]
            if fn_name == "calculate_urgency_score":
                result = tools.calculate_urgency_score(**fn_args)
            elif fn_name == "lookup_supplier_history":
                # Not expected here, but handled defensively in case the
                # model reaches for the wrong tool from the shared schema.
                result = tools.lookup_supplier_history(**fn_args)
            else:
                result = {"error": f"unknown tool {fn_name}"}
            messages.append({"role": "tool", "content": json.dumps(result)})
        response = chat(messages, tools=tools.TOOL_SCHEMA)
        tool_calls = response["message"].get("tool_calls", [])

    final_answer = response["message"]["content"]

    tools.log_decision(
        business_id=1,  # TODO: pass real business_id through once multi-business support exists
        agent_name="collections",
        subject_ids=[e["ledger_entry_id"] for e in ledger_snapshot],
        reasoning=final_answer,
        details={"ledger_snapshot": ledger_snapshot},
    )

    return {
        "recommendation": final_answer,
        "ledger_considered": ledger_snapshot,
    }


def run(business_name: str, ledger_image_paths: list[str] | None = None, business_id: int = 1) -> dict:
    if ledger_image_paths:
        print("Perceiving photographed ledger pages...")
        perceive_from_images(business_id, ledger_image_paths)

    print("Retrieving ledger + relationship history...")
    ledger_snapshot = retrieve(business_id)

    if not ledger_snapshot:
        return {"error": "No ledger entries found. Seed the DB or pass ledger_image_paths."}

    print("Reasoning...")
    result = reason_and_act(business_name, ledger_snapshot)

    print("\n--- COLLECTIONS PLAN ---\n")
    print(result["recommendation"])
    return result


if __name__ == "__main__":
    image_paths = sys.argv[1:] if len(sys.argv) > 1 else None
    run(business_name="Sharma Cement Traders", ledger_image_paths=image_paths)
