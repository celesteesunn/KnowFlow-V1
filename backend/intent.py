"""Intent router — decide what a user message is before any retrieval runs.

The assistant is a conversational AI that *has* RAG capabilities; RAG is one
tool it uses, not its response mechanism for every message. A user who types
"hello" or "thanks" is not asking about a document, and sending that to the
vector store both wastes retrieval and produces a nonsense "couldn't find
information" reply.

This module classifies a message into an intent so the caller knows whether to:

  * answer conversationally (greeting / gratitude / capability / smalltalk) —
    no retrieval, no embedding, no knowledge-gap entry;
  * resolve against conversation context and re-run RAG (follow-up / navigation
    / answer-modification);
  * or treat it as a genuine document question and run the hybrid pipeline.

Design notes
------------
* Not a string-equality table. Messages are normalized (case, punctuation, and
  "stretched" characters: "hiiii" / "helloo" / "heyy") and then matched against
  families of patterns, so natural variations collapse to the same intent.
* Navigation and answer-modification must FULL-match their pattern (after
  stripping leading politeness). That keeps a real question such as "what is the
  next step in the leave policy?" a document question, while a bare "next" is
  navigation.
* Conversational turns are marked so the follow-up topic extractor can skip
  them: a "hello" must never become the topic a later "who proposed it?"
  resolves against.
"""

import re

# --------------------------------------------------------------------------
# Intents
# --------------------------------------------------------------------------

GREETING = "greeting"
GRATITUDE = "gratitude"
CAPABILITY = "capability"
SMALLTALK = "smalltalk"
NAVIGATION = "navigation"
MODIFICATION = "answer_modification"
FOLLOWUP = "followup"
DOCUMENT = "document_query"

# The intents that are answered with a natural reply and never touch retrieval.
CONVERSATIONAL = {GREETING, GRATITUDE, CAPABILITY, SMALLTALK}


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

# Leading politeness only. Greeting words are NOT stripped here: "hello" and
# "ok" are meaningful intents in their own right, and removing them would turn a
# greeting into an empty message.
_POLITE_LEAD = re.compile(
    r"^\s*(?:(?:can|could|would|will|please|pls|kindly)\s+"
    r"(?:you|u|be\s+kind\s+to)?\s*)*"
)

# Collapse stretched characters: runs of 3+ of the same character become 2.
# "hiiii"->"hii", "hellooo"->"helloo", "sooo"->"soo". Two-letter runs are left
# alone so the canonical spellings below ("hii", "helloo", "heyy") match.
_STRETCH = re.compile(r"(.)\1{2,}")
_PUNCT = re.compile(r"[^a-z0-9\s']")
_WS = re.compile(r"\s+")


def normalize(text):
    """Lowercase, de-stretch, drop punctuation, strip leading politeness."""
    t = (text or "").lower().strip()
    t = t.replace("’", "'").replace("`", "'")
    t = _STRETCH.sub(r"\1\1", t)
    t = _PUNCT.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    t = _POLITE_LEAD.sub("", t).strip()
    return t


def _tokens(text):
    return [w for w in (text or "").split() if w]


# --------------------------------------------------------------------------
# Pattern families
# --------------------------------------------------------------------------
# Written with both the 1x and 2x spellings, because normalization keeps runs of
# two ("hii", "helloo", "heyy") rather than collapsing them to one.

GREETING_RE = re.compile(
    r"^(?:"
    r"hi|hii|hiii|hey|heyy|heyyy|hello|helloo|hellooo|hiya|hiyya|yo|"
    r"sup|supp|howdy|howdyy|heya|heyya|ayy|ayyy|"
    r"hey\s+there|hi\s+there|hello\s+there|heythere|hiya\s+there|"
    r"good\s+morning|good\s+afternoon|good\s+evening|good\s+day|"
    r"morning|afternoon|evening|"
    r"greetings|good\s+greetings|"
    r"hi\s+everyone|hello\s+everyone|hey\s+everyone|"
    r"anyone\s+there|anybody\s+there"
    r")$"
)

GRATITUDE_RE = re.compile(
    r"^(?:"
    r"thanks?|thank\s+you|thankyou|thank\s+u|thx|thnks|ta|cheers|"
    r"appreciate\s+it|much\s+appreciated|"
    r"ok|okay|okey|okeyy|k|kk|fine|alright|all\s+right|right|"
    r"got\s+it|got\s+that|gotcha|understood|noted|noted\s+that|"
    r"perfect|great|cool|nice|awesome|super|splendid|lovely|"
    r"sure|yes|yeah|yep|yup|yup|of\s+course|indeed|exactly|agreed|"
    r"done|that\s+makes\s+sense|makes\s+sense|good\s+to\s+know|"
    r"no\s+problem|np|my\s+pleasure|you\s+too|same|roger|acknowledged|"
    r"all\s+good|all\s+set|will\s+do|sounds\s+good"
    r")$"
)

