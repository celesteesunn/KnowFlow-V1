"""Chat blueprint — POST /api/chat, the RAG question-answering endpoint.

Permission model: the project must belong to the signed-in user. Retrieval
happens AFTER that check and is scoped to the project's current,
non-archived documents, so no unauthorized content ever reaches the LLM.
"""

from flask import Blueprint, jsonify, request, session

from ai import LOW_SCORE, generate_answer, retrieve_chunks
from auth import login_required
from db import get_db

bp = Blueprint("chat", __name__)


@bp.post("/api/chat")
@login_required
def chat():
    data = request.get_json(force=True)
    project_id = data.get("project_id")
    question = (data.get("question") or "").strip()

    if not project_id:
        return jsonify({"error": "project_id is required"}), 400
    if not question:
        return jsonify({"error": "Question is required"}), 400
    if len(question) > 2000:
        return jsonify({"error": "Question is too long (max 2000 characters)"}), 400

    conn = get_db()
    # Permission check BEFORE retrieval: only the project owner may ask.
    project = conn.execute(
        "SELECT id FROM projects WHERE id = ? AND owner_id = ?",
        (project_id, session["user_id"]),
    ).fetchone()
    if not project:
        conn.close()
        return jsonify({"error": "Project not found"}), 404

    hits = retrieve_chunks(conn, project_id, question)
    conn.close()

    # Part 4 — knowledge gap: record questions the AI could not answer well.
    top_score = max((h["score"] for h in hits), default=0.0)
    if not hits or top_score < LOW_SCORE:
        gap_conn = get_db()
        gap_conn.execute(
            "INSERT INTO knowledge_gaps (question, user_id, project_id) VALUES (?, ?, ?)",
            (question, session["user_id"], project_id),
        )
        gap_conn.commit()
        gap_conn.close()

    if not hits:
        return jsonify(
            {
                "answer": "I could not find the information in the available documents.",
                "mode": "none",
                "sources": [],
            }
        )

    result = generate_answer(question, hits)
    sources = [
        {
            "document": h["filename"],
            "page": h["page_number"],
            "score": round(h["score"], 3),
            "chunk": h["text"],
        }
        for h in hits
    ]
    return jsonify(
        {
            "answer": result["answer"],
            "mode": result["mode"],
            "sources": sources,
        }
    )