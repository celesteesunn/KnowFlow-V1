import { useEffect, useRef, useState } from 'react'
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
  upload: icon(
    <>
      <path d="M12 16V4" />
      <path d="m6 10 6-6 6 6" />
      <path d="M4 20h16" />
    </>,
  ),
}

// Upload limits — keep in sync with backend config.py (MAX_UPLOAD_MB,
// ALLOWED_EXTENSIONS). Only values the backend actually accepts are shown.
const MAX_UPLOAD_MB = 500
const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.txt']
const MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024

export default function UploadCard({ onUploaded }) {
  const [projects, setProjects] = useState(null)
  const [projectId, setProjectId] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [uploadError, setUploadError] = useState(null)
  const [picked, setPicked] = useState(null)
  const fileInput = useRef(null)

  useEffect(() => {
    api
      .projects()
      .then((d) => {
        setProjects(d.projects)
        if (d.projects.length > 0) setProjectId(String(d.projects[0].id))
      })
      .catch(() => {})
  }, [])

  const formatSize = (bytes) => {
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
    return `${bytes} B`
  }

  const doUpload = async (files, preRejected) => {
    setUploading(true)
    setUploadMsg(null)
    setUploadError(preRejected.length > 0 ? preRejected.join(' ') : null)

    // Each valid file is uploaded on its own; a file that fails at the
    // server is reported by name and the rest still go through.
    const failed = []
    let uploaded = 0
    for (const file of files) {
      try {
        await api.uploadDocument(projectId, file, {})
        uploaded += 1
      } catch (err) {
        failed.push(`${file.name}: ${err.message}`)
      }
    }

    if (failed.length > 0) {
      setUploadError(
        [
          ...(uploaded > 0 ? [`${uploaded} of ${files.length} files uploaded.`] : []),
          ...failed,
        ].join(' '),
      )
    } else {
      setUploadMsg(
        uploaded === 1
          ? 'Document uploaded successfully.'
          : `${uploaded} documents uploaded successfully.`,
      )
    }
    setPicked(null)
    setUploading(false)
    if (uploaded > 0 && onUploaded) onUploaded()
  }

  // Validate every selected file before any bytes are sent, so a file over
  // the limit never starts uploading and is never silently discarded.
  const onPickFile = (e) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    setUploadMsg(null)
    setUploadError(null)
    if (!projectId) {
      setUploadError('Select a project to upload into.')
      e.target.value = ''
      return
    }

    const valid = []
    const rejected = []
    for (const file of files) {
      const ext = `.${file.name.split('.').pop().toLowerCase()}`
      if (!ALLOWED_EXTENSIONS.includes(ext)) {
        rejected.push(`${file.name}: only PDF, DOCX or TXT files are allowed.`)
        continue
      }
      if (file.size > MAX_BYTES) {
        rejected.push(
          `${file.name}: file too large. The maximum allowed file size is ` +
            `${MAX_UPLOAD_MB} MB. Please choose a smaller file.`,
        )
        continue
      }
      valid.push(file)
    }

    if (valid.length === 0) {
      setUploadError(rejected.join(' '))
      e.target.value = ''
      return
    }
    setPicked(
      valid.length === 1
        ? { name: valid[0].name, size: valid[0].size, count: 1 }
        : { name: '', size: 0, count: valid.length },
    )
    doUpload(valid, rejected)
  }

  return (
    <section className="panel upload-card">
      <div className="upload-card-head">
        <span className="upload-card-icon">{ICONS.upload}</span>
        <div>
          <h2>Upload Documents</h2>
          <p className="muted">
            Add documents to your authorised knowledge space and make them available for your
            team.
          </p>
        </div>
      </div>

      <div className="upload-card-row">
        <select
          className="upload-project"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          disabled={uploading || !projects || projects.length === 0}
          aria-label="Project"
        >
          {projects && projects.length > 0 ? (
            projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))
          ) : (
            <option value="">No projects yet</option>
          )}
        </select>
        <button
          className="btn btn-primary"
          onClick={() => fileInput.current?.click()}
          disabled={uploading || !projects || projects.length === 0}
        >
          {uploading ? 'Uploading…' : 'Upload Documents'}
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".pdf,.docx,.txt"
          multiple
          style={{ display: 'none' }}
          onChange={onPickFile}
          disabled={uploading}
        />
      </div>

      <div className="upload-card-info">
        <span>Maximum file size: {MAX_UPLOAD_MB} MB per file</span>
        <span>
          Supported formats:{' '}
          {ALLOWED_EXTENSIONS.map((e) => e.slice(1).toUpperCase()).join(', ')}
        </span>
      </div>

      {projects && projects.length === 0 && (
        <p className="muted upload-picked">Create a project first to upload documents.</p>
      )}
      {picked && !uploading && (
        <p className="muted upload-picked">
          {picked.count > 1
            ? `${picked.count} files selected`
            : `${picked.name} · ${formatSize(picked.size)}`}
        </p>
      )}
      {uploading && <p className="muted upload-picked">Uploading and extracting text…</p>}
      {uploadMsg && <p className="ok-text upload-picked">{uploadMsg}</p>}
      {uploadError && <p className="error-text upload-picked">{uploadError}</p>}
    </section>
  )
}