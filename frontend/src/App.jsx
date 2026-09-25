import { useEffect, useState } from 'react'
import { api } from './api.js'
import Admin from './components/Admin.jsx'
import Assistant from './components/Assistant.jsx'
import Dashboard from './components/Dashboard.jsx'
import DocumentDetail from './components/DocumentDetail.jsx'
import Documents from './components/Documents.jsx'
import Insights from './components/Insights.jsx'
import Login from './components/Login.jsx'
import ProjectDetail from './components/ProjectDetail.jsx'
import Projects from './components/Projects.jsx'
import Search from './components/Search.jsx'
import './App.css'

function App() {
  const [user, setUser] = useState(null)
  const [booted, setBooted] = useState(false)
  const [view, setView] = useState('dashboard')
  const [project, setProject] = useState(null)
  const [docTarget, setDocTarget] = useState(null)

  useEffect(() => {
    api
      .me()
      .then((d) => setUser(d.user))
      .catch(() => {})
      .finally(() => setBooted(true))

    const onUnauthorized = () => setUser(null)
    window.addEventListener('knowflow:unauthorized', onUnauthorized)
    return () => window.removeEventListener('knowflow:unauthorized', onUnauthorized)
  }, [])

  const go = (v) => {
    setView(v)
    setProject(null)
    setDocTarget(null)
  }

  const openProject = (p) => {
    setProject(p)
    setView('project')
  }

  const openDocument = (docId, projectId, back) => {
    setDocTarget({ docId, projectId, back })
    setView('document')
  }

  if (!booted) {
    return (
      <div className="app">
        <main className="hero">
          <p className="muted">Loading…</p>
        </main>
      </div>
    )
  }

  const nav = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'projects', label: 'Projects' },
    { id: 'documents', label: 'Documents' },
    { id: 'search', label: 'Search' },
    { id: 'assistant', label: 'AI Assistant' },
  ]
  if (user?.is_admin) {
    nav.push({ id: 'admin', label: 'Admin' }, { id: 'insights', label: 'Insights' })
  }

  let content
  if (!user) {
    content = <Login onAuth={setUser} />
  } else if (view === 'project' && project) {
    content = <ProjectDetail project={project} onBack={() => go('projects')} />
  } else if (view === 'document' && docTarget) {
    content = (
      <DocumentDetail
        docId={docTarget.docId}
        projectId={docTarget.projectId}
        onBack={() => go(docTarget.back)}
        onChanged={() => {}}
      />
    )
  } else if (view === 'documents') {
    content = <Documents onOpenDocument={openDocument} />
  } else if (view === 'search') {
    content = <Search onOpenProject={openProject} />
  } else if (view === 'assistant') {
    content = <Assistant />
  } else if (view === 'admin') {
    content = <Admin />
  } else if (view === 'insights') {
    content = <Insights />
  } else if (view === 'projects') {
    content = <Projects user={user} onOpen={openProject} />
  } else {
    content = (
      <Dashboard user={user} onOpenProject={openProject} onOpenDocument={openDocument} />
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" onClick={() => go('dashboard')}>
          <span className="logo">K</span>
          <span className="brand-name">KnowFlow</span>
        </div>
        {user && (
          <nav className="nav">
            {nav.map((n) => (
              <button
                key={n.id}
                className={`nav-link ${view === n.id ? 'nav-link-active' : ''}`}
                onClick={() => go(n.id)}
              >
                {n.label}
              </button>
            ))}
            <span className="nav-user">{user.full_name || user.username}</span>
            <button
              className="btn btn-ghost"
              onClick={() => api.logout().then(() => setUser(null))}
            >
              Log out
            </button>
          </nav>
        )}
      </header>

      <main className="hero">{content}</main>
    </div>
  )
}

export default App