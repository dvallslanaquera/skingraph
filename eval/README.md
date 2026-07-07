# Eval harness — golden set, record & replay

The full eval/ops layer and the reasoning behind each piece is written up in
[`../EVAL-OPS.md`](../EVAL-OPS.md). The modules:

- **`eval/evaluate.py`** — back-label extraction accuracy (this README). Also
  captures per-scan latency + token cost on `--record` and reports it per model
  tier with `--bench` (§4).
- **`eval/vision_eval.py`** — the vision-layer *gates*: the Tier-1 pixel
  pre-flight (dark/bright/blank/blurry) and the Tier-2 content+side classifier.
  Driven by a hand-labeled manifest (`data/vision_eval_set.json`; images stay
  out of git). `--sweep` prints the Tier-1 stat distributions per label so the
  config thresholds can be calibrated from data; `--live` also scores the
  classifier (needs `GOOGLE_API_KEY`). Frames captured by the opt-in rejection
  store (`REJECTION_STORE_ENABLED=1` → `data/rejections/`) are the natural feed
  for this set.
- **`eval/coach_eval.py`** — coach faithfulness (§8): runs `coach_node` with the
  Gemini call stubbed to empty warnings and asserts every mandated safety
  caution survives into the card. Offline gate: `--min-coverage 1.0`.
- **`eval/scorecard.py`** — publishes the replay results as a Markdown scorecard
  (`$GITHUB_STEP_SUMMARY`), a trend history (`eval/history.jsonl`), and shields
  badges (`docs/badges/`) (§5).
- **`eval/diff.py`** — diffs two `--replay --save` result sets into a PR comment
  (§6; driven by `.github/workflows/eval-diff.yml`).
- **`eval/canary.py`** — live drift check against the pinned cassettes; `--dry-run`
  self-tests offline (§7; driven by `.github/workflows/canary.yml`).
- **`eval/sweep.py`** — Flash→Pro threshold sweep, the cost/accuracy Pareto
  frontier over recorded `--model both` cassettes (§9).

`eval/evaluate.py` scores the vision scanner's ingredient extraction against a
hand-annotated **golden set**: 40+ real product-label photos
(`data/golden_set/*.jpg`), 14 of which carry per-product ground truth in
`data/ground_truth.json` (brand, product name, quasi-drug flag, and the full
ingredient list with English-INCI translations). Several annotated photos show
the product's **front** — the ground truth was transcribed from the physical
label — so they exercise brand/product identification but structurally yield
zero extracted ingredients; the F1 gate therefore covers the photos whose
recorded extraction was an actual successful ingredient-list read.

Scoring is language-independent: every extracted ingredient is resolved to a
canonical English INCI name (the VLM's own `name_standardized`, then the
normalizer ledger's exact tier) and fuzzy-matched (rapidfuzz `WRatio`, cutoff
85) against the `ingredient_inci` ground truth, giving per-image and aggregate
precision / recall / F1. Only the ledger's exact tier is used — not the Qdrant
semantic tier — so the metric is deterministic and needs no vector index or
embedding model.

The label photos are **not committed** (they are personal photographs of
retail products; some contain store/receipt context) — only the annotations
and the recorded cassettes are. Replay never needs the images.

## The offline regression gate (CI)

Every PR runs, with no API key and no images:

```bash
python -m eval.evaluate --replay --min-f1 0.90
```

`--replay` feeds the **recorded** extractions (see below) through the real
scoring path — canonical-INCI resolution → normalizer ledger → fuzzy P/R/F1 —
and fails the build if the aggregate ingredient F1 drops below the floor.
This catches regressions in the normalizer, the ingredient master, the ground
truth, and the scoring itself on every change.

### Staleness guard

Each cassette stores `prompt_sha256` (hash of the scanner extraction prompt)
and `model_id` at record time. Replay recomputes both from the current code
(`src/prompts/scanner.py`, `src/config.py`) and **fails on any mismatch**:
a prompt or model change cannot silently ship with stale eval numbers — it
forces a local re-record so the committed scores always describe the current
pipeline. Golden-set drift is caught the same way (image hashes when the
images are present locally; manifest ids vs `ground_truth.json` otherwise).

## Recording cassettes (local, real API)

```bash
poetry run python -m eval.evaluate --record            # flash over the full set
poetry run python -m eval.evaluate --record --model both
```

Needs `GOOGLE_API_KEY` in `.env` and the golden-set images on disk. Writes one
JSON cassette per image+model to `eval/cassettes/<image-stem>.<model>.json`:

```json
{
  "id": "prod_001",
  "image_sha256": "…",
  "model_id": "gemini-3.1-flash-lite",
  "prompt_sha256": "…",
  "recorded_at": "2026-07-03T…+00:00",
  "extraction": { "…": "ProductExtraction.model_dump()" }
}
```

plus `eval/cassettes/manifest.json` with the covered ids and the aggregate
scores at record time. Commit both — they are small JSON and are what CI
replays. Re-record whenever you change the scanner prompt, the model id, or
the golden set (the gate will refuse to run until you do).

Cassettes are result-level (the parsed `ProductExtraction`), not HTTP-level:
gRPC + structured output make transport-layer replay brittle, and a
result-level cassette is honest about what is actually being regression-tested
— everything *downstream* of the VLM call.

## Reproducing the accuracy table

```bash
poetry run python -m eval.evaluate --model both --save data/eval_results.json
```

runs both scanners live over every annotated image and prints per-image
diagnostics (missed / hallucinated ingredients, brand & product match,
quasi-drug flag) plus the aggregate block. `--id prod_007` (repeatable)
narrows to specific entries while iterating.
