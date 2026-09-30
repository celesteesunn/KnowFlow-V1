"""RAG retrieval — hybrid candidates, RRF fusion, then reranking.

    query_plan + expansion
        -> chunk-level keyword ranking   ┐
        -> chunk-level semantic ranking  ┘-> RRF fusion -> rerank -> top-k

Why this is separate from search.py: the Search page ranks *documents* for a
human skimming results, while the assistant needs the specific passages that
actually contain the answer, ordered so the best evidence comes first and
noise never reaches the prompt. Two things follow from that:

  1. Ranking happens per chunk, not per document, and the chunk's heading and
     section path are first-class scoring fields. A passage that never repeats
     the section it lives in is still findable by that section.
  2. RRF merges the keyword and semantic rankings instead of blending their
     scores. Scores from a BM25-style term count and a cosine similarity live
     on incompatible scales; ranks do not.

The reranker then re-orders the fused candidates using signals a raw score
misses: how much of the question the chunk actually covers, whether the match
is in a heading rather than the body, whether the chunk's kind suits the
question's intent, and whether a better chunk from the same document already
took that slot.

Every SQL read is scoped to the signed-in user's own projects inside their
workspace, and to current, non-archived documents, before any scoring runs.
Restricted documents are never loaded, so they cannot influence a score.
"""

import re

import numpy as np

import search
from config import (
    RAG_CANDIDATE_POOL,
    RAG_CONTEXT_LEAD_CHARS,
    RAG_KEYWORD_WEIGHT,
    RAG_MAX_PER_DOCUMENT,
    RAG_MIN_RELEVANCE,
    RAG_MIN_SEMANTIC,
    RAG_RRF_K,
    RAG_SEMANTIC_WEIGHT,
    RAG_TOP_K,
)
from expansion import expand
from nlu import STYLE_WORDS

# Original question terms are worth more than synonyms we guessed.
_TERM_ORIGINAL = 1.0
_TERM_SYNONYM = 0.45

# Field weights for a keyword hit. A term in the section path says more about
# relevance than the same term buried in body prose, because the section path is
# the author's own statement of what the passage is about.
_FIELD_WEIGHTS = {
    "section": 2.6,
    "heading": 2.2,
    "body": 1.0,
    "doc_title": 1.6,
}

# Rerank feature weights (sum to 1.0).
_RERANK_WEIGHTS = {
    "fusion": 0.34,      # RRF agreement across both rankings
    "coverage": 0.24,    # fraction of the question's own terms present
    "semantic": 0.18,    # LSA cosine against the best expanded question
    "structure": 0.14,   # question terms appearing in heading / section
    "intent": 0.10,      # chunk kind matching what was asked
}

# Question intents that want a specific kind of passage.
_INTENT_KINDS = {
    "list": {"list", "table"},
    "comparison": {"table", "prose", "list"},
    "definition": {"prose", "table"},
    "explanation": {"prose"},
    "summary": {"prose", "list"},
}

# Multiplier applied to a chunk that shares no term with the question.
_NO_OVERLAP_PENALTY = 0.55

# Small additive boost for a document the conversation was already citing, used
# only on follow-up turns. It is deliberately small: it breaks ties toward the
# document already under discussion without being able to outrank a clearly
# better match found in a different document.
_CONTINUITY_BONUS = 0.06

