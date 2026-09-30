"""Bounded conversation memory for the assistant.

Follow-up questions are the ordinary case in a document assistant: "who
proposed it?", "what are its main points?". They cannot be answered by
retrieving on the question text alone, because the question contains no topic.
So the previous turns have to be available — but only just enough of them.

Two rules govern what is kept:

  1. History is scoped to one project and one user. A question in project A
     can never be resolved against a topic discussed in project B, and a
     shared user id can never read another user's conversation.
  2. History is bounded twice over — by turn count and by character budget —
     and trimmed from the oldest end. The most recent turns are the ones that
     carry the referent, and an unbounded transcript would eventually push the
     retrieved evidence out of the model's context.

Storage is per turn, not per session: a returning user in a new tab still gets
a follow-up resolved against what they just asked.
"""

import json

from config import RAG_HISTORY_MAX_CHARS, RAG_HISTORY_TURNS


def save_turn(conn, project_id, user_id, workspace_id, role, content,
              sources=None):
    """Record one user or assistant turn.

    sources is the list of {document, page} dicts the answer was grounded in.
    It is stored so a later turn can tell which documents the conversation was
    actually about, which is a more reliable referent than re-reading the
    question text.
    """
    if role not in ("user", "assistant"):
        raise ValueError("role must be 'user' or 'assistant'")
    payload = json.dumps(sources or []) if sources else ""
    conn.execute(
        """
        INSERT INTO chat_messages
            (project_id, user_id, workspace_id, role, content, sources)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_id, user_id, workspace_id, role, (content or "")[:8000], payload),
    )


def load_history(conn, project_id, user_id, turns=None,
                 max_chars=None):
    """Return the most recent turns for this project and user, oldest first.

    Turns are read newest-first with a hard LIMIT, then trimmed by character
    budget from the oldest end, so the cost of loading history does not grow
    with how long the conversation has been going.
    """
    turns = turns if turns is not None else RAG_HISTORY_TURNS
    max_chars = max_chars if max_chars is not None else RAG_HISTORY_MAX_CHARS

    rows = conn.execute(
        """
        SELECT role, content, sources FROM chat_messages
        WHERE project_id = ? AND user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (project_id, user_id, max(1, turns) * 2),
    ).fetchall()

    history = []
    budget = max_chars
    for row in rows:
        content = (row["content"] or "").strip()
        if not content:
            continue
        # A turn longer than the whole budget would starve every earlier turn,
        # so it is clipped rather than dropped: it is usually the current one.
        if len(content) > budget:
            content = content[:budget]
        budget -= len(content)
        entry = {"role": row["role"], "content": content}
        if row["sources"]:
            try:
                entry["sources"] = json.loads(row["sources"])
            except (ValueError, TypeError):
                entry["sources"] = []
        history.append(entry)
        if budget <= 0:
            break

    history.reverse()
    return history


def clear_history(conn, project_id, user_id):
    """Drop a project's conversation for one user."""
    conn.execute(
        "DELETE FROM chat_messages WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    )


def last_exchange(history):
    """The most recent question that was actually answered from documents.

    Used by the intent router so "next" and "make it shorter" act on what was
    just discussed instead of starting an unrelated search. Returns
    {"question", "answer", "sources"}, or None when no exchange has been
    answered from documents yet.

    The scan runs forwards, pairing each grounded answer with the question that
    actually produced it, because the most recent user message and the most
    recent answer are often *not* a pair. Three cases make that mismatch normal:

      * a navigation answer ("next") is grounded but follows a user turn that is
        not a topic, so it continues an earlier question;
      * a "couldn't find information" answer read no documents, so the question
        that produced it is a dead end and the real topic is further back;
      * a greeting or "thanks" is not a topic at all.

    A user turn only becomes the pending question when it is topical, and an
    answer only becomes the current exchange when it is grounded in sources.
    A navigation answer that has no pending question of its own therefore
    inherits the question of the exchange it is continuing, while still
    replacing that exchange's answer — which is exactly what "tell me the next
    point" and then "make it shorter" should do.
    """
    from intent import is_conversational, is_topical

    pending = None   # latest topical question, not yet answered
    current = None   # latest grounded exchange

    for turn in history or []:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        role = turn.get("role")

        if role == "user":
            if is_topical(content, has_history=True):
                pending = content
            continue

        if role != "assistant":
            continue
        if is_conversational(content, has_history=True):
            continue
        if not (turn.get("sources") or []):
            # Nothing was found, so this question is a dead end.
            pending = None
            continue

        if pending:
            current = {"question": pending, "answer": content}
        elif current:
            # A continuation of the exchange already in hand: keep its topic,
            # take the newer answer.
            current = {"question": current["question"], "answer": content}
        else:
            continue
        current["sources"] = turn.get("sources") or []
        pending = None

    return current


def format_for_prompt(history, max_chars=None):
    """Render history as a short transcript for the model prompt.

    Only user turns are quoted as questions; the assistant's own answers are
    summarised by the documents they cited, which keeps the prompt small and
    stops the model from simply restating its previous answer as if it were
    evidence.
    """
    max_chars = max_chars if max_chars is not None else RAG_HISTORY_MAX_CHARS
    lines = []
    used = 0
    for turn in history:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if turn.get("role") == "user":
            line = f"User asked earlier: {content}"
        else:
            docs = sorted({
                s.get("document", "")
                for s in (turn.get("sources") or [])
                if isinstance(s, dict) and s.get("document")
            })
            if not docs:
                continue
            pages = sorted({
                s.get("page")
                for s in (turn.get("sources") or [])
                if isinstance(s, dict) and s.get("page")
            })
            page_str = ", ".join(str(p) for p in pages if p)
            line = f"(A previous answer used: {', '.join(docs)}"
            line += f", page {page_str})" if page_str else ")"
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def referenced_documents(history):
    """Documents cited by the most recent assistant turns.

    Used as a weak retrieval hint: if the user follows up with "and its
    drawbacks?" the same document is very likely still relevant, so its chunks
    are given a small ranking boost rather than being re-ranked from scratch.
    """
    docs = []
    for turn in reversed(history):
        if turn.get("role") != "assistant":
            continue
        for src in turn.get("sources") or []:
            if isinstance(src, dict):
                name = src.get("document")
                if name and name not in docs:
                    docs.append(name)
        if len(docs) >= 3:
            break
    return docs
