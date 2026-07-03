import os

# Keep in sync with [project] version in pyproject.toml (the api image ships
# src/ without pyproject, so the version lives here for /health to report).
APP_VERSION = "1.0.0"

FLASH_ACCEPT_THRESHOLD = 0.85
FLASH_ESCALATE_THRESHOLD = 0.5
MAX_CORRECTIONS = 2
FLASH_MODEL = "gemini-3.1-flash-lite"
PRO_MODEL = "gemini-3.1-pro-preview"

# LLM list prices (USD per 1M tokens) for the cost-per-scan estimate, from the
# Gemini API price list as of July 2026 (standard tier, ≤200K-token prompts).
# Keyed by the model ids above; a model missing here estimates as $0.
MODEL_PRICES_USD_PER_MTOK = {
    FLASH_MODEL: {"input": 0.25, "output": 1.50},
    PRO_MODEL: {"input": 2.00, "output": 12.00},
}

# --- Tier-1 image pre-flight (deterministic, no VLM) ------------------------
# A cheap pixel-level gate that runs BEFORE any Gemini call. It bounces back
# obviously unusable photos (near-black, blown-out, or near-uniform/blank) so we
# neither pay for a VLM call nor let the structured-output scanner hallucinate a
# product from an image that has none. Thresholds are deliberately permissive —
# they only fire on degenerate frames, not on merely dark or low-contrast labels.
MIN_MEAN_LUMINANCE = 18.0  # mean grey < this ⇒ near-black frame
MAX_MEAN_LUMINANCE = 240.0  # mean grey > this ⇒ blown-out / blank-white frame
MIN_LUMINANCE_STDDEV = 6.0  # contrast spread < this ⇒ near-uniform (no product)

# Qdrant vector retrieval (embedded/local mode) — replaces the rapidfuzz scans
# for both product registry lookup and ingredient normalization. The store is
# an on-disk path (no server); embeddings come from a local multilingual model,
# so the whole retrieval layer runs offline once the model is downloaded once.
QDRANT_PATH = "data/qdrant"
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"  # 384-dim, CPU-friendly, multilingual
EMBEDDING_DIM = 384
# The model is run on ONNX Runtime (via fastembed), not torch, so the API worker
# never loads torch. fastembed's built-in catalog ships e5-large but not
# e5-small, so we register e5-small as a custom model pointing at an ONNX
# export in its own HF repo. The int8 file cuts the loaded model's RSS by
# roughly 45% vs the fp32 export (measured ~815 MB -> ~450 MB) with no
# measurable change to the cosine scores the thresholds below are tuned
# against — needed to fit Railway's default 512 MB container. Its "avx512_vnni"
# name describes the quantization toolchain, not a runtime CPU requirement: the
# resulting ops are portable and run on any x86_64 CPU via onnxruntime's default
# CPU provider.
EMBEDDING_ONNX_FILE = "onnx/model_qint8_avx512_vnni.onnx"
# Where fastembed caches the downloaded ONNX weights. Pinned via env so the
# Docker image's build-time download is reused at runtime (no first-scan refetch);
# unset locally, where fastembed falls back to its default temp cache.
EMBEDDING_CACHE_DIR = os.getenv("FASTEMBED_CACHE_DIR") or None
PRODUCT_COLLECTION = "products"
INGREDIENT_COLLECTION = "ingredients"
# Cosine-similarity gates (0..1) for vector hits. Tune against the eval harness.
PRODUCT_MATCH_THRESHOLD = 0.86  # normal product retrieval
PRODUCT_EARLY_THRESHOLD = 0.93  # high-confidence early short-circuit
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

# Goal → function categories that address it, covering the richer free-text goal
# vocabulary the UI offers (ui/src/lib/profile.ts::GOAL_SUGGESTIONS) plus the five
# canonical keys above. Drives the routine dashboard's per-goal coverage check and
# the 5-leaf score (a goal is "covered" when the shelf contains ANY of its
# categories). Keys are lowercase; goals absent here are shown as "not assessed".
GOAL_COVERAGE = {
    # canonical keys (kept aligned with GOAL_TO_FUNCTION)
    "brightening": ["Vitamin C", "Niacinamide"],
    "anti_aging": ["Retinoids", "Peptides", "Vitamin C"],
    "hydration": ["Hydration", "Barrier"],
    "acne_control": ["BHA", "Niacinamide"],
    "barrier_repair": ["Barrier"],
    # wrinkles / firmness
    "fine lines": ["Retinoids", "Peptides", "Vitamin C"],
    "deep wrinkles": ["Retinoids", "Peptides"],
    "crow's feet": ["Retinoids", "Peptides"],
    "crepey/thin skin": ["Retinoids", "Peptides", "Hydration"],
    "sagging skin": ["Retinoids", "Peptides"],
    "hollowness/volume loss": ["Peptides"],
    # tone / pigment
    "hyperpigmentation": ["Vitamin C", "Niacinamide", "AHA"],
    "melasma": ["Vitamin C", "Niacinamide"],
    "dullness": ["Vitamin C", "AHA", "Niacinamide"],
    "uneven skin": ["Vitamin C", "AHA", "Niacinamide"],
    "acne scars": ["Vitamin C", "AHA", "Niacinamide"],
    # acne / pores / oil
    "acne": ["BHA", "Niacinamide"],
    "blackheads/whiteheads": ["BHA", "Retinoids"],
    "enlarged pores": ["BHA", "Niacinamide", "Retinoids"],
    "oiliness": ["BHA", "Niacinamide"],
    # barrier / dryness / redness
    "dryness/dehydration": ["Hydration", "Barrier"],
    "flakiness/peeling": ["Barrier", "Hydration"],
    "redness": ["Niacinamide", "Barrier"],
    "rosacea": ["Niacinamide", "Barrier"],
    # eye area (limited topical leverage)
    "blue circles": ["Vitamin C", "Niacinamide"],
    "under-eye bags": ["Peptides", "Niacinamide"],
}

# Routine dashboard pricing: when a priced product has no estimated months-of-supply
# from the lookup, assume this many months when amortizing its cost per month.
DEFAULT_MONTHS_SUPPLY = 3.0

# Web-search fallback: only fires when the registry misses AND the photo
# yielded fewer than this many ingredients (i.e. no usable list to audit).
MIN_INGREDIENTS_FOR_AUDIT = 5
# Minimum confidence in the re-verified brand+product name before we trust it
# enough to query the web for that specific product's ingredients.
IDENTITY_CONFIDENCE_THRESHOLD = 0.8
