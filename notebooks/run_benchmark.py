#!/usr/bin/env python3
"""Terminal entry point for the Blast Radius benchmark.

Examples
--------
    # Offline smoke test (no API keys needed) — synthesizes labeled fake answers:
    python run_benchmark.py --demo

    # Real run, both models (needs ANTHROPIC_API_KEY and GLM_API_KEY):
    python run_benchmark.py

    # Just one model, first 3 symbols:
    python run_benchmark.py --models opus-4-8 --limit 3

Run with --help for all options.
"""

import sys
from pathlib import Path

# Make the sibling package importable whether run from notebooks/ or the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from blast_radius.runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
