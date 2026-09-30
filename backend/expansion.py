"""Query expansion — turn one question into several retrieval probes.

A single question rarely uses the same words as the document. "How did
management theories change over time?" has to reach a section headed
"Evolution of Management" that never says "how did ... change over time".

The expansion here is deterministic and derives from the structured query
understanding in nlu.py, so it works offline and never leaks the expanded
terms into the UI. Three kinds of probe are produced:

    {"terms": [...], "phrases": [...], "questions": [...]}

- terms:     stemmed single words, used for keyword scoring
- phrases:   multi-word spans worth matching as a unit
- questions: natural-language restatements, each embedded for semantic search
"""

import re

from nlu import STYLE_WORDS, _tokens
from search import stem

# Domain-agnostic synonym groups. These are deliberately conservative: each
# pair is a genuine lexical equivalence, not a topical guess. They exist so
# "evolve"/"evolution" and "functions"/"primary functions" collapse together
# instead of being counted twice against a phrase bonus.
SYNONYM_GROUPS = [
    {"function", "functions", "primary", "main", "key", "role", "responsibility",
     "responsibilities", "purpose", "objective", "objectives"},
    {"evolve", "evolution", "develop", "development", "change", "changed",
     "changing", "progress", "progression", "history", "shift", "era", "eras",
     "stage", "stages", "period", "periods"},
    {"principle", "principles", "rule", "rules", "guideline", "guidelines",
     "standard", "standards"},
    {"propose", "proposed", "proposer", "introduced", "introduce", "developed",
     "develop", "created", "create", "authored", "by", "father", "founder"},
    {"important", "importance", "significant", "significance", "key", "critical",
     "essential", "main", "major", "significant"},
    {"difference", "differences", "differ", "contrast", "compare",
     "comparison", "versus", "distinguish", "similarity", "similar"},
    {"example", "examples", "instance", "instances", "illustration",
     "illustrations", "sample", "samples"},
    {"explain", "explanation", "describe", "description", "meaning", "define",
     "definition", "concept", "overview", "summary"},
    {"company", "organisation", "organization", "firm", "business", "employer",
     "entity"},
    {"employee", "employees", "staff", "worker", "workers", "personnel",
     "workforce"},
    {"problem", "problems", "issue", "issues", "challenge", "challenges",
     "difficulty", "difficulties"},
    {"method", "methods", "technique", "techniques", "approach", "approaches",
     "way", "ways", "process", "processes"},
    {"result", "results", "outcome", "outcomes", "effect", "effects",
     "impact", "consequence", "consequences"},
    {"cost", "costs", "price", "expense", "expenses", "budget"},
    {"time", "timing", "duration", "period", "deadline", "schedule"},
    {"goal", "goals", "target", "targets", "aim", "aims", "objective"},
    {"type", "types", "kind", "kinds", "category", "categories", "classification"},
    {"step", "steps", "procedure", "process", "stage", "method"},
]

# Reverse index: stemmed word -> set of stemmed words it may substitute for.
_SYNONYM_INDEX = {}
for _group in SYNONYM_GROUPS:
    _members = {stem(w) for w in _group}
    for _w in _members:
        _SYNONYM_INDEX.setdefault(_w, set()).update(_members - {_w})

# Question-type phrasing used to build semantic probes. Each intent gets a
# short declarative restatement, which embeds closer to expository document
# prose than an interrogative does.
_INTENT_PROBE = {
    "definition": "definition and meaning of {topic}",
    "explanation": "explanation and description of {topic}",
    "summary": "summary and overview of {topic}",
    "list": "key points and main aspects of {topic}",
    "comparison": "differences and comparison between {topic}",
    "factual_lookup": "facts about {topic}",
    "factual_question": "information about {topic}",
}

# Phrases that are often a heading in a document even though they are phrased
# as a question fragment.
_PHRASE_STOP_HEAD = re.compile(
    r"^\s*(?:what|who|when|where|why|how|which|is|are|was|were|do|does|did|"
    r"the|a|an|of|in|on|for|and|or|to|me|about|explain|describe|define|"
    r"compare|summar(?:y|ise|ize)|give|show|list|please)\b\s*",
    re.IGNORECASE,
)


def _synonyms_for(word):
    """Stemmed synonyms of a single stemmed word (excluding itself)."""
    return sorted(_SYNONYM_INDEX.get(word, ()))


def _content_words(text):
    return [
        t for t in _tokens(text)
        if t not in STYLE_WORDS and len(t) > 2
    ]


