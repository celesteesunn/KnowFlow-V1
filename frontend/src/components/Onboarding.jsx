import { useState } from 'react'
import { api } from '../api.js'

// Position choices for the access request. Selecting "Other" reveals a free
// text field. No position grants admin rights — only creating a workspace
// promotes the creator to Admin / Workspace Owner.
const POSITIONS = [
  'Software Engineer',
  'Senior Software Engineer',
  'Team Lead',
  'Manager',
  'Department Head',
  'Analyst',
  'Intern',
  'HR',
  'HR Admin',
  'Finance',
  'Marketing',
  'Sales',
  'Operations',
  'IT Support',
  'Administrator',
  'Admin / Workspace Owner',
  'Other',
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

const EMPTY_CREATE = {
  name: '',
  description: '',
  code: '',
  org_name: '',
  org_email: '',
  org_website: '',
  timezone: 'UTC',
  language: 'en',
  require_admin_approval: true,
  invite_code_required: true,
  email_domain: '',
}

// Shown to accounts that registered but are still waiting for a workspace
// administrator to approve their access request.
function SuccessScreen({ user, onAuth, onLogout }) {
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
        <h2>Access request submitted</h2>
        <p className="muted">
          Your request has been sent to your organisation's Workspace Admin. You will
          receive access once your request is approved.
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

function ReviewRow({ label, value }) {
  return (
    <div className="review-row">
      <strong>{label}</strong>
      <span>{value || '—'}</span>
    </div>
  )
}

export default function Onboarding({ user, onAuth, onLogout }) {
  const [step, setStep] = useState('choose')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  // Create workspace (Admin / Workspace Owner flow)
  const [create, setCreate] = useState(EMPTY_CREATE)

  // Join workspace (employee flow)
  const [code, setCode] = useState('')
  const [verified, setVerified] = useState(null) // { workspace, departments }
  const [join, setJoin] = useState({ position: '', department: '', employee_id: '' })
  const [otherPosition, setOtherPosition] = useState('')

  if (user.status === 'pending_approval') {
    return <SuccessScreen user={user} onAuth={onAuth} onLogout={onLogout} />
  }

  const set = (key) => (e) => setCreate({ ...create, [key]: e.target.value })
  const setCheck = (key) => (e) => setCreate({ ...create, [key]: e.target.checked })

  const verify = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const data = await api.verifyWorkspace({ code })
      setVerified(data)
      setStep('join-details')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const submitCreate = async () => {
    setBusy(true)
    setError(null)
    try {
      const data = await api.createWorkspace(create)
      onAuth(data.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const submitJoin = async () => {
    setBusy(true)
    setError(null)
    try {
      const position =
        join.position === 'Other' ? otherPosition.trim() : join.position
      const data = await api.requestAccess({
        code,
        position,
        department: join.department,
        employee_id: join.employee_id,
      })
      onAuth(data.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const back = () => {
    setError(null)
    setStep('choose')
  }

  if (step === 'choose') {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h2>Welcome to KnowFlow</h2>
          <p className="muted">Set up your workspace to get started.</p>
          <div className="stack">
            <button className="btn btn-primary" onClick={() => setStep('create')}>
              Create a workspace
            </button>
            <p className="muted">
              I'm an Admin / Workspace Owner setting up my organisation.
            </p>
            <button className="btn" onClick={() => setStep('join')}>
              Join a workspace
            </button>
            <p className="muted">
              I'm an employee joining my organisation's workspace.
            </p>
          </div>
          <button className="link-btn" onClick={onLogout}>
            Log out
          </button>
        </div>
      </div>
    )
  }

  if (step === 'create') {
    return (
      <div className="auth-wrap">
        <div className="auth-card auth-card-wide">
          <h2>Create your workspace</h2>
          <p className="muted">
            You'll become the Admin / Workspace Owner of this workspace.
          </p>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault()
              setStep('create-review')
            }}
          >
            <div>
              <label className="field-label">Workspace name *</label>
              <input
                placeholder="e.g. Acme Technologies"
                value={create.name}
                onChange={set('name')}
                required
              />
            </div>
            <div>
              <label className="field-label">Description</label>
              <textarea
                rows={2}
                placeholder="What does your organisation do?"
                value={create.description}
                onChange={set('description')}
              />
            </div>
            <div>
              <label className="field-label">Workspace code *</label>
              <input
                placeholder="e.g. ABC-2026"
                value={create.code}
                onChange={set('code')}
                required
              />
              <p className="setting-note">
                Employees use this code to request access. 2-32 characters using
                letters, numbers, . _ or -.
              </p>
            </div>
            <div>
              <label className="field-label">Organisation name</label>
              <input
                placeholder="Defaults to the workspace name"
                value={create.org_name}
                onChange={set('org_name')}
              />
            </div>
            <div>
              <label className="field-label">Organisation email</label>
              <input
                type="email"
                placeholder="admin@company.com"
                value={create.org_email}
                onChange={set('org_email')}
              />
            </div>
            <div>
              <label className="field-label">Organisation website</label>
              <input
                placeholder="https://company.com"
                value={create.org_website}
                onChange={set('org_website')}
              />
            </div>
            <div className="form-row">
              <div>
                <label className="field-label">Timezone</label>
                <select value={create.timezone} onChange={set('timezone')}>
                  {TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="field-label">Language</label>
                <select value={create.language} onChange={set('language')}>
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
                placeholder="e.g. @company.com (optional)"
                value={create.email_domain}
                onChange={set('email_domain')}
              />
              <p className="setting-note">
                When set, only people with this email domain can request access.
              </p>
            </div>
            <label className="check-row">
              <input
                type="checkbox"
                checked={create.require_admin_approval}
                onChange={setCheck('require_admin_approval')}
              />
              <span>Require admin approval for new members</span>
            </label>
            <label className="check-row">
              <input
                type="checkbox"
                checked={create.invite_code_required}
                onChange={setCheck('invite_code_required')}
              />
              <span>Require the workspace code to join</span>
            </label>
            {error && <p className="error-text">{error}</p>}
            <div className="settings-edit-actions">
              <button className="btn" type="button" onClick={back}>
                Back
              </button>
              <button className="btn btn-primary">Review</button>
            </div>
          </form>
        </div>
      </div>
    )
  }

  if (step === 'create-review') {
    return (
      <div className="auth-wrap">
        <div className="auth-card auth-card-wide">
          <h2>Review your workspace</h2>
          <p className="muted">Confirm the details below to create your workspace.</p>
          <div className="panel review-panel">
            <ReviewRow label="Workspace name" value={create.name} />
            <ReviewRow label="Description" value={create.description} />
            <ReviewRow label="Workspace code" value={create.code} />
            <ReviewRow label="Organisation name" value={create.org_name} />
            <ReviewRow label="Organisation email" value={create.org_email} />
            <ReviewRow label="Organisation website" value={create.org_website} />
            <ReviewRow label="Timezone" value={create.timezone} />
            <ReviewRow label="Language" value={create.language} />
            <ReviewRow label="Email domain" value={create.email_domain} />
            <ReviewRow
              label="Admin approval"
              value={create.require_admin_approval ? 'Required' : 'Not required'}
            />
            <ReviewRow
              label="Invite code"
              value={create.invite_code_required ? 'Required' : 'Not required'}
            />
          </div>
          {error && <p className="error-text">{error}</p>}
          <div className="settings-edit-actions">
            <button className="btn" onClick={() => setStep('create')} disabled={busy}>
              Back
            </button>
            <button className="btn btn-primary" onClick={submitCreate} disabled={busy}>
              {busy ? 'Creating…' : 'Create workspace'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (step === 'join') {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <h2>Join a workspace</h2>
          <p className="muted">
            Enter the workspace code provided by your organisation's administrator.
          </p>
          <form className="stack" onSubmit={verify}>
            <input
              placeholder="Workspace code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
            {error && <p className="error-text">{error}</p>}
            <div className="settings-edit-actions">
              <button className="btn" type="button" onClick={back} disabled={busy}>
                Back
              </button>
              <button className="btn btn-primary" disabled={busy}>
                {busy ? 'Checking…' : 'Continue'}
              </button>
            </div>
          </form>
        </div>
      </div>
    )
  }

  if (step === 'join-details') {
    const position = join.position === 'Other' ? otherPosition.trim() : join.position
    const canContinue =
      position && join.department && join.employee_id.trim()
    return (
      <div className="auth-wrap">
        <div className="auth-card auth-card-wide">
          <h2>Request access</h2>
          <p className="muted">
            Joining <strong>{verified.workspace.name}</strong>
            {verified.workspace.description ? ` — ${verified.workspace.description}` : ''}.
          </p>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault()
              setStep('join-review')
            }}
          >
            <div>
              <label className="field-label">Position *</label>
              <select
                value={join.position}
                onChange={(e) => setJoin({ ...join, position: e.target.value })}
                required
              >
                <option value="">Select your position…</option>
                {POSITIONS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>
            {join.position === 'Other' && (
              <div>
                <label className="field-label">Your position *</label>
                <input
                  placeholder="e.g. Data Analyst"
                  value={otherPosition}
                  onChange={(e) => setOtherPosition(e.target.value)}
                  required
                />
              </div>
            )}
            <div>
              <label className="field-label">Department *</label>
              <select
                value={join.department}
                onChange={(e) => setJoin({ ...join, department: e.target.value })}
                required
              >
                <option value="">Select your department…</option>
                {verified.departments.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label">Employee ID *</label>
              <input
                placeholder="e.g. EMP-1001"
                value={join.employee_id}
                onChange={(e) => setJoin({ ...join, employee_id: e.target.value })}
                required
              />
              <p className="setting-note">
                Your employee ID must be unique within this workspace.
              </p>
            </div>
            {error && <p className="error-text">{error}</p>}
            <div className="settings-edit-actions">
              <button
                className="btn"
                type="button"
                onClick={() => setStep('join')}
                disabled={busy}
              >
                Back
              </button>
              <button className="btn btn-primary" disabled={!canContinue}>
                Review
              </button>
            </div>
          </form>
        </div>
      </div>
    )
  }

  // join-review
  const position = join.position === 'Other' ? otherPosition.trim() : join.position
  return (
    <div className="auth-wrap">
      <div className="auth-card auth-card-wide">
        <h2>Review your request</h2>
        <p className="muted">
          Your request will be sent to the administrators of{' '}
          <strong>{verified.workspace.name}</strong>.
        </p>
        <div className="panel review-panel">
          <ReviewRow label="Workspace" value={verified.workspace.name} />
          <ReviewRow label="Position" value={position} />
          <ReviewRow label="Department" value={join.department} />
          <ReviewRow label="Employee ID" value={join.employee_id} />
        </div>
        {error && <p className="error-text">{error}</p>}
        <div className="settings-edit-actions">
          <button
            className="btn"
            onClick={() => setStep('join-details')}
            disabled={busy}
          >
            Back
          </button>
          <button className="btn btn-primary" onClick={submitJoin} disabled={busy}>
            {busy ? 'Submitting…' : 'Submit request'}
          </button>
        </div>
      </div>
    </div>
  )
}