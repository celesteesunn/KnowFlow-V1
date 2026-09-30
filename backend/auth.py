"""Authentication blueprint — register, agreements, login, logout, session
user, and the active_required gate.

Account lifecycle:

    register --> onboarding --(creates workspace)--> active (Workspace Owner)
    register --> onboarding --(requests access)--> pending_approval
    pending_approval --(admin approves)--> active
    active --(admin)--> rejected | suspended
    pending_approval --(admin)--> rejected

Every new account starts in 'onboarding': the account exists and may hold a
session, but has no workspace yet. The user either creates an organisation
workspace (becoming the Workspace Owner / Admin, active immediately) or
requests access to an existing workspace (pending_approval until an admin
approves). Restrictions are enforced in the backend: rejected/suspended
accounts get 403 and no session; onboarding/pending accounts may hold a
session but every app endpoint is gated by active_required.
"""

import functools
import os
import re

from flask import Blueprint, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

import config
from db import get_db, log_activity

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def login_required(view):
    """Decorator: reject requests without an authenticated session."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        return view(*args, **kwargs)

    return wrapped


def workspace_id(conn):
    """Workspace id of the signed-in user, or None (still onboarding)."""
    row = conn.execute(
        "SELECT workspace_id FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    return row["workspace_id"] if row else None


def is_admin(conn, target_workspace_id=None):
    """True if the signed-in user is an admin of the given workspace.

    Pass target_workspace_id to also require the admin to belong to that
    workspace (cross-workspace admin actions are never allowed).
    """
    row = conn.execute(
        "SELECT is_admin, workspace_id FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    if not row or not row["is_admin"]:
        return False
    if target_workspace_id is not None and row["workspace_id"] != target_workspace_id:
        return False
    return True


def _status_block(user):
    """Return (code, message) if the account blocks app access, else (None, None).

    Active users must also have accepted the terms and the security
    agreement; the checks run in the order the user must complete them.
    """
    status = user["status"]
    if status == "rejected":
        return "rejected", "Your account was rejected. Contact an administrator."
    if status == "suspended":
        return "suspended", "Your account is suspended. Contact an administrator."
    if status == "onboarding":
        return "onboarding", "Complete your workspace setup to continue."
    if status == "pending_approval":
        if not user["terms_accepted"]:
            return "terms_required", "Accept the Terms & Conditions to continue."
        if not user["security_agreed"]:
            return (
                "security_required",
                "Accept the Security & Confidentiality agreement to continue.",
            )
        return "pending_approval", "Your account is awaiting organisation approval."
    # active
    if not user["terms_accepted"]:
        return "terms_required", "Accept the Terms & Conditions to continue."
    if not user["security_agreed"]:
        return (
            "security_required",
            "Accept the Security & Confidentiality agreement to continue.",
        )
    return None, None


def active_required(view):
    """Decorator: authenticated AND account fully active (not blocked)."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
        conn.close()
        if not user:
            session.clear()
            return jsonify({"error": "Authentication required"}), 401
        code, message = _status_block(user)
        if code:
            return jsonify({"error": message, "code": code}), 403
        return view(*args, **kwargs)

    return wrapped


def _public_user(row):
    data = {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "email": row["email"],
        "phone": row["phone"],
        "is_admin": bool(row["is_admin"]),
        "status": row["status"],
        "terms_accepted": bool(row["terms_accepted"]),
        "security_agreed": bool(row["security_agreed"]),
        "created_at": row["created_at"],
        "avatar": row["avatar"],
        "position": row["position"],
        "department": row["department"],
        "employee_id": row["employee_id"],
        "linkedin_url": row["linkedin_url"],
        "github_url": row["github_url"],
        "last_active_at": row["last_active_at"],
        "org_role": row["org_role"],
        "profile_visibility": row["profile_visibility"] or "everyone",
        "linkedin_visible": bool(row["linkedin_visible"]),
        "github_visible": bool(row["github_visible"]),
        "workspace_id": row["workspace_id"],
        "role_id": row["role_id"],
        "access_requested_at": row["access_requested_at"],
    }
    # Workspace name + unread notification count (cheap lookups; this
    # function is only called on auth/profile events, not per request).
    if row["workspace_id"]:
        conn = get_db()
        try:
            ws = conn.execute(
                "SELECT name FROM workspaces WHERE id = ?", (row["workspace_id"],)
            ).fetchone()
            unread = conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
                (row["id"],),
            ).fetchone()[0]
        finally:
            conn.close()
        data["workspace_name"] = ws["name"] if ws else None
        data["unread_notifications"] = unread
    else:
        data["workspace_name"] = None
        data["unread_notifications"] = 0
    return data


