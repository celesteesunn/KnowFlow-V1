import { useState } from 'react'
import { api } from '../api.js'

export default function Login({ onAuth, message }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({
    username: '',
    password: '',
    confirm_password: '',
    full_name: '',
    email: '',
    phone: '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (mode === 'register' && form.password !== form.confirm_password) {
      setError('Passwords do not match')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const fn = mode === 'login' ? api.login : api.register
      const data = await fn(form)
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
        <h2>{mode === 'login' ? 'Sign in' : 'Create account'}</h2>
        <p className="muted">Enterprise Knowledge &amp; Collaboration Platform</p>
        {message && <p className="ok-text login-message">{message}</p>}
        <form onSubmit={submit} className="stack">
          {mode === 'register' && (
            <>
              <input
                placeholder="Full name"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              />
              <input
                type="email"
                placeholder="Email address"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                required
              />
              <input
                type="tel"
                placeholder="Phone number (optional)"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </>
          )}
          <input
            placeholder="Username"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
            required
          />
          <input
            type="password"
            placeholder="Password (6+ characters)"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
          />
          {mode === 'register' && (
            <input
              type="password"
              placeholder="Confirm password"
              value={form.confirm_password}
              onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
              required
            />
          )}
          {error && <p className="error-text">{error}</p>}
          <button className="btn btn-primary" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Register'}
          </button>
        </form>
        <button
          className="link-btn"
          onClick={() => {
            setMode(mode === 'login' ? 'register' : 'login')
            setError(null)
          }}
        >
          {mode === 'login' ? 'Need an account? Register' : 'Have an account? Sign in'}
        </button>
      </div>
    </div>
  )
}