# SkinGraph — Implementation Roadmap (Phases 3–7)

> **Purpose of this file.** It is a self-contained execution spec. An engineer (or a
> fresh AI agent with no prior context) should be able to implement each phase below
> using **only this file** plus the codebase. It records the current state of the
> repo, the design decisions already made, the hard constraints, and a concrete,
> verifiable plan per phase. Read "Context", "Current state", and "Constraints &
> conventions" first — they apply to every phase.

## Status — 2026-07-07 (roadmap fully executed)

Every phase below has shipped to `main` (tagged `v1.0.0`). The per-phase specs are kept
as an implementation record; the ✅ headings mark what is live in the repo today.

- **Phase 3 — Code readability ✅** — prompts extracted to `src/prompts/`
  (`coach.py`/`scanner.py`/`websearch.py`), preprocessing split to `src/preprocess.py`,
  bilingual copy in `src/messages.py`, init-once DB migrations (`init_db()` +
  `_initialized` guard in `user_store.py`), and the `state.py`/`pricing.py` correctness
  fixes. (commits `dc87ba2`, `3741058`)
- **Phase 4 — Pipeline efficiency & consultant reasoning ✅** — `verify_identity` and
  `tag_language` nodes removed (graph is now 15 nodes; identity seeded off `classify_side`),
  `class Notice` bilingual carrier, `_introduction_pacing_flags` (one-active-at-a-time +
  patch-test) in `coach.py`, deterministic `Ingredient.is_active` in `normalizer.py`, and
  the anonymous-scan nudge (`check.nudge.*`) in `CheckProduct.tsx`. (commits `71d8743`,
  `26af57c`)
- **Phase 5 — MLOps hardening ✅** — ruff + mypy + pre-commit (`5f6310e`/`38fe0c3`/`fa09f14`),
  the ⭐ replay-based eval-regression gate (`eval/evaluate.py` + committed
  `eval/cassettes/*.json` + `eval/README.md`, `--min-f1` staleness-guarded), custom
  Prometheus metrics + cost-per-scan (`src/metrics.py`), and CI security scanning +
  coverage floor + versioning (`v1.0.0`, `/health` commit sha). (commits `a5cd8d2`,
  `b4305e0`, `56c6d39`)
- **Phase 6 — Coach follow-up chat ✅** — stateless `POST /scan/followup`
  (`src/followup.py`, `src/prompts/followup.py`, `FollowupRequest`/`FollowupResponse`),
  reusing the coach's 薬機法 + grounding contract; UI Q&A thread in `ScanResult.tsx`.
  (commit `52835b9`)
- **Phase 7 — Docs & UI polish ✅** — delivered and exceeded by the UI redesign arc below;
  README is bilingual with logo, `eval/README.md` documents the record/replay workflow.

### Post-roadmap work (delivered beyond this plan)

- **Vision-layer overhaul (S1–S17)** — grounded confidence, barcode lookup, and
  identity-verified web search; adds a dedicated `eval/vision_eval.py`. `SCANNER_SYSTEM_PROMPT`
  is kept byte-identical (cassette hash), so prompt changes require a `--record` re-run.
  (commit `9936e3b`)
- **UI redesign** — landing-style top + bottom nav, hero upload card with coach mascot,
  consistent line-icon set + leaf motifs, prominent scan CTA, mobile goal multi-select fix,
  routine step-order wait cues, a version footer, and expanded JA copy. (commits `405d7e1`,
  `898c402`, `4a60e99`, `b9ee93d`, `bfe13ce`, `7254a31`, `1edd123`)
- **Deterministic auditor** now emits bilingual Japanese safety warnings. (commit `ffc5fdb`)
- **`EVAL-OPS.md`** — a standalone eval/Ops playbook (latency+cost bench, CI scorecard,
  eval-diff PR bot, nightly canary, coach-faithfulness eval, router threshold sweep) with
  GitHub-safe mermaid diagrams. (commit `0187ad5` + pending mermaid-label fixes)

---

## Context

SkinGraph is an AI skincare-label-analysis app used as an **MLOps / AI-platform-engineer
portfolio piece**. A user photographs a product label; a LangGraph pipeline cleans the
image, reads it with a tiered vision-language model (Gemini Flash → Pro), grounds the
ingredients against a curated registry, runs a **deterministic** safety + routine audit,
and a bilingual (JP + EN) "coach" turns the grounded findings into 薬機法-compliant advice.

