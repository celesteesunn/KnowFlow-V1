"""SQLite database helpers for KnowFlow.

Schema covers users, projects, documents, per-page extracted text,
organisation workspaces, departments, roles and in-app notifications.
"""

import json
import os
import sqlite3

from config import DATA_DIR, DB_PATH

# Default departments provisioned for every new workspace.
DEFAULT_DEPARTMENTS = [
    "Engineering",
    "Human Resources",
    "Finance",
    "Marketing",
    "Sales",
    "Operations",
    "IT",
    "Administration",
]

# Default roles provisioned for every new workspace. Permissions are
# explicitly configured per role (never inferred from the role name);
# the Workspace Owner / Admin flags on the users table are the actual
# backend gate for admin endpoints.
DEFAULT_ROLES = {
    "Workspace Owner": {
        "manage_workspace": True,
        "manage_members": True,
        "manage_roles": True,
        "manage_departments": True,
        "view_insights": True,
        "manage_documents": True,
        "manage_projects": True,
    },
    "Admin": {
        "manage_workspace": True,
        "manage_members": True,
        "manage_roles": True,
        "manage_departments": True,
        "view_insights": True,
        "manage_documents": True,
        "manage_projects": True,
    },
    "HR Admin": {
        "manage_members": True,
        "view_insights": True,
    },
    "Manager": {
        "manage_documents": True,
        "manage_projects": True,
    },
    "Department Head": {
        "manage_documents": True,
        "manage_projects": True,
    },
    "Team Lead": {
        "manage_documents": True,
        "manage_projects": True,
    },
    "Employee": {
        "manage_documents": True,
        "manage_projects": True,
    },
    "Intern": {
        "manage_documents": True,
        "manage_projects": True,
    },
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    email         TEXT,
    email_verified INTEGER NOT NULL DEFAULT 0,
    verification_token TEXT,
    verification_token_expires TEXT,
    terms_accepted INTEGER NOT NULL DEFAULT 0,
    terms_accepted_at TEXT,
    security_agreed INTEGER NOT NULL DEFAULT 0,
    security_agreed_at TEXT,
    status        TEXT NOT NULL DEFAULT 'email_unverified',
    approved_by   INTEGER REFERENCES users(id),
    approved_at   TEXT,
    rejected_reason TEXT,
    suspended_reason TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    owner_id    INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id   INTEGER REFERENCES projects(id),
    filename     TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    page_count   INTEGER NOT NULL DEFAULT 0,
    uploaded_by  INTEGER REFERENCES users(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS document_pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    text        TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    page_number INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    text        TEXT NOT NULL,
    embedding   TEXT NOT NULL DEFAULT '',
    semantic_embedding TEXT NOT NULL DEFAULT '',
    -- Structure preserved from the document so a retrieved chunk carries its
    -- own context: the heading path it sits under, its section heading and
    -- whether it is prose, a list item or a table row.
    section     TEXT NOT NULL DEFAULT '',
    heading     TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT 'prose',
    -- Which chunker produced this row. 0 = the original structure-free
    -- splitter. This is how the backfill knows a document needs re-chunking:
    -- it cannot infer it from section, because a document with no headings
    -- legitimately stores an empty section forever.
    chunk_version INTEGER NOT NULL DEFAULT 0
);

-- Bounded conversation context for follow-up questions ("who proposed it?").
-- Rows are per-project so history can never cross a permission boundary.
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL REFERENCES projects(id),
    user_id     INTEGER NOT NULL REFERENCES users(id),
    workspace_id INTEGER,
    role        TEXT NOT NULL,          -- 'user' | 'assistant'
    content     TEXT NOT NULL DEFAULT '',
    -- Documents the answer was grounded in, so a follow-up can be resolved
    -- against the topic that was just discussed.
    sources     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT NOT NULL,
    user_id    INTEGER REFERENCES users(id),
    project_id INTEGER REFERENCES projects(id),
    asked_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS activity_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    activity_type TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    ref_type      TEXT,
    ref_id        INTEGER,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workspaces (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT NOT NULL,
    description           TEXT,
    code                  TEXT UNIQUE NOT NULL,
    org_name              TEXT,
    org_email             TEXT,
    org_website           TEXT,
    org_logo              TEXT,
    timezone              TEXT NOT NULL DEFAULT 'UTC',
    language              TEXT NOT NULL DEFAULT 'en',
    require_admin_approval INTEGER NOT NULL DEFAULT 1,
    invite_code_required  INTEGER NOT NULL DEFAULT 1,
    email_domain          TEXT,
    created_by            INTEGER REFERENCES users(id),
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS departments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (workspace_id, name)
);

CREATE TABLE IF NOT EXISTS roles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
    name         TEXT NOT NULL,
    permissions  TEXT NOT NULL DEFAULT '{}',
    is_system    INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (workspace_id, name)
);

