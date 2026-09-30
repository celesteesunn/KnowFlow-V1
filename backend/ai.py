"""RAG pipeline: chunking, retrieval, reranking, LLM generation.

Flow:

    Uploaded document -> extracted text -> structure-aware chunks
    (each keeping its heading path) -> dense LSA embeddings in SQLite
    -> question understanding + query expansion
    -> keyword + semantic chunk retrieval -> RRF fusion -> rerank
    -> grounded answer with style constraints -> answer + sources

Retrieval is scoped to the signed-in user's own projects inside their
workspace, and to current, non-archived documents, so the permission boundary
is enforced before any context reaches the LLM.

Without OPENAI_API_KEY the system runs in "retrieval-only" mode and returns
the best passages themselves, so the feature is fully demonstrable offline.
"""

import json
import logging

from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL

EMBED_DIM = 2**16      # HashingVectorizer feature count (fixed, no fit)
CHUNK_MAX_CHARS = 600  # legacy target chunk size (kept for backfill helpers)
CHUNK_OVERLAP = 100    # legacy overlap (kept for backfill helpers)
LOW_SCORE = 0.05       # below this, flag excerpts as possibly irrelevant


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

def chunk_text(text, max_chars=CHUNK_MAX_CHARS, overlap=CHUNK_OVERLAP):
    """Split a flat block of text into overlapping, sentence-aware chunks.

    Structure-aware chunking (chunking.chunk_pages) is what documents are
    stored with. This is the structure-free fallback for text that arrived
    without page or heading information.
    """
    from chunking import _pack_sentences, _split_sentences

    text = (text or "").strip()
    if not text:
        return []
    sentences = _split_sentences(text)
    if not sentences:
        return []
    return _pack_sentences(sentences, target=max_chars, overlap=overlap)


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

def store_chunks(conn, document_id, pages, filename=""):
    """Chunk + embed every page and store the rows in document_chunks.

    Chunking is structure-aware: each row keeps the heading path, the nearest
    heading and whether the passage is prose, a list or a table, so a retrieved
    passage carries its own context into the prompt.

    Each chunk also gets a dense LSA embedding (hybrid search), computed once
    here and reused, never regenerated per search. The section path is
    prepended before embedding so a passage is findable by the section it sits
    under even when the body text never repeats that section's name.
    """
    from chunking import CHUNK_VERSION, chunk_pages
    from search import (
        embed_texts as semantic_embed_texts,
        ensure_model,
        vector_to_json as dense_to_json,
    )

    structured = chunk_pages(pages, filename or "")
    if not structured:
        return 0

    all_texts = [f"{c['section']} {c['text']}".strip() for c in structured]
    model = ensure_model(conn, fallback_texts=all_texts)
    dense = semantic_embed_texts(all_texts, model) if model else None

    # chunk_index restarts per page so a section that continues over a page
    # break stays addressable, and _add_lead_context can find its predecessor.
    per_page = {}
    for c in structured:
        per_page.setdefault(c["page_number"], 0)
    rows = []
    for c in structured:
        page = c["page_number"]
        index = per_page[page]
        per_page[page] = index + 1
        rows.append((
            page, index, c["text"], c["section"], c["heading"], c["kind"],
            dense_to_json(dense[len(rows)]) if dense is not None else "",
        ))

    conn.executemany(
        """
        INSERT INTO document_chunks
            (document_id, page_number, chunk_index, text, embedding,
             semantic_embedding, section, heading, kind, chunk_version)
        VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?)
        """,
        [
            (document_id, page_number, index, text, dense_json, section,
             heading, kind, CHUNK_VERSION)
            for page_number, index, text, section, heading, kind, dense_json
            in rows
        ],
    )
    return len(rows)


