import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { createHistoryTracker, parseHash, serializeState } from './nav.js'
import { hasUnsaved } from './unsaved.js'
import Admin from './components/Admin.jsx'
import Agreements from './components/Agreements.jsx'
import Assistant from './components/Assistant.jsx'
import BookmarksView from './components/BookmarksView.jsx'
import Dashboard from './components/Dashboard.jsx'
import DocumentDetail from './components/DocumentDetail.jsx'
import Documents from './components/Documents.jsx'
import Insights from './components/Insights.jsx'
import KnowledgeView from './components/KnowledgeView.jsx'
import Login from './components/Login.jsx'
import MembersView from './components/MembersView.jsx'
import NotificationsView from './components/NotificationsView.jsx'
import Onboarding from './components/Onboarding.jsx'
import PendingApproval from './components/PendingApproval.jsx'
import Profile from './components/Profile.jsx'
import ProjectDetail from './components/ProjectDetail.jsx'
import Projects from './components/Projects.jsx'
import Search from './components/Search.jsx'
import Settings from './components/Settings.jsx'
import StatusScreen from './components/StatusScreen.jsx'
import UploadView from './components/UploadView.jsx'
import './App.css'

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
  dashboard: icon(
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>,
  ),
  projects: icon(
    <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />,
  ),
  members: icon(
    <>
      <path d="M17 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9.5" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </>,
  ),
  documents: icon(
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </>,
  ),
  upload: icon(
    <>
      <path d="M12 16V4" />
      <path d="m6 10 6-6 6 6" />
      <path d="M4 20h16" />
    </>,
  ),
  assistant: icon(
    <>
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
      <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" />
    </>,
  ),
  knowledge: icon(
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7c-2-1.5-5-1.5-7 0v10c2-1.5 5-1.5 7 0s5-1.5 7 0V7c-2-1.5-5-1.5-7 0z" />
      <path d="M12 7v10" />
    </>,
  ),
  bookmarks: icon(
    <path d="M6 3h12v18l-6-4-6 4z" />,
  ),
  bell: icon(
    <>
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.7 21a2 2 0 0 1-3.4 0" />
    </>,
  ),
  insights: icon(
    <>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20H2" />
    </>,
  ),
  profile: icon(
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21c0-4 3.6-6 8-6s8 2 8 6" />
    </>,
  ),
  admin: icon(
    <>
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" />
      <path d="M9.5 12l1.8 1.8L15 10" />
    </>,
  ),
  settings: icon(
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h.09a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v.09a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z" />
    </>,
  ),
  logout: icon(
    <>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5" />
      <path d="M21 12H9" />
    </>,
  ),
  menu: icon(
    <>
      <path d="M4 6h16" />
      <path d="M4 12h16" />
      <path d="M4 18h16" />
    </>,
  ),
}

const userInitials = (u) => {
  const name = (u.full_name || u.username || '?').trim()
  const parts = name.split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

const Logo = ({ className = '' }) => {
  const [failed, setFailed] = useState(false)
  if (failed) return <span className={`logo ${className}`}>K</span>
  return (
    <img
      src="/logo.png"
      alt="KnowFlow"
      className={`logo-img ${className}`}
      onError={() => setFailed(true)}
    />
  )
}

// Small modal used for logout / leave / unsaved-changes confirmations.
function ConfirmDialog({ title, message, cancelLabel, confirmLabel, onCancel, onConfirm, danger }) {
  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-card confirm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{title}</span>
        </div>
        <div className="modal-body">
          <p className="confirm-message">{message}</p>
          <div className="actions">
            <button className="btn" onClick={onCancel}>
              {cancelLabel}
            </button>
            <button
              className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
              onClick={onConfirm}
            >
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

const DEFAULT_SETTINGS = {
  theme: 'dark',
  density: 'comfortable',
  notifications: { uploads: true, projects: true, comments: false, knowledge: true, email: false },
  documents: { view: 'list', sort: 'newest', multiUpload: true, autoRefresh: true },
  accessibility: { fontSize: 'medium', reducedMotion: false, highContrast: false },
}

const SETTINGS_KEY = 'knowflow.settings'

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const parsed = JSON.parse(raw)
    return {
      ...DEFAULT_SETTINGS,
      ...parsed,
      notifications: { ...DEFAULT_SETTINGS.notifications, ...(parsed.notifications || {}) },
      documents: { ...DEFAULT_SETTINGS.documents, ...(parsed.documents || {}) },
      accessibility: { ...DEFAULT_SETTINGS.accessibility, ...(parsed.accessibility || {}) },
    }
  } catch {
    return DEFAULT_SETTINGS
  }
}

