# Claude Code Project Briefing: Learning Connection Time

## Project Mission

Transform student-to-teacher ratios into "Learning Connection Time" (LCT) metrics that tell the story of students getting shortchanged.

**Core Formula:**
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example:** 5,000 students, 250 teachers, 360 min/day → LCT = 18 min/student/day

**Goal:** Analyze data from the largest U.S. school districts to identify educational equity disparities.

---

## Project Context

Part of "Reducing the Ratio" educational equity initiative. Currently implementing **Phase 1.5**: enriching basic LCT with actual bell schedules from district websites.

**Known Limitations:** Individualization fallacy, time-as-quality assumption, averaging deception. See `docs/METHODOLOGY.md`.

---

## Current Status (2026-06-30)

Building the **per-school acquisition pipeline** stage-by-stage with **human-in-the-loop checkpoints**. The GT/benchmark exploration concluded and was archived; the validated design is now the active build. Canonical pipeline doc: **`docs/ACQUISITION_PIPELINE.md`** (9 stages + failure-modes→checkpoints table + reader-routing spec). Live code: **`infrastructure/acquisition/`** (promoted out of the retired `scripts/benchmark/`). Council research: `docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`. Leaderboard/costs: `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.

**Build progress (2026-06-29):** The console is **stage-selectable and built through Stage 5; the whole pipeline runs console-driven.** The governance re-architecture is complete (REQ-098 installable package — **`pip install -e .`**; REQ-103 isolated `governance` Postgres + cross-stage cache; REQ-099 `state_event` log + `current_state` view; REQ-094 event-driven `filtered.json`). Console stage views, all BUILT + run live on batch_00002–00007: **gate@1** queue (REQ-102), **Stage 2** deterministic SERP cascade (REQ-104), **Stage 3** capture + resilience (REQ-110), **Stage 4** process + the **Stage 4→5 incremental handoff** (REQ-111), and the **Stage 5 rework — district-driven, attention-first** (REQ-112). The architecture is settled: **the DB is the working store** (`common/cache_ingest.py` live cross-stage cache + the Stage-5 signal tables on the incremental `ingest_batch` path), **JSON files are receipts** (regenerable, for state-confirmation + district-level human inspection); the batch is a first-class PRECIOUS DB entity that **dissolves at the Stage 4→5 seam** (Stage 5 is district-driven on purpose). **Stage 6 (routing/release) is now BUILT to the Stage 6→7 seam (REQ-101, merged PR #2, 2026-06-30)** — the `stage6_handoff/` package + the **gate@6** console (preview routed/priced package → Approve & freeze) → immutable `handoff_<hash>_<ts>.json` + a precious `handoff` index row + a `dispatched` state_event; **stops before the paid call** (Stage 7). The standalone flow diagram was retired into the map (`ACQUISITION_PIPELINE.md` § Flow diagram). Authority: per-stage `STAGE*_DESIGN_*.md` (Stage 5 = §A–D, **Stage 6 = §0 as-built**) + `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` (§11 gates, §12 the seam); map = `ACQUISITION_PIPELINE.md`; decisions = `PROJECT_HISTORY.md`.

**Metric = GROSS bell-to-bell minutes (end − start), NOT net.** No lunch/passing/recess deduction, no *assumed* deductions. Existing GT is already gross; gross needs only two reliably-published numbers (↑accuracy). Net is a deferred enhancement. Labeled `gross_bell_to_bell`. Plausibility gate 240–510 min. (REQ-055; supersedes net in REQ-042/046.)

**INVARIANT — extractors read TIMES; deterministic code computes MINUTES + the MODE.** Council models return only per-school `{start_time,end_time,grade_level,school_name}` facts; Python does `gross=end−start` and the per-band exact-mode. Never ask a model to compute minutes or pick a "typical" schedule. (REQ-054.)

**Extraction = COUNCIL (correctness); Discovery = WAVES (recall).** Council: **consensus is on the per-school (start,end) pair, cross-family, ±15 min** — same-family agreement is NOT consensus (REQ-056). Candidate set = 6 non-reasoning models (Gemini 2.5 Flash, Mistral Large 2512, DeepSeek V3.2, Mistral Small 24B, Gemini 2.5 Flash-Lite, Qwen3-235B-2507); Grok 4.3 & Qwen3.7-Max **removed** (reasoning-token cost 4–70×). **Council template DECIDED (Stage 6): 2 cross-family voters → a 3rd-family judge** on disagreement (pair+judge cascade; judge>voter) — enforced in `councils.validate()`; seeds `low-cost-text`/`image`. **Composition (which models) is deferred to the council lab** (`cost_benchmark`, re-benchmarked on clean data), NOT guessed (the old Path-1/2 question collapsed into the template). Discovery (re-architected 2026-06-28, REQ-104; design note §7) = a **deterministic SERP cascade**, NOT agent waves: **Wave 1 = Bright Data SERP** (real Google, `site:`-scoped, recurring-free) + **Serper failover** on API failure (same index = uptime backup) → **Wave 2 = Claude WebSearch** on the residual (a *different* index, speculative). Decided by a measured 5-provider bake-off (`data/acquisition/diagnostics/`): **the index predicts recall** — raw Google wins (Bright Data 98% / Serper 100%), own-index Perplexity craters (43%, zero long-tail coverage). Retired: Claude-as-Wave-1 (66%), OpenRouter ($27/1K), Perplexity.

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()`+`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 **vision** (Gemini Flash / Mistral Large read JS/image/scan pages all text paths miss — proven). Trigger is "did the cheap reader recover usable content," not format. (Tier-1→2 structure-loss trigger is the one OPEN gate.)

**Ground truth re-established by hand (gross, per-school).** `data/benchmark/gt_curation_*/gt_proposals.json` — **940/943 schools human-verified** (per-school start/end). Pending: fold into a new gross GT manifest. Process: council *proposes*, human *verifies* (REQ-059). Failure-mode taxonomy (8 modes → checkpoints) in `ACQUISITION_PIPELINE.md`.

**Human-in-the-loop gates (stage-numbered, 2026-06-27; governance §11) = 5:** **gate@1** Queue (right districts/schools/bands), **gate@5** Filter (per-URL representation review — the critical gate), **gate@6** Handoff (which reps → which council config), **gate@7** Extract (review council requests), **gate@8** Aggregate (per-band results correct + honestly labeled — the effective old "CP-C"; Stage 9 then auto-writes). Stages 2/3/4 + the Stage-9 write are ungated. Each gate is manual/auto (Settings: global default + per-gate overrides; auto is confidence-escalating). Loosen later once confident.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Granite 4.1 8B = self-host candidate (headless Ubuntu server, separate project). Keys in gitignored `config/secrets.local.json` + `.env`. Requirements: **REQ-001…112** (042/046/048/057 superseded; 028–031/033 retired with the Crawlee era). Restore point for the archived GT/benchmark exercise: git tag `gt-exercise-complete`.

> **SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

### Next session (RESUME HERE — 2026-06-30)
**Stage 6 (routing/release) is BUILT to the Stage 6→7 seam and MERGED to main** (PR #2, `5f05d31`; docs
brought to as-built + the flow diagram retired into the map, `2200f48`). The `stage6_handoff/` package
(councils/routing/cost/package/handoff/models/prompts/requests — all pure, `common`-only) + the app-layer
bridge (`process_governance/stage6_dispatch.py`) + the **gate@6 console** (`static/stage6.js` +
`/api/handoff/*`): pick send-eligible districts → preview the routed/priced package → **Approve & freeze**
→ immutable `handoff_<hash>_<ts>.json` + a precious `handoff` index row + a `dispatched` state_event (atomic,
file written last) → OpenRouter requests assembled — **STOP before the paid call.** Council template = 2
cross-family voters → 3rd-family judge (validated in `councils.validate()`); routing is per-rep, data-driven
off each config's `input_kinds` + the capture-fidelity gate; cost = a labeled **bootstrap** model. Authority:
`STAGE6_HANDOFF_DESIGN_2026-06.md` **§0** (as-built code map).

**→ NEXT (pick one): the council lab first, OR Stage 7.** READ FIRST: `STAGE6_HANDOFF_DESIGN` §0 (what's
built) + §3C (the lab) + §3F (the "request more evidence" loop + the OpenRouter-session question — a Stage 7
concern) + the `PROJECT_HISTORY.md` Stage 6 entry (the two-layers / tokens×live-price reframe) +
`LLM_COUNCIL_RESEARCH_2026-06.md`.
- **Council lab** (`cost_benchmark`, DESIGNED not built, §3C): run candidate models over current clean reps,
  record OpenRouter token+cost telemetry, fit a per-model TOKEN model → rewrite `council_cost_model.json` as
  `provenance:"measured"`; **pricing is fetched LIVE from OpenRouter `/api/v1/models`** (a separate cache), NOT
  in the token model. Same harness re-benchmarks council COMPOSITION. Cost-only needs no GT; accuracy/composition
  must first ALIGN the prior GT into the pipeline (a big `batch_00000` — `gt_curation` has ZERO overlap with the
  current 59-district set). Ian's call: lower out-of-pocket by measuring, don't guess.
- **Stage 7** = the paid POST + the judge-on-disagreement loop + the request-more-evidence back-edges (7→6 / 7→1),
  cost-gated by the budget governor (REQ-051).
- Also open: REQ-100 (staleness), **gate@6 auto mode** (console does manual approve today), REQ-044 (recency).
- **Cadence: stage-sized work on a branch → PR** (Stage 6 was PR #2; draft-PR early for CI per push).

**Fresh-session essentials:** `/catchup` → `pip install -e .` → **Docker up** → `lint-imports` (3 kept/0
broken) + `pytest -q -m "not integration"` (**~654 pass**; resource-dependent tests are `integration`-marked).
**CI = two jobs** (`.github/workflows/test.yml`): the DB-free suite + **`governance-db`** (`pytest -m govdb`
against a Postgres service container — Stage 6 added a `handoff`-insert + a `/api/handoff` read there). Launch
from the repo root: `python3 -m infrastructure.acquisition.process_governance.server` (→ :8005); the
**Stage 6 · Handoff (gate@6)** view is in the stage selector (Stage 5 is the default). **Console changes are
JS+Python: reload the browser for `static/*.js`, restart the server for Python.** **Self-verify UI with
Playwright before shipping visuals** (python playwright isn't installed — drive the Node one in
`infrastructure/scraper/node_modules`: set `#stageSelect`=stage6, wait `#s6-list .s6-cand`, screenshot). The
council-config + cost-model knobs live in `common/config/council_configs.json` + `council_cost_model.json`
(config-as-data). Stage 2 SERP keys + the `claude -p` "blocked inside a Claude Code session" caveat unchanged.

**Precious state + backups:** `label`/`cluster_split`/`followup_flag` + the new **`handoff`** index row
(governance DB); the immutable `handoff_<hash>_<ts>.json` files under `data/acquisition/handoffs/` are the
dispatch records. `saved_view` (DB; UI prefs). The tracked **`.githooks/pre-commit`** sweeps `labels.json` +
`district_status.json` into every commit — on a fresh clone run `git config core.hooksPath .githooks`
(GETTING_STARTED §1b). Stage 4 needs system binaries poppler/tesseract/ghostscript (GETTING_STARTED §1a).

**Registered REQ#s:** REQ-001…112. **DONE this session:** REQ-101 (Stage 6 + gate@6, to the seam, merged PR #2).
**OPEN/next:** the **council lab** (`cost_benchmark`) + **Stage 7**; REQ-100 (staleness), gate@6 auto, REQ-044
(recency). **Deferred (with reason):** the lab is *designed not run* (§3C — do it when prepping Stage 7
composition / to replace the bootstrap cost model); the **ML on-ramp** (sklearn on the attention weights at
scale); the **"District Investigator"** holistic view; the harness **attention-ordering metric**; NCES
**locale** facet (needs an EDGE file).
---

## Current Data Years

**Current School Year:** 2025-26

### Data Year Strategy

| Data Type | Year | Notes |
|-----------|------|-------|
| Primary dataset | 2023-24 | NCES CCD enrollment/staffing |
| Bell schedules | 2025-26, 2024-25, 2023-24 | Any acceptable, search current first |
| COVID exclusion | 2019-20 through 2022-23 | Never use - abnormal schedules |

**Search Order:** 2025-26 → 2024-25 → 2023-24 (all post-COVID, interchangeable)


---

## Database Quick Reference

```bash
# Bell schedule count (source of truth)
python3 -c "
from infrastructure.database.connection import session_scope
from sqlalchemy import text
with session_scope() as s:
    print(s.execute(text('SELECT COUNT(DISTINCT district_id) FROM bell_schedules')).scalar())
"

# Query enrichment status
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report
with session_scope() as session:
    print_enrichment_report(session)
"
```

**Key Tables:** `districts`, `bell_schedules`, `state_requirements`, `lct_calculations`, `state_district_crosswalk`

---

## Essential Commands

```bash
# Calculate LCT (recommended)
python3 infrastructure/scripts/analyze/calculate_lct_variants.py

# Interactive enrichment
python3 infrastructure/scripts/enrich/interactive_enrichment.py --state WI

# Run SEA integration tests
pytest tests/test_*_integration.py -v

# VERIFICATION - Run after enrichment!
python3 infrastructure/scripts/verify_enrichment.py --quick
```

### Architecture & code-exploration tools (use these to read/verify the codebase — REQ-098)
These are installed (dev-deps) and are the project's standard way to map dependencies and enforce
layering — reach for them before writing or verifying any "what depends on what" narrative:
```bash
lint-imports                 # enforce the acquisition layering contracts (.importlinter); expect "3 kept, 0 broken"
python3 -c "import grimp; g=grimp.build_graph('infrastructure'); \
  print(sorted(g.find_modules_directly_imported_by('infrastructure.acquisition.stage1_queue.queue_batch')))"
                             # grimp: query the real import graph (what a module imports / is imported by)
vulture infrastructure/acquisition    # dead-code sweep
cd infrastructure/scraper && npx depcruise --config .dependency-cruiser.cjs lib   # Node (.mjs) side
```
> **Caveat (the recurring lesson):** these see **Python/Node imports only**. They do NOT see the
> *environmental* dependencies that often matter most — NCES CSV files read by path/year, **LCT DB
> tables** accessed via the ORM, `subprocess`/`claude -p` calls, OpenRouter API hosts. After the import
> graph, **read the code** for those edges. (Toolchain rationale: `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §10.)

#### Design System for frontend/UI via DesignSync
To access current design resources, use the claude_design MCP (https://api.anthropic.com/v1/design/mcp, auth via /design-login) to import this project: https://claude.ai/design/p/07ef80cc-f2fe-4393-945e-99f1a40b0809

---

## Key Files

| Task | File |
|------|------|
| **Acquisition pipeline (canonical)** | `docs/ACQUISITION_PIPELINE.md` |
| **Live pipeline code** | `infrastructure/acquisition/` (discovery/, council, aggregate, extractors) |
| Extraction leaderboard + costs | `docs/EXTRACTION_BENCHMARK_FINDINGS.md` |
| Council design research | `docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md` |
| Decisions, lessons, system map & latent issues | `docs/PROJECT_HISTORY.md` (Part 5 = map + open flags) |
| Data methodology | `docs/METHODOLOGY.md` |
| Database setup | `docs/DATABASE_SETUP.md` |
| SEA integration guide | `docs/SEA_INTEGRATION_GUIDE.md` |
| LCT calculation | `infrastructure/scripts/analyze/calculate_lct_variants.py` |
| Database migrations + ledger | `infrastructure/database/migrations/` (`migrate.py status`) |
| Database queries | `infrastructure/database/queries.py` |

---

## Load Additional Context When Needed

This is the core briefing. Load the right doc for the task (the old `docs/claude-instructions/` appendix
system was archived 2026-06-27 — superseded by these current homes):

| Context Needed | Load File |
|----------------|-----------|
| Decisions, lessons, history | `docs/PROJECT_HISTORY.md` |
| Dev setup, workflow, testing, commands, conventions | `docs/GETTING_STARTED.md` |
| Database setup + schema | `docs/DATABASE_SETUP.md` (schema authority = `infrastructure/database/models.py`) |
| Data sources, SEA integrations, ID crosswalks, complex districts | `docs/DATA_SOURCES.md` · `docs/SEA_INTEGRATION_GUIDE.md` |
| Data methodology (LCT, sampling, exclusions, temporal) | `docs/METHODOLOGY.md` |
| The acquisition pipeline + per-stage design notes | `docs/ACQUISITION_PIPELINE.md` (map) → `docs/technical-notes/STAGE*_DESIGN_*.md` |
| Governance / state model / gate model / console | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` |

**Token Efficiency:** load only what the task needs.

---

## Critical Rules

1. **Docker Required**: Always use `docker-compose up -d` before database operations. Never use `brew services start postgresql` - the `.env` is configured for Docker's PostgreSQL container.
2. **COVID Data Exclusion**: Never use 2019-20 through 2022-23 data
3. **Security Blocks**: ONE-attempt rule for Cloudflare/WAF-protected districts
4. **Temporal Validation**: Data from multiple sources must span ≤3 years
5. **Raw Data**: Never modify files in `data/raw/`
6. **Data Verification**: ALWAYS verify data exists in database before claiming enrichment counts. Never trust handoff documentation without database verification.

---

## Technical Reference

- **Crosswalk table**: `state_district_crosswalk` - single source of truth for all state mappings
- **SPED baseline**: 2017-18 IDEA 618/CRDC exempt from temporal rule
- **Acquisition pipeline**: the stage-based per-school pipeline in `infrastructure/acquisition/` — see `docs/ACQUISITION_PIPELINE.md` (the retired Crawlee+Ollama API/scraper was archived 2026-06-25 to `data/archive/crawlee-ollama-era-superseded-20260625/`)

For detailed reference, load the appropriate appendix above.
