"""Hybrid document search — keyword + semantic (LSA) embeddings.

Semantic embeddings are dense LSA vectors (HashingVectorizer -> TruncatedSVD)
computed once per chunk when a document is stored, then persisted in
document_chunks.semantic_embedding. At search time only the query is embedded
with the same frozen model, so embeddings are never recomputed per search.

The LSA model is fit once on the corpus (first use / startup backfill) and
then frozen, like a pretrained embedding model. HashingVectorizer has a fixed
feature space, so new documents never suffer from out-of-vocabulary drops.

Access control: every query is scoped to the signed-in user's own projects
(owner_id), so results can never leak documents the user cannot access.
"""

import json
import os
import pickle
import re

import numpy as np

from config import (
    DATA_DIR,
    SEARCH_KEYWORD_WEIGHT,
    SEARCH_MIN_COMBINED,
    SEARCH_SEMANTIC_WEIGHT,
)

MODEL_PATH = os.path.join(DATA_DIR, "search_model.pkl")
HASH_DIM = 2**16    # hashed feature count (fixed — no vocabulary fit)
LSA_DIM = 128       # dense semantic dimensions

_model_cache = None  # (mtime, model) — reloaded when the file changes


# --------------------------------------------------------------------------
# Tokenization + stemming (Porter) for keyword matching
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text):
    """Lowercase alphanumeric tokens of a text."""
    return _TOKEN_RE.findall((text or "").lower())


def _is_cons(word, i):
    """True if word[i] is a consonant (Porter definition)."""
    ch = word[i]
    if ch in "aeiou":
        return False
    if ch == "y":
        if i == 0:
            return True
        return not _is_cons(word, i - 1)
    return True


def _measure(word):
    """Porter's measure m: number of vowel-consonant sequences."""
    n = len(word)
    m = 0
    i = 0
    while i < n:
        while i < n and not _is_cons(word, i):
            i += 1
        while i < n and _is_cons(word, i):
            i += 1
        m += 1
    return m


def _contains_vowel(word):
    return any(not _is_cons(word, i) for i in range(len(word)))


def _ends_double_cons(word):
    return len(word) >= 2 and word[-1] == word[-2] and _is_cons(word, -1)


def _cvc(word):
    """True if word ends consonant-vowel-consonant (last not w/x/y)."""
    if len(word) < 3:
        return False
    if not (_is_cons(word, -1) and not _is_cons(word, -2) and _is_cons(word, -3)):
        return False
    return word[-1] not in "wxy"


def _step1a(word):
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies"):
        return word[:-2]
    if word.endswith("ss"):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def _step1b(word):
    flag = False
    if word.endswith("eed"):
        return word[:-1] if _measure(word[:-3]) > 0 else word
    if word.endswith("ed"):
        if _contains_vowel(word[:-2]):
            word, flag = word[:-2], True
    elif word.endswith("ing"):
        if _contains_vowel(word[:-3]):
            word, flag = word[:-3], True
    if not flag:
        return word
    if word.endswith(("at", "bl", "iz")):
        return word + "e"
    if _ends_double_cons(word) and word[-1] not in "lsz":
        return word[:-1]
    if _measure(word) == 1 and _cvc(word):
        return word + "e"
    return word


def _step1c(word):
    if word.endswith("y") and _contains_vowel(word[:-1]):
        return word[:-1] + "i"
    return word


def _step2(word):
    rules = {
        "ational": "ate", "tional": "tion", "enci": "ence", "anci": "ance",
        "izer": "ize", "bli": "ble", "alli": "al", "entli": "ent",
        "eli": "e", "ousli": "ous", "ization": "ize", "ation": "ate",
        "ator": "ate", "alism": "al", "iveness": "ive", "fulness": "ful",
        "ousness": "ous", "aliti": "al", "iviti": "ive", "biliti": "ble",
        "logi": "log",
    }
    for suffix, repl in rules.items():
        if word.endswith(suffix):
            if _measure(word[: -len(suffix)]) > 0:
                return word[: -len(suffix)] + repl
            return word
    return word


def _step3(word):
    rules = {
        "icate": "ic", "ative": "", "alize": "al", "iciti": "ic",
        "ical": "ic", "ful": "", "ness": "",
    }
    for suffix, repl in rules.items():
        if word.endswith(suffix):
            if _measure(word[: -len(suffix)]) > 0:
                return word[: -len(suffix)] + repl
            return word
    return word


