# GLM-5.2 vs Claude Opus 4.8 — two benchmarks

Two small, reproducible benchmarks behind the article's claim: that a long-context
model like **GLM-5.2** can rival **Claude Opus 4.8** at working over a whole codebase.
Both score against **deterministic** ground truth — a static-analysis oracle and a real
test suite — so the numbers are auditable and never drift.

| | Benchmark 1 — **Blast Radius** | Benchmark 2 — **Debug Loop** |
|---|---|---|
| Question | "If you rename `X`, what breaks?" | "This backend bug is reported — fix it." |
| Shape | One shot, whole repo in context | Agentic: tools + iterate |
| Ground truth | `grep`/find-references oracle | a real failing pytest (SWE-bench style) |
| Measures | long-context *retrieval* | long-context *reasoning + action* |
| Entry point | `python run_benchmark.py` | `python run_benchmark.py --debug-loop` |
| Results file | `results/latest.json` | `results/debug_loop_latest.json` |

> (Note: `notebooks/README.md` is a separate, pre-existing SkinGraph interview Q&A —
> this write-up lives in `BLAST_RADIUS.md` to avoid clobbering it.)

---

# Benchmark 1 — Blast Radius (single-shot find-references)

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

## Run it

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

Set the keys (see [Keys](#keys) below), then run. Each model that has a key is
benchmarked; the other is skipped.

```bash
python run_benchmark.py                      # both models, all 10 symbols
python run_benchmark.py --models opus-4-8    # one model only
python run_benchmark.py --limit 3            # first 3 symbols (quick/cheap)
```

Every run writes `results/<mode>_<timestamp>.json` **and** refreshes
`results/latest.json`. Then open the notebook for the charts (F1, precision/recall,
recall-vs-blast-radius, cost/latency):

```bash
jupyter notebook analysis.ipynb
```

---

# Benchmark 2 — Debug Loop (agentic bug-fix)

Where Benchmark 1 hands the model everything and grades one answer, this one gives each
model *tools* and lets it iterate to fix a real bug, graded by a real test. It's the
**SWE-bench pattern**.

## The scenario — commit `d11ae62`

A genuine bug from this repo's history:

- **Bug:** `POST /scan` ran the whole LangGraph pipeline in one blocking request; on
  Railway the long idle connection tripped the reverse-proxy timeout and the browser
  reported a generic "backend not running" error.
- **Fix:** a streaming `POST /scan/stream` SSE endpoint that emits a frame as each node
  finishes, with keepalive pings.
- **Oracle:** the same commit also added the `test_scan_stream_*` tests (fully offline,
  graph stubbed). The harness checks out the buggy parent `d11ae62^`, applies **only
  the test patch** from `d11ae62`, and lets the model edit source until those tests
  pass — without regressing the rest of `tests/test_api.py`.

The model never sees the fix; it sees the symptom (the failing test output) and a
description, exactly as an on-call engineer would.

## How a trial runs

- Each model+trial gets its **own isolated git worktree** on the buggy commit, using
  the project's Poetry venv — so models never interfere with each other or your tree.
- The model drives the loop by calling **five tools** (provider-neutral schemas, mapped
  per provider): `list_dir`, `read_file`, `grep`, `edit_file`, `run_tests`.
- "Done" = the `scan_stream` tests pass and `tests/test_api.py` doesn't regress, checked
  by actually running `pytest` in the worktree.
- The loop runs up to `--steps` tool-steps; the model finishes by replying with no tool
  calls.

## What it measures

Each model runs `--trials` independent attempts (default 5), and we report:

- **pass@1** and unbiased **pass@k** (Chen et al. 2021) — the probability that at least
  one of *k* sampled attempts produces a passing fix.
- **Efficiency** by **tool-call count, total tokens, cost, and latency** (medians) —
  *not* steps, since Opus can batch several tool calls into one step, making step counts
  incomparable across providers.
- **cost_per_pass** and a **pass@k-vs-expected-cost** curve — "what does a passing fix
  cost if I'm willing to sample *k* times?", the question that actually decides which
  model to put in a CI auto-fixer.

## Run it

```bash
python run_benchmark.py --debug-loop                       # both models, 5 trials each
python run_benchmark.py --debug-loop --trials 1 --steps 8  # quick smoke test
python run_benchmark.py --debug-loop --models opus-4-8     # one model only
```

| Flag | Meaning |
|---|---|
| `--trials N` | independent attempts per model (pass@k); default 5 |
| `--steps N` | max tool-loop steps per attempt; default 15 |
| `--no-verdict` | skip the pytest oracle; report loop mechanics only |
| `--install-deps` | if the pre-flight import fails on a missing dep, pip-install it into the venv |
| `--keep-worktree` | keep the per-trial worktrees for inspection (path printed) |

Results go to `results/debug_loop_<timestamp>.json` **and** `results/debug_loop_latest.json`
— and **never** touch `results/latest.json`, so the two benchmarks stay fully separate.
A pass@k-vs-cost summary table is printed to the terminal at the end.

> **Pre-flight:** the verdict needs the project's deps importable in the venv. If one is
> missing, run with `--install-deps` (auto-installs it) or `--no-verdict` (runs the loop
> without grading).

---

# Keys

GLM-5.2's default path is **Ollama Cloud** (`glm-5.2:cloud`); Opus uses the Anthropic
API. Keys are read from the environment — and, if `python-dotenv` is installed, from the
project `.env` automatically (real env vars still win).

```bash
# Claude Opus 4.8 — note: the API is billed separately from a Claude Pro subscription
export ANTHROPIC_API_KEY=sk-ant-...

# GLM-5.2 via Ollama Cloud
export OLLAMA_API_KEY=...          # OR run `ollama signin` and omit this
export GLM_MODEL=glm-5.2:cloud     # optional override (default shown)
export OLLAMA_NUM_CTX=131072       # optional; keep large so local Ollama can't truncate
```

On Windows PowerShell use `$env:ANTHROPIC_API_KEY = "..."` instead of `export`, or put
the keys in `.env`. Confirm both resolve before spending tokens:

```bash
python -c "from blast_radius import config, models; [print(c.label, '->', 'ready' if models.is_available(c) else 'NO KEY') for c in config.MODELS.values()]"
```

**To use z.ai / Zhipu instead of Ollama** for GLM, set `GLM_PROVIDER=openai_compatible`
and provide `GLM_API_KEY` (+ optional `GLM_BASE_URL`, `GLM_MODEL`).

## Pricing (for the cost figures)

- **Opus 4.8** input/output pricing is built in ($5 / $25 per 1M tokens) and it
  **prompt-caches** the shared context, so repeated calls reuse one cached prefix
  (cache reads bill ~0.1×).
- **GLM-5.2** pricing defaults to the GLM-5.2 Cloud API list rate ($1.40 / $4.40 per
  1M input/output tokens). When the GLM run goes through Ollama Cloud (the default
  provider), billing is by subscription/usage, so the per-token cost is only
  indicative — treat the GLM cost figures as a rough guide. Override with your real rate:
  ```bash
  export GLM_INPUT_PRICE=1.40     # USD per 1M input tokens
  export GLM_OUTPUT_PRICE=4.40    # USD per 1M output tokens
  ```

---

# Layout

```
notebooks/
├── run_benchmark.py        # terminal entry point for BOTH benchmarks (--debug-loop selects #2)
├── analysis.ipynb          # graphs for Benchmark 1 (reads results/latest.json)
├── requirements.txt
├── results/                # JSON written here (latest.json / debug_loop_latest.json)
└── blast_radius/
    ├── config.py           # target symbols, model configs, pricing, exclusions  ← tweak here
    ├── repo_context.py     # builds the line-numbered repo dump (excludes notebooks/)
    ├── oracle.py           # deterministic find-references ground truth (pure stdlib)
    ├── models.py           # Opus 4.8 (Anthropic) + GLM-5.2 (Ollama / OpenAI-compatible)
    ├── scoring.py          # precision / recall / F1, file + line level
    ├── runner.py           # Benchmark 1 orchestration + JSON output
    └── debug_loop.py       # Benchmark 2: tool harness, worktrees, pytest verdict, pass@k
```

The oracle, context builder, and scoring are **pure standard library** — no external
binary, no model — and run identically on Windows/macOS/Linux.

---

# Methodology & fairness notes

**Shared**

- **Identical prompts/tools for both models.** The only asymmetry is transport
  (Anthropic SDK with prompt caching vs. an OpenAI-compatible / Ollama chat call).
  Prompt caching is a cost optimization on Opus; it does not change what the model sees.
- **Same tolerant JSON parser** for replies (handles ```` ```json ```` fences,
  `<think>` blocks, an object with a `references` key, or a bare array), so neither
  model is penalized for formatting quirks.
- **The benchmark never measures itself** — `notebooks/` is excluded from the dump and
  the oracle, so the harness's own source (which lists the target symbols as strings)
  can't contaminate the ground truth.

**Benchmark 1**

- **One question per symbol, full repo in context each time** — independent calls, no
  cross-contamination; this is the long-context test, not a multi-turn chat.
- **Oracle definition.** Ground truth = every whole-identifier occurrence
  (definition + references) across tracked `.py`/`.ts`/`.tsx` files — exactly what a
  rename touches. Whole-token matching (identifier-boundary aware) avoids matching `X`
  inside `XError`.
- **Scoring conventions.** Empty prediction ⇒ precision is vacuously 1.0 (recall
  carries the penalty, so F1 still goes to 0 when nothing is found). Macro-average
  (each symbol counts equally) is the headline; micro-average is also in the JSON.

**Benchmark 2**

- **The model never sees the fix** — only the symptom (failing-test output) and the
  test file that defines "done". Source edits are the model's own.
- **Verdict is a real `pytest` run** in an isolated worktree — not a model judging a
  model — and the no-regression check guards against "fixes" that break other tests.
- **Efficiency is tool-calls + tokens + cost, not steps**, because providers batch tool
  calls differently per step. pass@k is the unbiased estimator, so small trial counts
  don't over- or under-state the pass rate.

---

# Limitations

- Single repository, one language family. Treat the numbers as indicative, not a
  universal ranking.
- **Benchmark 1's** oracle is a *syntactic* find-references, not type-aware — it counts
  same-named tokens regardless of scope. The chosen symbols are globally unique, so this
  is accurate here, but it would over-count a generic name like `data`. Line-level
  scoring also requires the model to echo the margin line numbers exactly, so file-level
  is the more robust headline.
- **Benchmark 2** is a single bug scenario — a strong signal about *this* fix, not a
  general SWE-bench score. Increase `--trials` for tighter pass@k confidence intervals.
- GLM cost figures are indicative when run through Ollama Cloud (subscription billing);
  Opus costs are exact.
