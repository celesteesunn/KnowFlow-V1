"""Projects blueprint — list and create knowledge projects.

Every query is scoped to the signed-in user's workspace AND ownership, so
users can only ever see projects inside their own organisation workspace.
"""

from flask import Blueprint, jsonify, request, session

from auth import active_required, workspace_id
from db import get_db, log_activity

bp = Blueprint("projects", __name__)


@bp.get("/api/projects")
@active_required
def list_projects():
    conn = get_db()
    ws_id = workspace_id(conn)
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.description, p.created_at,
               (SELECT COUNT(*) FROM documents d WHERE d.project_id = p.id)
                   AS document_count
        FROM projects p
        WHERE p.owner_id = ? AND p.workspace_id = ?
        ORDER BY p.created_at DESC
        """,
        (session["user_id"], ws_id),
    ).fetchall()
    conn.close()
    return jsonify({"projects": [dict(r) for r in rows]})


@bp.post("/api/projects")
@active_required
def create_project():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required"}), 400

    conn = get_db()
    ws_id = workspace_id(conn)
    cur = conn.execute(
        "INSERT INTO projects (name, description, owner_id, workspace_id) "
        "VALUES (?, ?, ?, ?)",
        (name, (data.get("description") or "").strip(), session["user_id"], ws_id),
    )
    log_activity(
        conn, session["user_id"], "project_create",
        f'Created project "{name}"', ref_type="project", ref_id=cur.lastrowid,
    )
    conn.commit()
    row = conn.execute(
        "SELECT id, name, description, created_at FROM projects WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    conn.close()
    return jsonify({"project": dict(row)}), 201