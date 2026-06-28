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

## Current Status (2026-06-27)

Building the **per-school acquisition pipeline** stage-by-stage with **human-in-the-loop checkpoints**. The GT/benchmark exploration concluded and was archived; the validated design is now the active build. Canonical pipeline doc: **`docs/ACQUISITION_PIPELINE.md`** (9 stages + failure-modes→checkpoints table + reader-routing spec). Live code: **`infrastructure/acquisition/`** (promoted out of the retired `scripts/benchmark/`). Council research: `docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`. Leaderboard/costs: `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.

**Build progress (2026-06-27):** Stages **1–4 built + run live** on `batch_00001` (each with a code-verified `STAGE*_DESIGN_*.md` note); **Stage 5 CONCLUDED** (review/label app + signals + de-chrome + clustering + labeled topology + tuning loop + the **event-driven `filtered.json` release generator**). Governance/state/Postgres **BUILT**: REQ-098 (installable package — **`pip install -e .`**), REQ-103 (isolated `governance` Postgres + cross-stage cache), REQ-099 (`state_event` log + `current_state` view), REQ-094 (event-driven `filtered.json`). **The console build has STARTED — gate@1 BACKEND built (REQ-102):** the batch is now a **first-class entity in the governance DB (the working store)** — normalized PRECIOUS tables `batch`/`batch_district`/`batch_school`, with `batch_NNNNN.json` regenerated from the rows as the **receipt**; gate@1 is an **in-band batch-level approval** with soft+audited editing; 7 console endpoints + `build_batch()`/`persist_batch()`. Read-first authority: **`PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`** (§11 gates/console, §11h gate@1 build) + the per-stage `STAGE*_DESIGN_*.md` (Stage 1 = §6 for the working store); slim *map* = `ACQUISITION_PIPELINE.md`; history → `PROJECT_HISTORY.md`.

**Metric = GROSS bell-to-bell minutes (end − start), NOT net.** No lunch/passing/recess deduction, no *assumed* deductions. Existing GT is already gross; gross needs only two reliably-published numbers (↑accuracy). Net is a deferred enhancement. Labeled `gross_bell_to_bell`. Plausibility gate 240–510 min. (REQ-055; supersedes net in REQ-042/046.)

**INVARIANT — extractors read TIMES; deterministic code computes MINUTES + the MODE.** Council models return only per-school `{start_time,end_time,grade_level,school_name}` facts; Python does `gross=end−start` and the per-band exact-mode. Never ask a model to compute minutes or pick a "typical" schedule. (REQ-054.)

**Extraction = COUNCIL (correctness); Discovery = WAVES (recall).** Council: **consensus is on the per-school (start,end) pair, cross-family, ±15 min** — same-family agreement is NOT consensus (REQ-056). Candidate set = 6 non-reasoning models (Gemini 2.5 Flash, Mistral Large 2512, DeepSeek V3.2, Mistral Small 24B, Gemini 2.5 Flash-Lite, Qwen3-235B-2507); Grok 4.3 & Qwen3.7-Max **removed** (reasoning-token cost 4–70×). **Open: exact council composition** — Path-1 cheap-trio vs Path-2 accuracy-pair vs Path-1-minus-Mistral, decided by measured escalation rate. Discovery waves: **Claude WebSearch (Haiku subagent) → OpenRouter `gpt-4o-mini-search` → flag manual; Perplexity dropped.** Domain-scoped; ~90% page-find on full-41.

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()`+`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 **vision** (Gemini Flash / Mistral Large read JS/image/scan pages all text paths miss — proven). Trigger is "did the cheap reader recover usable content," not format. (Tier-1→2 structure-loss trigger is the one OPEN gate.)

**Ground truth re-established by hand (gross, per-school).** `data/benchmark/gt_curation_*/gt_proposals.json` — **940/943 schools human-verified** (per-school start/end). Pending: fold into a new gross GT manifest. Process: council *proposes*, human *verifies* (REQ-059). Failure-mode taxonomy (8 modes → checkpoints) in `ACQUISITION_PIPELINE.md`.

**Human-in-the-loop gates (stage-numbered, 2026-06-27; governance §11) = 5:** **gate@1** Queue (right districts/schools/bands), **gate@5** Filter (per-URL representation review — the critical gate), **gate@6** Handoff (which reps → which council config), **gate@7** Extract (review council requests), **gate@8** Aggregate (per-band results correct + honestly labeled — the effective old "CP-C"; Stage 9 then auto-writes). Stages 2/3/4 + the Stage-9 write are ungated. Each gate is manual/auto (Settings: global default + per-gate overrides; auto is confidence-escalating). Loosen later once confident.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Granite 4.1 8B = self-host candidate (headless Ubuntu server, separate project). Keys in gitignored `config/secrets.local.json` + `.env`. Requirements: **REQ-001…109** (042/046/048/057 superseded; 028–031/033 retired with the Crawlee era). Restore point for the archived GT/benchmark exercise: git tag `gt-exercise-complete`.

> **SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

### Next session (RESUME HERE — 2026-06-27)
**The console build has started; gate@1 BACKEND is built (REQ-102).** The batch is now a first-class entity
in the governance DB (the working store: `batch`/`batch_district`/`batch_school`, PRECIOUS), with
`batch_NNNNN.json` regenerated from the rows as the receipt. gate@1 = an in-band **batch-level** approval
(`batch.status: draft → approved` + per-district `gate@1` events); editing is **soft + audited** (reject
district/school, add school; locked once approved, `reopen` to edit). Code: `stage1_queue/{queue_batch
(build_batch/persist_batch), batch_store, models}.py` + the `/api/queue/*` endpoints in
`process_governance/server.py`. Detail: `STAGE1_QUEUE_DESIGN_2026-06.md` §6 + governance §11h. The Stages
1–4 design notes + the 5-doc sync are done.

**→ NEXT: the gate@1 FRONTEND (step 3).** Build the queue view in `process_governance/static/`: a **stage
selector** (the wordmark — gate@1 queue ↔ the existing Stage-5 review), the **batch list**, a **Create
batch** button **with a loading/progress affordance** (create is synchronous, ~10–20s — the user asked for
this), the **district→band→school tree** (denominators + `n_*` counts + `included` flags), the **edit
controls** (reject district/school, add school via `GET …/district/{did}/candidates`), and **Approve/Reopen**.
**Then create `batch_00002` THROUGH the console** (the forcing-function milestone — never via scripts for the
batch-of-record; hand-run `queue_batch.py` = dev/test only). After that, walk batch_00002 stage-by-stage,
building each view; then REQ-100 (staleness) / REQ-101 (Stage 6 + gate@6). **Scope ends at gate@6 approval —
no paid dispatch.**

**Fresh-session essentials:** `/catchup` → `pip install -e .` → **Docker up** → `lint-imports` (3 kept/0
broken) + `pytest -q` (governance-DB tests skip without Docker). Launch the console:
`python3 -m infrastructure.acquisition.process_governance.server` (→ :8005). Rebuild the Stage-5 governance
cache + `filtered.json`: `python3 -m infrastructure.acquisition.stage5_filter.build_signals`. The batch
working store is created by `gdb.init_precious_schema()` (server does this at startup). Tests:
`tests/test_stage1_batch_store.py` (working store) + `tests/test_gate1_api.py` (endpoints). **Checkpoint at
session end with `/checkpoint`.**

**Registered REQ#s** (status `accepted`): **REQ-102** gate@1 (backend done; frontend next), **REQ-100**
staleness view, **REQ-101** Stage 6 handoff + gate@6 (OPEN #1 = council-config grain), **REQ-104** Stage 2
headless. Currency/recency = **REQ-044** (a Stage-5 enhancement, NOT REQ-104).

**Watch-items:** (a) docs rationalization not-yet-done: GETTING_STARTED's stale "Run Scraper Service" task
(retired Express :3000), DATA_SOURCES dangling `data-dictionaries/` refs, `docs/technical-notes/refactor-20260123/`
(obsolete); (b) `.claude/skills/per-school-acquire*` skills are stale — not the runbook; (c) `create` is
synchronous (heavy full-NCES draw) — fine for now, revisit if it becomes a UX problem.

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
