#!/usr/bin/env python3
"""Terminal entry point for the Blast Radius benchmarks.

Two benchmarks share this entry point and stay fully separated:

* **Single-shot find-references** (default): ``blast_radius.runner`` — hand each model
  the whole repo dump, score a one-shot answer against a grep oracle. Results land in
  ``results/<mode>_<timestamp>.json`` + ``results/latest.json``.
* **Debug-loop** (``--debug-loop``): ``blast_radius.debug_loop`` — models get tools and
  iterate to fix a real bug (commit ``d11ae62``), scored by pytest. Results land in
  ``results/debug_loop_<timestamp>.json`` + ``results/debug_loop_latest.json`` and
  NEVER touch ``results/latest.json``.

Examples
--------
    # Offline smoke test of the single-shot benchmark (no API keys needed):
    python run_benchmark.py --demo

    # Real single-shot run, both models (needs ANTHROPIC_API_KEY and GLM_API_KEY):
    python run_benchmark.py

    # Debug-loop benchmark instead (separate results file):
    python run_benchmark.py --debug-loop
    python run_benchmark.py --debug-loop --models opus-4-8 --steps 15

Run with --help for all options of the selected benchmark.
"""

import sys
from pathlib import Path

# Make the sibling package importable whether run from notebooks/ or the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    if "--debug-loop" in sys.argv:
        # Dispatch to the debug-loop benchmark; drop the flag so its argparse is clean.
        from blast_radius.debug_loop import main as debug_main  # noqa: E402
        raise SystemExit(debug_main([a for a in sys.argv[1:] if a != "--debug-loop"]))

    from blast_radius.runner import main  # noqa: E402
    raise SystemExit(main())