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
