import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import Markdown, { SourceList } from './Markdown.jsx'

export default function Chat({ project, onBack, showBack = true }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  // The conversation is stored server-side per project, so the transcript
  // survives a reload and a follow-up keeps its referent. Re-fetch when the
  // project changes, since history is scoped to one project.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .chatHistory(project.id)
      .then((res) => {
        if (cancelled) return
        setMessages(
          (res.history || []).map((t) => ({
            role: t.role,
            content: t.content,
            sources: t.sources || [],
          }))
        )
      })
      .catch(() => {
        // A failed history load is not worth interrupting the user for; they
        // can still ask questions, they just start without the transcript.
        if (!cancelled) setMessages([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [project.id])

  const newConversation = async () => {
    if (busy) return
    setError(null)
    setMessages([])
    try {
      await api.clearChatHistory(project.id)
    } catch (err) {
      // The local transcript is already cleared; a stale server-side history
      // only means a future follow-up may resolve against an older topic.
      setError(err.message)
    }
  }

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
      <div className="chat-header">
        <h1>Chat with the AI assistant</h1>
        {messages.length > 0 && (
          <button
            className="link-btn"
            onClick={newConversation}
            disabled={busy}
            title="Clear this conversation and start again"
          >
            New chat
          </button>
        )}
      </div>
      <p className="tagline">
        The assistant answers using only the documents in this project, and
        remembers this conversation so follow-up questions work.
      </p>

      <div className="chat-window">
        {loading && <p className="muted">Loading conversation…</p>}
        {!loading && messages.length === 0 && !busy && (
          <p className="muted">Ask anything about the documents in this project.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-${m.role}`}>
            {m.role === 'assistant' ? (
              <div className="chat-bubble chat-answer">
                <Markdown text={m.content} mode={m.mode} />
                <SourceList sources={m.sources} />
              </div>
            ) : (
              <div className="chat-bubble">{m.content}</div>
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