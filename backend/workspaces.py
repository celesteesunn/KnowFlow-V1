"""Workspaces blueprint — organisation workspace creation, joining via
workspace code, access requests, in-app notifications, and workspace-scoped
admin management (access requests, roles, departments, workspace settings).

Security model (enforced here, never just in the UI):
- Every endpoint resolves the signed-in user's workspace and scopes all
  queries to it. Cross-workspace access is impossible by construction.
- Admin endpoints require is_admin AND membership in the target workspace.
- The workspace code is an identifier/invitation, not a password: it can be
  regenerated without revoking previously approved users.
- Employee IDs are validated and unique per workspace; the API never
  discloses whether an ID belongs to another person.
- Only the workspace's configured departments are accepted for access
  requests (no arbitrary department strings).
"""

import json
import re
import secrets

from flask import Blueprint, jsonify, request, session

from auth import _public_user, active_required, is_admin, login_required, workspace_id
from db import DEFAULT_DEPARTMENTS, DEFAULT_ROLES, get_db, log_activity

bp = Blueprint("workspaces", __name__)

CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TIMEZONES = (
    "UTC", "America/New_York", "America/Chicago", "America/Denver",
    "America/Los_Angeles", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Asia/Tokyo",
    "Australia/Sydney", "Africa/Johannesburg", "America/Sao_Paulo",
)
LANGUAGES = ("en", "es", "fr", "de", "hi", "ar", "zh", "ja")


def _notify(conn, user_id, workspace_id, message):
    """Insert an in-app notification for a user."""
    conn.execute(
        "INSERT INTO notifications (user_id, workspace_id, message) VALUES (?, ?, ?)",
        (user_id, workspace_id, message),
    )


def _notify_workspace_admins(conn, ws_id, message):
    """Notify every active admin of a workspace."""
    admins = conn.execute(
        "SELECT id FROM users WHERE workspace_id = ? AND is_admin = 1 "
        "AND status = 'active'",
        (ws_id,),
    ).fetchall()
    for a in admins:
        _notify(conn, a["id"], ws_id, message)


def _workspace_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "code": row["code"],
        "org_name": row["org_name"],
        "org_email": row["org_email"],
        "org_website": row["org_website"],
        "timezone": row["timezone"],
        "language": row["language"],
        "require_admin_approval": bool(row["require_admin_approval"]),
        "invite_code_required": bool(row["invite_code_required"]),
        "email_domain": row["email_domain"],
        "created_at": row["created_at"],
    }


# --------------------------------------------------------------------------
# Onboarding — create workspace (Admin / Workspace Owner flow)
# --------------------------------------------------------------------------

