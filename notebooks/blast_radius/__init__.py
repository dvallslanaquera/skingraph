"""Blast Radius benchmark: long-context code comprehension, GLM-5.2 vs Claude Opus 4.8.

The benchmark dumps an entire repository into a model's context and asks, for a set
of target symbols, "if you rename this, every file and line that must change". The
answer is scored against a deterministic oracle built by static analysis, so the
ground truth is independent of any model.

See ``notebooks/README.md`` for the full write-up.
"""

__all__ = [
    "config",
    "repo_context",
    "oracle",
    "models",
    "scoring",
    "runner",
]