CREATE TABLE IF NOT EXISTS notifications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    workspace_id INTEGER REFERENCES workspaces(id),
    message      TEXT NOT NULL,
    is_read      INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at);
"""

# Applied after the base schema for databases created in earlier phases.
MIGRATIONS = [
    "ALTER TABLE documents ADD COLUMN text TEXT",
    "ALTER TABLE documents ADD COLUMN content_hash TEXT",
    # Chunking pipeline version, so a document chunked by an older splitter is
    # re-chunked exactly once rather than on every startup.
    "ALTER TABLE document_chunks ADD COLUMN chunk_version INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE documents ADD COLUMN title TEXT",
    "ALTER TABLE documents ADD COLUMN description TEXT",
    "ALTER TABLE documents ADD COLUMN category TEXT",
    "ALTER TABLE documents ADD COLUMN version INTEGER DEFAULT 1",
    "ALTER TABLE documents ADD COLUMN processing_status TEXT DEFAULT 'completed'",
    "ALTER TABLE documents ADD COLUMN is_current INTEGER DEFAULT 1",
    "ALTER TABLE documents ADD COLUMN is_archived INTEGER DEFAULT 0",
    "ALTER TABLE documents ADD COLUMN doc_group_id INTEGER",
    "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
    # Chunk 1 — authentication + email verification columns.
    # NOTE: email is added WITHOUT UNIQUE (SQLite forbids UNIQUE in
    # ALTER TABLE ADD COLUMN); a partial unique index is created in init_db.
    "ALTER TABLE users ADD COLUMN email TEXT",
    "ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN verification_token TEXT",
    "ALTER TABLE users ADD COLUMN verification_token_expires TEXT",
    "ALTER TABLE users ADD COLUMN terms_accepted INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN terms_accepted_at TEXT",
    "ALTER TABLE users ADD COLUMN security_agreed INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN security_agreed_at TEXT",
    "ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'email_unverified'",
    "ALTER TABLE users ADD COLUMN approved_by INTEGER",
    "ALTER TABLE users ADD COLUMN approved_at TEXT",
    "ALTER TABLE users ADD COLUMN rejected_reason TEXT",
    "ALTER TABLE users ADD COLUMN suspended_reason TEXT",
    # Profile picture (stored filename inside data/avatars).
    "ALTER TABLE users ADD COLUMN avatar TEXT",
    # Hybrid search — dense LSA embedding per chunk (keyword search stays
    # column-free; the sparse RAG embedding lives in document_chunks.embedding).
    "ALTER TABLE document_chunks ADD COLUMN semantic_embedding TEXT DEFAULT ''",
    # Structure-aware chunking — heading context stored with each chunk so the
    # retriever can tell "3. Scientific Management" from a mid-paragraph
    # fragment, and the answer generator can cite a section.
    "ALTER TABLE document_chunks ADD COLUMN section TEXT DEFAULT ''",
    "ALTER TABLE document_chunks ADD COLUMN heading TEXT DEFAULT ''",
    "ALTER TABLE document_chunks ADD COLUMN kind TEXT DEFAULT 'prose'",
    # Profile enrichment — enterprise employee profile fields.
    "ALTER TABLE users ADD COLUMN position TEXT",
    "ALTER TABLE users ADD COLUMN department TEXT",
    "ALTER TABLE users ADD COLUMN employee_id TEXT",
    "ALTER TABLE users ADD COLUMN linkedin_url TEXT",
    "ALTER TABLE users ADD COLUMN github_url TEXT",
    "ALTER TABLE users ADD COLUMN last_active_at TEXT",
    # Members directory — organisational role and profile visibility.
    # org_role: explicit leadership designation (leadership, department_head,
    # team_lead, project_lead) or NULL for regular members. Never inferred
    # from personal data.
    "ALTER TABLE users ADD COLUMN org_role TEXT",
    # profile_visibility: 'everyone' (default) | 'members' | 'private'.
    # 'private' hides the member from the directory for non-admins.
    "ALTER TABLE users ADD COLUMN profile_visibility TEXT DEFAULT 'everyone'",
    # Social link visibility: 0 hides the URL from other members (admins and
    # the member themselves always see their own links).
    "ALTER TABLE users ADD COLUMN linkedin_visible INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN github_visible INTEGER DEFAULT 1",
    # Workspace / multi-tenant columns. workspace_id is NULL while an
    # account is still in onboarding (registered, no workspace yet).
    "ALTER TABLE users ADD COLUMN workspace_id INTEGER",
    "ALTER TABLE users ADD COLUMN phone TEXT",
    "ALTER TABLE users ADD COLUMN role_id INTEGER",
    "ALTER TABLE users ADD COLUMN access_requested_at TEXT",
    "ALTER TABLE projects ADD COLUMN workspace_id INTEGER",
    "ALTER TABLE documents ADD COLUMN workspace_id INTEGER",
    "ALTER TABLE knowledge_gaps ADD COLUMN workspace_id INTEGER",
    # Search — comma-separated tags/keywords on a document (searchable metadata).
    "ALTER TABLE documents ADD COLUMN tags TEXT",
]

# Data fixes for rows created before the new columns existed.
BACKFILL = [
    "UPDATE documents SET title = filename WHERE title IS NULL OR title = ''",
    "UPDATE documents SET doc_group_id = id WHERE doc_group_id IS NULL",
    "UPDATE documents SET version = 1 WHERE version IS NULL",
    "UPDATE documents SET processing_status = 'completed' WHERE processing_status IS NULL",
]


def _migrate_auth_flow(conn) -> None:
    """One-time backfill: activate users created before the auth flow.

    Gated by PRAGMA user_version so it never re-runs: after this migration,
    new registrations must go through email verification + admin approval.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= 1:
        return
    conn.execute(
        """
        UPDATE users
        SET status = 'active', email_verified = 1,
            terms_accepted = 1, security_agreed = 1
        WHERE status = 'email_unverified'
        """
    )
    conn.execute("PRAGMA user_version = 1")