Three standing goals drive all remaining work:
1. **Simplify** — more logical, more efficient, easier to maintain.
2. **"Closer to what a human would do"** in three senses: (a) the pipeline should *reason*
   like a human skincare consultant, (b) the *output* should read human-written
   (prioritised, not exhaustive dumps), (c) the *code* should read like a senior human
   wrote it (few layers, no AI-boilerplate verbosity, no speculative abstraction).
3. **Strengthen the MLOps / platform-engineering signal** a recruiter sees.

**Already completed** (do not redo):
- **Phase 1 — Repo hygiene.** Deleted `fe.js`, `raildeploys.txt`, `svcs.json`,
  `data/ground_truth.json.docx`, `data/golden_set/desktop.ini`, the empty root
  `requirements.txt` (now gitignored), and the empty `src/utils/`. Renamed
  `legacy/README.md` → `docs/ARCHITECTURE.md` (it is the authoritative technical
  deep-dive; all README links updated, JP + EN). Extracted the LLM long-context
  benchmark that used to live in `notebooks/` into its own repo
  (`github.com/dvallslanaquera/glm5.2-benchmark`); `notebooks/` no longer exists here.
- **Phase 2 — Coach output contract.** The coach used to emit five redundant shapes; it
  now emits **one structured card**. See "Current state" for exactly what that means.

---

## Current state (post Phase 1 & 2) — read before editing

### The coach contract (Phase 2 result)
- **`src/state.py`** now defines the coach models (moved here from `coach.py`):
  - `Recommendation` — one single-language card: `verdict` (1–2 sentence headline),
    `product`, `purpose`, `warnings: List[str]`, `timing` ("AM"/"PM"/"AM & PM"),
    `frequency`, `application_notes: List[str]`, `recommendation_rationale`,
    `routine_integration`.
  - `RoutineFitCard` — `risks`, `redundancy`, `value_add` (all `List[str]`).
  - `CoachResponse` — `recommendation_score: Optional[int]` (None for anonymous scans),
    `japanese: Recommendation`, `english: Recommendation`, `routine_japanese`,
    `routine_english: RoutineFitCard`.
- **`AgentState`** (in `state.py`) "final output" fields are now just:
  `coach_advice: str` (plain-text channel used **only** for graceful-exit messages) and
  `coach_cards: Optional[CoachResponse]`. The old fields (`coach_advice_ja`,
  `coach_advice_en`, `routine_recommendations`, `coach_card`, top-level
  `recommendation_score`, `recommendation_rationale_ja/en`) **no longer exist**.
- **`src/nodes/coach.py`** — `_SYSTEM_PROMPT` is still inline here. The node computes
  deterministic safety cautions and prepends them to each card's `warnings`, then returns
  `{"coach_cards": response}`. Key helpers still here: `_PREGNANCY_FLAGGED_INCI`,
  `_DRYING_INCI`, `_PHOTOSENSITISING_INCI`, `_pregnancy_cautions(state, profile)`,
  `_dehydration_sun_flags(state)`, `_product_context`, `_user_context`, `_routine_context`.
- **`src/render.py`** (new, **CLI-only**) — `render_recommendation`, `render_routine_fit`,
  `render_coach_cards`. The API returns the structured card; only `run_pipeline.py` renders
  text. Do **not** reintroduce server-side text rendering for complete scans.
- **`src/api/schemas.py`** — `ScanResponse` carries `coach: Optional[CoachResponse]` and
  `coach_advice: Optional[str]` (graceful-exit text only). No top-level score/rationale.
- **`src/api/service.py`** — `_status_of` returns "complete" when
  `is_ready_for_logic and coach_cards`. The **server-side typewriter is gone**
  (no `coach_delta`, no `_pick_advice`, no `lang` param). `_to_response` maps
  `coach_cards → coach`. `_NODE_STEP` still maps `tag_language` and `verify_identity`
  (relevant to Phase 4).
- **`src/api/main.py`** — `/scan/stream` no longer takes a `lang` form field.
- **UI** — `ui/src/components/ScanResult.tsx` renders the structured card natively
  (verdict via `ui/src/components/Typewriter.tsx`, timing/frequency badges, warning &
  application-note lists, routine-fit in the UI language with the deterministic
  `routine_fit` as fallback). `ui/src/api/types.ts` mirrors `CoachResponse` as
  `CoachCards`. `ui/src/api/client.ts` `scanStream` has no `lang`/`onCoachDelta`.
  i18n keys `scan.coach.*` exist in `ui/src/i18n/strings.ts` (JP + EN).

