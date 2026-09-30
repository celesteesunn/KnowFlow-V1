"""KnowFlow Flask backend — application entry point.

Chunk 2: auth, projects, document upload/extraction, search, AI Q&A with
source citations, and duplicate detection.
"""

import os
from datetime import timedelta

from flask import Flask, jsonify
from flask_cors import CORS

import config
from ai import backfill_chunks, backfill_semantic
from auth import bp as auth_bp
from chat import bp as chat_bp
from db import get_db, init_db
from documents import bp as documents_bp
from knowledge import bp as knowledge_bp
from members import bp as members_bp
from profile import bp as profile_bp
from projects import bp as projects_bp
from workspaces import bp as workspaces_bp

APP_VERSION = "0.5.0"


def create_app():
    """Application factory."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
    # Session cookies: HTTP-only and SameSite=Lax so cross-site requests
    # never carry the session cookie. Sessions expire naturally after
    # SESSION_LIFETIME_HOURS (login marks the session permanent).
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        hours=config.SESSION_LIFETIME_HOURS
    )
    # The frontend talks to the backend through the Vite /api proxy, so
    # cross-origin requests are only allowed from the local dev servers.
    CORS(
        app,
        supports_credentials=True,
        origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    )

    # Ensure runtime directories exist
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    os.makedirs(config.AVATAR_DIR, exist_ok=True)

    # Initialise the SQLite schema on startup
    init_db()
    # Create RAG chunks for documents extracted before chunking existed.
    backfill_chunks(get_db())
    # Dense semantic embeddings for chunks stored before hybrid search.
    backfill_semantic(get_db())

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(knowledge_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(workspaces_bp)

    @app.errorhandler(413)
    def file_too_large(_err):
        return (
            jsonify(
                {
                    "error": (
                        "File too large. The maximum allowed file size is "
                        f"{config.MAX_UPLOAD_MB} MB. Please choose a smaller file."
                    )
                }
            ),
            413,
        )

    @app.errorhandler(400)
    def bad_request(_err):
        return jsonify({"error": "Bad request"}), 400

    @app.get("/api/health")
    def health():
        """Liveness + readiness probe used by the frontend."""
        db_ok = True
        try:
            conn = get_db()
            conn.execute("SELECT 1")
            conn.close()
        except Exception:
            db_ok = False

        return jsonify(
            {
                "status": "ok" if db_ok else "degraded",
                "service": "knowflow-backend",
                "version": APP_VERSION,
                "database": "connected" if db_ok else "error",
            }
        )

    return app


app = create_app()

if __name__ == "__main__":
    # debug=True enables auto-reload during development. The reloader needs a
    # live stdin; when the server is started detached (no terminal) it exits
    # silently on stdin EOF, so it can be disabled with KNOWFLOW_USE_RELOADER=0.
    use_reloader = os.environ.get("KNOWFLOW_USE_RELOADER", "1") != "0"
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=use_reloader)