def backfill_chunks(conn):
    """Create chunks for documents extracted before chunking existed.

    Also re-chunks documents whose rows were produced by an older splitter.
    Staleness is detected from document_chunks.chunk_version, not from whether
    a section was recorded: a document with no headings stores an empty section
    legitimately, so keying off section would re-chunk those documents on every
    single startup.

    Re-chunking replaces the document's rows outright rather than appending,
    so a document is never left holding a mix of old and new chunking.
    """
    from chunking import CHUNK_VERSION

    rows = conn.execute(
        """
        SELECT d.id, d.filename FROM documents d
        WHERE EXISTS (SELECT 1 FROM document_pages p WHERE p.document_id = d.id)
          AND NOT EXISTS (
            SELECT 1 FROM document_chunks c
            WHERE c.document_id = d.id AND c.chunk_version >= ?
          )
        """,
        (CHUNK_VERSION,),
    ).fetchall()
    for r in rows:
        pages = conn.execute(
            """
            SELECT page_number, text FROM document_pages
            WHERE document_id = ? ORDER BY page_number
            """,
            (r["id"],),
        ).fetchall()
        if not pages:
            continue
        conn.execute(
            "DELETE FROM document_chunks WHERE document_id = ?", (r["id"],)
        )
        store_chunks(conn, r["id"], [dict(p) for p in pages], r["filename"] or "")
    if rows:
        conn.commit()
    return len(rows)


def backfill_semantic(conn):
    """Compute dense semantic embeddings for chunks that lack them.

    Runs once at startup for documents stored before the hybrid-search
    feature existed. The LSA model is fit on the whole corpus if missing.
    """
    from search import (
        embed_texts,
        ensure_model,
        vector_to_json as dense_to_json,
    )

    rows = conn.execute(
        """
        SELECT id, text FROM document_chunks
        WHERE semantic_embedding = '' OR semantic_embedding IS NULL
        """
    ).fetchall()
    if not rows:
        return 0

    model = ensure_model(conn)
    if model is None:
        return 0

    texts = [r["text"] for r in rows]
    dense = embed_texts(texts, model)
    for r, vec in zip(rows, dense):
        conn.execute(
            "UPDATE document_chunks SET semantic_embedding = ? WHERE id = ?",
            (dense_to_json(vec), r["id"]),
        )
    conn.commit()
    return len(rows)


# --------------------------------------------------------------------------
# Retrieval (permission-scoped hybrid search + reranking)
# --------------------------------------------------------------------------

def retrieve_chunks(conn, project_id, question, uid=None, ws_id=None,
                    plan=None, history=None, top_k=None):
    """Retrieve the passages that should answer a question.

    Delegates to rag.retrieve, which runs keyword + semantic chunk retrieval,
    fuses the two rankings with RRF and reranks the result. The permission
    scope is the signed-in user's own projects inside their workspace, narrowed
    further to this project, and only current, non-archived documents.

    The similarity scores behind the ordering stay inside the server: only the
    passages, their document, page and section are used downstream.
    """
    from conversation import referenced_documents
    from rag import retrieve

    history = history or []
    followup = bool(plan and plan.get("is_followup"))
    return retrieve(
        conn, uid, ws_id, question,
        plan=plan,
        project_id=project_id,
        top_k=top_k,
        continuity_docs=(
            referenced_documents(history) if followup else None
        ),
    )


# --------------------------------------------------------------------------
# Context assembly
# --------------------------------------------------------------------------

_EXCERPT_CHARS = 1600


def _build_context(chunks):
    """Render retrieved passages for the prompt.

    Each passage is labelled with its document, page and section, so the model
    can tell a heading that applies to the text from the text itself, and can
    resolve what a shortened name or pronoun in a passage refers to. Lead
    context carried over from the previous chunk is included, since a passage
    that begins mid-sentence is not readable without it.
    """
    parts = []
    for i, c in enumerate(chunks, start=1):
        label = f"{c['document']}, page {c['page_number']}"
        section = c.get("section") or c.get("heading") or ""
        if section:
            label += f", section: {section}"
        body = c.get("context_text") or c.get("text") or ""
        parts.append(f"[{i}] {label}\n{body[:_EXCERPT_CHARS]}")
    return "\n\n".join(parts)


