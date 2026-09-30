import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import DocumentViewer from './DocumentViewer.jsx'

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
  search: icon(
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </>,
  ),
  empty: icon(
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
      <path d="M8.5 8.5l5 5" />
      <path d="M13.5 8.5l-5 5" />
    </>,
  ),
}

// Wrap every occurrence of any query term in <mark> (longest term first).
const highlight = (text, terms) => {
  if (!text) return text
  const sorted = [...new Set(terms.filter(Boolean))].sort((a, b) => b.length - a.length)
  if (sorted.length === 0) return text
  const lower = text.toLowerCase()
  const parts = []
  let i = 0
  while (i < text.length) {
    let best = null
    for (const t of sorted) {
      if (lower.startsWith(t, i) && (!best || t.length > best.length)) best = t
    }
    if (best) {
      parts.push(<mark key={i}>{text.slice(i, i + best.length)}</mark>)
      i += best.length
    } else {
      let j = i + 1
      while (j < text.length) {
        if (sorted.some((t) => lower.startsWith(t, j))) break
        j += 1
      }
      parts.push(text.slice(i, j))
      i = j
    }
  }
  return parts
}

const fileTypeOf = (filename) => {
  const ext = (filename || '').split('.').pop().toLowerCase()
  return { pdf: 'PDF', docx: 'DOCX', txt: 'TXT' }[ext] || ext.toUpperCase()
}

