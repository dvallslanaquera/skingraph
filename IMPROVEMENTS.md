# Refactor Changelog

> Record of the code-review clean-up applied on 2026-06-15. Every item below was
> implemented; the full offline test suite (128 tests) stays green. No runtime
> behaviour changed — these were dead-code removals, de-duplication, and
> readability fixes.

## A. Dead code & files removed
- **A1** — Deleted `src/verify.py` (an unused env smoke-test that defined a
  second `AgentState`, shadowing the real one). Removed the matching `TODO.md` item.
- **A2** — Moved the root `test_scanner.py` (a manual live-API script) to
  [scripts/try_scanner.py](scripts/try_scanner.py) and gave it a proper docstring +
  `sys.path` shim, so it no longer masquerades as a pytest test.
- **A3** — Dropped the unused `pyahocorasick` dependency from
  [pyproject.toml](pyproject.toml) and regenerated `poetry.lock` (`poetry check` passes).
- **A4** — Removed the dead `SUPPORTED_LANGUAGES` constant from [src/config.py](src/config.py).
- **A5** — Removed the vestigial `language_supported` flag (state field,
  `tag_language_node` output, and the two test asserts).

## B. Redundancy factored out
- **B1** — Added [`inci_names()`](src/state.py) as the single source for "collect
  canonical INCI names from `standardized_ingredients`", replacing the inline
  comprehension that was copied across the auditor, coach (×3), API service, and CLI.
- **B2** — Collapsed `flash_scanner_node` / `pro_scanner_node` into a shared
  [`_run_scanner()`](src/nodes/scanner.py) core; the two public nodes now only
  differ by model, prompt, and tag.
- **B3** — Added [`build_vlm()`](src/nodes/scanner.py) and
  [`image_message()`](src/nodes/scanner.py) helpers; the 4 VLM nodes (classify,
  flash, pro, verify-identity) now share client + image-message construction.
- **B4** — [`_run_registry_match()`](src/nodes/registry.py) now returns a single
  dict instead of a `(bool, dict)` whose boolean both callers discarded.
- **B5** — Added [`build_initial_state()`](src/state.py),
  [`load_user_context()`](src/user_store.py), and
  [`save_scanned_product()`](src/user_store.py); `UserNotFoundError` moved to
  `user_store` (re-exported from the API service). The CLI
  ([run_pipeline.py](run_pipeline.py)), the API
  ([service.py](src/api/service.py)), and [try_coach.py](scripts/try_coach.py) now
  share one entry-state factory and one user-load / routine-save path.

## C. Small simplifications
- **C1** — One-lined the trivial `early_registry_router` / `pro_scanner_router`.
- **C2** — Hoisted the coach renderer's per-language label tables to module
  constants ([src/nodes/coach.py](src/nodes/coach.py)).
- **C3** — Scanner log lines now interpolate `FLASH_MODEL` / `PRO_MODEL` instead
  of the stale hard-coded "Gemini 2.5" strings. (Also dropped the obsolete
  prompt-location TODOs.)

## D. Repo hygiene
- **D1** — Added `*.tsbuildinfo` to [ui/.gitignore](ui/.gitignore) and untracked
  the two committed TypeScript build caches.

## E. Documentation accuracy
- **E1** — Updated the README (both JP + EN): registry lookup + INCI normalization
  are now correctly credited to **Qdrant vector search**; `rapidfuzz` is scoped to
  the eval harness; the removed `pyahocorasick` line is gone; the functional-block
  diagram label and "design decision 3" were corrected.

## Intentionally left for the owner to decide
- **A6** — `data/ground_truth.json.docx` (a binary doc committed next to the JSON)
  was **not** deleted: it may be the authoring source of the ground truth and
  isn't something this refactor created. Recommend confirming it's redundant and
  then `git rm`-ing it, or moving it out of `data/`.
  *Resolved 2026-07-02: confirmed redundant and removed (see below).*

---

# Repo hygiene pass — 2026-07-02

- Deleted stray artifacts: `fe.js` (orphaned minified bundle), `raildeploys.txt`,
  `svcs.json`, `data/golden_set/desktop.ini`, and `data/ground_truth.json.docx`
  (closing **A6** — `ground_truth.json` is canonical).
- Deleted the empty root `requirements.txt` and gitignored it: Docker and CI
  regenerate it on the fly via `poetry export`, so a committed copy can only
  mislead.
- **`legacy/README.md` → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — it is
  the authoritative technical deep-dive, not legacy material; the folder name
  said the opposite. All README links updated (JP + EN).
- Extracted the LLM long-context benchmarks (`notebooks/`) into their own
  repository — they compare GLM-5.2 vs Claude Opus 4.8 using this codebase as
  the corpus, which is a separate project from SkinGraph itself. The extracted
  copy takes the target-repo path via `TARGET_REPO_ROOT`.
