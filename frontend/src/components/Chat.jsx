import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

export default function Chat({ project, onBack, showBack = true }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  const send = async (e) => {
    e.preventDefault()
    const q = input.trim()
    if (!q || busy) return
    setInput('')
    setError(null)
    setMessages((m) => [...m, { role: 'user', content: q }])
    setBusy(true)
    try {
      const res = await api.chat(project.id, q)
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: res.answer, sources: res.sources, mode: res.mode },
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      {showBack && (
        <button className="link-btn" onClick={onBack}>
          ← {project.name}
        </button>
      )}
      <h1>Chat with the AI assistant</h1>
      <p className="tagline">
        The assistant answers using only the documents in this project.
      </p>

      <div className="chat-window">
        {messages.length === 0 && !busy && (
          <p className="muted">Ask anything about the documents in this project.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            <div className="chat-bubble">{m.content}</div>
            {m.sources && m.sources.length > 0 && (
              <div className="sources">
                <strong>Sources:</strong>
                <ul>
                  {m.sources.map((s, j) => (
                    <li key={j}>
                      {s.document} — page {s.page} (score {s.score})
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
        {busy && (
          <div className="chat-msg chat-assistant">
            <div className="chat-bubble muted">Thinking…</div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <p className="error-text">{error}</p>}

      <form onSubmit={send} className="chat-form">
        <input
          placeholder="Ask a question about the documents…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <button className="btn btn-primary" disabled={busy || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}