def _style_instructions(plan):
    """Turn the question's detected constraints into explicit instructions.

    A user who writes "explain in simple words in 5 points" asked for two
    different things, and a model will not reliably infer either from the
    question text alone. Naming them here is what makes the constraint stick.
    """
    if not plan:
        return []
    c = plan.get("constraints") or {}
    out = []
    if c.get("simple"):
        out.append(
            "Use simple, everyday language. Avoid jargon, or explain any term "
            "the first time it appears."
        )
    if c.get("detailed") or c.get("elaborate"):
        out.append(
            "Be thorough and cover the supporting detail, not just the headline."
        )
    if c.get("short") or c.get("brief"):
        out.append("Be brief and direct. A few sentences at most.")
    if c.get("bullet"):
        out.append("Answer as bullet points.")
    if c.get("numbered"):
        out.append("Answer as a numbered list.")
    if c.get("list") or c.get("points"):
        n = c.get("points")
        out.append(
            f"Answer as a numbered list of exactly {n} points."
            if n else "Answer as a short numbered list of the key points."
        )
    if c.get("example") or c.get("examples"):
        out.append("Include a concrete example.")
    if c.get("steps"):
        out.append("Present the answer as clear, ordered steps.")
    if c.get("compare") or c.get("comparison"):
        out.append(
            "Present the comparison as a table or a clearly labelled "
            "point-by-point breakdown."
        )
    if c.get("summary") or c.get("summarize"):
        out.append("Give a concise summary of the key ideas.")
    if c.get("conclusion"):
        out.append("Close with a brief conclusion.")
    return out


_SYSTEM_PROMPT = (
    "You are KnowFlow, an enterprise knowledge assistant. You answer strictly "
    "from document passages you are given.\n\n"
    "Rules:\n"
    "- Use ONLY facts stated in the passages. Never add outside knowledge, and "
    "never guess.\n"
    "- If the passages do not contain the answer, say so plainly and stop. Do "
    "not fill the gap with related information the user did not ask for.\n"
    "- If only part of the answer is present, give that part first, then state "
    "plainly what was not found.\n"
    "- A passage's section heading tells you what that passage is about. Use it "
    "to resolve what a pronoun or a shortened name refers to, but never state "
    "the heading as if it were the answer.\n"
    "- When a follow-up refers back to earlier turns, answer about the same "
    "subject the conversation was already on, unless the new question clearly "
    "changes it.\n\n"
    "Writing style - reply as a polished, readable answer:\n"
    "- Use Markdown for structure: '##' for section headings, '**bold**' for key "
    "terms, '-' bullets and '1.' numbered lists.\n"
    "- Keep paragraphs short and separated by a blank line.\n"
    "- Start with the answer itself. Do not restate the question, and do not "
    "open with filler like 'Based on the provided documents'.\n"
    "- Do not mention passages, excerpts, context, chunks, retrieval, "
    "similarity scores or any other internals.\n"
    "- Do not write source citations into the answer body; the application adds "
    "a Sources section for you.\n"
    'If the information is missing, reply naturally, for example: "I couldn\'t '
    'find information about X in the uploaded document."'
)


