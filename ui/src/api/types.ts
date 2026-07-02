// TypeScript mirrors of the Pydantic models in src/state.py and
// src/api/schemas.py. Keep these in sync with the backend contracts.

// --- users ------------------------------------------------------------------

export type SkinType =
  | "dry"
  | "oily"
  | "combination"
  | "normal"
  | "sensitive";

export type SunDamageHistory = "none" | "mild" | "moderate" | "severe";
export type RoutineTime = "minimal" | "moderate" | "extensive";
export type Gender = "male" | "female" | "other";
export type SkinUndertone = "asian" | "non_asian";

export interface UserProfile {
  skin_type?: SkinType | null;
  age?: number | null;
  gender?: string | null;
  // Fitzpatrick phototype as 1 (I) – 6 (VI), plus the undertone palette it was
  // picked from (Asian vs non-Asian skins differ at the same phototype).
  fitzpatrick?: number | null;
  skin_undertone?: SkinUndertone | null;
  goals: string[];
  is_pregnant: boolean;
  skin_conditions: string[];
  sun_damage_history?: SunDamageHistory | null;
  routine_time?: RoutineTime | null;
  // Whether the coach may also suggest devices / at-home treatments.
  consider_devices: boolean;
  // Monthly skincare budget in USD (0–250, where 250 is treated as "$250+").
  budget?: number | null;
}

export interface UserSummary {
  user_id: string;
  name?: string | null;
}

export interface UserDetail {
  user_id: string;
  name?: string | null;
  profile: UserProfile;
}

export interface UserUpsertRequest {
  name?: string | null;
  profile: UserProfile;
}

export interface UserCreateResponse {
  user_id: string;
}

// --- routine ("shelf") ------------------------------------------------------

export type Timing = "AM" | "PM" | "AM & PM";

export interface RoutineProduct {
  product_id: string;
  brand: string;
  product_name: string;
  ingredients: string[];
  is_quasi_drug?: boolean | null;
  timing?: Timing | string | null;
  application_notes?: string[];
  price_usd?: number | null;
  price_native?: number | null;
  price_currency?: string | null;
  price_market?: string | null;
  months_supply?: number | null;
  price_source?: string | null;
}

export interface RoutineProductRequest {
  brand: string;
  product_name: string;
  ingredients: string[];
  is_quasi_drug?: boolean | null;
}

export interface RoutineProductResponse {
  product_id: string;
}

// --- routine dashboard ------------------------------------------------------

export interface RoutineDashboardCard {
  product_id: string;
  brand: string;
  product_name: string;
  ingredients: string[];
  is_quasi_drug?: boolean | null;
  timing: Timing | string;
  application_notes: string[];
  price_usd?: number | null;
  price_native?: number | null;
  price_currency?: string | null;
  price_market?: string | null;
  months_supply?: number | null;
  price_source?: string | null;
  monthly_cost_usd?: number | null;
  monthly_cost_native?: number | null;
}

export interface GoalCoverage {
  goal: string;
  covered: boolean | null;
  addressed_by: string[];
}

export interface RoutineDashboard {
  products: RoutineDashboardCard[];
  monthly_cost_usd?: number | null;
  monthly_cost_jpy?: number | null;
  currency: string;
  goals: GoalCoverage[];
  leaf_score: number;
}

// --- scan -------------------------------------------------------------------

export type ScanStatus =
  | "complete"
  | "retake_required"
  | "action_needed"
  | "incomplete";

export interface Ingredient {
  name_raw: string;
  name_standardized?: string | null;
  is_active?: boolean | null;
  source_language: string;
}

export interface NormalizedIngredient {
  name_raw: string;
  name_standardized?: string | null;
  is_active?: boolean | null;
  source_language?: string | null;
}

export interface ProductExtraction {
  brand: string;
  product_name: string;
  jan_code?: string | null;
  ingredients: Ingredient[];
  is_quasi_drug?: boolean | null;
  source_language: string;
  extraction_confidence: number;
  system_status: "SUCCESS" | "INCOMPLETE" | "RETAKE_REQUIRED";
}

export interface SafetyAudit {
  ingredient_conflicts: string[];
  risk_ingredients: string[];
  warnings: string[];
  safety_score: number;
}

export interface CrossConflict {
  with_product: string;
  severity: string;
  groups: [string, string];
  reason: string;
}

export interface RoutineFit {
  conflicts: CrossConflict[];
  redundancy: string[];
  value_add: string[];
  existing_products: string[];
}

// One complete coach recommendation card, written in a single language.
export interface CoachRecommendation {
  verdict: string;
  product: string;
  purpose: string;
  warnings: string[];
  timing: string; // "AM" | "PM" | "AM & PM"
  frequency: string;
  application_notes: string[];
  recommendation_rationale: string;
  routine_integration: string;
}

// LLM-phrased routine-fit notes (empty lists when no routine context).
export interface CoachRoutineFit {
  risks: string[];
  redundancy: string[];
  value_add: string[];
}

// The coach's structured bilingual output — mirrors CoachResponse in
// src/state.py. recommendation_score is null for anonymous scans.
export interface CoachCards {
  recommendation_score?: number | null;
  japanese: CoachRecommendation;
  english: CoachRecommendation;
  routine_japanese: CoachRoutineFit;
  routine_english: CoachRoutineFit;
}

export interface ScanResponse {
  status: ScanStatus;
  trace_id?: string | null;
  model_used?: string | null;
  inference_confidence?: number | null;
  registry_matched?: boolean | null;
  ingredient_source?: string | null;
  detected_language?: string | null;
  product?: ProductExtraction | null;
  standardized_ingredients: NormalizedIngredient[];
  unmatched_ingredients: string[];
  safety_report?: SafetyAudit | null;
  routine_fit?: RoutineFit | null;
  // The coach's structured bilingual card; null on graceful exits.
  coach?: CoachCards | null;
  // Plain-text graceful-exit message (retake / identity / search).
  coach_advice?: string | null;
  web_sources: string[];
  added_product_id?: string | null;
}