CAPABILITY_RE = re.compile(
    r"^(?:"
    r"who\s+are\s+you|who\s+r\s+you|what\s+are\s+you|"
    r"what\s+can\s+you\s+do|what\s+could\s+you\s+do|what\s+do\s+you\s+do|"
    r"what\s+do\s+you\s+know|what\s+can\s+i\s+ask\s+you|"
    r"what\s+can\s+i\s+do|what\s+should\s+i\s+ask\s+you|"
    r"what\s+are\s+you\s+able\s+to\s+do|what\s+are\s+your\s+capabilities|"
    r"how\s+can\s+you\s+help|how\s+do\s+you\s+help|how\s+can\s+you\s+help\s+me|"
    r"how\s+do\s+you\s+work|what\s+are\s+you\s+for|"
    r"introduce\s+yourself|tell\s+me\s+about\s+yourself|"
    r"are\s+you\s+(?:a\s+)?(?:bot|robot|human|ai|chatbot|llm)|"
    r"are\s+you\s+real|what\s+kind\s+of\s+assistant\s+are\s+you"
    r")$"
)

SMALLTALK_RE = re.compile(
    r"^(?:"
    r"how\s+are\s+you|how\s+are\s+you\s+doing|how\s+are\s+you\s+today|"
    r"how\s+r\s+you|how\s+you\s+doing|how'?s\s+it\s+going|hows\s+it\s+going|"
    r"how\s+is\s+it\s+going|how\s+have\s+you\s+been|"
    r"what'?s\s+up|whats\s+up|what\s+is\s+up|"
    r"you\s+ok|you\s+alright|everything\s+ok"
    r")$"
)

# Navigation: the WHOLE message is a "continue" command. Anchored so a real
# question that merely contains "next" is not swallowed.
NAVIGATION_RE = re.compile(
    r"^(?:"
    r"next|next\s+one|next\s+ones|next\s+point|next\s+points|"
    r"next\s+topic|next\s+topics|next\s+section|next\s+sections|"
    r"next\s+part|next\s+page|next\s+chapter|next\s+step|next\s+steps|"
    r"next\s+please|what'?s\s+next|whats\s+next|what\s+is\s+next|"
    r"what\s+comes\s+next|then\s+what|"
    r"continue|continuing|please\s+continue|go\s+on|carry\s+on|"
    r"keep\s+going|move\s+on|proceed|resume|"
    r"anything\s+else|anything\s+more|more|"
    r"and\s+then|and\s+after\s+that|"
    r"tell\s+me\s+more|elaborate"
    r")$"
)

# "give 5 points", "in 3 bullet points", "list the main reasons", ...
_COUNT_NOUNS = (
    r"points?|bullet\s+points?|reasons?|ways?|steps?|items?|examples?|"
    r"ideas?|features?|advantages?|disadvantages?|things?"
)
_COUNT_NUM = r"(?:\d+|two|three|four|five|six|seven|eight|nine|ten)"
# Adjective that may sit between the count and the noun: "3 KEY points".
_COUNT_ADJ = r"(?:(?:key|main|important|top|bullet|big)\s+)?"

# Answer modification: reformat the PREVIOUS answer, not a fresh search.
MODIFICATION_RE = re.compile(
    r"^(?:"
    r"make\s+(?:it|this|that|the\s+answer|the\s+last\s+answer)?\s*"
    r"(?:shorter|short|simpler|simple|brief|concise|detailed|"
    r"longer|clearer|clear|easy\s+to\s+read|shorter\s+and\s+simpler)"
    r"|shorter|shorten|make\s+shorter|"
    r"simpler|simplify|make\s+simpler|explain\s+simply|explain\s+simple|"
    r"in\s+simple\s+words|in\s+simple\s+language|in\s+plain\s+english|"
    r"in\s+layman(?:'s)?\s+terms|"
    r"brief|briefly|be\s+brief|concise|concisely|"
    r"longer|lengthen|expand|elaborate\s+on\s+(?:it|that|this)|"
    r"in\s+detail|in\s+depth|more\s+detail|more\s+details|"
    r"detail\s+it\s+up|explain\s+in\s+detail|go\s+deeper|"
    # a count request: "give 5 points", "in 3 bullet points", "5 key points"
    r"(?:give|list|write|show|tell)(?:\s+me)?\s+" + _COUNT_NUM +
    r"\s+" + _COUNT_ADJ + _COUNT_NOUNS + r"|"
    r"in\s+" + _COUNT_NUM + r"\s+" + _COUNT_ADJ + _COUNT_NOUNS + r"|"
    r"\d+\s*" + _COUNT_ADJ + _COUNT_NOUNS + r"|"
    r"in\s+bullet\s+points?|as\s+bullet\s+points?|bullet\s+points?|"
    r"step\s+by\s+step|"
    r"exam[\s-]?ready|make\s+it\s+exam[\s-]?ready|for\s+(?:my\s+)?exam|"
    r"rephrase|rewrite|reword|reword\s+it|put\s+it\s+(?:in\s+)?"
    r"(?:a\s+)?table|as\s+a\s+table|one\s+line|in\s+one\s+line|"
    r"tl\s*dr|tldr|"
    r"in\s+a\s+nutshell|in\s+brief"
    r")$"
)

