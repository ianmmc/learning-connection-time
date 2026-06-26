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

## Current Status (2026-06-26)

Building the **per-school acquisition pipeline** stage-by-stage with **human-in-the-loop checkpoints**. The GT/benchmark exploration concluded and was archived; the validated design is now the active build. Canonical pipeline doc: **`docs/ACQUISITION_PIPELINE.md`** (9 stages + failure-modes→checkpoints table + reader-routing spec). Live code: **`infrastructure/acquisition/`** (promoted out of the retired `scripts/benchmark/`). Council research: `docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`. Leaderboard/costs: `docs/EXTRACTION_BENCHMARK_FINDINGS.md`.

**Build progress (2026-06-26):** Stages **1–4 built + run live** on `batch_00001` (12 districts, 150 URLs). **Stage 5** (local filter) — review app + deterministic signals + de-chrome + near-dup clustering + labeled topology + the **tuning learning-loop** (config-as-data, measurement harness REQ-090, episode ledger REQ-095, frontier/grid search REQ-096) all built; the operational `filtered.json` release generator (REQ-094) is the remaining Stage-5 piece. The project is now executing the **governance/state/Postgres re-architecture** — **authority doc: `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`** (read it first; it supersedes older design notes where they conflict). **REQ-098 DONE** (acquisition tree is now a proper installable package — **run `pip install -e .`**, no more `sys.path` shims; import-linter/grimp/vulture + dependency-cruiser enforce layering). **REQ-103 (Postgres governance DB) COMPLETE** — Stage-5 ingest + readers + tests migrated SQLite→isolated `governance` Postgres (103b–f, commit `bbd0f66`), cross-stage cache added (103c), docs updated (103g). **Next build step: REQ-099** (state event-log). See `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §1b.

**Metric = GROSS bell-to-bell minutes (end − start), NOT net.** No lunch/passing/recess deduction, no *assumed* deductions. Existing GT is already gross; gross needs only two reliably-published numbers (↑accuracy). Net is a deferred enhancement. Labeled `gross_bell_to_bell`. Plausibility gate 240–510 min. (REQ-055; supersedes net in REQ-042/046.)

**INVARIANT — extractors read TIMES; deterministic code computes MINUTES + the MODE.** Council models return only per-school `{start_time,end_time,grade_level,school_name}` facts; Python does `gross=end−start` and the per-band exact-mode. Never ask a model to compute minutes or pick a "typical" schedule. (REQ-054.)

**Extraction = COUNCIL (correctness); Discovery = WAVES (recall).** Council: **consensus is on the per-school (start,end) pair, cross-family, ±15 min** — same-family agreement is NOT consensus (REQ-056). Candidate set = 6 non-reasoning models (Gemini 2.5 Flash, Mistral Large 2512, DeepSeek V3.2, Mistral Small 24B, Gemini 2.5 Flash-Lite, Qwen3-235B-2507); Grok 4.3 & Qwen3.7-Max **removed** (reasoning-token cost 4–70×). **Open: exact council composition** — Path-1 cheap-trio vs Path-2 accuracy-pair vs Path-1-minus-Mistral, decided by measured escalation rate. Discovery waves: **Claude WebSearch (Haiku subagent) → OpenRouter `gpt-4o-mini-search` → flag manual; Perplexity dropped.** Domain-scoped; ~90% page-find on full-41.

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()`+`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 **vision** (Gemini Flash / Mistral Large read JS/image/scan pages all text paths miss — proven). Trigger is "did the cheap reader recover usable content," not format. (Tier-1→2 structure-loss trigger is the one OPEN gate.)

**Ground truth re-established by hand (gross, per-school).** `data/benchmark/gt_curation_*/gt_proposals.json` — **940/943 schools human-verified** (per-school start/end). Pending: fold into a new gross GT manifest. Process: council *proposes*, human *verifies* (REQ-059). Failure-mode taxonomy (8 modes → checkpoints) in `ACQUISITION_PIPELINE.md`.

**Human-in-the-loop checkpoints (current mode) = 3:** **CP-A Queue** (right schools/bands targeted), **CP-B Input** (legible capture — the critical gate), **CP-C Output→Write** (per-school times correct + honestly labeled; approval gates the DB write). Loosen later once confident.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Granite 4.1 8B = self-host candidate (headless Ubuntu server, separate project). Keys in gitignored `config/secrets.local.json` + `.env`. Requirements: **REQ-001…107** (042/046/048/057 superseded; 028–031/033 retired with the Crawlee era). Restore point for the archived GT/benchmark exercise: git tag `gt-exercise-complete`.

> **SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

### Next session (RESUME HERE — 2026-06-26)
**The immediate task is REQ-099** (the state event-log — migrate `district_status` → Postgres
`state_event` + derived current-state; design in `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §3).
**REQ-103 is COMPLETE** (governance DB stood up; Stage-5 ingest/readers/tests on isolated `governance`
Postgres; cross-stage cache; docs) — 103a `3c725f3`, 103b–f `bbd0f66`, 103c/g in the follow-up pass.

**First, in a fresh session:** `/catchup`, then `pip install -e .` (required since REQ-098 packaged the
tree). Verify state with `lint-imports` (expect 3 kept/0 broken) and `pytest -q`. Docker must be up
(the governance-DB tests skip without it). Rebuild the governance DB if needed:
`python3 -m infrastructure.acquisition.stage5_filter.build_signals`.

**Build sequence after REQ-103** (from the governance doc §9): **REQ-099** state event-log (migrate
`district_status` → Postgres) → **REQ-094** release generator (`filtered.json`) → REQ-100 trigger UI →
REQ-101 Stage-6 handoff → REQ-102 CP-A view / stage selector → REQ-104 Stage 2 headless (`claude -p`).

**Watch-items:** (a) the Stage-5 review app moved to `infrastructure/acquisition/process_governance/`
and `build_signals.py` to `stage5_filter/` (REQ-098) — imports are now absolute package paths, no
`sys.path` shims; (b) discovery's Wave 1 is moving from an in-chat Haiku *subagent* to **headless
`claude -p`** (REQ-104, not built yet); (c) the `.claude/skills/per-school-acquire*` skills are
**premature/stale** (bundle all 9 stages) — don't treat them as the runbook; walk stages individually.

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

This is the core briefing (~115 lines). For detailed information, load these appendices:

| Context Needed | Load File |
|----------------|-----------|
| Historical progress, directory structure, technical stack | `docs/claude-instructions/CLAUDE_REFERENCE.md` |
| Development workflow, testing, common commands | `docs/claude-instructions/CLAUDE_WORKFLOWS.md` |
| Data architecture, SEA integrations, crosswalks | `docs/claude-instructions/CLAUDE_DATA.md` |

**Token Efficiency:** Only load appendices relevant to the current task. This modular structure reduces context consumption by ~80% compared to the previous monolithic file.

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
