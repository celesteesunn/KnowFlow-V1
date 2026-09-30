"""Documents blueprint — upload, list, details, download, replace, archive,
search, ask and duplicate detection.

Document management features:
- PDF, DOCX and TXT upload with metadata (title, description, category, tags)
- File validation (extension + readable content) and a 500 MB per-file size limit
- Per-project document list (current versions only)
- Document details with version history
- Download the stored PDF
- Replace a document -> new version, previous version kept
- Archive (soft delete)
- Text extraction per page (PyPDF) for later search / RAG
"""

import hashlib
import os
import time
import zipfile
import xml.etree.ElementTree as ET

from flask import Blueprint, jsonify, request, send_file, session
from pypdf import PdfReader
from werkzeug.utils import secure_filename

from ai import ask_documents, store_chunks
from auth import active_required, workspace_id
from config import ALLOWED_EXTENSIONS, DUPLICATE_THRESHOLD, MAX_UPLOAD_MB, UPLOAD_DIR
from db import get_db, log_activity

bp = Blueprint("documents", __name__)

# DOCX paragraphs live in word/document.xml; text is inside w:t elements.
_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _extract_pdf(path):
    """Return [{page_number, text}] extracted from a PDF."""
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append({"page_number": i, "text": text})
    return pages


def _extract_docx(path):
    """Return [{page_number, text}] extracted from a DOCX (paragraphs +
    table cells, in document order). Uses only the standard library."""
    with zipfile.ZipFile(path) as zf:
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)

    parts = []
    for el in root.iter():
        if el.tag == f"{{{_DOCX_NS['w']}}}p":
            text = "".join(
                t.text or ""
                for t in el.iter(f"{{{_DOCX_NS['w']}}}t")
            ).strip()
            if text:
                parts.append(text)
    if not parts:
        return []
    return [{"page_number": 1, "text": "\n".join(parts)}]


def _extract_txt(path):
    """Return [{page_number, text}] extracted from a plain-text file."""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    text = text.strip()
    if not text:
        return []
    return [{"page_number": 1, "text": text}]


def _extract_by_ext(path, ext):
    if ext == ".pdf":
        return _extract_pdf(path)
    if ext == ".docx":
        return _extract_docx(path)
    if ext == ".txt":
        return _extract_txt(path)
    raise ValueError("Unsupported file type")


def _too_large_message():
    """User-friendly message for an over-limit upload.

    Shared by the Content-Length check, the streamed byte count and the
    413 handler in app.py so every rejection reads the same.
    """
    return (
        "File too large. The maximum allowed file size is "
        f"{MAX_UPLOAD_MB} MB. Please choose a smaller file."
    )


def _save_and_extract(file, project_id):
    """Validate and store an uploaded file, then extract its text.

    Raises ValueError with a user-friendly message on invalid input.
    Returns (filename, save_path, pages, full_text, content_hash).
    """
    if not file or not file.filename:
        raise ValueError("No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Only PDF, DOCX or TXT files are allowed")

    filename = secure_filename(file.filename) or f"document{ext}"
    save_path = os.path.join(
        UPLOAD_DIR, f"{project_id}_{int(time.time() * 1000)}_{filename}"
    )

    # Enforce the per-file size limit. Content-Length is checked first when
    # the client sent one, then the body is streamed to disk while counting
    # bytes, so a request that omits or misreports Content-Length is still
    # rejected once the real size passes the limit.
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    declared = getattr(file, "content_length", None)
    try:
        declared_bytes = int(declared) if declared is not None else None
    except (TypeError, ValueError):
        declared_bytes = None
    if declared_bytes is not None and declared_bytes > max_bytes:
        raise ValueError(_too_large_message())

    written = 0
    try:
        with open(save_path, "wb") as out:
            while True:
                chunk = file.stream.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(_too_large_message())
                out.write(chunk)
    except ValueError:
        # Oversized (or unreadable) upload: never leave a partial file behind.
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass
        raise
    except Exception:
        if os.path.exists(save_path):
            try:
                os.remove(save_path)
            except OSError:
                pass
        raise ValueError("Invalid or corrupted file")

    try:
        pages = _extract_by_ext(save_path, ext)
    except Exception:
        os.remove(save_path)
        raise ValueError("Invalid or corrupted file")

    full_text = "\n\n".join(p["text"] for p in pages)
    if not full_text.strip():
        os.remove(save_path)
        raise ValueError("No readable text found in the file")
    content_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    return filename, save_path, pages, full_text, content_hash


