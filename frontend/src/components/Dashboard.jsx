import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Dashboard({ user, onOpenProject, onOpenDocument }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .dashboard()
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  if (!data) {
    return (
      <div>
        <h1>Dashboard</h1>
        <p className="muted">Loading…</p>
        {error && <p className="error-text">{error}</p>}
      </div>
    )
  }

  return (
    <div>
      <h1>Dashboard</h1>
      <p className="tagline">Welcome back, {user.full_name || user.username}</p>

      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-value">{data.projects_count}</span>
          <span className="stat-label">Projects</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{data.documents_count}</span>
          <span className="stat-label">Documents</span>
        </div>
      </div>

      <div className="two-col">
        <section className="panel">
          <h2>Recently uploaded</h2>
          {data.recent_uploads.length === 0 && <p className="muted">No documents yet.</p>}
          <ul className="plain-list">
            {data.recent_uploads.map((d) => (
              <li key={d.id}>
                <button
                  className="link-btn"
                  onClick={() => onOpenDocument(d.id, d.project_id, 'dashboard')}
                >
                  {d.title}
                </button>
                <span className="muted">
                  {d.project_name} · {d.created_at}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Recently updated</h2>
          {data.recent_updates.length === 0 && (
            <p className="muted">No documents updated yet.</p>
          )}
          <ul className="plain-list">
            {data.recent_updates.map((d) => (
              <li key={d.id}>
                <button
                  className="link-btn"
                  onClick={() => onOpenDocument(d.id, d.project_id, 'dashboard')}
                >
                  {d.title}
                </button>
                <span className="muted">
                  v{d.version} · {d.created_at}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <div className="two-col">
        <section className="panel">
          <h2>Recent unanswered questions</h2>
          {data.recent_gaps.length === 0 && (
            <p className="muted">No unanswered questions.</p>
          )}
          <ul className="plain-list">
            {data.recent_gaps.map((g, i) => (
              <li key={i}>
                <span>{g.question}</span>
                <span className="muted">{g.asked_at}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="panel">
          <h2>Potential duplicates</h2>
          {data.potential_duplicates.length === 0 && (
            <p className="ok-text">No potential duplicates found.</p>
          )}
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
        </section>
      </div>
    </div>
  )
}