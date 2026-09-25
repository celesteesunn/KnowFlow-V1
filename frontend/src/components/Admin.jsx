import { useEffect, useState } from 'react'
import { api } from '../api.js'

export default function Admin() {
  const [users, setUsers] = useState(null)
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)

  const load = () =>
    api
      .adminUsers()
      .then((d) => setUsers(d.users))
      .catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const toggle = async (u) => {
    setError(null)
    setMsg(null)
    try {
      const res = await api.toggleAdmin(u.id)
      setMsg(`${res.username} is now ${res.is_admin ? 'an admin' : 'a regular user'}`)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h1>User management</h1>
      <p className="tagline">Manage user accounts and admin roles</p>

      {!users && <p className="muted">Loading…</p>}
      {users && (
        <section className="panel">
          <table className="data-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Full name</th>
                <th>Role</th>
                <th>Projects</th>
                <th>Documents</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>
                    <strong>{u.username}</strong>
                  </td>
                  <td>{u.full_name || '—'}</td>
                  <td>
                    {u.is_admin ? (
                      <span className="badge badge-admin">admin</span>
                    ) : (
                      <span className="badge">user</span>
                    )}
                  </td>
                  <td>{u.project_count}</td>
                  <td>{u.document_count}</td>
                  <td className="muted">{u.created_at}</td>
                  <td>
                    <button className="btn btn-small" onClick={() => toggle(u)}>
                      {u.is_admin ? 'Remove admin' : 'Make admin'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {msg && <p className="ok-text">{msg}</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  )
}