"""Profile blueprint — the signed-in user's own activity timeline.

Privacy rule: only the signed-in user's own activity is ever returned.
There is no endpoint that exposes another user's activity; admins manage
users through the existing admin endpoints, not through profile activity.
"""

from flask import Blueprint, jsonify, session

from auth import active_required
from db import get_db

bp = Blueprint("profile", __name__)

ACTIVITY_LIMIT = 50


@bp.get("/api/profile/activity")
@active_required
def profile_activity():
    """Return the signed-in user's recent activity, newest first."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, activity_type, description, ref_type, ref_id, created_at
        FROM activity_log
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (session["user_id"], ACTIVITY_LIMIT),
    ).fetchall()
    conn.close()
    return jsonify({"activity": [dict(r) for r in rows]})