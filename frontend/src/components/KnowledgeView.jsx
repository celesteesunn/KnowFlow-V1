import { useEffect, useState } from 'react'
import { api } from '../api.js'

const icon = (paths) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {paths}
  </svg>
)

const ICONS = {
  knowledge: icon(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7c-2-1.5-5-1.5-7 0v10c2-1.5 5-1.5 7 0s5-1.5 7 0V7c-2-1.5-5-1.5-7 0z" />
      <path d="M12 7v10" />
    </>,
  ),
  search: icon(
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </>,
  ),
  assistant: icon(
    <>
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
      <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" />
    </>,
  ),
}

export default function KnowledgeView({ onOpenDocument, nav }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .dashboard()
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  return (
    <div>
      <h1>Knowledge</h1>
      <p className="tagline">Knowledge gaps and activity across your workspace</p>

      <div className="dash-grid">
        <section className="panel dash-card">
          <div className="card-head">
            <h2>Knowledge Gaps</h2>
          </div>
          {!data && <p className="muted">Loading…</p>}
          {data && data.recent_gaps.length === 0 && (
            <div className="empty-state">
              {ICONS.knowledge}
              <span className="empty-state-title">No unanswered questions</span>
              <span className="empty-state-text">
                Questions the AI could not answer will appear here.
              </span>
            </div>
          )}
          {data && data.recent_gaps.length > 0 && (
            <ul className="plain-list">
              {data.recent_gaps.map((g, i) => (
                <li key={i}>
                  <span>{g.question}</span>
                  <span className="muted">{g.asked_at}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel dash-card">
          <div className="card-head">
            <h2>Potential Duplicates</h2>
          </div>
          {!data && <p className="muted">Loading…</p>}
          {data && data.potential_duplicates.length === 0 && (
            <div className="empty-state">
              {ICONS.search}
              <span className="empty-state-title">No potential duplicates</span>
              <span className="empty-state-text">
                Documents that look similar will be flagged here.
              </span>
            </div>
          )}
          {data && data.potential_duplicates.length > 0 && (
            <ul className="plain-list">
              {data.potential_duplicates.map((p, i) => (
                <li key={i}>
                  <span>
                    {p.document_a} ↔ {p.document_b}
                  </span>
                  <span className="badge">{Math.round(p.similarity * 100)}% similar</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="dash-grid">
        <section className="panel dash-card">
          <div className="card-head">
            <h2>Search Knowledge</h2>
          </div>
          <p className="muted">
            Find content across all your documents with keyword and semantic search.
          </p>
          <div className="stack" style={{ marginTop: 14 }}>
            <button className="btn btn-primary" onClick={nav.search}>
              Open Search
            </button>
          </div>
        </section>

        <section className="panel dash-card">
          <div className="card-head">
            <h2>Ask the AI Assistant</h2>
          </div>
          <p className="muted">
            Ask questions about your authorised knowledge. Answers are grounded in the
            uploaded content with sources.
          </p>
          <div className="stack" style={{ marginTop: 14 }}>
            <button className="btn btn-primary" onClick={nav.assistant}>
              Open AI Assistant
            </button>
          </div>
        </section>
      </div>

      {error && <p className="error-text">{error}</p>}
    </div>
  )
}