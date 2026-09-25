// KnowFlow API client — talks to the Flask backend via the Vite /api proxy.

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (res.status === 401) {
    // Session expired or not authenticated — let the app show the login page.
    window.dispatchEvent(new CustomEvent('knowflow:unauthorized'))
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

// Multipart upload helper (file + optional metadata fields).
async function upload(path, file, meta = {}) {
  const form = new FormData()
  form.append('file', file)
  if (meta.title) form.append('title', meta.title)
  if (meta.description) form.append('description', meta.description)
  if (meta.category) form.append('category', meta.category)
  const res = await fetch(path, { method: 'POST', body: form })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

export const api = {
  // Auth
  me: () => request('/api/auth/me'),
  register: (body) => request('/api/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body) => request('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),

  // Projects
  projects: () => request('/api/projects'),
  createProject: (body) => request('/api/projects', { method: 'POST', body: JSON.stringify(body) }),

  // Dashboard
  dashboard: () => request('/api/dashboard'),

  // Documents
  documents: (projectId) => request(`/api/projects/${projectId}/documents`),
  allDocuments: () => request('/api/documents'),
  uploadDocument: (projectId, file, meta) =>
    upload(`/api/projects/${projectId}/documents`, file, meta),
  replaceDocument: (projectId, docId, file, meta) =>
    upload(`/api/projects/${projectId}/documents/${docId}/replace`, file, meta),
  documentDetail: (docId) => request(`/api/documents/${docId}`),
  downloadUrl: (docId) => `/api/documents/${docId}/download`,
  archiveDocument: (docId) => request(`/api/documents/${docId}`, { method: 'DELETE' }),
  deleteDocument: (docId) =>
    request(`/api/documents/${docId}/permanent`, { method: 'DELETE' }),

  // Knowledge features
  search: (projectId, q) => request(`/api/projects/${projectId}/search?q=${encodeURIComponent(q)}`),
  globalSearch: (q) => request(`/api/search?q=${encodeURIComponent(q)}`),
  ask: (projectId, question) =>
    request(`/api/projects/${projectId}/ask`, { method: 'POST', body: JSON.stringify({ question }) }),
  chat: (projectId, question) =>
    request('/api/chat', { method: 'POST', body: JSON.stringify({ project_id: projectId, question }) }),
  duplicates: (projectId) => request(`/api/projects/${projectId}/duplicates`),
  relatedDocuments: (docId) =>
    request(`/api/documents/${docId}/related`, { method: 'POST' }),
  knowledgeGaps: () => request('/api/knowledge-gaps'),

  // Admin
  adminUsers: () => request('/api/admin/users'),
  toggleAdmin: (userId) =>
    request(`/api/admin/users/${userId}/admin`, { method: 'POST' }),
  adminInsights: () => request('/api/admin/insights'),
}