def _doc_summary(row):
    return {
        "id": row["id"],
        "filename": row["filename"],
        "title": row["title"],
        "description": row["description"],
        "category": row["category"],
        "tags": row["tags"] or "",
        "project_id": row["project_id"],
        "page_count": row["page_count"],
        "version": row["version"],
        "processing_status": row["processing_status"],
        "created_at": row["created_at"],
    }


def _project_owned(conn, project_id):
    """True if the signed-in user owns the project (same workspace)."""
    ws_id = workspace_id(conn)
    return conn.execute(
        "SELECT 1 FROM projects WHERE id = ? AND owner_id = ? AND workspace_id = ?",
        (project_id, session["user_id"], ws_id),
    ).fetchone() is not None


def _document_owned(conn, doc_id):
    """True if the signed-in user owns the document's project (same workspace)."""
    ws_id = workspace_id(conn)
    return conn.execute(
        """
        SELECT 1 FROM documents d
        JOIN projects p ON p.id = d.project_id
        WHERE d.id = ? AND p.owner_id = ? AND p.workspace_id = ?
        """,
        (doc_id, session["user_id"], ws_id),
    ).fetchone() is not None


def _check_duplicates(conn, project_id, new_doc_id, full_text):
    """Return [{filename, similarity}] for existing docs similar to the new one.

    Uses TF-IDF cosine similarity. A high score means the documents are
    potentially similar, not that they are factually duplicates.
    """
    if not (full_text or "").strip():
        return []
    rows = conn.execute(
        """
        SELECT id, filename, text FROM documents
        WHERE project_id = ? AND is_current = 1 AND is_archived = 0
          AND id != ? AND text != ''
        """,
        (project_id, new_doc_id),
    ).fetchall()
    if not rows:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
        matrix = vectorizer.fit_transform([full_text] + [r["text"] for r in rows])
        sims = cosine_similarity(matrix[0:1], matrix[1:])[0]
    except ValueError:
        return []

    matches = [
        {"filename": r["filename"], "similarity": round(float(s), 3)}
        for r, s in zip(rows, sims)
        if s >= DUPLICATE_THRESHOLD
    ]
    matches.sort(key=lambda x: x["similarity"], reverse=True)
    return matches


