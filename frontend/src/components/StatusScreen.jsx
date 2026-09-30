// Shown to accounts that were rejected or suspended by an administrator.
export default function StatusScreen({ user, onLogout }) {
  const rejected = user.status === 'rejected'
  const reason = rejected ? user.rejected_reason : user.suspended_reason

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h2>{rejected ? 'Account rejected' : 'Account suspended'}</h2>
        <p className="muted">
          {rejected
            ? 'Your workspace access request was not approved. Please contact your organisation administrator if you believe this was incorrect.'
            : 'Your account has been suspended. Contact an administrator if you believe this is a mistake.'}
        </p>
        {reason && (
          <p className="error-text">
            Reason: {reason}
          </p>
        )}
        <div className="actions">
          <button className="btn" onClick={onLogout}>
            Log out
          </button>
        </div>
      </div>
    </div>
  )
}