"""
Ledgr backend API. Was a server-rendered HTML app; now a plain JSON API so
a real frontend (frontend/, Vite + React) can drive it instead. Same
planner/agent logic underneath — nothing about the agents changed, only how
their output reaches the screen.

Runs entirely on localhost against Ollama; no cloud calls. CORS is enabled
for the Vite dev server origin so this stays a two-process local setup
(backend on :5000, frontend on :5173) rather than one bundled app, which
keeps iteration fast on both sides.

Usage:
    pip install -r requirements.txt
    python db/seed_data.py
    python app.py
API is then at http://localhost:5000
"""

import os
import sys
import sqlite3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agent"))
import planner  # noqa: E402
import tools  # noqa: E402
import voice  # noqa: E402

app = Flask(__name__)
CORS(app)  # dev-friendly default; tighten to the Vite origin before demo day if needed

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.route("/api/ask", methods=["POST"])
def ask():
    """
    Accepts multipart/form-data (so photo uploads work) with a `query`
    field and optional `images` files, OR a plain JSON body with just
    `query` for text-only requests.

    Returns: { category, recommendation, error, details? }
    `details` is only present for agents that expose extra structured
    data worth showing (e.g. forecast_result, feasibility_result) — the
    frontend can render it or ignore it.
    """
    if request.content_type and "multipart/form-data" in request.content_type:
        query = request.form.get("query", "").strip()
        saved_paths = []
        for f in request.files.getlist("images"):
            if f and f.filename:
                path = os.path.join(UPLOAD_DIR, f.filename)
                f.save(path)
                saved_paths.append(path)
    else:
        payload = request.get_json(silent=True) or {}
        query = (payload.get("query") or "").strip()
        saved_paths = []

    if not query:
        return jsonify({"category": None, "error": "Type a question first."}), 400

    result = planner.route(query, attachments=saved_paths or None)
    return jsonify(result)


@app.route("/api/ask-voice", methods=["POST"])
def ask_voice():
    """
    Accepts a recorded audio clip (multipart field `audio`), transcribes
    it offline, routes the transcript through the planner exactly like
    /api/ask, then synthesizes the recommendation back to speech.

    Returns: { transcript, category, recommendation, error, audio_url }
    `audio_url` points at /api/audio/<file> for the frontend to play back.
    """
    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "No audio file provided."}), 400

    temp_path = os.path.join(UPLOAD_DIR, f"voice_{uuid_safe_name(audio_file.filename)}")
    audio_file.save(temp_path)

    transcript = voice.transcribe_audio(temp_path)
    if not transcript:
        return jsonify({
            "category": None,
            "error": "Couldn't make out what was said — try again closer to the mic.",
        })

    result = planner.route(transcript, attachments=None)
    result["transcript"] = transcript

    if result.get("recommendation"):
        audio_path = voice.speak_text(result["recommendation"])
        result["audio_url"] = f"/api/audio/{os.path.basename(audio_path)}"

    return jsonify(result)


@app.route("/api/audio/<path:filename>", methods=["GET"])
def get_audio(filename):
    return send_from_directory(voice.AUDIO_OUTPUT_DIR, filename)


def uuid_safe_name(filename):
    """Browsers send odd/empty filenames for recorded blobs — never trust it as-is."""
    import uuid
    ext = os.path.splitext(filename or "")[1] or ".webm"
    return f"{uuid.uuid4().hex}{ext}"


@app.route("/api/trust-panel", methods=["GET"])
def trust_panel():
    """Returns the last N decisions across all agents, most recent first."""
    limit = request.args.get("limit", default=20, type=int)
    conn = sqlite3.connect(tools.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, agent_name, reasoning, details_json, drafted_messages_json, created_at "
        "FROM decision_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()

    decisions = [
        {
            "id": r[0],
            "agent_name": r[1],
            "reasoning": r[2],
            "details_json": r[3],
            "drafted_messages_json": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]
    return jsonify({"decisions": decisions})


@app.route("/api/agents", methods=["GET"])
def agents():
    """Static metadata the frontend uses to render the five-agent selector."""
    return jsonify(
        {
            "agents": [
                {"key": "supplier", "label": "Supplier", "seal": "01"},
                {"key": "collections", "label": "Collections", "seal": "02"},
                {"key": "pricing", "label": "Pricing", "seal": "03"},
                {"key": "forecasting", "label": "Forecasting", "seal": "04"},
                {"key": "operations", "label": "Operations", "seal": "05"},
            ]
        }
    )


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
