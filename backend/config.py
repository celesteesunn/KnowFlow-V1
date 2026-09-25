"""KnowFlow configuration — paths and runtime settings.

All values can be overridden with environment variables.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
UPLOAD_DIR = os.path.join(ROOT_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "knowflow.db")


def _load_dotenv(path):
    """Minimal .env loader (no external dependency).

    backend/.env holds local secrets (API keys) and is gitignored.
    Real environment variables always win over .env values.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv(os.path.join(BASE_DIR, ".env"))

# Flask session signing key. Override in production:
#   set KNOWFLOW_SECRET_KEY=...
SECRET_KEY = os.environ.get("KNOWFLOW_SECRET_KEY", "dev-secret-change-me")

# LLM API (OpenAI-compatible). Leave OPENAI_API_KEY empty to run in
# "retrieval-only" mode: answers come from the top matching passages with
# source citations, no external API call.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Upload limits
MAX_UPLOAD_MB = 20
ALLOWED_EXTENSIONS = {".pdf"}

# Duplicate detection threshold (cosine similarity, 0..1)
DUPLICATE_THRESHOLD = 0.7