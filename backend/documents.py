"""Documents blueprint — upload, list, search, ask, duplicates."""

import hashlib
import os
import time

from flask import Blueprint, jsonify, request, session
from pypdf import PdfReader
from werkzeug.utils import secure_filename

from ai import generate_answer, retrieve_pages
from auth import login_required
from config import ALLOWED_EXTENSIONS, DUPLICATE_THRESHOLD, UPLOAD_DIR
from db import get_db

bp = Blueprint("documents", __name__)


def _extract_pdf(path):
    """Return [{page_number, text}] extracted from a PDF."""
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append({"page_number": i, "text": text})
    return pages


def _project_exists(conn, project_id):
    return conn.execute(
        "SELECT 1 FROM projects WHERE id = ?", (project_id,)
    ).fetchone() is not None


@bp.post("/api/projects/<int:project_id>/documents")
@login_required
def upload_document(project_id):
    conn = get_db()
    if not _project_exists(conn, project_id):
        conn.close()
        return jsonify({"error": "Project not found"}), 404

    file = request.files.get("file")
    if not file or not file.filename:
        conn.close()
        return jsonify({"error": "No file provided"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        conn.close()
        return jsonify({"error": "Only PDF files are allowed"}), 400

    filename = secure_filename(file.filename) or "document.pdf"
    save_path = os.path.join(
        UPLOAD_DIR, f"{project_id}_{int(time.time())}_{filename}"
    )
    file.save(save_path)

    pages = _extract_pdf(save_path)
    full_text = "\n\n".join(p["text"] for p in pages)
    content_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()

    cur = conn.execute(
        """
        INSERT INTO documents
            (project_id, filename, file_path, page_count, uploaded_by, text, content_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            filename,
            save_path,
            len(pages),
            session["user_id"],
            full_text,
            content_hash,
        ),
    )
    doc_id = cur.lastrowid
    for p in pages:
        conn.execute(
            "INSERT INTO document_pages (document_id, page_number, text) VALUES (?, ?, ?)",
            (doc_id, p["page_number"], p["text"]),
        )
    conn.commit()
    conn.close()

    return (
        jsonify(
            {
                "document": {
                    "id": doc_id,
                    "filename": filename,
                    "page_count": len(pages),
                }
            }
        ),
        201,
    )


@bp.get("/api/projects/<int:project_id>/documents")
@login_required
def list_documents(project_id):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, filename, page_count, created_at
        FROM documents
        WHERE project_id = ?
        ORDER BY created_at DESC
        """,
        (project_id,),
    ).fetchall()
    conn.close()
    return jsonify({"documents": [dict(r) for r in rows]})


@bp.get("/api/projects/<int:project_id>/search")
@login_required
def search(project_id):
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})

    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, filename, page_count, text
        FROM documents
        WHERE project_id = ? AND (text LIKE ? OR filename LIKE ?)
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
    conn.close()
    return jsonify({"results": results})


@bp.post("/api/projects/<int:project_id>/ask")
@login_required
def ask(project_id):
    data = request.get_json(force=True)
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Question is required"}), 400

    conn = get_db()
    rows = conn.execute(
        """
        SELECT p.document_id, d.filename, p.page_number, p.text
        FROM document_pages p
        JOIN documents d ON d.id = p.document_id
        WHERE d.project_id = ? AND p.text != ''
        """,
        (project_id,),
    ).fetchall()
    conn.close()

    pages = [dict(r) for r in rows]
    hits = retrieve_pages(pages, question)
    if not hits:
        return jsonify(
            {
                "answer": "No relevant content found in this project's documents.",
                "sources": [],
                "mode": "none",
            }
        )

    result = generate_answer(question, hits)
    sources = [
        {
            "document": h["page"]["filename"],
            "page": h["page"]["page_number"],
            "score": round(h["score"], 3),
        }
        for h in hits
    ]
    return jsonify(
        {
            "answer": result["answer"],
            "mode": result["mode"],
            "sources": sources,
        }
    )


@bp.get("/api/projects/<int:project_id>/duplicates")
@login_required
def duplicates(project_id):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, filename, text
        FROM documents
        WHERE project_id = ? AND text != ''
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