### The pipeline (unchanged since original)
LangGraph `StateGraph` in **`src/graph.py`** (~12 nodes, ~9 routers). Flow:
`image_quality_gate` (pixel checks, no VLM) → `classify_side` (Gemini Flash: OOD gate +
front/back) → **back path:** `flash_scanner` (Flash, structured output) → confidence
routing → `correction` loop (max 2) / `early_registry_check` / `pro_scanner` (Gemini Pro)
→ `tag_language` → `registry_lookup` (Qdrant, embedded, `multilingual-e5-small` via
fastembed/ONNX) → `normalizer` (exact dict + semantic fallback to INCI) →
`auditor` (deterministic conflict matrix + irritant registry) → `routine_advisor`
(deterministic cross-product taxonomy) → `coach`. **Front path** (or registry miss with
too few ingredients): `verify_identity` (Flash) → `web_search` (Flash + Google Search
grounding) → `normalizer`… Graceful exits: `retake_request`, `confirm_identity`,
`search_failed` (each sets `coach_advice` and ends).

### Persistence & infra
- **SQLite** (`src/user_store.py`): `users` + `routine_products` tables. Migrations run
  on **every** `_connect()` (Phase 3 fixes this). Scans saved via `save_scanned_product`,
  which now reads `state["coach_cards"]`.
- **Qdrant** (embedded, `src/vectorstore.py`), pre-baked into the Docker image.
- **API**: FastAPI, `POST /scan` (blocking), `POST /scan/stream` (SSE), users CRUD,
  routine CRUD + dashboard. No auth, no rate limiting.
- **Docker**: 4-stage `Dockerfile` (builder → base [pre-bakes ONNX model + Qdrant index]
  → ocr-worker [benchmark-only] → api). `entrypoint.sh`, `railway.toml`.
- **CI** (`.github/workflows/ci.yml`): pytest matrix (3.10/3.12, offline), UI build,
  docker build (no push), terraform validate. Shared dep install:
  `.github/actions/python-deps/action.yml` (runs `poetry export`). `deploy.yml`: re-runs
  tests, optional AWS ECS path (skipped — AWS/Terraform is portfolio-reference only).
- **Eval**: `evaluate.py` at **repo root** — P/R/F1 for ingredient extraction vs
  `data/ground_truth.json` over `data/golden_set/*.jpg` (40 images, gitignored), fuzzy
  INCI matching. Runs against the **real** Gemini API (manual, local only today).
- **Docs**: `README.md` (bilingual marketing), `docs/ARCHITECTURE.md` (deep-dive),
  `docs/preprocessing_comparison.md`, `IMPROVEMENTS.md` (changelog).
- **Tests**: `tests/` — fully offline, Gemini + Qdrant mocked, ~160 tests passing.

---

## Constraints & conventions (apply to every phase)

1. **CI must stay free and offline.** No real LLM/network calls in CI. Recording real
   Gemini responses **once, locally** into committed fixtures and replaying them offline
   is allowed and encouraged (Phase 5).
2. **The app is live.** Railway auto-deploys `main` (API); Vercel auto-deploys `main`
   (UI). Do all work on a **feature branch**; merge to `main` only after the full
   verification suite is green. An API-contract change and its UI change must land in the
   **same merge** (both track `main`).
3. **Bilingual JP + EN is a product requirement** (Japan-market portfolio). Every
   user-facing string needs both languages.
4. **No speculative abstraction.** Do not add provider-abstraction interfaces,
   repository/DI layers, or base classes "for flexibility". The bar for every refactor:
   a senior reviewer should call the result *tastefully small*. Match existing idioms.
5. **薬機法 (Yakukihō) compliance** is mandatory in all coach/advice output — cosmetics
   language only, never medical claims. The rules live in `coach.py`'s `_SYSTEM_PROMPT`;
   reuse them, don't reinvent them.
6. **Determinism for safety.** Anything safety-critical (conflicts, irritants, pregnancy,
   sun/dehydration, active-introduction pacing) is computed by **rules in code**, not left
   to the model. The model only phrases grounded findings.

