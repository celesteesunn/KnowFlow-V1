import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Upload limit — keep in sync with backend config.py (MAX_UPLOAD_MB).
const MAX_UPLOAD_MB = 500
const MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024

export default function DocumentDetail({ docId, projectId, onBack, onChanged }) {
  const [currentId, setCurrentId] = useState(docId)
  const [detail, setDetail] = useState(null)
  const [related, setRelated] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const replaceInput = useRef(null)

  const load = () => {
    api
      .documentDetail(currentId)
      .then((d) => setDetail(d))
      .catch((e) => setError(e.message))
    api
      .relatedDocuments(currentId)
      .then((r) => setRelated(r.related))
      .catch(() => setRelated([]))
  }

  useEffect(() => {
    load()
  }, [currentId])

  const onReplaceFile = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setError(null)
    setMsg(null)
    // Checked locally so a file over the limit is never sent to the server.
    if (file.size > MAX_BYTES) {
      setError(
        `${file.name}: file too large. The maximum allowed file size is ` +
          `${MAX_UPLOAD_MB} MB. Please choose a smaller file.`,
      )
      e.target.value = ''
      return
    }
    setBusy(true)
    try {
      const res = await api.replaceDocument(projectId, currentId, file, {})
      setMsg(`Replaced with version ${res.version}`)
      e.target.value = ''
      await load()
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const onArchive = async () => {
    if (!window.confirm('Archive this document? It will be hidden from the project.')) return
    setBusy(true)
    setError(null)
    try {
      await api.archiveDocument(currentId)
      onChanged()
      onBack()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async () => {
    const title = detail?.document?.title || 'this document'
    if (
      !window.confirm(
        `Permanently delete "${title}" and all its versions? This cannot be undone.`,
      )
    )
      return
    setBusy(true)
    setError(null)
    try {
      await api.deleteDocument(currentId)
      onChanged()
      onBack()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (!detail) {
    return (
      <div>
        <button className="link-btn" onClick={onBack}>
          ← Back to project
        </button>
        <p className="muted">Loading document…</p>
        {error && <p className="error-text">{error}</p>}
      </div>
    )
  }

  const d = detail.document

  return (
    <div>
      <button className="link-btn" onClick={onBack}>
        ← Back to project
      </button>
      <h1>{d.title}</h1>
      {d.category && <span className="badge">{d.category}</span>}

      <section className="panel">
        <h2>Document information</h2>
        <dl className="detail-grid">
          <div>
            <dt>Filename</dt>
            <dd>{d.filename}</dd>
          </div>
          <div>
            <dt>Project</dt>
            <dd>{d.project_name}</dd>
          </div>
          <div>
            <dt>Uploaded by</dt>
            <dd>{d.full_name || d.username}</dd>
          </div>
          <div>
            <dt>Upload date</dt>
            <dd>{d.created_at}</dd>
          </div>
          <div>
            <dt>Version</dt>
            <dd>v{d.version}</dd>
          </div>
          <div>
            <dt>Pages</dt>
            <dd>{d.page_count}</dd>
          </div>
          <div>
            <dt>Processing status</dt>
            <dd>
              <span className={`status-badge status-${d.processing_status}`}>
                {d.processing_status}
              </span>
            </dd>
          </div>
          <div>
            <dt>Description</dt>
            <dd>{d.description || '—'}</dd>
          </div>
        </dl>

        <div className="actions">
          <a className="btn btn-primary" href={api.downloadUrl(currentId)}>
            Download
          </a>
          <button className="btn" onClick={() => replaceInput.current.click()} disabled={busy}>
            Replace document
          </button>
          <button className="btn btn-danger" onClick={onArchive} disabled={busy}>
            Archive
          </button>
          <button className="btn btn-danger" onClick={onDelete} disabled={busy}>
            Delete permanently
          </button>
          <input
            ref={replaceInput}
            type="file"
            accept=".pdf,.docx,.txt"
            style={{ display: 'none' }}
            onChange={onReplaceFile}
          />
        </div>
        {msg && <p className="ok-text">{msg}</p>}
        {error && <p className="error-text">{error}</p>}
      </section>

      <section className="panel">
        <h2>Related documents</h2>
        {related === null && <p className="muted">Loading…</p>}
        {related && related.length === 0 && (
          <p className="muted">No related documents found.</p>
        )}
        {related && related.length > 0 && (
          <ul className="version-list">
            {related.map((r) => (
              <li key={r.document_id} className="version-item">
                <span className="version-file">
                  <button className="link-btn" onClick={() => setCurrentId(r.document_id)}>
                    {r.title || r.filename}
                  </button>
                </span>
                <span className="muted">{r.project_name}</span>
                <span className="badge">{Math.round(r.similarity * 100)}% similar</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2>Version history</h2>
        <ul className="version-list">
          {detail.versions.map((v) => (
            <li key={v.id} className="version-item">
              <span className="version-no">v{v.version}</span>
              <span className="version-file">{v.filename}</span>
              <span className="muted">{v.created_at}</span>
              {v.is_current === 1 && <span className="badge badge-current">current</span>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}