export default function Search({ onOpenProject, onOpenDocument, initialQuery = '' }) {
  const [query, setQuery] = useState(initialQuery)
  const [results, setResults] = useState(null) // array of results (or null = no search yet)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [filters, setFilters] = useState({ category: '', type: '', project_id: '' })
  const [filterOptions, setFilterOptions] = useState({ categories: [], types: [], projects: [] })
  const suggestTimer = useRef(null)

  const terms = (query.toLowerCase().match(/[a-z0-9]+/g) || []).map((t) => t.toLowerCase())

  // Filter options come from the user's own documents, so they can never
  // expose categories/projects the user cannot access.
  useEffect(() => {
    api
      .allDocuments()
      .then((data) => {
        const docs = data.documents || []
        const categories = [...new Set(docs.map((d) => d.category).filter(Boolean))].sort()
        const types = [...new Set(docs.map((d) => fileTypeOf(d.filename)))].sort()
        const projects = []
        const seen = new Set()
        for (const d of docs) {
          if (d.project_id && !seen.has(d.project_id)) {
            seen.add(d.project_id)
            projects.push({ id: d.project_id, name: d.project_name })
          }
        }
        setFilterOptions({ categories, types, projects })
      })
      .catch(() => {}) // filters are optional; search still works without them
  }, [])

  // Run the search immediately when arriving with a query from the dashboard.
  useEffect(() => {
    if (initialQuery) doSearch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Debounced suggestions while typing (only the user's own documents).
  useEffect(() => {
    if (suggestTimer.current) clearTimeout(suggestTimer.current)
    const q = query.trim()
    if (!q || searching || results) {
      setSuggestions([])
      return
    }
    suggestTimer.current = setTimeout(async () => {
      try {
        const data = await api.searchSuggestions(q)
        setSuggestions(data.suggestions || [])
      } catch {
        setSuggestions([])
      }
    }, 250)
    return () => {
      if (suggestTimer.current) clearTimeout(suggestTimer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, searching, results])

  const doSearch = async (e) => {
    if (e) e.preventDefault()
    const q = query.trim()
    if (!q) {
      setResults(null)
      setSuggestions([])
      return
    }
    setSearching(true)
    setError(null)
    setSuggestions([])
    try {
      const data = await api.globalSearch(q, filters)
      setResults(data.results || [])
    } catch {
      // Never expose backend/database errors to normal users.
      setError('Unable to search documents right now. Please try again.')
    } finally {
      setSearching(false)
    }
  }

  const applyFilter = (key, value) => {
    const next = { ...filters, [key]: value }
    setFilters(next)
    if (query.trim()) {
      setSearching(true)
      setError(null)
      api
        .globalSearch(query.trim(), next)
        .then((data) => setResults(data.results || []))
        .catch(() => setError('Unable to search documents right now. Please try again.'))
        .finally(() => setSearching(false))
    }
  }

  const clearFilters = () => {
    const next = { category: '', type: '', project_id: '' }
    setFilters(next)
    if (query.trim()) {
      setSearching(true)
      setError(null)
      api
        .globalSearch(query.trim(), next)
        .then((data) => setResults(data.results || []))
        .catch(() => setError('Unable to search documents right now. Please try again.'))
        .finally(() => setSearching(false))
    }
  }

  const clear = () => {
    setQuery('')
    setResults(null)
    setError(null)
    setSuggestions([])
    setFilters({ category: '', type: '', project_id: '' })
  }

  const onDelete = async (r) => {
    if (
      !window.confirm(
        `Are you sure you want to delete "${r.title}"? This will permanently remove the document and all its versions.`,
      )
    )
      return
    setBusyId(r.document_id)
    setError(null)
    try {
      await api.deleteDocument(r.document_id)
      setResults((prev) => (prev ? prev.filter((x) => x.document_id !== r.document_id) : prev))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  const hasActiveFilters = filters.category || filters.type || filters.project_id

  return (
    <div>
      <h1>Search</h1>
      <p className="tagline">Search across all your documents</p>

      <section className="panel">
        <form onSubmit={doSearch} className="search-form">
          <div className="search-box">
            <span className="search-box-icon">{ICONS.search}</span>
            <input
              className="search-input"
              placeholder="Search documents by keyword or meaning..."
              value={query}
              onChange={(e) => {
                setQuery(e.target.value)
                if (!e.target.value) {
                  setResults(null)
                  setSuggestions([])
                }
              }}
              aria-label="Search documents"
            />
            {query && (
              <button
                type="button"
                className="search-clear"
                onClick={clear}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>
          <button
            className="btn btn-primary"
            type="submit"
            disabled={searching || !query.trim()}
          >
            {searching ? 'Searching…' : 'Search'}
          </button>
        </form>

        {suggestions.length > 0 && !searching && !results && (
          <div className="search-suggestions">
            <span className="muted">Suggestions:</span>
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                className="suggestion-chip"
                onClick={() => {
                  setQuery(s)
                  setSuggestions([])
                  api
                    .globalSearch(s, filters)
                    .then((data) => setResults(data.results || []))
                    .catch(() =>
                      setError('Unable to search documents right now. Please try again.'),
                    )
                }}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {filterOptions.categories.length + filterOptions.types.length + filterOptions.projects.length >
          0 && (
          <div className="search-filters">
            <select
              aria-label="Filter by category"
              value={filters.category}
              onChange={(e) => applyFilter('category', e.target.value)}
            >
              <option value="">All categories</option>
              {filterOptions.categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by file type"
              value={filters.type}
              onChange={(e) => applyFilter('type', e.target.value)}
            >
              <option value="">All file types</option>
              {filterOptions.types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by project"
              value={filters.project_id}
              onChange={(e) => applyFilter('project_id', e.target.value)}
            >
              <option value="">All projects</option>
              {filterOptions.projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            {hasActiveFilters && (
              <button
                type="button"
                className="btn btn-small"
                onClick={clearFilters}
              >
                Clear filters
              </button>
            )}
          </div>
        )}

        {!results && !searching && !error && (
          <p className="search-state">
            <span className="search-state-icon">{ICONS.empty}</span>
            Search documents
            <span className="search-state-hint">
              Search across your documents by keyword or meaning.
            </span>
          </p>
        )}

        {searching && <p className="search-state">Searching documents...</p>}

        {results && results.length === 0 && !searching && (
          <p className="search-state">
            No documents found
            <span className="search-state-hint">
              Try different keywords or describe what you're looking for.
            </span>
          </p>
        )}

        {results && results.length > 0 && !searching && (
          <div className="search-results">
            <p className="muted">
              {results.length} result{results.length === 1 ? '' : 's'} for "{query}"
              {hasActiveFilters && ' (filtered)'}
            </p>
            {results.map((r) => (
              <div key={r.document_id} className="search-result">
                <div className="search-result-head">
                  <span className="search-result-title">{r.title}</span>
                  <span className="badge">{r.type}</span>
                  {r.category && <span className="badge">{r.category}</span>}
                  <span className="badge">{r.project_name}</span>
                  {r.relevance > 0 && (
                    <span className="badge badge-relevance">
                      {Math.round(r.relevance * 100)}% relevant
                    </span>
                  )}
                </div>
                <p className="search-result-snippet">{highlight(r.snippet, terms)}</p>
                {r.tags && (
                  <div className="search-result-tags">
                    {r.tags
                      .split(',')
                      .map((t) => t.trim())
                      .filter(Boolean)
                      .map((t) => (
                        <span key={t} className="tag-chip">
                          {t}
                        </span>
                      ))}
                  </div>
                )}
                <div className="search-result-meta">
                  page {r.page_number} · v{r.version} · by {r.uploader_name || 'unknown'} ·{' '}
                  {r.created_at}
                </div>
                <div className="search-result-actions">
                  <button className="btn btn-small" onClick={() => setViewing(r)}>
                    View
                  </button>
                  <button
                    className="btn btn-small btn-danger"
                    onClick={() => onDelete(r)}
                    disabled={busyId === r.document_id}
                  >
                    {busyId === r.document_id ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {error && <p className="error-text">{error}</p>}
      </section>

      {viewing && (
        <DocumentViewer
          doc={{ id: viewing.document_id, title: viewing.title, filename: viewing.filename }}
          onClose={() => setViewing(null)}
        />
      )}
    </div>
  )
}