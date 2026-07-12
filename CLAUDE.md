# Claude Code Project Briefing: Learning Connection Time

This is the first thing a fresh Claude Code session sees. It's a navigation hub + durable operating rules —
not a build log. For *why* this project exists, read `docs/PROJECT_CONTEXT.md`; for *what's built right
now*, read GitHub Issues (this repo uses them as the live tracker) — this file stays short on purpose so it
doesn't need constant rewriting.

## Project Mission

Transform student-to-teacher ratios into "Learning Connection Time" (LCT) metrics that tell the story of students getting shortchanged.

**Core Formula:**
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example:** 5,000 students, 250 teachers, 360 min/day → LCT = 18 min/student/day

**Goal:** Analyze data from the largest U.S. school districts to identify educational equity disparities.
Full mission, reframe, and 6-phase roadmap: `docs/PROJECT_CONTEXT.md`. Currently in **Phase 1.5**: enriching
basic LCT with actual bell schedules acquired via the 9-stage acquisition pipeline
(`docs/ACQUISITION_PIPELINE.md`). Known methodological limitations (individualization fallacy,
time-as-quality assumption, averaging deception): `docs/METHODOLOGY.md`.

---

## Where to look for what

| You need... | Go to... |
|---|---|
| **What's currently built / in flight / next** | `gh issue list` (this repo's live tracker) — not this file |
| The mission, the story, the evolution roadmap | `docs/PROJECT_CONTEXT.md` |
| Dev setup, fresh-checkout orientation, conventions | `docs/GETTING_STARTED.md` |
| LCT calculation mechanics, SPED segmentation, QA | `docs/METHODOLOGY.md` |
| The 9-stage acquisition pipeline, end to end | `docs/ACQUISITION_PIPELINE.md` (the map) → `docs/technical-notes/STAGE*_DESIGN_2026-06.md` (per-stage present state) |
| Cross-stage architecture: DB/state/gate model | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` |
| Why a decision was made, project history | `docs/PROJECT_HISTORY.md` |
| Vocabulary | `docs/TERMINOLOGY.md` (read first) |

---

## Durable pipeline facts (settled architecture — rarely changes; NOT current-status)

**Metric = GROSS bell-to-bell minutes (end − start), NOT net.** No lunch/passing/recess deduction, no
*assumed* deductions. Ground truth is already gross; gross needs only two reliably-published numbers
(↑accuracy). Net is a deferred enhancement. Labeled `gross_bell_to_bell`. Plausibility gate 240–510 min.
(REQ-055; supersedes net in REQ-042/046.)

**INVARIANT — extractors read TIMES; deterministic code computes MINUTES + the MODE.** Council models
return only per-school `{start_time,end_time,grade_level,school_name}` facts; Python does `gross=end−start`
and the per-band exact-mode. Never ask a model to compute minutes or pick a "typical" schedule. (REQ-054.)

**Extraction = COUNCIL (correctness); Discovery = WAVES (recall).** Council: consensus is on the per-school
(start,end) pair, cross-family, ±15 min — same-family agreement is NOT consensus (REQ-056). Council
template: 2 cross-family voters → a 3rd-family judge on disagreement, enforced in `councils.validate()`.
Model composition is deferred to the council lab (`cost_benchmark`), never guessed. Discovery = a
deterministic SERP cascade, NOT agent waves: Wave 1 = Bright Data SERP + Serper failover (real Google
index) → Wave 2 = Claude WebSearch on the residual (a different index, speculative). The index predicts
recall — raw Google wins; own-index providers crater on long-tail K-12.

**The DB is the working store; disk holds binaries + receipts.** The governance Postgres DB is what every
stage actually reads/writes; per-stage JSON files (`discovery.json`, `filtered.json`, `handoff_*.json`,
etc.) are regenerable, auditable receipts — never the transport between stages.

**Human-in-the-loop gates are stage-numbered:** `gate@1` (Queue) · `gate@5` (Filter — the critical
per-URL review gate) · `gate@6` (Dispatch) · `gate@7` (Extract) · `gate@8` (Aggregate — Stage 9 then
auto-writes). Stages 2/3/4 + the Stage-9 write are ungated. Each gate is manual/auto (confidence-escalating).

**Ramp-up model (standing operating posture):** the pipeline is built **high-supervision-first** — every
gate manual now, easing toward auto (confidence-escalating) only as each gate's reliability is proven;
the destination is a self-governing app. **So present gate output as a recommendation for human sign-off,
not a done deal, until that gate is explicitly set to auto** — the human inspects real output at each gate
and catches real-data bugs code review misses. (governance §11b.)

**Three batch types (Stage 1):** `first-run`, `follow-up`, and `benchmark` (the 27 curated-GT districts
injected as `batch_00000` — permanently walled off from Stage-9 writes and funnel/enrichment stats; see
`STAGE1_QUEUE_DESIGN_2026-06.md` §2h).

**Ground truth, hand-verified (gross, per-school):** `data/benchmark/gt_curation_*/gt_proposals.json` —
940/943 schools human-verified. Process: council *proposes*, human *verifies* (REQ-059).

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()` +
`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 vision (reads JS/image/scan pages
all text paths miss). Trigger is "did the cheap reader recover usable content," not format.

**SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory
minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition
path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Keys in gitignored
`config/secrets.local.json` + `.env`. Requirements are tracked as REQ-001…115+ in `docs/REQUIREMENTS.yaml`
(some numbers superseded/retired — see that file's own status column, not a list here).

---

## Fresh-session essentials

`/catchup` → `pip install -e .` → **Docker up** (`docker-compose up -d`) → `lint-imports` (expect "kept/0
broken") + `pytest -q -m "not integration"`. `build_signals` full re-ingest (~2.5 min, idempotent, preserves
labels/facets) is only needed after a scoring/config change or new captures — not just to reboot the app.

Console: `python3 -m infrastructure.acquisition.process_governance.server` (→ :8005; Stage 5 default).
**Reload the browser for `static/*.js`, restart the server for Python changes.** Self-verify UI changes with
Playwright before shipping visuals (Python playwright isn't installed — drive the Node one in
`infrastructure/scraper`). CI runs two jobs: the DB-free suite + `governance-db` (`pytest -m govdb` on a
Postgres service container).

**Precious state + backups:** `label` (incl. `facets_json`) / `cluster_split` / `followup_flag` / `handoff`
live in the governance DB; `handoff_<hash>_<ts>.json` under `data/acquisition/handoffs/` is immutable;
`saved_view` holds UI prefs. The tracked `.githooks/pre-commit` sweeps `labels.json` +
`district_status.json` into every commit — on a fresh clone run `git config core.hooksPath .githooks`
(`GETTING_STARTED.md` §1b). Stage 4 needs poppler/tesseract/ghostscript (`GETTING_STARTED.md` §1a).

**Current status (2026-07-12):** the console runs the pipeline live through **`gate@7`**. The **"whittle
down open issues" hygiene campaign is fully CLOSED** (Batches 1–6 + #124, PRs #177–#199, #206), as is
**epic #123** (tech-debt/hygiene, closed via #127's `node:test` harness, PR #239). **Epic #209** (runtime
guardrails for the manual→auto transition, framed by the four commandments) has shipped **Phase 0/1/2**
(PRs #217/#218/#220): #208 recall floor, #210/REQ-121 gate-decision calibration log (live at gate@5/6/7),
#211/REQ-120 exploration-quota control law (**live wiring now SHIPPED** — see below), #212/#213 group-aware
promotion gate + safe-promotion machinery (**dormant**, activation tracked as one checklist, #219). **Epic
#200** (shift-left defect prevention: #201–#204) **MERGED (PR #221)**.

**#211 live wiring SHIPPED (2026-07-12, `exploration_live.py`):** the DB half of the anti-survivorship
exploration quota — the reject-population query (the tier-D SUPPRESS bucket), the randomized draw + coverage
meter, and **`resolve_gate5_mode`** (the gate@5 demote-hook and the first live caller of
`exploration_audit.resolve_gate_mode`, reading the `gate_mode` store #104). Wired into `save_label`
(self-healing) + `GET /api/exploration-audit` → a Settings-console coverage meter (Playwright-verified).
**Enforcement DORMANT** — gate@5 configured manual → returns manual, writes nothing. Current-config scoping
is STRUCTURAL (window recomputed over the live tier-D set; no reject-audit table). Verified live: 566
rejects, 24 sampled @5%, all census-labeled zero-miss → quality 1.0, window 24/300. REQ-120 → **tested**.
7 govdb tests + an endpoint smoke (suite: **1192** DB-free + **185** govdb).

**The batch_00013 live shakedown** (started 2026-07-06, #122) surfaced a chain of real request-loop and
data-quality bugs, closed across three PRs: **PR #221** (#231/#232, incl. REQ-122's cumulative-merge fix),
**PR #240** (#230/#233/#234/#235 — request-loop integrity; #233/REQ-123 is gate@7's auto-withdraw, the
**one deliberate exception** to the manual-gate ramp-up posture, justified by risk asymmetry — see
`PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §11b), and **PR #242** (the empty-domain contamination chain —
#229 prevention at Stage-1 admission **plus** Stage 2's own `gate_urls()` failing closed as
defense-in-depth, #228's gate@5 "Reset labels" remedy, #227's `remediate_contamination.py` cleanup
tooling). Every PR in this arc went through a max-effort adversarial review that found real defects even
in already-passing code, including in its own first-draft fixes (PR #240's auto-withdraw logic, PR #242's
guard depth and a remediation-script transaction-safety bug) — see `docs/PROJECT_HISTORY.md`'s newest
entries for the full lesson set. **The aggregation-quality pair #236/#237 is now closed out** (branch
`fix/aggregation-quality-236-237`, commits `3353632`/`214ce56`): **#236** shipped (`norm_school` now strips
US district-type suffixes so "Union Hill" == "Union Hill ISD" — same physical school stops
double-counting in a band); **#237 was mis-diagnosed** — the inflated charter school counts are cross-LEA
contamination (charter-network siblings on a *shared CMO domain* like `ascendlearning.org`, or blank-domain
captures — the Millard #227 class), NOT a topology undercount, so the topology change was **reverted** and
replaced with a `detect_single_school_over_extraction` detector (nces_count==1 LEA yielding >1 distinct
school → flagged for human review at gate@7, **detect-and-flag, never auto-reject**). This spun off a
**structure-aware charter track** (PROJECT_HISTORY 2026-07-12 entry): #243 charter segmentation, #244
structure-C dependent-charter carve-out (20.6% of enrollment), #245 junk-name facts, #246 gate@7 banner
render. Also still open: #238 (deferred efficiency follow-ups).

**#104 part (a) shipped (`d487f6a`, REQ-108):** the per-gate manual/auto **Settings store + console
toggle** — the ramp-up control surface the #209 guardrails were waiting on. A precious `gate_mode` table
(`common/gate_mode.py`: `configured_mode` + `license_state` per key, global 'default' + gate@1..8
overrides), `GET`/`POST /api/gate-mode`, a console **⚙ Settings** panel (Playwright-verified), git-backed
`gate_modes.json`. **Behavior-neutral by design:** every gate still runs manual — no handler branches on
the mode yet; setting a gate 'auto' persists intent only. Part (b) (per-gate confidence-escalating AUTO)
is the follow-on per-gate work, #211 first. Detail: governance §11b + REQ-108.

**The full stage-design-notes tower + `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` + `ACQUISITION_PIPELINE.md`
(incl. the Mermaid diagram) were resynced against current code 2026-07-12** (a multi-agent audit-then-rewrite
pass, verified by spot-checking rewrite claims against real file:line evidence) — treat every doc under
`docs/technical-notes/acquisition-pipeline-stage-design-notes/` plus those two as current as of this commit,
not as carrying drift from the PR #240/#242 arc.

**Next (RESUME HERE — 2026-07-12):** **#104 part (a) AND #211 live wiring are both DONE** — resume the
**pipeline sequence** at **#214**: the **measured-pass** that closes **epic #209**. Its instrument now
exists — `exploration_live.calibrate_against_census(con)` (does a p% random draw over the fully-labeled
reject bucket reproduce the census reject-quality? — the retrospective validation §5a describes). #214 is:
*run* it over the live census, confirm the sampler reproduces reject-quality within tolerance (worst-case:
completed districts are attention-sorted/messiest-first), record the measured-pass verdict, and — if it
passes — that's the evidence to trust the exploration quota before census-labeling stops. Then close epic
#209 (the four-commandments guardrail epic). Then **Stage 8** (the fact-based aggregation *algorithm* is
live inside gate@7 today; the standalone stage/gate@8/console is not built — #89/#90). Backlog: the charter
track (#243/#244/#245/#246), Council Lab (#80/#81), #238; and the *dedicated* `run_kind=exploration_audit`
queue MODE in the Stage-5 tree (deferred — the Settings pending list is today's working surface, sufficient
while census-labeling means every reject is already labeled). **Branch state:**
`fix/aggregation-quality-236-237` (now spans MIXED concerns — #236/#237 + research + Millard + parallel
receipts + #104 gates + #211 wiring; when opening PRs, likely split #104/#211 gate-automation work from the
aggregation-quality work). Untracked, left for Ian: earlier-run receipts under
`data/acquisition/{extractions,handoffs}/`. Resume-essentials: `pip install -e .` → Docker up
(`docker-compose up -d`) → `git config core.hooksPath .githooks` (fresh clone only) → `lint-imports` (expect
4 kept/0 broken) + `pytest -q -m "not integration"` (expect **1192** pass) + `pytest -q -m govdb` (expect
**185**, Postgres up). Full detail: `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` (§11b — the gate-mode +
exploration-quota control law, live wiring As-Built), `STAGE5_FILTER_DESIGN_2026-06.md` §5a (the #211 spec +
As-Built), `docs/PROJECT_HISTORY.md` (newest entries).

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
pytest tests/test_arch_manifest.py    # cross-boundary FITNESS functions vs arch-manifest.json (#124)
```
> **Caveat (the recurring lesson):** the import tools see **Python/Node imports only**. They do NOT see the
> *environmental* dependencies that often matter most — NCES CSV files read by path/year, **LCT DB
> tables** accessed via the ORM, `subprocess`/`claude -p` calls, OpenRouter API hosts. After the import
> graph, **read the code** for those edges. (Toolchain rationale: `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §10.)
> **`arch-manifest.json` + `tests/test_arch_manifest.py` (#124) now close part of this gap:** the declared
> ground truth for the cross-boundary edges (external processes, guarded entry points, client↔server rule
> literals, stage receipts), enforced as fitness functions. **When you add such an edge, update the manifest**
> — that edit is the review surface, and the suite fails on an undeclared one.

#### Design System for frontend/UI via DesignSync
To access current design resources, use the claude_design MCP (https://api.anthropic.com/v1/design/mcp, auth via /design-login) to import this project: https://claude.ai/design/p/07ef80cc-f2fe-4393-945e-99f1a40b0809

---

## Key Files

| Task | File |
|------|------|
| **Acquisition pipeline (canonical map)** | `docs/ACQUISITION_PIPELINE.md` |
| **Per-stage present-state design notes** | `docs/technical-notes/STAGE*_DESIGN_2026-06.md` |
| **Live pipeline code** | `infrastructure/acquisition/` (stage1_queue/ … stage9, process_governance/ console) |
| Extraction leaderboard + costs | `docs/EXTRACTION_BENCHMARK_FINDINGS.md` |
| Council design research | `docs/technical-notes/models-and-council-composition/LLM_COUNCIL_RESEARCH_2026-06.md` |
| Decisions, lessons, project history | `docs/PROJECT_HISTORY.md` |
| Data methodology (incl. SPED, QA dashboard) | `docs/METHODOLOGY.md` |
| Database setup | `docs/DATABASE_SETUP.md` |
| SEA integration guide | `docs/SEA_INTEGRATION_GUIDE.md` |
| LCT calculation | `infrastructure/scripts/analyze/calculate_lct_variants.py` |
| Database migrations + ledger | `infrastructure/database/migrations/` (`migrate.py status`) |
| Database queries | `infrastructure/database/queries.py` |

---

## Load Additional Context When Needed

This is the core briefing. Load the right doc for the task:

| Context Needed | Load File |
|----------------|-----------|
| Decisions, lessons, history | `docs/PROJECT_HISTORY.md` |
| Dev setup, workflow, testing, commands, conventions | `docs/GETTING_STARTED.md` |
| Database setup + schema | `docs/DATABASE_SETUP.md` (schema authority = `infrastructure/database/models.py`) |
| Data sources, SEA integrations, ID crosswalks, complex districts | `docs/DATA_SOURCES.md` · `docs/SEA_INTEGRATION_GUIDE.md` |
| Data methodology (LCT, sampling, exclusions, temporal) | `docs/METHODOLOGY.md` |
| The acquisition pipeline + per-stage design notes | `docs/ACQUISITION_PIPELINE.md` (map) → `docs/technical-notes/STAGE*_DESIGN_2026-06.md` |
| Governance / state model / gate model / console | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` |

**Token Efficiency:** load only what the task needs.

---

## Critical Rules

1. **Docker Required**: Always use `docker-compose up -d` before database operations. Never use `brew services start postgresql` - the `.env` is configured for Docker's PostgreSQL container.
2. **COVID Data Exclusion**: Never use 2019-20 through 2022-23 data
3. **Security Blocks**: ONE-attempt rule for Cloudflare/WAF-protected districts
4. **Temporal Validation**: Data from multiple sources must span ≤3 years
5. **Raw Data**: Never modify files in `data/raw/`
6. **Data Verification**: ALWAYS verify data exists in database before claiming enrichment counts. Never trust dispatch documentation without database verification.
7. **Research before implementing**: When a task involves a non-trivial design decision, an unfamiliar
   failure mode, or a pattern this codebase hasn't established a convention for (state-machine/invariant
   design, a new library, a class of bug just hit), do a web search *before* writing code — not only
   after a bug or a code-review finding surfaces it. Goal: prevention over correction — spend a small,
   cheap search now to avoid a larger token/time cost fixing it later (a wrong implementation, a review
   round-trip, a CI failure). Cite what you found and how it shaped the approach, the same as any other
   research. This does not replace reading this codebase's own conventions first (CLAUDE.md, the
   `docs/technical-notes/` design notes, existing code in the area) — check those before an external
   search, since a local precedent usually beats a generic pattern.

---

## Technical Reference

- **Crosswalk table**: `state_district_crosswalk` - single source of truth for all state mappings
- **SPED baseline**: 2017-18 IDEA 618/CRDC exempt from temporal rule
- **Acquisition pipeline**: the stage-based per-school pipeline in `infrastructure/acquisition/` — see `docs/ACQUISITION_PIPELINE.md` (the retired Crawlee+Ollama API/scraper was archived 2026-06-25 to `data/archive/crawlee-ollama-era-superseded-20260625/`)

For detailed reference, load the appropriate appendix above.
