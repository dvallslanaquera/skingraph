# LangSmith observability helpers.
#
# Tracing itself is turned on purely by environment variables — set
# LANGCHAIN_TRACING_V2=true (or LANGSMITH_TRACING=true) and LANGCHAIN_API_KEY,
# and LangGraph + the Gemini chat models auto-report every run to LangSmith. No
# code change is needed to *enable* tracing.
#
# This module only does two things on top of that:
#   1. log_tracing_status() — print, at startup, whether tracing is live and to
#      which project, so it's obvious from the logs that traces are flowing.
#   2. scan_run_config()    — name + tag + attach metadata to each graph run, so
#      the runs are filterable in the LangSmith UI instead of anonymous
#      "LangGraph" entries.
import logging
import os
from typing import Any

from langchain_core.runnables import RunnableConfig

# Stable name every scan trace shares, so they group together in the UI.
SCAN_RUN_NAME = "skincare-scan"


def tracing_enabled() -> bool:
    """True when LangSmith tracing is configured (flag on + an API key present).

    Accepts both the legacy LANGCHAIN_* and the newer LANGSMITH_* variable names;
    the langsmith SDK reads either.
    """
    flag = (
        os.getenv("LANGCHAIN_TRACING_V2") or os.getenv("LANGSMITH_TRACING") or ""
    ).strip().lower() in ("true", "1", "yes")
    has_key = bool(os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY"))
    return flag and has_key


def log_tracing_status() -> None:
    """Log whether LangSmith tracing is active so it's visible at startup."""
    if tracing_enabled():
        project = os.getenv("LANGCHAIN_PROJECT") or os.getenv("LANGSMITH_PROJECT") or "default"
        logging.info("LangSmith tracing ENABLED → project '%s'.", project)
    else:
        logging.info(
            "LangSmith tracing disabled "
            "(set LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY to enable)."
        )


def scan_run_config(
    *,
    entrypoint: str,
    image_type: str | None = None,
    user_id: str | None = None,
    has_routine: bool = False,
    callbacks: list[Any] | None = None,
) -> RunnableConfig:
    """Build the LangGraph invoke config that names, tags, and annotates a scan.

    Passing the result as the second argument to ``app.invoke(state, config)``
    makes the trace identifiable in LangSmith (filter by entrypoint, label side,
    or whether the run was personalised). It does not enable or disable tracing.

    ``callbacks`` (e.g. the usage/cost aggregator in src/metrics.py) propagate
    to every LLM call inside the run.
    """
    tags: list[str] = [f"entry:{entrypoint}"]
    if image_type:
        tags.append(f"side:{image_type}")
    tags.append("personalised" if user_id else "anonymous")
    if has_routine:
        tags.append("with-routine")

    metadata: dict[str, Any] = {
        "entrypoint": entrypoint,
        "image_type": image_type or "auto",
        "personalised": bool(user_id),
        "has_routine": has_routine,
    }
    config: RunnableConfig = {"run_name": SCAN_RUN_NAME, "tags": tags, "metadata": metadata}
    if callbacks:
        config["callbacks"] = callbacks
    return config
