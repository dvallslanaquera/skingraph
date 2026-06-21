"""Blast Radius benchmark: long-context code comprehension, GLM-5.2 vs Claude Opus 4.8.

The benchmark dumps an entire repository into a model's context and asks, for a set
of target symbols, "if you rename this, every file and line that must change". The
answer is scored against a deterministic oracle built by static analysis, so the
ground truth is independent of any model.

See ``notebooks/README.md`` for the full write-up.
"""

# Load the project's .env (if present) so ANTHROPIC_API_KEY / OLLAMA_API_KEY / GLM_*
# can live alongside the rest of the project's secrets, like the main app. Runs at
# package import — before config.py reads any env var. Real environment variables
# still win (load_dotenv does not override variables already set).
try:
    from pathlib import Path as _Path

    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_Path(__file__).resolve().parents[2] / ".env")
except Exception:  # python-dotenv absent or unreadable .env — fall back to env vars
    pass

__all__ = [
    "config",
    "repo_context",
    "oracle",
    "models",
    "scoring",
    "runner",
]