# A passage that starts like this is a continuation, not a self-contained
# thought, so the preceding chunk is prepended for context.
_CONTINUATION_START = re.compile(
    r"^\s*(?:and|but|or|so|because|which|that|this|these|those|it|its|they|"
    r"their|he|she|his|her|however|therefore|thus|also|then|such)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Candidate loading
# --------------------------------------------------------------------------

def _load_candidates(conn, uid, ws_id, project_id=None):
    """Load every chunk the user is allowed to read, with its document meta.

    The permission boundary lives in the WHERE clause, exactly as it does for
    search.py, so unauthorised documents are never read into memory.
    """
    where, params = search._scope_where(uid, ws_id, project_id=project_id)
    rows = conn.execute(
        f"""
        SELECT c.id, c.document_id, c.page_number, c.chunk_index, c.text,
               c.section, c.heading, c.kind, c.semantic_embedding,
               d.filename, d.title, d.category, d.tags
        FROM document_chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN projects p ON p.id = d.project_id
        WHERE {where} AND c.text != ''
        ORDER BY c.document_id, c.chunk_index
        """,
        params,
    ).fetchall()

    candidates = []
    for r in rows:
        section = r["section"] or ""
        heading = r["heading"] or ""
        candidates.append({
            "chunk_id": r["id"],
            "document_id": r["document_id"],
            "page_number": r["page_number"],
            "chunk_index": r["chunk_index"],
            "text": r["text"] or "",
            "section": section,
            "heading": heading,
            "kind": r["kind"] or "prose",
            "embedding": r["semantic_embedding"] or "",
            "filename": r["filename"] or "",
            "title": r["title"] or r["filename"] or "",
            "doc_title_tokens": set(
                search.stem(t)
                for t in search.tokenize(
                    f"{r['title'] or ''} {r['filename'] or ''}"
                )
            ),
            "_stems": None,   # filled lazily by _prepare
        })
    return candidates


def _prepare(candidate):
    """Cache stemmed fields and lowercased text once per candidate."""
    if candidate["_stems"] is not None:
        return candidate
    text_low = candidate["text"].lower()
    structure_low = f"{candidate['section']} {candidate['heading']}".lower()
    candidate["_text_low"] = text_low
    candidate["_structure_low"] = structure_low
    candidate["_stems"] = {
        "body": set(search.stem(t) for t in search.tokenize(text_low)),
        "structure": set(search.stem(t) for t in search.tokenize(structure_low)),
    }
    candidate["_term_counts"] = {}
    for t in search.tokenize(text_low):
        candidate["_term_counts"][t] = candidate["_term_counts"].get(t, 0) + 1
    return candidate


# --------------------------------------------------------------------------
# Keyword scoring
# --------------------------------------------------------------------------

def _saturated(count):
    """BM25-style term-frequency saturation in (0, 1)."""
    if count <= 0:
        return 0.0
    return count / (count + 1.2)


def _keyword_features(cand, original_stems, synonym_stems, phrases):
    """Return (keyword_score, coverage, structure_score) for one chunk.

    coverage    how many of the question's *own* terms appear anywhere
    structure   how many appear in the heading / section path
    """
    _prepare(cand)
    body = cand["_stems"]["body"]
    structure = cand["_stems"]["structure"]

    total, weight = 0.0, 0.0
    for t in original_stems:
        if t in body or t in structure or t in cand["doc_title_tokens"]:
            total += _TERM_ORIGINAL
        weight += _TERM_ORIGINAL
    for t in synonym_stems:
        if t in body or t in structure or t in cand["doc_title_tokens"]:
            total += _TERM_SYNONYM
        weight += _TERM_SYNONYM

    if weight <= 0:
        return 0.0, 0.0, 0.0

    # Weighted field scoring, using saturation so a term repeated 50 times does
    # not dominate a passage that mentions it once in its heading.
    field_total = 0.0
    for t in original_stems:
        field_total += _TERM_ORIGINAL * _max_field_score(cand, t, body, structure)
    for t in synonym_stems:
        field_total += _TERM_SYNONYM * _max_field_score(cand, t, body, structure)

    phrase_bonus = 0.0
    for phrase in phrases:
        if phrase and phrase in cand["_text_low"]:
            phrase_bonus += 0.30
        elif phrase and phrase in cand["_structure_low"]:
            phrase_bonus += 0.18
    phrase_bonus = min(phrase_bonus, 0.6)

    keyword = (field_total / max(weight, 1e-6)) + phrase_bonus
    keyword = max(0.0, min(1.0, keyword))

    # Coverage uses the question's own terms only: synonyms exist to help find
    # text, not to claim the text answers the question.
    if original_stems:
        hits = sum(
            1 for t in original_stems
            if t in body or t in structure or t in cand["doc_title_tokens"]
        )
        coverage = hits / len(original_stems)
    else:
        coverage = 0.0

    if original_stems:
        s_hits = sum(1 for t in original_stems if t in structure)
        structure_score = s_hits / len(original_stems)
    else:
        structure_score = 0.0

    return keyword, coverage, structure_score


def _max_field_score(cand, term, body, structure):
    """Best field-weighted saturation score for one term in one chunk."""
    best = 0.0
    if term in structure:
        best = max(
            best,
            _saturated(cand["_term_counts"].get(term, 1)) * _FIELD_WEIGHTS["section"],
        )
    if term in body:
        best = max(best, _saturated(cand["_term_counts"].get(term, 0)) * _FIELD_WEIGHTS["body"])
    if term in cand["doc_title_tokens"]:
        best = max(best, _FIELD_WEIGHTS["doc_title"])
    return best


# --------------------------------------------------------------------------
# Semantic scoring
# --------------------------------------------------------------------------

def _semantic_scores(candidates, questions, model):
    """Best cosine similarity per chunk across all expanded questions.

    Multiple probes matter for multi-part questions: a chunk about part B
    should score well against probe B even if it is unrelated to probe A.
    """
    if model is None or not questions:
        return {}
    qvecs = search.embed_texts(questions, model)
    if qvecs is None or len(qvecs) == 0:
        return {}

    idx, vectors = [], []
    for i, cand in enumerate(candidates):
        raw = cand.get("embedding")
        if not raw:
            continue
        try:
            vectors.append(search.json_to_vector(raw))
            idx.append(i)
        except (ValueError, TypeError):
            continue
    if not vectors:
        return {}

    matrix = np.vstack(vectors)
    # rows = chunks, cols = question probes
    sims = matrix @ qvecs.T
    best = sims.max(axis=1)
    mean = sims.mean(axis=1)
    return {
        candidates[idx[i]]["chunk_id"]: {
            "best": float(max(best[i], 0.0)),
            # A chunk that matches one probe well and the rest badly is usually
            # more on-topic than one that is vaguely close to all of them, so
            # the blend leans on the best match.
            "blend": float(max(0.0, 0.7 * best[i] + 0.3 * mean[i])),
        }
        for i in range(len(idx))
    }


# --------------------------------------------------------------------------
# Reciprocal rank fusion
# --------------------------------------------------------------------------

def _rrf(ranked_ids, k=RAG_RRF_K):
    """Reciprocal rank fusion scores for one ranking.

    Ranks are compared instead of scores, which is what lets a keyword count
    and a cosine similarity contribute to the same ordering.
    """
    fused = {}
    for rank, cid in enumerate(ranked_ids):
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return fused


def _normalize_ranks(scored):
    """Map raw fused values to 0..1 for use as a rerank feature."""
    if not scored:
        return {}
    values = list(scored.values())
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scored}
    span = hi - lo
    return {k: (v - lo) / span for k, v in scored.items()}


