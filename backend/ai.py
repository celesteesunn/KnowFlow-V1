"""Retrieval + LLM answer generation.

Retrieval: TF-IDF (scikit-learn) cosine similarity between the question and
every extracted page; the top-k pages become the answer sources.

Generation: an OpenAI-compatible chat completion grounded in those pages.
Without OPENAI_API_KEY the system runs in "retrieval-only" mode and returns
the top passages themselves, so the feature is fully demonstrable offline.
"""

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


def retrieve_pages(pages, question, top_k=3):
    """Rank pages by TF-IDF cosine similarity to the question.

    pages: list of dicts {document_id, filename, page_number, text}
    Returns: list of {"page": <page dict>, "score": float} sorted by score.
    """
    if not pages:
        return []

    texts = [p["text"] for p in pages]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
        matrix = vectorizer.fit_transform(texts + [question])
        sims = cosine_similarity(matrix[-1:], matrix[:-1])[0]
    except ValueError:
        # Empty vocabulary (e.g. all stop words) — nothing to rank.
        sims = [0.0] * len(texts)

    ranked = sorted(zip(pages, sims), key=lambda x: x[1], reverse=True)
    return [
        {"page": p, "score": float(s)}
        for p, s in ranked[:top_k]
        if s > 0
    ]


def _build_context(hits):
    parts = []
    for h in hits:
        page = h["page"]
        excerpt = (page["text"] or "")[:1500]
        parts.append(f"[{page['filename']} — page {page['page_number']}]\n{excerpt}")
    return "\n\n".join(parts)


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
                        "If the answer is not in the excerpts, say so clearly. "
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