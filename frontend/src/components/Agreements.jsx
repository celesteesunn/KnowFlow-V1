import { useState } from 'react'
import { api } from '../api.js'

// Shown to pending_approval accounts that still have to accept the
// Terms & Conditions and the Security & Confidentiality agreement.
export default function Agreements({ user, onAuth }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const acceptTerms = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await api.acceptTerms()
      onAuth(data.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const acceptSecurity = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await api.acceptSecurity()
      onAuth(data.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h2>Welcome, {user.full_name || user.username}</h2>
        <p className="muted">Please review and accept the agreements to continue.</p>

        {!user.terms_accepted && (
          <section className="panel">
            <h2>Terms &amp; Conditions</h2>
            <p className="agree-text">
              KnowFlow is an enterprise knowledge management platform. By using
              this system you agree to use it solely for authorised business
              purposes, to keep your credentials confidential, and to comply with
              the organisation's acceptable-use and data-handling policies.
            </p>
            <button className="btn btn-primary" onClick={acceptTerms} disabled={busy}>
              Accept Terms &amp; Conditions
            </button>
          </section>
        )}

        {user.terms_accepted && !user.security_agreed && (
          <section className="panel">
            <h2>Security &amp; Confidentiality</h2>
            <p className="agree-text">
              You are granted access to confidential company documents. You agree
              not to disclose, copy, or share any information you access through
              KnowFlow outside the organisation, and to report any suspected
              security incident immediately.
            </p>
            <button className="btn btn-primary" onClick={acceptSecurity} disabled={busy}>
              Accept Security &amp; Confidentiality
            </button>
          </section>
        )}

        {error && <p className="error-text">{error}</p>}
      </div>
    </div>
  )
}