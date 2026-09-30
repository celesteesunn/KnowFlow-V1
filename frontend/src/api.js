// KnowFlow API client — talks to the Flask backend via the Vite /api proxy.

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await res.json().catch(() => ({}))
  if (res.status === 401) {
    // Session expired or not authenticated — let the app show the login page.
    window.dispatchEvent(new CustomEvent('knowflow:unauthorized'))
  } else if (res.status === 403 && data.code) {
    // Account blocked (unverified / pending / rejected / suspended) — the
    // app re-checks the session and shows the matching status screen.
    window.dispatchEvent(new CustomEvent('knowflow:restricted'))
  }
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
  if (meta.tags) form.append('tags', meta.tags)
  const res = await fetch(path, { method: 'POST', body: form })
  const data = await res.json().catch(() => ({}))
  if (res.status === 403 && data.code) {
    window.dispatchEvent(new CustomEvent('knowflow:restricted'))
  }
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

export const api = {
  // Auth
  me: () => request('/api/auth/me'),
  register: (body) => request('/api/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  login: (body) => request('/api/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  acceptTerms: () => request('/api/auth/accept-terms', { method: 'POST' }),
  acceptSecurity: () => request('/api/auth/accept-security', { method: 'POST' }),
  updateProfile: (body) =>
    request('/api/auth/profile', { method: 'POST', body: JSON.stringify(body) }),
  changePassword: (body) =>
    request('/api/auth/password', { method: 'POST', body: JSON.stringify(body) }),
  uploadAvatar: (file) => upload('/api/auth/avatar', file),
  removeAvatar: () => request('/api/auth/avatar', { method: 'DELETE' }),
  avatarUrl: (name) => `/api/avatars/${encodeURIComponent(name)}`,
  health: () => request('/api/health'),

  // Workspaces & onboarding
  createWorkspace: (body) =>
    request('/api/workspaces', { method: 'POST', body: JSON.stringify(body) }),
  verifyWorkspace: (body) =>
    request('/api/workspaces/verify', { method: 'POST', body: JSON.stringify(body) }),
  requestAccess: (body) =>
    request('/api/workspaces/request-access', { method: 'POST', body: JSON.stringify(body) }),

  // Notifications
  notifications: () => request('/api/notifications'),
  markNotificationRead: (id) =>
    request(`/api/notifications/${id}/read`, { method: 'POST' }),
  markAllNotificationsRead: () =>
    request('/api/notifications/read-all', { method: 'POST' }),

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
  documentText: (docId) => request(`/api/documents/${docId}/text`),
  downloadUrl: (docId) => `/api/documents/${docId}/download`,
  viewUrl: (docId) => `/api/documents/${docId}/view`,
  archiveDocument: (docId) => request(`/api/documents/${docId}`, { method: 'DELETE' }),
  deleteDocument: (docId) =>
    request(`/api/documents/${docId}/permanent`, { method: 'DELETE' }),

  // Knowledge features
  search: (projectId, q) => request(`/api/projects/${projectId}/search?q=${encodeURIComponent(q)}`),
  globalSearch: (q, filters = {}) => {
    const sp = new URLSearchParams({ q })
    if (filters.category) sp.set('category', filters.category)
    if (filters.type) sp.set('type', filters.type)
    if (filters.project_id) sp.set('project_id', filters.project_id)
    if (filters.uploaded_by) sp.set('uploaded_by', filters.uploaded_by)
    if (filters.date_from) sp.set('date_from', filters.date_from)
    if (filters.date_to) sp.set('date_to', filters.date_to)
    if (filters.tags) sp.set('tags', filters.tags)
    return request(`/api/search?${sp.toString()}`)
  },
  searchSuggestions: (q) =>
    request(`/api/search/suggestions?q=${encodeURIComponent(q)}`),
  ask: (projectId, question) =>
    request(`/api/projects/${projectId}/ask`, { method: 'POST', body: JSON.stringify({ question }) }),
  chat: (projectId, question) =>
    request('/api/chat', { method: 'POST', body: JSON.stringify({ project_id: projectId, question }) }),
  chatHistory: (projectId) =>
    request(`/api/chat/history?project_id=${projectId}`),
  clearChatHistory: (projectId) =>
    request('/api/chat/history/clear', { method: 'POST', body: JSON.stringify({ project_id: projectId }) }),
  duplicates: (projectId) => request(`/api/projects/${projectId}/duplicates`),
  relatedDocuments: (docId) =>
    request(`/api/documents/${docId}/related`, { method: 'POST' }),
  knowledgeGaps: () => request('/api/knowledge-gaps'),

  // Profile
  profileActivity: () => request('/api/profile/activity'),

  // Members directory
  members: (params = {}) => {
    const sp = new URLSearchParams()
    if (params.q) sp.set('q', params.q)
    if (params.category) sp.set('category', params.category)
    if (params.department) sp.set('department', params.department)
    const qs = sp.toString()
    return request(`/api/members${qs ? `?${qs}` : ''}`)
  },
  memberDepartments: () => request('/api/members/departments'),
  member: (userId) => request(`/api/members/${userId}`),
  updateMember: (userId, body) =>
    request(`/api/members/${userId}`, { method: 'POST', body: JSON.stringify(body) }),

  // Admin
  adminUsers: () => request('/api/admin/users'),
  toggleAdmin: (userId) =>
    request(`/api/admin/users/${userId}/admin`, { method: 'POST' }),
  adminApprove: (userId) =>
    request(`/api/admin/users/${userId}/approve`, { method: 'POST' }),
  adminReject: (userId, reason) =>
    request(`/api/admin/users/${userId}/reject`, { method: 'POST', body: JSON.stringify({ reason }) }),
  adminSuspend: (userId, reason) =>
    request(`/api/admin/users/${userId}/suspend`, { method: 'POST', body: JSON.stringify({ reason }) }),
  adminReactivate: (userId) =>
    request(`/api/admin/users/${userId}/reactivate`, { method: 'POST' }),
  adminInsights: () => request('/api/admin/insights'),

  // Admin — workspace access requests
  adminAccessRequests: () => request('/api/admin/access-requests'),
  adminPendingCount: () => request('/api/admin/pending-count'),
  adminApproveRequest: (userId) =>
    request(`/api/admin/access-requests/${userId}/approve`, { method: 'POST' }),
  adminRejectRequest: (userId, reason) =>
    request(`/api/admin/access-requests/${userId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  // Admin — roles
  adminRoles: () => request('/api/admin/roles'),
  adminCreateRole: (body) =>
    request('/api/admin/roles', { method: 'POST', body: JSON.stringify(body) }),
  adminUpdateRole: (roleId, body) =>
    request(`/api/admin/roles/${roleId}`, { method: 'POST', body: JSON.stringify(body) }),
  adminDeleteRole: (roleId) =>
    request(`/api/admin/roles/${roleId}`, { method: 'DELETE' }),

  // Admin — departments
  adminDepartments: () => request('/api/admin/departments'),
  adminCreateDepartment: (body) =>
    request('/api/admin/departments', { method: 'POST', body: JSON.stringify(body) }),
  adminDeleteDepartment: (deptId) =>
    request(`/api/admin/departments/${deptId}`, { method: 'DELETE' }),

  // Admin — workspace settings
  adminWorkspace: () => request('/api/admin/workspace'),
  adminUpdateWorkspace: (body) =>
    request('/api/admin/workspace', { method: 'POST', body: JSON.stringify(body) }),
  adminRegenerateCode: () =>
    request('/api/admin/workspace/regenerate-code', { method: 'POST' }),
}