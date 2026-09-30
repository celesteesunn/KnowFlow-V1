import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import Chat from './Chat.jsx'
import DocumentDetail from './DocumentDetail.jsx'
import DocumentViewer from './DocumentViewer.jsx'

// Upload limits — keep in sync with backend config.py (MAX_UPLOAD_MB,
// ALLOWED_EXTENSIONS). Only values the backend actually accepts are shown.
const MAX_UPLOAD_MB = 500
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt']
const MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024

const tooLarge = (name) =>
  `${name}: file too large. The maximum allowed file size is ` +
  `${MAX_UPLOAD_MB} MB. Please choose a smaller file.`

const badType = (name) => `${name}: only PDF, DOCX or TXT files are allowed.`

// Check a file locally so an over-limit file is never sent to the server.
const rejectReason = (file) => {
  const ext = `.${file.name.split('.').pop().toLowerCase()}`
  if (!ALLOWED_EXTENSIONS.includes(ext)) return badType(file.name)
  if (file.size > MAX_BYTES) return tooLarge(file.name)
  return null
}

export default function ProjectDetail({ project, onBack }) {
  const [documents, setDocuments] = useState([])
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [uploadError, setUploadError] = useState(null)
  const [uploadForm, setUploadForm] = useState({ title: '', description: '', category: '', tags: '' })
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [dups, setDups] = useState(null)
  const [dupBusy, setDupBusy] = useState(false)
  const [error, setError] = useState(null)
  const fileInput = useRef(null)
  const replaceInputs = useRef({})

  const loadDocs = () =>
    api
      .documents(project.id)
      .then((d) => setDocuments(d.documents))
      .catch((e) => setError(e.message))

  useEffect(() => {
    loadDocs()
  }, [project.id])

  const upload = async (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    setUploading(true)
    setUploadMsg(null)
    setUploadError(null)

    // The 500 MB limit is applied to each selected file on its own, so one
    // oversized file is rejected by name while the rest still upload.
    const valid = []
    const rejected = []
    for (const file of files) {
      const reason = rejectReason(file)
      if (reason) rejected.push(reason)
      else valid.push(file)
    }

    const notes = []
    let uploaded = 0
    try {
      for (const file of valid) {
        try {
          const res = await api.uploadDocument(project.id, file, uploadForm)
          let msg = `Uploaded ${res.document.title} (v${res.document.version})`
          if (res.potentially_similar && res.potentially_similar.length > 0) {
            const top = res.potentially_similar[0]
            msg += ` — Possible duplicate detected: ${top.filename} — ${Math.round(
              top.similarity * 100,
            )}% similarity. Potentially similar document.`
          }
          notes.push(msg)
          uploaded += 1
        } catch (err) {
          rejected.push(`${file.name}: ${err.message}`)
        }
      }
    } finally {
      if (uploaded > 0) {
        setUploadMsg(notes.join(' '))
        setUploadForm({ title: '', description: '', category: '', tags: '' })
        await loadDocs()
      }
      if (rejected.length > 0) setUploadError(rejected.join(' '))
      e.target.value = ''
      setUploading(false)
    }
  }

  const onReplaceFile = async (docId, e) => {
    const file = e.target.files[0]
    if (!file) return
    setError(null)
    const reason = rejectReason(file)
    if (reason) {
      setError(reason)
      e.target.value = ''
      return
    }
    try {
      const res = await api.replaceDocument(project.id, docId, file, {})
      setUploadMsg(`Replaced with version ${res.version}`)
      e.target.value = ''
      await loadDocs()
    } catch (err) {
      setError(err.message)
    }
  }

  const onArchive = async (doc) => {
    if (!window.confirm(`Archive "${doc.title}"? It will be hidden from the project.`)) return
    setError(null)
    try {
      await api.archiveDocument(doc.id)
      await loadDocs()
    } catch (err) {
      setError(err.message)
    }
  }

  const onDelete = async (doc) => {
    if (
      !window.confirm(
        `Permanently delete "${doc.title}" and all its versions? This cannot be undone.`,
      )
    )
      return
    setError(null)
    try {
      await api.deleteDocument(doc.id)
      await loadDocs()
    } catch (err) {
      setError(err.message)
    }
  }

  const doSearch = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      setResults(await api.search(project.id, query))
    } catch (err) {
      setError(err.message)
    }
  }

  const doDups = async () => {
    setDupBusy(true)
    setError(null)
    try {
      setDups(await api.duplicates(project.id))
    } catch (err) {
      setError(err.message)
    } finally {
      setDupBusy(false)
    }
  }

  if (selectedDoc) {
    return (
      <DocumentDetail
        docId={selectedDoc}
        projectId={project.id}
        onBack={() => setSelectedDoc(null)}
        onChanged={loadDocs}
      />
    )
  }

  if (chatOpen) {
    return <Chat project={project} onBack={() => setChatOpen(false)} />
  }

  return (
    <div>
      <button className="link-btn" onClick={onBack}>
        ← All projects
      </button>
      <h1>{project.name}</h1>
      {project.description && <p className="tagline">{project.description}</p>}

      <section className="panel">
        <h2>Upload document</h2>
        <div className="upload-form">
          <input
            placeholder="Title (defaults to filename)"
            value={uploadForm.title}
            onChange={(e) => setUploadForm({ ...uploadForm, title: e.target.value })}
          />
          <input
            placeholder="Description (optional)"
            value={uploadForm.description}
            onChange={(e) => setUploadForm({ ...uploadForm, description: e.target.value })}
          />
          <input
            placeholder="Category (optional, e.g. Policy, Report)"
            value={uploadForm.category}
            onChange={(e) => setUploadForm({ ...uploadForm, category: e.target.value })}
          />
          <input
            placeholder="Tags (optional, comma separated)"
            value={uploadForm.tags}
            onChange={(e) => setUploadForm({ ...uploadForm, tags: e.target.value })}
          />
          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.docx,.txt"
            multiple
            onChange={upload}
            disabled={uploading}
          />
        </div>
        <p className="muted">
          Maximum file size: {MAX_UPLOAD_MB} MB per file · Supported formats:{' '}
          {ALLOWED_EXTENSIONS.map((x) => x.slice(1).toUpperCase()).join(', ')}
        </p>
        {uploading && <p className="muted">Uploading and extracting text…</p>}
        {uploadMsg && <p className="ok-text">{uploadMsg}</p>}
        {uploadError && <p className="error-text">{uploadError}</p>}
      </section>

      <section className="panel">
        <h2>Documents ({documents.length})</h2>
        {documents.length === 0 && (
          <p className="muted">No documents yet — upload a PDF, DOCX or TXT above.</p>
        )}
        <ul className="doc-list">
          {documents.map((d) => (
            <li key={d.id} className="doc-item">
              <div className="doc-main">
                <span className="doc-name">{d.title}</span>
                <span className="muted">
                  {d.filename} · by {d.full_name || d.username} · {d.created_at}
                </span>
                <span className="doc-meta">
                  <span className="badge">v{d.version}</span>
                  <span className={`status-badge status-${d.processing_status}`}>
                    {d.processing_status}
                  </span>
                  {d.category && <span className="badge">{d.category}</span>}
                  <span className="badge">{d.page_count} pages</span>
                </span>
              </div>
              <div className="doc-actions">
                <button className="btn btn-small" onClick={() => setViewing(d)}>
                  View
                </button>
                <a className="btn btn-small" href={api.downloadUrl(d.id)}>
                  Download
                </a>
                <button
                  className="btn btn-small"
                  onClick={() => replaceInputs.current[d.id]?.click()}
                >
                  Replace
                </button>
                <button className="btn btn-small btn-danger" onClick={() => onArchive(d)}>
                  Archive
                </button>
                <button className="btn btn-small btn-danger" onClick={() => onDelete(d)}>
                  Delete
                </button>
                <input
                  ref={(el) => (replaceInputs.current[d.id] = el)}
                  type="file"
                  accept=".pdf,.docx,.txt"
                  style={{ display: 'none' }}
                  onChange={(e) => onReplaceFile(d.id, e)}
                />
              </div>
            </li>
          ))}
        </ul>
      </section>

      <div className="two-col">
        <section className="panel">
          <h2>Search documents</h2>
          <form onSubmit={doSearch} className="stack">
            <input
              placeholder="Search terms…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button className="btn btn-primary">Search</button>
          </form>
          {results && (
            <div className="results">
              {results.results.length === 0 && <p className="muted">No matches.</p>}
              {results.results.map((r) => (
                <div key={r.id} className="result-item">
                  <strong>{r.filename}</strong>
                  <p className="muted">{r.snippet}</p>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="panel">
          <h2>Ask the AI assistant</h2>
          <p className="muted">
            Chat with the AI about the documents in this project. Answers are
            grounded in the uploaded content with sources.
          </p>
          <button className="btn btn-primary" onClick={() => setChatOpen(true)}>
            Open chat
          </button>
        </section>
      </div>

      <section className="panel">
        <h2>Duplicate detection</h2>
        <button className="btn" onClick={doDups} disabled={dupBusy}>
          {dupBusy ? 'Scanning…' : 'Check for duplicates'}
        </button>
        {dups && (
          <div className="results">
            {dups.duplicates.length === 0 && (
              <p className="ok-text">No potential duplicates found.</p>
            )}
            {dups.duplicates.map((d, i) => (
              <div key={i} className="result-item">
                <strong>{d.document_a}</strong> ↔ <strong>{d.document_b}</strong>
                <span className="badge">{Math.round(d.similarity * 100)}% similar</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {error && <p className="error-text">{error}</p>}

      {viewing && <DocumentViewer doc={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}