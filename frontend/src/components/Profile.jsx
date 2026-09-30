import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { setUnsaved } from '../unsaved.js'

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

const MAX_AVATAR_MB = 2

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
  linkedin: icon(
    <>
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6z" />
      <rect x="2" y="9" width="4" height="12" />
      <circle cx="4" cy="4" r="2" />
    </>,
  ),
  github: icon(
    <>
      <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
    </>,
  ),
  upload: icon(
    <>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </>,
  ),
  update: icon(
    <>
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </>,
  ),
  view: icon(
    <>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </>,
  ),
  archive: icon(
    <>
      <polyline points="21 8 21 21 3 21 3 8" />
      <rect x="1" y="3" width="22" height="5" />
      <line x1="10" y1="12" x2="14" y2="12" />
    </>,
  ),
  delete: icon(
    <>
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </>,
  ),
  project: icon(
    <>
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </>,
  ),
  search: icon(
    <>
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </>,
  ),
  ai: icon(
    <>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </>,
  ),
  knowledge: icon(
    <>
      <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
      <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </>,
  ),
  signin: icon(
    <>
      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
      <polyline points="10 17 15 12 10 7" />
      <line x1="15" y1="12" x2="3" y2="12" />
    </>,
  ),
}

// Activity type -> display label, filter tab and icon.
const ACTIVITY_META = {
  sign_in: { label: 'Sign in', tab: 'signins', icon: 'signin' },
  document_upload: { label: 'Document Upload', tab: 'uploads', icon: 'upload' },
  document_update: { label: 'Document Update', tab: 'updates', icon: 'update' },
  document_view: { label: 'Document View', tab: 'updates', icon: 'view' },
  document_archive: { label: 'Document Archived', tab: 'updates', icon: 'archive' },
  document_delete: { label: 'Document Deleted', tab: 'updates', icon: 'delete' },
  project_create: { label: 'Project Created', tab: 'updates', icon: 'project' },
  search: { label: 'Search', tab: 'ai_search', icon: 'search' },
  ai_question: { label: 'AI Question', tab: 'ai_search', icon: 'ai' },
  knowledge_access: { label: 'Knowledge Access', tab: 'knowledge', icon: 'knowledge' },
}

// Filter tabs. Comments is intentionally absent: the platform has no
// comment feature, so that tab would never have data.
const TABS = [
  { id: 'all', label: 'All' },
  { id: 'uploads', label: 'Uploads' },
  { id: 'updates', label: 'Updates' },
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'ai_search', label: 'AI & Search' },
  { id: 'signins', label: 'Sign-ins' },
]

