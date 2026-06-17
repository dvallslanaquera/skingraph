// "My Profile" — view and edit the active user's skin data.
//
// Loads /users/{id} for the selected user, edits a local draft, and PUTs the
// whole UserUpsertRequest back on save (the API replaces the profile wholesale).
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { Gender, SkinUndertone, UserProfile } from "../api/types";
import { NoUser } from "../components/NoUser";
import { TagInput } from "../components/TagInput";
import { useUsers } from "../context/UserContext";
import { useI18n } from "../i18n";
import { formatBudget } from "../i18n/strings";
import {
  BUDGET_MAX,
  BUDGET_STEP,
  CONDITION_SUGGESTIONS,
  FITZPATRICK_ASIAN,
  FITZPATRICK_LEVELS,
  FITZPATRICK_NON_ASIAN,
  GENDER_OPTIONS,
  GOAL_SUGGESTIONS,
  ROUTINE_OPTIONS,
  SKIN_TYPES,
  SUN_DAMAGE,
} from "../lib/profile";

export function MyProfile() {
  const { t, term, lang } = useI18n();
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

  if (!currentUserId) return <NoUser action={t("noUser.action.profile")} />;

  function set<K extends keyof UserProfile>(key: K, value: UserProfile[K]) {
    setProfile((p) => (p ? { ...p, [key]: value } : p));
    setSaved(false);
  }

  function setGender(value: Gender) {
    // Pregnancy only applies to female users — clear the flag otherwise so a
    // hidden control can't leave a stale "pregnant" value on the profile.
    setProfile((p) =>
      p
        ? {
            ...p,
            gender: value,
            is_pregnant: value === "female" ? p.is_pregnant : false,
          }
        : p,
    );
    setSaved(false);
  }

  function setFitzpatrick(level: number, undertone: SkinUndertone) {
    setProfile((p) =>
      p
        ? {
            ...p,
            // Click the already-selected swatch to clear it.
            fitzpatrick:
              p.fitzpatrick === level && p.skin_undertone === undertone
                ? null
                : level,
            skin_undertone:
              p.fitzpatrick === level && p.skin_undertone === undertone
                ? null
                : undertone,
          }
        : p,
    );
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
    if (!confirm(t("profile.deleteConfirm"))) return;
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
          <h1>{t("profile.title")}</h1>
          <p className="page-sub">{t("profile.sub")}</p>
        </div>
        <code className="user-id-badge">{currentUserId}</code>
      </header>

      {error && <div className="banner banner-error">{error}</div>}

      {loading || !profile ? (
        <div className="card">{t("profile.loading")}</div>
      ) : (
        <>
          <section className="card">
            <h2 className="card-title">{t("profile.section.identity")}</h2>
            <div className="form-grid">
              <Field label={t("profile.displayName")}>
                <input
                  className="text-input"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setSaved(false);
                  }}
                  placeholder={currentUser?.name ?? t("profile.displayName.placeholder")}
                />
              </Field>
              <Field label={t("profile.age")}>
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
            </div>

            <FieldBlock label={t("profile.gender")}>
              <div className="segmented" role="group" aria-label={t("profile.gender")}>
                {GENDER_OPTIONS.map((g) => (
                  <button
                    key={g.value}
                    type="button"
                    className={`segmented-option${
                      profile.gender === g.value ? " active" : ""
                    }`}
                    aria-pressed={profile.gender === g.value}
                    onClick={() => setGender(g.value)}
                  >
                    {t(`gender.${g.value}`)}
                  </button>
                ))}
              </div>
            </FieldBlock>

            {profile.gender === "female" && (
              <label className="pregnancy-row">
                <input
                  type="checkbox"
                  checked={profile.is_pregnant}
                  onChange={(e) => set("is_pregnant", e.target.checked)}
                />
                <span>{t("profile.pregnancy")}</span>
              </label>
            )}
          </section>

          <section className="card">
            <h2 className="card-title">{t("profile.section.skin")}</h2>

            <FieldBlock label={t("profile.fitz")}>
              <p className="field-help">{t("profile.fitz.help")}</p>
              <div className="fitz-scale">
                <FitzRow
                  label={t("profile.fitz.asian")}
                  undertone="asian"
                  colors={FITZPATRICK_ASIAN}
                  selectedLevel={profile.fitzpatrick ?? null}
                  selectedUndertone={profile.skin_undertone ?? null}
                  onPick={setFitzpatrick}
                />
                <FitzRow
                  label={t("profile.fitz.other")}
                  undertone="non_asian"
                  colors={FITZPATRICK_NON_ASIAN}
                  selectedLevel={profile.fitzpatrick ?? null}
                  selectedUndertone={profile.skin_undertone ?? null}
                  onPick={setFitzpatrick}
                />
                <div className="fitz-row fitz-levels" aria-hidden="true">
                  <span className="fitz-row-label" />
                  {FITZPATRICK_LEVELS.map((roman) => (
                    <span key={roman} className="fitz-level">
                      {roman}
                    </span>
                  ))}
                </div>
              </div>
            </FieldBlock>

            <div className="form-grid">
              <Field label={t("profile.skinType")}>
                <Select
                  value={profile.skin_type ?? ""}
                  options={SKIN_TYPES}
                  format={term}
                  onChange={(v) =>
                    set("skin_type", (v || null) as UserProfile["skin_type"])
                  }
                />
              </Field>
              <Field label={t("profile.sunDamage")}>
                <Select
                  value={profile.sun_damage_history ?? ""}
                  options={SUN_DAMAGE}
                  format={term}
                  onChange={(v) =>
                    set(
                      "sun_damage_history",
                      (v || null) as UserProfile["sun_damage_history"],
                    )
                  }
                />
              </Field>
            </div>

            <Field label={t("profile.goals")}>
              <TagInput
                values={profile.goals}
                onChange={(v) => set("goals", v)}
                suggestions={GOAL_SUGGESTIONS}
                formatLabel={term}
                placeholder={t("profile.goals.placeholder")}
              />
            </Field>

            <Field label={t("profile.conditions")}>
              <TagInput
                values={profile.skin_conditions}
                onChange={(v) => set("skin_conditions", v)}
                suggestions={CONDITION_SUGGESTIONS}
                formatLabel={term}
                placeholder={t("profile.conditions.placeholder")}
              />
            </Field>
          </section>

          <section className="card">
            <h2 className="card-title">{t("profile.section.prefs")}</h2>

            <FieldBlock label={t("profile.routineTime")}>
              <div
                className="routine-options"
                role="group"
                aria-label={t("profile.routineTime")}
              >
                {ROUTINE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className={`routine-option${
                      profile.routine_time === opt.value ? " selected" : ""
                    }`}
                    aria-pressed={profile.routine_time === opt.value}
                    onClick={() =>
                      set(
                        "routine_time",
                        profile.routine_time === opt.value ? null : opt.value,
                      )
                    }
                  >
                    <RoutineCat kind={opt.value} />
                    <span className="routine-option-title">
                      {t(`routineTime.${opt.value}.title`)}
                    </span>
                    <span className="routine-option-detail">
                      {t(`routineTime.${opt.value}.detail`)}
                    </span>
                  </button>
                ))}
              </div>
            </FieldBlock>

            <label className="checkbox-row devices-row">
              <input
                type="checkbox"
                checked={profile.consider_devices}
                onChange={(e) => set("consider_devices", e.target.checked)}
              />
              <span>{t("profile.devices")}</span>
            </label>

            <FieldBlock label={t("profile.budget")}>
              <p className="field-help">{t("profile.budget.help")}</p>
              <div className="budget-slider">
                <input
                  type="range"
                  min={0}
                  max={BUDGET_MAX}
                  step={BUDGET_STEP}
                  aria-label={t("profile.budget")}
                  value={profile.budget ?? 0}
                  onChange={(e) => set("budget", Number(e.target.value))}
                />
                <span className="budget-value">
                  {profile.budget == null
                    ? t("profile.budget.notSet")
                    : `${formatBudget(lang, profile.budget, BUDGET_MAX)}${t("common.perMonthShort")}`}
                </span>
              </div>
              <div className="budget-scale" aria-hidden="true">
                <span>{formatBudget(lang, 0, BUDGET_MAX)}</span>
                <span>{formatBudget(lang, BUDGET_MAX, BUDGET_MAX)}</span>
              </div>
            </FieldBlock>
          </section>

          <div className="page-actions">
            <button
              className="btn btn-danger"
              onClick={() => void handleDelete()}
              disabled={deleting || saving}
            >
              {deleting ? t("profile.deleting") : t("profile.delete")}
            </button>
            <div className="page-actions-right">
              {saved && <span className="saved-flag">{t("profile.saved")}</span>}
              <button
                className="btn btn-primary"
                onClick={() => void handleSave()}
                disabled={saving}
              >
                {saving ? t("common.saving") : t("profile.save")}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function FitzRow({
  label,
  undertone,
  colors,
  selectedLevel,
  selectedUndertone,
  onPick,
}: {
  label: string;
  undertone: SkinUndertone;
  colors: string[];
  selectedLevel: number | null;
  selectedUndertone: SkinUndertone | null;
  onPick: (level: number, undertone: SkinUndertone) => void;
}) {
  return (
    <div className="fitz-row">
      <span className="fitz-row-label">{label}</span>
      {colors.map((color, i) => {
        const level = i + 1;
        const selected =
          selectedLevel === level && selectedUndertone === undertone;
        return (
          <button
            key={level}
            type="button"
            className={`fitz-swatch${selected ? " selected" : ""}`}
            style={{ backgroundColor: color }}
            aria-label={`Fitzpatrick type ${FITZPATRICK_LEVELS[i]}, ${label}`}
            aria-pressed={selected}
            onClick={() => onPick(level, undertone)}
          />
        );
      })}
    </div>
  );
}

