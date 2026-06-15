FLASH_ACCEPT_THRESHOLD = 0.85
FLASH_ESCALATE_THRESHOLD = 0.5
MAX_CORRECTIONS = 2
FLASH_MODEL = "gemini-3.1-flash-lite"
PRO_MODEL = "gemini-3.1-pro-preview"

# Qdrant vector retrieval (embedded/local mode) — replaces the rapidfuzz scans
# for both product registry lookup and ingredient normalization. The store is
# an on-disk path (no server); embeddings come from a local multilingual model,
# so the whole retrieval layer runs offline once the model is downloaded once.
QDRANT_PATH = "data/qdrant"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"  # 384-dim, CPU-friendly, multilingual
EMBEDDING_DIM = 384
PRODUCT_COLLECTION = "products"
INGREDIENT_COLLECTION = "ingredients"
# Cosine-similarity gates (0..1) for vector hits. Tune against the eval harness.
PRODUCT_MATCH_THRESHOLD = 0.86   # normal product retrieval
PRODUCT_EARLY_THRESHOLD = 0.93   # high-confidence early short-circuit
INGREDIENT_MATCH_THRESHOLD = 0.86  # normalizer's semantic tier (after exact lookup)

# Normalizer: seeds the ingredient vector index; tier-1 exact lookup still uses it.
INGREDIENT_MASTER_PATH = "data/ingredient_master.json"
# Where un-registered products are logged so they can be added to the registry later.
REGISTRY_CANDIDATES_PATH = "data/registry_candidates.json"

# Auditor: deterministic safety analysis over the normalized INCI names.
CONFLICT_MATRIX_PATH = "data/conflict_matrix.json"
IRRITANT_REGISTRY_PATH = "data/irritant_registry.json"
# safety_score starts at 1.0; each finding subtracts by severity, clamped to [0, 1].
CONFLICT_PENALTY = {"high": 0.30, "medium": 0.15, "low": 0.05}
IRRITANT_PENALTY = {"high": 0.15, "medium": 0.08, "low": 0.03}

# Coach: local SQLite store for returning users' skincare profiles + routines.
USER_DB_PATH = "data/users.db"

# Routine advisor: function/active taxonomy for redundancy + value-add analysis
# (safety conflicts reuse conflict_matrix.json instead). Maps a function category
# to its defining canonical INCI markers; see the file's _comment for the rules.
FUNCTION_GROUPS_PATH = "data/function_groups.json"
# Maps a user goal (UserProfile.goals) to the function categories that serve it.
# Drives value-add: a new product earns a value-add note when it introduces one
# of these categories for a stated goal that the existing routine does not cover.
GOAL_TO_FUNCTION = {
    "brightening": ["Vitamin C", "Niacinamide"],
    "anti_aging": ["Retinoids", "Peptides"],
    "hydration": ["Hydration"],
    "acne_control": ["BHA", "Niacinamide"],
    "barrier_repair": ["Barrier"],
}

# Web-search fallback: only fires when the registry misses AND the photo
# yielded fewer than this many ingredients (i.e. no usable list to audit).
MIN_INGREDIENTS_FOR_AUDIT = 5
# Minimum confidence in the re-verified brand+product name before we trust it
# enough to query the web for that specific product's ingredients.
IDENTITY_CONFIDENCE_THRESHOLD = 0.8
