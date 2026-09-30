"""Query understanding — turn a raw user question into a structured plan.

The goal is to stop sending the raw string straight into a keyword lookup and
instead work out what the user actually wants before anything is retrieved:

    {"topic": "evolution of management", "intent": "explanation",
     "question_type": "how", "entities": [...], "keywords": [...],
     "constraints": {"simple": True, "points": 5}, "sub_questions": [...]}

Everything here is deterministic (no LLM call) so the pipeline works offline
and behaves identically on every run. The result is what the retriever, the
reranker and the answer generator all read from, which is also what keeps
them consistent with each other.
"""

import re

# --------------------------------------------------------------------------
# Constraint phrases -> flags the answer generator acts on
# --------------------------------------------------------------------------

CONSTRAINT_PATTERNS = [
    # simple / plain language
    ("simple", r"\b(in\s+)?simple\s+words?\b|\bsimpl(?:e|er|ify|ified)\b|\bsimply\b|\bplain\s+english\b|\bplain\s+language\b|\b(?:in\s+)?layman(?:'s)?\s+terms\b|\beasy\s+to\s+(?:understand|read)\b|\bfor\s+beginners?\b|\beli5\b|\bin\s+a\s+simple\s+way\b"),
    # detail / elaboration
    ("detailed", r"\bin\s+(?:great\s+)?detail\b|\bdetail(?:ed|s)?\b|\belaborate\b|\bthorough(?:ly)?\b|\bcomprehensive(?:ly)?\b|\bin\s+depth\b|\bexplain\s+more\b|\bgo\s+deeper\b|\blonger\b|\bexpand\b"),
    # brevity
    # The comparative forms matter here: "make it shorter" has to set `short`,
    # otherwise a reformat request silently returns the original length.
    ("short", r"\bbrief(?:ly)?\b|\bshort(?:er|ly|en)?\b|\bconcise(?:ly)?\b|\btl;?dr\b|\bin\s+short\b|\bsummar(?:y|ise|ize)\b|\bquick(?:ly)?\b|\bbriefly\b"),
    # exam / academic register
    ("exam", r"\bexam[\s-]?ready\b|\bfor\s+(?:my\s+)?exam\b|\bexam\s+answer\b|\baccording\s+to\s+the\s+syllabus\b|\bnotes?\s+for\s+exam\b"),
    # structural requests
    ("examples", r"\bexample(?:s)?\b|\billustrat(?:e|ed|ion)\b|\bwith\s+examples\b"),
    ("steps", r"\bstep[\s-]?by[\s-]?step\b|\bstages?\b|\bprocedure\b|\bhow\s+to\b"),
    ("list", r"\bin\s+(?:a\s+)?list\b|\bbullet\s+points?\b|\benumerat\w*\b|\bpoints?\b"),
    ("compare", r"\bcompare\b|\bcomparison\b|\bversus\b|\bvs\.?\b|\bdifference(?:s)?\s+between\b|\bdistinguish\b|\bversus\b"),
    ("summary", r"\bsummar(?:y|ise|ize|ise)\w*\b|\boverview\b|\bin\s+a\s+nutshell\b|\brecap\b|\btl;?dr\b"),
    ("definition", r"\bwhat\s+(?:is|are|was|were)\b|\bdefine\b|\bdefinition\b|\bmeaning\s+of\b"),
    ("only_important", r"\bonly\s+(?:the\s+)?(?:important|main|key|essential)\b|\bmain\s+points?\b|\bkey\s+points?\b|\bhighlight\w*\b"),
]

# "in 5 points", "in three bullet points", "top 3 reasons"
_COUNT_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
}
_COUNT_RE = re.compile(
    r"\b(?:in|into|as|give|list|write)\s+"
    r"(?:(?:about|around|approximately|roughly)\s+)?"
    r"(\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)\s*"
    r"(?:\w+\s+){0,2}?(?:points?|bullets?|reasons?|ways?|steps?|items?|"
    r"examples?|ideas?|differences?|features?|advantages?|disadvantages?)\b",
    re.IGNORECASE,
)

# Words that only steer presentation and must never be treated as topic.
STYLE_WORDS = {
    "explain", "describe", "tell", "give", "show", "list", "write", "summarize",
    "summarise", "compare", "define", "outline", "elaborate", "detail",
    "detailed", "brief", "short", "simple", "simply", "points", "point",
    "bullet", "bullets", "words", "word", "example", "examples", "step",
    "steps", "way", "ways", "please", "could", "would", "can", "you", "me",
    "my", "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "is",
    "are", "was", "were", "do", "does", "did", "about", "with", "from", "that",
    "this", "these", "those", "it", "its", "they", "them", "there", "here",
    "make", "made", "shorter", "longer", "simpler", "again", "more", "less",
    "top", "main", "important", "key", "essential", "highlight", "note",
    "notes", "exam", "ready", "chapter", "section", "document", "uploaded",
    "content", "according", "based", "knowflow", "assistant", "understand",
    "want", "need", "like", "tell me", "explain to me",
}