# --------------------------------------------------------------------------
# Reranking
# --------------------------------------------------------------------------

def _intent_fit(cand, intent):
    """How well the chunk's kind suits the question's intent, in 0..1."""
    wanted = _INTENT_KINDS.get(intent)
    if not wanted:
        return 0.5
    if cand["kind"] in wanted:
        return 1.0
    # Prose is an acceptable answer to a list request, but a table is a poor
    # answer to a request for an explanation.
    if cand["kind"] == "prose" and intent in {"list", "summary", "comparison"}:
        return 0.7
    return 0.35


def _near_duplicate(cand, chosen):
    """True if this chunk repeats one already chosen (overlapping window)."""
    probe = cand["_text_low"][:220]
    for c in chosen:
        other = c["_text_low"][:220]
        if probe and other:
            if probe in other or other in probe:
                return True
    return False


def _rerank(candidates, features, top_k, max_per_doc, continuity_docs=None):
    """Order fused candidates by the weighted feature blend.

    Applies a per-document cap and near-duplicate suppression after scoring, so
    a long document with many similar windows cannot fill the whole context.
    """
    continuity = {d for d in (continuity_docs or [])}
    scored = []
    for cand in candidates:
        f = features[cand["chunk_id"]]
        score = (
            _RERANK_WEIGHTS["fusion"] * f["fusion"]
            + _RERANK_WEIGHTS["coverage"] * f["coverage"]
            + _RERANK_WEIGHTS["semantic"] * f["semantic"]
            + _RERANK_WEIGHTS["structure"] * f["structure"]
            + _RERANK_WEIGHTS["intent"] * f["intent"]
        )
        # A passage that shares no word with the question cannot be answering
        # it, however close its vector happens to be. On a small corpus LSA is
        # noisy enough that fuzzy-only matches otherwise drift into the top
        # slots. The penalty is a discount rather than a rejection so a
        # genuinely paraphrased question, where no chunk shares a term, can
        # still be answered on the semantic signal alone.
        if f["coverage"] == 0.0:
            score *= _NO_OVERLAP_PENALTY
        if continuity and cand["filename"] in continuity:
            score += _CONTINUITY_BONUS
        if score < RAG_MIN_RELEVANCE:
            continue
        scored.append((score, cand, f))
    scored.sort(key=lambda x: x[0], reverse=True)

    chosen, per_doc, seen_sections = [], {}, set()
    for score, cand, f in scored:
        doc_id = cand["document_id"]
        if per_doc.get(doc_id, 0) >= max_per_doc:
            continue
        if _near_duplicate(cand, chosen):
            continue
        # Two chunks from the same section add little once one is in context.
        section_key = (doc_id, cand["section"] or cand["heading"])
        if section_key in seen_sections and len(chosen) >= 2:
            continue
        per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
        seen_sections.add(section_key)
        chosen.append(cand)
        if len(chosen) >= top_k:
            break
    return chosen