@bp.post("/api/workspaces")
@login_required
def create_workspace():
    data = request.get_json(force=True) or {}
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "Authentication required"}), 401
    if user["workspace_id"]:
        conn.close()
        return jsonify({"error": "You already belong to a workspace"}), 400

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    code = (data.get("code") or "").strip().upper()
    org_name = (data.get("org_name") or "").strip() or name
    org_email = (data.get("org_email") or "").strip().lower()
    org_website = (data.get("org_website") or "").strip()
    timezone = (data.get("timezone") or "UTC").strip()
    language = (data.get("language") or "en").strip()
    require_approval = 1 if data.get("require_admin_approval", True) else 0
    invite_required = 1 if data.get("invite_code_required", True) else 0
    email_domain = (data.get("email_domain") or "").strip().lower()

    if not name or len(name) > 120:
        conn.close()
        return jsonify({"error": "Workspace name is required (max 120 characters)"}), 400
    if len(description) > 500:
        conn.close()
        return jsonify({"error": "Description is too long (max 500 characters)"}), 400
    if not CODE_RE.match(code):
        conn.close()
        return (
            jsonify(
                {
                    "error": (
                        "Workspace code must be 2-32 characters using letters, "
                        "numbers, . _ or - (for example ABC-2026)."
                    )
                }
            ),
            400,
        )
    if conn.execute("SELECT 1 FROM workspaces WHERE code = ?", (code,)).fetchone():
        conn.close()
        return (
            jsonify(
                {"error": "That workspace code is already in use. Please choose another."}
            ),
            409,
        )
    if org_email and not EMAIL_RE.match(org_email):
        conn.close()
        return jsonify({"error": "Organisation email is not valid"}), 400
    if org_website and not (
        org_website.startswith("http://") or org_website.startswith("https://")
    ):
        conn.close()
        return jsonify({"error": "Organisation website must start with http:// or https://"}), 400
    if timezone not in TIMEZONES:
        conn.close()
        return jsonify({"error": "Invalid timezone"}), 400
    if language not in LANGUAGES:
        conn.close()
        return jsonify({"error": "Invalid language"}), 400
    if email_domain:
        if not email_domain.startswith("@") or len(email_domain) < 3 or "." not in email_domain:
            conn.close()
            return jsonify({"error": "Email domain must look like @company.com"}), 400

    cur = conn.execute(
        """
        INSERT INTO workspaces
            (name, description, code, org_name, org_email, org_website,
             timezone, language, require_admin_approval, invite_code_required,
             email_domain, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            description or None,
            code,
            org_name,
            org_email or None,
            org_website or None,
            timezone,
            language,
            require_approval,
            invite_required,
            email_domain or None,
            user["id"],
        ),
    )
    ws_id = cur.lastrowid

    # Provision default departments and roles for the new workspace.
    for d in DEFAULT_DEPARTMENTS:
        conn.execute(
            "INSERT INTO departments (workspace_id, name) VALUES (?, ?)", (ws_id, d)
        )
    for rname, perms in DEFAULT_ROLES.items():
        conn.execute(
            "INSERT INTO roles (workspace_id, name, permissions, is_system) "
            "VALUES (?, ?, ?, 1)",
            (ws_id, rname, json.dumps(perms)),
        )
    owner_role = conn.execute(
        "SELECT id FROM roles WHERE workspace_id = ? AND name = 'Workspace Owner'",
        (ws_id,),
    ).fetchone()

    # The creator becomes the Workspace Owner / Admin, active immediately.
    conn.execute(
        """
        UPDATE users
        SET workspace_id = ?, is_admin = 1, status = 'active',
            position = 'Admin / Workspace Owner', role_id = ?,
            approved_by = ?, approved_at = datetime('now')
        WHERE id = ?
        """,
        (ws_id, owner_role["id"] if owner_role else None, user["id"], user["id"]),
    )
    log_activity(
        conn, user["id"], "workspace_create",
        f'Created workspace "{name}"', ref_type="workspace", ref_id=ws_id,
    )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    ws = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    conn.close()
    return jsonify(
        {"user": _public_user(updated), "workspace": _workspace_dict(ws)}
    ), 201


# --------------------------------------------------------------------------
# Onboarding — verify workspace code (employee flow, step 1)
# --------------------------------------------------------------------------

@bp.post("/api/workspaces/verify")
@login_required
def verify_workspace():
    """Look up a workspace by code.

    Returns only non-sensitive information (name + description) plus the
    workspace's configured departments, which the employee needs for the
    access request form. No member data is ever exposed here.
    """
    data = request.get_json(force=True) or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "Workspace code is required"}), 400

    conn = get_db()
    ws = conn.execute(
        "SELECT id, name, description FROM workspaces WHERE code = ?", (code,)
    ).fetchone()
    if not ws:
        conn.close()
        return (
            jsonify(
                {"error": "No workspace found with that code. Check the code and try again."}
            ),
            404,
        )
    departments = conn.execute(
        "SELECT name FROM departments WHERE workspace_id = ? ORDER BY name COLLATE NOCASE",
        (ws["id"],),
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "workspace": {
                "id": ws["id"],
                "name": ws["name"],
                "description": ws["description"] or "",
            },
            "departments": [d["name"] for d in departments],
        }
    )


# --------------------------------------------------------------------------
# Onboarding — request access (employee flow, final step)
# --------------------------------------------------------------------------

@bp.post("/api/workspaces/request-access")
@login_required
def request_access():
    data = request.get_json(force=True) or {}
    code = (data.get("code") or "").strip().upper()
    position = (data.get("position") or "").strip()
    department = (data.get("department") or "").strip()
    employee_id = (data.get("employee_id") or "").strip()

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({"error": "Authentication required"}), 401
    if user["workspace_id"]:
        conn.close()
        return jsonify({"error": "You already belong to a workspace"}), 400

    ws = conn.execute("SELECT * FROM workspaces WHERE code = ?", (code,)).fetchone()
    if not ws:
        conn.close()
        return jsonify({"error": "No workspace found with that code."}), 404
    if not position or len(position) > 100:
        conn.close()
        return jsonify({"error": "Position is required (max 100 characters)"}), 400
    if not department or len(department) > 100:
        conn.close()
        return jsonify({"error": "Department is required"}), 400
    if not employee_id or len(employee_id) > 50:
        conn.close()
        return jsonify({"error": "Employee ID is required (max 50 characters)"}), 400

    # Email domain restriction (optional workspace setting).
    if ws["email_domain"]:
        user_domain = ""
        if user["email"] and "@" in user["email"]:
            user_domain = "@" + user["email"].split("@")[-1].lower()
        if user_domain != ws["email_domain"]:
            conn.close()
            return (
                jsonify(
                    {
                        "error": (
                            "Your email domain is not allowed in this workspace. "
                            "Contact the workspace administrator."
                        )
                    }
                ),
                403,
            )

    # Department must come from the workspace's configured list.
    dept = conn.execute(
        "SELECT 1 FROM departments WHERE workspace_id = ? AND name = ?",
        (ws["id"], department),
    ).fetchone()
    if not dept:
        conn.close()
        return (
            jsonify(
                {
                    "error": (
                        "Department must be selected from the workspace's "
                        "configured departments."
                    )
                }
            ),
            400,
        )

    # Employee ID uniqueness within the workspace. The error message never
    # reveals whose ID it is — it only says the ID is already in use.
    dup = conn.execute(
        "SELECT 1 FROM users WHERE workspace_id = ? AND employee_id = ?",
        (ws["id"], employee_id),
    ).fetchone()
    if dup:
        conn.close()
        return (
            jsonify(
                {
                    "error": (
                        "This Employee ID is already associated with an account "
                        "in this workspace."
                    )
                }
            ),
            409,
        )

    conn.execute(
        """
        UPDATE users
        SET workspace_id = ?, position = ?, department = ?, employee_id = ?,
            status = 'pending_approval', access_requested_at = datetime('now'),
            rejected_reason = NULL, suspended_reason = NULL
        WHERE id = ?
        """,
        (ws["id"], position, department, employee_id, user["id"]),
    )
    _notify_workspace_admins(
        conn, ws["id"],
        f"New access request from {user['full_name'] or user['username']}.",
    )
    log_activity(
        conn, user["id"], "access_request",
        f'Requested access to "{ws["name"]}"', ref_type="workspace", ref_id=ws["id"],
    )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user["id"],)
    ).fetchone()
    conn.close()
    return jsonify(
        {
            "user": _public_user(updated),
            "workspace": {"id": ws["id"], "name": ws["name"]},
        }
    ), 201


# --------------------------------------------------------------------------
# Notifications
# --------------------------------------------------------------------------

@bp.get("/api/notifications")
@active_required
def list_notifications():
    conn = get_db()
    ws_id = workspace_id(conn)
    rows = conn.execute(
        """
        SELECT id, message, is_read, created_at
        FROM notifications
        WHERE user_id = ? AND (workspace_id IS NULL OR workspace_id = ?)
        ORDER BY created_at DESC, id DESC
        LIMIT 50
        """,
        (session["user_id"], ws_id),
    ).fetchall()
    conn.close()
    return jsonify({"notifications": [dict(r) for r in rows]})


@bp.post("/api/notifications/<int:notif_id>/read")
@active_required
def mark_notification_read(notif_id):
    conn = get_db()
    conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
        (notif_id, session["user_id"]),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.post("/api/notifications/read-all")
@active_required
def mark_all_notifications_read():
    conn = get_db()
    conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
        (session["user_id"],),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Admin — access requests
# --------------------------------------------------------------------------

@bp.get("/api/admin/access-requests")
@active_required
def access_requests():
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    rows = conn.execute(
        """
        SELECT u.id, u.username, u.full_name, u.email, u.phone, u.position,
               u.department, u.employee_id, u.avatar, u.status,
               u.access_requested_at, u.created_at
        FROM users u
        WHERE u.workspace_id = ? AND u.status = 'pending_approval'
        ORDER BY u.access_requested_at DESC, u.id DESC
        """,
        (ws_id,),
    ).fetchall()
    conn.close()
    return jsonify({"requests": [dict(r) for r in rows]})


@bp.get("/api/admin/pending-count")
@active_required
def pending_count():
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"count": 0})
    count = conn.execute(
        "SELECT COUNT(*) FROM users WHERE workspace_id = ? AND status = 'pending_approval'",
        (ws_id,),
    ).fetchone()[0]
    conn.close()
    return jsonify({"count": count})


def _access_target(conn, user_id, ws_id):
    """Shared guard for approve/reject. Returns (error, row); error None on success."""
    if not is_admin(conn, ws_id):
        return (jsonify({"error": "Admin access required"}), 403), None
    if user_id == session["user_id"]:
        return (
            jsonify({"error": "You cannot change your own account status"}),
            400,
        ), None
    row = conn.execute(
        "SELECT id, username, full_name, status FROM users "
        "WHERE id = ? AND workspace_id = ?",
        (user_id, ws_id),
    ).fetchone()
    if not row:
        return (jsonify({"error": "Request not found"}), 404), None
    return None, row


@bp.post("/api/admin/access-requests/<int:user_id>/approve")
@active_required
def approve_access_request(user_id):
    conn = get_db()
    ws_id = workspace_id(conn)
    err, row = _access_target(conn, user_id, ws_id)
    if err:
        conn.close()
        return err
    ws = conn.execute(
        "SELECT name FROM workspaces WHERE id = ?", (ws_id,)
    ).fetchone()
    conn.execute(
        """
        UPDATE users SET status = 'active', approved_by = ?,
            approved_at = datetime('now'), rejected_reason = NULL,
            suspended_reason = NULL
        WHERE id = ?
        """,
        (session["user_id"], user_id),
    )
    _notify(
        conn, user_id, ws_id,
        f"Your access request has been approved. Welcome to {ws['name']}.",
    )
    log_activity(
        conn, session["user_id"], "member_approve",
        f'Approved access for "{row["full_name"] or row["username"]}"',
        ref_type="user", ref_id=user_id,
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "username": row["username"], "status": "active"})


@bp.post("/api/admin/access-requests/<int:user_id>/reject")
@active_required
def reject_access_request(user_id):
    data = request.get_json(force=True) or {}
    reason = (data.get("reason") or "").strip()[:300]
    conn = get_db()
    ws_id = workspace_id(conn)
    err, row = _access_target(conn, user_id, ws_id)
    if err:
        conn.close()
        return err
    conn.execute(
        """
        UPDATE users SET status = 'rejected', rejected_reason = ?,
            suspended_reason = NULL
        WHERE id = ?
        """,
        (reason or None, user_id),
    )
    _notify(
        conn, user_id, ws_id,
        "Your workspace access request was not approved. Please contact your "
        "organisation administrator if you believe this was incorrect.",
    )
    log_activity(
        conn, session["user_id"], "member_reject",
        f'Rejected access for "{row["full_name"] or row["username"]}"',
        ref_type="user", ref_id=user_id,
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "username": row["username"], "status": "rejected"})


# --------------------------------------------------------------------------
# Admin — roles (explicitly configured permissions)
# --------------------------------------------------------------------------

@bp.get("/api/admin/roles")
@active_required
def list_roles():
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    rows = conn.execute(
        """
        SELECT id, name, permissions, is_system
        FROM roles WHERE workspace_id = ?
        ORDER BY is_system DESC, name COLLATE NOCASE
        """,
        (ws_id,),
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "roles": [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "permissions": json.loads(r["permissions"] or "{}"),
                    "is_system": bool(r["is_system"]),
                }
                for r in rows
            ]
        }
    )


@bp.post("/api/admin/roles")
@active_required
def create_role():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    permissions = data.get("permissions") or {}
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    if not name or len(name) > 100:
        conn.close()
        return jsonify({"error": "Role name is required (max 100 characters)"}), 400
    if conn.execute(
        "SELECT 1 FROM roles WHERE workspace_id = ? AND name = ?", (ws_id, name)
    ).fetchone():
        conn.close()
        return jsonify({"error": "A role with that name already exists"}), 409
    cur = conn.execute(
        "INSERT INTO roles (workspace_id, name, permissions) VALUES (?, ?, ?)",
        (ws_id, name, json.dumps(permissions)),
    )
    conn.commit()
    conn.close()
    return (
        jsonify(
            {
                "role": {
                    "id": cur.lastrowid,
                    "name": name,
                    "permissions": permissions,
                    "is_system": False,
                }
            }
        ),
        201,
    )


@bp.post("/api/admin/roles/<int:role_id>")
@active_required
def update_role(role_id):
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    permissions = data.get("permissions")
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    row = conn.execute(
        "SELECT id, name FROM roles WHERE id = ? AND workspace_id = ?",
        (role_id, ws_id),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Role not found"}), 404
    if name and name != row["name"]:
        if conn.execute(
            "SELECT 1 FROM roles WHERE workspace_id = ? AND name = ? AND id != ?",
            (ws_id, name, role_id),
        ).fetchone():
            conn.close()
            return jsonify({"error": "A role with that name already exists"}), 409
        conn.execute("UPDATE roles SET name = ? WHERE id = ?", (name, role_id))
    if permissions is not None:
        conn.execute(
            "UPDATE roles SET permissions = ? WHERE id = ?",
            (json.dumps(permissions), role_id),
        )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.delete("/api/admin/roles/<int:role_id>")
@active_required
def delete_role(role_id):
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    row = conn.execute(
        "SELECT id, is_system FROM roles WHERE id = ? AND workspace_id = ?",
        (role_id, ws_id),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Role not found"}), 404
    if row["is_system"]:
        conn.close()
        return jsonify({"error": "System roles cannot be deleted"}), 400
    used = conn.execute(
        "SELECT 1 FROM users WHERE role_id = ?", (role_id,)
    ).fetchone()
    if used:
        conn.close()
        return (
            jsonify({"error": "Role is assigned to members and cannot be deleted"}),
            400,
        )
    conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Admin — departments
# --------------------------------------------------------------------------

@bp.get("/api/admin/departments")
@active_required
def list_departments():
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    rows = conn.execute(
        """
        SELECT d.id, d.name,
               (SELECT COUNT(*) FROM users u
                WHERE u.workspace_id = d.workspace_id
                  AND u.department = d.name
                  AND u.status IN ('active', 'suspended')) AS member_count
        FROM departments d
        WHERE d.workspace_id = ?
        ORDER BY d.name COLLATE NOCASE
        """,
        (ws_id,),
    ).fetchall()
    conn.close()
    return jsonify({"departments": [dict(r) for r in rows]})


@bp.post("/api/admin/departments")
@active_required
def create_department():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    if not name or len(name) > 100:
        conn.close()
        return jsonify({"error": "Department name is required (max 100 characters)"}), 400
    if conn.execute(
        "SELECT 1 FROM departments WHERE workspace_id = ? AND name = ?",
        (ws_id, name),
    ).fetchone():
        conn.close()
        return jsonify({"error": "Department already exists"}), 409
    cur = conn.execute(
        "INSERT INTO departments (workspace_id, name) VALUES (?, ?)", (ws_id, name)
    )
    conn.commit()
    conn.close()
    return (
        jsonify(
            {"department": {"id": cur.lastrowid, "name": name, "member_count": 0}}
        ),
        201,
    )


@bp.delete("/api/admin/departments/<int:dept_id>")
@active_required
def delete_department(dept_id):
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    row = conn.execute(
        "SELECT id, name FROM departments WHERE id = ? AND workspace_id = ?",
        (dept_id, ws_id),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Department not found"}), 404
    used = conn.execute(
        "SELECT 1 FROM users WHERE workspace_id = ? AND department = ?",
        (ws_id, row["name"]),
    ).fetchone()
    if used:
        conn.close()
        return (
            jsonify(
                {"error": "Department is assigned to members and cannot be deleted"}
            ),
            400,
        )
    conn.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# --------------------------------------------------------------------------
# Admin — workspace settings + code regeneration
# --------------------------------------------------------------------------

@bp.get("/api/admin/workspace")
@active_required
def get_workspace():
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    ws = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    conn.close()
    if not ws:
        return jsonify({"error": "Workspace not found"}), 404
    return jsonify({"workspace": _workspace_dict(ws)})


@bp.post("/api/admin/workspace")
@active_required
def update_workspace():
    data = request.get_json(force=True) or {}
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    ws = conn.execute("SELECT * FROM workspaces WHERE id = ?", (ws_id,)).fetchone()
    if not ws:
        conn.close()
        return jsonify({"error": "Workspace not found"}), 404

    name = (data.get("name") or "").strip() or ws["name"]
    description = data.get("description")
    org_name = (data.get("org_name") or "").strip() or ws["org_name"] or name
    org_email = (data.get("org_email") or "").strip().lower()
    org_website = (data.get("org_website") or "").strip()
    timezone = (data.get("timezone") or "").strip() or ws["timezone"]
    language = (data.get("language") or "").strip() or ws["language"]
    require_approval = 1 if data.get("require_admin_approval", ws["require_admin_approval"]) else 0
    invite_required = 1 if data.get("invite_code_required", ws["invite_code_required"]) else 0
    email_domain = (data.get("email_domain") or "").strip().lower()

    if len(name) > 120:
        conn.close()
        return jsonify({"error": "Workspace name is too long (max 120 characters)"}), 400
    if description is not None and len(description) > 500:
        conn.close()
        return jsonify({"error": "Description is too long (max 500 characters)"}), 400
    if org_email and not EMAIL_RE.match(org_email):
        conn.close()
        return jsonify({"error": "Organisation email is not valid"}), 400
    if org_website and not (
        org_website.startswith("http://") or org_website.startswith("https://")
    ):
        conn.close()
        return jsonify({"error": "Organisation website must start with http:// or https://"}), 400
    if timezone not in TIMEZONES:
        conn.close()
        return jsonify({"error": "Invalid timezone"}), 400
    if language not in LANGUAGES:
        conn.close()
        return jsonify({"error": "Invalid language"}), 400
    if email_domain:
        if not email_domain.startswith("@") or len(email_domain) < 3 or "." not in email_domain:
            conn.close()
            return jsonify({"error": "Email domain must look like @company.com"}), 400

    conn.execute(
        """
        UPDATE workspaces
        SET name = ?, description = ?, org_name = ?, org_email = ?, org_website = ?,
            timezone = ?, language = ?, require_admin_approval = ?,
            invite_code_required = ?, email_domain = ?
        WHERE id = ?
        """,
        (
            name,
            (description if description is not None else ws["description"]) or None,
            org_name,
            org_email or None,
            org_website or None,
            timezone,
            language,
            require_approval,
            invite_required,
            email_domain or None,
            ws_id,
        ),
    )
    log_activity(
        conn, session["user_id"], "workspace_update",
        f'Updated workspace settings for "{name}"', ref_type="workspace", ref_id=ws_id,
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.post("/api/admin/workspace/regenerate-code")
@active_required
def regenerate_code():
    """Generate a new unique workspace code.

    The code is an identifier/invitation, not a password: regenerating it
    never revokes previously approved users — they keep their access.
    """
    conn = get_db()
    ws_id = workspace_id(conn)
    if not is_admin(conn, ws_id):
        conn.close()
        return jsonify({"error": "Admin access required"}), 403
    for _ in range(50):
        code = f"{secrets.token_hex(3).upper()}-{secrets.token_hex(2).upper()}"
        if not conn.execute("SELECT 1 FROM workspaces WHERE code = ?", (code,)).fetchone():
            conn.execute("UPDATE workspaces SET code = ? WHERE id = ?", (code, ws_id))
            conn.commit()
            conn.close()
            return jsonify({"ok": True, "code": code})
    conn.close()
    return jsonify({"error": "Could not generate a unique code"}), 500