# Phrases that signal a follow-up needing the previous turn's topic resolved.
FOLLOWUP_RE = re.compile(
    r"^\s*(?:and\s+)?(?:what|who|when|where|why|how|which|tell|explain|"
    r"describe|define|give|list|show|provide|summari[sz]e|compare|expand|"
    r"elaborate|continue|more)\b",
    re.IGNORECASE,
)

# Pronouns/deixis that only make sense with prior context.
ANAPHORA_RE = re.compile(
    r"\b(it|its|it's|they|their|them|this|that|these|those|the same|"
    r"the second|the first|the third|he|she|him|her|the other one|"
    r"the previous one|above|earlier|previously)\b",
    re.IGNORECASE,
)

# Interrogative opening -> question type.
QUESTION_TYPE_RULES = [
    ("who", re.compile(r"^\s*who\b|\bwho\s+(?:is|are|was|were|proposed|"
                       r"developed|introduced|created|founded|said|wrote|"
                       r"defined|discovered)\b", re.I)),
    ("when", re.compile(r"^\s*when\b|\bwhat\s+year\b|\bwhich\s+year\b", re.I)),
    ("where", re.compile(r"^\s*where\b", re.I)),
    ("why", re.compile(r"^\s*why\b|\breason(?:s)?\s+(?:for|behind|why)\b", re.I)),
    ("how", re.compile(r"^\s*how\b|\bhow\s+did\b|\bhow\s+do(?:es)?\b|"
                       r"\bhow\s+has\b|\bhow\s+can\b", re.I)),
    ("comparison", re.compile(r"\bcompare\b|\bcomparison\b|\bdifference(?:s)?\s+between\b|"
                              r"\bdistinguish\b|\bversus\b|\bvs\.?\b", re.I)),
    ("summary", re.compile(r"\bsummar(?:y|ise|ize)\w*\b|\boverview\b|"
                           r"\bin\s+a\s+nutshell\b|\brecap\b|\btl;?dr\b", re.I)),
    ("definition", re.compile(r"^\s*what\s+(?:is|are|was|were)\b|"
                              r"\bdefine\b|\bdefinition\s+of\b|\bmeaning\s+of\b", re.I)),
    ("list", re.compile(r"^\s*(?:what|which)\s+are\s+the\b|\blist\b|"
                        r"\bname\s+the\b|\benumerate\b|\bwhat\s+are\s+\w+\s+of\b", re.I)),
    ("explanation", re.compile(r"^\s*explain\b|\bexplain\s+(?:this|that|it|how|why|what)\b|"
                               r"\bwhat\s+do(?:es)?\s+\w+\s+mean\b|\belaborate\b", re.I)),
]
DEFAULT_QUESTION_TYPE = "what"

# Sub-question splits for multi-part questions.
_SPLIT_RE = re.compile(
    r"\s*(?:\?|;|\band\s+(?:also\s+)?(?:what|who|when|where|why|how|which)\b|"
    r"\bplus\b|\balso\b)\s*",
    re.IGNORECASE,
)

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'\-]*", re.IGNORECASE)


def _tokens(text):
    return [t.lower() for t in _WORD_RE.findall(text or "")]


def _strip_constraint_phrases(text, patterns):
    """Remove constraint phrases so they don't pollute the topic string."""
    out = text
    # The count phrase must be removed first: it ends in a word like "points"
    # that a later pattern ("only the main points") would strip on its own,
    # leaving a dangling number behind.
    out = _COUNT_RE.sub(" ", out)
    for _flag, pattern in patterns:
        out = re.sub(pattern, " ", out, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", out).strip()


def _clean_topic(text):
    """Reduce a question to the noun phrase it is about."""
    t = text.strip().rstrip("?.! ")
    # Leading interrogatives and polite fillers.
    t = re.sub(
        r"^\s*(?:please\s+)?(?:can\s+you\s+|could\s+you\s+|would\s+you\s+)?"
        r"(?:tell\s+me\s+about|explain\s+to\s+me\s+about|tell\s+me\s+)?",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"^\s*(?:what|who|when|where|why|how|which)\s+(?:is|are|was|were|do|does|did|"
        r"of|in|about|the|a|an)?\s*",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"^\s*(?:explain|describe|define|summar(?:y|ise|ize)|compare|outline|"
        r"list|give|show|write|elaborate)\s+",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"^(?:me\s+about|about|on)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(
        r"\b(?:in|from|per|of)\s+(?:the\s+)?(?:uploaded\s+)?"
        r"(?:document|documents|docx|pdf|file|files|text|chapter|content)\b",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s{2,}", " ", t).strip(" ,;:-")


def detect_question_type(text):
    for name, pattern in QUESTION_TYPE_RULES:
        if pattern.search(text or ""):
            return name
    return DEFAULT_QUESTION_TYPE


def detect_constraints(text):
    """Return the instruction flags and requested point count, if any."""
    flags = {}
    for flag, pattern in CONSTRAINT_PATTERNS:
        if re.search(pattern, text or "", flags=re.IGNORECASE):
            flags[flag] = True

    m = _COUNT_RE.search(text or "")
    if m:
        raw = m.group(1).lower()
        flags["points"] = _COUNT_WORDS.get(raw) or int(raw)
    return flags


def extract_entities(text):
    """Capitalised phrases that are likely proper nouns / named concepts.

    Sentence-initial words are excluded so a question starting with "Who
    proposed..." does not yield "Who" as an entity.
    """
    out = []
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9'\-]*(?:\s+[A-Z][A-Za-z0-9'\-]*)*)", text or ""):
        phrase = m.group(1).strip()
        if not phrase:
            continue
        if m.start() == 0:
            # Sentence-initial: drop the leading capital's first word only
            # when it is a common function word.
            first = phrase.split()[0].lower()
            if first in {
                "what", "who", "when", "where", "why", "how", "which",
                "explain", "describe", "compare", "summarize", "summarise",
                "define", "list", "give", "show", "tell", "please", "can",
                "could", "would", "the", "a", "an", "is", "are", "in", "of",
            }:
                rest = phrase.split()[1:]
                if not rest:
                    continue
                phrase = " ".join(rest)
            else:
                continue
        low = phrase.lower()
        if low in STYLE_WORDS or len(phrase) < 3:
            continue
        if low not in [o.lower() for o in out]:
            out.append(phrase)
    return out