def generate_answer(question, chunks, plan=None, history=None,
                    route_intent=None):
    """Return {"answer": str, "mode": "llm" | "retrieval-only"}.

    chunks is the rag.retrieve result's "chunks" list. plan is the query
    understanding, used to honour style constraints and resolve follow-up
    references. history is the bounded recent conversation.

    route_intent carries the router's decision for the two context intents, so
    the model is told to *continue* (navigation) or *reformat* (modification)
    rather than to answer a fresh question.
    """
    from conversation import format_for_prompt, last_exchange

    context = _build_context(chunks)

    if not OPENAI_API_KEY:
        # Without a key the passages are the answer. They are still the right
        # passages: the router already resolved the query to the previous topic
        # for navigation and reformatting.
        return {
            "answer": (
                "Here are the passages closest to your question.\n\n" + context
            ),
            "mode": "retrieval-only",
        }

    instructions = _style_instructions(plan)
    system = _SYSTEM_PROMPT

    if route_intent == "navigation":
        system += (
            "\n\nThe user asked to continue. Move on to the NEXT related "
            "topic, point or section in the same document(s), building on "
            "what has already been covered. Do not repeat the previous answer."
        )
    elif route_intent == "answer_modification":
        system += (
            "\n\nThe user wants the previous answer reformatted. Keep the "
            "same facts and sources, and change only the presentation. Do not "
            "introduce new content or start a different topic."
        )

    if instructions:
        system += (
            "\n\nFollow the requested format for this answer:\n- "
            + "\n- ".join(instructions)
        )

    user_parts = []
    transcript = format_for_prompt(history or [])
    if transcript:
        user_parts.append("Earlier in this conversation:\n" + transcript)

    # The reformat and navigation intents act on a specific previous answer, so
    # it is passed through explicitly rather than only implied by the transcript
    # summary.
    if route_intent in ("answer_modification", "navigation"):
        previous = last_exchange(history)
        if previous:
            if route_intent == "answer_modification":
                user_parts.append(
                    "Rewrite this previous answer:\n" + previous["answer"]
                )
            else:
                user_parts.append(
                    "This has already been covered:\n" + previous["answer"]
                )

    if plan and plan.get("is_followup") and plan.get("previous_topic"):
        user_parts.append(
            f'The current question refers back to: "{plan["previous_topic"]}".'
        )
    user_parts.append(f"Question: {question}")
    user_parts.append(f"Document passages:\n{context}")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            temperature=0.2,
        )
        return {"answer": response.choices[0].message.content, "mode": "llm"}
    except Exception:  # noqa: BLE001 - degrade gracefully
        # The exception is logged server-side, never returned to the user.
        logging.getLogger(__name__).warning("LLM call failed: %s", exc_info=True)
        return {
            "answer": (
                "A generated answer is not available right now. Here are the "
                "passages closest to your question.\n\n" + context
            ),
            "mode": "retrieval-only",
        }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _not_found_answer(original, effective, plan):
    """The no-result reply, naming what was actually searched for.

    This is only reached for a document-related question, so it can be
    specific: "I couldn't find information about the maternity leave policy"
    tells the user which topic came up empty. A greeting can never land here,
    because greetings are answered before retrieval runs.
    """
    # Prefer the cleaned topic ("company maternity leave policy") over the raw
    # question, but fall back to the question itself when the topic is empty.
    topic = ""
    if plan:
        topic = (plan.get("topic") or "").strip()
        if plan.get("is_followup") and plan.get("previous_topic"):
            topic = plan["previous_topic"]
    if not topic:
        topic = (effective or original or "").strip(" ?.!")

    if not topic:
        return (
            "I couldn't find anything relevant in the documents you have "
            "access to. Try asking about a specific topic."
        )
    return (
        f"I couldn't find information about {topic} in the documents you "
        f"have access to."
    )


