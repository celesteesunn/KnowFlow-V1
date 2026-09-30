import { useState } from 'react'
import { api } from '../api.js'

// Shown to accounts that registered but are still waiting for an
// administrator to approve them.
export default function PendingApproval({ user, onAuth, onLogout }) {
  const [busy, setBusy] = useState(false)

  const refresh = async () => {
    setBusy(true)
    try {
      const data = await api.me()
      onAuth(data.user)
    } catch {
      // keep the current screen
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h2>Awaiting approval</h2>
        <p className="muted">
          Your request has been sent to your organisation's Workspace Admin. You
          will receive access once your request is approved.
        </p>
        <p className="muted">
          Signed in as <strong>{user.username}</strong> ({user.email}).
        </p>
        <div className="actions">
          <button className="btn btn-primary" onClick={refresh} disabled={busy}>
            Check status
          </button>
          <button className="btn" onClick={onLogout}>
            Log out
          </button>
        </div>
      </div>
    </div>
  )
}