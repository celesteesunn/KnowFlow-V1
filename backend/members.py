"""Members blueprint — enterprise directory, member profiles and admin
member management.

Privacy rules are enforced here (never just hidden in the UI):
- Only active accounts can view the directory (active_required).
- employee_id is visible only to admins and the member themselves.
- email is visible only to admins (members see their own via /api/auth/me).
- Social links honour the member's linkedin_visible / github_visible
  settings; admins and the member themselves always see their own links.
- profile_visibility='private' hides the member from directory lists and
  profile lookups for non-admins (admins and the member still see them).
- last_active_at and activity are never exposed through the directory.
- No document or project content is exposed through the directory.
"""

from flask import Blueprint, jsonify, request, session

from auth import active_required, is_admin, workspace_id
from db import get_db, log_activity

bp = Blueprint("members", __name__)

# Explicit leadership designations. Never inferred from personal data.
LEADERSHIP_ROLES = ("leadership", "department_head", "team_lead", "project_lead")

# Accounts that appear in the directory. Pending and rejected accounts are
# managed by admins on the Admin page, not in the directory.
DIRECTORY_STATUSES = ("active", "suspended")

VALID_VISIBILITY = ("everyone", "members", "private")


def _is_admin(conn):
    """True if the signed-in user is an admin of their own workspace."""
    return is_admin(conn, workspace_id(conn))


def _member_summary(row, viewer_id, viewer_admin):
    """RBAC-filtered member record for directory lists and profiles."""
    is_self = row["id"] == viewer_id
    data = {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "position": row["position"],
        "department": row["department"],
        "org_role": row["org_role"],
        "avatar": row["avatar"],
        "status": row["status"],
        "created_at": row["created_at"],
    }
    if viewer_admin or is_self:
        data["employee_id"] = row["employee_id"]
    if viewer_admin:
        data["email"] = row["email"]
    if viewer_admin or is_self or row["linkedin_visible"]:
        data["linkedin_url"] = row["linkedin_url"]
    if viewer_admin or is_self or row["github_visible"]:
        data["github_url"] = row["github_url"]
    return data


def _visible(conn, target_id, viewer_id, viewer_admin):
    """True if the target member may be seen by the viewer.

    Hidden when the account is outside the directory (pending/rejected),
    belongs to a different workspace, or the member set
    profile_visibility='private' and the viewer is neither an admin nor the
    member themselves.
    """
    ws_id = workspace_id(conn)
    row = conn.execute(
        "SELECT status, profile_visibility, workspace_id FROM users WHERE id = ?",
        (target_id,),
    ).fetchone()
    if not row:
        return False
    if row["workspace_id"] != ws_id:
        return False
    if row["status"] not in DIRECTORY_STATUSES and not viewer_admin:
        return False
    if (
        row["profile_visibility"] == "private"
        and not viewer_admin
        and target_id != viewer_id
    ):
        return False
    return True


def _like_pattern(q):
    """Escape a search term for a LIKE ... ESCAPE '\\' pattern."""
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@bp.get("/api/members")
@active_required
def list_members():
    """Directory list with search and category filters.

    Query params:
        q          search term (name, username, position, department)
        category   all | active | recently_joined | my_department |
                   my_projects | leadership
        department exact department filter (used by the Departments browse)
    """
    conn = get_db()
    viewer_admin = _is_admin(conn)
    viewer_id = session["user_id"]
    ws_id = workspace_id(conn)

    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "all").strip()
    department = (request.args.get("department") or "").strip()

    where = ["u.status IN ('active', 'suspended')", "u.workspace_id = ?"]
    params = [ws_id]

    if category == "active":
        where.append("u.status = 'active'")
    elif category == "leadership":
        placeholders = ",".join("?" for _ in LEADERSHIP_ROLES)
        where.append(f"u.org_role IN ({placeholders})")
        params.extend(LEADERSHIP_ROLES)
    elif category == "my_department":
        viewer = conn.execute(
            "SELECT department FROM users WHERE id = ?", (viewer_id,)
        ).fetchone()
        if viewer and viewer["department"]:
            where.append("u.department = ?")
            params.append(viewer["department"])
        else:
            # Viewer has no department — nothing to show in this category.
            conn.close()
            return jsonify({"members": [], "total": 0})
    elif category == "my_projects":
        # Members who share projects with the viewer: they uploaded documents
        # to the viewer's projects, or own projects the viewer contributed to.
        where.append(
            """
            (
                u.id IN (
                    SELECT d.uploaded_by FROM documents d
                    JOIN projects p ON p.id = d.project_id
                    WHERE p.owner_id = ? AND p.workspace_id = ?
                )
                OR u.id IN (
                    SELECT p.owner_id FROM projects p
                    JOIN documents d ON d.project_id = p.id
                    WHERE d.uploaded_by = ? AND p.workspace_id = ?
                )
            )
            """
        )
        params.extend([viewer_id, ws_id, viewer_id, ws_id])
    elif category == "recently_joined":
        pass  # ordering + limit below
    elif category != "all":
        conn.close()
        return jsonify({"error": "Unknown category"}), 400

    if department:
        where.append("u.department = ?")
        params.append(department)

    if q:
        pattern = _like_pattern(q)
        where.append(
            """
            (
                u.full_name LIKE ? ESCAPE '\\'
                OR u.username LIKE ? ESCAPE '\\'
                OR u.position LIKE ? ESCAPE '\\'
                OR u.department LIKE ? ESCAPE '\\'
            )
            """
        )
        params.extend([pattern, pattern, pattern, pattern])

    # profile_visibility='private' hides the member from non-admins.
    if not viewer_admin:
        where.append(
            "(u.profile_visibility IS NULL OR u.profile_visibility != 'private')"
        )

    order = (
        "u.created_at DESC"
        if category == "recently_joined"
        else "CASE WHEN u.status = 'active' THEN 0 ELSE 1 END, "
        "COALESCE(u.full_name, u.username) COLLATE NOCASE"
    )
    limit = " LIMIT 12" if category == "recently_joined" else ""

    sql = (
        "SELECT u.* FROM users u WHERE "
        + " AND ".join(where)
        + f" ORDER BY {order}{limit}"
    )
    rows = conn.execute(sql, params).fetchall()
    members = [_member_summary(r, viewer_id, viewer_admin) for r in rows]
    conn.close()
    return jsonify({"members": members, "total": len(members)})


