// Unsaved-changes registry.
//
// Forms register themselves with setUnsaved(id, dirty) while the user is
// editing. App consults hasUnsaved() before any navigation (sidebar clicks,
// internal Back, browser Back) and before the page unloads, so edits are
// never lost silently. The registry is module-level because forms unmount
// when the view changes; each form clears its own flag on save, cancel and
// unmount.

const dirty = new Set()

export function setUnsaved(id, isDirty) {
  if (isDirty) dirty.add(id)
  else dirty.delete(id)
}

export function hasUnsaved() {
  return dirty.size > 0
}