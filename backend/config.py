"""KnowFlow configuration — paths and runtime settings.

All values can be overridden with environment variables.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(ROOT_DIR, "data")
UPLOAD_DIR = os.path.join(ROOT_DIR, "uploads")
AVATAR_DIR = os.path.join(DATA_DIR, "avatars")
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

# How long a signed-in session stays valid before it expires naturally.
# After this the browser drops the session cookie and the user must sign
# in again. Override with KNOWFLOW_SESSION_HOURS.
SESSION_LIFETIME_HOURS = int(os.environ.get("KNOWFLOW_SESSION_HOURS", "8"))

# LLM API (OpenAI-compatible). Leave OPENAI_API_KEY empty to run in
# "retrieval-only" mode: answers come from the top matching passages with
# source citations, no external API call.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

# Upload limits — maximum 500 MB per file. The backend enforces this both
# via Flask's MAX_CONTENT_LENGTH (Content-Length header) and by counting
# actual bytes while streaming the file to disk, so a client that omits or
# misreports Content-Length cannot bypass the limit.
MAX_UPLOAD_MB = 500
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}

# Hybrid search tuning (keyword vs semantic blend, 0..1 each).
# Override with KNOWFLOW_SEARCH_KEYWORD_WEIGHT / KNOWFLOW_SEARCH_SEMANTIC_WEIGHT.
SEARCH_KEYWORD_WEIGHT = float(os.environ.get("KNOWFLOW_SEARCH_KEYWORD_WEIGHT", "0.5"))
SEARCH_SEMANTIC_WEIGHT = float(os.environ.get("KNOWFLOW_SEARCH_SEMANTIC_WEIGHT", "0.5"))
# Below this combined relevance a document is not shown at all.
SEARCH_MIN_COMBINED = float(os.environ.get("KNOWFLOW_SEARCH_MIN_COMBINED", "0.02"))

# --------------------------------------------------------------------------
# RAG retrieval (assistant answers)
# --------------------------------------------------------------------------
# These tune the chat retrieval pipeline only; the Search page keeps using the
# SEARCH_* weights above so tuning the assistant does not change search results.

# How many chunks are pulled from the hybrid stage before reranking.
RAG_CANDIDATE_POOL = int(os.environ.get("KNOWFLOW_RAG_CANDIDATE_POOL", "40"))
# How many chunks are handed to the answer generator.
RAG_TOP_K = int(os.environ.get("KNOWFLOW_RAG_TOP_K", "6"))
# RRF damping constant. Higher values flatten the rank contribution.
RAG_RRF_K = int(os.environ.get("KNOWFLOW_RAG_RRF_K", "60"))
# Blend of the keyword and semantic rankings inside reciprocal rank fusion.
RAG_KEYWORD_WEIGHT = float(os.environ.get("KNOWFLOW_RAG_KEYWORD_WEIGHT", "0.5"))
RAG_SEMANTIC_WEIGHT = float(os.environ.get("KNOWFLOW_RAG_SEMANTIC_WEIGHT", "0.5"))
# Cap on chunks taken from any single document, so one long document cannot
# crowd every other document out of the context window.
RAG_MAX_PER_DOCUMENT = int(os.environ.get("KNOWFLOW_RAG_MAX_PER_DOCUMENT", "3"))
# Chunks scoring below this are treated as not relevant and dropped.
RAG_MIN_RELEVANCE = float(os.environ.get("KNOWFLOW_RAG_MIN_RELEVANCE", "0.12"))
# Below this cosine similarity a chunk is not considered semantically related,
# no matter how well it matches on keywords.
RAG_MIN_SEMANTIC = float(os.environ.get("KNOWFLOW_RAG_MIN_SEMANTIC", "0.05"))
# Characters of the preceding chunk prepended when a chunk starts mid-thought,
# so the generator never sees a passage that begins without its antecedent.
RAG_CONTEXT_LEAD_CHARS = int(os.environ.get("KNOWFLOW_RAG_CONTEXT_LEAD_CHARS", "220"))
# Conversation turns of history kept per project, and the character budget for
# the history text included in a prompt.
RAG_HISTORY_TURNS = int(os.environ.get("KNOWFLOW_RAG_HISTORY_TURNS", "6"))
RAG_HISTORY_MAX_CHARS = int(os.environ.get("KNOWFLOW_RAG_HISTORY_MAX_CHARS", "2500"))

# Profile picture limits
MAX_AVATAR_MB = 2
ALLOWED_AVATAR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Duplicate detection threshold (cosine similarity, 0..1)
DUPLICATE_THRESHOLD = 0.7