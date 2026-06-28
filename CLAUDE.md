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

## Current Status (2026-06-28)

Building the **per-school acquisition pipeline** stage-by-stage with **human-in-the-loop checkpoints**. The GT/benchmark exploration concluded and was archived; the validated design is now the active build. Canonical pipeline doc: **`docs/ACQUISITION_PIPELINE.md`** (9 stages + failure-modes→checkpoints table + reader-routing spec). Live code: **`infrastructure/acquisition/`** (promoted out of the retired `scripts/benchmark/`). Council research: `docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`. Leaderboard/costs: `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.

**Build progress (2026-06-28):** Stages **1–4 built + run live** on `batch_00001` (each with a code-verified `STAGE*_DESIGN_*.md` note); **Stage 5 CONCLUDED** (review/label app + signals + de-chrome + clustering + labeled topology + tuning loop + the **event-driven `filtered.json` release generator**). Governance/state/Postgres **BUILT**: REQ-098 (installable package — **`pip install -e .`**), REQ-103 (isolated `governance` Postgres + cross-stage cache), REQ-099 (`state_event` log + `current_state` view), REQ-094 (event-driven `filtered.json`). **The console build is underway — gate@1 FULLY built (REQ-102), backend + frontend:** the batch is a **first-class entity in the governance DB (the working store)** — normalized PRECIOUS tables `batch`/`batch_district`/`batch_school`, with `batch_NNNNN.json` regenerated from the rows as the (gitignored, regenerable) **receipt**; gate@1 is an **in-band batch-level approval** with soft/reversible/audited editing; the **queue-review UI** (first console stage view, on the **MMM Design System** via the **DesignSync** tool) is live. **`batch_00002` created → edited → approved through the console** (the forcing-function milestone). **Stage 2 (Discover) then re-architected to a deterministic SERP cascade + the Stage-2 console view BUILT + RUN LIVE (REQ-104, 2026-06-28):** **Wave 1 = Bright Data SERP** (real Google, recurring-free, 98% recall) + **Serper failover** on API failure → **Wave 2 = Claude WebSearch** on the residual (different index, speculative). `batch_00002` (Bright Data found 28/30 schools) + `batch_00003` both ran end-to-end through the UI. Read-first authority: **`STAGE2_DISCOVER_DESIGN_2026-06.md` §7** (the SERP cascade) + **`PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`** (§7a Stage 2, §11/§11h console); slim *map* = `ACQUISITION_PIPELINE.md` §2; history → `PROJECT_HISTORY.md`.

**Metric = GROSS bell-to-bell minutes (end − start), NOT net.** No lunch/passing/recess deduction, no *assumed* deductions. Existing GT is already gross; gross needs only two reliably-published numbers (↑accuracy). Net is a deferred enhancement. Labeled `gross_bell_to_bell`. Plausibility gate 240–510 min. (REQ-055; supersedes net in REQ-042/046.)

**INVARIANT — extractors read TIMES; deterministic code computes MINUTES + the MODE.** Council models return only per-school `{start_time,end_time,grade_level,school_name}` facts; Python does `gross=end−start` and the per-band exact-mode. Never ask a model to compute minutes or pick a "typical" schedule. (REQ-054.)

**Extraction = COUNCIL (correctness); Discovery = WAVES (recall).** Council: **consensus is on the per-school (start,end) pair, cross-family, ±15 min** — same-family agreement is NOT consensus (REQ-056). Candidate set = 6 non-reasoning models (Gemini 2.5 Flash, Mistral Large 2512, DeepSeek V3.2, Mistral Small 24B, Gemini 2.5 Flash-Lite, Qwen3-235B-2507); Grok 4.3 & Qwen3.7-Max **removed** (reasoning-token cost 4–70×). **Open: exact council composition** — Path-1 cheap-trio vs Path-2 accuracy-pair vs Path-1-minus-Mistral, decided by measured escalation rate. Discovery (re-architected 2026-06-28, REQ-104; design note §7) = a **deterministic SERP cascade**, NOT agent waves: **Wave 1 = Bright Data SERP** (real Google, `site:`-scoped, recurring-free) + **Serper failover** on API failure (same index = uptime backup) → **Wave 2 = Claude WebSearch** on the residual (a *different* index, speculative). Decided by a measured 5-provider bake-off (`data/acquisition/diagnostics/`): **the index predicts recall** — raw Google wins (Bright Data 98% / Serper 100%), own-index Perplexity craters (43%, zero long-tail coverage). Retired: Claude-as-Wave-1 (66%), OpenRouter ($27/1K), Perplexity.

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()`+`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 **vision** (Gemini Flash / Mistral Large read JS/image/scan pages all text paths miss — proven). Trigger is "did the cheap reader recover usable content," not format. (Tier-1→2 structure-loss trigger is the one OPEN gate.)

**Ground truth re-established by hand (gross, per-school).** `data/benchmark/gt_curation_*/gt_proposals.json` — **940/943 schools human-verified** (per-school start/end). Pending: fold into a new gross GT manifest. Process: council *proposes*, human *verifies* (REQ-059). Failure-mode taxonomy (8 modes → checkpoints) in `ACQUISITION_PIPELINE.md`.

**Human-in-the-loop gates (stage-numbered, 2026-06-27; governance §11) = 5:** **gate@1** Queue (right districts/schools/bands), **gate@5** Filter (per-URL representation review — the critical gate), **gate@6** Handoff (which reps → which council config), **gate@7** Extract (review council requests), **gate@8** Aggregate (per-band results correct + honestly labeled — the effective old "CP-C"; Stage 9 then auto-writes). Stages 2/3/4 + the Stage-9 write are ungated. Each gate is manual/auto (Settings: global default + per-gate overrides; auto is confidence-escalating). Loosen later once confident.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Granite 4.1 8B = self-host candidate (headless Ubuntu server, separate project). Keys in gitignored `config/secrets.local.json` + `.env`. Requirements: **REQ-001…109** (042/046/048/057 superseded; 028–031/033 retired with the Crawlee era). Restore point for the archived GT/benchmark exercise: git tag `gt-exercise-complete`.

> **SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

### Next session (RESUME HERE — 2026-06-28)
**gate@1 + Stage 2 console are DONE; discovery RAN LIVE on `batch_00002` + `batch_00003`.** Stage 2 is now
a **deterministic SERP cascade** — `discover.brightdata_search` (Wave 1, real Google, recurring-free) +
`serper_search` failover on API failure → `headless._wave2_claude` (Wave 2, Claude WebSearch on the
residual). Code: `common/discover.py` (the 3 search fns + gate), `stage2_discover/discover_stage2.py`
(`run_wave1`/`run_wave2(search_fn)`, gate/residual/flatten/write), `stage2_discover/headless.py`
(`brightdata_then_serper`, `_wave2_claude`, `discover_district`, sequential `run_batch`), console
`/api/discover/*` in `server.py` + `static/stage2.js`. Bake-off harnesses: `scripts/stage2_*` →
reports in `data/acquisition/diagnostics/`. **Authority: `STAGE2_DISCOVER_DESIGN_2026-06.md` §7.**

**→ NEXT: REQ-100 (staleness view) / REQ-101 (Stage 6 handoff + gate@6).** Scope ends at gate@6 approval —
**no paid dispatch.** Open Stage-2 *watch-items* to revisit with more data (design note §7d), not blockers:
(a) is the **Claude Wave-2 tier** worth its latency — it recovered 0/2 on batch_00002 and its `claude -p`
timeout (420s) is too long for the sequential run (lower to ~60–90s); (b) **Serper-on-Bright-Data-misses**
(beyond failover) once real-batch misses accumulate; (c) Stages 3 & 4 console views likely follow.

**Fresh-session essentials:** `/catchup` → `pip install -e .` → **Docker up** → `lint-imports` (3 kept/0
broken) + `pytest -q -m "not integration"` (567 pass; resource-dependent tests are `integration`-marked,
excluded in CI). Launch the console **from the repo root**:
`python3 -m infrastructure.acquisition.process_governance.server` (→ :8005). Stage 2 needs SERP keys in
gitignored `config/secrets.local.json`: `BRIGHTDATA_API_KEY` + `BRIGHTDATA_SERP_ZONE` (must be a **SERP-API**
zone, not residential-proxy), `SERPER_API_KEY` (+ existing OPENROUTER/PERPLEXITY/GEMINI). `claude -p` (Wave 2)
runs headlessly from the server but is **blocked inside a Claude Code session** (CLAUDECODE set) — diagnostics
run in a plain terminal. Rebuild Stage-5 cache: `python3 -m infrastructure.acquisition.stage5_filter.build_signals`.
**UI design:** MMM Design System via the `DesignSync` tool. **Caveat:** static JS has **no lint/`no-undef` gate**
(a switcher refactor briefly broke Stage 1 via a deleted var) — diff `static/*.js` carefully; `node --check`
catches syntax only.

**Registered REQ#s:** **REQ-102** gate@1 DONE, **REQ-104** Stage 2 SERP cascade + console **DONE**, **REQ-100**
staleness view (next), **REQ-101** Stage 6 handoff + gate@6 (next; OPEN #1 = council-config grain).
Currency/recency = **REQ-044** (a Stage-5 enhancement). Batch receipts (`batch_*.json`) gitignored/regenerable;
git-durable lifecycle record = `district_status.json`.

**Watch-items:** (a) docs rationalization not-yet-done: GETTING_STARTED's stale "Run Scraper Service" task
(retired Express :3000), DATA_SOURCES dangling `data-dictionaries/` refs; (b) `.claude/skills/per-school-acquire*`
**and `stage2-discover`** skills are now **obsolete** (drove the retired agent Wave-1) — not the runbook; (c)
`create` is synchronous (heavy full-NCES draw) — fine for now.

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
