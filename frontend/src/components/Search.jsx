import { useState } from 'react'
import { api } from '../api.js'

export default function Search({ onOpenProject }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState(null)

  const doSearch = async (e) => {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    setError(null)
    try {
      setResults(await api.globalSearch(query))
    } catch (err) {
      setError(err.message)
    } finally {
      setSearching(false)
    }
  }

  return (
    <div>
      <h1>Search</h1>
      <p className="tagline">Search across all your documents</p>

      <section className="panel">
        <form onSubmit={doSearch} className="stack">
          <input
            placeholder="Search terms…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button className="btn btn-primary" disabled={searching}>
            {searching ? 'Searching…' : 'Search'}
          </button>
        </form>

        {results && (
          <div className="results">
            {results.results.length === 0 && <p className="muted">No matches.</p>}
            {results.results.map((r) => (
              <div key={`${r.document_id}-${r.page_number}`} className="result-item">
                <strong>{r.title || r.filename}</strong>
                <span className="badge">{r.project_name}</span>
                <span className="badge">page {r.page_number}</span>
                <p className="muted">{r.snippet}</p>
                <button
                  className="link-btn"
                  onClick={() => onOpenProject({ id: r.project_id, name: r.project_name })}
                >
                  Open project
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      {error && <p className="error-text">{error}</p>}
    </div>
  )
}