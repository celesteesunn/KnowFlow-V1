import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { setUnsaved } from '../unsaved.js'

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
  search: icon(
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </>,
  ),
  back: icon(
    <>
      <path d="M19 12H5" />
      <path d="m12 19-7-7 7-7" />
    </>,
  ),
  linkedin: icon(
    <>
      <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4V8h4v1.5" />
      <rect x="2" y="9" width="4" height="12" />
      <circle cx="4" cy="4" r="2" />
    </>,
  ),
  github: icon(
    <>
      <path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21" />
    </>,
  ),
  mail: icon(
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </>,
  ),
  edit: icon(
    <>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
    </>,
  ),
  close: icon(
    <>
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </>,
  ),
}

const ROLE_LABELS = {
  leadership: 'Leadership',
  department_head: 'Department Head',
  team_lead: 'Team Lead',
  project_lead: 'Project Lead',
}

const CATEGORIES = [
  { id: 'all', label: 'All Members' },
  { id: 'active', label: 'Active Members' },
  { id: 'recently_joined', label: 'Recently Joined' },
  { id: 'my_department', label: 'My Department' },
  { id: 'my_projects', label: 'My Projects / Teams' },
  { id: 'leadership', label: 'Leadership' },
]

const initials = (m) => {
  const name = (m.full_name || m.username || '?').trim()
  const parts = name.split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

const formatJoined = (iso) => {
  if (!iso) return '—'
  const d = new Date(iso.replace(' ', 'T') + 'Z')
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short' })
}

const MemberAvatar = ({ member, size = 'md' }) => {
  if (member.avatar) {
    return <img className={`member-avatar member-avatar-${size}`} src={api.avatarUrl(member.avatar)} alt="" />
  }
  return <span className={`member-avatar member-avatar-${size} member-avatar-initials`}>{initials(member)}</span>
}

const RoleBadge = ({ role }) => {
  if (!role) return null
  return <span className="badge badge-role">{ROLE_LABELS[role] || role}</span>
}

const StatusBadge = ({ status }) => {
  if (status === 'active') {
    return (
      <span className="badge badge-active">
        <span className="status-dot" />
        Active
      </span>
    )
  }
  return (
    <span className="badge badge-inactive">
      <span className="status-dot" />
      Inactive
    </span>
  )
}

function MemberCard({ member, viewer, onOpen }) {
  const isAdmin = viewer.is_admin
  const contact = isAdmin && member.email ? (
    <a className="btn btn-small" href={`mailto:${member.email}`}>
      {ICONS.mail}
      <span>Contact</span>
    </a>
  ) : (
    <button className="btn btn-small" onClick={() => onOpen(member)}>
      <span>View profile</span>
    </button>
  )

  return (
    <div className="panel member-card" onClick={() => onOpen(member)} role="button" tabIndex={0}>
      <div className="member-card-top">
        <MemberAvatar member={member} />
        <div className="member-card-identity">
          <h3 className="member-card-name">{member.full_name || member.username}</h3>
          <p className="member-card-position">{member.position || '—'}</p>
          <p className="member-card-dept">{member.department || '—'}</p>
        </div>
      </div>
      <div className="member-card-badges">
        <RoleBadge role={member.org_role} />
        <StatusBadge status={member.status} />
      </div>
      <div className="member-card-meta">
        <span>Joined {formatJoined(member.created_at)}</span>
        {member.employee_id && <span>ID {member.employee_id}</span>}
      </div>
      <div className="member-card-actions" onClick={(e) => e.stopPropagation()}>
        {member.linkedin_url && (
          <a className="social-link" href={member.linkedin_url} target="_blank" rel="noreferrer" title="LinkedIn">
            {ICONS.linkedin}
          </a>
        )}
        {member.github_url && (
          <a className="social-link" href={member.github_url} target="_blank" rel="noreferrer" title="GitHub">
            {ICONS.github}
          </a>
        )}
        {contact}
      </div>
    </div>
  )
}

function MemberProfile({ member, viewer, onBack, onEdit }) {
  const isAdmin = viewer.is_admin
  const isSelf = member.id === viewer.id
  const contact = isAdmin && member.email ? (
    <a className="btn btn-primary" href={`mailto:${member.email}`}>
      {ICONS.mail}
      <span>Contact</span>
    </a>
  ) : null

  return (
    <div className="member-profile">
      <button className="btn btn-small member-back" onClick={onBack}>
        {ICONS.back}
        <span>Back to directory</span>
      </button>

      <section className="panel profile-hero">
        <div className="profile-hero-top">
          <MemberAvatar member={member} size="lg" />
          <div className="profile-identity">
            <div className="profile-name-row">
              <h2 className="profile-name">{member.full_name || member.username}</h2>
              <StatusBadge status={member.status} />
              <RoleBadge role={member.org_role} />
            </div>
            <p className="profile-position">
              {[member.position, member.department].filter(Boolean).join(' · ') || 'Member'}
            </p>
            {isAdmin && (
              <button className="btn btn-primary profile-edit-btn" onClick={onEdit}>
                {ICONS.edit}
                <span>Edit member</span>
              </button>
            )}
          </div>
        </div>

        <div className="profile-info-grid">
          {isAdmin && (
            <div className="profile-info-item">
              <span className="profile-info-label">Email</span>
              <span className="profile-info-value">{member.email || '—'}</span>
            </div>
          )}
          {(isAdmin || isSelf) && (
            <div className="profile-info-item">
              <span className="profile-info-label">Employee ID</span>
              <span className="profile-info-value">{member.employee_id || '—'}</span>
            </div>
          )}
          <div className="profile-info-item">
            <span className="profile-info-label">Department</span>
            <span className="profile-info-value">{member.department || '—'}</span>
          </div>
          <div className="profile-info-item">
            <span className="profile-info-label">Joined</span>
            <span className="profile-info-value">{formatJoined(member.created_at)}</span>
          </div>
          <div className="profile-info-item">
            <span className="profile-info-label">Username</span>
            <span className="profile-info-value">{member.username}</span>
          </div>
        </div>

        <div className="profile-social">
          {member.linkedin_url ? (
            <a className="social-link" href={member.linkedin_url} target="_blank" rel="noreferrer">
              {ICONS.linkedin}
              <span className="social-action">LinkedIn</span>
            </a>
          ) : (
            <span className="social-link social-link-empty">
              {ICONS.linkedin}
              <span className="social-action">LinkedIn</span>
            </span>
          )}
          {member.github_url ? (
            <a className="social-link" href={member.github_url} target="_blank" rel="noreferrer">
              {ICONS.github}
              <span className="social-action">GitHub</span>
            </a>
          ) : (
            <span className="social-link social-link-empty">
              {ICONS.github}
              <span className="social-action">GitHub</span>
            </span>
          )}
          {contact}
        </div>
      </section>
    </div>
  )
}

function AdminEditModal({ member, onClose, onSaved }) {
  const [position, setPosition] = useState(member.position || '')
  const [department, setDepartment] = useState(member.department || '')
  const [employeeId, setEmployeeId] = useState(member.employee_id || '')
  const [orgRole, setOrgRole] = useState(member.org_role || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [statusMsg, setStatusMsg] = useState('')

  // Clear the unsaved flag when the modal unmounts.
  useEffect(() => () => setUnsaved('member-edit', false), [])

  const close = () => {
    setUnsaved('member-edit', false)
    onClose()
  }

  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const d = await api.updateMember(member.id, {
        position,
        department,
        employee_id: employeeId,
        org_role: orgRole || null,
      })
      setUnsaved('member-edit', false)
      onSaved(d.member)
      setStatusMsg('Member profile updated.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const setStatus = async (status) => {
    setBusy(true)
    setError('')
    setStatusMsg('')
    try {
      if (status === 'active') {
        await api.adminReactivate(member.id)
      } else {
        await api.adminSuspend(member.id, 'Deactivated from the Members directory')
      }
      setStatusMsg(status === 'active' ? 'Member activated.' : 'Member deactivated.')
      onSaved({ ...member, status })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={close}>
      <div className="modal-card profile-edit-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">Edit member — {member.full_name || member.username}</span>
          <button className="modal-close" onClick={close} aria-label="Close">
            {ICONS.close}
          </button>
        </div>
        <form onSubmit={save} className="modal-body stack">
          <label className="field-label">
            Position / Job title
            <input
              className="field-input"
              value={position}
              onChange={(e) => {
                setPosition(e.target.value)
                setUnsaved('member-edit', true)
              }}
              maxLength={100}
            />
          </label>
          <label className="field-label">
            Department
            <input
              className="field-input"
              value={department}
              onChange={(e) => {
                setDepartment(e.target.value)
                setUnsaved('member-edit', true)
              }}
              maxLength={100}
            />
          </label>
          <label className="field-label">
            Employee ID
            <input
              className="field-input"
              value={employeeId}
              onChange={(e) => {
                setEmployeeId(e.target.value)
                setUnsaved('member-edit', true)
              }}
              maxLength={50}
            />
          </label>
          <label className="field-label">
            Organisational role
            <select
              className="field-input"
              value={orgRole}
              onChange={(e) => {
                setOrgRole(e.target.value)
                setUnsaved('member-edit', true)
              }}
            >
              <option value="">Member</option>
              <option value="leadership">Leadership</option>
              <option value="department_head">Department Head</option>
              <option value="team_lead">Team Lead</option>
              <option value="project_lead">Project Lead</option>
            </select>
          </label>

          <div className="edit-note">
            Account status: {member.status === 'active' ? 'Active' : 'Inactive'}
          </div>
          <div className="actions">
            <button
              type="button"
              className="btn btn-small btn-danger"
              disabled={busy || member.status !== 'active'}
              onClick={() => setStatus('suspended')}
            >
              Deactivate
            </button>
            <button
              type="button"
              className="btn btn-small"
              disabled={busy || member.status === 'active'}
              onClick={() => setStatus('active')}
            >
              Activate
            </button>
          </div>

          {statusMsg && <p className="ok-text">{statusMsg}</p>}
          {error && <p className="error-text">{error}</p>}
          <div className="actions">
            <button type="button" className="btn" onClick={close}>
              Cancel
            </button>
            <button className="btn btn-primary" disabled={busy}>
              Save changes
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function MembersView({ user }) {
  const [category, setCategory] = useState('all')
  const [q, setQ] = useState('')
  const [department, setDepartment] = useState('')
  const [members, setMembers] = useState([])
  const [departments, setDepartments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [profile, setProfile] = useState(null)
  const [editMember, setEditMember] = useState(null)

  // Load the department list once.
  useEffect(() => {
    api
      .memberDepartments()
      .then((d) => setDepartments(d.departments || []))
      .catch(() => {})
  }, [])

  // Debounced directory fetch.
  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true)
      setError('')
      api
        .members({ q: q.trim(), category, department })
        .then((d) => setMembers(d.members || []))
        .catch((err) => setError(err.message))
        .finally(() => setLoading(false))
    }, q ? 300 : 0)
    return () => clearTimeout(t)
  }, [q, category, department])

  const openMember = useCallback((m) => {
    setSelected(m)
    setProfile(null)
    api
      .member(m.id)
      .then((d) => setProfile(d.member))
      .catch((err) => setError(err.message))
  }, [])

  const closeMember = useCallback(() => {
    setSelected(null)
    setProfile(null)
  }, [])

  const onAdminSaved = useCallback(
    (updated) => {
      setProfile(updated)
      setMembers((prev) => prev.map((m) => (m.id === updated.id ? updated : m)))
    },
    [],
  )

  const visibleCount = useMemo(() => members.length, [members])

  if (selected) {
    return (
      <div className="page">
        <MemberProfile
          member={profile || selected}
          viewer={user}
          onBack={closeMember}
          onEdit={() => setEditMember(profile || selected)}
        />
        {editMember && (
          <AdminEditModal
            member={editMember}
            onClose={() => setEditMember(null)}
            onSaved={(updated) => {
              setEditMember(null)
              onAdminSaved(updated)
            }}
          />
        )}
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Members</h1>
          <p className="tagline">Enterprise directory — find colleagues, teams and leadership</p>
        </div>
        <div className="member-search">
          {ICONS.search}
          <input
            className="member-search-input"
            placeholder="Search by name, position or department…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
      </div>

      <div className="member-categories" role="tablist">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            role="tab"
            aria-selected={category === c.id}
            className={`member-cat ${category === c.id ? 'member-cat-active' : ''}`}
            onClick={() => setCategory(c.id)}
          >
            {c.label}
          </button>
        ))}
      </div>

      {departments.length > 0 && (
        <div className="member-depts">
          <span className="member-depts-label">Departments</span>
          <button
            className={`dept-chip ${!department ? 'dept-chip-active' : ''}`}
            onClick={() => setDepartment('')}
          >
            All
          </button>
          {departments.map((d) => (
            <button
              key={d.name}
              className={`dept-chip ${department === d.name ? 'dept-chip-active' : ''}`}
              onClick={() => setDepartment(department === d.name ? '' : d.name)}
            >
              {d.name}
              <span className="dept-chip-count">{d.count}</span>
            </button>
          ))}
        </div>
      )}

      {error && <p className="error-text">{error}</p>}
      {loading ? (
        <p className="muted">Loading members…</p>
      ) : members.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-title">No members found</div>
          <div className="empty-state-text">
            {q
              ? 'Try a different search term.'
              : 'No members match this category yet.'}
          </div>
        </div>
      ) : (
        <>
          <p className="muted member-count">
            {visibleCount} {visibleCount === 1 ? 'member' : 'members'}
          </p>
          <div className="member-grid">
            {members.map((m) => (
              <MemberCard key={m.id} member={m} viewer={user} onOpen={openMember} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}