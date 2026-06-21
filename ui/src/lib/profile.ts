import type {
  Gender,
  RoutineTime,
  SkinType,
  SunDamageHistory,
  UserProfile,
} from "../api/types";

export function emptyProfile(): UserProfile {
  return {
    skin_type: null,
    age: null,
    gender: null,
    fitzpatrick: null,
    skin_undertone: null,
    goals: [],
    is_pregnant: false,
    skin_conditions: [],
    sun_damage_history: null,
    routine_time: null,
    consider_devices: false,
    budget: null,
  };
}

// Turn a stored canonical value ("fine lines", "anti_aging") into an "Abc def"
// display label: underscores → spaces, first character capitalised. Slashes,
// apostrophes and hyphens are left intact ("blackheads/whiteheads", "crow's feet").
export function prettify(value: string): string {
  const text = value.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Option lists for the profile form selects. Kept in one place so the form and
// any future validation share the same source of truth as the backend Literals.
export const SKIN_TYPES: SkinType[] = [
  "dry",
  "oily",
  "combination",
  "normal",
  "sensitive",
];

export const SUN_DAMAGE: SunDamageHistory[] = [
  "none",
  "mild",
  "moderate",
  "severe",
];

export const GENDER_OPTIONS: { value: Gender; label: string }[] = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
  { value: "other", label: "Prefer not to say" },
];

// Fitzpatrick phototypes I–VI. The selected value stored on the profile is the
// 1-based index (1 = I … 6 = VI); these two palettes only change the swatch
// colour so a user can match their own undertone (Asian skins skew warmer/olive,
// other skins cooler/pink at the same phototype).
export const FITZPATRICK_LEVELS = ["I", "II", "III", "IV", "V", "VI"];

export const FITZPATRICK_ASIAN = [
  "#f7e0c8",
  "#f1cda3",
  "#e3b083",
  "#cc9362",
  "#a66e3e",
  "#6f4828",
];

export const FITZPATRICK_NON_ASIAN = [
  "#f9ddd3",
  "#f0c2aa",
  "#d99d7d",
  "#bb7a54",
  "#8c5736",
  "#5d3922",
];

// Routine-time presets shown as picture cards. Values match the backend Literal.
export const ROUTINE_OPTIONS: {
  value: RoutineTime;
  title: string;
  detail: string;
}[] = [
  {
    value: "minimal",
    title: "Minimal / lazy",
    detail: "Under 5 min/day, once daily — for busy people short on time.",
  },
  {
    value: "moderate",
    title: "Moderate",
    detail: "5–15 min/day, usually morning and night.",
  },
  {
    value: "extensive",
    title: "Extensive / serious",
    detail: "No time limits — happy with a full multi-step routine.",
  },
];

// Monthly budget slider, in USD. The top of the range is treated as "$250+".
export const BUDGET_MAX = 250;
export const BUDGET_STEP = 5;

export function formatBudget(usd: number): string {
  return usd >= BUDGET_MAX ? `$${BUDGET_MAX}+` : `$${usd}`;
}

// Suggested skin-concern goals; users can still type their own. Stored verbatim
// (lowercase) and shown via prettify().
export const GOAL_SUGGESTIONS = [
  "fine lines",
  "deep wrinkles",
  "sagging skin",
  "hollowness/volume loss",
  "crepey/thin skin",
  "hyperpigmentation",
  "melasma",
  "redness",
  "dullness",
  "uneven skin",
  "acne",
  "blackheads/whiteheads",
  "acne scars",
  "dryness/dehydration",
  "flakiness/peeling",
  "rosacea",
  "enlarged pores",
  "oiliness",
  "blue circles",
  "crow's feet",
  "under-eye bags",
];

export const CONDITION_SUGGESTIONS = [
  "eczema",
  "rosacea",
  "acne",
  "psoriasis",
  "hyperpigmentation",
];
