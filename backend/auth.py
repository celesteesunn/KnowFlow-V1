"""Authentication blueprint — register, login, logout, session user.

Uses Flask session cookies (same-origin via the Vite proxy) and
werkzeug password hashing. No tokens, no external services.
"""

import functools

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

bp = Blueprint("auth", __name__)


def login_required(view):
    """Decorator: reject requests without an authenticated session."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required"}), 401
        return view(*args, **kwargs)

    return wrapped


def _public_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "is_admin": bool(row["is_admin"]),
    }


@bp.post("/api/auth/register")
def register():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()

    if len(username) < 3 or len(username) > 50:
        return jsonify({"error": "Username must be 3-50 characters"}), 400
    if not all(c.isalnum() or c in "_-." for c in username):
        return jsonify({"error": "Username may only contain letters, numbers, _ - ."}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if len(password) > 128:
        return jsonify({"error": "Password is too long (max 128 characters)"}), 400
    if len(full_name) > 100:
        return jsonify({"error": "Full name is too long (max 100 characters)"}), 400

    conn = get_db()
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        return jsonify({"error": "Username already taken"}), 409

    conn.execute(
        "INSERT INTO users (username, password_hash, full_name) VALUES (?, ?, ?)",
        (username, generate_password_hash(password), full_name),
    )
    conn.commit()
    user = conn.execute(
        "SELECT id, username, full_name, is_admin FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    conn.close()

    session["user_id"] = user["id"]
    return jsonify({"user": _public_user(user)}), 201


@bp.post("/api/auth/login")
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password"}), 401

    session["user_id"] = user["id"]
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
        "SELECT id, username, full_name, is_admin FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()
    conn.close()
    return jsonify({"user": _public_user(user) if user else None})