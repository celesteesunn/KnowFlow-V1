"""Projects blueprint — list and create knowledge projects."""

from flask import Blueprint, jsonify, request, session

from auth import login_required
from db import get_db

bp = Blueprint("projects", __name__)


@bp.get("/api/projects")
@login_required
def list_projects():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.description, p.created_at,
               (SELECT COUNT(*) FROM documents d WHERE d.project_id = p.id)
                   AS document_count
        FROM projects p
        WHERE p.owner_id = ?
        ORDER BY p.created_at DESC
        """,
        (session["user_id"],),
    ).fetchall()
    conn.close()
    return jsonify({"projects": [dict(r) for r in rows]})


@bp.post("/api/projects")
@login_required
def create_project():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO projects (name, description, owner_id) VALUES (?, ?, ?)",
        (name, (data.get("description") or "").strip(), session["user_id"]),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, name, description, created_at FROM projects WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    return jsonify({"project": dict(row)}), 201