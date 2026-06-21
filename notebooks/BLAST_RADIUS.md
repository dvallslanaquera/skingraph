# Blast Radius — GLM-5.2 vs Claude Opus 4.8

A small, reproducible benchmark for **long-context code comprehension**. It tests the
claim behind the article: that a long-context model like **GLM-5.2** can rival
**Claude Opus 4.8** at reading many files at once and reasoning across them.

The task is deliberately one where the ground truth is **deterministic** — produced by
static analysis, not by a model — so the scores are auditable and never drift.

> (Note: `notebooks/README.md` is a separate, pre-existing SkinGraph interview Q&A —
> this benchmark write-up lives here in `BLAST_RADIUS.md` to avoid clobbering it.)

## The idea

Dump this entire repository into a model's context and ask, for each of ten target
symbols:

> *"If you rename `X` everywhere, list every file and line that must change."*

That's the **blast radius** of a refactor. A real find-references pass
(`rg -nw <symbol>`) gives the exact answer, so we can score each model's reply against
it. We measure **recall** (did it find every reference?) and **precision** (did it
invent any?), at two granularities:

- **File level** — the right *set of files*. The question a refactoring engineer
  actually asks ("what do I need to open?"). This is the headline metric.
- **Line level** — the exact `(file, line)`. Stricter. The context dump prefixes every
  line with its number, so this tests precise long-context *retrieval*, not the
  model's ability to count newlines.

## Why this repo is a good fit

| | |
|---|---|
| Source size | 61 files (`.py`/`.ts`/`.tsx`), ~7.4k LOC |
| Context dump | ~477k chars ≈ **~129k tokens** (fits Opus 4.8's 1M and GLM-5.2's long context with room to spare) |
| Symbol spread | 3-line config constant → 48-line core type (`UserProfile`) — easy *and* hard retrieval in one run |

The codebase is a clean LangGraph-style agent with distinctive, widely-referenced
symbols (`AgentState`, `UserProfile`, `PRODUCT_MATCH_THRESHOLD`, …), so the
word-boundary oracle is high-precision.

## Layout

```
notebooks/
├── run_benchmark.py        # terminal entry point
├── analysis.ipynb          # graphs comparing the two models
├── requirements.txt
├── results/                # JSON written here; results/latest.json is what the notebook reads
└── blast_radius/
    ├── config.py           # target symbols, model configs, pricing  ← tweak here
    ├── repo_context.py     # builds the line-numbered repo dump
    ├── oracle.py           # deterministic ground truth (pure stdlib)
    ├── models.py           # Opus 4.8 (Anthropic SDK) + GLM-5.2 (OpenAI-compatible)
    ├── scoring.py          # precision / recall / F1, file + line level
    └── runner.py           # orchestration + JSON output
```

The oracle, context builder, and scoring are **pure standard library** — no external
binary, no model, runs identically on Windows/macOS/Linux.

## Quick start

```bash
cd notebooks
pip install -r requirements.txt

# 1) Offline smoke test — no API keys. Synthesizes clearly-labeled fake answers
#    so you can see the whole pipeline + notebook work end-to-end.
python run_benchmark.py --demo

# 2) Inspect the deterministic oracle on its own:
python -m blast_radius.oracle
```

### Real run

Set the keys, then run. Each model that has a key is benchmarked; the other is skipped.

```bash
# Claude Opus 4.8
export ANTHROPIC_API_KEY=sk-ant-...

# GLM-5.2 — default path is Ollama Cloud (glm-5.2:cloud), via the `ollama` package.
export OLLAMA_API_KEY=...          # OR run `ollama signin` and omit this
# optional overrides (defaults shown):
export GLM_MODEL=glm-5.2:cloud
export OLLAMA_NUM_CTX=131072       # keep large — Ollama truncates long input otherwise

python run_benchmark.py                      # both models, all 10 symbols
python run_benchmark.py --models opus-4-8    # one model only
python run_benchmark.py --limit 3            # first 3 symbols (quick/cheap)
```

On Windows PowerShell use `$env:ANTHROPIC_API_KEY = "..."` instead of `export`.

**To use z.ai / Zhipu instead of Ollama** for GLM, set `GLM_PROVIDER=openai_compatible`
and provide `GLM_API_KEY` (+ optional `GLM_BASE_URL`, `GLM_MODEL`).

Every run writes `results/<mode>_<timestamp>.json` **and** refreshes
`results/latest.json`. Then open the notebook:

```bash
jupyter notebook analysis.ipynb
```

## Pricing (for the cost chart)

- **Opus 4.8** input/output pricing is built in ($5 / $25 per 1M tokens) and it
  **prompt-caches** the shared repo dump, so the 10 per-symbol calls reuse one cached
  prefix (cache reads bill ~0.1×).
- **GLM-5.2** pricing is a **placeholder** (defaults to GLM-4.6-class public rates).
  Ollama Cloud bills by subscription/usage, so per-token cost is only indicative —
  treat the GLM cost bar as a rough guide. Set your real rate to override:
  ```bash
  export GLM_INPUT_PRICE=0.60     # USD per 1M input tokens
  export GLM_OUTPUT_PRICE=2.20    # USD per 1M output tokens
  ```

## Methodology & fairness notes

- **One question per symbol, full repo in context each time.** Independent calls, no
  cross-contamination — this is the long-context test, not a multi-turn chat.
- **Identical prompt for both models.** The only asymmetry is transport (Anthropic SDK
  with prompt caching vs. an OpenAI-compatible chat call). Prompt caching is a cost
  optimization on Opus; it does not change what the model sees or answers.
- **Same tolerant JSON parser** for both replies (handles ```` ```json ```` fences,
  `<think>` blocks, an object with a `references` key, or a bare array), so neither
  model is penalized for formatting quirks.
- **Oracle definition.** Ground truth = every whole-identifier occurrence
  (definition + references) across tracked `.py`/`.ts`/`.tsx` files — exactly what a
  rename touches. Whole-token matching (identifier-boundary aware) avoids matching `X`
  inside `XError`. With the distinctive symbols chosen, stray matches in
  comments/strings are negligible; any that exist are part of the documented oracle,
  not a bug.
- **Scoring conventions.** Empty prediction ⇒ precision is vacuously 1.0 (recall
  carries the penalty, so F1 still goes to 0 when nothing is found). Macro-average
  (each symbol counts equally) is the headline; micro-average (weighted by reference
  count) is also recorded in the JSON.

## Limitations

- Single repository, one language family. Treat the numbers as indicative, not a
  universal ranking.
- The oracle is a *syntactic* find-references, not a type-aware one — it counts
  same-named tokens regardless of scope. The chosen symbols are globally unique, so
  this is accurate here, but it would over-count a generic name like `data`.
- Line-level scoring requires the model to echo the margin line numbers exactly;
  file-level is the more robust headline.
