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
export type Budget = "budget" | "mid-range" | "premium";

export interface UserProfile {
  skin_type?: SkinType | null;
  age?: number | null;
  gender?: string | null;
  goals: string[];
  is_pregnant: boolean;
  skin_conditions: string[];
  sun_damage_history?: SunDamageHistory | null;
  routine_time?: RoutineTime | null;
  budget?: Budget | null;
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

export interface RoutineProduct {
  product_id: string;
  brand: string;
  product_name: string;
  ingredients: string[];
  is_quasi_drug?: boolean | null;
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
  coach_advice?: string | null;
  routine_recommendations: string[];
  web_sources: string[];
  added_product_id?: string | null;
}
