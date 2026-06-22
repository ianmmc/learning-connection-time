# Project Synthesis — Learning Connection Time

> **Purpose of this document:** A reorientation map produced after a ~4.5-month pause (work paused ~2026-01-31; this synthesis written 2026-06-05). It captures the current architecture, pipelines, and data state, points to where authoritative information lives, and **flags** errors / inconsistencies / opportunities — *without fixing them*. It is a starting point for resuming work, not a change log.
>
> **Method:** Synthesized from five parallel read-only specialist investigations (acquisition pipeline, enrichment scripts, database + LCT core, documentation corpus, tests + data state). No code was run and the database was **not** queried — so every count or "what happened" claim here is **UNVERIFIED against the live DB** and flagged as such. Per project rule #6, verify in the DB before trusting any number.

> **Cleanup pass — 2026-06-05 (after this synthesis):** A directory cleanup was run on top of restore-point commit `59603c3` (commits `3d4c7a9` + `8f71c6e`). It **resolved** several Section 8 flags: #1 (`Claude.md`→`CLAUDE.md` rename), #3 (`MULTI_TIER_ENRICHMENT_ARCHITECTURE.md`→`ACQUISITION_PIPELINE.md`), #2/#4 (stale Firecrawl/Gemini/Playwright + acquisition-tier prose rewritten across README/PROJECT_CONTEXT/CLAUDE_CORE/REFERENCE/GETTING_STARTED/TERMINOLOGY/METHODOLOGY), #22 (deleted broken `full_pipeline.py`), #23 (corrected — `google_drive_handler.py` is live-imported, NOT orphaned; `content_parser.py` is test-covered; both kept), plus `.DS_Store` litter, a 66 MB `context.xml`, the `src/` scaffold, and `setup_structure.py`. Also: the pre-commit hook **DB-verified 65 districts have bell schedules** (resolves the count uncertainty in §7). The remaining flags — data-quality / unfinished benchmark (B), pipeline seams (C), DB/migrations (D), missing tests (F) — were **not** touched and still stand.

> **Pipeline verification + migration repair — 2026-06-06:** Ran the full test suite (**786 passed / 20 skipped / 0 failed**) and inspected the live DB directly: NCES (17,842 districts), SPED estimates (17,222), state crosswalk (17,842, all `st_leaid`), and bell schedules (65 districts: 81 human_provided + 61 automated) all present and coherent. A reproducibility re-run of `calculate_lct_variants.py` surfaced and fixed two **latent bugs** that had silently broken LCT regeneration: **(1)** migration `014_add_staff_scope_to_lct.sql` was **half-applied** — repaired (applied atomically) and a **migration ledger now exists** (`schema_migrations` + `infrastructure/database/migrations/migrate.py`, 002–015 backfilled) → **resolves flag #17**, and **#16** (duplicate `014`) is now tracked/managed; **(2)** the `lct_calculations` id sequence was out of sync *and* the script never cleared rows before writing — fixed the script (`clear_lct_calculations` now called before write) so full re-runs are idempotent. Also: **#18 resolved** (`districts.is_shared_service_entity` confirmed present in the live DB) and **migration 015 confirmed applied**. LCT was recalculated (167,391 rows) so metrics now reflect all 65 enriched districts. Still open from group D: **#19** (stale data dictionary) and **#20** (obsolete `schema.sql`). Group F is partially addressed (added `tests/test_migrations.py`); the acquisition-pipeline test gap remains.

---

## 0. TL;DR — Where Things Stand

1. **Mission is unchanged and durable.** Transform student-teacher ratios into "Learning Connection Time" (LCT) = `(Daily Instructional Minutes × Instructional Staff) / Enrollment`. The LCT/SPED/data-year methodology is stable and well-documented.

2. **A major architecture shift happened just before the pause (Jan 25–26, 2026):** the bell-schedule acquisition system was rebuilt from a **multi-tier Firecrawl/Gemini/Playwright** pipeline to a **Crawlee + FastAPI + Ollama (local LLM)** pipeline. The removal of the old system is **complete in code** but **lagging in several docs**.

