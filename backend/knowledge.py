"""Knowledge blueprint — global search, related documents, knowledge gaps.

- GET  /api/search?q=…        search across all projects the user owns
- POST /api/documents/<id>/related   semantically similar documents (owner only)
- GET  /api/knowledge-gaps    frequently unanswered AI questions (admin only)

All queries are scoped to projects owned by the signed-in user AND inside
the user's workspace, so users can only ever see their own authorised
documents and never content from another organisation workspace.
"""

from flask import Blueprint, jsonify, request, session

from auth import active_required, is_admin, workspace_id
from config import DUPLICATE_THRESHOLD
from db import get_db, log_activity
from search import hybrid_search

# Only show documents with at least 10% similarity as "related".
RELATED_MIN_SIMILARITY = 0.1


def _duplicate_pairs(conn, uid=None, ws_id=None, limit=10):
    """Find near-duplicate document pairs (TF-IDF cosine similarity).

    uid=None scans every project in the workspace (admin insights);
    otherwise only the user's own projects are scanned. ws_id always
    restricts the scan to one workspace.
    """
    if uid is None:
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.text, p.name AS project_name
            FROM documents d
            JOIN projects p ON p.id = d.project_id
            WHERE p.workspace_id = ? AND d.is_current = 1 AND d.is_archived = 0
              AND d.text != ''
            """,
            (ws_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.text, p.name AS project_name
            FROM documents d
            JOIN projects p ON p.id = d.project_id
            WHERE p.owner_id = ? AND p.workspace_id = ?
              AND d.is_current = 1 AND d.is_archived = 0 AND d.text != ''
            """,
            (uid, ws_id),
        ).fetchall()
    docs = [dict(r) for r in rows]
    if len(docs) < 2:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
        matrix = vectorizer.fit_transform([d["text"] for d in docs])
        sims = cosine_similarity(matrix)
    except ValueError:
        return []

    pairs = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            score = float(sims[i][j])
            if score >= DUPLICATE_THRESHOLD:
                pairs.append(
                    {
                        "document_a": docs[i]["filename"],
                        "document_b": docs[j]["filename"],
                        "project_a": docs[i]["project_name"],
                        "project_b": docs[j]["project_name"],
                        "similarity": round(score, 3),
                    }
                )
    pairs.sort(key=lambda x: x["similarity"], reverse=True)
    return pairs[:limit]

bp = Blueprint("knowledge", __name__)


# --------------------------------------------------------------------------
# Part 1 — Knowledge search (across all authorised projects)
# --------------------------------------------------------------------------