// Minimalist line-art cats for the three routine-time presets: a sleeping curl
// (lazy), a sitting cat (moderate), and an alert standing cat (serious).
function RoutineCat({ kind }: { kind: "minimal" | "moderate" | "extensive" }) {
  const common = {
    className: "routine-cat",
    viewBox: "0 0 72 52",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (kind === "minimal") {
    return (
      <svg {...common}>
        <path d="M12 40c2-12 16-18 30-13 11 4 17 13 6 18-12 5-34 4-36 1-1-2-1-4 0-6z" />
        <path d="M16 35l-2-7 7 3" />
        <path d="M30 30c2 2 6 2 8 0" />
        <path d="M24 38c2 1 4 1 6 0" />
        <path d="M48 24q3-3 6-1" />
        <path d="M50 12l6 0-6 6 6 0" />
      </svg>
    );
  }
  if (kind === "moderate") {
    return (
      <svg {...common}>
        <path d="M26 46c-7 0-11-9-11-18 0-9 5-16 13-16s13 7 13 16c0 9-4 18-11 18z" />
        <path d="M18 16l-2-9 8 5" />
        <path d="M36 16l2-9-8 5" />
        <circle cx="24" cy="22" r="1.4" fill="currentColor" stroke="none" />
        <circle cx="32" cy="22" r="1.4" fill="currentColor" stroke="none" />
        <path d="M26 26c1 1.5 3 1.5 4 0" />
        <path d="M39 44c10 0 13-7 12-16" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M16 46V28c0-9 5-15 12-15s12 6 12 15v18" />
      <path d="M16 46h24" />
      <path d="M20 14l-2-9 8 5" />
      <path d="M36 14l2-9-8 5" />
      <circle cx="24" cy="22" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="32" cy="22" r="1.4" fill="currentColor" stroke="none" />
      <path d="M26 26c1 1.5 3 1.5 4 0" />
      <path d="M40 44c8-2 14-12 12-26" />
    </svg>
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

// Like Field, but a <div> rather than a <label> — for grouped controls (button
// groups, sliders with help text) that shouldn't live inside a <label>.
function FieldBlock({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      {children}
    </div>
  );
}

function Select({
  value,
  options,
  onChange,
  format = (v) => v,
}: {
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
  format?: (value: string) => string;
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
          {format(o)}
        </option>
      ))}
    </select>
  );
}
