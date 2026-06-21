"""Static configuration for the Blast Radius benchmark.

Everything that a reader might want to tweak — which symbols to probe, which files
make up the context, which models to call, and how to price them — lives here so the
rest of the package stays mechanical.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- Paths ------------------------------------------------------------------
# The repo root is the parent of notebooks/. Resolved from this file's location so
# the benchmark runs the same whether invoked from the repo root or from notebooks/.
REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"

# File extensions that count as "source" for both the context dump and the oracle.
# Kept to the languages a rename would actually touch; data/JSON/images are excluded
# so the oracle isn't polluted by, e.g., a symbol name appearing in a fixture.
SOURCE_GLOBS = ("*.py", "*.ts", "*.tsx")

# Path prefixes excluded from the dump AND the oracle. The benchmark must never
# measure its own source: notebooks/blast_radius/config.py literally lists the
# target symbols as strings, which would contaminate the ground truth once the
# notebooks/ folder is git-tracked.
EXCLUDE_PREFIXES = ("notebooks/",)

# --- Target symbols ---------------------------------------------------------
# Chosen for a deliberate spread of blast-radius sizes (measured on this repo):
# from a 2-file/3-line config dict up to a 13-file/48-line core type. Distinctive
# names (no collisions with common words) keep the word-boundary oracle precise.
TARGET_SYMBOLS: tuple[str, ...] = (
    "UserProfile",                 # ~13 files — core Pydantic model, wide blast radius
    "AgentState",                  # ~11 files — LangGraph state TypedDict
    "RoutineProduct",              # ~8 files
    "ProductExtraction",           # ~8 files
    "SafetyAudit",                 # ~7 files
    "inci_names",                  # ~5 files — helper function
    "MIN_INGREDIENTS_FOR_AUDIT",   # ~5 files — config constant
    "build_initial_state",         # ~4 files — entry-point factory
    "PRODUCT_MATCH_THRESHOLD",     # ~3 files — tuning constant
    "IDENTITY_CONFIDENCE_THRESHOLD",  # ~3 files — smallest, hardest to find them all
)


# --- Model configuration ----------------------------------------------------
@dataclass(frozen=True)
class ModelConfig:
    """Everything needed to call one model and price its usage."""

    key: str                       # short id used in result files / plots
    label: str                     # human label for plots
    provider: str                  # "anthropic" | "openai_compatible"
    model_id: str                  # the API model string
    input_price_per_mtok: float    # USD per 1M input tokens
    output_price_per_mtok: float   # USD per 1M output tokens
    # OpenAI-compatible only:
    base_url: str | None = None
    api_key_env: tuple[str, ...] = field(default_factory=tuple)  # env vars to try, in order


# Opus 4.8: model id + pricing are authoritative as of 2026-06 (claude-api skill).
OPUS = ModelConfig(
    key="opus-4-8",
    label="Claude Opus 4.8",
    provider="anthropic",
    model_id="claude-opus-4-8",
    input_price_per_mtok=5.0,
    output_price_per_mtok=25.0,
    api_key_env=("ANTHROPIC_API_KEY",),
)

# GLM-5.2 can be reached two ways; choose with GLM_PROVIDER:
#   "ollama"            -> Ollama Cloud via the `ollama` package (model "glm-5.2:cloud") [default]
#   "openai_compatible" -> Zhipu / z.ai OpenAI-compatible endpoint
# Pricing is GLM-5.2 Cloud API list pricing (USD per 1M tokens): $1.40 input,
# $4.40 output. Override with GLM_INPUT_PRICE / GLM_OUTPUT_PRICE if you have a
# discounted rate. Ollama Cloud bills by subscription/usage, so its per-token
# cost is only indicative if used through that provider.
GLM_PROVIDER = os.getenv("GLM_PROVIDER", "ollama")
_GLM_PRICE = dict(
    input_price_per_mtok=float(os.getenv("GLM_INPUT_PRICE", "1.40")),
    output_price_per_mtok=float(os.getenv("GLM_OUTPUT_PRICE", "4.40")),
)

if GLM_PROVIDER == "ollama":
    GLM = ModelConfig(
        key="glm-5-2",
        label="GLM-5.2",
        provider="ollama",
        model_id=os.getenv("GLM_MODEL", "glm-5.2:cloud"),
        base_url=os.getenv("OLLAMA_HOST") or None,  # None -> ollama package default
        api_key_env=("OLLAMA_API_KEY",),
        **_GLM_PRICE,
    )
else:
    GLM = ModelConfig(
        key="glm-5-2",
        label="GLM-5.2",
        provider="openai_compatible",
        model_id=os.getenv("GLM_MODEL", "glm-5.2"),
        base_url=os.getenv("GLM_BASE_URL", "https://api.z.ai/api/paas/v4"),
        api_key_env=("GLM_API_KEY", "ZHIPUAI_API_KEY"),
        **_GLM_PRICE,
    )

MODELS: dict[str, ModelConfig] = {OPUS.key: OPUS, GLM.key: GLM}

# Ollama defaults to a tiny context window (~4096 tokens) and SILENTLY TRUNCATES
# longer input — which would gut a ~129k-token long-context benchmark. Force it wide.
# (For ":cloud" models the cloud manages context server-side; passing this is a
# harmless belt-and-suspenders.) Override with OLLAMA_NUM_CTX.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "131072"))

# Output cap for the answer. The reply is a JSON list of references — even a wide
# blast radius is well under this. Small cap keeps non-streaming calls fast & cheap.
MAX_OUTPUT_TOKENS = 8000

# Rough chars-per-token used only for a friendly pre-flight size estimate when no
# tokenizer is available. The real input_tokens come back in each model's usage.
CHARS_PER_TOKEN_ESTIMATE = 3.7