def _ensure_admin(conn) -> None:
    """Guarantee at least one active admin exists (no adminless deadlock).

    Only accounts that already belong to a workspace are considered: a
    freshly registered account (status 'onboarding', workspace_id NULL)
    must complete the workspace flow first, so it is never force-activated
    here. This is a safety net for migrated databases or edge cases where
    no active admin remains.
    """
    row = conn.execute(
        "SELECT id FROM users WHERE is_admin = 1 AND status = 'active' "
        "AND workspace_id IS NOT NULL ORDER BY id LIMIT 1"
    ).fetchone()
    if row:
        return
    row = conn.execute(
        "SELECT id FROM users WHERE workspace_id IS NOT NULL ORDER BY id LIMIT 1"
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET is_admin = 1, status = 'active', email_verified = 1, "
            "terms_accepted = 1, security_agreed = 1 WHERE id = ?",
            (row["id"],),
        )


def _backfill_workspace(conn) -> None:
    """Assign legacy single-tenant data to a default workspace.

    Databases created before workspaces existed have users, projects,
    documents and knowledge gaps with workspace_id NULL. This creates one
    default workspace (if none exists) and assigns every legacy row to it,
    so the multi-tenant scoping never drops existing data. Idempotent: rows
    that already have a workspace are left untouched.
    """
    legacy_users = conn.execute(
        "SELECT COUNT(*) FROM users WHERE workspace_id IS NULL"
    ).fetchone()[0]
    if legacy_users == 0:
        return

    ws = conn.execute("SELECT id FROM workspaces ORDER BY id LIMIT 1").fetchone()
    if not ws:
        first = conn.execute(
            "SELECT id FROM users WHERE workspace_id IS NULL ORDER BY id LIMIT 1"
        ).fetchone()
        cur = conn.execute(
            """
            INSERT INTO workspaces (name, description, code, org_name, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "KnowFlow Workspace",
                "Default workspace for existing KnowFlow data.",
                "KNOWFLOW-1",
                "KnowFlow",
                first["id"],
            ),
        )
        ws_id = cur.lastrowid
    else:
        ws_id = ws["id"]

    conn.execute(
        "UPDATE users SET workspace_id = ? WHERE workspace_id IS NULL", (ws_id,)
    )
    conn.execute(
        "UPDATE projects SET workspace_id = ? WHERE workspace_id IS NULL", (ws_id,)
    )
    conn.execute(
        "UPDATE documents SET workspace_id = ? WHERE workspace_id IS NULL", (ws_id,)
    )
    conn.execute(
        "UPDATE knowledge_gaps SET workspace_id = ? WHERE workspace_id IS NULL",
        (ws_id,),
    )
    for name in DEFAULT_DEPARTMENTS:
        conn.execute(
            "INSERT OR IGNORE INTO departments (workspace_id, name) VALUES (?, ?)",
            (ws_id, name),
        )
    for name, perms in DEFAULT_ROLES.items():
        conn.execute(
            "INSERT OR IGNORE INTO roles (workspace_id, name, permissions, is_system) "
            "VALUES (?, ?, ?, 1)",
            (ws_id, name, json.dumps(perms)),
        )


def init_db() -> None:
    """Create the data directory, tables, missing columns and backfill data."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        for stmt in MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        # Email uniqueness: partial index so multiple NULL emails are allowed
        # (accounts created before the auth flow have no email address).
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email "
            "ON users(email) WHERE email IS NOT NULL"
        )
        # Workspace indexes are created AFTER migrations add the columns.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_workspace ON users(workspace_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_workspace ON projects(workspace_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_workspace ON documents(workspace_id)"
        )
        # Search: permission scoping + current-version filtering are the hot
        # paths for every search query, so index them up front.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_owner_ws "
            "ON projects(owner_id, workspace_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_current "
            "ON documents(is_current, is_archived)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_project_current "
            "ON documents(project_id, is_current, is_archived)"
        )
        # RAG retrieval walks chunks of current documents in a project; the
        # document_id leading column keeps that scan off a full table read.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_document "
            "ON document_chunks(document_id)"
        )
        # Conversation context: the newest turns for one project/user.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_project_recent "
            "ON chat_messages(project_id, user_id, created_at)"
        )
        for stmt in BACKFILL:
            conn.execute(stmt)
        _migrate_auth_flow(conn)
        _backfill_workspace(conn)
        _ensure_admin(conn)
        conn.commit()
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    """Open a connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def log_activity(conn, user_id, activity_type, description="", ref_type=None,
                 ref_id=None) -> None:
    """Record a user activity event and refresh the user's last-active time.

    Callers pass their already-open connection; the caller owns the commit.
    Activity types (kept stable for the profile timeline):
        sign_in, document_upload, document_update, document_view,
        document_archive, document_delete, project_create, search,
        ai_question, knowledge_access
    """
    conn.execute(
        """
        INSERT INTO activity_log (user_id, activity_type, description,
                                  ref_type, ref_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, activity_type, description, ref_type, ref_id),
    )
    conn.execute(
        "UPDATE users SET last_active_at = datetime('now') WHERE id = ?",
        (user_id,),
    )