# "summarise this" is a reformat only when we have actually answered
# something; with no history it is an ordinary document question.
_SOFT_SUMMARIZE_RE = re.compile(
    r"^(?:summari[sz]e\s+(?:it|this|that)|recap\s+(?:it|this|that))$"
)


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

def _match(rx, norm):
    return bool(rx.match(norm)) if norm else False


def classify(text, has_history=False):
    """Classify a user message.

    Returns a dict:
      {
        "intent":         one of the intent constants,
        "conversational": True when retrieval must NOT run,
        "needs_context":  True when the previous conversation matters
                          (follow-up / navigation / modification),
        "normalized":     the normalized message (internal, for tests/debug),
      }
    """
    norm = normalize(text)
    result = {
        "intent": DOCUMENT,
        "conversational": False,
        "needs_context": False,
        "normalized": norm,
    }
    if not norm:
        # An empty/emoji-only message is conversational, not a document query.
        result["intent"] = SMALLTALK
        result["conversational"] = True
        return result

    # Order matters: conversational first (never retrieve), then
    # navigation/modification (context, not literal search), then follow-up,
    # then a genuine document question.
    if _match(GREETING_RE, norm):
        result.update(intent=GREETING, conversational=True)
    elif _match(GRATITUDE_RE, norm):
        result.update(intent=GRATITUDE, conversational=True)
    elif _match(CAPABILITY_RE, norm):
        result.update(intent=CAPABILITY, conversational=True)
    elif _match(SMALLTALK_RE, norm):
        result.update(intent=SMALLTALK, conversational=True)
    elif _match(NAVIGATION_RE, norm):
        result.update(intent=NAVIGATION, needs_context=True)
    elif _match(MODIFICATION_RE, norm) or (
        has_history and _match(_SOFT_SUMMARIZE_RE, norm)
    ):
        result.update(intent=MODIFICATION, needs_context=True)
    else:
        # Everything else is a document question; the NLU decides separately
        # whether it leans on prior context (follow-up).
        result.update(intent=DOCUMENT, needs_context=False)

    return result


def is_conversational(text, has_history=False):
    return classify(text, has_history)["conversational"]


def is_topical(text, has_history=False):
    """True when the message is a real question worth retrieving on.

    Greetings, thanks, "who are you" and bare navigation or reformat commands
    ("next", "make it shorter") are all *about the conversation*, not about a
    document, so none of them can be the topic that a later follow-up resolves
    against. Only a document question can anchor the topic.
    """
    return classify(text, has_history)["intent"] == DOCUMENT


# --------------------------------------------------------------------------
# Conversational replies
# --------------------------------------------------------------------------
# Deterministic, so the assistant behaves identically offline and without a
# latency or cost cliff on every "hi". None of these read a document, so they
# carry no sources.

_CAPABILITY_ANSWER = (
    "I can help you find, understand and summarise information from the "
    "documents you have access to in your KnowFlow workspace.\n\n"
    "Ask me a question about your documents and I will search them, then "
    "answer with the page I used. I also remember this conversation, so you "
    "can follow up with things like \"explain the second one\" or \"make it "
    "shorter\"."
)


def _greeting_reply(norm, has_history):
    if "morning" in norm:
        return "Good morning! How can I help you?"
    if "afternoon" in norm:
        return "Good afternoon! How can I help you?"
    if "evening" in norm:
        return "Good evening! How can I help you?"
    if has_history:
        return "Hello! How can I help you with your documents?"
    return "Hello! How can I help you?"


def _gratitude_reply(norm):
    if norm in {"ok", "okay", "okey", "k", "kk", "fine", "alright",
                "all right", "right", "good", "cool", "nice"}:
        return "Great! Ask me anything about your documents."
    if "welcome" in norm or "pleasure" in norm:
        return "Happy to help!"
    if "no problem" in norm or "np" in norm:
        return "No problem at all."
    return "You're welcome! Let me know if you need anything else."


def _smalltalk_reply():
    return (
        "I'm doing well, thanks for asking! I'm ready to help you find "
        "information in your documents."
    )


def build_reply(route, has_history=False):
    """Natural reply for a conversational intent.

    Returns None for intents that must go through retrieval instead.
    """
    intent = route.get("intent")
    norm = route.get("normalized") or ""
    if intent == GREETING:
        return _greeting_reply(norm, has_history)
    if intent == GRATITUDE:
        return _gratitude_reply(norm)
    if intent == CAPABILITY:
        return _CAPABILITY_ANSWER
    if intent == SMALLTALK:
        return _smalltalk_reply()
    return None


# A navigation or reformat request only makes sense once something has been
# answered; with an empty conversation it is a prompt for a real question
# rather than a document search for the word "next".
NO_CONTEXT_REPLY = (
    "Tell me what you'd like to know about your documents and I'll take it "
    "from there."
)
