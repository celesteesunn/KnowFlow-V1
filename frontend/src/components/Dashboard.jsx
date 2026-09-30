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
  search: icon(
    <>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </>,
  ),
  assistant: icon(
    <>
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
      <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" />
    </>,
  ),
  upload: icon(
    <>
      <path d="M12 16V4" />
      <path d="m6 10 6-6 6 6" />
      <path d="M4 20h16" />
    </>,
  ),
  knowledge: icon(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7c-2-1.5-5-1.5-7 0v10c2-1.5 5-1.5 7 0s5-1.5 7 0V7c-2-1.5-5-1.5-7 0z" />
      <path d="M12 7v10" />
    </>,
  ),
  bookmarks: icon(<path d="M6 3h12v18l-6-4-6 4z" />),
  help: icon(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4" />
      <path d="M12 17h.01" />
    </>,
  ),
  faq: icon(
    <>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M9 9h6" />
      <path d="M9 13h4" />
    </>,
  ),
  contact: icon(
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </>,
  ),
  report: icon(
    <>
      <path d="M4 21V4" />
      <path d="M4 5h12l-2 4 2 4H4" />
    </>,
  ),
  about: icon(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 8h.01" />
    </>,
  ),
  docs: icon(
    <>
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </>,
  ),
  privacy: icon(
    <>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </>,
  ),
  terms: icon(
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
    </>,
  ),
  company: icon(
    <>
      <path d="M3 21h18" />
      <path d="M5 21V7l7-4 7 4v14" />
      <path d="M9 21v-4h6v4" />
      <path d="M9 10h.01" />
      <path d="M15 10h.01" />
      <path d="M9 14h.01" />
      <path d="M15 14h.01" />
    </>,
  ),
}

