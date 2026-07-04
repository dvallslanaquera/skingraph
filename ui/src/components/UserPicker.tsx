// Top-right avatar menu: pick the active user or spin up a new one.
// Replaces the old sidebar 現在のユーザー dropdown — consumer apps switch users
// from a profile avatar, not a bare <select>.
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { useUsers } from "../context/UserContext";
import { useI18n } from "../i18n";
import { emptyProfile } from "../lib/profile";

export function UserMenu() {
  const { t } = useI18n();
  const { users, currentUserId, currentUser, selectUser, refreshUsers, loading, error } =
    useUsers();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    setCreateError(null);
    try {
      const { user_id } = await api.createUser({
        name,
        profile: emptyProfile(),
      });
      await refreshUsers();
      selectUser(user_id);
      setNewName("");
      setCreating(false);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const initial =
    (currentUser?.name?.trim()?.[0] ?? "?").toUpperCase() || "?";
  const activeLabel = currentUser?.name || currentUser?.user_id || t("userPicker.select");

  return (
    <div className="user-menu" ref={ref}>
      <button
        type="button"
        className="user-menu-btn"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={activeLabel}
      >
        {initial}
      </button>

      {open && (
        <div className="user-menu-panel" role="menu">
          <div className="user-menu-head">
            <span className="user-menu-head-label">{t("userPicker.activeUser")}</span>
            {error && (
              <span className="user-picker-error" title={error}>
                {t("userPicker.unreachable")}
              </span>
            )}
          </div>

          <ul className="user-menu-list">
            {users.map((u) => (
              <li key={u.user_id}>
                <button
                  type="button"
                  className={`user-menu-item${u.user_id === currentUserId ? " active" : ""}`}
                  onClick={() => {
                    selectUser(u.user_id);
                    setOpen(false);
                  }}
                >
                  <span className="user-menu-item-avatar">
                    {(u.name?.trim()?.[0] ?? "?").toUpperCase()}
                  </span>
                  <span className="user-menu-item-name">{u.name || u.user_id}</span>
                  {u.user_id === currentUserId && (
                    <span className="user-menu-check" aria-hidden="true">
                      ✓
                    </span>
                  )}
                </button>
              </li>
            ))}
            {loading && <li className="user-menu-empty">{t("userPicker.loading")}</li>}
            {!loading && users.length === 0 && (
              <li className="user-menu-empty">{t("userPicker.select")}</li>
            )}
          </ul>

          {creating ? (
            <div className="user-create">
              <input
                className="text-input"
                placeholder={t("userPicker.newName")}
                value={newName}
                autoFocus
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleCreate();
                  if (e.key === "Escape") setCreating(false);
                }}
              />
              <div className="user-create-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={busy || !newName.trim()}
                  onClick={() => void handleCreate()}
                >
                  {busy ? "…" : t("common.create")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={busy}
                  onClick={() => {
                    setCreating(false);
                    setCreateError(null);
                  }}
                >
                  {t("common.cancel")}
                </button>
              </div>
              {createError && <div className="field-error">{createError}</div>}
            </div>
          ) : (
            <button
              type="button"
              className="user-menu-new"
              disabled={!!error}
              onClick={() => setCreating(true)}
            >
              {t("userPicker.newUser")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}