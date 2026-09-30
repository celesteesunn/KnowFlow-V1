"""Structure-aware chunking for RAG.

The previous splitter cut a page into fixed-size overlapping windows with no
idea what surrounded them, so a retrieved chunk could be half a sentence with
no indication of which section it belonged to. That is what made answers feel
contextless.

This splitter keeps the document's own structure:

    Document > section (heading path) > heading > block (prose/list) > chunk

Every emitted chunk carries:
  - text        the passage, prefixed with its heading path so the passage is
                self-describing when read on its own
  - section     the full heading path ("Evolution of Management > Classical")
  - heading     the nearest heading above the chunk
  - kind        prose | list | table
  - page_number inherited from the source page

Blocks are kept whole where possible and only split when a single block is
larger than the target, in which case it is split on sentence boundaries with
overlap. Chunks are never emitted below MIN_CHUNK_CHARS unless the block
itself is that short, so a chunk always carries enough context to stand alone.
"""

import re

CHUNK_TARGET_CHARS = 900    # aim for chunks around this size
CHUNK_MAX_CHARS = 1400      # hard cap before a split is forced
CHUNK_MIN_CHARS = 180       # never merge, but prefer not to emit below this
CHUNK_OVERLAP_CHARS = 150   # carried into the next chunk of a split block

# Bumped whenever the chunking behaviour changes in a way that makes existing
# rows worth re-creating. Stored on every chunk as chunk_version so the startup
# backfill can tell "chunker output is stale" from "this document genuinely
# has no headings", which both look like an empty section.
CHUNK_VERSION = 1

# Heading detection, ordered from strongest signal to weakest.
_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*\S)\s*$")
_NUM_HEADING = re.compile(
    r"^\s{0,6}(?:"
    r"(?:chapter|section|unit|module|part|lesson|topic)\s+"
    r"(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)\b[\s:.\-–—]*"
    r".*"
    r"|\d+(?:\.\d+)*[\s.)–—-]+\s*\S.*"          # 1. / 2.3 / 3) then text
    r")$",
    # Case-insensitive only for the keyword and roman-numeral branches. An
    # ALL-CAPS line is detected separately in _looks_like_heading with a real
    # isupper() test; putting an [A-Z] class in an IGNORECASE pattern would
    # match lowercase too and turn every wrapped sentence into a heading.
    re.IGNORECASE,
)
_SHORT_LINE = re.compile(r"^\s*\S[^:]{0,90}:\s*$")  # "Definition:"

# A heading is short and has no sentence punctuation.
_SENTENCE_END = re.compile(r"[.!?;]\s*$")

_LIST_ITEM = re.compile(
    r"^\s*(?:[-*•‣▪·]|\d+[.)]|[a-z][.)])\s+\S"
)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$|^\s*\S+\t+\S+")

_BULLET_CONT = re.compile(r"^\s*(?:[-*•‣▪·]|\d+[.)])\s+")


def _looks_like_heading(line):
    """True if this line is a heading rather than body text."""
    if not line or len(line) > 120:
        return False
    stripped = line.strip()
    if not stripped:
        return False
    if _MD_HEADING.match(line):
        return True
    if _SENTENCE_END.search(stripped):
        return False
    if len(stripped) > 90:
        return False

    # Numbered section titles ("1. Classical Management Theory",
    # "2.3 Systems Thinking") are headings even though they share a shape with
    # a numbered list item. What separates them is brevity: a list item runs
    # into a clause, a section title stops at its name. Markdown headings and
    # "Chapter 3" / "MODULE 1" markers are unambiguous, so they go first.
    if _MD_HEADING.match(line) or re.match(
        r"^\s*(?:chapter|section|unit|module|part|lesson|topic)\b", stripped, re.I
    ):
        return True
    num = re.match(r"^\s*\d+(?:\.\d+)*[\s.)–—-]+\s*\S", line)
    if num and not _TABLE_ROW.match(line):
        return True

    if _LIST_ITEM.match(line) or _TABLE_ROW.match(line):
        return False
    if _SHORT_LINE.match(line):
        return True
    if _NUM_HEADING.match(line):
        return True

    letters = [c for c in stripped if c.isalpha()]
    if letters and len(letters) >= 3:
        if stripped.isupper():
            return True
        if stripped == stripped.title() and len(stripped.split()) <= 10:
            return True
    return False


def _strip_md_prefix(line):
    m = _MD_HEADING.match(line)
    return m.group(2).strip() if m else line.strip()


def _split_sentences(text):
    """Sentence-aware split that keeps the terminator attached."""
    parts = re.split(r"(?<=[.!?])\s+", text or "")
    return [p.strip() for p in parts if p.strip()]


def _classify(lines):
    if any(_TABLE_ROW.match(l) for l in lines):
        return "table"
    if any(_LIST_ITEM.match(l) for l in lines):
        return "list"
    return "prose"


def _pack_sentences(sentences, target=CHUNK_TARGET_CHARS,
                    overlap=CHUNK_OVERLAP_CHARS):
    """Group sentences into windows of roughly `target` characters."""
    chunks, current = [], ""
    for sent in sentences:
        if current and len(current) + 1 + len(sent) > target:
            chunks.append(current)
            tail = current[-overlap:] if len(current) > overlap else ""
            # Resume from a sentence boundary inside the overlap window.
            cut = tail.rfind(". ")
            tail = tail[cut + 2:] if cut != -1 else tail
            current = (tail + " " + sent).strip() if tail else sent
        else:
            current = (current + " " + sent).strip() if current else sent
    if current:
        chunks.append(current)
    return chunks


def _split_long_block(text):
    """Split a block that exceeds the hard cap on sentence boundaries."""
    sentences = _split_sentences(text)
    if len(sentences) <= 1:
        # No sentence boundaries (e.g. a long table): hard-wrap on words.
        out, remaining = [], text
        while len(remaining) > CHUNK_MAX_CHARS:
            cut = remaining.rfind(" ", 0, CHUNK_MAX_CHARS)
            if cut <= 0:
                cut = CHUNK_MAX_CHARS
            out.append(remaining[:cut].strip())
            remaining = remaining[max(0, cut - CHUNK_OVERLAP_CHARS):]
        if remaining.strip():
            out.append(remaining.strip())
        return out
    return _pack_sentences(sentences)


def _classify_heading(line):
    """Classify a heading line into the four shapes the splitter understands.

    Returns (kind, level) where kind is one of:
      "chapter"  a module/unit/chapter marker, or a document title
      "section"  a numbered or markdown section inside the current part
      "title"    an unnumbered Title Case / ALL CAPS heading
    """
    m = _MD_HEADING.match(line)
    if m:
        return ("chapter" if len(m.group(1)) == 1 else "section",
                len(m.group(1)))
    stripped = line.strip()
    if re.match(
        r"^(?:chapter|section|unit|module|part|lesson|topic)\b", stripped, re.I
    ):
        return "chapter", 0
    num = re.match(r"^\s*(\d+(?:\.\d+)*)[\s.)–—-]+\s*\S", line)
    if num:
        return "section", num.group(1).count(".") + 1
    return "title", 0


def detect_structure(text, state=None):
    """Split a document's text into a flat list of blocks with metadata.

    Returns [{"kind", "text", "heading", "section", "level"}] in reading
    order. Used both by the chunker and to give retrieved chunks context.

    Headings are tracked as two independent paths, because real documents mix
    an outer part with an inner numbering:

        part_path   MODULE 1 > Evolution of Management
        sec_path    1. Classical Management Theory
        section     MODULE 1 > Evolution of Management > 1. Classical ...

    A chapter marker or document title resets the section path; a numbered or
    markdown section pushes onto it; an unnumbered heading extends the part
    path. This keeps "MODULE 1" from being discarded by the numbering that
    follows it, which a single level stack cannot do.

    `state` is an optional dict holding {"part_path", "sec_stack"}. Pass the
    same dict for consecutive pages so a section that continues over a page
    break keeps its full heading path.
    """
    lines = (text or "").splitlines()
    blocks = []
    if state is None:
        state = {"part_path": [], "sec_stack": []}
    part_path = state["part_path"]     # ["MODULE 1", "Evolution of Management"]
    sec_stack = state["sec_stack"]     # [(level, "1. Classical Management ...")
    current_heading = ""
    current_section = ""
    buffer = []
    buffer_heading = ""
    buffer_section = ""

    def flush():
        nonlocal buffer
        if not buffer:
            return
        body = "\n".join(l for l in buffer if l.strip()).strip()
        if body:
            blocks.append({
                "kind": _classify(buffer),
                "text": body,
                "heading": buffer_heading,
                "section": buffer_section,
                "level": 0,
            })
        buffer = []

    def sync():
        nonlocal current_heading, current_section
        if sec_stack:
            current_heading = sec_stack[-1][1]
        elif part_path:
            current_heading = part_path[-1]
        else:
            current_heading = ""
        current_section = " > ".join(part_path + [t for _l, t in sec_stack])

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue

        if _looks_like_heading(line):
            flush()
            title = _strip_md_prefix(line)
            kind, level = _classify_heading(line)
            if kind == "chapter":
                # A new module/chapter/document title re-anchors everything.
                part_path = [title]
                sec_stack = []
            elif kind == "section":
                while sec_stack and sec_stack[-1][0] >= level:
                    sec_stack.pop()
                sec_stack.append((level, title))
            else:
                # Unnumbered heading: nest under the current part, and drop the
                # section path because the old numbering no longer applies.
                if part_path and part_path[-1] == title:
                    pass
                else:
                    part_path.append(title)
                # Keep the part path from growing without bound on documents
                # that use a Title Case line for every paragraph.
                if len(part_path) > 4:
                    part_path = part_path[:1] + part_path[-3:]
                sec_stack = []
            sync()
            buffer_heading = current_heading
            buffer_section = current_section
            continue

        if not buffer:
            # Body text starting here belongs to the current heading.
            buffer_heading = current_heading
            buffer_section = current_section
        buffer.append(line)

    flush()
    return blocks


def chunk_pages(pages, document_title="", include_title_in_text=False):
    """Chunk a document's pages into structure-aware chunks.

    pages: [{"page_number": int, "text": str}]
    Returns a list of chunk dicts ready for store_chunks.
    """
    chunks = []
    # Structure state is threaded across pages so a section that continues
    # over a page break keeps its full heading path.
    state = {"part_path": [], "sec_stack": []}
    for page in pages:
        page_number = page.get("page_number", 1)
        text = page.get("text") or ""
        if not text.strip():
            continue

        blocks = detect_structure(text, state)
        if not blocks:
            blocks = [{"kind": "prose", "text": text.strip(),
                       "heading": "", "section": "", "level": 0}]

        # A run of blocks under the same heading is packed together so a
        # section's prose stays together rather than fragmenting per block.
        run, run_heading, run_section = [], "", ""
        pending = []

        def emit_run():
            nonlocal run, run_heading, run_section
            if not run:
                return
            body = "\n\n".join(run)
            pieces = (
                [body] if len(body) <= CHUNK_MAX_CHARS
                else _split_long_block(body)
            )
            for piece in pieces:
                if not piece.strip():
                    continue
                chunks.append({
                    "page_number": page_number,
                    "text": piece.strip(),
                    "heading": run_heading,
                    "section": run_section,
                    "kind": _classify(run),
                })
            run = []
            run_heading = ""
            run_section = ""

        for block in blocks:
            if block["section"] != run_section:
                emit_run()
                run_heading = block["heading"]
                run_section = block["section"]
            # A very large block is chunked on its own.
            if len(block["text"]) > CHUNK_TARGET_CHARS * 1.6:
                emit_run()
                for piece in _split_long_block(block["text"]):
                    if piece.strip():
                        chunks.append({
                            "page_number": page_number,
                            "text": piece.strip(),
                            "heading": block["heading"],
                            "section": block["section"],
                            "kind": block["kind"],
                        })
                run_heading = block["heading"]
                run_section = block["section"]
                continue
            run.append(block["text"])

        emit_run()

        # Prepend heading context so a chunk reads sensibly on its own. This is
        # what lets the retriever match "Scientific Management" against a chunk
        # whose body text never repeats the heading.
        if include_title_in_text and document_title:
            for c in chunks:
                if c["page_number"] == page_number and not c["text"].startswith(
                    document_title
                ):
                    c["text"] = f"{document_title}\n{c['text']}"

    return chunks