def _step4(word):
    suffixes = [
        "al", "ance", "ence", "er", "ic", "able", "ible", "ant",
        "ement", "ment", "ent", "ion", "ou", "ism", "ate", "iti",
        "ous", "ive", "ize",
    ]
    for suffix in suffixes:
        if word.endswith(suffix):
            stem = word[: -len(suffix)]
            if _measure(stem) > 1:
                if suffix == "ion" and stem and stem[-1] not in "st":
                    return word
                return stem
            return word
    return word


def _step5a(word):
    if word.endswith("e"):
        stem = word[:-1]
        if _measure(stem) > 1:
            return stem
        if _measure(stem) == 1 and not _cvc(stem):
            return stem
    return word


def _step5b(word):
    if _measure(word) > 1 and _ends_double_cons(word) and word[-1] == "l":
        return word[:-1]
    return word


def stem(word):
    """Porter stemmer (public-domain algorithm)."""
    word = word.lower()
    if len(word) <= 2:
        return word
    word = _step1a(word)
    word = _step1b(word)
    word = _step1c(word)
    word = _step2(word)
    word = _step3(word)
    word = _step4(word)
    word = _step5a(word)
    word = _step5b(word)
    return word


def _stopwords():
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    return ENGLISH_STOP_WORDS


def query_tokens(query):
    """Stemmed, stop-word-free tokens used for keyword scoring."""
    stops = _stopwords()
    return [stem(t) for t in tokenize(query) if t not in stops]


# --------------------------------------------------------------------------
# Semantic model (HashingVectorizer -> TruncatedSVD, fit once, frozen)
# --------------------------------------------------------------------------

def _hash_vectorizer():
    from sklearn.feature_extraction.text import HashingVectorizer

    return HashingVectorizer(
        stop_words="english",
        n_features=HASH_DIM,
        norm="l2",
        alternate_sign=False,
    )


def _normalize(matrix):
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _load_model():
    """Return the fitted model dict, or None. Cached by file mtime."""
    global _model_cache
    mtime = os.path.getmtime(MODEL_PATH) if os.path.exists(MODEL_PATH) else None
    if _model_cache is not None and _model_cache[0] == mtime:
        return _model_cache[1]
    if mtime is None:
        _model_cache = (None, None)
        return None
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    _model_cache = (mtime, model)
    return model


def _save_model(model):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)
    global _model_cache
    _model_cache = (os.path.getmtime(MODEL_PATH), model)


def ensure_model(conn, fallback_texts=None):
    """Fit the LSA model on the corpus if it does not exist yet.

    fallback_texts: chunk texts of the document being stored right now,
    used when the database has no committed chunks to fit on yet.
    Returns the model dict, or None when there is nothing to fit on.
    """
    model = _load_model()
    if model is not None:
        return model

    texts = list(fallback_texts or [])
    if not texts:
        rows = conn.execute(
            "SELECT text FROM document_chunks WHERE text != ''"
        ).fetchall()
        texts = [r["text"] for r in rows]
    if not texts:
        return None

    from sklearn.decomposition import TruncatedSVD

    vectorizer = _hash_vectorizer()
    matrix = vectorizer.transform(texts)
    n_comp = min(LSA_DIM, max(2, len(texts)))
    svd = TruncatedSVD(n_components=n_comp, random_state=42)
    dense = _normalize(svd.fit_transform(matrix))
    model = {"vectorizer": vectorizer, "svd": svd, "fit_count": len(texts)}
    _save_model(model)
    return model


def embed_texts(texts, model):
    """Dense L2-normalized embeddings for texts using the frozen model."""
    if model is None or not texts:
        return None
    matrix = model["vectorizer"].transform(texts)
    dense = model["svd"].transform(matrix)
    return _normalize(dense)


def embed_query(text, model):
    """Dense L2-normalized embedding for a single query."""
    if model is None:
        return None
    return embed_texts([text], model)[0]


def vector_to_json(vec):
    return json.dumps(vec.tolist())


def json_to_vector(data):
    return np.asarray(json.loads(data), dtype=float)


# --------------------------------------------------------------------------
# Keyword scoring
# --------------------------------------------------------------------------

def _file_type(filename):
    """Human-readable file type from the stored filename."""
    ext = os.path.splitext(filename or "")[1].lower()
    return {"pdf": "PDF", "docx": "DOCX", "txt": "TXT"}.get(
        ext, ext.lstrip(".").upper() or "FILE"
    )


