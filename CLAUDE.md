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
| The 9-stage acquisition pipeline, end to end | `docs/ACQUISITION_PIPELINE.md` (the map) → `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` (per-stage present state) |
| Cross-stage architecture: DB/state/gate model | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md` |
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
stage actually reads/writes; per-stage JSON files (`discovery.json`, `stage5_filter.<ts>...`,
`handoff_*.json`, etc.) are regenerable, auditable receipts — never the transport between stages. Stages
5-9 write theirs via the ONE shared `common/receipts.py::write_receipt`, ALWAYS datetime-stamped
(`stage<N>_<stage_name>.<fs_stamp>.<writer>-<h8>.json`, unified naming 2026-07-23); stages 2-4 stay
fixed-filename handoffs whose EXISTENCE is a stage-done marker (REQ-164; conversion tracked #617/#622/#623).

**Human-in-the-loop gates are stage-numbered:** `gate@1` (Queue) · `gate@5` (Filter — the critical
per-URL review gate) · `gate@6` (Dispatch) · `gate@7` (Extract) · `gate@8` (Aggregate — Stage 9 then
auto-writes). Stages 2/3/4 + the Stage-9 write are ungated. Each gate is manual/auto (confidence-escalating).

**Ramp-up model (standing operating posture):** the pipeline is built **high-supervision-first** — every
gate manual now, easing toward auto (confidence-escalating) only as each gate's reliability is proven;
the destination is a self-governing app. **So present gate output as a recommendation for human sign-off,
not a done deal, until that gate is explicitly set to auto** — the human inspects real output at each gate
and catches real-data bugs code review misses. (governance §11b.)

**When working on bell schedule acquisition infrastructure, a robust pipeline — not harvesting the instructional time data — is the immediate goal.** The way that we get instructional time data extracted and integrated is by way of the pipeline.
Bell-schedule acquisition work targets the highly-automated, as-deterministic-as-possible pipeline in `ACQUISITION_PIPELINE.md`. A correct outcome
reached by hand-orchestration — reading captures by eye, watching district-by-district for whether a rule
triggers, re-adjudicating an already-approved gate@8 decision — is a **process failure even when the
number is right**: it violates commandments #2 + #4 (manual inspection of ~20k districts doesn't scale)
AND commandment #1 (a probabilistic model judgment isn't reproducible or auditable the way a deterministic
guard is — run at a different time/model and the "verdict" could differ). Trust the deterministic inputs
(the approved gate@8 receipt is authoritative; a note here is not) and the script's own guards (benchmark
wall, TOCTOU, REQ-147 same-vintage staleness, REQ-026 temporal window, foreign-collision fail-loud) as the
ONLY legitimate gates. When an outcome is wrong or fragile, fix the **pipeline** (a guard, a metadata gap)
— never hand-fix the district. (2026-07-23, Ian.)

**Three batch types (Stage 1):** `first-run`, `follow-up`, and `benchmark` (the 27 curated-GT districts
injected as `batch_00000` — permanently walled off from Stage-9 writes and funnel/enrichment stats; see
`STAGE1_QUEUE_DESIGN.md` §2h).

**Ground truth, hand-verified (gross, per-school):** `data/benchmark/gt_curation_*/gt_proposals.json` —
940/943 schools human-verified across `batch_00000`'s 27 districts. Process: council *proposes*, human
*verifies* (REQ-059). **This set is FIXED — gate@8 approvals do NOT append to it** (no such code path;
Stage 9, the writer, is unbuilt — #93). What grows is the **confirmed-fact base**: every district approved
at gate@8 accrues a `stage8_approval` row + a frozen closing-argument receipt, and the more confirmed facts
we hold, the more we have to *learn from and improve with* — realized as pipeline-improvement work (epics
#478/#119, continuing in #106), not as a write into the GT corpus (Ian, 2026-07-16).

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()` +
`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 vision (reads JS/image/scan pages
all text paths miss). Trigger is "did the cheap reader recover usable content," not format.

**SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory
minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition
path. See `INSTRUCTIONAL_TIME_HARVEST.md`.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Keys in gitignored
`config/secrets.local.json` + `.env`. Requirements are tracked as REQ-001…151 in `docs/REQUIREMENTS.yaml`
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

**Precious state + backups:** `label` (incl. `facets_json`) / `cluster_split` / `followup_flag` /
`handoff` + the gate@8 human-judgment tables (`stage8_approval` incl. frozen receipts, `band_exclusion`,
`human_added_fact`, `slot_assignment`, `gate_mode`) live in the governance DB;
`handoff_<hash>_<ts>.json` under `data/acquisition/handoffs/` is immutable; `saved_view` holds UI prefs.
The tracked `.githooks/pre-commit` sweeps the git-backed JSON twins (`labels.json`,
`district_status.json`, `stage8_approvals.json`, `band_exclusions.json`, `human_added_facts.json`,
`slot_assignments.json`, …) into every commit — on a fresh clone run `git config core.hooksPath
.githooks` (`GETTING_STARTED.md` §1b). Stage 4 needs poppler/tesseract/ghostscript
(`GETTING_STARTED.md` §1a).

**Current status (2026-08-17): Tranche C steps 1-2 are MERGED, and step 3's premise was measured
false and re-scoped.** Three PRs landed the extraction-correctness core. **#774** — roster-anchored
school identity (REQ-173): variant spellings of one school now meet instead of minting false
disagreement, ambiguity is never auto-resolved, the roster (not voter agreement) adjudicates a
cross-band claim, and an unmatched name survives as `roster_unmatched`; `grade_level` STAYS in the
grouping key (35 level-collapse districts would mass-merge without it). **#792** — per-model context
accounting (REQ-174): every call clamps to the model's real window, a doomed call refuses pre-flight
at zero spend, and a rep records `council_degraded` when a VOTER is structurally lost. **#813** —
repetition-loop detection (#812): a voter emitting one row until the ceiling stops it is no longer
recorded as a large successful extraction. Three review rounds (#777-791, #797-811, #814-820 — 37
findings, all real, all fixed before merge). Docs re-synced to code 2026-08-17 (38adc81):
ACQUISITION_PIPELINE.md de-changelogged (109 date/BUILT stamps → 0, two false diagram claims fixed),
governance §14 added (extraction integrity), PROJECT_HISTORY entry written.

**What the measurements changed (the reason this session's plan moved):** four times the issue's own
diagnosis was wrong. #721's proposed fix would have mass-merged schools; #714's clamp turned a loud
400 into a *silent* partial; #793's own marker was then gated on zero-yield, which structurally
misses the partial it was built for; and **#794 was closed `not planned`** — bounding the school
estimate by roster size is worse than the status quo in the direction that loses data (570/918 and
82/918 under-predictions vs 56/918), and charter networks break its premise outright (KIPP Durham:
`nces_school_count=1`, 50 accepted schools). Chasing that found #812 and falsified our own record:
**there is no genuine dropped-tail truncation anywhere in the receipt store** — all six
truncated-with-facts calls are repetition loops. **#795 was stopped rather than shipped**: a
deterministic pre-dispatch hub classifier tops out ~59%/63%, misses the three biggest hubs, and
under a better matcher false-positives on the exact document its acceptance criteria reject.

**Tranche C's remainder + Tranche D (approved in shape, not started):** step 3 capture-completeness
(#708 OCR name-mangling ships as fidelity-clean · #685 Stage 3 captures only the ACTIVE tab panel ·
#672 the 5→1 widened rung dilutes geo derivation) · step 4 ladder-guard robustness (#710 a document
that never names its school burns 3 alternate-rep rounds · #711 a transient 429 records as a clean
zero-yield). **Tranche D** paired by surface: gate@5 (#673 no vintage surface + #674 a human label
unconditionally overrides the #241 validity floor — same floor, fix together) and the Stage 2-4
console triple (#669/#670/#671 — settle #671's design question first, the other two fall out of it).
**Deliberately deferred behind both:** epic #723's receipts→gov_db work and epic #617's remainder.

**Next (RESUME HERE — 2026-08-17):**
1. **#796 — page scoping is reachable only through the handbook door.** A roster table inside a long
   non-handbook PDF is sent whole. `harvest_pages` is already computed for EVERY PDF record; only
   slice *materialization* is gated on `is_handbook`, so widening that trigger needs no hub
   classifier — #796 does NOT depend on #795 (which is why it's next). The #230 yield guard is
   load-bearing and must keep holding: a slice that clips half the table must never shadow the full
   read.
2. **Then #795, re-scoped** — its surviving half is "fix `roster_school_names_hit` to use
   `norm_school`" (measured: Memphis 0→27, Broward 3→42, Orange 1→36), which needs the district-name
   collision handled (level-stripping collapses a small district's roster to the district's own
   name). The population half needs no classifier and is already measured.
3. **Then** Tranche C steps 3-4 → Tranche D's gate@5 pair → the Stage 2-4 console triple → #723.
4. **Ian's call, not a session task:** routing Broward/Cleveland/Essex's send-backs and resuming the
   5→1 composer on West Ada/Lincoln/Baldwin — live pipeline spend, stays console-driven.
Ian drives the console; prepare and verify, don't execute stage runs (Stage 9 CLI + the #716 replay
are the verification exceptions — read-only intent, idempotent, guarded). *Falsifier unchanged: if
any district needs a hand-edit or a re-adjudicated gate@8 call, the mechanism is wrong — fix the
pipeline, not the district.*

**Standing method note (now on its seventh instance): measure the thing before fixing it.** An
issue's proposed fix has been overturned by measurement seven times (#691, #684, #719, #755, #706's
severity ranking, #721, #794). Two corollaries earned this session: **a fix can remove a failure's
VISIBILITY instead of the failure** (#792's clamp made the 400 unrepresentable by making the same
event succeed quietly), and **a marker without a consequence is decoration** (#793 marked the
truncation, then gated its remedy on a condition that shape cannot meet). Before calling a fix done,
ask what would now be *observable* if it were wrong.

**The implemented-twice-drifts class (four instances this session — keep watching):** the
absent-`kinds` default resolved opposite ways in two files (#798); refusal-outranks-truncation was a
`!=` guard in one file and a set-membership negation in another (#810); a per-record dict
comprehension discarded a sibling rep's marker (#799, the #785 shape one subsystem over); and #816's
`ok` gate had two unguarded siblings in the telemetry layer. Countermeasure that works: **one
function in the base layer both callers invoke**, then diff every sibling path against a new fix —
including siblings inside the SAME PR.

**The standing lesson (now tripled): three separate layers shipped green against measurements that
could not fail (§10.11), then the fix round's own review findings repeated it (§10.19/§10.20), then a
MERGED fix sat un-run against the live DB for a day and nothing detected it (§13.1).** When a change
is justified by "it diverges only in the future case," construct that case and test it — and for
precious-state migrations, "merged" is not "landed": verify against the live system, not the diff.

**Schema invariant (bit us on PR #641):** a `_PRECIOUS_ALTERS` column's DDL must be declared TWICE,
identically — a SQLAlchemy `default=` never reaches the DDL, so a fresh `create_all()` DB diverges
from a migrated one and fails raw `text()` INSERTs **on CI only**. Always pair with `server_default=`.
Enforced DB-free by `tests/test_precious_alters_parity.py`. **Verify a new precious column against a
THROWAWAY governance DB — the local migrated one tests the path that isn't broken.**

**Outstanding:** Playwright-verify the gate@6 + gate@1 console changes AND #647's Stage 2/3/4
status/Run control (static-source-pinned only; #667's gate@8/#662's gate@5 badges, #684's gate@5
staff-day surfacing, AND the three new gate@8 arrows ARE verified — rerunnable verifiers:
`infrastructure/scraper/verify_684_console.mjs` (gate@5 staff-day) and
`infrastructure/scraper/verify_682_console.mjs` (gate@8's write badge / send-back routing /
re-review flag — covers #682/#689/#713 together, the pattern to extend for Tranche D's console work).
**Deferred by design (epic #128):** **#642** (content-derived document vintage — #662 makes this MORE
valuable) and **#643** (the Stage-3 render-facts probe; rides #623's Node seam).
**Retired, do not do:** Phase 2e's retroactive `dispatch_type='benchmark'` tagging — arm 2 derives it.
Banked routing: #112 → epic #128. Parked: #475/#476, #103/#80 (+#110); the SEA integration follow-up
(~9 states) is an opt-in backlog item — ask Ian before filing.
Documented-in-code deferrals: `_satisfied_bands_now` batching; the #522 guardrail's per-rep
keyword/table attribution (needs a server payload change); JS behavioral tests (no JS harness);
the remediation-receipt exception is not STAGE-scoped (30-day expiry since 2026-07-20); attribution
v1 reads each district's LATEST candidate plan.
Resume-essentials (ALL re-verified 2026-08-17 on this checkpoint, post-merge): `pip install -e .` →
Docker up (`docker-compose up -d`) → `git config core.hooksPath .githooks` (fresh clone only) →
`lint-imports` (expect **4 kept/0 broken**) + `pytest -q -m "not integration"` (expect **2325**
pass, 1 skipped [pyarrow]) + `pytest -q -m govdb` (expect **396** pass, Postgres up) + `pytest
tests/test_*_integration.py` (expect **257** pass, 149 skipped) + `cd infrastructure/scraper &&
npm test` (expect **91**). NB `pytest -m integration` now also carries a NETWORK test
(`test_model_windows_integration.py`, #809) that re-fetches OpenRouter and fails with "refresh the
catalog" if `MODEL_WINDOWS` has drifted — it skips cleanly offline and is excluded from the default
suite; a failure there means bump the catalog + `MODEL_WINDOWS_FETCHED`, not a broken build.
**pytest is 9.1.1**: `pytest.ini` declares `pythonpath = .` — without it, pytest 9's bare `pytest`
script fails COLLECTION on `tests/test_benchmark_*` (`from tests import benchmark_seed`).
`requirements.txt` floor raised to `pytest>=9.0`. **Scheduled CI now runs nightly (#722, merged)** —
`main` no longer sits silently red between pushes the way it did 08-11→08-14.
Console: reload the browser for `static/*.js`; Playwright-verify UI work against REAL records (Huntington
`4824000:af06722adb` 333k-char handbook; `0602095:6e8db3e114` 258 rasters; Bentonville
`0503060:a5f32ff869` staff-day tier B, `0503060` again for gate@8's write badge; Broward `1200180`
for gate@8 send-back routing). Drive the Node Playwright from `infrastructure/scraper` (a script in
/tmp cannot resolve the package); run scratch console servers on a spare port (`:8015`), never
Ian's `:8005`.
Stage 9 incorporate CLI: `python3 -m infrastructure.acquisition.stage9_incorporate <did> [--dry-run]`
(now also fires automatically on gate@8 approval, #682 — the CLI stays the recovery/backfill path);
gate@8 send-back routing CLI: `python3 -m infrastructure.acquisition.process_governance.stage8_sendback
{route <did> --route 8->1|8->6|unrouted} [--dry-run]` (#689); re-review audit CLI: `python3 -m
infrastructure.acquisition.stage8_aggregate.rereview [<did> …]` (#713); sign-off preview: `python3
-m infrastructure.scripts.analyze.per_grade_lct_sample`.
Full detail: `docs/PROJECT_HISTORY.md`, `STAGE1-9_*_DESIGN.md`, `PIPELINE_GOVERNANCE_AND_STATE.md`,
`docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md` §14,
`docs/REQUIREMENTS.yaml`.

---

## Current Data Years

**Current School Year:** derived automatically (July-1 rollover) by
`infrastructure/utilities/school_year.py:current_school_year()` — the single source of truth,
never hand-bumped (2026-27 as of this writing). `NCES_PRIMARY_YEAR` in the same module IS
hand-bumped, on ingest of a new CCD (a data event), verified against `lct_calculations` rows.

### Data Year Strategy

| Data Type | Year | Notes |
|-----------|------|-------|
| Primary dataset | 2024-25 | NCES CCD enrollment/staffing (ingested + LCT-calculated 2026-07) |
| Bell schedules | current → 2023-24 | Post-COVID acceptable, search current first; the REQ-026 blend window (span ≤ 2 start-years) arbitrates per calculation |
| COVID exclusion | 2019-20 through 2022-23 | Never use - abnormal schedules |

**Search Order:** current school year first, then back to 2023-24 (all post-COVID)

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

# Run SEA integration tests
pytest tests/test_*_integration.py -v

# VERIFICATION - Run after enrichment!
python3 infrastructure/scripts/verify_enrichment.py --quick
```

### Architecture & code-exploration tools (use these to read/verify the codebase — REQ-098)
These are installed (dev-deps) and are the project's standard way to map dependencies and enforce
layering — reach for them before writing or verifying any "what depends on what" narrative:
```bash
lint-imports                 # enforce the acquisition layering contracts (config: pyproject.toml); expect "4 kept, 0 broken"
python3 -c "import grimp; g=grimp.build_graph('infrastructure'); \
  print(sorted(g.find_modules_directly_imported_by('infrastructure.acquisition.stage1_queue.queue_batch')))"
                             # grimp: query the real import graph (what a module imports / is imported by)
vulture infrastructure/acquisition    # dead-code sweep
cd infrastructure/scraper && npm run lint:deps   # Node (.mjs) side — depcruise over the flat *.mjs (no lib/ dir)
pytest tests/test_arch_manifest.py    # cross-boundary FITNESS functions vs arch-manifest.json (#124)
```
> **Caveat (the recurring lesson):** the import tools see **Python/Node imports only**. They do NOT see the
> *environmental* dependencies that often matter most — NCES CSV files read by path/year, **LCT DB
> tables** accessed via the ORM, `subprocess`/`claude -p` calls, OpenRouter API hosts. After the import
> graph, **read the code** for those edges. (Toolchain rationale: `PIPELINE_GOVERNANCE_AND_STATE.md` §10.)
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
| **Per-stage present-state design notes** | `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` |
| **Live pipeline code** | `infrastructure/acquisition/` (stage1_queue/ … stage9, process_governance/ console) |
| Extraction leaderboard + costs | `docs/technical-notes/learning-loop-reports/EXTRACTION_BENCHMARK_FINDINGS.md` |
| Council design research | `docs/technical-notes/models-and-council-composition/LLM_COUNCIL_RESEARCH_2026-06.md` |
| Decisions, lessons, project history | `docs/PROJECT_HISTORY.md` |
| Data methodology (incl. SPED, QA dashboard) | `docs/METHODOLOGY.md` |
| Database setup | `docs/DATABASE_SETUP.md` |
| SEA integration guide | `SEA_INTEGRATION_GUIDE.md` |
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
| Data sources, SEA integrations, ID crosswalks, complex districts | `docs/DATA_SOURCES.md` · `SEA_INTEGRATION_GUIDE.md` |
| Data methodology (LCT, sampling, exclusions, temporal) | `docs/METHODOLOGY.md` |
| The acquisition pipeline + per-stage design notes | `docs/ACQUISITION_PIPELINE.md` (map) → `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` |
| Governance / state model / gate model / console | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md` |

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
