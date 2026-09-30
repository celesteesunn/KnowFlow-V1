import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'
import { setUnsaved } from '../unsaved.js'

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

const MAX_AVATAR_MB = 2

const NOTIF_ITEMS = [
  {
    key: 'uploads',
    name: 'Document uploads',
    desc: 'Receive notifications when documents are uploaded or updated.',
  },
  {
    key: 'projects',
    name: 'Project updates',
    desc: 'Get notified when projects are created or changed.',
  },
  {
    key: 'comments',
    name: 'Comments and mentions',
    desc: 'Alerts when you are mentioned or someone comments on your work.',
  },
  {
    key: 'knowledge',
    name: 'Knowledge-base updates',
    desc: 'Updates when the knowledge base gains new content.',
  },
  {
    key: 'email',
    name: 'Email notifications',
    desc: 'Send notification summaries to your email address.',
  },
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

function Toggle({ on, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      className={`toggle${on ? ' toggle-on' : ''}`}
      onClick={() => onChange(!on)}
    />
  )
}

function SettingRow({ name, desc, children }) {
  return (
    <div className="setting-row">
      <div className="setting-info">
        <div className="setting-name">{name}</div>
        {desc && <div className="setting-desc">{desc}</div>}
      </div>
      <div className="setting-control">{children}</div>
    </div>
  )
}

export default function Settings({ user, onAuth, settings, onChange }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    full_name: user.full_name || '',
    email: user.email || '',
  })
  const [saveBusy, setSaveBusy] = useState(false)
  const [saveMsg, setSaveMsg] = useState(null)
  const [saveError, setSaveError] = useState(null)
  const [photoBusy, setPhotoBusy] = useState(false)
  const photoInput = useRef(null)

  const [pw, setPw] = useState({ current: '', next: '', confirm: '' })
  const [pwBusy, setPwBusy] = useState(false)
  const [pwMsg, setPwMsg] = useState(null)
  const [pwError, setPwError] = useState(null)

  const [docCount, setDocCount] = useState(null)
  const [version, setVersion] = useState(null)

  useEffect(() => {
    api
      .allDocuments()
      .then((d) => setDocCount(d.documents.length))
      .catch(() => {})
    api
      .health()
      .then((h) => setVersion(h.version))
      .catch(() => {})
  }, [])

  // Clear the unsaved flags when the settings view unmounts.
  useEffect(
    () => () => {
      setUnsaved('settings-profile', false)
      setUnsaved('settings-password', false)
    },
    [],
  )

  const update = (patch) => onChange({ ...settings, ...patch })
  const updateNested = (key, patch) =>
    onChange({ ...settings, [key]: { ...settings[key], ...patch } })

  const startEdit = () => {
    setForm({ full_name: user.full_name || '', email: user.email || '' })
    setSaveMsg(null)
    setSaveError(null)
    setEditing(true)
  }

  const saveProfile = async (e) => {
    e.preventDefault()
    setSaveBusy(true)
    setSaveError(null)
    setSaveMsg(null)
    try {
      const data = await api.updateProfile(form)
      onAuth(data.user)
      setUnsaved('settings-profile', false)
      setSaveMsg('Profile saved.')
      setEditing(false)
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSaveBusy(false)
    }
  }

  const onPhoto = async (e) => {
    const file = e.target.files[0]
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setSaveError('Please choose an image file (PNG, JPG, GIF or WebP).')
      setSaveMsg(null)
      e.target.value = ''
      return
    }
    if (file.size > MAX_AVATAR_MB * 1024 * 1024) {
      setSaveError(`Image too large. Maximum size is ${MAX_AVATAR_MB} MB.`)
      setSaveMsg(null)
      e.target.value = ''
      return
    }
    setPhotoBusy(true)
    setSaveError(null)
    setSaveMsg(null)
    try {
      const data = await api.uploadAvatar(file)
      onAuth(data.user)
      setSaveMsg('Profile picture updated.')
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setPhotoBusy(false)
      e.target.value = ''
    }
  }

  const onRemovePhoto = async () => {
    if (!window.confirm('Remove your profile picture?')) return
    setPhotoBusy(true)
    setSaveError(null)
    setSaveMsg(null)
    try {
      const data = await api.removeAvatar()
      onAuth(data.user)
      setSaveMsg('Profile picture removed.')
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setPhotoBusy(false)
    }
  }

  const changePassword = async (e) => {
    e.preventDefault()
    if (pw.next.length < 6) {
      setPwError('New password must be at least 6 characters.')
      setPwMsg(null)
      return
    }
    if (pw.next !== pw.confirm) {
      setPwError('New password and confirmation do not match.')
      setPwMsg(null)
      return
    }
    setPwBusy(true)
    setPwError(null)
    setPwMsg(null)
    try {
      await api.changePassword({ current_password: pw.current, new_password: pw.next })
      setUnsaved('settings-password', false)
      setPwMsg('Password changed.')
      setPw({ current: '', next: '', confirm: '' })
    } catch (err) {
      setPwError(err.message)
    } finally {
      setPwBusy(false)
    }
  }

  const active = user.status === 'active'
  const joined = joinedDate(user.created_at)
  const position = user.is_admin ? 'Administrator' : 'Member'
  const notif = settings.notifications
  const docPrefs = settings.documents
  const a11y = settings.accessibility

  return (
    <div>
      <h1>Settings</h1>
      <p className="tagline">Manage your account and application preferences</p>

      {/* 1. Account */}
      <section className="panel">
        <h2>Account</h2>
        {!editing ? (
          <>
            <div className="settings-account">
              <div className="settings-avatar" aria-hidden="true">
                {user.avatar ? (
                  <img src={api.avatarUrl(user.avatar)} alt="" />
                ) : (
                  initials(user)
                )}
              </div>
              <div className="settings-account-info">
                <div className="settings-account-name">
                  {user.full_name || user.username}
                </div>
                <div className="settings-account-line">{user.email || 'No email set'}</div>
                <div className="settings-account-line">{position}</div>
                {joined && <div className="settings-account-line">Joined {joined}</div>}
                <div className="settings-account-status">
                  <span className="status-dot" />
                  {active ? 'Active' : user.status}
                </div>
              </div>
              <button className="btn" onClick={startEdit}>
                Edit Profile
              </button>
            </div>
          </>
        ) : (
          <form onSubmit={saveProfile} className="stack">
            <div className="settings-account">
              <div className="settings-avatar" aria-hidden="true">
                {user.avatar ? (
                  <img src={api.avatarUrl(user.avatar)} alt="" />
                ) : (
                  initials(user)
                )}
              </div>
              <div className="settings-account-info">
                <div className="settings-photo-actions">
                  <button
                    type="button"
                    className="btn btn-small"
                    onClick={() => photoInput.current?.click()}
                    disabled={photoBusy}
                  >
                    {photoBusy ? 'Uploading…' : user.avatar ? 'Change photo' : 'Upload photo'}
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
            </div>
            <div>
              <label className="field-label">Full name</label>
              <input
                placeholder="Full name"
                value={form.full_name}
                onChange={(e) => {
                  setForm({ ...form, full_name: e.target.value })
                  setUnsaved('settings-profile', true)
                }}
              />
            </div>
            <div>
              <label className="field-label">Email address</label>
              <input
                type="email"
                placeholder="Email address"
                value={form.email}
                onChange={(e) => {
                  setForm({ ...form, email: e.target.value })
                  setUnsaved('settings-profile', true)
                }}
              />
            </div>
            <div>
              <label className="field-label">Position</label>
              <input value={position} disabled />
              <p className="setting-note">
                Position is assigned by an administrator and cannot be edited here.
              </p>
            </div>
            {saveError && <p className="error-text">{saveError}</p>}
            {saveMsg && <p className="ok-text">{saveMsg}</p>}
            <div className="settings-edit-actions">
              <button className="btn btn-primary" disabled={saveBusy}>
                {saveBusy ? 'Saving…' : 'Save Changes'}
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setUnsaved('settings-profile', false)
                  setEditing(false)
                }}
                disabled={saveBusy}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </section>

      {/* 2. Appearance */}
      <section className="panel">
        <h2>Appearance</h2>
        <SettingRow name="Theme" desc="Choose how KnowFlow looks on this device.">
          <select
            className="setting-select"
            value={settings.theme}
            onChange={(e) => update({ theme: e.target.value })}
          >
            <option value="light">Light</option>
            <option value="dark">Dark</option>
            <option value="system">System default</option>
          </select>
        </SettingRow>
        <SettingRow name="Interface density" desc="Controls spacing and padding throughout the app.">
          <select
            className="setting-select"
            value={settings.density}
            onChange={(e) => update({ density: e.target.value })}
          >
            <option value="comfortable">Comfortable</option>
            <option value="compact">Compact</option>
          </select>
        </SettingRow>
      </section>

      {/* 3. Notifications */}
      <section className="panel">
        <h2>Notifications</h2>
        {NOTIF_ITEMS.map((item) => (
          <SettingRow key={item.key} name={item.name} desc={item.desc}>
            <Toggle
              on={!!notif[item.key]}
              onChange={(v) => updateNested('notifications', { [item.key]: v })}
            />
          </SettingRow>
        ))}
        <p className="setting-note">
          KnowFlow does not send notifications yet. Your preferences are saved on this
          device and will be used when notification delivery is added.
        </p>
      </section>

      {/* 4. Documents */}
      <section className="panel">
        <h2>Documents</h2>
        <SettingRow name="Default document view" desc="How documents are shown in lists.">
          <select
            className="setting-select"
            value={docPrefs.view}
            onChange={(e) => updateNested('documents', { view: e.target.value })}
          >
            <option value="list">List</option>
            <option value="grid">Grid</option>
          </select>
        </SettingRow>
        <SettingRow name="Default sorting" desc="Order of documents in lists.">
          <select
            className="setting-select"
            value={docPrefs.sort}
            onChange={(e) => updateNested('documents', { sort: e.target.value })}
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="name_az">Name A–Z</option>
            <option value="name_za">Name Z–A</option>
          </select>
        </SettingRow>
        <SettingRow
          name="Allow multiple uploads"
          desc="Select and upload several documents at once, up to 500 MB each."
        >
          <Toggle
            on={!!docPrefs.multiUpload}
            onChange={(v) => updateNested('documents', { multiUpload: v })}
          />
        </SettingRow>
        <SettingRow
          name="Automatically refresh document list"
          desc="Refresh the list after an upload or change."
        >
          <Toggle
            on={!!docPrefs.autoRefresh}
            onChange={(v) => updateNested('documents', { autoRefresh: v })}
          />
        </SettingRow>
        <SettingRow name="Storage used" desc="Documents currently stored in KnowFlow.">
          <span className="badge">{docCount === null ? '…' : `${docCount} documents`}</span>
        </SettingRow>
      </section>

      {/* 5. Privacy & Security */}
      <section className="panel">
        <h2>Privacy &amp; Security</h2>
        <form onSubmit={changePassword} className="stack">
          <div>
            <label className="field-label">Current password</label>
            <input
              type="password"
              autoComplete="current-password"
              value={pw.current}
              onChange={(e) => {
                setPw({ ...pw, current: e.target.value })
                setUnsaved('settings-password', true)
              }}
            />
          </div>
          <div>
            <label className="field-label">New password</label>
            <input
              type="password"
              autoComplete="new-password"
              value={pw.next}
              onChange={(e) => {
                setPw({ ...pw, next: e.target.value })
                setUnsaved('settings-password', true)
              }}
            />
          </div>
          <div>
            <label className="field-label">Confirm new password</label>
            <input
              type="password"
              autoComplete="new-password"
              value={pw.confirm}
              onChange={(e) => {
                setPw({ ...pw, confirm: e.target.value })
                setUnsaved('settings-password', true)
              }}
            />
          </div>
          {pwError && <p className="error-text">{pwError}</p>}
          {pwMsg && <p className="ok-text">{pwMsg}</p>}
          <div className="settings-edit-actions">
            <button className="btn btn-primary" disabled={pwBusy}>
              {pwBusy ? 'Changing…' : 'Change Password'}
            </button>
          </div>
        </form>

        <div className="setting-row" style={{ marginTop: 18 }}>
          <div className="setting-info">
            <div className="setting-name">Active sessions</div>
            <div className="setting-desc">
              KnowFlow uses a single browser session (a signed cookie). Session details
              are not stored on the server, so there are no other sessions to manage.
            </div>
          </div>
        </div>

        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-name">Privacy</div>
            <div className="setting-desc">
              Your account data is stored in the organisation's local KnowFlow database.
              You accepted the Terms &amp; Conditions and the Security &amp; Confidentiality
              agreement when you joined.
            </div>
          </div>
        </div>
      </section>

      {/* 6. Accessibility */}
      <section className="panel">
        <h2>Accessibility</h2>
        <SettingRow name="Font size" desc="Scales the interface text and spacing.">
          <select
            className="setting-select"
            value={a11y.fontSize}
            onChange={(e) => updateNested('accessibility', { fontSize: e.target.value })}
          >
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large</option>
          </select>
        </SettingRow>
        <SettingRow name="Reduced motion" desc="Reduce animations and transitions.">
          <Toggle
            on={!!a11y.reducedMotion}
            onChange={(v) => updateNested('accessibility', { reducedMotion: v })}
          />
        </SettingRow>
        <SettingRow name="High contrast" desc="Increase colour contrast for better readability.">
          <Toggle
            on={!!a11y.highContrast}
            onChange={(v) => updateNested('accessibility', { highContrast: v })}
          />
        </SettingRow>
      </section>

      {/* 7. About */}
      <section className="panel settings-about">
        <img src="/logo.png" alt="" className="settings-about-logo" aria-hidden="true" />
        <div className="settings-about-name">KnowFlow</div>
        <div className="settings-about-tagline">Enterprise and Knowledge Platform</div>
        <div className="settings-about-meta">
          {version ? `Version ${version}` : 'Version —'} · Local deployment · Privacy Policy ·
          Terms of Service
        </div>
      </section>
    </div>
  )
}