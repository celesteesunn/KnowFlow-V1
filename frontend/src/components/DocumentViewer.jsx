import { useEffect, useState } from 'react'
import { api } from '../api.js'

// In-app document viewer. PDFs render inside the application using the
// browser's native PDF rendering (iframe pointing at the inline /view
// endpoint). DOCX/TXT files cannot be rendered inline by the browser, so
// their extracted text is shown instead (the same text used for search).
// Close via the button, clicking the backdrop, or pressing Escape.
export default function DocumentViewer({ doc, onClose }) {
  const [text, setText] = useState(null)
  const [textError, setTextError] = useState(false)
  const isPdf = (doc.filename || '').toLowerCase().endsWith('.pdf')

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (isPdf) return
    let cancelled = false
    api
      .documentText(doc.id)
      .then((data) => {
        if (!cancelled) setText(data.text || '')
      })
      .catch(() => {
        if (!cancelled) setTextError(true)
      })
    return () => {
      cancelled = true
    }
  }, [doc.id, isPdf])

  return (
    <div className="viewer-overlay" onClick={onClose}>
      <div className="viewer-modal" onClick={(e) => e.stopPropagation()}>
        <div className="viewer-header">
          <span className="viewer-title">{doc.title || doc.filename}</span>
          <a className="btn btn-small" href={api.downloadUrl(doc.id)}>
            Download
          </a>
          <button className="btn btn-small" onClick={onClose}>
            Close
          </button>
        </div>
        {isPdf ? (
          <iframe
            className="viewer-frame"
            src={api.viewUrl(doc.id)}
            title={doc.filename}
          />
        ) : textError ? (
          <div className="viewer-text viewer-text-empty">
            <p>Unable to load the document text.</p>
            <a className="btn btn-small" href={api.downloadUrl(doc.id)}>
              Download the file instead
            </a>
          </div>
        ) : text === null ? (
          <div className="viewer-text viewer-text-empty">Loading text…</div>
        ) : (
          <pre className="viewer-text">{text}</pre>
        )}
      </div>
    </div>
  )
}