"""Knowledge blueprint — global search, related documents, knowledge gaps.

- GET  /api/search?q=…        search across all projects the user owns
- POST /api/documents/<id>/related   semantically similar documents (owner only)
- GET  /api/knowledge-gaps    frequently unanswered AI questions (admin only)

All queries are scoped to projects owned by the signed-in user, so users can
only ever see their own authorised documents.
"""

from flask import Blueprint, jsonify, request, session

from auth import login_required
from config import DUPLICATE_THRESHOLD
from db import get_db

# Only show documents with at least 10% similarity as "related".
RELATED_MIN_SIMILARITY = 0.1


def _duplicate_pairs(conn, uid=None, limit=10):
    """Find near-duplicate document pairs (TF-IDF cosine similarity).

    uid=None scans every project (admin insights); otherwise only the
    user's own projects are scanned.
    """
    if uid is None:
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.text, p.name AS project_name
            FROM documents d
            JOIN projects p ON p.id = d.project_id
            WHERE d.is_current = 1 AND d.is_archived = 0 AND d.text != ''
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.text, p.name AS project_name
            FROM documents d
            JOIN projects p ON p.id = d.project_id
            WHERE p.owner_id = ? AND d.is_current = 1 AND d.is_archived = 0
              AND d.text != ''
            """,
            (uid,),
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
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})

    conn = get_db()
    rows = conn.execute(
        """
        SELECT d.id AS document_id, d.filename, d.title,
               p.id AS project_id, p.name AS project_name,
               pg.page_number, pg.text
        FROM document_pages pg
        JOIN documents d ON d.id = pg.document_id
        JOIN projects p ON p.id = d.project_id
        WHERE p.owner_id = ? AND d.is_current = 1 AND d.is_archived = 0
          AND (pg.text LIKE ? OR d.filename LIKE ?)
        ORDER BY d.created_at DESC
        LIMIT 20
        """,
        (session["user_id"], f"%{q}%", f"%{q}%"),
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        text = r["text"] or ""
        idx = text.lower().find(q.lower())
        if idx == -1:
            idx = 0  # match came from the filename
        start = max(0, idx - 120)
        snippet = " ".join(text[start : start + 300].split())
        results.append(
            {
                "document_id": r["document_id"],
                "filename": r["filename"],
                "title": r["title"],
                "project_id": r["project_id"],
                "project_name": r["project_name"],
                "page_number": r["page_number"],
                "snippet": snippet,
            }
        )
    return jsonify({"results": results})


# --------------------------------------------------------------------------
# Part 3 — Related documents (semantic similarity, owner's projects only)
# --------------------------------------------------------------------------

@bp.post("/api/documents/<int:doc_id>/related")
@login_required
def related(doc_id):
    conn = get_db()
    target = conn.execute(
        """
        SELECT d.id, d.text
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE d.id = ? AND p.owner_id = ? AND d.is_current = 1 AND d.is_archived = 0
        """,
        (doc_id, session["user_id"]),
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
        WHERE p.owner_id = ? AND d.is_current = 1 AND d.is_archived = 0
          AND d.id != ?
        """,
        (session["user_id"], doc_id),
    ).fetchall()
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
@login_required
def knowledge_gaps():
    conn = get_db()
    row = conn.execute(
        "SELECT is_admin FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    if not row or not row["is_admin"]:
        conn.close()
        return jsonify({"error": "Admin access required"}), 403

    gaps = conn.execute(
        """
        SELECT question, COUNT(*) AS occurrences, MAX(asked_at) AS last_asked
        FROM knowledge_gaps
        GROUP BY question
        ORDER BY occurrences DESC, last_asked DESC
        LIMIT 50
        """
    ).fetchall()
    conn.close()
    return jsonify({"gaps": [dict(g) for g in gaps]})


# --------------------------------------------------------------------------
# Dashboard (real statistics for the signed-in user)
# --------------------------------------------------------------------------

@bp.get("/api/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    conn = get_db()

    projects_count = conn.execute(
        "SELECT COUNT(*) FROM projects WHERE owner_id = ?", (uid,)
    ).fetchone()[0]
    documents_count = conn.execute(
        """
        SELECT COUNT(*) FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE p.owner_id = ? AND d.is_current = 1 AND d.is_archived = 0
        """,
        (uid,),
    ).fetchone()[0]

    recent_uploads = conn.execute(
        """
        SELECT d.id, d.filename, d.title, d.version, d.created_at,
               p.name AS project_name
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE p.owner_id = ? AND d.is_current = 1 AND d.is_archived = 0
        ORDER BY d.created_at DESC
        LIMIT 5
        """,
        (uid,),
    ).fetchall()

    recent_updates = conn.execute(
        """
        SELECT d.id, d.filename, d.title, d.version, d.created_at,
               p.name AS project_name
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE p.owner_id = ? AND d.is_current = 1 AND d.is_archived = 0
          AND d.version > 1
        ORDER BY d.created_at DESC
        LIMIT 5
        """,
        (uid,),
    ).fetchall()

    recent_gaps = conn.execute(
        """
        SELECT question, asked_at FROM knowledge_gaps
        WHERE user_id = ?
        ORDER BY asked_at DESC
        LIMIT 5
        """,
        (uid,),
    ).fetchall()
    conn.close()

    return jsonify(
        {
            "projects_count": projects_count,
            "documents_count": documents_count,
            "recent_uploads": [dict(r) for r in recent_uploads],
            "recent_updates": [dict(r) for r in recent_updates],
            "recent_gaps": [dict(r) for r in recent_gaps],
            "potential_duplicates": _duplicate_pairs(get_db(), uid=uid, limit=5),
        }
    )


# --------------------------------------------------------------------------
# Admin — user management
# --------------------------------------------------------------------------

def _require_admin(conn):
    row = conn.execute(
        "SELECT is_admin FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    return bool(row and row["is_admin"])


@bp.get("/api/admin/users")
@login_required
def admin_users():
    conn = get_db()
    if not _require_admin(conn):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403

    rows = conn.execute(
        """
        SELECT u.id, u.username, u.full_name, u.is_admin, u.created_at,
               (SELECT COUNT(*) FROM projects p WHERE p.owner_id = u.id)
                   AS project_count,
               (SELECT COUNT(*) FROM documents d
                JOIN projects p ON p.id = d.project_id
                WHERE p.owner_id = u.id AND d.is_current = 1 AND d.is_archived = 0)
                   AS document_count
        FROM users u
        ORDER BY u.created_at
        """
    ).fetchall()
    conn.close()
    return jsonify({"users": [dict(r) for r in rows]})


@bp.post("/api/admin/users/<int:user_id>/admin")
@login_required
def toggle_admin(user_id):
    conn = get_db()
    if not _require_admin(conn):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    if user_id == session["user_id"]:
        conn.close()
        return jsonify({"error": "You cannot change your own admin status"}), 400

    row = conn.execute(
        "SELECT id, username, is_admin FROM users WHERE id = ?", (user_id,)
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


# --------------------------------------------------------------------------
# Admin — knowledge insights (gaps + duplicates across all projects)
# --------------------------------------------------------------------------

@bp.get("/api/admin/insights")
@login_required
def admin_insights():
    conn = get_db()
    if not _require_admin(conn):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403

    gaps = conn.execute(
        """
        SELECT question, COUNT(*) AS occurrences, MAX(asked_at) AS last_asked
        FROM knowledge_gaps
        GROUP BY question
        ORDER BY occurrences DESC, last_asked DESC
        LIMIT 50
        """
    ).fetchall()
    conn.close()

    return jsonify(
        {
            "gaps": [dict(g) for g in gaps],
            "duplicates": _duplicate_pairs(get_db(), uid=None, limit=10),
        }
    )