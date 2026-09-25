"""SQLite database helpers for KnowFlow.

Schema covers users, projects, documents and per-page extracted text.
"""

import os
import sqlite3

from config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
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
    embedding   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    question   TEXT NOT NULL,
    user_id    INTEGER REFERENCES users(id),
    project_id INTEGER REFERENCES projects(id),
    asked_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Applied after the base schema for databases created in earlier phases.
MIGRATIONS = [
    "ALTER TABLE documents ADD COLUMN text TEXT",
    "ALTER TABLE documents ADD COLUMN content_hash TEXT",
    "ALTER TABLE documents ADD COLUMN title TEXT",
    "ALTER TABLE documents ADD COLUMN description TEXT",
    "ALTER TABLE documents ADD COLUMN category TEXT",
    "ALTER TABLE documents ADD COLUMN version INTEGER DEFAULT 1",
    "ALTER TABLE documents ADD COLUMN processing_status TEXT DEFAULT 'completed'",
    "ALTER TABLE documents ADD COLUMN is_current INTEGER DEFAULT 1",
    "ALTER TABLE documents ADD COLUMN is_archived INTEGER DEFAULT 0",
    "ALTER TABLE documents ADD COLUMN doc_group_id INTEGER",
    "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
]

# Data fixes for rows created before the new columns existed.
BACKFILL = [
    "UPDATE documents SET title = filename WHERE title IS NULL OR title = ''",
    "UPDATE documents SET doc_group_id = id WHERE doc_group_id IS NULL",
    "UPDATE documents SET version = 1 WHERE version IS NULL",
    "UPDATE documents SET processing_status = 'completed' WHERE processing_status IS NULL",
    # The first registered account is the admin (sees knowledge gaps).
    "UPDATE users SET is_admin = 1 WHERE id = 1",
]


def init_db() -> None:
    """Create the data directory, tables, missing columns and backfill data."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        for stmt in MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
        for stmt in BACKFILL:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    """Open a connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn