// Renders assistant answers as formatted React elements.
//
// The model returns Markdown, so it is parsed here instead of being shown as
// raw text. Everything is built as React elements — no dangerouslySetInnerHTML —
// so answer text can never inject HTML into the page.
//
// Supported: headings, bold, italic, inline code, fenced code, bullet and
// numbered lists, blockquotes, horizontal rules, paragraphs and links.

/* -------------------------------------------------------------------------
 * Cleanup
 * ---------------------------------------------------------------------- */

// Retrieval and debug noise the model sometimes echoes back. Removed so the
// user sees only the answer, never pipeline internals.
const NOISE_PATTERNS = [
  // [Source: file.pdf — page 2] / [file.pdf — page 2] / (Source: file.pdf, p. 2)
  /\[\s*source\s*:\s*[^\]]{0,200}\]/gi,
  /\(\s*source\s*:\s*[^)]{0,200}\)/gi,
  /\[\s*chunk\s*#?\s*\d+[^\]]{0,80}\]/gi,
  /\[\s*retriev(?:al|ed)\s+id[^\]]{0,80}\]/gi,
  /\[\s*embed(?:ding|dings)?[^\]]{0,80}\]/gi,
  // retrieval identifiers and debug values, anywhere in the line
  /\bretrieval\s*id\s*[:=]\s*\S+/gi,
  /\bchunk\s*#\s*\d+/gi,
  /\b(?:vector|embedding|doc(?:ument)?)\s*id\s*[:=]\s*\S+/gi,
  /\b(?:retrieval|vector|embedding|chunk|similarity|relevance|confidence)\s*score\s*[:=]\s*[0-9.]+/gi,
  // a heading that only hedges where the content came from
  /\s*\(\s*(?:as\s+)?(?:described|mentioned|stated|shown|explained|discussed|quoted|presented|listed)\s+(?:in|by|from)\s+(?:the\s+)?(?:uploaded\s+|provided\s+|retrieved\s+)?(?:pdf|docx|document|documents|excerpts?|text|file|files)\s*\)/gi,
  /\s*,\s*(?:as\s+)?(?:described|mentioned|stated|shown|explained|discussed|quoted|presented)\s+(?:in|by|from)\s+(?:the\s+)?(?:uploaded\s+|provided\s+)?(?:pdf|docx|document|documents|excerpts?|text|file|files)\b/gi,
  // vector / retrieval debug commentary
  /^\s*[-*]?\s*(?:retrieval|retrieved|vector|embedding|chunk|similarity|score|confidence)\s*(?:id|score|vector|embedding)?\s*[:=]\s*\S+.*$/gim,
  /\bcosine\s+similarity\s*[:=]\s*[0-9.]+/gi,
  /\b(?:similarity|relevance|confidence)\s+score\s*[:=]\s*[0-9.]+/gi,
  // model disclaimers about the excerpts
  /^\s*\(?\s*note\s*:\s*the excerpts? above[^\n]*$/gim,
  /\bthe (?:provided |retrieved |above )?excerpts? (?:do(?:es)? not|don't|does not) contain[^\n]*/gi,
  /\bbased on the (?:provided |retrieved )?excerpts? (?:above )?(?:only )?,?/gi,
  /\baccording to the (?:provided |retrieved )?excerpts? (?:above )?,?/gi,
]

// Strip markers, collapse the blank lines they leave behind, and tidy spaces.
export function cleanAnswer(text) {
  if (!text) return ''
  let out = String(text).replace(/\r\n/g, '\n')

  for (const re of NOISE_PATTERNS) out = out.replace(re, '')

  return out
    // a marker that was the entire line leaves an empty line behind
    .replace(/[ \t]+$/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

// Retrieval-only mode returns raw passages with this header per excerpt.
const PASSAGE_HEADER = /^\s*\[([^\]]{1,200}?)\s+[—-]\s+page\s+(\d+)\s*\]\s*$/i

/* -------------------------------------------------------------------------
 * Inline parsing -> React nodes
 * ---------------------------------------------------------------------- */

// A fresh regex per call: renderInline recurses (bold inside a link label),
// and a shared global regex would have its lastIndex reset by the inner call,
// looping forever.
const INLINE_SRC =
  '(`[^`]+`)|(\\*\\*|__)(?=\\S)([\\s\\S]*?\\S)\\2|(\\*|_)(?=\\S)([\\s\\S]*?\\S)\\4|(\\[[^\\]]{1,200}\\]\\([^)\\s]{1,2000}\\))'

function renderInline(text, keyBase) {
  if (!text) return null
  const nodes = []
  let last = 0
  let m
  let i = 0
  const re = new RegExp(INLINE_SRC, 'g')

  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const key = `${keyBase}-i${i++}`

    if (m[1]) {
      nodes.push(
        <code className="md-code" key={key}>
          {m[1].slice(1, -1)}
        </code>,
      )
    } else if (m[2]) {
      nodes.push(
        <strong key={key}>{renderInline(m[3], key)}</strong>,
      )
    } else if (m[4]) {
      nodes.push(<em key={key}>{renderInline(m[5], key)}</em>)
    } else if (m[6]) {
      const link = /^\[([^\]]*)\]\(([^)\s]+)\)$/.exec(m[6])
      const label = link ? link[1] : m[6]
      const href = link ? link[2] : ''
      // Only http(s) links become anchors; anything else stays plain text so
      // a model response cannot smuggle in javascript: or data: URLs.
      if (/^https?:\/\//i.test(href)) {
        nodes.push(
          <a
            className="md-link"
            key={key}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
          >
            {label}
          </a>,
        )
      } else {
        nodes.push(label)
      }
    }
    last = m.index + m[0].length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

/* -------------------------------------------------------------------------
 * Block parsing
 * ---------------------------------------------------------------------- */

const BULLET = /^[-*+]\s+(.*)$/
const ORDERED = /^\d+[.)]\s+(.*)$/
const HEADING = /^(#{1,6})\s+(.*)$/
const QUOTE = /^>\s?(.*)$/
const FENCE = /^\s*(?:```|~~~)\s*([\w+-]*)\s*$/
const RULE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/

function renderBlocks(lines, keyBase) {
  const out = []
  let i = 0
  let n = 0

  const key = () => `${keyBase}-b${n++}`

  while (i < lines.length) {
    const line = lines[i]

    if (!line.trim()) {
      i += 1
      continue
    }

    // fenced code
    const fence = FENCE.exec(line)
    if (fence) {
      const body = []
      i += 1
      while (i < lines.length && !FENCE.test(lines[i])) {
        body.push(lines[i])
        i += 1
      }
      i += 1 // closing fence
      out.push(
        <pre className="md-pre" key={key()}>
          <code>{body.join('\n')}</code>
        </pre>,
      )
      continue
    }

    if (RULE.test(line)) {
      out.push(<hr className="md-hr" key={key()} />)
      i += 1
      continue
    }

    const h = HEADING.exec(line)
    if (h) {
      const level = Math.min(h[1].length, 6)
      const Tag = `h${level}`
      out.push(
        <Tag className={`md-h md-h${level}`} key={key()}>
          {renderInline(h[2].trim(), key())}
        </Tag>,
      )
      i += 1
      continue
    }

    if (QUOTE.test(line)) {
      const body = []
      while (i < lines.length && QUOTE.test(lines[i])) {
        body.push(QUOTE.exec(lines[i])[1])
        i += 1
      }
      out.push(
        <blockquote className="md-quote" key={key()}>
          {body.map((b, bi) => (
            <p key={`${keyBase}-q${bi}`}>{renderInline(b, `${keyBase}-q${bi}`)}</p>
          ))}
        </blockquote>,
      )
      continue
    }

    // lists (a run of bullets or a run of numbers)
    if (BULLET.test(line) || ORDERED.test(line)) {
      const ordered = ORDERED.test(line)
      const items = []
      while (i < lines.length) {
        const m = ordered ? ORDERED.exec(lines[i]) : BULLET.exec(lines[i])
        if (!m) break
        const parts = [m[1]]
        i += 1
        // continuation lines indented under the item
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !BULLET.test(lines[i])) {
          parts.push(lines[i].trim())
          i += 1
        }
        items.push(parts.join(' '))
      }
      const List = ordered ? 'ol' : 'ul'
      out.push(
        <List className={ordered ? 'md-ol' : 'md-ul'} key={key()}>
          {items.map((it, ii) => (
            <li key={`${keyBase}-li${ii}`}>{renderInline(it, `${keyBase}-li${ii}`)}</li>
          ))}
        </List>,
      )
      continue
    }

    // paragraph: consecutive non-blank lines that start no other block
    const para = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !HEADING.test(lines[i]) &&
      !BULLET.test(lines[i]) &&
      !ORDERED.test(lines[i]) &&
      !QUOTE.test(lines[i]) &&
      !FENCE.test(lines[i]) &&
      !RULE.test(lines[i])
    ) {
      para.push(lines[i].trim())
      i += 1
    }
    if (para.length === 0) {
      i += 1
      continue
    }
    const joined = para.join(' ')
    // A whole paragraph wrapped in bold (optionally numbered) is a subheading
    // in practice — e.g. "**1. Classical Management Theory**". Render it as
    // one so it gets real visual hierarchy instead of a bold paragraph.
    const asHeading = /^\*\*\s*((?:\d+[.)]\s*)?)(?!\d)([^*]+?)\s*\*\*$/.exec(joined)
    if (asHeading) {
      const level = asHeading[1] ? 3 : 2
      const Tag = `h${level}`
      out.push(
        <Tag className={`md-h md-h${level}`} key={key()}>
          {renderInline(asHeading[2].trim(), key())}
        </Tag>,
      )
      continue
    }
    out.push(
      <p className="md-p" key={key()}>
        {renderInline(joined, key())}
      </p>,
    )
  }

  return out
}

/* -------------------------------------------------------------------------
 * Retrieval-only mode
 * ---------------------------------------------------------------------- */

// Without an LLM key the answer is a list of raw passages, each headed by
// "[filename — page n]". Split those out so they read as quoted excerpts
// with their citation kept, instead of leaking the retrieval block format.
function renderPassages(text, keyBase) {
  const lines = text.split('\n')
  const out = []
  let i = 0
  let n = 0

  while (i < lines.length) {
    const m = PASSAGE_HEADER.exec(lines[i])
    if (!m) {
      i += 1
      continue
    }
    const citation = `${m[1].trim()}, page ${m[2]}`
    i += 1
    const body = []
    while (i < lines.length && !PASSAGE_HEADER.test(lines[i])) {
      body.push(lines[i])
      i += 1
    }
    const text_ = body.join('\n').trim()
    if (!text_) continue
    out.push(
      <blockquote className="md-quote md-passage" key={`${keyBase}-p${n++}`}>
        <p>{renderInline(text_, `${keyBase}-p${n}`)}</p>
        <cite className="md-cite">{citation}</cite>
      </blockquote>,
    )
  }
  return out
}

/* -------------------------------------------------------------------------
 * Component
 * ---------------------------------------------------------------------- */

export default function Markdown({ text, mode }) {
  const cleaned = cleanAnswer(text)
  if (!cleaned) return null

  // Retrieval-only answers are passages, not prose: render them as excerpts
  // and keep anything left over as normal formatted text.
  if (mode === 'retrieval-only' && PASSAGE_HEADER.test(cleaned)) {
    const passages = renderPassages(cleaned, 'md')
    const leftover = cleaned
      .split('\n')
      .filter((l) => !PASSAGE_HEADER.test(l))
      .join('\n')
      .trim()
    return (
      <div className="md">
        {passages.length > 0 && (
          <>
            <p className="md-p md-note">
              Generated answers are unavailable, so these are the passages closest to
              your question.
            </p>
            {passages}
          </>
        )}
        {leftover && <>{renderBlocks(leftover.split('\n'), 'md-lo')}</>}
      </div>
    )
  }

  return <div className="md">{renderBlocks(cleaned.split('\n'), 'md')}</div>
}

// Exported for the Sources block, which needs the same tidy-up.
export function SourceList({ sources }) {
  if (!sources || sources.length === 0) return null
  // Same document on several pages collapses to one entry per page.
  const seen = new Set()
  const rows = []
  for (const s of sources) {
    const name = (s.document || 'Document').trim()
    const page = s.page ? `Page ${s.page}` : ''
    const k = `${name}|${page}`
    if (seen.has(k)) continue
    seen.add(k)
    rows.push({ name, page })
  }
  return (
    <div className="md-sources">
      <strong>Sources</strong>
      <ul>
        {rows.map((r, i) => (
          <li key={i}>
            {r.name}
            {r.page ? <span className="md-source-page">, {r.page}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  )
}