### Git workflow
- `origin` = `github.com/ShinBellator/skingraph` (**no write access** from the
  `dvallslanaquera` account — do not push there).
- Push feature branches to the `dvallslanaquera` remote:
  `git@github.com:dvallslanaquera/skingraph.git` (add it if absent:
  `git remote add dvallslanaquera git@github.com:dvallslanaquera/skingraph.git`).
- Branch per phase, e.g. `refactor/phase-3-readability`. Commit with
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

### Verification suite (run before every merge)
```bash
poetry run pytest -q                       # offline, must be green
cd ui && npm run build                     # tsc + vite, type-checks the contract
docker build --target api -t skingraph-api-test .   # image still builds
# For phases that change model behaviour, ALSO one real-key run (needs GOOGLE_API_KEY):
poetry run python run_pipeline.py data/golden_set/prod_001.jpg
# and a live API smoke test:
poetry run uvicorn src.api.main:app --port 8010   # then POST an image to /scan and /scan/stream
```

### Phase numbering note
These phases supersede any earlier informal numbering. Recommended execution order is
3 → 4 → 5 → 6 → 7. Phases 3 and 5 are largely independent; Phase 4 benefits from Phase 3
(the `src/messages.py` and `src/prompts/` packages it introduces). **The single
highest-leverage item in this whole roadmap is Phase 5.2 (the offline eval-regression
gate)** — if you only do one thing, do that.

---

## Phase 3 — Code readability & layout ✅ DONE (Effort: M · Risk: low)

Pure refactors, verified fully offline. No behaviour change except the two small
correctness fixes noted. Goal: the repo reads hand-crafted.

### 3.1 Extract prompts into `src/prompts/` (plain `.py` modules)
Rationale: prompts are the biggest inline blobs; extracting them declutters the nodes and
(bonus) makes the Phase 5 cassette staleness-hash trivial. Use `.py`, not `.md` — no
loader code, greppable, supports `.format()`.
- Create `src/prompts/__init__.py` (empty), `src/prompts/coach.py` (the ~186-line
  `_SYSTEM_PROMPT` from `coach.py` → `COACH_SYSTEM_PROMPT`), `src/prompts/scanner.py`
  (the OCR/extraction system prompt + the classify prompt from `src/nodes/scanner.py`),
  `src/prompts/websearch.py` (the verify + search prompts from `src/nodes/websearch.py`).
- Import them back into the nodes. Keep the small pricing prompt inside `src/pricing.py`
  (self-contained, one short prompt).

### 3.2 Split image preprocessing out of `src/nodes/scanner.py`
`scanner.py` mixes a 9-step Pillow/NumPy pipeline with the graph nodes.
- Move `assess_image_quality`, `preprocess_image`, `encode_image`, and the private
  `_apply_white_balance … _sharpen` helpers to a new **`src/preprocess.py`** (it is image
  processing, not a graph node). `scanner.py` keeps `build_vlm`, `image_message`,
  `classify_side_node`, `_run_scanner`, `flash_scanner_node`, `pro_scanner_node`.
- **Efficiency win while moving:** `encode_image` re-runs the full preprocessing (incl.
  the multi-angle deskew loop + CLAHE) on **every** VLM call — classify, each flash
  attempt, pro, and verify all pay it again for the same temp file. Add
  `functools.lru_cache(maxsize=8)` to `encode_image(image_path)`. Saves ~1–3 s/scan.

### 3.3 Introduce `src/messages.py` for graceful-exit copy
Move `_DEFAULT_RETAKE_MESSAGE` / `_REJECTION_MESSAGES` out of `graph.py` (and the
graceful-exit strings currently inline in `src/nodes/websearch.py`'s
`confirm_identity_node` / `search_failed_node`). This module becomes the **bilingual**
message table that Phase 4.2 needs, so structure each entry as `{"en": ..., "ja": ...}`
from the start (Phase 3 can still consume only `en` to stay behaviour-neutral; Phase 4.2
wires up `ja`).

### 3.4 Init-once DB migrations (`src/user_store.py`)
`_connect()` runs `_SCHEMA` + `_migrate_users` + `_ROUTINE_SCHEMA` + `_migrate_routine`
(two `PRAGMA table_info` + conditional `ALTER`s) on **every** call. Move that one-time DDL
into `init_db()` guarded by a module-level `_initialized` flag; `_connect()` becomes
`connect + row_factory` only. Then the defensive `_row_keys`/`opt()` dance in
`_row_to_routine_product` can be simplified (columns are guaranteed post-migration). Keep
it a flat function module — **no repository class**.

