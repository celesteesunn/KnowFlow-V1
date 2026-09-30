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
  bookmarks: icon(<path d="M6 3h12v18l-6-4-6 4z" />),
}

export default function BookmarksView() {
  return (
    <div>
      <h1>My Bookmarks</h1>
      <p className="tagline">Quick access to your saved documents, projects and knowledge</p>

      <section className="panel">
        <div className="empty-state">
          {ICONS.bookmarks}
          <span className="empty-state-title">No bookmarks yet</span>
          <span className="empty-state-text">
            Bookmarks are not available in this deployment yet. Documents, projects and
            knowledge articles you save will appear here.
          </span>
        </div>
      </section>
    </div>
  )
}