function Modal({ title, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{title}</span>
          <button className="btn btn-small" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

function HelpTopic({ title, children }) {
  return (
    <div className="help-topic">
      <div className="help-topic-title">{title}</div>
      <div className="help-topic-text">{children}</div>
    </div>
  )
}

function FeedbackForm({ preset, onDone }) {
  const [type, setType] = useState(preset || 'general')
  const [message, setMessage] = useState('')
  const [sent, setSent] = useState(false)

  const submit = (e) => {
    e.preventDefault()
    if (!message.trim()) return
    try {
      const key = 'knowflow.feedback'
      const list = JSON.parse(localStorage.getItem(key) || '[]')
      list.push({ type, message: message.trim(), at: new Date().toISOString() })
      localStorage.setItem(key, JSON.stringify(list))
    } catch {
      /* storage unavailable — nothing to do */
    }
    setSent(true)
  }

  if (sent) {
    return (
      <div className="stack">
        <p className="ok-text">Thank you! Your feedback has been recorded.</p>
        <p className="setting-note">
          Feedback is stored on this device. KnowFlow does not yet submit feedback to a
          server.
        </p>
        <div>
          <button className="btn" onClick={onDone}>
            Done
          </button>
        </div>
      </div>
    )
  }

  return (
    <form onSubmit={submit} className="stack">
      <div>
        <label className="field-label">Feedback type</label>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="general">General feedback</option>
          <option value="bug">Bug report</option>
          <option value="feature">Feature request</option>
        </select>
      </div>
      <div>
        <label className="field-label">Message</label>
        <textarea
          rows={5}
          placeholder="Tell us what's on your mind…"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
      </div>
      <div className="settings-edit-actions">
        <button className="btn btn-primary" disabled={!message.trim()}>
          Submit Feedback
        </button>
      </div>
    </form>
  )
}

export default function Dashboard({ user, onOpenProject, onOpenDocument, nav }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [version, setVersion] = useState(null)
  const [modal, setModal] = useState(null)
  const [feedbackPreset, setFeedbackPreset] = useState('general')
  const [projects, setProjects] = useState(null)
  const [allDocs, setAllDocs] = useState(null)
  const [actionQuery, setActionQuery] = useState('')
  const [pendingCount, setPendingCount] = useState(null)

  useEffect(() => {
    api
      .dashboard()
      .then(setData)
      .catch((e) => setError(e.message))
    api
      .health()
      .then((h) => setVersion(h.version))
      .catch(() => {})
    api
      .projects()
      .then((d) => setProjects(d.projects))
      .catch(() => {})
    api
      .allDocuments()
      .then((d) => setAllDocs(d.documents))
      .catch(() => {})
    if (user.is_admin) {
      api
        .adminPendingCount()
        .then((d) => setPendingCount(d.count))
        .catch(() => {})
    }
  }, [user.is_admin])

  const openFeedback = (preset) => {
    setFeedbackPreset(preset)
    setModal('feedback')
  }

  const submitActionSearch = (e) => {
    e.preventDefault()
    if (actionQuery.trim()) nav.search(actionQuery.trim())
  }

  if (!data) {
    return (
      <div>
        <h1>Dashboard</h1>
        <p className="muted">Loading…</p>
        {error && <p className="error-text">{error}</p>}
      </div>
    )
  }

  return (
    <div>
      {/* Search / actions */}
      <section className="action-bar">
        <form onSubmit={submitActionSearch} className="action-search">
          <span className="action-search-icon">{ICONS.search}</span>
          <input
            placeholder="Search documents & knowledge..."
            value={actionQuery}
            onChange={(e) => setActionQuery(e.target.value)}
            aria-label="Search documents and knowledge"
          />
        </form>
        <button className="btn btn-primary" onClick={nav.assistant}>
          Ask AI
        </button>
        <button className="btn" onClick={nav.upload}>
          Quick Upload
        </button>
        <span className="action-upload-note">PDF, DOCX or TXT · max 500 MB</span>
      </section>

      {/* Pending access requests (admins) */}
      {user.is_admin && (
        <section className="panel dash-card dash-card-wide">
          <div className="card-head">
            <h2>
              Pending Access Requests ({pendingCount === null ? '…' : pendingCount})
            </h2>
            <button className="btn btn-small" onClick={nav.admin}>
              Review Requests
            </button>
          </div>
          <p className="muted">
            {pendingCount === null
              ? 'Loading…'
              : pendingCount > 0
                ? 'New employees are waiting for approval to join your workspace.'
                : 'No pending access requests. New requests will appear here.'}
          </p>
        </section>
      )}

      {/* Authorised documents */}
      <section className="panel dash-card dash-card-wide">
        <div className="card-head">
          <h2>Authorised Documents ({allDocs ? allDocs.length : '…'})</h2>
          <button className="link-btn" onClick={nav.documents}>
            View all
          </button>
        </div>
        {!allDocs && <p className="muted">Loading…</p>}
        {allDocs && allDocs.length === 0 && (
          <div className="empty-state">
            {ICONS.docs}
            <span className="empty-state-title">No documents yet</span>
            <span className="empty-state-text">
              Upload a document to start building your knowledge base.
            </span>
          </div>
        )}
        {allDocs && allDocs.length > 0 && (
          <ul className="dash-doc-list">
            {allDocs.slice(0, 6).map((d) => (
              <li key={d.id} className="dash-doc-item">
                <div className="dash-doc-main">
                  <span className="dash-doc-name">{d.title}</span>
                  <span className="dash-doc-meta">
                    <span>PDF</span>
                    <span className={`status-badge status-${d.processing_status}`}>
                      {d.processing_status}
                    </span>
                    <span>v{d.version}</span>
                    <span>{d.project_name}</span>
                    <span>{d.created_at}</span>
                  </span>
                </div>
                <button
                  className="btn btn-small"
                  onClick={() => onOpenDocument(d.id, d.project_id, 'dashboard')}
                >
                  View
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="dash-grid">
        {/* AI Assistant */}
        <section className="panel dash-card">
          <div className="card-head">
            <h2>AI Assistant</h2>
          </div>
          <p className="muted">
            Ask questions about your authorised knowledge. Answers are grounded in the
            uploaded content with sources.
          </p>
          <div className="stack" style={{ marginTop: 14 }}>
            <button className="btn btn-primary" onClick={nav.assistant}>
              Open AI Assistant
            </button>
          </div>
        </section>

        {/* My Projects */}
        <section className="panel dash-card">
          <div className="card-head">
            <h2>My Projects ({projects ? projects.length : '…'})</h2>
            <button className="link-btn" onClick={nav.projects}>
              View all
            </button>
          </div>
          {!projects && <p className="muted">Loading…</p>}
          {projects && projects.length === 0 && (
            <div className="empty-state">
              {ICONS.company}
              <span className="empty-state-title">No projects yet</span>
              <span className="empty-state-text">
                Create a project to organise your documents.
              </span>
            </div>
          )}
          {projects && projects.length > 0 && (
            <ul className="plain-list">
              {projects.slice(0, 4).map((p) => (
                <li key={p.id}>
                  <button className="link-btn" onClick={() => onOpenProject(p)}>
                    {p.name}
                  </button>
                  <span className="muted">
                    {p.document_count} document{p.document_count === 1 ? '' : 's'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Quick Bookmarks */}
        <section className="panel dash-card dash-card-wide">
          <div className="card-head">
            <h2>Quick Bookmarks</h2>
            <button className="link-btn" onClick={nav.bookmarks}>
              View all
            </button>
          </div>
          <div className="empty-state">
            {ICONS.bookmarks}
            <span className="empty-state-title">No bookmarks yet</span>
            <span className="empty-state-text">
              Bookmarks are not available in this deployment yet.
            </span>
          </div>
        </section>
      </div>

      {/* Help & support + company */}
      <div className="dash-grid">
        <section className="panel dash-card">
          <h2>Help &amp; Support</h2>
          <div className="help-grid">
            <button className="help-option" onClick={() => setModal('help')}>
              {ICONS.help}
              <span>Help Centre</span>
            </button>
            <button className="help-option" onClick={() => setModal('faq')}>
              {ICONS.faq}
              <span>FAQ</span>
            </button>
            <button className="help-option" onClick={() => setModal('contact')}>
              {ICONS.contact}
              <span>Contact Support</span>
            </button>
            <button className="help-option" onClick={() => openFeedback('bug')}>
              {ICONS.report}
              <span>Report an Issue</span>
            </button>
          </div>
        </section>

        <section className="panel dash-card">
          <h2>Company / Organisation</h2>
          <div className="company-block">
            <div>
              <div className="company-name">KnowFlow</div>
              <div className="company-tagline">Enterprise Knowledge Platform</div>
            </div>
            <div className="company-row">
              <strong>Email</strong>
              <span>support@example.com</span>
            </div>
            <div className="company-row">
              <strong>Phone</strong>
              <span>+91 XXXXX XXXXX</span>
            </div>
            <div className="company-row">
              <strong>Address</strong>
              <span>[Company Address]</span>
            </div>
            <div className="company-row">
              <strong>Working hours</strong>
              <span>[Working Hours]</span>
            </div>
            <p className="setting-note">
              Placeholder contact details — replace them with your organisation's real
              information.
            </p>
          </div>
        </section>
      </div>

      {/* Footer */}
      <footer className="dash-footer">
        <div>
          <div className="dash-footer-brand">© KnowFlow</div>
          <div className="dash-footer-tagline">Enterprise Knowledge Platform</div>
        </div>
        <div className="dash-footer-links">
          <button className="dash-footer-link" onClick={() => setModal('privacy')}>
            Privacy
          </button>
          <button className="dash-footer-link" onClick={() => setModal('terms')}>
            Terms
          </button>
          <button className="dash-footer-link" onClick={() => setModal('help')}>
            Help
          </button>
          <button className="dash-footer-link" onClick={() => setModal('contact')}>
            Contact
          </button>
        </div>
        <div className="dash-footer-version">
          {version ? `Version ${version}` : 'Version —'}
        </div>
      </footer>

      {/* Modals */}
      {modal === 'help' && (
        <Modal title="Help Centre" onClose={() => setModal(null)}>
          <HelpTopic title="Uploading documents">
            Use the Upload Documents page, or open a project and use its upload panel. You can
            add a title, description, category and tags, and KnowFlow extracts the text
            automatically. PDF, DOCX and TXT files up to 500 MB each are supported.
          </HelpTopic>
          <HelpTopic title="Searching documents">
            Use the Search page to find content across all your projects, or search within
            a single project from its page.
          </HelpTopic>
          <HelpTopic title="AI Assistant">
            Ask questions about your documents in the AI Assistant. Answers are grounded in
            the uploaded content with source citations.
          </HelpTopic>
          <HelpTopic title="Managing documents">
            Every document can be viewed, downloaded, replaced with a new version, archived
            or permanently deleted from the Documents page.
          </HelpTopic>
          <HelpTopic title="Account and access">
            Manage your profile picture, name, email and password in Settings. Access is
            controlled by an administrator.
          </HelpTopic>
        </Modal>
      )}

      {modal === 'faq' && (
        <Modal title="Frequently Asked Questions" onClose={() => setModal(null)}>
          <HelpTopic title="How do I upload a document?">
            Open a project and use the upload panel at the top of the page, or use the Upload
            Documents page. PDF, DOCX and TXT files up to 500 MB each are supported.
          </HelpTopic>
          <HelpTopic title="How do I search across documents?">
            Use the Search page in the sidebar. It searches the extracted text of every
            document you can access.
          </HelpTopic>
          <HelpTopic title="What is the AI Assistant?">
            It answers questions using the content of your documents, citing the sources it
            used. It works per project.
          </HelpTopic>
          <HelpTopic title="How do I change my password?">
            Go to Settings, then Privacy &amp; Security, and use the Change Password form.
          </HelpTopic>
          <HelpTopic title="Who can see my documents?">
            Documents belong to projects. Access is managed by your organisation's
            administrators.
          </HelpTopic>
        </Modal>
      )}

      {modal === 'contact' && (
        <Modal title="Contact Support" onClose={() => setModal(null)}>
          <div className="company-block">
            <div className="company-row">
              <strong>Email</strong>
              <span>support@example.com</span>
            </div>
            <div className="company-row">
              <strong>Phone</strong>
              <span>+91 XXXXX XXXXX</span>
            </div>
            <div className="company-row">
              <strong>Address</strong>
              <span>[Company Address]</span>
            </div>
            <div className="company-row">
              <strong>Working hours</strong>
              <span>[Working Hours]</span>
            </div>
            <p className="setting-note">
              Placeholder contact details — replace them with your organisation's real
              information.
            </p>
          </div>
        </Modal>
      )}

      {modal === 'feedback' && (
        <Modal title="Send Feedback" onClose={() => setModal(null)}>
          <FeedbackForm preset={feedbackPreset} onDone={() => setModal(null)} />
        </Modal>
      )}

      {modal === 'about' && (
        <Modal title="About KnowFlow" onClose={() => setModal(null)}>
          <div className="company-block">
            <div className="company-name">KnowFlow</div>
            <div className="company-tagline">Enterprise Knowledge Platform</div>
            <div className="company-row">
              <strong>Version</strong>
              <span>{version || '—'}</span>
            </div>
            <div className="company-row">
              <strong>Deployment</strong>
              <span>Local deployment</span>
            </div>
            <p className="setting-note">
              KnowFlow stores your account and document data in the organisation's local
              database.
            </p>
          </div>
        </Modal>
      )}

      {modal === 'privacy' && (
        <Modal title="Privacy Policy" onClose={() => setModal(null)}>
          <div className="company-block">
            <p className="help-topic-text">
              KnowFlow stores your account details and uploaded documents in the
              organisation's local database. Your data stays within the organisation's
              deployment.
            </p>
            <p className="help-topic-text">
              You accepted the Security &amp; Confidentiality agreement when you joined,
              which governs how documents and knowledge are handled.
            </p>
            <p className="setting-note">
              This is a summary. Replace it with your organisation's full privacy policy.
            </p>
          </div>
        </Modal>
      )}

      {modal === 'terms' && (
        <Modal title="Terms of Service" onClose={() => setModal(null)}>
          <div className="company-block">
            <p className="help-topic-text">
              Use of KnowFlow is subject to the Terms &amp; Conditions accepted during
              account setup, including responsible use of uploaded documents and the
              knowledge base.
            </p>
            <p className="setting-note">
              This is a summary. Replace it with your organisation's full terms of service.
            </p>
          </div>
        </Modal>
      )}
    </div>
  )
}