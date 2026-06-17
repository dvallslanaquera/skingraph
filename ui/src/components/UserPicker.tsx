// Sidebar dropdown to choose the active user, plus a quick "new user" action.
import { useState } from "react";
import { api } from "../api/client";
import { useUsers } from "../context/UserContext";
import { useI18n } from "../i18n";
import { emptyProfile } from "../lib/profile";

export function UserPicker() {
  const { t } = useI18n();
  const { users, currentUserId, selectUser, refreshUsers, loading, error } =
    useUsers();
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

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

  return (
    <div className="user-picker">
      <label className="user-picker-label">{t("userPicker.activeUser")}</label>

      {error ? (
        <div className="user-picker-error" title={error}>
          {t("userPicker.unreachable")}
        </div>
      ) : (
        <select
          className="user-select"
          value={currentUserId ?? ""}
          disabled={loading}
          onChange={(e) => selectUser(e.target.value || null)}
        >
          <option value="">
            {loading ? t("userPicker.loading") : t("userPicker.select")}
          </option>
          {users.map((u) => (
            <option key={u.user_id} value={u.user_id}>
              {u.name || u.user_id}
            </option>
          ))}
        </select>
      )}

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
              className="btn btn-primary btn-sm"
              disabled={busy || !newName.trim()}
              onClick={() => void handleCreate()}
            >
              {busy ? "…" : t("common.create")}
            </button>
            <button
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
          className="btn btn-ghost btn-sm new-user-btn"
          disabled={!!error}
          onClick={() => setCreating(true)}
        >
          {t("userPicker.newUser")}
        </button>
      )}
    </div>
  );
}