def _phrases_from(text, max_len=4):
    """Multi-word spans from the text worth matching as a unit.

    Contiguous runs of content words become candidate phrases; the longest
    runs are kept first because they are the most specific.
    """
    words = _tokens(text)
    content_positions = [
        i for i, w in enumerate(words)
        if w not in STYLE_WORDS and len(w) > 2
    ]
    if not content_positions:
        return []

    # Group positions that are adjacent or separated only by a style word.
    groups, current = [], [content_positions[0]]
    for pos in content_positions[1:]:
        if pos - current[-1] <= 2:
            current.append(pos)
        else:
            groups.append(current)
            current = [pos]
    groups.append(current)

    phrases = []
    for group in groups:
        # Slide a window over the group to build the useful spans.
        for size in range(min(max_len, len(group)), 1, -1):
            for start in range(0, len(group) - size + 1):
                span = group[start:start + size]
                phrase = " ".join(words[span[0]:span[-1] + 1])
                phrase = _PHRASE_STOP_HEAD.sub("", phrase).strip()
                if len(_tokens(phrase)) >= 2 and phrase not in phrases:
                    phrases.append(phrase)
    return phrases


def expand(query_plan):
    """Build retrieval probes from a query-understanding dict.

    Returns {"terms", "phrases", "questions", "expanded"} where:
      terms     stemmed single words (originals + synonyms)
      phrases   multi-word spans, longest first
      questions natural-language probes for the semantic index
    """
    topic = (query_plan.get("topic") or query_plan.get("raw") or "").strip()
    if not topic:
        return {"terms": [], "phrases": [], "questions": [], "expanded": []}

    base_words = _content_words(topic)
    base_stems = []
    for w in base_words:
        s = stem(w)
        if s not in base_stems:
            base_stems.append(s)

    # Terms: the question's own words, then synonyms of each.
    terms = list(base_stems)
    for s in base_stems:
        for syn in _synonyms_for(s):
            if syn not in terms:
                terms.append(syn)

    # Entities are strong retrieval anchors, so they are always included.
    for ent in query_plan.get("entities") or []:
        for w in _content_words(ent):
            s = stem(w)
            if s not in terms:
                terms.append(s)

    # Phrases: the topic, then the spans inside it.
    phrases = []
    if len(_tokens(topic)) >= 2:
        phrases.append(topic)
    phrases.extend(_phrases_from(topic))

    # Sub-questions each become their own probe, so a multi-part question
    # retrieves evidence for every part rather than only the first.
    questions = []
    intent = query_plan.get("intent") or "factual_question"
    template = _INTENT_PROBE.get(intent, _INTENT_PROBE["factual_question"])

    for sub in query_plan.get("sub_questions") or []:
        sub_topic = _strip_instruction(sub)
        if sub_topic:
            questions.append(sub_topic)
            questions.append(template.format(topic=sub_topic))

    if topic not in questions:
        questions.append(topic)
    questions.append(template.format(topic=topic))

    # Constraints change the shape of the evidence we want, so a "compare"
    # question also probes for each side of the comparison.
    if intent == "comparison":
        for ent in query_plan.get("entities") or []:
            questions.append(ent)

    if query_plan.get("previous_topic") and query_plan.get("is_followup"):
        questions.insert(0, query_plan["previous_topic"])

    # Deduplicate, keep order.
    seen, unique_q = set(), []
    for q in questions:
        k = q.lower().strip()
        if k and k not in seen:
            seen.add(k)
            unique_q.append(q.strip())

    return {
        "terms": terms,
        "phrases": phrases[:8],
        "questions": unique_q[:8],
        "expanded": _describe(terms, phrases, unique_q),
    }


def _strip_instruction(text):
    """Reduce a sub-question to its subject, for use as a retrieval probe."""
    t = (text or "").strip().rstrip("?.! ")
    t = re.sub(
        r"^\s*(?:please\s+)?(?:can\s+you\s+|could\s+you\s+)?"
        r"(?:tell\s+me\s+about|explain\s+to\s+me\s+about)?",
        "",
        t, flags=re.IGNORECASE,
    )
    t = re.sub(
        r"^\s*(?:what|who|when|where|why|how|which)\s+"
        r"(?:is|are|was|were|do|does|did|of|in|about|the|a|an)?\s*",
        "", t, flags=re.IGNORECASE,
    )
    t = re.sub(
        r"^\s*(?:explain|describe|define|summar(?:y|ise|ize)|compare|outline|"
        r"list|give|show|write)\s+", "", t, flags=re.IGNORECASE,
    )
    return t.strip(" ,;:-")


def _describe(terms, phrases, questions):
    """Short internal description, used for logging and tests only.

    This is never shown to the user.
    """
    return {
        "term_count": len(terms),
        "phrase_count": len(phrases),
        "question_count": len(questions),
        "sample_terms": terms[:10],
        "sample_phrases": phrases[:5],
    }
