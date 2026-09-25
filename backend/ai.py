"""RAG pipeline: chunking, embeddings, similarity search, LLM generation.

Flow (per the core AI feature spec):

    Uploaded PDF -> extracted text -> sentence-aware chunks
    -> sparse embeddings (HashingVectorizer, a simple local approach,
       no vector database) stored in SQLite
    -> question embedding -> cosine similarity -> top-k chunks
    -> LLM answer generation -> answer + sources

Retrieval is scoped to a project's current, non-archived documents, so the
permission boundary is enforced before any context reaches the LLM.

Without OPENAI_API_KEY the system runs in "retrieval-only" mode and returns
the top chunks themselves, so the feature is fully demonstrable offline.
"""

import json

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

EMBED_DIM = 2**16      # HashingVectorizer feature count (fixed, no fit)
CHUNK_MAX_CHARS = 600  # target chunk size
CHUNK_OVERLAP = 100    # overlap between consecutive chunks
LOW_SCORE = 0.05       # below this, flag excerpts as possibly irrelevant


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

def chunk_text(text, max_chars=CHUNK_MAX_CHARS, overlap=CHUNK_OVERLAP):
    """Split text into overlapping, sentence-aware chunks."""
    text = (text or "").strip()
    if not text:
        return []

    import re

    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", text)
        if s.strip()
    ]
    chunks, current = [], ""
    for s in sentences:
        if current and len(current) + len(s) + 1 > max_chars:
            chunks.append(current)
            tail = current[-overlap:] if len(current) > overlap else ""
            current = (tail + " " + s).strip()
        else:
            current = (current + " " + s).strip()
    if current:
        chunks.append(current)
    return chunks


# --------------------------------------------------------------------------
# Embeddings (simple local approach: hashed bag-of-words vectors)
# --------------------------------------------------------------------------

def _vectorizer():
    from sklearn.feature_extraction.text import HashingVectorizer

    return HashingVectorizer(stop_words="english", n_features=EMBED_DIM, norm="l2")


def embed_texts(texts):
    """Return a scipy sparse matrix of embeddings for the given texts."""
    return _vectorizer().transform(texts)


def vector_to_json(vec):
    """Serialize a sparse vector as {"indices": [...], "values": [...]}."""
    coo = vec.tocoo()
    return json.dumps({"indices": coo.col.tolist(), "values": coo.data.tolist()})


def json_to_vector(data, dim=EMBED_DIM):
    """Rebuild a sparse vector from the JSON serialization."""
    from scipy.sparse import csr_matrix

    d = json.loads(data)
    return csr_matrix(
        (d["values"], ([0] * len(d["indices"]), d["indices"])),
        shape=(1, dim),
    )


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

def store_chunks(conn, document_id, pages):
    """Chunk + embed every page and store the rows in document_chunks."""
    for p in pages:
        chunks = chunk_text(p["text"])
        if not chunks:
            continue
        vectors = embed_texts(chunks)
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            conn.execute(
                """
                INSERT INTO document_chunks
                    (document_id, page_number, chunk_index, text, embedding)
                VALUES (?, ?, ?, ?, ?)
                """,
                (document_id, p["page_number"], i, chunk, vector_to_json(vec)),
            )


def backfill_chunks(conn):
    """Create chunks for documents extracted before chunking existed."""
    rows = conn.execute(
        """
        SELECT d.id FROM documents d
        WHERE EXISTS (SELECT 1 FROM document_pages p WHERE p.document_id = d.id)
          AND NOT EXISTS (SELECT 1 FROM document_chunks c WHERE c.document_id = d.id)
        """
    ).fetchall()
    for r in rows:
        pages = conn.execute(
            """
            SELECT page_number, text FROM document_pages
            WHERE document_id = ? ORDER BY page_number
            """,
            (r["id"],),
        ).fetchall()
        store_chunks(conn, r["id"], [dict(p) for p in pages])
    if rows:
        conn.commit()
    return len(rows)


# --------------------------------------------------------------------------
# Retrieval (permission-scoped similarity search)
# --------------------------------------------------------------------------

def retrieve_chunks(conn, project_id, question, top_k=3):
    """Rank stored chunks by cosine similarity to the question.

    Only chunks of current, non-archived documents in the project are
    considered, so the retrieval never touches documents the user cannot
    access. Returns the top-k chunks with their scores.
    """
    rows = conn.execute(
        """
        SELECT c.document_id, d.filename, c.page_number, c.text, c.embedding
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.project_id = ? AND d.is_current = 1 AND d.is_archived = 0
          AND c.embedding != ''
        """,
        (project_id,),
    ).fetchall()
    if not rows:
        return []

    from scipy.sparse import vstack
    from sklearn.metrics.pairwise import cosine_similarity

    matrix = vstack([json_to_vector(r["embedding"]) for r in rows]).tocsr()
    qvec = embed_texts([question])
    sims = cosine_similarity(qvec, matrix)[0]

    ranked = sorted(zip(rows, sims), key=lambda x: x[1], reverse=True)
    return [
        {
            "document_id": r["document_id"],
            "filename": r["filename"],
            "page_number": r["page_number"],
            "text": r["text"],
            "score": float(s),
        }
        for r, s in ranked[:top_k]
    ]


# --------------------------------------------------------------------------
# Answer generation
# --------------------------------------------------------------------------

def _build_context(hits):
    parts = []
    for h in hits:
        excerpt = (h["text"] or "")[:1500]
        parts.append(f"[{h['filename']} — page {h['page_number']}]\n{excerpt}")
    context = "\n\n".join(parts)
    if hits and max(h["score"] for h in hits) < LOW_SCORE:
        context += (
            "\n\n(Note: the excerpts above may not be relevant to the "
            "question. Say so if they do not answer it.)"
        )
    return context


def generate_answer(question, hits):
    """Return {"answer": str, "mode": "llm" | "retrieval-only"}."""
    context = _build_context(hits)

    if not OPENAI_API_KEY:
        return {
            "answer": (
                "No LLM API key is configured (set OPENAI_API_KEY to enable "
                "generated answers). Here are the most relevant passages "
                "found in the documents:\n\n" + context
            ),
            "mode": "retrieval-only",
        }

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are KnowFlow, an enterprise knowledge assistant. "
                        "Answer using ONLY the provided document excerpts. "
                        "If the question is general, such as asking what a "
                        "document is about, summarize the excerpts. "
                        "If the answer is not in the excerpts, reply that the "
                        "information was not found in the available documents. "
                        "Always cite the source document and page number."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nDocument excerpts:\n{context}",
                },
            ],
            temperature=0.2,
        )
        return {"answer": response.choices[0].message.content, "mode": "llm"}
    except Exception as exc:  # noqa: BLE001 — degrade gracefully
        return {
            "answer": (
                f"LLM call failed ({exc}). Showing the most relevant passages "
                "instead:\n\n" + context
            ),
            "mode": "retrieval-only",
        }