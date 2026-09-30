import { useEffect, useState } from 'react'
import { api } from '../api.js'

const STATUS_LABEL = {
  pending_approval: 'Pending approval',
  active: 'Active',
  rejected: 'Rejected',
  suspended: 'Suspended',
}

// Permission keys used by the backend role definitions.
const PERMISSIONS = [
  ['manage_workspace', 'Manage workspace'],
  ['manage_members', 'Manage members'],
  ['manage_roles', 'Manage roles'],
  ['manage_departments', 'Manage departments'],
  ['view_insights', 'View insights'],
  ['manage_documents', 'Manage documents'],
  ['manage_projects', 'Manage projects'],
]

const TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
  'Africa/Johannesburg',
  'America/Sao_Paulo',
]

const LANGUAGES = [
  ['en', 'English'],
  ['es', 'Spanish'],
  ['fr', 'French'],
  ['de', 'German'],
  ['hi', 'Hindi'],
  ['ar', 'Arabic'],
  ['zh', 'Chinese'],
  ['ja', 'Japanese'],
]

// ---------------------------------------------------------------------------
// Access Requests
// ---------------------------------------------------------------------------

function AccessRequestsTab() {
  const [requests, setRequests] = useState(null)
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)

  const load = () =>
    api
      .adminAccessRequests()
      .then((d) => setRequests(d.requests))
      .catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const act = async (fn, successText) => {
    setError(null)
    setMsg(null)
    try {
      const res = await fn()
      setMsg(successText(res))
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const approve = (r) =>
    act(
      () => api.adminApproveRequest(r.id),
      (res) => `${res.username} approved — account is now active`
    )

  const reject = (r) => {
    const reason = window.prompt(
      `Reason for rejecting ${r.full_name || r.username}? (optional)`,
      ''
    )
    if (reason === null) return
    act(
      () => api.adminRejectRequest(r.id, reason),
      (res) => `${res.username} rejected`
    )
  }

  return (
    <section className="panel">
      {!requests && <p className="muted">Loading…</p>}
      {requests && requests.length === 0 && (
        <div className="empty-state">
          <span className="empty-state-title">No pending requests</span>
          <span className="empty-state-text">
            New access requests from employees will appear here.
          </span>
        </div>
      )}
      {requests && requests.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Applicant</th>
              <th>Position</th>
              <th>Department</th>
              <th>Employee ID</th>
              <th>Requested</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {requests.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.full_name || r.username}</strong>
                  {r.email && <div className="muted">{r.email}</div>}
                  {r.phone && <div className="muted">{r.phone}</div>}
                </td>
                <td>{r.position}</td>
                <td>{r.department}</td>
                <td>{r.employee_id}</td>
                <td className="muted">{r.access_requested_at}</td>
                <td>
                  <div className="doc-actions">
                    <button className="btn btn-small" onClick={() => approve(r)}>
                      Approve
                    </button>
                    <button
                      className="btn btn-small btn-danger"
                      onClick={() => reject(r)}
                    >
                      Reject
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {msg && <p className="ok-text">{msg}</p>}
      {error && <p className="error-text">{error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Members (existing user management)
// ---------------------------------------------------------------------------

function MembersTab() {
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

  const act = async (fn, successText) => {
    setError(null)
    setMsg(null)
    try {
      const res = await fn()
      setMsg(successText(res))
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const toggle = (u) =>
    act(
      () => api.toggleAdmin(u.id),
      (res) => `${res.username} is now ${res.is_admin ? 'an admin' : 'a regular user'}`
    )

  const approve = (u) =>
    act(
      () => api.adminApprove(u.id),
      (res) => `${res.username} approved — account is now active`
    )

  const reject = (u) => {
    const reason = window.prompt(`Reason for rejecting ${u.username}?`, '')
    if (reason === null) return
    act(
      () => api.adminReject(u.id, reason),
      (res) => `${res.username} rejected`
    )
  }

  const suspend = (u) => {
    const reason = window.prompt(`Reason for suspending ${u.username}?`, '')
    if (reason === null) return
    act(
      () => api.adminSuspend(u.id, reason),
      (res) => `${res.username} suspended`
    )
  }

  const reactivate = (u) =>
    act(
      () => api.adminReactivate(u.id),
      (res) => `${res.username} reactivated — account is now active`
    )

  return (
    <section className="panel">
      {!users && <p className="muted">Loading…</p>}
      {users && (
        <table className="data-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Full name</th>
              <th>Role</th>
              <th>Status</th>
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
                  {u.email && <div className="muted">{u.email}</div>}
                </td>
                <td>{u.full_name || '—'}</td>
                <td>
                  {u.is_admin ? (
                    <span className="badge badge-admin">admin</span>
                  ) : (
                    <span className="badge">user</span>
                  )}
                </td>
                <td>
                  <span className={`badge status-${u.status}`}>
                    {STATUS_LABEL[u.status] || u.status}
                  </span>
                </td>
                <td>{u.project_count}</td>
                <td>{u.document_count}</td>
                <td className="muted">{u.created_at}</td>
                <td>
                  <div className="doc-actions">
                    {u.status === 'pending_approval' && (
                      <>
                        <button className="btn btn-small" onClick={() => approve(u)}>
                          Approve
                        </button>
                        <button
                          className="btn btn-small btn-danger"
                          onClick={() => reject(u)}
                        >
                          Reject
                        </button>
                      </>
                    )}
                    {u.status === 'active' && (
                      <button
                        className="btn btn-small btn-danger"
                        onClick={() => suspend(u)}
                      >
                        Suspend
                      </button>
                    )}
                    {u.status === 'suspended' && (
                      <button className="btn btn-small" onClick={() => reactivate(u)}>
                        Reactivate
                      </button>
                    )}
                    <button className="btn btn-small" onClick={() => toggle(u)}>
                      {u.is_admin ? 'Remove admin' : 'Make admin'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {msg && <p className="ok-text">{msg}</p>}
      {error && <p className="error-text">{error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

function RolesTab() {
  const [roles, setRoles] = useState(null)
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)
  const [editing, setEditing] = useState(null) // role being edited
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [perms, setPerms] = useState({})

  const load = () =>
    api
      .adminRoles()
      .then((d) => setRoles(d.roles))
      .catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const togglePerm = (key) => setPerms({ ...perms, [key]: !perms[key] })

  const startCreate = () => {
    setError(null)
    setMsg(null)
    setName('')
    setPerms({})
    setCreating(true)
    setEditing(null)
  }

  const startEdit = (r) => {
    setError(null)
    setMsg(null)
    setName(r.name)
    setPerms({ ...r.permissions })
    setEditing(r)
    setCreating(false)
  }

  const cancel = () => {
    setCreating(false)
    setEditing(null)
    setError(null)
  }

  const save = async (e) => {
    e.preventDefault()
    setError(null)
    setMsg(null)
    try {
      if (editing) {
        await api.adminUpdateRole(editing.id, { name, permissions: perms })
        setMsg('Role updated')
      } else {
        await api.adminCreateRole({ name, permissions: perms })
        setMsg('Role created')
      }
      setCreating(false)
      setEditing(null)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async (r) => {
    if (!window.confirm(`Delete role "${r.name}"?`)) return
    setError(null)
    setMsg(null)
    try {
      await api.adminDeleteRole(r.id)
      setMsg('Role deleted')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="panel">
      <div className="card-head">
        <h2>Roles &amp; permissions</h2>
        {!creating && !editing && (
          <button className="btn btn-small" onClick={startCreate}>
            New role
          </button>
        )}
      </div>
      <p className="muted">
        Permissions are explicitly configured per role. Admin access itself is
        controlled separately by the Admin flag on each member.
      </p>

      {(creating || editing) && (
        <form onSubmit={save} className="stack role-editor">
          <div>
            <label className="field-label">Role name</label>
            <input
              placeholder="e.g. Content Editor"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="field-label">Permissions</label>
            <div className="perm-grid">
              {PERMISSIONS.map(([key, label]) => (
                <label key={key} className="check-row">
                  <input
                    type="checkbox"
                    checked={!!perms[key]}
                    onChange={() => togglePerm(key)}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="settings-edit-actions">
            <button className="btn" type="button" onClick={cancel}>
              Cancel
            </button>
            <button className="btn btn-primary" disabled={!name.trim()}>
              {editing ? 'Save changes' : 'Create role'}
            </button>
          </div>
        </form>
      )}

      {!roles && <p className="muted">Loading…</p>}
      {roles && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Role</th>
              <th>Permissions</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {roles.map((r) => (
              <tr key={r.id}>
                <td>
                  <strong>{r.name}</strong>
                  {r.is_system && <span className="badge">system</span>}
                </td>
                <td>
                  <div className="perm-chips">
                    {PERMISSIONS.filter(([key]) => r.permissions[key]).map(
                      ([key, label]) => (
                        <span key={key} className="badge">
                          {label}
                        </span>
                      )
                    )}
                    {PERMISSIONS.every(([key]) => !r.permissions[key]) && (
                      <span className="muted">No permissions</span>
                    )}
                  </div>
                </td>
                <td>
                  <div className="doc-actions">
                    <button className="btn btn-small" onClick={() => startEdit(r)}>
                      Edit
                    </button>
                    {!r.is_system && (
                      <button
                        className="btn btn-small btn-danger"
                        onClick={() => remove(r)}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {msg && <p className="ok-text">{msg}</p>}
      {error && <p className="error-text">{error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Departments
// ---------------------------------------------------------------------------

function DepartmentsTab() {
  const [departments, setDepartments] = useState(null)
  const [name, setName] = useState('')
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)

  const load = () =>
    api
      .adminDepartments()
      .then((d) => setDepartments(d.departments))
      .catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const add = async (e) => {
    e.preventDefault()
    setError(null)
    setMsg(null)
    try {
      await api.adminCreateDepartment({ name })
      setName('')
      setMsg('Department added')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const remove = async (d) => {
    if (!window.confirm(`Delete department "${d.name}"?`)) return
    setError(null)
    setMsg(null)
    try {
      await api.adminDeleteDepartment(d.id)
      setMsg('Department deleted')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="panel">
      <div className="card-head">
        <h2>Departments</h2>
      </div>
      <form onSubmit={add} className="inline-form">
        <input
          placeholder="New department name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <button className="btn btn-primary" disabled={!name.trim()}>
          Add department
        </button>
      </form>
      {!departments && <p className="muted">Loading…</p>}
      {departments && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Department</th>
              <th>Members</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {departments.map((d) => (
              <tr key={d.id}>
                <td>
                  <strong>{d.name}</strong>
                </td>
                <td>{d.member_count}</td>
                <td>
                  <button
                    className="btn btn-small btn-danger"
                    onClick={() => remove(d)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {msg && <p className="ok-text">{msg}</p>}
      {error && <p className="error-text">{error}</p>}
    </section>
  )
}

// ---------------------------------------------------------------------------
// Workspace settings
// ---------------------------------------------------------------------------

function WorkspaceTab() {
  const [ws, setWs] = useState(null)
  const [form, setForm] = useState(null)
  const [error, setError] = useState(null)
  const [msg, setMsg] = useState(null)

  const load = () =>
    api
      .adminWorkspace()
      .then((d) => {
        setWs(d.workspace)
        setForm({
          name: d.workspace.name,
          description: d.workspace.description || '',
          org_name: d.workspace.org_name || '',
          org_email: d.workspace.org_email || '',
          org_website: d.workspace.org_website || '',
          timezone: d.workspace.timezone,
          language: d.workspace.language,
          require_admin_approval: d.workspace.require_admin_approval,
          invite_code_required: d.workspace.invite_code_required,
          email_domain: d.workspace.email_domain || '',
        })
      })
      .catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })
  const setCheck = (key) => (e) => setForm({ ...form, [key]: e.target.checked })

  const save = async (e) => {
    e.preventDefault()
    setError(null)
    setMsg(null)
    try {
      await api.adminUpdateWorkspace(form)
      setMsg('Workspace settings saved')
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  const regen = async () => {
    if (
      !window.confirm(
        'Regenerate the workspace code? Previously approved members keep their access.'
      )
    )
      return
    setError(null)
    setMsg(null)
    try {
      const res = await api.adminRegenerateCode()
      setMsg(`New workspace code: ${res.code}`)
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  if (!ws || !form) {
    return (
      <section className="panel">
        <p className="muted">Loading…</p>
        {error && <p className="error-text">{error}</p>}
      </section>
    )
  }

  return (
    <section className="panel">
      <div className="card-head">
        <h2>Workspace settings</h2>
      </div>
      <div className="company-block">
        <div className="company-row">
          <strong>Workspace code</strong>
          <span>
            <code className="ws-code">{ws.code}</code>{' '}
            <button className="btn btn-small" onClick={regen}>
              Regenerate
            </button>
          </span>
        </div>
        <p className="setting-note">
          Employees use this code to request access. Regenerating it never revokes
          previously approved members.
        </p>
      </div>
      <form onSubmit={save} className="stack">
        <div>
          <label className="field-label">Workspace name</label>
          <input value={form.name} onChange={set('name')} required />
        </div>
        <div>
          <label className="field-label">Description</label>
          <textarea
            rows={2}
            value={form.description}
            onChange={set('description')}
          />
        </div>
        <div>
          <label className="field-label">Organisation name</label>
          <input value={form.org_name} onChange={set('org_name')} />
        </div>
        <div>
          <label className="field-label">Organisation email</label>
          <input
            type="email"
            value={form.org_email}
            onChange={set('org_email')}
          />
        </div>
        <div>
          <label className="field-label">Organisation website</label>
          <input value={form.org_website} onChange={set('org_website')} />
        </div>
        <div className="form-row">
          <div>
            <label className="field-label">Timezone</label>
            <select value={form.timezone} onChange={set('timezone')}>
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label">Language</label>
            <select value={form.language} onChange={set('language')}>
              {LANGUAGES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="field-label">Restrict to email domain</label>
          <input
            placeholder="e.g. @company.com"
            value={form.email_domain}
            onChange={set('email_domain')}
          />
        </div>
        <label className="check-row">
          <input
            type="checkbox"
            checked={form.require_admin_approval}
            onChange={setCheck('require_admin_approval')}
          />
          <span>Require admin approval for new members</span>
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={form.invite_code_required}
            onChange={setCheck('invite_code_required')}
          />
          <span>Require the workspace code to join</span>
        </label>
        {msg && <p className="ok-text">{msg}</p>}
        {error && <p className="error-text">{error}</p>}
        <div className="settings-edit-actions">
          <button className="btn btn-primary">Save settings</button>
        </div>
      </form>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Admin page
// ---------------------------------------------------------------------------

const TABS = [
  ['requests', 'Access Requests'],
  ['members', 'Members'],
  ['roles', 'Roles'],
  ['departments', 'Departments'],
  ['workspace', 'Workspace'],
]

export default function Admin() {
  const [tab, setTab] = useState('requests')

  return (
    <div>
      <h1>Admin</h1>
      <p className="tagline">
        Manage access requests, members, roles, departments and workspace settings
      </p>

      <div className="admin-tabs">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            className={`admin-tab${tab === id ? ' admin-tab-active' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'requests' && <AccessRequestsTab />}
      {tab === 'members' && <MembersTab />}
      {tab === 'roles' && <RolesTab />}
      {tab === 'departments' && <DepartmentsTab />}
      {tab === 'workspace' && <WorkspaceTab />}
    </div>
  )
}