def keyword_score(q_tokens, doc, chunk_texts):
    """Relevance of a document to the query tokens, normalized to 0..1.

    Metadata weights: title 3.0, filename 2.5, description/category/tags 2.0,
    uploader name 1.0, body (chunk text) 1.0, partial (substring) matches
    1.5/0.5. A phrase bonus rewards documents containing the query terms
    together. The body is scored against the stored chunk index (the same
    representation used for semantic search), never the full document text.
    """
    if not q_tokens:
        return 0.0

    title = [stem(t) for t in tokenize(doc["title"] or "")]
    filename = [stem(t) for t in tokenize(doc["filename"] or "")]
    desc = [stem(t) for t in tokenize(doc["description"] or "")]
    cat = [stem(t) for t in tokenize(doc["category"] or "")]
    tags = [stem(t) for t in tokenize(doc["tags"] or "")]
    uploader = [stem(t) for t in tokenize(doc["full_name"] or doc["username"] or "")]
    body = [stem(t) for t in tokenize(" ".join(chunk_texts))]

    total = 0.0
    for qt in q_tokens:
        if qt in title:
            total += 3.0
        elif qt in filename:
            total += 2.5
        elif qt in desc or qt in cat or qt in tags:
            total += 2.0
        elif qt in uploader:
            total += 1.0
        elif qt in body:
            total += 1.0
        elif any(qt in t for t in title) or any(qt in t for t in filename):
            total += 1.5
        elif any(qt in t for t in body):
            total += 0.5

    score = total / (3.0 * len(q_tokens))

    if len(q_tokens) >= 2:
        joined = " ".join(q_tokens)
        if joined in " ".join(body):
            score += 0.15
        elif all(qt in body for qt in q_tokens):
            score += 0.1

    return min(score, 1.0)


# --------------------------------------------------------------------------
# Hybrid search
# --------------------------------------------------------------------------

def _build_snippet(chunk, doc, raw_terms):
    """Return (snippet, page_number) around the best match."""
    if chunk:
        text, page = chunk[0], chunk[1]
    else:
        text, page = doc["text"] or "", 1
    if not text:
        return "", page

    low = text.lower()
    idx = -1
    for term in raw_terms:
        i = low.find(term)
        if i != -1 and (idx == -1 or i < idx):
            idx = i
    if idx == -1:
        idx = 0
    start = max(0, idx - 120)
    snippet = " ".join(text[start : start + 300].split())
    return snippet, page


def _scope_where(uid, ws_id, category=None, doc_type=None, project_id=None,
                 uploaded_by=None, date_from=None, date_to=None, tags=None):
    """WHERE clause + params: permission boundary first, then optional filters.

    Access control is applied inside the query itself (owner + workspace),
    so restricted documents never reach the ranking step.
    """
    where = [
        "p.owner_id = ?",
        "p.workspace_id = ?",
        "d.is_current = 1",
        "d.is_archived = 0",
    ]
    params = [uid, ws_id]

    if category:
        where.append("d.category = ?")
        params.append(category)
    if doc_type:
        where.append("LOWER(SUBSTR(d.filename, INSTR(d.filename, '.') + 1)) = ?")
        params.append(doc_type.lower())
    if project_id:
        where.append("d.project_id = ?")
        params.append(project_id)
    if uploaded_by:
        where.append("d.uploaded_by = ?")
        params.append(uploaded_by)
    if date_from:
        where.append("date(d.created_at) >= date(?)")
        params.append(date_from)
    if date_to:
        where.append("date(d.created_at) <= date(?)")
        params.append(date_to)
    if tags:
        tag_conds = []
        for t in tags.split(","):
            t = t.strip()
            if t:
                tag_conds.append("d.tags LIKE ?")
                params.append(f"%{t}%")
        if tag_conds:
            where.append("(" + " OR ".join(tag_conds) + ")")

    return " AND ".join(where), params


