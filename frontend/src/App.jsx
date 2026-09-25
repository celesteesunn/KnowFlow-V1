import { useEffect, useState } from 'react'
import { api } from './api.js'
import Login from './components/Login.jsx'
import ProjectDetail from './components/ProjectDetail.jsx'
import Projects from './components/Projects.jsx'
import './App.css'

function App() {
  const [user, setUser] = useState(null)
  const [booted, setBooted] = useState(false)
  const [project, setProject] = useState(null) // null = projects list

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

  if (!booted) {
    return (
      <div className="app">
        <main className="hero">
          <p className="muted">Loading…</p>
        </main>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand" onClick={() => setProject(null)}>
          <span className="logo">K</span>
          <span className="brand-name">KnowFlow</span>
        </div>
        {user && (
          <div className="nav">
            <span className="nav-user">{user.full_name || user.username}</span>
            <button className="btn btn-ghost" onClick={() => api.logout().then(() => setUser(null))}>
              Log out
            </button>
          </div>
        )}
      </header>

      <main className="hero">
        {!user ? (
          <Login onAuth={setUser} />
        ) : project ? (
          <ProjectDetail project={project} onBack={() => setProject(null)} />
        ) : (
          <Projects user={user} onOpen={setProject} />
        )}
      </main>
    </div>
  )
}

export default App