3. **~2,000 lines of uncommitted work** sit in the working tree (FastAPI API + TypeScript scraper). This is a **coherent feature expansion** (async crawl jobs, school discovery/sampling, serial queue, LLM time-extraction stage), not a broken mid-refactor. It was run successfully but **never committed**.

4. **The true "where it stopped" point is later than the last commit.** After the Jan 26 batch enrichment runs produced **unreliable extractions** (wrong grades, implausible times, ~50% success), work pivoted (Jan 27–31) to building a **benchmark / ground-truth harness** to measure Ollama extraction accuracy. That harness is **built but never run to completion** (`data/benchmark_results/` is empty; 6 hand-labeled ground-truth files exist). **You paused mid-evaluation of extraction quality, not mid-build.**

5. **Testing is inverted relative to activity:** the stable backbone (LCT math, SPED, safeguards, verification, SEA integrations) is well-tested; the **new acquisition pipeline has zero automated tests**, and the old scraper tests are now broken/inert (reference a deleted module).

---

## 1. System Map

The project has **four layers**. The first three are stable; the fourth is where all recent churn lives.

```
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 4: ACQUISITION + ENRICHMENT  (NEW, Jan 2026, mostly uncommitted)│
│   Crawlee scraper (Node/TS, :3000) ── FastAPI orchestrator (:8000)    │
│        └ map / discover / capture        └ rank·triage·extract·queue  │
│                                          └ Ollama (local LLM, :11434)  │
│   → captured PDFs → text → extracted times → minutes → DB import       │
└─────────────────────────────────────────────────────────────────────┘
            │ writes bell_schedules rows
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 3: DATA BACKBONE  (stable)                                      │
│   PostgreSQL (Docker) + SQLAlchemy models + migrations 002→015        │
│   districts · bell_schedules · state_requirements · staff_counts_*    │
│   · enrollment_by_grade · sped_estimates · *_crosswalk · lct_calc…    │
└─────────────────────────────────────────────────────────────────────┘
            │ read by
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 2: LCT ENGINE  (stable)                                        │
│   calculate_lct_variants.py — DB-first; 7+3 scopes; safeguards; QA    │
│   → lct_calculations rows → exported CSVs/JSON                        │
└─────────────────────────────────────────────────────────────────────┘
            ▲ fed by
┌─────────────────────────────────────────────────────────────────────┐
│ LAYER 1: SOURCE DATA  (stable)                                       │
│   NCES CCD (2023-24 primary) · CRDC · IDEA 618 · 9 SEA integrations   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer 4 — Acquisition + Enrichment Pipeline (the active frontier)

### 2.1 Two services + local LLM

| Component | Tech | Port | Responsibility |
|---|---|---|---|
| **Crawlee scraper** | Node/TypeScript (Express, `tsx`, Playwright) | 3000 | Crawl district + sampled school sites; extract per-page signals; capture pages as PDFs; disk-backed async jobs |
| **FastAPI orchestrator** | Python | 8000 | Drive the whole flow; talk to Crawlee over HTTP and Ollama via the `ollama` lib; serial work queue; DB import; LLM time-extraction |
| **Ollama** | local LLM | 11434 | `phi3:mini` ranks URLs; `llama3.1:8b` triages PDFs and extracts times. Auto-launched low-priority by `ollama_launcher.py` |

### 2.2 End-to-end flow

```
district URL
  → /discover/sample (find schools, grade-band sample)
  → /map/start + poll /map/status  (async crawl per school; 180s timeout; falls back to district-level /map)
  → Ollama rank_urls (phi3:mini, keep score ≥ 0.3, top-N)        ── learning loop feeds URL scores
  → capture PDFs   (Google Drive → handler; direct .pdf → requests; else Crawlee /capture)
  → pdftotext → Ollama triage_pdf (llama3.1:8b)
        ≥0.7 → active/ ; 0.3–0.7 → quarantine/ ; <0.3 → rejected/   ── learning loop feeds triage results
  → metadata.json