const VIEW_TITLES = {
  documents: 'Documents',
  upload: 'Upload Documents',
  search: 'Search',
  assistant: 'AI Assistant',
  knowledge: 'Knowledge',
  projects: 'Projects',
  members: 'Members',
  bookmarks: 'My Bookmarks',
  notifications: 'Notifications',
  profile: 'My Profile',
  admin: 'Admin',
  insights: 'Insights',
  settings: 'Settings',
}

function App() {
  const [user, setUser] = useState(null)
  const [booted, setBooted] = useState(false)
  const [view, setView] = useState('dashboard')
  const [project, setProject] = useState(null)
  const [docTarget, setDocTarget] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [settings, setSettings] = useState(loadSettings)
  // Auth lifecycle: message shown on the login screen (logged out /
  // session expired) and the confirmation dialogs.
  const [authMessage, setAuthMessage] = useState('')
  const [logoutOpen, setLogoutOpen] = useState(false)
  const [leaveOpen, setLeaveOpen] = useState(false)
  const [unsavedOpen, setUnsavedOpen] = useState(false)

  // History-based navigation bookkeeping. The tracker mirrors the KnowFlow
  // entries in the browser history so in-app Back buttons know whether a
  // previous KnowFlow page exists (and never leave the application).
  const tracker = useRef(createHistoryTracker()).current

  // Refs mirror live values for the popstate listener (registered once with
  // empty deps, so it must not close over stale state).
  const activeRef = useRef(false)
  const userRef = useRef(null)
  const stateRef = useRef({ view: 'dashboard' })
  // A browser Back that would leave KnowFlow is deferred until the user
  // confirms; leavePendingRef lets the confirmed Back actually exit.
  const pendingNavRef = useRef(null)
  const leavePendingRef = useRef(false)
  // Set when the user confirms discarding unsaved changes, so the deferred
  // navigation runs without re-prompting.
  const unsavedConfirmedRef = useRef(false)

  const applyState = (state) => {
    stateRef.current = state
    setView(state.view || 'dashboard')
    setProject(state.project || null)
    setDocTarget(state.docTarget || null)
    setSearchQuery(state.query || '')
    setMenuOpen(false)
  }

  useEffect(() => {
    let cancelled = false

    // Restore the page from the URL on direct access (e.g. #/documents),
    // and mark the current entry as a KnowFlow entry so Back/Forward can
    // return to it and in-app Back knows it is at the start of history.
    const initHistory = async () => {
      const parsed = parseHash()
      let state = { view: parsed.view || 'dashboard', query: parsed.query || '' }
      if (parsed.view === 'project' && parsed.projectId) {
        try {
          const d = await api.projects()
          const p = (d.projects || []).find((x) => x.id === parsed.projectId)
          state = p ? { view: 'project', project: p } : { view: 'projects' }
        } catch {
          state = { view: 'projects' }
        }
      } else if (parsed.view === 'document' && parsed.docId) {
        state = {
          view: 'document',
          docTarget: {
            docId: parsed.docId,
            projectId: parsed.projectId || null,
            back: 'documents',
          },
        }
      }
      if (cancelled) return
      tracker.reset(1)
      const url = serializeState(state)
      // Boundary sentinel: replace the current entry with a marker, then push
      // the real first KnowFlow entry on top. Browser Back from the first
      // page now lands on the sentinel (same-document navigation) so popstate
      // can intercept it and ask before leaving the application. Without this,
      // Back from the first page is a cross-document navigation to the
      // previous website and popstate never fires.
      history.replaceState({ kf: 'sentinel' }, '', url)
      history.pushState({ kf: true, id: 1, s: state }, '', url)
      applyState(state)
    }

    const boot = async () => {
      await Promise.all([
        api.me().then((d) => setUser(d.user)).catch(() => {}),
        initHistory(),
      ])
      if (!cancelled) setBooted(true)
    }
    boot()

    // A 401 mid-session means the session expired or was invalidated.
    // Only show the expiry message when the user was actually signed in.
    const onUnauthorized = () => {
      if (userRef.current) {
        setAuthMessage('Your session has expired. Please sign in again.')
      }
      setUser(null)
    }
    const onRestricted = () => {
      api
        .me()
        .then((d) => setUser(d.user))
        .catch(() => {})
    }
    // Ask before leaving: show the Leave dialog (or the unsaved-changes
    // dialog first when edits are pending). The user is sitting on the
    // boundary entry, so "Stay" replaces it with the current page and
    // "Leave" continues the Back navigation.
    const askBeforeLeave = () => {
      if (hasUnsaved() && !unsavedConfirmedRef.current) {
        pendingNavRef.current = () => {
          unsavedConfirmedRef.current = true
          leavePendingRef.current = true
          history.back()
        }
        setUnsavedOpen(true)
      } else {
        setLeaveOpen(true)
      }
    }

    // Browser Back/Forward: restore the KnowFlow page from history state.
    // When Back reaches the boundary of KnowFlow's history (the sentinel
    // entry, or the first page after a "Stay"), keep the page and ask before
    // actually leaving the application.
    const onPop = () => {
      const st = history.state

      // Leaving was confirmed: keep backing until we exit KnowFlow history
      // (stale entries from before a refresh/logout may sit below the
      // boundary). Terminates because the stack is finite.
      if (leavePendingRef.current) {
        if (st && st.kf) {
          history.back()
          return
        }
        leavePendingRef.current = false
        tracker.markStart()
        return
      }

      if (st && st.kf && st.s) {
        // Landed on a real KnowFlow page.
        if (tracker.atStart()) {
          // Boundary reached after "Stay": the entry below the first
          // KnowFlow page is another copy of it, not a previous page.
          if (!activeRef.current) {
            tracker.markStart()
            return
          }
          askBeforeLeave()
          return
        }
        // Normal Back/Forward between KnowFlow pages.
        if (hasUnsaved() && !unsavedConfirmedRef.current) {
          // Restore the current page and ask before discarding edits.
          const cur = stateRef.current
          const url = serializeState(cur)
          const { id } = tracker.record(url, window.location.hash)
          history.pushState({ kf: true, id, s: cur }, '', url)
          pendingNavRef.current = () => history.back()
          setUnsavedOpen(true)
          return
        }
        unsavedConfirmedRef.current = false
        tracker.sync(st.id)
        applyState(st.s)
        return
      }

      if (st && st.kf === 'sentinel') {
        // Boundary: browser Back from the first KnowFlow page landed on the
        // sentinel entry. Keep the page and ask before leaving.
        if (!activeRef.current) {
          tracker.markStart()
          return
        }
        askBeforeLeave()
        return
      }

      // Entry outside KnowFlow (defensive; cross-document navigations do not
      // fire popstate, so this is rarely reached).
      tracker.markStart()
    }
    // Native browser warning when the user refreshes/closes with edits.
    const onBeforeUnload = (e) => {
      if (hasUnsaved()) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('popstate', onPop)
    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('knowflow:unauthorized', onUnauthorized)
    window.addEventListener('knowflow:restricted', onRestricted)
    return () => {
      cancelled = true
      window.removeEventListener('popstate', onPop)
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('knowflow:unauthorized', onUnauthorized)
      window.removeEventListener('knowflow:restricted', onRestricted)
    }
  }, [])

  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e) => {
      if (e.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  // Apply saved appearance/accessibility preferences.
  useEffect(() => {
    const root = document.documentElement
    const apply = () => {
      const theme =
        settings.theme === 'system'
          ? window.matchMedia('(prefers-color-scheme: light)').matches
            ? 'light'
            : 'dark'
          : settings.theme
      root.setAttribute('data-theme', theme)
      root.classList.toggle('density-compact', settings.density === 'compact')
      root.classList.toggle('reduce-motion', settings.accessibility.reducedMotion)
      root.classList.toggle('high-contrast', settings.accessibility.highContrast)
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
    }
    apply()
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    const onMq = () => {
      if (settings.theme === 'system') apply()
    }
    mq.addEventListener('change', onMq)
    return () => mq.removeEventListener('change', onMq)
  }, [settings])

  // Record a page change in the browser history and render it. If a form
  // has unsaved changes, ask first (the navigation is deferred until the
  // user confirms).
  const navigate = (state) => {
    if (hasUnsaved() && !unsavedConfirmedRef.current) {
      pendingNavRef.current = () => navigate(state)
      setUnsavedOpen(true)
      return
    }
    unsavedConfirmedRef.current = false
    const url = serializeState(state)
    const { id, action } = tracker.record(url, window.location.hash)
    if (action === 'push') {
      history.pushState({ kf: true, id, s: state }, '', url)
    } else {
      history.replaceState({ kf: true, id, s: state }, '', url)
    }
    applyState(state)
  }

  const go = (v) => navigate({ view: v })

  const openProject = (p) => navigate({ view: 'project', project: p })

  const openDocument = (docId, projectId, back) =>
    navigate({ view: 'document', docTarget: { docId, projectId, back } })

  const runSearch = (q) => navigate({ view: 'search', query: q })

  // In-app Back/Go Back: return to the previous KnowFlow page when one
  // exists in history; otherwise fall back to a sensible page. Never
  // navigates outside the application.
  const goBack = (fallback) => {
    if (!tracker.atStart()) {
      if (hasUnsaved() && !unsavedConfirmedRef.current) {
        pendingNavRef.current = () => goBack(fallback)
        setUnsavedOpen(true)
        return
      }
      history.back()
    } else if (fallback) {
      navigate({ view: fallback })
    }
  }

  const handleAuth = (u) => {
    setUser(u)
    setAuthMessage('')
    leavePendingRef.current = false
    unsavedConfirmedRef.current = false
    pendingNavRef.current = null
  }

  // Logout is confirmed in a dialog first, then the session is cleared and
  // the user is sent to the login screen with a confirmation message.
  const openLogoutConfirm = () => setLogoutOpen(true)

  const doLogout = async () => {
    setLogoutOpen(false)
    try {
      await api.logout()
    } catch {
      // Session may already be gone — clear locally regardless.
    }
    // Reset navigation history so browser Back cannot return to protected
    // pages after logout.
    tracker.reset(1)
    history.replaceState({ kf: true, id: 1, s: { view: 'dashboard' } }, '', '#/dashboard')
    leavePendingRef.current = false
    unsavedConfirmedRef.current = false
    pendingNavRef.current = null
    setUser(null)
    setAuthMessage("You've been logged out successfully.")
  }

  if (!booted) {
    return (
      <div className="app">
        <div className="app-main">
          <main className="hero">
            <p className="muted">Loading…</p>
          </main>
        </div>
      </div>
    )
  }

  const active = user && user.status === 'active'
  activeRef.current = active
  userRef.current = user

  const sideNav = [
    { id: 'dashboard', label: 'Dashboard', icon: ICONS.dashboard },
    { id: 'documents', label: 'Documents', icon: ICONS.documents },
    { id: 'upload', label: 'Upload', icon: ICONS.upload },
    { id: 'assistant', label: 'AI Assistant', icon: ICONS.assistant },
    { id: 'knowledge', label: 'Knowledge', icon: ICONS.knowledge },
    { id: 'projects', label: 'Projects', icon: ICONS.projects },
    { id: 'members', label: 'Members', icon: ICONS.members },
    { id: 'bookmarks', label: 'My Bookmarks', icon: ICONS.bookmarks },
  ]
  if (user?.is_admin) {
    sideNav.push({ id: 'insights', label: 'Insights', icon: ICONS.insights })
  }
  sideNav.push({ id: 'settings', label: 'Settings', icon: ICONS.settings })

  const nav = {
    search: runSearch,
    assistant: () => go('assistant'),
    upload: () => go('upload'),
    documents: () => go('documents'),
    projects: () => go('projects'),
    members: () => go('members'),
    knowledge: () => go('knowledge'),
    bookmarks: () => go('bookmarks'),
    notifications: () => go('notifications'),
    admin: () => go('admin'),
  }

  let content
  if (!user) {
    content = <Login onAuth={handleAuth} message={authMessage} />
  } else if (user.status === 'rejected' || user.status === 'suspended') {
    content = <StatusScreen user={user} onLogout={openLogoutConfirm} />
  } else if (user.status === 'onboarding' || user.status === 'pending_approval') {
    // New accounts complete workspace setup first (create a workspace or
    // request access). Employees stay on the wizard's success screen while
    // their request is pending — they only reach the agreements and the
    // platform after an administrator approves them.
    content = <Onboarding user={user} onAuth={setUser} onLogout={openLogoutConfirm} />
  } else if (!user.terms_accepted || !user.security_agreed) {
    // Every account (including the bootstrap admin) must accept the
    // agreements before using the platform.
    content = <Agreements user={user} onAuth={setUser} />
  } else if (user.status === 'pending_approval') {
    content = <PendingApproval user={user} onAuth={setUser} onLogout={openLogoutConfirm} />
  } else if (view === 'project' && project) {
    content = <ProjectDetail project={project} onBack={() => goBack('projects')} />
  } else if (view === 'document' && docTarget) {
    content = (
      <DocumentDetail
        docId={docTarget.docId}
        projectId={docTarget.projectId}
        onBack={() => goBack(docTarget.back || 'documents')}
        onChanged={() => {}}
      />
    )
  } else if (view === 'documents') {
    content = <Documents onOpenDocument={openDocument} />
  } else if (view === 'upload') {
    content = <UploadView />
  } else if (view === 'search') {
    content = <Search onOpenProject={openProject} onOpenDocument={openDocument} initialQuery={searchQuery} />
  } else if (view === 'assistant') {
    content = <Assistant />
  } else if (view === 'knowledge') {
    content = <KnowledgeView onOpenDocument={openDocument} nav={nav} />
  } else if (view === 'bookmarks') {
    content = <BookmarksView />
  } else if (view === 'members') {
    content = <MembersView user={user} />
  } else if (view === 'notifications') {
    content = <NotificationsView />
  } else if (view === 'profile') {
    content = (
      <Profile
        user={user}
        onAuth={setUser}
        onOpenProject={openProject}
        onOpenDocument={openDocument}
      />
    )
  } else if (view === 'admin') {
    content = <Admin />
  } else if (view === 'insights') {
    content = <Insights />
  } else if (view === 'settings') {
    content = <Settings user={user} onAuth={setUser} settings={settings} onChange={setSettings} />
  } else if (view === 'projects') {
    content = <Projects user={user} onOpen={openProject} />
  } else {
    content = (
      <Dashboard user={user} onOpenProject={openProject} onOpenDocument={openDocument} nav={nav} />
    )
  }

  const fontClass =
    settings.accessibility.fontSize === 'small'
      ? 'font-small'
      : settings.accessibility.fontSize === 'large'
        ? 'font-large'
        : ''

  // Header title: time-based greeting on the dashboard, view name elsewhere.
  let headerTitle = 'KnowFlow'
  if (active) {
    if (view === 'dashboard') {
      const h = new Date().getHours()
      const part = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
      const first = (user.full_name || user.username || '').trim().split(/\s+/)[0] || ''
      headerTitle = `${part}${first ? `, ${first}` : ''}`
    } else if (view === 'project' && project) {
      headerTitle = project.name
    } else if (view === 'document') {
      headerTitle = 'Document'
    } else {
      headerTitle = VIEW_TITLES[view] || 'KnowFlow'
    }
  }

  return (
    <div className={`app${fontClass ? ` ${fontClass}` : ''}`}>
      {active && (
        <>
          <aside className={`sidebar${menuOpen ? ' sidebar-open' : ''}`}>
            <div className="side-brand" onClick={() => go('dashboard')}>
              <div className="side-brand-row">
                <Logo />
                <span className="side-brand-name">KnowFlow</span>
              </div>
              <span className="side-brand-tagline">Enterprise Knowledge Platform</span>
            </div>
            <nav className="side-nav">
              {sideNav.map((n) => (
                <button
                  key={n.id}
                  className={`side-link ${view === n.id ? 'side-link-active' : ''}`}
                  onClick={() => go(n.id)}
                >
                  {n.icon}
                  <span>{n.label}</span>
                </button>
              ))}
            </nav>
            <div className="side-user-card">
              <span className="side-user-avatar">
                {user.avatar ? (
                  <img src={api.avatarUrl(user.avatar)} alt="" />
                ) : (
                  userInitials(user)
                )}
              </span>
              <div className="side-user-info">
                <span className="side-user-name">{user.full_name || user.username}</span>
                <span className="side-user-role">
                  {user.is_admin ? 'Administrator' : 'Member'}
                </span>
                <span className="side-user-status">
                  <span className="status-dot" />
                  Active
                </span>
              </div>
              <button
                className="side-logout"
                onClick={openLogoutConfirm}
                aria-label="Log out"
                title="Log out"
              >
                {ICONS.logout}
              </button>
            </div>
          </aside>
          {menuOpen && (
            <div className="sidebar-backdrop" onClick={() => setMenuOpen(false)} />
          )}
        </>
      )}

      <div className="app-main">
        <header className="topbar">
          {active && (
            <button
              className="menu-toggle"
              onClick={() => setMenuOpen(!menuOpen)}
              aria-label="Toggle menu"
            >
              {ICONS.menu}
            </button>
          )}
          {active ? (
            <div className="topbar-title-wrap">
              <Logo className="topbar-logo" />
              <div className="topbar-title">{headerTitle}</div>
            </div>
          ) : (
            <div className="brand" onClick={() => go('dashboard')}>
              <Logo />
              <span className="brand-name">KnowFlow</span>
            </div>
          )}
          {active && (
            <div className="top-actions">
              <button className="top-action" onClick={() => go('notifications')}>
                {ICONS.bell}
                <span>Notifications</span>
              </button>
              <button className="top-action" onClick={() => go('profile')}>
                {ICONS.profile}
                <span>Profile</span>
              </button>
              {user.is_admin && (
                <button className="top-action" onClick={() => go('admin')}>
                  {ICONS.admin}
                  <span>Admin</span>
                </button>
              )}
              <button className="btn btn-ghost" onClick={openLogoutConfirm}>
                Log out
              </button>
            </div>
          )}
        </header>

        <main className="hero">{content}</main>
      </div>

      {logoutOpen && (
        <ConfirmDialog
          title="Log out of KnowFlow?"
          message="You will need to sign in again to access your documents, projects and knowledge."
          cancelLabel="Cancel"
          confirmLabel="Log out"
          danger
          onCancel={() => setLogoutOpen(false)}
          onConfirm={doLogout}
        />
      )}

      {leaveOpen && (
        <ConfirmDialog
          title="Leave KnowFlow?"
          message="You are about to leave the KnowFlow application and return to the previous browser page."
          cancelLabel="Stay in KnowFlow"
          confirmLabel="Leave KnowFlow"
          danger
          onCancel={() => {
            // Stay: push the current page on top of the boundary entry so the
            // user is back on the KnowFlow page and the next Back hits the
            // boundary again. pushState truncates the stale forward entry, so
            // no duplicate entries accumulate.
            const cur = stateRef.current
            const url = serializeState(cur)
            const { id } = tracker.record(url, window.location.hash)
            history.pushState({ kf: true, id, s: cur }, '', url)
            setLeaveOpen(false)
          }}
          onConfirm={() => {
            // Leave: allow the original Back navigation to continue.
            leavePendingRef.current = true
            setLeaveOpen(false)
            history.back()
          }}
        />
      )}

      {unsavedOpen && (
        <ConfirmDialog
          title="Unsaved changes"
          message="You have unsaved changes. If you leave now, your changes will be lost."
          cancelLabel="Stay"
          confirmLabel="Leave"
          danger
          onCancel={() => {
            pendingNavRef.current = null
            setUnsavedOpen(false)
          }}
          onConfirm={() => {
            unsavedConfirmedRef.current = true
            setUnsavedOpen(false)
            const fn = pendingNavRef.current
            pendingNavRef.current = null
            if (fn) fn()
          }}
        />
      )}
    </div>
  )
}

export default App