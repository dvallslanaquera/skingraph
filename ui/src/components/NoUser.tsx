// Shared empty-state shown on pages that require an active user.
export function NoUser({ action }: { action: string }) {
  return (
    <div className="empty-state">
      <div className="empty-emoji">👤</div>
      <h2>No user selected</h2>
      <p>
        Pick a user from the sidebar (or create one) to {action}.
      </p>
    </div>
  );
}