function initials(user) {
  const name = (user.full_name || user.username || '?').trim()
  const parts = name.split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

function joinedDate(createdAt) {
  if (!createdAt) return null
  const m = String(createdAt).match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return String(createdAt)
  const [, y, mo, d] = m
  return `${MONTHS[Number(mo) - 1]} ${Number(d)}, ${y}`
}

// SQLite datetime('now') values are UTC; treat them as such.
function relativeTime(iso) {
  if (!iso) return null
  const d = new Date(String(iso).replace(' ', 'T') + 'Z')
  if (Number.isNaN(d.getTime())) return null
  const diff = Date.now() - d.getTime()
  if (diff < 60 * 1000) return 'just now'
  const m = Math.floor(diff / 60000)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const days = Math.floor(h / 24)
  if (days < 7) return `${days}d ago`
  const weeks = Math.floor(days / 7)
  if (weeks < 5) return `${weeks}w ago`
  return joinedDate(String(iso).slice(0, 10))
}

// My Profile — enterprise employee profile with real activity data.
export default function Profile({ user, onAuth, onOpenProject, onOpenDocument }) {
  const [activity, setActivity] = useState(null) // null = loading
  const [projects, setProjects] = useState(null)
  const [tab, setTab] = useState('all')
  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState({
    full_name: user.full_name || '',
    email: user.email || '',
    position: user.position || '',
    department: user.department || '',
    linkedin_url: user.linkedin_url || '',
    github_url: user.github_url || '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)
  const [photoBusy, setPhotoBusy] = useState(false)
  const [photoMsg, setPhotoMsg] = useState(null)
  const [photoError, setPhotoError] = useState(null)
  const photoInput = useRef(null)

  useEffect(() => {
    api
      .profileActivity()
      .then((d) => setActivity(d.activity || []))
      .catch(() => setActivity([]))
    api
      .projects()
      .then((d) => setProjects(d.projects || []))
      .catch(() => setProjects([]))
  }, [])

  // Keep the edit form in sync with the latest user object (after saves).
  useEffect(() => {
    setForm({
      full_name: user.full_name || '',
      email: user.email || '',
      position: user.position || '',
      department: user.department || '',
      linkedin_url: user.linkedin_url || '',
      github_url: user.github_url || '',
    })
  }, [user])

  // Clear the unsaved flag when the profile view unmounts.
  useEffect(() => () => setUnsaved('profile-edit', false), [])

  // Update one edit-form field and mark the form as having unsaved changes.
  const setField = (patch) => {
    setForm((f) => ({ ...f, ...patch }))
    setUnsaved('profile-edit', true)
  }

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      const data = await api.updateProfile(form)
      onAuth(data.user)
      setUnsaved('profile-edit', false)
      setSaved(true)
      setEditOpen(false)
      window.setTimeout(() => setSaved(false), 4000)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const onPhoto = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setPhotoError('Please choose an image file (PNG, JPG, GIF or WebP).')
      setPhotoMsg(null)
      e.target.value = ''
      return
    }
    if (file.size > MAX_AVATAR_MB * 1024 * 1024) {
      setPhotoError(`Image too large. Maximum size is ${MAX_AVATAR_MB} MB.`)
      setPhotoMsg(null)
      e.target.value = ''
      return
    }
    setPhotoBusy(true)
    setPhotoError(null)
    setPhotoMsg(null)
    try {
      const data = await api.uploadAvatar(file)
      onAuth(data.user)
      setPhotoMsg('Profile picture updated.')
    } catch (err) {
      setPhotoError(err.message)
    } finally {
      setPhotoBusy(false)
      e.target.value = ''
    }
  }

  const onRemovePhoto = async () => {
    if (!window.confirm('Remove your profile picture?')) return
    setPhotoBusy(true)
    setPhotoError(null)
    setPhotoMsg(null)
    try {
      const data = await api.removeAvatar()
      onAuth(data.user)
      setPhotoMsg('Profile picture removed.')
    } catch (err) {
      setPhotoError(err.message)
    } finally {
      setPhotoBusy(false)
    }
  }

  const openRef = async (a) => {
    if (a.ref_type === 'project') {
      const p = (projects || []).find((x) => x.id === a.ref_id)
      if (p && onOpenProject) onOpenProject(p)
    } else if (a.ref_type === 'document' && onOpenDocument) {
      try {
        const d = await api.documentDetail(a.ref_id)
        onOpenDocument(a.ref_id, d.document.project_id, 'profile')
      } catch {
        // Document no longer exists — nothing to open.
      }
    }
  }

  const active = user.status === 'active'
  const joined = joinedDate(user.created_at)
  const lastActive = relativeTime(user.last_active_at)
  const roleBadge = user.is_admin ? 'ADMIN' : 'EMPLOYEE'

  // Tab counts from real activity only.
  const counts = {}
  ;(activity || []).forEach((a) => {
    const meta = ACTIVITY_META[a.activity_type]
    if (meta) counts[meta.tab] = (counts[meta.tab] || 0) + 1
  })
  const visibleTabs = TABS.filter((t) => t.id === 'all' || (counts[t.id] || 0) > 0)
  const filtered =
    activity === null
      ? null
      : activity.filter(
          (a) => tab === 'all' || ACTIVITY_META[a.activity_type]?.tab === tab,
        )

  return (
    <div>
      <h1>My Profile</h1>
      <p className="tagline">Your employee profile and recent activity</p>

      {saved && <p className="ok-text profile-saved">Profile saved.</p>}

      {/* Profile header card */}
      <section className="panel profile-hero">
        <div className="profile-hero-top">
          <div className="profile-avatar-lg" aria-hidden="true">
            {user.avatar ? (
              <img src={api.avatarUrl(user.avatar)} alt="" />
            ) : (
              initials(user)
            )}
          </div>
          <div className="profile-identity">
            <div className="profile-name-row">
              <h2 className="profile-name">{user.full_name || user.username}</h2>
              {active && (
                <span className="badge badge-active">
                  <span className="status-dot" />
                  Active
                </span>
              )}
              <span className="badge badge-role">{roleBadge}</span>
            </div>
            <p className="profile-position">
              {user.position || (user.is_admin ? 'Administrator' : 'Member')}
            </p>
          </div>
          <button
            className="btn btn-primary profile-edit-btn"
            onClick={() => setEditOpen(true)}
          >
            Edit Profile
          </button>
        </div>

        <div className="profile-info-grid">
          <div className="profile-info-item">
            <span className="profile-info-label">Email</span>
            <span className="profile-info-value">{user.email || '—'}</span>
          </div>
          <div className="profile-info-item">
            <span className="profile-info-label">Department</span>
            <span className="profile-info-value">{user.department || '—'}</span>
          </div>
          <div className="profile-info-item">
            <span className="profile-info-label">Employee ID</span>
            <span className="profile-info-value">{user.employee_id || '—'}</span>
          </div>
          <div className="profile-info-item">
            <span className="profile-info-label">Joined</span>
            <span className="profile-info-value">{joined || '—'}</span>
          </div>
          <div className="profile-info-item">
            <span className="profile-info-label">Last Active</span>
            <span className="profile-info-value">
              {lastActive ? `Last active ${lastActive}` : '—'}
            </span>
          </div>
          <div className="profile-info-item">
            <span className="profile-info-label">Username</span>
            <span className="profile-info-value">{user.username}</span>
          </div>
        </div>

        <div className="profile-social">
          <a
            className="social-link"
            href={user.linkedin_url || undefined}
            target="_blank"
            rel="noreferrer"
            onClick={
              user.linkedin_url
                ? undefined
                : (e) => {
                    e.preventDefault()
                    setEditOpen(true)
                  }
            }
          >
            {ICONS.linkedin}
            <span>LinkedIn</span>
            <span className="social-action">
              {user.linkedin_url ? 'View LinkedIn' : 'Add LinkedIn profile'}
            </span>
          </a>
          <a
            className="social-link"
            href={user.github_url || undefined}
            target="_blank"
            rel="noreferrer"
            onClick={
              user.github_url
                ? undefined
                : (e) => {
                    e.preventDefault()
                    setEditOpen(true)
                  }
            }
          >
            {ICONS.github}
            <span>GitHub</span>
            <span className="social-action">
              {user.github_url ? 'View GitHub' : 'Add GitHub profile'}
            </span>
          </a>
        </div>
      </section>

      {/* Activity + Projects */}
      <div className="profile-layout">
        <section className="panel profile-activity">
          <div className="card-head">
            <h2>Recent Contributions &amp; Activity</h2>
          </div>
          <div className="activity-tabs" role="tablist">
            {visibleTabs.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                className={`activity-tab${tab === t.id ? ' activity-tab-active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {filtered === null ? (
            <p className="muted activity-loading">Loading activity…</p>
          ) : filtered.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-title">No activity yet</div>
              <div className="empty-state-text">
                {tab === 'all'
                  ? 'Your uploads, searches, AI questions and sign-ins will appear here.'
                  : 'Nothing in this category yet.'}
              </div>
            </div>
          ) : (
            <div className="activity-list">
              {filtered.map((a) => {
                const meta = ACTIVITY_META[a.activity_type] || {
                  label: 'Activity',
                  tab: 'all',
                  icon: 'view',
                }
                return (
                  <div className="activity-item" key={a.id}>
                    <span className="activity-icon">{ICONS[meta.icon]}</span>
                    <div className="activity-main">
                      <p className="activity-desc">{a.description}</p>
                      <p className="activity-meta">
                        {meta.label} · {relativeTime(a.created_at) || 'recently'}
                      </p>
                    </div>
                    {a.ref_type && (
                      <button
                        className="activity-open"
                        onClick={() => openRef(a)}
                      >
                        Open
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>

        <section className="panel profile-projects">
          <div className="card-head">
            <h2>Projects</h2>
          </div>
          {projects === null ? (
            <p className="muted activity-loading">Loading…</p>
          ) : projects.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-title">No projects yet</div>
              <div className="empty-state-text">
                Not a member of any project yet.
              </div>
            </div>
          ) : (
            <div className="project-list">
              {projects.map((p) => (
                <div
                  className="project-row"
                  key={p.id}
                  onClick={() => onOpenProject && onOpenProject(p)}
                >
                  <div className="project-row-main">
                    <span className="project-row-name">{p.name}</span>
                    <span className="project-row-meta">
                      {p.document_count} document
                      {p.document_count === 1 ? '' : 's'}
                    </span>
                  </div>
                  <span className="badge badge-owner">Owner</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Edit Profile modal */}
      {editOpen && (
        <div
          className="modal-overlay"
          onClick={() => {
            setUnsaved('profile-edit', false)
            setEditOpen(false)
          }}
        >
          <div
            className="modal-card profile-edit-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <span className="modal-title">Edit Profile</span>
              <button
                className="modal-close"
                onClick={() => {
                  setUnsaved('profile-edit', false)
                  setEditOpen(false)
                }}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <form onSubmit={submit} className="modal-body stack">
              <div className="edit-photo-row">
                <div className="profile-avatar-sm" aria-hidden="true">
                  {user.avatar ? (
                    <img src={api.avatarUrl(user.avatar)} alt="" />
                  ) : (
                    initials(user)
                  )}
                </div>
                <div className="edit-photo-actions">
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={() => photoInput.current?.click()}
                    disabled={photoBusy}
                  >
                    {photoBusy
                      ? 'Uploading…'
                      : user.avatar
                        ? 'Change photo'
                        : 'Upload photo'}
                  </button>
                  {user.avatar && (
                    <button
                      type="button"
                      className="btn btn-small btn-danger"
                      onClick={onRemovePhoto}
                      disabled={photoBusy}
                    >
                      Remove photo
                    </button>
                  )}
                  <input
                    ref={photoInput}
                    type="file"
                    accept="image/png,image/jpeg,image/gif,image/webp"
                    style={{ display: 'none' }}
                    onChange={onPhoto}
                  />
                </div>
              </div>
              {photoMsg && <p className="ok-text">{photoMsg}</p>}
              {photoError && <p className="error-text">{photoError}</p>}

              <div>
                <label className="field-label">Full name</label>
                <input
                  placeholder="Full name"
                  value={form.full_name}
                  onChange={(e) => setField({ full_name: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">Position / Job title</label>
                <input
                  placeholder="e.g. Knowledge Manager"
                  value={form.position}
                  onChange={(e) => setField({ position: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">Department</label>
                <input
                  placeholder="e.g. Operations"
                  value={form.department}
                  onChange={(e) => setField({ department: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">Email</label>
                <input
                  type="email"
                  placeholder="Email address"
                  value={form.email}
                  onChange={(e) => setField({ email: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">LinkedIn profile URL</label>
                <input
                  placeholder="https://linkedin.com/in/…"
                  value={form.linkedin_url}
                  onChange={(e) => setField({ linkedin_url: e.target.value })}
                />
              </div>
              <div>
                <label className="field-label">GitHub profile URL</label>
                <input
                  placeholder="https://github.com/…"
                  value={form.github_url}
                  onChange={(e) => setField({ github_url: e.target.value })}
                />
              </div>

              <p className="edit-note">
                Employee ID, join date and access level are managed by your
                administrator and cannot be changed here.
              </p>

              {error && <p className="error-text">{error}</p>}
              <div className="actions">
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setUnsaved('profile-edit', false)
                    setEditOpen(false)
                  }}
                >
                  Cancel
                </button>
                <button className="btn btn-primary" disabled={busy}>
                  {busy ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}