def _insert_document(conn, project_id, filename, save_path, pages, full_text,
                     content_hash, title, description, category, tags, version,
                     doc_group_id):
    # The document inherits its workspace from the project, so a document
    # can never be created in a workspace the project does not belong to.
    ws_row = conn.execute(
        "SELECT workspace_id FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    ws_id = ws_row["workspace_id"] if ws_row else None
    cur = conn.execute(
        """
        INSERT INTO documents
            (project_id, workspace_id, filename, file_path, page_count,
             uploaded_by, text, content_hash, title, description, category,
             tags, version, processing_status, is_current, is_archived,
             doc_group_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', 1, 0, ?)
        """,
        (
            project_id,
            ws_id,
            filename,
            save_path,
            len(pages),
            session["user_id"],
            full_text,
            content_hash,
            title,
            description,
            category,
            tags,
            version,
            doc_group_id,
        ),
    )
    doc_id = cur.lastrowid
    for p in pages:
        conn.execute(
            "INSERT INTO document_pages (document_id, page_number, text) VALUES (?, ?, ?)",
            (doc_id, p["page_number"], p["text"]),
        )
    # Chunk + embed the extracted text for RAG retrieval. The filename is
    # passed so the chunker can use the document's own title as context when
    # a page's text does not repeat it.
    store_chunks(conn, doc_id, pages, filename)
    return doc_id


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------

@bp.post("/api/projects/<int:project_id>/documents")
@active_required
def upload_document(project_id):
    conn = get_db()
    if not _project_owned(conn, project_id):
        conn.close()
        return jsonify({"error": "Project not found"}), 404
    conn.close()

    try:
        filename, save_path, pages, full_text, content_hash = _save_and_extract(
            request.files.get("file"), project_id
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    title = (request.form.get("title") or "").strip() or os.path.splitext(filename)[0]
    description = (request.form.get("description") or "").strip()
    category = (request.form.get("category") or "").strip()
    tags = (request.form.get("tags") or "").strip()

    conn = get_db()
    doc_id = _insert_document(
        conn, project_id, filename, save_path, pages, full_text, content_hash,
        title, description, category, tags, version=1, doc_group_id=None,
    )
    # A new document is its own version group.
    conn.execute("UPDATE documents SET doc_group_id = ? WHERE id = ?", (doc_id, doc_id))
    # Part 2 — duplicate detection: compare with existing documents.
    potentially_similar = _check_duplicates(conn, project_id, doc_id, full_text)
    log_activity(
        conn, session["user_id"], "document_upload",
        f'Uploaded "{title}"', ref_type="document", ref_id=doc_id,
    )
    conn.commit()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    return jsonify(
        {"document": _doc_summary(row), "potentially_similar": potentially_similar}
    ), 201


# --------------------------------------------------------------------------
# List (all documents across the user's projects)
# --------------------------------------------------------------------------

@bp.get("/api/documents")
@active_required
def all_documents():
    conn = get_db()
    ws_id = workspace_id(conn)
    rows = conn.execute(
        """
        SELECT d.id, d.filename, d.title, d.version, d.processing_status,
               d.created_at, d.page_count,
               p.id AS project_id, p.name AS project_name,
               u.username, u.full_name
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        JOIN users u ON u.id = d.uploaded_by
        WHERE p.owner_id = ? AND p.workspace_id = ?
          AND d.is_current = 1 AND d.is_archived = 0
        ORDER BY d.created_at DESC
        """,
        (session["user_id"], ws_id),
    ).fetchall()
    conn.close()
    return jsonify({"documents": [dict(r) for r in rows]})


# --------------------------------------------------------------------------
# List (per project)
# --------------------------------------------------------------------------

@bp.get("/api/projects/<int:project_id>/documents")
@active_required
def list_documents(project_id):
    conn = get_db()
    if not _project_owned(conn, project_id):
        conn.close()
        return jsonify({"error": "Project not found"}), 404
    rows = conn.execute(
        """
        SELECT d.id, d.filename, d.title, d.description, d.category,
               d.page_count, d.version, d.processing_status, d.created_at,
               u.username, u.full_name
        FROM documents d
        JOIN users u ON u.id = d.uploaded_by
        WHERE d.project_id = ? AND d.is_current = 1 AND d.is_archived = 0
        ORDER BY d.created_at DESC
        """,
        (project_id,),
    ).fetchall()
    conn.close()
    return jsonify({"documents": [dict(r) for r in rows]})


# --------------------------------------------------------------------------
# Details, download, archive
# --------------------------------------------------------------------------

@bp.get("/api/documents/<int:doc_id>")
@active_required
def document_detail(doc_id):
    conn = get_db()
    if not _document_owned(conn, doc_id):
        conn.close()
        return jsonify({"error": "Document not found"}), 404
    row = conn.execute(
        """
        SELECT d.*, u.username, u.full_name, p.name AS project_name
        FROM documents d
        JOIN users u ON u.id = d.uploaded_by
        JOIN projects p ON p.id = d.project_id
        WHERE d.id = ?
        """,
        (doc_id,),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Document not found"}), 404

    versions = conn.execute(
        """
        SELECT id, filename, title, version, processing_status, created_at, is_current
        FROM documents
        WHERE doc_group_id = ?
        ORDER BY version DESC
        """,
        (row["doc_group_id"],),
    ).fetchall()
    conn.close()
    return jsonify(
        {
            "document": {
                "id": row["id"],
                "filename": row["filename"],
                "title": row["title"],
                "description": row["description"],
                "category": row["category"],
                "project_id": row["project_id"],
                "project_name": row["project_name"],
                "page_count": row["page_count"],
                "version": row["version"],
                "processing_status": row["processing_status"],
                "created_at": row["created_at"],
                "uploaded_by": row["uploaded_by"],
                "username": row["username"],
                "full_name": row["full_name"],
            },
            "versions": [dict(v) for v in versions],
        }
    )


@bp.get("/api/documents/<int:doc_id>/download")
@active_required
def download_document(doc_id):
    conn = get_db()
    if not _document_owned(conn, doc_id):
        conn.close()
        return jsonify({"error": "Document not found"}), 404
    row = conn.execute(
        "SELECT filename, file_path FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Document not found"}), 404
    if not os.path.exists(row["file_path"]):
        return jsonify({"error": "File missing on disk"}), 404
    return send_file(
        row["file_path"], as_attachment=True, download_name=row["filename"]
    )


@bp.get("/api/documents/<int:doc_id>/view")
@active_required
def view_document(doc_id):
    """Serve the stored file inline so the browser can render it inside the
    application (embedded viewer). Unlike /download this is not an
    attachment, so PDFs open in the page rather than being saved."""
    conn = get_db()
    if not _document_owned(conn, doc_id):
        conn.close()
        return jsonify({"error": "Document not found"}), 404
    row = conn.execute(
        "SELECT filename, file_path FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    log_activity(
        conn, session["user_id"], "document_view",
        f'Viewed "{row["filename"]}"' if row else "Viewed a document",
        ref_type="document", ref_id=doc_id,
    )
    conn.commit()
    conn.close()
    if not row:
        return jsonify({"error": "Document not found"}), 404
    if not os.path.exists(row["file_path"]):
        return jsonify({"error": "File missing on disk"}), 404
    ext = os.path.splitext(row["filename"])[1].lower()
    mimetype = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain; charset=utf-8",
    }.get(ext, "application/octet-stream")
    return send_file(
        row["file_path"],
        as_attachment=False,
        mimetype=mimetype,
        download_name=row["filename"],
    )


@bp.get("/api/documents/<int:doc_id>/text")
@active_required
def document_text(doc_id):
    """Return the extracted text of a document (for non-PDF viewing).

    The text is the same extracted content used for search and RAG, so the
    viewer never needs to parse the original file format.
    """
    conn = get_db()
    if not _document_owned(conn, doc_id):
        conn.close()
        return jsonify({"error": "Document not found"}), 404
    row = conn.execute(
        "SELECT filename, text FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Document not found"}), 404
    return jsonify({"filename": row["filename"], "text": row["text"] or ""})


