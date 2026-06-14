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
