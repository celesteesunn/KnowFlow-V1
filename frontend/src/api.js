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

export const api = {
  // Auth
  me: () => request('/api/auth/me'),
  register: (body) => request('/api/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body) => request('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),

  // Projects
  projects: () => request('/api/projects'),
  createProject: (body) => request('/api/projects', { method: 'POST', body: JSON.stringify(body) }),

  // Documents
  documents: (projectId) => request(`/api/projects/${projectId}/documents`),
  uploadDocument: (projectId, file) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`/api/projects/${projectId}/documents`, { method: 'POST', body: form }).then(
      async (res) => {
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
        return data
      },
    )
  },
  search: (projectId, q) => request(`/api/projects/${projectId}/search?q=${encodeURIComponent(q)}`),
  ask: (projectId, question) =>
    request(`/api/projects/${projectId}/ask`, { method: 'POST', body: JSON.stringify({ question }) }),
  duplicates: (projectId) => request(`/api/projects/${projectId}/duplicates`),
}