def hybrid_search(conn, uid, ws_id, query, limit=20, category=None,
                  doc_type=None, project_id=None, uploaded_by=None,
                  date_from=None, date_to=None, tags=None):
    """Hybrid keyword + semantic search over the user's authorised documents.

    Only documents in projects owned by uid AND inside the user's workspace
    are considered, so the existing permission boundary is enforced before
    any ranking happens. Optional filters (category, file type, project,
    uploader, date range, tags) narrow the authorised set further.
    """
    q_tokens = query_tokens(query)
    raw_terms = tokenize(query)
    if not q_tokens:
        return []

    where, params = _scope_where(
        uid, ws_id, category, doc_type, project_id, uploaded_by, date_from,
        date_to, tags,
    )

    docs = conn.execute(
        f"""
        SELECT d.id AS document_id, d.filename, d.title, d.description,
               d.category, d.tags, d.page_count, d.version, d.created_at,
               d.text, d.uploaded_by, u.username, u.full_name,
               p.id AS project_id, p.name AS project_name
        FROM documents d
        JOIN projects p ON p.id = d.project_id
        JOIN users u ON u.id = d.uploaded_by
        WHERE {where}
        """,
        params,
    ).fetchall()
    if not docs:
        return []

    # Semantic scores: query embedding vs stored chunk embeddings.
    model = _load_model()
    qvec = embed_query(query, model) if model else None

    sem_by_doc = {}
    best_chunk = {}
    chunk_texts_by_doc = {}
    if qvec is not None:
        chunk_rows = conn.execute(
            f"""
            SELECT c.document_id, c.page_number, c.text, c.semantic_embedding
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN projects p ON p.id = d.project_id
            WHERE {where}
              AND c.semantic_embedding != ''
            """,
            params,
        ).fetchall()
        if chunk_rows:
            matrix = np.vstack(
                [json_to_vector(r["semantic_embedding"]) for r in chunk_rows]
            )
            sims = matrix @ qvec  # both L2-normalized -> cosine similarity
            for r, s in zip(chunk_rows, sims):
                doc_id = r["document_id"]
                sim = float(s)
                sem_by_doc.setdefault(doc_id, []).append(sim)
                chunk_texts_by_doc.setdefault(doc_id, []).append(
                    (r["text"], r["page_number"])
                )
                if doc_id not in best_chunk or sim > best_chunk[doc_id][2]:
                    best_chunk[doc_id] = (r["text"], r["page_number"], sim)
    else:
        # No model yet — still load chunk texts for keyword scoring.
        chunk_rows = conn.execute(
            f"""
            SELECT c.document_id, c.page_number, c.text
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN projects p ON p.id = d.project_id
            WHERE {where}
            """,
            params,
        ).fetchall()
        for r in chunk_rows:
            chunk_texts_by_doc.setdefault(r["document_id"], []).append(
                (r["text"], r["page_number"])
            )

    # Keyword scores (metadata + chunk index, never the full document text).
    kw_by_doc = {
        d["document_id"]: keyword_score(
            q_tokens, d,
            [t for t, _ in chunk_texts_by_doc.get(d["document_id"], [])],
        )
        for d in docs
    }

    # Snippet selection: prefer the best semantic chunk; otherwise the chunk
    # with the most keyword hits (so keyword-only matches still get a
    # meaningful excerpt instead of the start of the document).
    for d in docs:
        doc_id = d["document_id"]
        if doc_id in best_chunk:
            continue
        texts = chunk_texts_by_doc.get(doc_id, [])
        if not texts:
            continue
        best, best_hits = None, -1
        for text, page in texts:
            hits = sum(text.lower().count(term) for term in raw_terms)
            if hits > best_hits:
                best_hits, best = hits, (text, page, 0.0)
        if best is not None and best_hits > 0:
            best_chunk[doc_id] = best

    scored = []
    for d in docs:
        doc_id = d["document_id"]
        kw = kw_by_doc.get(doc_id, 0.0)
        sem = max(sem_by_doc.get(doc_id, [0.0]))
        combined = SEARCH_KEYWORD_WEIGHT * kw + SEARCH_SEMANTIC_WEIGHT * sem
        if combined < SEARCH_MIN_COMBINED:
            continue
        scored.append((combined, kw, sem, d, best_chunk.get(doc_id)))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for combined, kw, sem, d, chunk in scored[:limit]:
        snippet, page = _build_snippet(chunk, d, raw_terms)
        results.append(
            {
                "document_id": d["document_id"],
                "filename": d["filename"],
                "title": d["title"] or d["filename"],
                "description": d["description"] or "",
                "category": d["category"] or "",
                "tags": d["tags"] or "",
                "type": _file_type(d["filename"]),
                "project_id": d["project_id"],
                "project_name": d["project_name"],
                "page_number": page,
                "page_count": d["page_count"],
                "version": d["version"],
                "created_at": d["created_at"],
                "uploaded_by": d["uploaded_by"],
                "uploader_name": d["full_name"] or d["username"] or "",
                "snippet": snippet,
                "relevance": round(combined, 3),
            }
        )
    return results