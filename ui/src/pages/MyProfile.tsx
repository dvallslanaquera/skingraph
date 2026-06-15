// "My Profile" — view and edit the active user's skin data.
//
// Loads /users/{id} for the selected user, edits a local draft, and PUTs the
// whole UserUpsertRequest back on save (the API replaces the profile wholesale).
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { UserProfile } from "../api/types";
import { NoUser } from "../components/NoUser";
import { TagInput } from "../components/TagInput";
import { useUsers } from "../context/UserContext";
import {
  BUDGETS,
  CONDITION_SUGGESTIONS,
  GOAL_SUGGESTIONS,
  ROUTINE_TIMES,
  SKIN_TYPES,
  SUN_DAMAGE,
} from "../lib/profile";

export function MyProfile() {
  const { currentUserId, currentUser, refreshUsers } = useUsers();

  const [name, setName] = useState("");
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async (userId: string) => {
    setLoading(true);
    setError(null);
    try {
      const detail = await api.getUser(userId);
      setName(detail.name ?? "");
      setProfile(detail.profile);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (currentUserId) void load(currentUserId);
    else setProfile(null);
  }, [currentUserId, load]);

  if (!currentUserId) return <NoUser action="view and edit a profile" />;

  function set<K extends keyof UserProfile>(key: K, value: UserProfile[K]) {
    setProfile((p) => (p ? { ...p, [key]: value } : p));
    setSaved(false);
  }

  async function handleSave() {
    if (!currentUserId || !profile) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateUser(currentUserId, {
        name: name.trim() || null,
        profile,
      });
      await refreshUsers();
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!currentUserId) return;
    if (!confirm("Delete this user and their routine? This cannot be undone."))
      return;
    setDeleting(true);
    setError(null);
    try {
      await api.deleteUser(currentUserId);
      await refreshUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setDeleting(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>My Profile</h1>
          <p className="page-sub">
            This data personalises every scan's safety check and coaching.
          </p>
        </div>
        <code className="user-id-badge">{currentUserId}</code>
      </header>

      {error && <div className="banner banner-error">{error}</div>}

      {loading || !profile ? (
        <div className="card">Loading profile…</div>
      ) : (
        <>
          <section className="card">
            <h2 className="card-title">Identity</h2>
            <div className="form-grid">
              <Field label="Display name">
                <input
                  className="text-input"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setSaved(false);
                  }}
                  placeholder={currentUser?.name ?? "e.g. Hana"}
                />
              </Field>
              <Field label="Age">
                <input
                  className="text-input"
                  type="number"
                  min={0}
                  max={120}
                  value={profile.age ?? ""}
                  onChange={(e) =>
                    set("age", e.target.value ? Number(e.target.value) : null)
                  }
                  placeholder="—"
                />
              </Field>
              <Field label="Gender">
                <input
                  className="text-input"
                  value={profile.gender ?? ""}
                  onChange={(e) => set("gender", e.target.value || null)}
                  placeholder="—"
                />
              </Field>
              <Field label="Pregnant">
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={profile.is_pregnant}
                    onChange={(e) => set("is_pregnant", e.target.checked)}
                  />
                  <span>
                    Flag pregnancy-unsafe ingredients (e.g. retinoids)
                  </span>
                </label>
              </Field>
            </div>
          </section>

          <section className="card">
            <h2 className="card-title">Skin</h2>
            <div className="form-grid">
              <Field label="Skin type">
                <Select
                  value={profile.skin_type ?? ""}
                  options={SKIN_TYPES}
                  onChange={(v) =>
                    set("skin_type", (v || null) as UserProfile["skin_type"])
                  }
                />
              </Field>
              <Field label="Sun damage history">
                <Select
                  value={profile.sun_damage_history ?? ""}
                  options={SUN_DAMAGE}
                  onChange={(v) =>
                    set(
                      "sun_damage_history",
                      (v || null) as UserProfile["sun_damage_history"],
                    )
                  }
                />
              </Field>
            </div>

            <Field label="Goals">
              <TagInput
                values={profile.goals}
                onChange={(v) => set("goals", v)}
                suggestions={GOAL_SUGGESTIONS}
                placeholder="e.g. hydration"
              />
            </Field>

            <Field label="Skin conditions">
              <TagInput
                values={profile.skin_conditions}
                onChange={(v) => set("skin_conditions", v)}
                suggestions={CONDITION_SUGGESTIONS}
                placeholder="e.g. rosacea"
              />
            </Field>
          </section>

          <section className="card">
            <h2 className="card-title">Preferences</h2>
            <div className="form-grid">
              <Field label="Routine time">
                <Select
                  value={profile.routine_time ?? ""}
                  options={ROUTINE_TIMES}
                  onChange={(v) =>
                    set(
                      "routine_time",
                      (v || null) as UserProfile["routine_time"],
                    )
                  }
                />
              </Field>
              <Field label="Budget">
                <Select
                  value={profile.budget ?? ""}
                  options={BUDGETS}
                  onChange={(v) =>
                    set("budget", (v || null) as UserProfile["budget"])
                  }
                />
              </Field>
            </div>
          </section>

          <div className="page-actions">
            <button
              className="btn btn-danger"
              onClick={() => void handleDelete()}
              disabled={deleting || saving}
            >
              {deleting ? "Deleting…" : "Delete user"}
            </button>
            <div className="page-actions-right">
              {saved && <span className="saved-flag">✓ Saved</span>}
              <button
                className="btn btn-primary"
                onClick={() => void handleSave()}
                disabled={saving}
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

function Select({
  value,
  options,
  onChange,
}: {
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      className="select"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">—</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}