@bp.get("/api/members/departments")
@active_required
def list_departments():
    """Distinct departments with directory member counts (own workspace)."""
    conn = get_db()
    viewer_admin = _is_admin(conn)
    ws_id = workspace_id(conn)
    if not viewer_admin:
        rows = conn.execute(
            """
            SELECT department AS name, COUNT(*) AS count
            FROM users
            WHERE workspace_id = ?
              AND status IN ('active', 'suspended')
              AND department IS NOT NULL AND department != ''
              AND (profile_visibility IS NULL OR profile_visibility != 'private')
            GROUP BY department
            ORDER BY department COLLATE NOCASE
            """,
            (ws_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT department AS name, COUNT(*) AS count
            FROM users
            WHERE workspace_id = ?
              AND status IN ('active', 'suspended')
              AND department IS NOT NULL AND department != ''
            GROUP BY department
            ORDER BY department COLLATE NOCASE
            """,
            (ws_id,),
        ).fetchall()
    conn.close()
    return jsonify({"departments": [dict(r) for r in rows]})


@bp.get("/api/members/<int:user_id>")
@active_required
def member_profile(user_id):
    """Member profile detail (RBAC-filtered)."""
    conn = get_db()
    viewer_admin = _is_admin(conn)
    viewer_id = session["user_id"]

    if not _visible(conn, user_id, viewer_id, viewer_admin):
        conn.close()
        return jsonify({"error": "Member not found"}), 404

    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Member not found"}), 404

    member = _member_summary(row, viewer_id, viewer_admin)
    conn.close()
    return jsonify({"member": member})


@bp.post("/api/members/<int:user_id>")
@active_required
def update_member(user_id):
    """Admin-only: edit professional info, department, role and employee id.

    Account status changes (activate/deactivate) stay on the existing
    /api/admin/users endpoints so approval/suspension reasons are recorded
    in one place.
    """
    conn = get_db()
    if not _is_admin(conn):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403

    ws_id = workspace_id(conn)
    row = conn.execute(
        "SELECT id, username, full_name FROM users WHERE id = ? AND workspace_id = ?",
        (user_id, ws_id),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Member not found"}), 404

    data = request.get_json(force=True) or {}
    position = (data.get("position") or "").strip()
    department = (data.get("department") or "").strip()
    employee_id = (data.get("employee_id") or "").strip()
    org_role = (data.get("org_role") or "").strip() or None

    if len(position) > 100:
        conn.close()
        return jsonify({"error": "Position is too long (max 100 characters)"}), 400
    if len(department) > 100:
        conn.close()
        return jsonify({"error": "Department is too long (max 100 characters)"}), 400
    if len(employee_id) > 50:
        conn.close()
        return jsonify({"error": "Employee ID is too long (max 50 characters)"}), 400
    if org_role and org_role not in LEADERSHIP_ROLES:
        conn.close()
        return jsonify({"error": "Invalid organisational role"}), 400

    conn.execute(
        """
        UPDATE users
        SET position = ?, department = ?, employee_id = ?, org_role = ?
        WHERE id = ?
        """,
        (position or None, department or None, employee_id or None, org_role, user_id),
    )
    log_activity(
        conn, session["user_id"], "member_update",
        f'Updated member profile for "{row["full_name"] or row["username"]}"',
        ref_type="user", ref_id=user_id,
    )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return jsonify({"member": _member_summary(updated, user_id, True)})