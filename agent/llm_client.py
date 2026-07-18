"""
Thin wrapper around a local Gemma model served via Ollama.

Setup (one-time, on your machine):
    1. Install Ollama: https://ollama.com
    2. Pull Gemma 4:  ollama pull gemma4:12b
       (the 12B "Unified" variant — encoder-free multimodal, vision + audio
       flow straight into the model, native function-calling. Fits Ledgr's
       needs exactly: photo-reading agents + tool-calling reasoning.)
    3. ollama serve   (usually runs automatically after install)

Everything below talks to localhost only — no cloud calls, ever. That's the
whole point: business data never leaves the device.
"""

import json
import ollama

MODEL_NAME = "gemma4:12b"


def chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """
    Send a chat turn to the local model. `messages` follows the standard
    {"role": ..., "content": ...} format. `tools` follows Ollama's
    function-calling schema (see tools.py for the definitions).

    Returns the raw response dict so the caller can inspect tool_calls.
    """
    response = ollama.chat(
        model=MODEL_NAME,
        messages=messages,
        tools=tools or [],
    )
    return response


def vision_extract(image_path: str, instruction: str) -> str:
    """
    Send an image + instruction to Gemma's multimodal endpoint and return
    the raw text response (expected to be JSON per the prompt — see
    prompts.py:QUOTE_EXTRACTION_PROMPT).
    """
    response = ollama.chat(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": instruction,
                "images": [image_path],
            }
        ],
    )
    return response["message"]["content"]


def safe_json_parse(text: str) -> dict:
    """
    Gemma will sometimes wrap JSON in prose or code fences. Strip the
    common cases before parsing so a demo doesn't crash on a stray
    ```json fence during a live run.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start : end + 1])
        raise
