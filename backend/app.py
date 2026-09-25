"""KnowFlow Flask backend — application entry point.

Chunk 2: auth, projects, PDF upload/extraction, search, AI Q&A with
source citations, and duplicate detection.
"""

import os

from flask import Flask, jsonify
from flask_cors import CORS

import config
from auth import bp as auth_bp
from db import get_db, init_db
from documents import bp as documents_bp
from projects import bp as projects_bp

APP_VERSION = "0.2.0"


def create_app():
    """Application factory."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_MB * 1024 * 1024
    CORS(app, supports_credentials=True)

    # Ensure runtime directories exist
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)

    # Initialise the SQLite schema on startup
    init_db()

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(documents_bp)

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
    # debug=True enables auto-reload during development
    app.run(host="127.0.0.1", port=5000, debug=True)