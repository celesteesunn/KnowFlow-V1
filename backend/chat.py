"""Chat blueprint — POST /api/chat, the RAG question-answering endpoint.

Permission model: the project must belong to the signed-in user inside their
workspace. That check runs BEFORE retrieval, and retrieval is additionally
scoped to the same user, workspace and project, so no unauthorized content ever
reaches the LLM — even if a caller elsewhere forgets the check.

Conversation memory is stored per project and per user. A follow-up question
is resolved against what was just asked in the same project; it can never be
resolved against another project's topic or another user's conversation.
"""

from flask import Blueprint, jsonify, request, session

from ai import ask_documents
from auth import active_required, workspace_id
from db import get_db, log_activity

bp = Blueprint("chat", __name__)


@bp.post("/api/chat")
@active_required
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
    ws_id = workspace_id(conn)
    # Permission check BEFORE retrieval: only the project owner (same
    # workspace) may ask.
    project = conn.execute(
        "SELECT id FROM projects WHERE id = ? AND owner_id = ? AND workspace_id = ?",
        (project_id, session["user_id"], ws_id),
    ).fetchone()
    if not project:
        conn.close()
        return jsonify({"error": "Project not found"}), 404

    result = ask_documents(
        conn, session["user_id"], ws_id, project_id, question
    )
    log_activity(
        conn, session["user_id"], "ai_question",
        f'Asked the AI: "{question}"', ref_type="project", ref_id=project_id,
    )
    conn.commit()

    # Knowledge gap: record a question the documents could not answer, so the
    # gap is visible rather than silently returning nothing. A conversational
    # turn ("hello", "thanks") never ran a search, so it is not a gap.
    if result["retrieval_attempted"] and not result["matched"]:
        conn.execute(
            "INSERT INTO knowledge_gaps (question, user_id, project_id, workspace_id) "
            "VALUES (?, ?, ?, ?)",
            (question, session["user_id"], project_id, ws_id),
        )
        conn.commit()
    conn.close()

    # sources carry the document and page only. Similarity scores, chunk ids
    # and raw passage text are retrieval internals and are deliberately not
    # sent to the client.
    return jsonify(
        {
            "answer": result["answer"],
            "mode": result["mode"],
            "sources": result["sources"],
            "intent": result["intent"],
        }
    )


@bp.get("/api/chat/history")
@active_required
def chat_history():
    """Return this project's recent conversation for the signed-in user."""
    project_id = request.args.get("project_id", type=int)
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    conn = get_db()
    ws_id = workspace_id(conn)
    project = conn.execute(
        "SELECT id FROM projects WHERE id = ? AND owner_id = ? AND workspace_id = ?",
        (project_id, session["user_id"], ws_id),
    ).fetchone()
    if not project:
        conn.close()
        return jsonify({"error": "Project not found"}), 404

    from conversation import load_history

    history = load_history(conn, project_id, session["user_id"])
    conn.close()
    return jsonify({"history": history})


@bp.post("/api/chat/history/clear")
@active_required
def clear_chat_history():
    """Forget this project's conversation for the signed-in user.

    Clearing is scoped to one user and one project: it cannot wipe another
    user's transcript, and it does not touch other projects' conversations.
    """
    data = request.get_json(force=True)
    project_id = data.get("project_id")
    if not project_id:
        return jsonify({"error": "project_id is required"}), 400

    conn = get_db()
    ws_id = workspace_id(conn)
    project = conn.execute(
        "SELECT id FROM projects WHERE id = ? AND owner_id = ? AND workspace_id = ?",
        (project_id, session["user_id"], ws_id),
    ).fetchone()
    if not project:
        conn.close()
        return jsonify({"error": "Project not found"}), 404

    from conversation import clear_history

    clear_history(conn, project_id, session["user_id"])
    conn.commit()
    conn.close()
    return jsonify({"ok": True})