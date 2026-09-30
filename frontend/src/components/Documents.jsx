import { useEffect, useState } from 'react'
import { api } from '../api.js'
import DocumentViewer from './DocumentViewer.jsx'

export default function Documents({ onOpenDocument }) {
  const [docs, setDocs] = useState(null)
  const [error, setError] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const load = () => {
    api
      .allDocuments()
      .then((d) => setDocs(d.documents))
      .catch((e) => setError(e.message))
  }

  useEffect(() => {
    load()
  }, [])

  const onDelete = async (d) => {
    if (
      !window.confirm(
        `Are you sure you want to delete "${d.title}"? This will permanently remove the document and all its versions.`,
      )
    )
      return
    setBusyId(d.id)
    setError(null)
    try {
      await api.deleteDocument(d.id)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <h1>Documents</h1>
      <p className="tagline">All documents across your projects</p>

      {!docs && <p className="muted">Loading…</p>}
      {docs && docs.length === 0 && (
        <p className="muted">No documents yet — upload a PDF inside a project.</p>
      )}
      {docs && docs.length > 0 && (
        <ul className="doc-list">
          {docs.map((d) => (
            <li key={d.id} className="doc-item">
              <div className="doc-main">
                <span className="doc-name">{d.title}</span>
                <span className="muted">
                  {d.filename} · {d.project_name} · by {d.full_name || d.username} ·{' '}
                  {d.created_at}
                </span>
                <span className="doc-meta">
                  <span className="badge">v{d.version}</span>
                  <span className={`status-badge status-${d.processing_status}`}>
                    {d.processing_status}
                  </span>
                  <span className="badge">{d.page_count} pages</span>
                </span>
              </div>
              <div className="doc-actions">
                <button
                  className="btn btn-small"
                  onClick={() => onOpenDocument(d.id, d.project_id, 'documents')}
                >
                  Open
                </button>
                <button className="btn btn-small" onClick={() => setViewing(d)}>
                  View
                </button>
                <button
                  className="btn btn-small btn-danger"
                  onClick={() => onDelete(d)}
                  disabled={busyId === d.id}
                >
                  {busyId === d.id ? 'Deleting…' : 'Delete'}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="error-text">{error}</p>}

      {viewing && <DocumentViewer doc={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}