def _valid_email(email):
    return bool(email) and len(email) <= 254 and EMAIL_RE.match(email) is not None


@bp.post("/api/auth/register")
def register():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password")
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()

    if len(username) < 3 or len(username) > 50:
        return jsonify({"error": "Username must be 3-50 characters"}), 400
    if not all(c.isalnum() or c in "_-." for c in username):
        return jsonify({"error": "Username may only contain letters, numbers, _ - ."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if len(password) > 128:
        return jsonify({"error": "Password is too long (max 128 characters)"}), 400
    if confirm_password is not None and password != confirm_password:
        return jsonify({"error": "Passwords do not match"}), 400
    if not full_name:
        return jsonify({"error": "Full name is required"}), 400
    if len(full_name) > 100:
        return jsonify({"error": "Full name is too long (max 100 characters)"}), 400
    if not _valid_email(email):
        return jsonify({"error": "A valid email address is required"}), 400
    if len(phone) > 30:
        return jsonify({"error": "Phone number is too long (max 30 characters)"}), 400

    conn = get_db()
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        return jsonify({"error": "Username already taken"}), 409
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        conn.close()
        return jsonify({"error": "Email already registered"}), 409

    # Every new account starts in onboarding: it exists and may hold a
    # session, but has no workspace yet. The user either creates an
    # organisation workspace (becoming the Workspace Owner, active
    # immediately) or requests access to an existing workspace.
    cur = conn.execute(
        """
        INSERT INTO users (username, password_hash, full_name, email, phone, status)
        VALUES (?, ?, ?, ?, ?, 'onboarding')
        """,
        (
            username,
            generate_password_hash(password),
            full_name,
            email,
            phone or None,
        ),
    )
    conn.commit()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    conn.close()

    session["user_id"] = user["id"]
    return jsonify({"user": _public_user(user)}), 201


@bp.post("/api/auth/accept-terms")
@login_required
def accept_terms():
    conn = get_db()
    conn.execute(
        "UPDATE users SET terms_accepted = 1, terms_accepted_at = datetime('now') "
        "WHERE id = ?",
        (session["user_id"],),
    )
    conn.commit()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()
    return jsonify({"user": _public_user(user)})


@bp.post("/api/auth/accept-security")
@login_required
def accept_security():
    conn = get_db()
    conn.execute(
        "UPDATE users SET security_agreed = 1, security_agreed_at = datetime('now') "
        "WHERE id = ?",
        (session["user_id"],),
    )
    conn.commit()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()
    return jsonify({"user": _public_user(user)})


@bp.post("/api/auth/profile")
@login_required
def update_profile():
    data = request.get_json(force=True)
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    position = (data.get("position") or "").strip()
    department = (data.get("department") or "").strip()
    linkedin_url = (data.get("linkedin_url") or "").strip()
    github_url = (data.get("github_url") or "").strip()
    profile_visibility = (data.get("profile_visibility") or "everyone").strip()
    linkedin_visible = data.get("linkedin_visible", True)
    github_visible = data.get("github_visible", True)

    if len(full_name) > 100:
        return jsonify({"error": "Full name is too long (max 100 characters)"}), 400
    if email and not _valid_email(email):
        return jsonify({"error": "A valid email address is required"}), 400
    if len(position) > 100:
        return jsonify({"error": "Position is too long (max 100 characters)"}), 400
    if len(department) > 100:
        return jsonify({"error": "Department is too long (max 100 characters)"}), 400
    if profile_visibility not in ("everyone", "members", "private"):
        return jsonify({"error": "Invalid profile visibility setting"}), 400
    for label, url in (("LinkedIn", linkedin_url), ("GitHub", github_url)):
        if len(url) > 500:
            return jsonify({"error": f"{label} URL is too long (max 500 characters)"}), 400
        if url and not (url.startswith("http://") or url.startswith("https://")):
            return jsonify(
                {"error": f"{label} URL must start with http:// or https://"}
            ), 400

    conn = get_db()
    if email:
        dup = conn.execute(
            "SELECT 1 FROM users WHERE email = ? AND id != ?",
            (email, session["user_id"]),
        ).fetchone()
        if dup:
            conn.close()
            return jsonify({"error": "Email already registered"}), 409
    conn.execute(
        """
        UPDATE users
        SET full_name = ?, email = COALESCE(?, email),
            position = ?, department = ?,
            linkedin_url = ?, github_url = ?,
            profile_visibility = ?, linkedin_visible = ?, github_visible = ?
        WHERE id = ?
        """,
        (
            full_name,
            email or None,
            position or None,
            department or None,
            linkedin_url or None,
            github_url or None,
            profile_visibility,
            1 if linkedin_visible else 0,
            1 if github_visible else 0,
            session["user_id"],
        ),
    )
    conn.commit()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()
    return jsonify({"user": _public_user(user)})


@bp.post("/api/auth/password")
@login_required
def change_password():
    """Change the signed-in user's password (verifies the current one)."""
    data = request.get_json(force=True)
    current = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    if len(new_password) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400
    if len(new_password) > 128:
        return jsonify({"error": "New password is too long (max 128 characters)"}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    if not user or not check_password_hash(user["password_hash"], current):
        conn.close()
        return jsonify({"error": "Current password is incorrect"}), 400
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), session["user_id"]),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.post("/api/auth/avatar")
@login_required
def upload_avatar():
    """Upload / replace the signed-in user's profile picture.

    The image is stored in data/avatars as u<user_id>.<ext> and the filename
    is saved on the users row. Replacing a photo removes the previous file.
    """
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No file provided"}), 400
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in config.ALLOWED_AVATAR_EXTENSIONS:
        return (
            jsonify({"error": "Only PNG, JPG, GIF or WebP images are allowed"}),
            400,
        )
    data = file.read()
    if not data:
        return jsonify({"error": "Empty file"}), 400
    if len(data) > config.MAX_AVATAR_MB * 1024 * 1024:
        return (
            jsonify(
                {
                    "error": (
                        f"Image too large. Maximum size is "
                        f"{config.MAX_AVATAR_MB} MB."
                    )
                }
            ),
            413,
        )

    os.makedirs(config.AVATAR_DIR, exist_ok=True)
    conn = get_db()
    old = conn.execute(
        "SELECT avatar FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    filename = f"u{session['user_id']}{ext}"
    with open(os.path.join(config.AVATAR_DIR, filename), "wb") as f:
        f.write(data)
    if old and old["avatar"] and old["avatar"] != filename:
        old_path = os.path.join(config.AVATAR_DIR, old["avatar"])
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    conn.execute(
        "UPDATE users SET avatar = ? WHERE id = ?",
        (filename, session["user_id"]),
    )
    conn.commit()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()
    return jsonify({"user": _public_user(user)})


@bp.delete("/api/auth/avatar")
@login_required
def remove_avatar():
    """Remove the signed-in user's profile picture (falls back to initials)."""
    conn = get_db()
    row = conn.execute(
        "SELECT avatar FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    if row and row["avatar"]:
        old_path = os.path.join(config.AVATAR_DIR, row["avatar"])
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    conn.execute(
        "UPDATE users SET avatar = NULL WHERE id = ?", (session["user_id"],)
    )
    conn.commit()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()
    return jsonify({"user": _public_user(user)})


@bp.get("/api/avatars/<path:filename>")
def get_avatar(filename):
    """Serve a stored profile picture (public image, no auth needed)."""
    return send_from_directory(config.AVATAR_DIR, filename)


@bp.post("/api/auth/login")
def login():
    data = request.get_json(force=True)
    identifier = (data.get("username") or "").strip()
    password = data.get("password") or ""

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? OR email = ?",
        (identifier, identifier.lower()),
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    if user["status"] in ("rejected", "suspended"):
        return (
            jsonify(
                {
                    "error": "Your account is not active. Contact an administrator.",
                    "code": user["status"],
                }
            ),
            403,
        )

    session["user_id"] = user["id"]
    # Permanent session: the cookie carries an expiry so the session ends
    # naturally after SESSION_LIFETIME_HOURS instead of lasting forever.
    session.permanent = True
    # Record the sign-in and refresh last-active time.
    conn = get_db()
    log_activity(conn, user["id"], "sign_in", "Signed in to KnowFlow")
    conn.commit()
    conn.close()
    return jsonify({"user": _public_user(user)})


@bp.post("/api/auth/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/api/auth/me")
def me():
    if "user_id" not in session:
        return jsonify({"user": None})
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()
    return jsonify({"user": _public_user(user) if user else None})