### 3.5 Small correctness fixes in `src/state.py`
- `Ingredient.is_active`'s description says "whether the product is a quasi-drug" — a
  copy-paste bug. Fix the docstring to describe an *active* ingredient. (Deterministic
  population of the field is Phase 4.4.)
- `trace_id` is assigned inside `_run_scanner`, so **front-path scans return
  `trace_id: null`**. Assign it in `build_initial_state` instead so every path has one.

### 3.6 `src/pricing.py` dedupe
`pricing.py` has a private ~12-line grounded-response text extractor duplicating
`_text_of` in `src/nodes/websearch.py`. Import the one from `websearch` instead.

### 3.7 Leave `graph.py` routers alone
The ~9 one-liner routers are the LangGraph idiom, each documented. Do **not** consolidate
them — it would hide routing logic. (Node *removals* happen in Phase 4, not here.)

**Verification:** update imports in the affected tests (`tests/test_scanner.py`,
`tests/test_coach.py`, `tests/test_user_store.py`) and `evaluate.py`; run the offline
suite + `docker build --target api` (confirms `COPY src/` picks up the new modules — it
copies the whole dir, so this is safe). No real-key run needed.

---

## Phase 4 — Pipeline efficiency & human-consultant reasoning ✅ DONE (Effort: M · Risk: medium — touches model behaviour)

### 4.1 Remove the third Flash call (`verify_identity`), keep defense-in-depth
`verify_identity_node` (`src/nodes/websearch.py`) makes a Flash call to re-read
brand/product that the classifier and scanner already looked at.
- **Do NOT merge `classify_side` into `flash_scanner`** — the gate exists because the
  structured `ProductExtraction` schema would force the scanner to fabricate a product for
  OOD/selfie frames. Two calls there are justified.
- **Do** eliminate `verify_identity`'s call: extend the `ImageSide` model in
  `src/nodes/scanner.py` with `brand`, `product_name`, `identity_confidence`, and extend
  the classify prompt to also read the branding (the model already looks at it to decide
  front/back). `classify_side_node` writes `identity_confidence` and, on a front photo,
  seeds the minimal `ProductExtraction` that `verify_identity_node` builds today. For the
  back-path web fallback (registry miss + <5 ingredients), reuse the scanner's already
  extracted `brand`/`product_name` and gate `identity_router` on the scanner's
  `extraction_confidence`.
- Delete `verify_identity_node`; re-point `identity_router` to hang off the
  `classify_side` / `registry_lookup` edges. `confirm_identity` / `search_failed` are
  unchanged. Update `_NODE_STEP` in `src/api/service.py`, `tests/test_websearch.py`,
  `tests/test_routers.py`.
- Net: front-path 3 Flash calls → 2; back-path web fallback 4 → 3.

### 4.2 Delete the `tag_language` node
`tag_language_node` (`graph.py`) only uppercases `extracted.source_language` into
`detected_language`. Compute `detected_language` where it's consumed instead:
`_to_response` in `src/api/service.py` and the summary/registry-candidate logging in
`run_pipeline.py` (both from `extracted_data.source_language`). Remove the node, its edge,
and the `detected_language` **state** field (keep the **response** field). Update
`_NODE_STEP`.

### 4.3 Bilingual graceful exits
Graceful-exit messages (`retake_request`, `confirm_identity`, `search_failed`) are
English-only; a JP-UI user who uploads a blurry photo gets English. Since Phase 2 removed
the per-language state fields, add a small bilingual carrier:
- In `src/state.py`, add `class Notice(BaseModel): en: str; ja: str`. Add `notice:
  Optional[Notice]` to `AgentState` and to `ScanResponse` (`src/api/schemas.py`). Drop the
  now-redundant `coach_advice` string field from both (its only remaining use is these
  notices).
- The graceful-exit nodes set `notice=` from the `src/messages.py` bilingual table
  (Phase 3.3). `_status_of` keys "retake_required"/"action_needed" off `notice` +
  `retake_requested`.
