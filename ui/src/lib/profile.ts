import type {
  Budget,
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
    goals: [],
    is_pregnant: false,
    skin_conditions: [],
    sun_damage_history: null,
    routine_time: null,
    budget: null,
  };
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

export const ROUTINE_TIMES: RoutineTime[] = [
  "minimal",
  "moderate",
  "extensive",
];

export const BUDGETS: Budget[] = ["budget", "mid-range", "premium"];

// Suggested chips; users can type their own too.
export const GOAL_SUGGESTIONS = [
  "anti_aging",
  "brightening",
  "hydration",
  "acne_control",
  "barrier_repair",
];

export const CONDITION_SUGGESTIONS = [
  "eczema",
  "rosacea",
  "acne",
  "psoriasis",
  "hyperpigmentation",
];