@bp.get("/api/search")
@active_required
def search():
    """Hybrid search: keyword + semantic (LSA) embeddings.

    Only documents in projects owned by the signed-in user (inside their
    workspace) are considered, so results never leak documents the user
    cannot access. Optional filters (category, type, project, uploader,
    date range, tags) narrow the authorised set further.
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})

    conn = get_db()
    try:
        ws_id = workspace_id(conn)
        results = hybrid_search(
            conn, session["user_id"], ws_id, q,
            category=(request.args.get("category") or "").strip() or None,
            doc_type=(request.args.get("type") or "").strip() or None,
            project_id=(request.args.get("project_id") or "").strip() or None,
            uploaded_by=(request.args.get("uploaded_by") or "").strip() or None,
            date_from=(request.args.get("date_from") or "").strip() or None,
            date_to=(request.args.get("date_to") or "").strip() or None,
            tags=(request.args.get("tags") or "").strip() or None,
        )
        log_activity(
            conn, session["user_id"], "search",
            f'Searched for "{q}"',
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"results": results, "query": q})


@bp.get("/api/search/suggestions")
@active_required
def search_suggestions():
    """Lightweight search suggestions from the user's own documents.

    Returns up to 6 suggestion strings (titles, categories, tags) that match
    the typed prefix. Only the signed-in user's authorised documents are
    consulted, so suggestions can never leak another user's content.
    """
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 1:
        return jsonify({"suggestions": []})

    conn = get_db()
    try:
        ws_id = workspace_id(conn)
        rows = conn.execute(
            """
            SELECT d.title, d.category, d.tags
            FROM documents d
            JOIN projects p ON p.id = d.project_id
            WHERE p.owner_id = ? AND p.workspace_id = ?
              AND d.is_current = 1 AND d.is_archived = 0
            """,
            (session["user_id"], ws_id),
        ).fetchall()
    finally:
        conn.close()

    suggestions = []
    seen = set()
    for r in rows:
        for field in (r["title"], r["category"], r["tags"]):
            if not field:
                continue
            for piece in field.split(","):
                piece = piece.strip()
                if not piece or piece.lower() in seen:
                    continue
                if piece.lower().startswith(q):
                    seen.add(piece.lower())
                    suggestions.append(piece)
        if len(suggestions) >= 6:
            break
    return jsonify({"suggestions": suggestions[:6]})


# --------------------------------------------------------------------------
# Part 3 — Related documents (semantic similarity, owner's projects only)
# --------------------------------------------------------------------------

@bp.post("/api/documents/<int:doc_id>/related")
@active_required
def related(doc_id):
    conn = get_db()
    ws_id = workspace_id(conn)
    target = conn.execute(
        """
        SELECT d.id, d.text
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE d.id = ? AND p.owner_id = ? AND p.workspace_id = ?
          AND d.is_current = 1 AND d.is_archived = 0
        """,
        (doc_id, session["user_id"], ws_id),
    ).fetchone()
    if not target:
        conn.close()
        return jsonify({"error": "Document not found"}), 404

    rows = conn.execute(
        """
        SELECT d.id, d.filename, d.title, d.text,
               p.id AS project_id, p.name AS project_name
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE p.owner_id = ? AND p.workspace_id = ?
          AND d.is_current = 1 AND d.is_archived = 0 AND d.id != ?
        """,
        (session["user_id"], ws_id, doc_id),
    ).fetchall()
    log_activity(
        conn, session["user_id"], "knowledge_access",
        f'Explored related documents for "{target["title"] or target["filename"]}"',
        ref_type="document", ref_id=doc_id,
    )
    conn.commit()
    conn.close()

    docs = [dict(r) for r in rows]
    if not docs or not (target["text"] or "").strip():
        return jsonify({"related": []})

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
        matrix = vectorizer.fit_transform([target["text"]] + [d["text"] for d in docs])
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
    except ValueError:
        return jsonify({"related": []})

    ranked = sorted(zip(docs, sims), key=lambda x: x[1], reverse=True)
    related = [
        {
            "document_id": d["id"],
            "filename": d["filename"],
            "title": d["title"],
            "project_id": d["project_id"],
            "project_name": d["project_name"],
            "similarity": round(float(s), 3),
        }
        for d, s in ranked[:3]
        if s >= RELATED_MIN_SIMILARITY
    ]
    return jsonify({"related": related})


# --------------------------------------------------------------------------
# Part 4 — Knowledge gaps (admin view of unanswered questions)
# --------------------------------------------------------------------------

@bp.get("/api/knowledge-gaps")
@active_required
def knowledge_gaps():
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403

    gaps = conn.execute(
        """
        SELECT question, COUNT(*) AS occurrences, MAX(asked_at) AS last_asked
        FROM knowledge_gaps
        WHERE workspace_id = ?
        GROUP BY question
        ORDER BY occurrences DESC, last_asked DESC
        LIMIT 50
        """,
        (ws_id,),
    ).fetchall()
    conn.close()
    return jsonify({"gaps": [dict(g) for g in gaps]})


# --------------------------------------------------------------------------
# Dashboard (real statistics for the signed-in user)
# --------------------------------------------------------------------------

@bp.get("/api/dashboard")
@active_required
def dashboard():
    uid = session["user_id"]
    conn = get_db()
    ws_id = workspace_id(conn)

    projects_count = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE owner_id = ? AND workspace_id = ?",
        (uid, ws_id),
    ).fetchone()[0]
    documents_count = conn.execute(
        """
        SELECT COUNT(*) FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE p.owner_id = ? AND p.workspace_id = ?
          AND d.is_current = 1 AND d.is_archived = 0
        """,
        (uid, ws_id),
    ).fetchone()[0]

    recent_uploads = conn.execute(
        """
        SELECT d.id, d.filename, d.title, d.version, d.created_at,
               p.name AS project_name
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE p.owner_id = ? AND p.workspace_id = ?
          AND d.is_current = 1 AND d.is_archived = 0
        ORDER BY d.created_at DESC
        LIMIT 5
        """,
        (uid, ws_id),
    ).fetchall()

    recent_updates = conn.execute(
        """
        SELECT d.id, d.filename, d.title, d.version, d.created_at,
               p.name AS project_name
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE p.owner_id = ? AND p.workspace_id = ?
          AND d.is_current = 1 AND d.is_archived = 0 AND d.version > 1
        ORDER BY d.created_at DESC
        LIMIT 5
        """,
        (uid, ws_id),
    ).fetchall()

    recent_gaps = conn.execute(
        """
        SELECT question, asked_at FROM knowledge_gaps
        WHERE user_id = ? AND workspace_id = ?
        ORDER BY asked_at DESC
        LIMIT 5
        """,
        (uid, ws_id),
    ).fetchall()
    conn.close()

    return jsonify(
        {
            "projects_count": projects_count,
            "documents_count": documents_count,
            "recent_uploads": [dict(r) for r in recent_uploads],
            "recent_updates": [dict(r) for r in recent_updates],
            "recent_gaps": [dict(r) for r in recent_gaps],
            "potential_duplicates": _duplicate_pairs(
                get_db(), uid=uid, ws_id=ws_id, limit=5
            ),
        }
    )


# --------------------------------------------------------------------------
# Admin — user management
# --------------------------------------------------------------------------

def _require_admin(conn):
    """True if the signed-in user is an admin of their own workspace."""
    ws_id = workspace_id(conn)
    return is_admin(conn, ws_id)


@bp.get("/api/admin/users")
@active_required
def admin_users():
    conn = get_db()
    ws_id = workspace_id(conn)
    if not _require_admin(conn):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403

    rows = conn.execute(
        """
        SELECT u.id, u.username, u.full_name, u.email, u.is_admin,
               u.status, u.terms_accepted, u.security_agreed,
               u.position, u.department, u.employee_id, u.phone,
               u.created_at, u.approved_at, u.rejected_reason, u.suspended_reason,
               (SELECT COUNT(*) FROM projects p WHERE p.owner_id = u.id
                AND p.workspace_id = u.workspace_id)
                   AS project_count,
               (SELECT COUNT(*) FROM documents d
                JOIN projects p ON p.id = d.project_id
                WHERE p.owner_id = u.id AND p.workspace_id = u.workspace_id
                  AND d.is_current = 1 AND d.is_archived = 0)
                   AS document_count
        FROM users u
        WHERE u.workspace_id = ?
        ORDER BY u.created_at
        """,
        (ws_id,),
    ).fetchall()
    conn.close()
    return jsonify({"users": [dict(r) for r in rows]})


@bp.post("/api/admin/users/<int:user_id>/admin")
@active_required
def toggle_admin(user_id):
    conn = get_db()
    ws_id = workspace_id(conn)
    if not _require_admin(conn):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    if user_id == session["user_id"]:
        conn.close()
        return jsonify({"error": "You cannot change your own admin status"}), 400

    row = conn.execute(
        "SELECT id, username, is_admin FROM users WHERE id = ? AND workspace_id = ?",
        (user_id, ws_id),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "User not found"}), 404

    new_value = 0 if row["is_admin"] else 1
    conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_value, user_id))
    conn.commit()
    conn.close()
    return jsonify(
        {"ok": True, "username": row["username"], "is_admin": bool(new_value)}
    )


def _admin_target(conn, user_id):
    """Shared guard for account-status actions.

    The target must belong to the admin's own workspace. Returns
    (error_response, target_row); error_response is None on success.
    """
    ws_id = workspace_id(conn)
    if not _require_admin(conn):
        return (jsonify({"error": "Admin access required"}), 403), None
    if user_id == session["user_id"]:
        return (jsonify({"error": "You cannot change your own account status"}), 400), None
    row = conn.execute(
        "SELECT id, username, status FROM users WHERE id = ? AND workspace_id = ?",
        (user_id, ws_id),
    ).fetchone()
    if not row:
        return (jsonify({"error": "User not found"}), 404), None
    return None, row


@bp.post("/api/admin/users/<int:user_id>/approve")
@active_required
def approve_user(user_id):
    conn = get_db()
    err, row = _admin_target(conn, user_id)
    if err:
        conn.close()
        return err
    conn.execute(
        "UPDATE users SET status = 'active', approved_by = ?, "
        "approved_at = datetime('now'), rejected_reason = NULL, "
        "suspended_reason = NULL WHERE id = ?",
        (session["user_id"], user_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "username": row["username"], "status": "active"})


@bp.post("/api/admin/users/<int:user_id>/reject")
@active_required
def reject_user(user_id):
    data = request.get_json(force=True) or {}
    reason = (data.get("reason") or "").strip()[:300]
    conn = get_db()
    err, row = _admin_target(conn, user_id)
    if err:
        conn.close()
        return err
    conn.execute(
        "UPDATE users SET status = 'rejected', rejected_reason = ?, "
        "suspended_reason = NULL WHERE id = ?",
        (reason or None, user_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "username": row["username"], "status": "rejected"})


@bp.post("/api/admin/users/<int:user_id>/suspend")
@active_required
def suspend_user(user_id):
    data = request.get_json(force=True) or {}
    reason = (data.get("reason") or "").strip()[:300]
    conn = get_db()
    err, row = _admin_target(conn, user_id)
    if err:
        conn.close()
        return err
    conn.execute(
        "UPDATE users SET status = 'suspended', suspended_reason = ?, "
        "rejected_reason = NULL WHERE id = ?",
        (reason or None, user_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "username": row["username"], "status": "suspended"})


@bp.post("/api/admin/users/<int:user_id>/reactivate")
@active_required
def reactivate_user(user_id):
    conn = get_db()
    err, row = _admin_target(conn, user_id)
    if err:
        conn.close()
        return err
    conn.execute(
        "UPDATE users SET status = 'active', approved_by = ?, "
        "approved_at = datetime('now'), rejected_reason = NULL, "
        "suspended_reason = NULL WHERE id = ?",
        (session["user_id"], user_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "username": row["username"], "status": "active"})


# --------------------------------------------------------------------------
# Admin — knowledge insights (gaps + duplicates across all projects)
# --------------------------------------------------------------------------

@bp.get("/api/admin/insights")
@active_required
def admin_insights():
    conn = get_db()
    ws_id = workspace_id(conn)
    if not _require_admin(conn):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403

    gaps = conn.execute(
        """
        SELECT question, COUNT(*) AS occurrences, MAX(asked_at) AS last_asked
        FROM knowledge_gaps
        WHERE workspace_id = ?
        GROUP BY question
        ORDER BY occurrences DESC, last_asked DESC
        LIMIT 50
        """,
        (ws_id,),
    ).fetchall()
    conn.close()

    return jsonify(
        {
            "gaps": [dict(g) for g in gaps],
            "duplicates": _duplicate_pairs(get_db(), uid=None, ws_id=ws_id, limit=10),
        }
    )