import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Insights() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .adminInsights()
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  if (!data) {
    return (
      <div>
        <h1>Knowledge insights</h1>
        <p className="muted">Loading…</p>
        {error && <p className="error-text">{error}</p>}
      </div>
    )
  }

  return (
    <div>
      <h1>Knowledge insights</h1>
      <p className="tagline">
        Unanswered questions and potential duplicates across all projects
      </p>

      <section className="panel">
        <h2>Frequently unanswered questions</h2>
        {data.gaps.length === 0 && <p className="ok-text">No unanswered questions recorded.</p>}
        <ul className="plain-list">
          {data.gaps.map((g, i) => (
            <li key={i}>
              <span>{g.question}</span>
              <span className="badge">{g.occurrences}×</span>
              <span className="muted">last asked {g.last_asked}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel">
        <h2>Potential duplicate documents</h2>
        {data.duplicates.length === 0 && <p className="ok-text">No potential duplicates found.</p>}
        <ul className="plain-list">
          {data.duplicates.map((p, i) => (
            <li key={i}>
              <span>
                {p.document_a} ↔ {p.document_b}
              </span>
              <span className="muted">
                {p.project_a} / {p.project_b}
              </span>
              <span className="badge">{Math.round(p.similarity * 100)}% similar</span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}