# --------------------------------------------------------------------------
# Context assembly
# --------------------------------------------------------------------------

def _needs_lead_context(cand):
    """True if the passage starts mid-thought and needs its antecedent."""
    text = (cand["text"] or "").lstrip()
    if not text:
        return False
    if _CONTINUATION_START.match(text):
        return True
    # A passage that opens with a lowercase word is a fragment.
    first = text.split(" ", 1)[0]
    return bool(first) and first[0].islower()


def _add_lead_context(chosen, by_index):
    """Prepend the tail of the preceding chunk where a passage is a fragment.

    Only the previous chunk from the same document is considered, and only
    RAG_CONTEXT_LEAD_CHARS characters of it, so the extra context is bounded
    and cannot pull in unrelated earlier material.
    """
    enriched = []
    for cand in chosen:
        lead = ""
        if _needs_lead_context(cand):
            prev = by_index.get((cand["document_id"], cand["chunk_index"] - 1))
            if prev:
                prev_text = (prev["text"] or "").strip()
                if prev_text:
                    lead = prev_text[-RAG_CONTEXT_LEAD_CHARS:].strip()
        item = dict(cand)
        item["lead"] = lead
        item["context_text"] = (
            f"{lead}\n{cand['text']}" if lead else cand["text"]
        )
        enriched.append(item)
    return enriched