─────────────────  (separate, manual trigger)  ─────────────────
  → POST /enrich/extract → extraction_service (llama3.1:8b over active/*.txt) → extraction_result.json
  → [MANUAL Claude verification → verified_extraction.json]   ← NO SCRIPT; human-in-the-loop gap
  → calculate_minutes.py (deterministic math) → enrichment_ready.json
  → pipeline_import_bell_schedules.py → DB (bell_schedules) → import_result.json
  → pipeline_verify_enrichment.py → verification_report.json
```

A serial **queue** (`queue_service.py`, `/acquire/start`) processes districts one at a time. The acquisition half and the enrichment/extraction half are **not auto-chained** — the latter is driven out-of-band by scripts in `infrastructure/scripts/enrich/`.

### 2.3 Key files

**Scraper** (`infrastructure/scraper/src/`):
- `server.ts` — Express API: `/scrape`, `/discover`, `/discover/sample`, `/map`, `/map/start`, `/map/status/:id`, `/map/jobs`, `/capture`; API-key auth.
- `mapper.ts` — Crawlee crawl + per-page signal extraction (time-pattern counts, schedule-PDF links, keywords); sync + async variants.
- `discovery.ts` — find individual school sites from a district; grade inference; grade-band sampling.
- `jobManager.ts` — disk-backed async job state in `data/jobs/{jobId}/`.
- `capturer.ts`, `pool.ts`, `queue.ts`, `scraper.ts`, `types.ts`, `logger.ts` — PDF capture, browser pool, in-proc queue, single-URL scrape, types, logging.

**API** (`infrastructure/api/`):
- `main.py` — FastAPI app; mounts routers `acquire`, `triage`, `patterns`, `enrich`; `nice +10`.
- `routes/acquire.py` — orchestrator + serial-queue endpoints (largest, most central file).
- `routes/enrich.py` — time-extraction endpoints (newer "Phase 8/9").
- `routes/triage.py`, `routes/patterns.py` — single-PDF triage; pattern inspection/learning.
- `services/crawlee_client.py` — async HTTP client to Crawlee.
- `services/ollama_service.py` — URL ranking + PDF triage (each with heuristic fallback).
- `services/extraction_service.py` — LLM time extraction + rule-based validation/grade inference.
- `services/ollama_launcher.py` — ensures Ollama running via `~/.local/bin/ollama-serve-lowpri`.
- `services/queue_service.py` — file-based serial acquisition queue.
- `services/patterns_service.py` — semantic-keyword URL pattern learning loop.
- `data/config/crawlee_patterns.json` — learned include/exclude URL globs + stats.
- `data/config/extraction_rules.json` — time labels, grade inference, validation bounds, learned corrections.

**Enrichment scripts** (`infrastructure/scripts/enrich/`):
- **Current 5-step pipeline (production-shaped):** `regex_extract_times.py` (LLM-free fallback extractor) · `calculate_minutes.py` (deterministic minutes; subtracts 30-min lunch if day >330 min) · `pipeline_import_bell_schedules.py` (validated DB import) · `pipeline_verify_enrichment.py` (DB-vs-source diff) · `grade_level_utils.py`.
- **Throwaway run drivers:** `run_batch_pipeline.py` (hardcoded 10-district list; delete-then-import; skips verify) · `retry_failed_districts.py` (hardcoded 5 failures).
- **Older / superseded:** `content_parser.py`, `extract_from_pdfs.py`, `google_drive_handler.py` (still reference Firecrawl/Claude/Gemini; Gemini branch is an unimplemented stub) · `ollama_selector.py`, `import_manual_bell_schedules.py`, `migrate_manual_pdfs.py`, `interactive_enrichment.py`, `enrichment_progress.py`, `filter_enrichment_candidates.py`.
- `infrastructure/scripts/enrich/CLAUDE.md` — **empty auto-generated stub**, not a real briefing.

**Benchmark harness** (`infrastructure/scripts/benchmark/`, created Jan 27): `create_ground_truth.py`, `run_benchmark.py`, `score_extraction.py`, `compare_models.py` — model-comparison + extraction-scoring framework. **Built, not yet run** (`data/benchmark_results/` empty).

### 2.4 Authoritative docs for this layer

- **`docs/MULTI_TIER_ENRICHMENT_ARCHITECTURE.md`** — despite the misleading filename, this is the **canonical, current** description of the new Crawlee+Ollama pipeline (rewritten Jan 26; all 13 referenced files exist). It does *not* yet cover the `enrich.py` / `extraction_service.py` extraction stage.
- The enrichment-script "Phase 8/9" design source-of-truth is cited in code headers as `~/.claude/plans/crispy-brewing-blanket.md` (outside the repo; not reviewed).

---

## 3. Layer 3 — Data Backbone (stable)

**PostgreSQL on Docker** (`lct_postgres`), SQLAlchemy ORM. **`infrastructure/database/models.py` is the authoritative schema** (`schema.sql` is the obsolete original DDL; the data dictionary is stale — see flags).

**Key tables:** `districts` (PK `nces_id`) · `bell_schedules` (enriched minutes; unique on district_id+year+grade_level; method ∈ automated_enrichment / human_provided / statutory_fallback) · `state_requirements` (statutory minutes fallback) · `staff_counts` + `staff_counts_effective` (pre-computed scope + level splits) · `enrollment_by_grade` · `sped_estimates` + `ca_sped_district_environments` · `state_district_crosswalk` (single source of truth for NCES↔state IDs) + per-state tables (TX/FL/IL/MA/MI/NY/PA/VA/CA) · `lct_calculations` (output) · `calculation_runs` · `enrichment_attempts` + `enrichment_queue` · `data_lineage` / `data_source_registry`.

**Migration story (002→015):** granular staffing (002) → state SEA integration + crosswalk (003–007) → temporal 3-year window + calc modes (008–009) → enrichment audit + queue (010–011) → NCES website/grade-span/security-blocking (012–014) → staff-scope expansion + NCES-ID leading-zero fix (014_add_staff_scope, 015).

**Key files:** `connection.py` (`session_scope()`, Docker health check) · `models.py` · `queries.py` (read/report helpers + a **legacy** single-scope LCT path) · `enrichment_tracking.py` · `enrichment_utils.py` (`copy_enrichment_to_bell_schedules`) · `batch_composer.py` · `export_json.py` · `migrations/`.

---

## 4. Layer 2 — LCT Engine (stable)

**`infrastructure/scripts/analyze/calculate_lct_variants.py`** (the current/recommended engine, ~1,545 lines).

- **Formula:** `lct = (instructional_minutes × staff_count) / enrollment`.
- **Minutes priority:** bell schedule for grade → any-level bell fallback (high>middle>elem) → state requirement → 360 default → mapped to data_tier 1/2/3.
- **Modes:** `BLENDED` (default; most-recent data within the 3-year window) vs `TARGET_YEAR`.
- **Scopes emitted (one `lct_calculations` row each):** 5 base (`teachers_only`, `teachers_core`, `instructional`, `instructional_plus_support`, `all`) + 2 grade-level (`teachers_elementary` K-5, `teachers_secondary` 6-12) + 3 SPED (`core_sped`, `teachers_gened`, `instructional_sped`; precedence CA actual > federal 2017-18 estimate; capped at 360).
- **Safeguards:** ERR_FLAT_STAFF, ERR_IMPOSSIBLE_SSR, ERR_VOLATILE, ERR_RATIO_CEILING, WARN_LCT_LOW/HIGH (flag-only, not filtered).
- **DB-first (commit f0b772f):** writes to DB first, then exports CSVs *from* the DB; run tracked in `calculation_runs`. Outputs in `data/enriched/lct-calculations/`.

---

## 5. Layer 1 — Source Data (stable)

NCES CCD (**2023-24 primary**), CRDC (LEA SPED), IDEA 618 (2017-18 SPED baseline, exempt from the ≤3-year temporal rule), and **9 SEA integrations** (FL, TX, CA, NY, IL, MI, PA, VA, MA). Bell schedules: 2025-26 / 2024-25 / 2023-24 interchangeable, search current first; **COVID years 2019-20→2022-23 never used**.

---

## 6. Durable Methodology Facts (still true)

- **LCT formula:** `(Daily Instructional Minutes × Instructional Staff) / Enrollment`. Ex: 360 × 250 / 5000 = 18 min/student/day.
- **Variants** (all exclude Pre-K): Teachers, Core, Instructional (recommended primary), Support, All + Teachers-Elementary (K-5) + Teachers-Secondary (6-12) + 3 SPED scopes.
- **Data-year strategy:** NCES CCD 2023-24 primary; bell schedules post-COVID interchangeable; COVID excluded.
- **SPED v3:** self-contained SPED (~6.7%) is the denominator for SPED teacher ratios; mainstreamed (~93.3%) folds into GenEd; SPED baseline 2017-18 exempt from temporal rule.
- **Critical rules:** Docker required for DB; ≤3-year temporal span; never modify `data/raw/`; one-attempt rule on Cloudflare/WAF; **always verify counts in DB before trusting handoff docs**.
- **Canonical methodology docs:** `docs/METHODOLOGY.md`, `docs/SPED_SEGMENTATION_IMPLEMENTATION.md`, `CLAUDE.md`.

---

## 7. Data State at Pause (⚠️ ALL UNVERIFIED — confirm against live DB)

Reconstructed from on-disk artifacts/logs; per rule #6 these are **not** ground truth.

- **Jan 26 PM:** FastAPI up, serving `/enrich/extract` against local Ollama, shut down cleanly 19:51. Crawlee jobs ran (`data/jobs/<uuid>/`). Acquisition queue drained (`data/acquisition_queue/queue.json` empty).
- **`data/batch_pipeline_results.json`:** 10 processed, **5 succeeded / 5 failed** (all failures = "Extraction failed").
- **`data/retry_pipeline_results.json`:** 5 retried, **1 recovered** (Rapid City). Persistent failures: Denver (all-unknown grades → no records), New Haven & SF (0 extracted), Fresno (import error).
- **`data/enrichment_pipeline_test_results.md`:** self-reports **serious data-quality problems** — Sioux Falls elem "12:00–19:00", Rapid City identical middle/high times, Jeffco 480-min elem, Fresno flipped high→elem. Author's conclusion: **"Human review required before production use."**
- **`docs/UNENRICHED_DISTRICTS_REPORT.md`:** claims enriched count **52 → 66** (contradicts the caution above; unverified).
- **Working corpus:** `data/raw/bell_schedule_pdfs/` — ~64 district dirs across ~27 states.
- **Jan 27–31 (true last activity):** benchmark harness built + 6 hand-labeled `ground_truth.json` files (AK ×3, AL ×3) created through Jan 31; `data/benchmark_results/` empty. **This is where work stopped.**
- **DB backups:** newest usable is `2025-12-25 …194754.sql` (~6.2 MB); two backups are 0 bytes. Newest backup **predates all Jan acquisition work**.

---

## 8. Flagged Issues — Errors, Inconsistencies, Opportunities

> Documented, **not** addressed. Grouped by theme; severity is my estimate.

### A. Documentation drift (HIGH — first thing a returning dev hits)
1. **`CLAUDE.md` vs `Claude.md` are byte-identical duplicates** colliding on the case-insensitive macOS filesystem — a footgun (edits may hit the wrong one). *Opportunity: delete `Claude.md`.*
2. **Stale "what we have" docs** still describe the dead Firecrawl/Gemini/Playwright tier system as current: `docs/PROJECT_CONTEXT.md` ("What We Have"), `docs/claude-instructions/CLAUDE_CORE.md` & `CLAUDE_REFERENCE.md` (Playwright scraper), `README.md` (advertises "5-tier" + `--tier 2` example), `docs/GETTING_STARTED.md` (Playwright `npm run dev`). Code has **no** Firecrawl/Gemini/tier references remaining.
3. **`MULTI_TIER_ENRICHMENT_ARCHITECTURE.md` is misnamed** — it now documents the *opposite* of "multi-tier." High rediscovery risk. *Opportunity: rename to e.g. `ACQUISITION_PIPELINE.md` and fix cross-links.*
4. **"Tier" is overloaded** across three unrelated meanings — (a) acquisition tiers = OBSOLETE; (b) staffing-scope tiers in LCT = VALID; (c) state/data-quality tiers = VALID. Easy to conflate.
5. **The new extraction stage is undocumented** — `enrich.py`/`extraction_service.py`, the `data/jobs/`+`acquisition_queue/` state, and Ollama model management have no narrative doc.

### B. Data quality / trust (HIGH — blocks production use)
6. **Ollama extractions are unreliable** per the project's own Jan 26 results doc (wrong grades, implausible times, ~50% batch success). This is *the* open problem and the reason the benchmark harness was built.
7. **The benchmark never completed** — harness + ground truth exist, `benchmark_results/` empty. The accuracy question that paused the project is **unanswered**.
8. **Possible bad data in the DB** — `import_result.success: true` appears despite quality warnings; unclear whether implausible rows (e.g., Sioux Falls 12:00–19:00) reached `bell_schedules` or were cleaned up. *Needs DB check.*

### C. Pipeline seams / correctness (MEDIUM)
9. **Missing step-2 "Claude verification" script** — every pipeline header names a `verified_extraction.json` step, but **no script produces it**; it's a manual human gate. `run_batch_pipeline.py` silently skips it (extract → calc → delete → import), so batch runs have **no human gate** — exactly why bad data landed.
10. **Validation ranges disagree:** `calculate_minutes.py` validates 300–480 min; `pipeline_import_bell_schedules.py` validates 100–600 min. A record can be "invalid" to one and fine to the other.
11. **`run_batch_pipeline.py` deletes-then-imports** while the importer *also* has dedup/skip logic — the skip path is effectively dead inside batch flow; divergent assumptions.
12. **`queue_service.update_current_step()` is dead code** — `acquire.py` tracks step in an in-memory dict instead, so persisted `current.json` step is stale.
13. **In-memory acquisition status** — a FastAPI restart loses live status (queue itself is file-backed and survives).
14. **External dependency `~/.local/bin/ollama-serve-lowpri`** must exist or Ollama auto-start fails and *every* LLM call **silently degrades to heuristic fallback** — easy to miss because the pipeline still "succeeds."
15. **Ollama model-name drift** in `ollama_service.py` docstrings (`llama3:8b-instruct` vs actual `llama3.1:8b`, `phi-3-mini` vs `phi3:mini`). If the exact tags aren't pulled, calls silently fall back to heuristics.

### D. Database / migrations (MEDIUM)
16. **Two `014_` migrations** (`014_add_staff_scope_to_lct.sql`, `014_add_security_blocking.sql`) — numbering collision; touch disjoint tables (no data conflict) but ambiguous for any ordinal runner, and `015` depends on both.
17. **No migration ledger / version table** — migrations applied ad-hoc via per-file `apply_*.py`; "is 014/015 applied?" can only be answered by querying the live DB.
18. **`districts.is_shared_service_entity`** is used by the LCT engine (`calculate_lct_variants.py:423`) and exists in `models.py`, but **no SQL migration adds it** — could be absent if the DB was built from migrations rather than `create_all`. *Needs runtime check.*
19. **Stale data dictionary** — `docs/data-dictionaries/database_schema_latest.md` (gen. 2025-12-28) predates migrations 003–015; missing many tables/columns and shows the old LCT constraint. Use `models.py` instead.
20. **`schema.sql` obsolete** — its `data_tier` comment diverges from the engine's actual tiering.

### E. Dead / divergent code paths (MEDIUM)
21. **Two LCT code paths coexist:** legacy `queries.calculate_and_store_lct` (single-scope, per-grade rows, reads `districts.instructional_staff`) vs the modern variant engine (scope rows, `grade_level=NULL`, reads `staff_counts_effective`). Under the new unique constraint these write incompatible row shapes — confirm only the modern engine runs in production.
22. **`pipelines/full_pipeline.py` is broken/abandoned** — calls a non-existent `analyze/calculate_lct.py` (only `calculate_lct_variants.py` exists); predates the DB-first refactor. README still advertises it (`--tier 2`).
23. **Orphaned earlier-gen extractors** — `content_parser.py`, `extract_from_pdfs.py`, `google_drive_handler.py` still reference Firecrawl/Gemini and weren't pruned in the tier cleanup.

### F. Testing (HIGH — inverted coverage)
24. **The new acquisition pipeline has zero automated tests** — no test references Crawlee, Ollama, `extraction_service`, `queue_service`, the new scraper endpoints, or the FastAPI app. The most active subsystem is entirely unverified.
25. **Old scraper tests are broken/inert** — `test_scraper_resilience.py` / `test_scraper_security.py` import a **deleted** `fetch_bell_schedules.py` and target a `/scrape`-only server model that no longer matches `server.ts`; they silently `pytest.skip` without a live `:3000` service → false confidence.

### G. Version control / recoverability (MEDIUM)
26. **~2,000 lines uncommitted** across the API + scraper (a coherent, already-run feature set) plus many untracked files (benchmark scripts, enrich scripts, result artifacts). One bad `git checkout` would lose substantial working code. *Was the pause simply "before a commit"?*
27. **Newest DB backup predates all Jan work** (2025-12-25; two backups empty). Recent enrichment is not recoverable from backups if the live DB is lost.

---

## 9. Where Authoritative Info Lives (quick index)

| Need | Go to |
|---|---|
| New acquisition pipeline design | `docs/MULTI_TIER_ENRICHMENT_ARCHITECTURE.md` (misnamed but current) |
| LCT / SPED / data-year methodology | `docs/METHODOLOGY.md`, `docs/SPED_SEGMENTATION_IMPLEMENTATION.md`, `CLAUDE.md` |
| Authoritative DB schema | `infrastructure/database/models.py` (NOT `schema.sql` or the data dictionary) |
| LCT computation | `infrastructure/scripts/analyze/calculate_lct_variants.py` |
| Enrichment script flow | `infrastructure/scripts/enrich/` (5-step: regex/extract → calculate_minutes → import → verify) |
| Extraction "Phase 8/9" design | `~/.claude/plans/crispy-brewing-blanket.md` (external, unreviewed) |
| Workflow commands (current) | `docs/claude-instructions/CLAUDE_WORKFLOWS.md` |
| What was last attempted | `data/enrichment_pipeline_test_results.md`, `docs/UNENRICHED_DISTRICTS_REPORT.md` (both UNVERIFIED) |

---

## 10. Suggested Resume Questions (not actions)

1. **Is the uncommitted work meant to be committed?** It's coherent and was run — likely "paused before commit."
2. **Did the benchmark ever run, and what does the DB actually contain?** The accuracy question that paused the project is unanswered; enriched-count claims (52→66) are unverified.
3. **Did questionable Jan 26 extractions reach `bell_schedules`,** and do they need cleanup?
4. **Is the manual "Claude verification" gate intended to stay manual,** or be automated? Batch runs currently bypass it.
5. **Migration state:** are both 014s and 015 applied? Is `is_shared_service_entity` actually in the live schema?

---

*End of synthesis. This document records the current picture and known issues; it does not modify any code, data, or configuration.*