def ask_documents(conn, uid, ws_id, project_id, question, record=True):
    """Answer a message using RAG only when the message is actually a question.

    The intent router runs FIRST, because the assistant is a conversational AI
    that has document retrieval as one capability — not a search box that
    answers every input with passages. A greeting, a "thanks", or "what can you
    do?" is answered directly and never reaches the vector store, so those
    messages cannot produce a "couldn't find information" reply and do not burn
    retrieval.

    Routes:
      conversational -> natural reply, no retrieval, no sources
      navigation /
      answer_modification -> resolve against the previous topic, then RAG
      follow-up / document question -> hybrid RAG pipeline

    "couldn't find information" is only ever produced for a document-related
    question where a search actually ran and found nothing relevant.

    The caller is responsible for the permission check on the project; this
    function additionally scopes retrieval to that user's workspace and
    project, so the boundary holds even if a caller forgets.

    Returns {
      "answer": str, "mode": str, "sources": [{"document", "page"}],
      "matched": bool, "query_plan": dict, "intent": str,
      "retrieval_attempted": bool,
    }
    """
    from conversation import last_exchange, load_history, save_turn
    from intent import (
        CAPABILITY, MODIFICATION, NAVIGATION, NO_CONTEXT_REPLY, build_reply,
        classify,
    )
    from nlu import understand

    history = load_history(conn, project_id, uid) if record else []
    prior_user = [h for h in history if h.get("role") == "user"]
    has_history = bool(prior_user)

    route = classify(question, has_history)

    # ------------------------------------------------------------------
    # 1. Conversational: answer directly, never retrieve.
    # ------------------------------------------------------------------
    reply = build_reply(route, has_history)
    if reply is not None:
        if record:
            save_turn(conn, project_id, uid, ws_id, "user", question)
            save_turn(conn, project_id, uid, ws_id, "assistant", reply, [])
        return {
            "answer": reply,
            "mode": "conversational",
            "sources": [],
            # Nothing was searched, so this is not a knowledge gap and must
            # never be logged as one.
            "matched": True,
            "query_plan": None,
            "intent": route["intent"],
            "retrieval_attempted": False,
        }

    # ------------------------------------------------------------------
    # 2. Navigation / answer modification need a prior answer to act on.
    # ------------------------------------------------------------------
    if route["intent"] in (NAVIGATION, MODIFICATION) and not has_history:
        if record:
            save_turn(conn, project_id, uid, ws_id, "user", question)
            save_turn(conn, project_id, uid, ws_id, "assistant",
                      NO_CONTEXT_REPLY, [])
        return {
            "answer": NO_CONTEXT_REPLY,
            "mode": "conversational",
            "sources": [],
            "matched": True,
            "query_plan": None,
            "intent": route["intent"],
            "retrieval_attempted": False,
        }

    # ------------------------------------------------------------------
    # 3. Document-related: the hybrid RAG pipeline.
    # ------------------------------------------------------------------
    # For navigation and reformatting the retrieval query is the PREVIOUS
    # topic, never the literal words "next" or "make it shorter". That is what
    # stops "next" from searching for the word "next".
    effective = question
    previous = None
    if route["intent"] in (NAVIGATION, MODIFICATION):
        previous = last_exchange(history)
        if previous:
            effective = previous["question"]

    plan = understand(effective, history)
    if route["intent"] in (NAVIGATION, MODIFICATION):
        # These are context operations even when the previous question was long
        # enough not to trip the NLU's follow-up heuristic.
        plan["is_followup"] = True
        plan["route_intent"] = route["intent"]

    if route["intent"] == MODIFICATION and previous:
        # The topic and the keywords stay with the previous question, but the
        # requested FORMAT comes from the message just sent. Planning from the
        # previous question alone would drop it and re-ask for the original
        # format, so "make it shorter" would return the full-length answer.
        current = understand(question, history)
        merged = dict(plan.get("constraints") or {})
        merged.update(current.get("constraints") or {})
        if merged:
            plan["constraints"] = merged
        if current.get("question_type"):
            plan["question_type"] = current["question_type"]

    result = retrieve_chunks(
        conn, project_id, effective, uid=uid, ws_id=ws_id,
        plan=plan, history=history,
    )

    # "next" must move forward. The same topic query will rank the chunks the
    # previous answer already used at the top, so those are dropped and the
    # retrieval continues into the following material. If the document has
    # nothing further, the original set is kept rather than returning nothing.
    if route["intent"] == NAVIGATION and previous and result["chunks"]:
        seen = {
            (s.get("document"), s.get("page"))
            for s in (previous.get("sources") or [])
        }
        if seen:
            fresh = [
                c for c in result["chunks"]
                if (c.get("document"), c.get("page_number")) not in seen
            ]
            if fresh:
                result["chunks"] = fresh
                result["sources"] = [
                    {"document": c["document"], "page": c["page_number"]}
                    for c in fresh
                ]

    if not result["chunks"]:
        answer = _not_found_answer(question, effective, plan)
        mode = "none"
        sources = []
    else:
        generated = generate_answer(
            effective, result["chunks"], plan, history,
            route_intent=route["intent"],
        )
        answer = generated["answer"]
        mode = generated["mode"]
        sources = result["sources"]

    if record:
        # The user turn is saved even when nothing matched: a follow-up to a
        # question that went unanswered still has a topic to refer back to.
        save_turn(conn, project_id, uid, ws_id, "user", question)
        save_turn(conn, project_id, uid, ws_id, "assistant", answer, sources)

    return {
        "answer": answer,
        "mode": mode,
        "sources": sources,
        "matched": result["matched"],
        "query_plan": plan,
        "intent": route["intent"],
        "retrieval_attempted": True,
    }
