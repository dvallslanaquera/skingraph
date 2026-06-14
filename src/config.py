FLASH_ACCEPT_THRESHOLD = 0.85
FLASH_ESCALATE_THRESHOLD = 0.5
MAX_CORRECTIONS = 2
REGISTRY_MATCH_THRESHOLD = 90
REGISTRY_EARLY_THRESHOLD = 99
FLASH_MODEL = "gemini-3.1-flash-lite"
PRO_MODEL = "gemini-3.1-pro-preview"

# Label languages the downstream registry/normalizer/auditor support.
# Anything outside this set is routed to a clean "unsupported language" exit
# instead of silently failing the registry lookup.
SUPPORTED_LANGUAGES = {"JP"}

# Normalizer: maps raw ingredient names to canonical INCI keys.
INGREDIENT_MASTER_PATH = "data/ingredient_master.json"
NORMALIZER_FUZZY_THRESHOLD = 90  # rapidfuzz score below which a name stays unmapped
# Where un-registered products are logged so they can be added to the registry later.
REGISTRY_CANDIDATES_PATH = "data/registry_candidates.json"

# Auditor: deterministic safety analysis over the normalized INCI names.
CONFLICT_MATRIX_PATH = "data/conflict_matrix.json"
IRRITANT_REGISTRY_PATH = "data/irritant_registry.json"
# safety_score starts at 1.0; each finding subtracts by severity, clamped to [0, 1].
CONFLICT_PENALTY = {"high": 0.30, "medium": 0.15, "low": 0.05}
IRRITANT_PENALTY = {"high": 0.15, "medium": 0.08, "low": 0.03}
