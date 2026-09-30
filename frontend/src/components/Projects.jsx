import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { setUnsaved } from '../unsaved.js'

export default function Projects({ user, onOpen }) {
  const [projects, setProjects] = useState([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = () =>
    api
      .projects()
      .then((d) => setProjects(d.projects))
      .catch((e) => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  // Clear the unsaved flag when the projects view unmounts.
  useEffect(() => () => setUnsaved('project-create', false), [])

  const create = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.createProject({ name, description })
      setUnsaved('project-create', false)
      setName('')
      setDescription('')
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <h1>Projects</h1>
      <p className="tagline">Your knowledge projects</p>

      <div className="two-col">
        <section className="panel">
          <h2>New project</h2>
          <form onSubmit={create} className="stack">
            <input
              placeholder="Project name"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                setUnsaved('project-create', true)
              }}
              required
            />
            <input
              placeholder="Description (optional)"
              value={description}
              onChange={(e) => {
                setDescription(e.target.value)
                setUnsaved('project-create', true)
              }}
            />
            {error && <p className="error-text">{error}</p>}
            <button className="btn btn-primary" disabled={busy}>
              {busy ? 'Creating…' : 'Create project'}
            </button>
          </form>
        </section>

        <section className="panel">
          <h2>Projects ({projects.length})</h2>
          {projects.length === 0 && (
            <p className="muted">No projects yet — create your first one.</p>
          )}
          <ul className="project-list">
            {projects.map((p) => (
              <li key={p.id} className="project-item" onClick={() => onOpen(p)}>
                <div>
                  <strong>{p.name}</strong>
                  {p.description && <p className="muted">{p.description}</p>}
                </div>
                <span className="badge">{p.document_count} docs</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}