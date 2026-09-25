import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function ProjectDetail({ project, onBack }) {
  const [documents, setDocuments] = useState([])
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [asking, setAsking] = useState(false)
  const [dups, setDups] = useState(null)
  const [dupBusy, setDupBusy] = useState(false)
  const [error, setError] = useState(null)

  const loadDocs = () =>
    api
      .documents(project.id)
      .then((d) => setDocuments(d.documents))
      .catch((e) => setError(e.message))

  useEffect(() => {
    loadDocs()
  }, [project.id])

  const upload = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    setUploading(true)
    setUploadMsg(null)
    setError(null)
    try {
      await api.uploadDocument(project.id, file)
      setUploadMsg(`Uploaded ${file.name}`)
      e.target.value = ''
      await loadDocs()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
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

  const doAsk = async (e) => {
    e.preventDefault()
    if (!question.trim()) return
    setAsking(true)
    setAnswer(null)
    setError(null)
    try {
      setAnswer(await api.ask(project.id, question))
    } catch (err) {
      setError(err.message)
    } finally {
      setAsking(false)
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

  return (
    <div>
      <button className="link-btn" onClick={onBack}>
        ← All projects
      </button>
      <h1>{project.name}</h1>
      {project.description && <p className="tagline">{project.description}</p>}

      <section className="panel">
        <h2>Upload PDF</h2>
        <input type="file" accept=".pdf" onChange={upload} disabled={uploading} />
        {uploading && <p className="muted">Uploading and extracting text…</p>}
        {uploadMsg && <p className="ok-text">{uploadMsg}</p>}
      </section>

      <section className="panel">
        <h2>Documents ({documents.length})</h2>
        {documents.length === 0 && <p className="muted">No documents yet — upload a PDF above.</p>}
        <ul className="doc-list">
          {documents.map((d) => (
            <li key={d.id} className="doc-item">
              <span className="doc-name">{d.filename}</span>
              <span className="badge">{d.page_count} pages</span>
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
          <form onSubmit={doAsk} className="stack">
            <textarea
              placeholder="Ask a question about the documents…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={3}
            />
            <button className="btn btn-primary" disabled={asking}>
              {asking ? 'Thinking…' : 'Ask'}
            </button>
          </form>
          {answer && (
            <div className="answer">
              <p className="answer-text">{answer.answer}</p>
              {answer.sources && answer.sources.length > 0 && (
                <div className="sources">
                  <strong>Sources:</strong>
                  <ul>
                    {answer.sources.map((s, i) => (
                      <li key={i}>
                        {s.document} — page {s.page} (score {s.score})
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {answer.mode && <p className="muted">Mode: {answer.mode}</p>}
            </div>
          )}
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
    </div>
  )
}