@bp.delete("/api/documents/<int:doc_id>")
@active_required
def archive_document(doc_id):
    conn = get_db()
    if not _document_owned(conn, doc_id):
        conn.close()
        return jsonify({"error": "Document not found"}), 404
    row = conn.execute(
        "SELECT id, filename FROM documents WHERE id = ? AND is_archived = 0", (doc_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Document not found"}), 404
    conn.execute("UPDATE documents SET is_archived = 1 WHERE id = ?", (doc_id,))
    log_activity(
        conn, session["user_id"], "document_archive",
        f'Archived "{row["filename"]}"', ref_type="document", ref_id=doc_id,
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@bp.delete("/api/documents/<int:doc_id>/permanent")
@active_required
def delete_document(doc_id):
    """Permanently delete a document and every version in its group.

    Removes the database rows, the extracted pages and the PDF files from
    disk. This cannot be undone.
    """
    conn = get_db()
    if not _document_owned(conn, doc_id):
        conn.close()
        return jsonify({"error": "Document not found"}), 404
    row = conn.execute(
        "SELECT * FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Document not found"}), 404

    group = row["doc_group_id"] or row["id"]
    files = conn.execute(
        "SELECT file_path FROM documents WHERE doc_group_id = ?", (group,)
    ).fetchall()

    conn.execute(
        """
        DELETE FROM document_pages
        WHERE document_id IN (SELECT id FROM documents WHERE doc_group_id = ?)
        """,
        (group,),
    )
    conn.execute(
        """
        DELETE FROM document_chunks
        WHERE document_id IN (SELECT id FROM documents WHERE doc_group_id = ?)
        """,
        (group,),
    )
    conn.execute("DELETE FROM documents WHERE doc_group_id = ?", (group,))
    log_activity(
        conn, session["user_id"], "document_delete",
        f'Deleted "{row["filename"]}"', ref_type="document", ref_id=row["id"],
    )
    conn.commit()
    conn.close()

    removed = 0
    for f in files:
        try:
            if os.path.exists(f["file_path"]):
                os.remove(f["file_path"])
                removed += 1
        except OSError:
            pass

    return jsonify({"ok": True, "deleted_versions": len(files), "files_removed": removed})


# --------------------------------------------------------------------------
# Replace (versioning)
# --------------------------------------------------------------------------

@bp.post("/api/projects/<int:project_id>/documents/<int:doc_id>/replace")
@active_required
def replace_document(project_id, doc_id):
    conn = get_db()
    if not _project_owned(conn, project_id):
        conn.close()
        return jsonify({"error": "Project not found"}), 404
    target = conn.execute(
        """
        SELECT * FROM documents
        WHERE id = ? AND project_id = ? AND is_archived = 0
        """,
        (doc_id, project_id),
    ).fetchone()
    if not target:
        conn.close()
        return jsonify({"error": "Document not found in this project"}), 404

    try:
        filename, save_path, pages, full_text, content_hash = _save_and_extract(
            request.files.get("file"), project_id
        )
    except ValueError as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 400

    group = target["doc_group_id"] or target["id"]
    new_version = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM documents WHERE doc_group_id = ?",
        (group,),
    ).fetchone()[0]

    title = (request.form.get("title") or "").strip() or target["title"]
    description = (request.form.get("description") or "").strip() or target["description"]
    category = (request.form.get("category") or "").strip() or target["category"]
    tags = (request.form.get("tags") or "").strip() or target["tags"] or ""

    # Previous versions stay in the database and on disk; only the current
    # flag moves to the new version.
    conn.execute("UPDATE documents SET is_current = 0 WHERE doc_group_id = ?", (group,))
    new_id = _insert_document(
        conn, project_id, filename, save_path, pages, full_text, content_hash,
        title, description, category, tags, version=new_version, doc_group_id=group,
    )
    log_activity(
        conn, session["user_id"], "document_update",
        f'Updated "{title}" to version {new_version}',
        ref_type="document", ref_id=new_id,
    )
    conn.commit()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify({"document": _doc_summary(row), "version": new_version}), 201


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

@bp.get("/api/projects/<int:project_id>/search")
@active_required
def search(project_id):
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})

    conn = get_db()
    if not _project_owned(conn, project_id):
        conn.close()
        return jsonify({"error": "Project not found"}), 404
    rows = conn.execute(
        """
        SELECT id, filename, page_count, text
        FROM documents
        WHERE project_id = ? AND is_current = 1 AND is_archived = 0
          AND (text LIKE ? OR filename LIKE ?)
        ORDER BY created_at DESC
        """,
        (project_id, f"%{q}%", f"%{q}%"),
    ).fetchall()

    results = []
    for r in rows:
        text = r["text"] or ""
        idx = text.lower().find(q.lower())
        if idx == -1:
            # Match came from the filename — show the start of the text.
            idx = 0
        start = max(0, idx - 120)
        snippet = " ".join(text[start : start + 300].split())
        results.append(
            {
                "id": r["id"],
                "filename": r["filename"],
                "page_count": r["page_count"],
                "snippet": snippet,
            }
        )
    log_activity(
        conn, session["user_id"], "search",
        f'Searched for "{q}"', ref_type="project", ref_id=project_id,
    )
    conn.commit()
    conn.close()
    return jsonify({"results": results})


