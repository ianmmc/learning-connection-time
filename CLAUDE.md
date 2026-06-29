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

## Current Status (2026-06-29)

Building the **per-school acquisition pipeline** stage-by-stage with **human-in-the-loop checkpoints**. The GT/benchmark exploration concluded and was archived; the validated design is now the active build. Canonical pipeline doc: **`docs/ACQUISITION_PIPELINE.md`** (9 stages + failure-modes→checkpoints table + reader-routing spec). Live code: **`infrastructure/acquisition/`** (promoted out of the retired `scripts/benchmark/`). Council research: `docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`. Leaderboard/costs: `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.

**Build progress (2026-06-28):** Stages **1–4 built + run live** on `batch_00001` (each with a code-verified `STAGE*_DESIGN_*.md` note); **Stage 5 CONCLUDED** (review/label app + signals + de-chrome + clustering + labeled topology + tuning loop + the **event-driven `filtered.json` release generator**). Governance/state/Postgres **BUILT**: REQ-098 (installable package — **`pip install -e .`**), REQ-103 (isolated `governance` Postgres + cross-stage cache), REQ-099 (`state_event` log + `current_state` view), REQ-094 (event-driven `filtered.json`). **The console build is underway — gate@1 FULLY built (REQ-102), backend + frontend:** the batch is a **first-class entity in the governance DB (the working store)** — normalized PRECIOUS tables `batch`/`batch_district`/`batch_school`, with `batch_NNNNN.json` regenerated from the rows as the (gitignored, regenerable) **receipt**; gate@1 is an **in-band batch-level approval** with soft/reversible/audited editing; the **queue-review UI** (first console stage view, on the **MMM Design System** via the **DesignSync** tool) is live. **`batch_00002` created → edited → approved through the console** (the forcing-function milestone). **Stage 2 (Discover) then re-architected to a deterministic SERP cascade + the Stage-2 console view BUILT + RUN LIVE (REQ-104, 2026-06-28):** **Wave 1 = Bright Data SERP** (real Google, recurring-free, 98% recall) + **Serper failover** on API failure → **Wave 2 = Claude WebSearch** on the residual (different index, speculative). `batch_00002` (Bright Data found 28/30 schools) + `batch_00003` both ran end-to-end through the UI. **Stage 3 (Capture) console BUILT + RUN LIVE + HARDENED (REQ-110, 2026-06-28/29)** on batch_00002–00005: per-district Node-Playwright run trigger + a health/emergent readout reading the **DB cross-stage cache** (which graduated to a *live working store* — schema + per-district UPSERTs in `common/cache_ingest.py`, each stage's finish hook keeps it fresh; Stage 2's console repointed to it too). Hardenings: no-link districts skip Playwright; failures/timeouts surface + are retriable; shared status labels + honest left-pane progress (`static/outcomes.js`, "0/10 captured · 2 no-links"); **node-owns-shutdown** (a capture timeout writes a PARTIAL manifest → `captured_partial`, never orphans work) + **`capture_stage3 reconstruct`** (rebuild a manifest from on-disk folders for already-orphaned districts; also the interim manual-follow-up path — recovered Brookwood/Fairfield/LAS CRUCES + folded in a hand-downloaded handbook PDF). Read-first authority: **`STAGE3_CAPTURE_DESIGN_2026-06.md` §7** (Stage 3 console + resilience), **`STAGE2_DISCOVER_DESIGN_2026-06.md` §7** (SERP cascade) + **`PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`** (§7a, §11/§11h); slim *map* = `ACQUISITION_PIPELINE.md`; history → `PROJECT_HISTORY.md`.

**Metric = GROSS bell-to-bell minutes (end − start), NOT net.** No lunch/passing/recess deduction, no *assumed* deductions. Existing GT is already gross; gross needs only two reliably-published numbers (↑accuracy). Net is a deferred enhancement. Labeled `gross_bell_to_bell`. Plausibility gate 240–510 min. (REQ-055; supersedes net in REQ-042/046.)

**INVARIANT — extractors read TIMES; deterministic code computes MINUTES + the MODE.** Council models return only per-school `{start_time,end_time,grade_level,school_name}` facts; Python does `gross=end−start` and the per-band exact-mode. Never ask a model to compute minutes or pick a "typical" schedule. (REQ-054.)

**Extraction = COUNCIL (correctness); Discovery = WAVES (recall).** Council: **consensus is on the per-school (start,end) pair, cross-family, ±15 min** — same-family agreement is NOT consensus (REQ-056). Candidate set = 6 non-reasoning models (Gemini 2.5 Flash, Mistral Large 2512, DeepSeek V3.2, Mistral Small 24B, Gemini 2.5 Flash-Lite, Qwen3-235B-2507); Grok 4.3 & Qwen3.7-Max **removed** (reasoning-token cost 4–70×). **Open: exact council composition** — Path-1 cheap-trio vs Path-2 accuracy-pair vs Path-1-minus-Mistral, decided by measured escalation rate. Discovery (re-architected 2026-06-28, REQ-104; design note §7) = a **deterministic SERP cascade**, NOT agent waves: **Wave 1 = Bright Data SERP** (real Google, `site:`-scoped, recurring-free) + **Serper failover** on API failure (same index = uptime backup) → **Wave 2 = Claude WebSearch** on the residual (a *different* index, speculative). Decided by a measured 5-provider bake-off (`data/acquisition/diagnostics/`): **the index predicts recall** — raw Google wins (Bright Data 98% / Serper 100%), own-index Perplexity craters (43%, zero long-tail coverage). Retired: Claude-as-Wave-1 (66%), OpenRouter ($27/1K), Perplexity.

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()`+`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 **vision** (Gemini Flash / Mistral Large read JS/image/scan pages all text paths miss — proven). Trigger is "did the cheap reader recover usable content," not format. (Tier-1→2 structure-loss trigger is the one OPEN gate.)

**Ground truth re-established by hand (gross, per-school).** `data/benchmark/gt_curation_*/gt_proposals.json` — **940/943 schools human-verified** (per-school start/end). Pending: fold into a new gross GT manifest. Process: council *proposes*, human *verifies* (REQ-059). Failure-mode taxonomy (8 modes → checkpoints) in `ACQUISITION_PIPELINE.md`.

**Human-in-the-loop gates (stage-numbered, 2026-06-27; governance §11) = 5:** **gate@1** Queue (right districts/schools/bands), **gate@5** Filter (per-URL representation review — the critical gate), **gate@6** Handoff (which reps → which council config), **gate@7** Extract (review council requests), **gate@8** Aggregate (per-band results correct + honestly labeled — the effective old "CP-C"; Stage 9 then auto-writes). Stages 2/3/4 + the Stage-9 write are ungated. Each gate is manual/auto (Settings: global default + per-gate overrides; auto is confidence-escalating). Loosen later once confident.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Granite 4.1 8B = self-host candidate (headless Ubuntu server, separate project). Keys in gitignored `config/secrets.local.json` + `.env`. Requirements: **REQ-001…109** (042/046/048/057 superseded; 028–031/033 retired with the Crawlee era). Restore point for the archived GT/benchmark exercise: git tag `gt-exercise-complete`.

> **SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

### Next session (RESUME HERE — 2026-06-29)
**Console stage views gate@1 (REQ-102) + Stage 2 (REQ-104) + Stage 3 (REQ-110) are DONE + run live on
batch_00002–00005.** The console reads the **DB cross-stage cache** (live working store, `common/cache_ingest.py`;
each stage's finish hook keeps it fresh); the batch is resolved from the DB working store, not the receipt.
Shared UI: `static/outcomes.js` (`outcomeBadge` + `progressBadge`) drives per-district labels + left-pane
progress for Stage 2/3 (and Stage 4 next). Stage 3 capture is resilient: **node-owns-shutdown** (Node writes a
PARTIAL `captures.json` on its own deadline → `captured_partial`; Python's subprocess timeout is a backstop)
+ `capture_stage3 reconstruct` recovery/manual-add.

**→ NEXT: build the Stage 4 (Process) console view.** It's the simplest stage view — **copy Stage 3**. The
scaffolding is already stage-agnostic + in place: Stage 4's finish hook upserts `processed_doc`;
`list_batches.progress.processed` + `progressBadge("stage4")` + `outcomes.js` `processed_*` labels exist.
Build `stage4_process/headless.py` (mirror `stage3_capture/headless.py` — but Stage 4 runs IN-PROCESS, so
**no node-owns-shutdown to design**), `/api/process/*` in `server.py`, `static/stage4.js` + the `index.html`
selector + `gate1.js` switcher hook. **Full forward spec: `STAGE4_PROCESS_DESIGN_2026-06.md` §4a.** After
Stage 4: REQ-100 (staleness) / REQ-101 (Stage 6 + gate@6; scope ends at gate@6 approval — no paid dispatch).

**Fresh-session essentials:** `/catchup` → `pip install -e .` → **Docker up** → `lint-imports` (3 kept/0
broken) + `pytest -q -m "not integration"` (**576 pass**; resource-dependent tests are `integration`-marked,
excluded in CI). Launch the console **from the repo root**:
`python3 -m infrastructure.acquisition.process_governance.server` (→ :8005). **Console changes are JS+Python:
reload the browser for `static/*.js`; restart the server for Python.** Stage 2 needs SERP keys in gitignored
`config/secrets.local.json`: `BRIGHTDATA_API_KEY` + `BRIGHTDATA_SERP_ZONE` (a **SERP-API** zone), `SERPER_API_KEY`
(+ OPENROUTER/PERPLEXITY/GEMINI). `claude -p` (Stage 2 Wave 2) is **blocked inside a Claude Code session**
(CLAUDECODE set) — runs from a plain terminal / the launched server. Rebuild Stage-5 cache:
`python3 -m infrastructure.acquisition.stage5_filter.build_signals`. **Recover an orphaned capture:**
`python3 -m infrastructure.acquisition.stage3_capture.capture_stage3 reconstruct <district_id>`.
**UI design:** MMM Design System via `DesignSync`. **Caveat:** static JS has **no lint/`no-undef` gate** —
diff `static/*.js` carefully; `node --check` catches syntax only.

**Registered REQ#s:** **REQ-102** gate@1, **REQ-104** Stage 2 SERP+console, **REQ-110** Stage 3 console +
capture resilience — all **DONE**. **REQ-100** staleness (after Stage 4 console), **REQ-101** Stage 6 + gate@6
(OPEN #1 = council-config grain). Batch receipts (`batch_*.json`) + `data/raw/` captures are
gitignored/regenerable; git-durable state backup = `data/acquisition/status/district_status.json`.

**Watch-items (not blockers):** (a) **partial-retry** — a `captured_partial`/recovered district has a
captures.json so reconcile treats it done; its `not_attempted`/`not_recovered` candidates don't auto-retry
(a reconcile enhancement); (b) capture **politeness/rate-limiting** — the 5-concurrent burst likely caused the
Brookwood transient stall (consider a small delay / lower per-district concurrency); (c) **Claude Wave-2 earns
its keep** — batch_00005 recovered a page Google missed (first live YES; watch the pattern); (d) obsolete
skills `.claude/skills/per-school-acquire*` + `stage2-discover`; (e) GETTING_STARTED's stale "Run Scraper
Service" task / DATA_SOURCES dangling refs.

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
