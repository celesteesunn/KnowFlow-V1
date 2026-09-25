import { useEffect, useState } from 'react'
import { api } from '../api.js'
import Chat from './Chat.jsx'

export default function Assistant() {
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .projects()
      .then((d) => {
        setProjects(d.projects)
        if (d.projects.length > 0) setProjectId(d.projects[0].id)
      })
      .catch((e) => setError(e.message))
  }, [])

  const project = projects.find((p) => p.id === projectId)

  return (
    <div>
      <h1>AI Assistant</h1>
      <p className="tagline">Ask questions about your documents</p>

      <section className="panel">
        <label className="field-label" htmlFor="project-select">
          Project
        </label>
        <select
          id="project-select"
          value={projectId || ''}
          onChange={(e) => setProjectId(Number(e.target.value))}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </section>

      {error && <p className="error-text">{error}</p>}
      {projects.length === 0 && (
        <p className="muted">No projects yet — create one first.</p>
      )}
      {project && <Chat project={project} onBack={() => {}} showBack={false} />}
    </div>
  )
}