- UI: `ScanResult.tsx` renders `result.notice?.[lang]` where it currently renders
  `coach_advice`; update `ui/src/api/types.ts`. `run_pipeline.py` prints `notice.en`
  (CLI is English).

### 4.4 Deterministic human-consultant behaviours (mostly prompt + tiny code)
All within the existing single coach call — **no new nodes**:
- **One-active-at-a-time + patch test.** Add `_introduction_pacing_flags(state, profile)`
  next to `_dehydration_sun_flags` in `coach.py`: if the new product introduces
  Retinoids/AHA/BHA (reuse the function-group classification in
  `src/nodes/routine_advisor.py`, which loads `data/function_groups.json`) **and** the
  saved shelf already has a strong active **or** the profile is `sensitive`, append a
  deterministic ja/en caution ("introduce one new active at a time; patch-test on the
  inner arm for 24 h"). Prepend to `warnings` like the other deterministic flags.
  Deterministic because it is safety-adjacent (same rationale as the pregnancy/sun flags).
- **Sequence placement.** Add one line to the coach prompt's ROUTINE INTEGRATION section:
  "state where in the AM/PM sequence (cleanser → toner → serum → moisturiser → SPF) this
  product goes."
- (Verdict-first + warnings-ordered-by-importance were already added in Phase 2.)

### 4.5 Populate `Ingredient.is_active` deterministically
In `src/nodes/normalizer.py`, after resolving the INCI name, set `is_active=True` when the
canonical name appears in the `data/function_groups.json` markers (cache the flat marker
set at module load, mirroring the other `_*_CACHE` patterns). This lights up the UI's
active-ingredient chips (`ScanResult.tsx`), an immediate "this app understands the label"
signal.

### 4.6 Anonymous-scan nudge (UI)
In `ui/src/pages/CheckProduct.tsx`, when a completed result renders with **no** selected
user, show a banner ("Tell me your skin type and I can tailor this further") linking to
My Profile. Add ja/en strings to `ui/src/i18n/strings.ts`. (Better UX than baking the
nudge into the coach card.)

**Verification:** offline unit tests for the classify-schema change, router changes,
`Notice`, pacing flags, and `is_active`. **Before merge (model-facing change):** one
real-key run (`GOOGLE_API_KEY`) over ~6 golden-set images + one front photo + one OOD
photo — confirm the classifier still gates OOD correctly and front-path identity behaves.
If Phase 5 landed first, use its record-mode to regenerate cassettes here instead.

---

## Phase 5 — MLOps hardening, offline-only CI ✅ DONE (Effort: M–L · Risk: low, mostly CI)

Do the sub-steps in this order. **5.2 is the highest-leverage item in the whole roadmap.**

### 5.1 Ruff + pre-commit + mypy (~half day; table stakes, do first)
- `pyproject.toml`: add `[tool.ruff]` (line-length 100; `lint.select = ["E","F","I","UP","B","S"]`
  — `S` is the bandit ruleset, which is why a separate bandit tool is unnecessary;
  per-file-ignores `S101` for `tests/`, and `S608` where `user_store.py`'s parametrised
  `ALTER TABLE` trips it). Add `[tool.mypy]` scoped to `src/`,
  `plugins = ["pydantic.mypy"]`, non-strict to start.
- `.pre-commit-config.yaml`: ruff, ruff-format, gitleaks.
- New CI job `lint` in `ci.yml`: `ruff check . && ruff format --check . && mypy src`.
- Commit the one-time `ruff format` reflow **separately** from any logic change.

### 5.2 ⭐ Replay-based eval-regression gate in CI (~half day; the differentiator)
Turns the hand-annotated 40-image golden set from a "trust me, I ran it once" F1 number
into an **enforced, offline, prompt-hash-guarded** quality gate on every PR. Use custom
JSON cassettes (not VCR/LangChain-cache — grpc + structured output make HTTP-layer replay
brittle; a result-level cassette is honest and simple).
- Move `evaluate.py` → `eval/evaluate.py` (its `data/...` paths are cwd-relative, so
  `python -m eval.evaluate` from the repo root still works; update the top-of-file usage
  comment and any README reference).
- `eval/evaluate.py --record`: run the real scanners over the golden set (as today) and
  write one cassette per image+model to `eval/cassettes/<image-stem>.<model>.json`:
  ```json
  {
    "image_sha256": "...", "model_id": "gemini-...-flash-lite",
    "prompt_sha256": "...", "recorded_at": "2026-...",
    "extraction": { /* ProductExtraction.model_dump() */ }
  }
  ```
  plus `eval/cassettes/manifest.json` holding the aggregate scores at record time.
  Cassettes are small JSON and **are committed** even though `data/golden_set/*.jpg` stays
  gitignored (replay never needs the images).
- `--replay`: skip the VLM entirely; feed each recorded `extraction` through the **real**
  scoring path (`canonical_inci` → normalizer ledger → fuzzy P/R/F1 vs
  `data/ground_truth.json`); exit non-zero if aggregate F1 < `--min-f1` (set `0.90` for
  flash vs the measured ~0.94).
- **Staleness guard:** replay recomputes `sha256(COACH/scanner prompt text)` +
  `model_id` from `src/config.py` / `src/prompts/`; on mismatch, **fail** with
  "prompts/model changed — re-record locally". This is what makes the gate honest:
  a prompt change cannot silently ship with stale eval numbers.
- New CI job `eval-replay` (reuse `.github/actions/python-deps`):
  `python -m eval.evaluate --replay --min-f1 0.90`. Fully offline; catches regressions in
  the normalizer, ingredient master, ground truth, and scoring on every PR.
- Write `eval/README.md`: golden-set description, why images aren't committed, how to
  reproduce the F1 table, and the record/replay workflow.

### 5.3 Custom Prometheus metrics + cost-per-scan in the API (~1 day)
- New `src/metrics.py` (`prometheus_client`; the existing `Instrumentator().expose()` in
  `main.py` already serves `/metrics`): `scans_total{status,entrypoint}`,
  `scan_node_duration_seconds{node}` histogram, `scan_escalations_total` (pro fallback),
  `scan_corrections_total`, `scan_tokens_total{model,direction}`,
  `scan_cost_usd_total{model}`.
- Node latency: `run_scan_stream` already observes node boundaries via
  `stream_mode="updates"` — record time deltas per node there. Consider refactoring
  `run_scan` to drive the same internal stream loop synchronously so both the blocking and
  SSE paths share one instrumented execution path (a simplification + a metrics win).
- Tokens/cost: attach `langchain_core.callbacks.UsageMetadataCallbackHandler` via
  `callbacks` in `scan_run_config` (`src/observability.py`) — zero node-code changes,
  aggregates usage across all Gemini calls in a run. Add a static
  `MODEL_PRICES_USD_PER_MTOK` table to `src/config.py`. Add
  `usage: {input_tokens, output_tokens, estimated_cost_usd, model_calls}` to
  `ScanResponse` — **cost-per-scan in the response payload is highly recruiter-visible.**
- Test with mocked usage metadata in `tests/test_api.py`.

### 5.4 Security scanning in CI (~1 hour)
Extend the `docker` job: build with `load: true`, then `aquasecurity/trivy-action`
(severity `CRITICAL,HIGH`, fail on findings). Add a `gitleaks/gitleaks-action` job. Bandit
is already covered by ruff's `S` rules — do not add the separate tool.

### 5.5 Coverage gate (~1 hour)
Add `pytest-cov` to the dev group; measure current coverage first, then set
`--cov=src --cov-fail-under=<current − 5>` in `addopts`; ratchet up later. Runs inside the
existing backend matrix — no new job.

### 5.6 Versioning (~1 hour)
- Tag `v1.0.0` when the refactor line merges; keep `[project] version` in `pyproject.toml`
  in sync.
- CI docker job: also tag `skincare-coach-api:${{ github.sha }}`.
- `/health` returns `{status, version, commit}` — commit from `RAILWAY_GIT_COMMIT_SHA`
  (Railway injects it) with a local fallback.

**Verification:** everything offline — CI green is the verification. Only 5.3 touches the
live path — verify locally with one real scan checking `/metrics` and the `usage` block,
then confirm on Railway's `/metrics` after merge.

---

## Phase 6 — Coach follow-up chat ✅ DONE (Effort: M · Risk: medium — new endpoint + UI)

The most human-like feature: after a scan, let the user ask the coach a follow-up
("can I use this with my vitamin C?", "is it OK while pregnant?"). Keep it **stateless** —
no server-side conversation store.

- **Endpoint** `POST /scan/followup` (`src/api/main.py` + `src/api/service.py`). Request
  (`FollowupRequest` in `schemas.py`) carries the grounding the client already received
  from `/scan` plus the question: `product` (brand/name), `standardized_ingredients`,
  `safety_report`, `routine_fit` (optional), `question: str`, `lang: "ja"|"en"`,
  `user_id: Optional[str]` (to reload profile + routine for personalisation). No image,
  no re-scan.
- **Prompt**: a new `src/prompts/followup.py` that **reuses the coach's 薬機法 rules and
  the "ground only in the provided ingredients / never invent benefits" contract**. The
  model answers the single question in the requested language only. Return
  `FollowupResponse { answer: str }` (single language per `lang`).
- **Safety**: the same deterministic guards apply — if the question touches
  pregnancy/conflicts already flagged, surface the deterministic finding rather than
  letting the model reason it out. Refuse medical-diagnosis questions politely (already
  implied by 薬機法 rules).
- **UI**: an "Ask a follow-up" input at the bottom of `ScanResult.tsx`; keep the Q&A
  thread in component state (client-side only). Add `api.followup()` to
  `ui/src/api/client.ts`, types to `ui/src/api/types.ts`, i18n strings.
- **Tests**: mock the LLM (mirror `tests/test_coach.py`'s `mock_coach_llm` fixture);
  assert the prompt includes the grounding context and that an empty/again-scan question
  is handled.

**Verification:** offline unit tests + one real-key manual exchange (ask a follow-up about
`prod_001` and confirm the answer is grounded and 薬機法-safe). API + UI land in one merge.

---

## Phase 7 — Docs & UI polish ✅ DONE (Effort: S–M · Risk: low)

### 7.1 Docs
- `docs/ARCHITECTURE.md`: trim the marketing intro that duplicates `README.md`; add short
  sections for the new eval-replay gate and the metrics/cost tracking; **refresh the
  state-machine diagram** (remove `verify_identity` and `tag_language` after Phase 4).
- `README.md` (keep the bilingual JP + EN structure): add a "Quality gates" subsection to
  the reliability section (eval replay + F1 floor, coverage, Trivy) and mention
  cost-per-scan. Add a one-line "related research" link to the extracted
  `glm5.2-benchmark` repo.
- Ensure `eval/README.md` (from 5.2) is complete.

### 7.2 UI light pass (`ui/src/`) — not a redesign
- **Humanise the meta row** (`ScanResult.tsx`): it shows raw internals (`flash`/`pro`/
  `database`, confidence %). Map through i18n ("Read from label", "Matched in registry",
  "Found via web search") and move confidence into a smaller "details" line.
- **Cap the ingredient dump**: show ~12 chips with a "show all N" toggle — prioritised
  output, not an exhaustive list.
- Confirm the Phase 4.5 active chips render correctly.
- Confirm `ui/.gitignore` covers `dist/` and `*.tsbuildinfo` explicitly.

**Verification:** `npm run build` + a Vercel preview deployment on the PR.

---

## Live-deploy risk register (quick reference)

| Change | Risk | Pre-merge check |
|---|---|---|
| Prompt extraction, preprocess split, DB init-once (Phase 3) | None — pure refactor | pytest + docker build |
| Node removal/rename: `tag_language`, `verify_identity` (Phase 4) | `_NODE_STEP` map + tests must move in the **same** PR | pytest + local SSE scan |
| Classify schema/prompt extension (4.1) | Real Gemini behaviour can shift | Local real-key run on ~6 golden + 1 front + 1 OOD (or Phase 5 cassette re-record) |
| `run_scan` → shared stream loop (5.3) | Blocking `/scan` path changes | `tests/test_api.py` + one local real `/scan` |
| New `/scan/followup` (Phase 6) | New surface, isolated | offline tests + one real exchange |
| Any merge to `main` | Auto-deploys Railway + Vercel | Watch `/health` (now returns commit sha), one live scan, check `/metrics` |

## Effort & sequencing summary
- **Phase 3** — M (1–2 days), low risk, do first (unblocks 4).
- **Phase 4** — M (1–2 days), needs one real-key verification pass.
- **Phase 5** — M–L (2–3 days for 5.1–5.3; 5.4–5.6 an afternoon). **5.2 is #1 priority.**
- **Phase 6** — M (1–2 days).
- **Phase 7** — S–M (1 day); do last so docs/diagrams reflect the final architecture.
