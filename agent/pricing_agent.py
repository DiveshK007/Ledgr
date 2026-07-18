"""
The Pricing Agent's orchestration loop: Perceive -> Retrieve -> Reason (with
tool calls) -> Act. Same shape as supplier_agent.py / collections_agent.py.

Scoped deliberately narrow for P0: not general SKU-level dynamic pricing
(that needs live POS data you won't have in a hackathon), just the one
decision an SME owner actually faces often — stock about to spoil, markdown
now or risk losing it.

Perceive now supports camera-based inventory grounding: point a phone at a
shelf or crate instead of relying only on the manually seeded
inventory_snapshot table. Only products already in the `product` table get
updated this way — a brand-new product spotted on camera has no
cost_price/normal_sell_price to reason about yet, so it's flagged as
needing manual catalog setup rather than guessed at, since the markdown
math downstream depends on those numbers being real.

Run directly for a quick manual test against seeded data:
    python agent/pricing_agent.py
"""

import json

from llm_client import chat, vision_extract, safe_json_parse
from prompts import PRICING_AGENT_SYSTEM_PROMPT, SHELF_INVENTORY_PROMPT
import tools


def perceive_from_images(business_id: int, image_paths: list[str]) -> list[str]:
    """Reads shelf/crate photos and inserts fresh inventory_snapshot rows for
    whatever's already in the product catalog. Returns a list of warnings
    (low-confidence reads, unmatched products) for the caller to surface."""
    warnings = []
    conn = tools._conn()
    cur = conn.cursor()

    for path in image_paths:
        raw = vision_extract(path, SHELF_INVENTORY_PROMPT)
        try:
            items = safe_json_parse(raw)
            if isinstance(items, dict):
                items = [items]
        except (ValueError, KeyError):
            warnings.append(f"Couldn't parse a shelf reading from {path}.")
            continue

        for item in items:
            name = item.get("product_name", "")
            if item.get("confidence", 1.0) < 0.4:
                warnings.append(f"Low-confidence read on '{name}' from {path} — verify before trusting it.")

            cur.execute(
                "SELECT id FROM product WHERE business_id = ? AND lower(name) LIKE ?",
                (business_id, f"%{name.lower()}%"),
            )
            row = cur.fetchone()
            if row is None:
                warnings.append(
                    f"'{name}' spotted on camera but not in the product catalog yet — "
                    "add its cost/sell price manually before pricing it."
                )
                continue

            cur.execute(
                "INSERT INTO inventory_snapshot (business_id, product_id, quantity_on_hand, "
                "days_until_spoilage, snapshot_date, notes) VALUES (?,?,?,?,date('now'),?)",
                (
                    business_id,
                    row[0],
                    item.get("estimated_quantity", 0),
                    item.get("estimated_days_until_spoilage"),
                    f"[camera] {item.get('condition_notes', '')} (confidence {item.get('confidence', '?')})",
                ),
            )

    conn.commit()
    conn.close()
    return warnings


def retrieve(business_id: int) -> list[dict]:
    """Pull the latest snapshot for every perishable product at risk."""
    return tools.get_inventory_snapshot(business_id)


def reason_and_act(business_name: str, inventory: list[dict]) -> dict:
    """
    For each item, Gemma is expected to call calculate_markdown_scenarios
    first (real math), then interpret the scenarios rather than just
    picking the deepest discount by default — e.g. an item with 2 days left
    and healthy quantity might warrant a smaller markdown than one with 1
    day left, even though both are "urgent."
    """
    messages = [
        {"role": "system", "content": PRICING_AGENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Here is the current perishable inventory at risk of spoiling:\n\n"
                f"{json.dumps(inventory, indent=2)}\n\n"
                "For each item, call calculate_markdown_scenarios first, then decide "
                "whether a markdown is warranted and how deep. Explain your reasoning "
                "using the actual numbers from the scenarios. Draft a short announcement "
                "for whichever items you recommend marking down."
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
            if fn_name == "calculate_markdown_scenarios":
                result = tools.calculate_markdown_scenarios(**fn_args)
            else:
                result = {"error": f"unknown tool {fn_name}"}
            messages.append({"role": "tool", "content": json.dumps(result)})
        response = chat(messages, tools=tools.TOOL_SCHEMA)
        tool_calls = response["message"].get("tool_calls", [])

    final_answer = response["message"]["content"]

    tools.log_decision(
        business_id=1,  # TODO: pass real business_id through once multi-business support exists
        agent_name="pricing",
        subject_ids=[item["snapshot_id"] for item in inventory],
        reasoning=final_answer,
        details={"inventory_considered": inventory},
    )

    return {
        "recommendation": final_answer,
        "inventory_considered": inventory,
    }


def run(business_name: str, attachments: list[str] | None = None, business_id: int = 1) -> dict:
    camera_warnings = []
    if attachments:
        print("Perceiving shelf/crate photos...")
        camera_warnings = perceive_from_images(business_id, attachments)

    print("Retrieving perishable inventory...")
    inventory = retrieve(business_id)

    if not inventory:
        return {"error": "No perishable inventory found. Seed the DB first or attach a shelf photo."}

    print("Reasoning...")
    result = reason_and_act(business_name, inventory)
    result["camera_warnings"] = camera_warnings or None

    print("\n--- PRICING RECOMMENDATION ---\n")
    print(result["recommendation"])
    return result


if __name__ == "__main__":
    run(business_name="Sharma Cement Traders")