def is_followup(text, has_history):
    """True when the question cannot be understood without prior turns."""
    if not has_history:
        return False
    t = (text or "").strip()
    if len(_tokens(t)) <= 6 and ANAPHORA_RE.search(t):
        return True
    # Almost contentless short turn that leans on the topic.
    if len(_tokens(t)) <= 4 and FOLLOWUP_RE.match(t):
        return True
    # "Explain that in simple words" / "make it shorter" style.
    if ANAPHORA_RE.search(t) and len(_tokens(t)) <= 8:
        return True
    return False


def split_sub_questions(text):
    """Split a multi-part question into its individual questions."""
    parts = [p.strip(" ?.!,;") for p in _SPLIT_RE.split(text or "")]
    parts = [p for p in parts if len(_tokens(p)) >= 2]
    # Preserve order, drop duplicates.
    seen, out = set(), []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def understand(question, history=None):
    """Structured analysis of a user question.

    history: optional list of prior turns (dicts with role/content, oldest
    first). Only used to decide whether this is a follow-up and to carry a
    previous topic forward; never to widen what the user can retrieve.
    """
    q = (question or "").strip()
    history = history or []
    prior_user = [
        h.get("content", "") for h in history if h.get("role") == "user"
    ]
    has_history = bool(prior_user)

    question_type = detect_question_type(q)
    constraints = detect_constraints(q)

    # Topic: strip the instruction words so the topic is the subject matter.
    topic = _clean_topic(_strip_constraint_phrases(q, CONSTRAINT_PATTERNS))
    if not topic:
        topic = _clean_topic(q)
    if not topic:
        topic = q

    # Follow-up: the question leans on the previous turn, so the previous
    # topic becomes this question's topic too.
    followup = is_followup(q, has_history)
    previous_topic = ""
    if has_history:
        for prev in reversed(prior_user):
            # Only a real document question can be a topic. A greeting, a
            # "thanks", or a bare navigation/reformat command ("next", "make
            # it shorter") is about the conversation, not about a document.
            # Without this, "hello" then "who proposed it?" would resolve
            # against "hello", and "next" would poison the topic of the
            # following turn.
            from intent import is_topical

            if not is_topical(prev, has_history=True):
                continue
            candidate = _clean_topic(
                _strip_constraint_phrases(prev, CONSTRAINT_PATTERNS)
            )
            if candidate:
                previous_topic = candidate
                break
    if followup and previous_topic and len(_tokens(topic)) <= 4:
        topic = f"{previous_topic} {topic}".strip()

    entities = extract_entities(q)
    if followup and previous_topic:
        for e in extract_entities(previous_topic):
            if e not in entities:
                entities.append(e)

    # Keywords: content words, de-duplicated, minus the instruction words.
    keywords = []
    for t in _tokens(topic):
        if t in STYLE_WORDS or len(t) < 3:
            continue
        if t not in keywords:
            keywords.append(t)

    sub_questions = split_sub_questions(q)

    return {
        "raw": q,
        "topic": topic,
        "previous_topic": previous_topic,
        "is_followup": followup,
        "intent": _intent_for(question_type, constraints),
        "question_type": question_type,
        "entities": entities,
        "keywords": keywords,
        "constraints": constraints,
        "sub_questions": sub_questions,
        "has_history": has_history,
    }


def _intent_for(question_type, constraints):
    """Coarse intent label used by the reranker and the answer prompt."""
    if "compare" in constraints or question_type == "comparison":
        return "comparison"
    if question_type == "summary" or "summary" in constraints:
        return "summary"
    if question_type in ("who", "when", "where"):
        return "factual_lookup"
    if question_type in ("why", "how"):
        return "explanation"
    if question_type == "list":
        return "list"
    if question_type == "explanation" or "detailed" in constraints:
        return "explanation"
    if "definition" in constraints or question_type == "definition":
        return "definition"
    return "factual_question"