# --------------------------------------------------------------------------
# Ask (AI Q&A over documents)
# --------------------------------------------------------------------------

@bp.post("/api/projects/<int:project_id>/ask")
@active_required
def ask(project_id):
    data = request.get_json(force=True)
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Question is required"}), 400
    if len(question) > 2000:
        return jsonify({"error": "Question is too long (max 2000 characters)"}), 400

    conn = get_db()
    if not _project_owned(conn, project_id):
        conn.close()
        return jsonify({"error": "Project not found"}), 404

    # Same pipeline as /api/chat, so a question asked from the project page
    # and the same question asked in the assistant panel retrieve identically.
    result = ask_documents(
        conn, session["user_id"], workspace_id(conn), project_id, question
    )
    log_activity(
        conn, session["user_id"], "ai_question",
        f'Asked the AI: "{question}"', ref_type="project", ref_id=project_id,
    )
    conn.commit()
    conn.close()

    # Document and page only: similarity scores and raw chunk text are
    # retrieval internals and are not sent to the client.
    return jsonify(
        {
            "answer": result["answer"],
            "mode": result["mode"],
            "sources": result["sources"],
            "intent": result["intent"],
        }
    )


# --------------------------------------------------------------------------
# Duplicate detection
# --------------------------------------------------------------------------

@bp.get("/api/projects/<int:project_id>/duplicates")
@active_required
def duplicates(project_id):
    conn = get_db()
    if not _project_owned(conn, project_id):
        conn.close()
        return jsonify({"error": "Project not found"}), 404
    rows = conn.execute(
        """
        SELECT id, filename, text
        FROM documents
        WHERE project_id = ? AND is_current = 1 AND is_archived = 0 AND text != ''
        """,
        (project_id,),
    ).fetchall()
    conn.close()

    docs = [dict(r) for r in rows]
    if len(docs) < 2:
        return jsonify({"duplicates": []})

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
        matrix = vectorizer.fit_transform([d["text"] for d in docs])
        sims = cosine_similarity(matrix)
    except ValueError:
        return jsonify({"duplicates": []})

    pairs = []
    for i in range(len(docs)):
        for j in range(i + 1, len(docs)):
            score = float(sims[i][j])
            if score >= DUPLICATE_THRESHOLD:
                pairs.append(
                    {
                        "document_a": docs[i]["filename"],
                        "document_b": docs[j]["filename"],
                        "similarity": round(score, 3),
                    }
                )
    pairs.sort(key=lambda x: x["similarity"], reverse=True)
    return jsonify({"duplicates": pairs})