def _format_source(cand):
    """Source citation for the client.

    Document name and page only. The document id is an internal identifier and
    is not sent, even though it is used to deduplicate citations above.
    """
    return {
        "document": cand["filename"],
        "page": cand["page_number"],
    }


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def retrieve(conn, uid, ws_id, question, plan=None, project_id=None,
             top_k=None, candidate_pool=None, max_per_doc=None,
             continuity_docs=None):
    """Retrieve the passages most likely to answer a question.

    Returns {
      "chunks":     [{context_text, text, section, heading, kind, page_number,
                      document, document_id, lead}],
      "sources":    [{"document", "page", "document_id"}]  (deduplicated),
      "query_plan": the plan used,
      "expansion":  internal expansion summary (never shown to the user),
      "candidate_count": how many chunks entered reranking,
      "matched":    whether anything cleared the relevance floor,
    }

    `chunks` is what the answer generator sees; the scores behind the ordering
    are intentionally not exposed to the client.
    """
    top_k = top_k or RAG_TOP_K
    candidate_pool = candidate_pool or RAG_CANDIDATE_POOL
    max_per_doc = max_per_doc or RAG_MAX_PER_DOCUMENT

    if plan is None:
        from nlu import understand

        plan = understand(question)
    expansion = expand(plan)

    result = {
        "chunks": [],
        "sources": [],
        "query_plan": plan,
        "expansion": expansion["expanded"],
        "candidate_count": 0,
        "matched": False,
    }

    questions = expansion["questions"]
    if not questions:
        return result

    candidates = _load_candidates(conn, uid, ws_id, project_id=project_id)
    if not candidates:
        return result

    # Original question terms carry full weight; everything expansion added is
    # a synonym, which must not be able to outvote the question itself.
    question_stems = {search.stem(w) for w in _question_words(plan)}
    original_stems, synonym_stems = [], []
    for t in expansion["terms"]:
        target = original_stems if t in question_stems else synonym_stems
        if t not in target:
            target.append(t)
    phrases = [p.lower() for p in expansion["phrases"]]

    features = {}
    for cand in candidates:
        keyword, coverage, structure = _keyword_features(
            cand, original_stems, synonym_stems, phrases
        )
        features[cand["chunk_id"]] = {
            "keyword": keyword,
            "coverage": coverage,
            "structure": structure,
        }

    model = search._load_model()
    semantic = _semantic_scores(candidates, questions, model)
    for cand in candidates:
        sem = semantic.get(cand["chunk_id"], {})
        features[cand["chunk_id"]]["semantic"] = sem.get("blend", 0.0)

    # A chunk that is not semantically related and does not cover the question
    # is dropped before fusion, so it cannot dilute either ranking.
    pool = []
    for cand in candidates:
        f = features[cand["chunk_id"]]
        if f["semantic"] < RAG_MIN_SEMANTIC and f["coverage"] == 0:
            continue
        pool.append(cand)
    if not pool:
        return result

    keyword_ranked = [
        c["chunk_id"]
        for c in sorted(pool, key=lambda c: features[c["chunk_id"]]["keyword"],
                        reverse=True)
    ]
    semantic_ranked = [
        c["chunk_id"]
        for c in sorted(pool, key=lambda c: features[c["chunk_id"]]["semantic"],
                        reverse=True)
    ]

    fused = {}
    for cid, score in _rrf(keyword_ranked[:candidate_pool]).items():
        fused[cid] = fused.get(cid, 0.0) + RAG_KEYWORD_WEIGHT * score
    for cid, score in _rrf(semantic_ranked[:candidate_pool]).items():
        fused[cid] = fused.get(cid, 0.0) + RAG_SEMANTIC_WEIGHT * score

    fusion_norm = _normalize_ranks(fused)

    pool_by_id = {c["chunk_id"]: c for c in pool}
    for cid, norm in fusion_norm.items():
        cand = pool_by_id.get(cid)
        if cand is None:
            continue
        f = features[cid]
        f["fusion"] = norm
        f["intent"] = _intent_fit(cand, plan.get("intent"))

    ranked_pool = [pool_by_id[cid] for cid in fusion_norm if cid in pool_by_id]
    chosen = _rerank(ranked_pool, features, top_k, max_per_doc, continuity_docs)
    if not chosen:
        return result

    by_index = {(c["document_id"], c["chunk_index"]): c for c in pool}
    enriched = _add_lead_context(chosen, by_index)

    sources, seen = [], set()
    for cand in enriched:
        key = (cand["document_id"], cand["page_number"])
        if key in seen:
            continue
        seen.add(key)
        sources.append(_format_source(cand))

    result["chunks"] = [
        {
            "context_text": c["context_text"],
            "text": c["text"],
            "lead": c["lead"],
            "section": c["section"],
            "heading": c["heading"],
            "kind": c["kind"],
            "page_number": c["page_number"],
            "document": c["filename"],
            "document_id": c["document_id"],
        }
        for c in enriched
    ]
    result["sources"] = sources
    result["candidate_count"] = len(pool)
    result["matched"] = True
    return result


def _question_words(plan):
    """The question's own content words, used to tell originals from synonyms."""
    words = list(plan.get("keywords") or [])
    topic = plan.get("topic") or ""
    words.extend(w for w in search.tokenize(topic) if w not in STYLE_WORDS)
    return words
