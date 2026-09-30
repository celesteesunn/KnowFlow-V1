// KnowFlow navigation helpers — hash-based URLs + browser history state.
//
// KnowFlow is a single-page app. Every page change is recorded in the
// browser history (a hash URL plus state) so the browser Back/Forward
// buttons move between KnowFlow pages instead of leaving the app. In-app
// Back/Go Back buttons use goBack() in App.jsx, which only navigates
// within KnowFlow and never leaves the application.

export const VALID_VIEWS = new Set([
  'dashboard',
  'documents',
  'upload',
  'search',
  'assistant',
  'knowledge',
  'projects',
  'members',
  'bookmarks',
  'notifications',
  'profile',
  'admin',
  'insights',
  'settings',
  'project',
  'document',
])

// Serialize app state to a hash URL, e.g. "#/documents", "#/project/3",
// "#/document/5?project=3", "#/search?q=budget".
export function serializeState(state) {
  const { view, project, docTarget, query } = state
  if (view === 'project' && project) return `#/project/${project.id}`
  if (view === 'document' && docTarget) {
    let url = `#/document/${docTarget.docId}`
    if (docTarget.projectId) url += `?project=${docTarget.projectId}`
    return url
  }
  if (view === 'search' && query) return `#/search?q=${encodeURIComponent(query)}`
  return `#/${view || 'dashboard'}`
}

// Parse a hash URL into app state. Unknown views fall back to the dashboard.
export function parseHash(hash = window.location.hash) {
  const raw = hash.replace(/^#\/?/, '')
  const [pathPart, queryPart] = raw.split('?')
  const params = new URLSearchParams(queryPart || '')
  const segs = pathPart.split('/').filter(Boolean)
  const view = segs[0] || 'dashboard'
  if (!VALID_VIEWS.has(view)) return { view: 'dashboard', query: '' }
  if (view === 'project' && segs[1]) {
    return { view, projectId: Number(segs[1]), query: params.get('q') || '' }
  }
  if (view === 'document' && segs[1]) {
    return {
      view,
      docId: Number(segs[1]),
      projectId: Number(params.get('project')) || null,
      query: params.get('q') || '',
    }
  }
  return { view, query: params.get('q') || '' }
}

// Tracks the KnowFlow entries in the browser history so in-app Back knows
// whether a previous KnowFlow page exists (and never leaves the app).
// Pure logic — no window/history access — so it can be unit tested.
export function createHistoryTracker() {
  let navId = 0
  const stack = []
  let pos = 0

  return {
    // Record a navigation to `url`. If the URL is unchanged (same page),
    // the current entry is replaced instead of pushing a duplicate.
    // Returns { id, action: 'push' | 'replace' }.
    record(url, currentHash) {
      const id = ++navId
      if (url === currentHash) {
        if (stack.length) stack[pos] = id
        else {
          stack.push(id)
          pos = 0
        }
        return { id, action: 'replace' }
      }
      stack.push(id)
      pos = stack.length - 1
      return { id, action: 'push' }
    },

    // After a popstate to a known KnowFlow entry, move the position there.
    sync(id) {
      const idx = stack.indexOf(id)
      if (idx >= 0) pos = idx
    },

    // Reached an entry outside KnowFlow (browser Back at the start).
    markStart() {
      pos = 0
    },

    // Record the initial entry (direct page access) as position 0.
    reset(id) {
      navId = id
      stack.length = 0
      stack.push(id)
      pos = 0
    },

    // True when there is no previous KnowFlow page to go back to.
    atStart() {
      return pos <= 0
    },
  }
}