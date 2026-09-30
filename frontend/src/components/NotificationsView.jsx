import { useEffect, useState } from 'react'
import { api } from '../api.js'

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
  bell: icon(
    <>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </>,
  ),
}

export default function NotificationsView() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)

  const load = () =>
    api
      .notifications()
      .then((d) => setItems(d.notifications))
      .catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const markRead = async (n) => {
    try {
      await api.markNotificationRead(n.id)
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  const markAll = async () => {
    setError(null)
    setMsg(null)
    try {
      await api.markAllNotificationsRead()
      setMsg('All notifications marked as read')
      load()
    } catch (e) {
      setError(e.message)
    }
  }

  const unread = items ? items.filter((n) => !n.is_read).length : 0

  return (
    <div>
      <h1>Notifications</h1>
      <p className="tagline">Updates about your workspace, access and knowledge</p>

      <section className="panel">
        <div className="card-head">
          <h2>
            {items ? `${items.length} notification${items.length === 1 ? '' : 's'}` : '…'}
            {unread > 0 && <span className="badge badge-admin"> {unread} unread</span>}
          </h2>
          {items && unread > 0 && (
            <button className="btn btn-small" onClick={markAll}>
              Mark all as read
            </button>
          )}
        </div>

        {!items && <p className="muted">Loading…</p>}
        {items && items.length === 0 && (
          <div className="empty-state">
            {ICONS.bell}
            <span className="empty-state-title">No notifications yet</span>
            <span className="empty-state-text">
              Workspace updates, access request outcomes and other activity will
              appear here.
            </span>
          </div>
        )}
        {items && items.length > 0 && (
          <ul className="notif-list">
            {items.map((n) => (
              <li
                key={n.id}
                className={`notif-item${n.is_read ? '' : ' notif-item-unread'}`}
              >
                <div className="notif-main">
                  <span className="notif-message">{n.message}</span>
                  <span className="notif-meta muted">{n.created_at}</span>
                </div>
                {!n.is_read && (
                  <button className="btn btn-small" onClick={() => markRead(n)}>
                    Mark read
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {msg && <p className="ok-text">{msg}</p>}
        {error && <p className="error-text">{error}</p>}
      </section>
    </div>
  )
}