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

**Current status (2026-07-26): epic #617 Phase 3 MERGED to `main` as PR #648 (`af1ce77`). Five PRs
are OPEN and green, awaiting Ian's review — and ONE DECISION (#662) blocks the epic's only
validation.** Base `main` = `af1ce77`. Everything before it: PR #641 (`9865666`, phases 0-2c), PR
#629 (`a26aee9`, REQ-164 receipts + the Stage 9 campaign 38/38).

**#617 in one line: a guard mirrored across five sites asked "has this district EVER been in a
`batch_type='benchmark'` batch", `batch_district` rows are never deleted, so all 27 batch_00000
districts were refused a Stage-9 write FOREVER — including correct minutes from later honest
production runs.** The fix is a grain change: a run's handling type is a property of **the work**,
never of the district. Landed on `main`: **#621** · **Phase 2a** (five copies of the benchmark
predicate → one home, `common/benchmark.py`) · **#618/2b** (`dispatch_type` first-class, in
`handoff._identity`, gate@6 REFUSES a production freeze holding benchmark reps) · **Phase 2c**
(`batch.redo_attempted` DECLARED + targeted composers) · and now **#619** (the TWO-ARM provenance
guard, re-keyed at 8 sites), **#644** (two of three freeze paths were entirely unguarded),
**#134** (request-execution walls → directive provenance), **#647** (Stage 2/3/4 console status was
district-grain, so a redo batch hid its own Run control).

**#662 is DECIDED AND FIXED (PR #663) — #620 is unblocked once that merges.** #619 re-keyed the Stage-9 wall
to provenance, but the GRAIN moved and the SCOPE did not ("ever" vs "this run"), so two layers in
FRONT of the wall are still district-permanent and an honestly re-run district *still* cannot
incorporate. Measured on the live DB: all **25 of 25** #620 districts are walled by the gate@8 queue
predicate TODAY (it asks "has this DISTRICT ever produced a `benchmark_gt` fact" over append-only
tables — permanently true), and `merge_fact_runs` gives the OLD benchmark facts the win (**957 of
957** carry `school_year=NULL`, so the year-supersede rule never engages and earliest-run wins). Only
Stage 9's own wall is receipt-scoped and correct. Ian decided **(c) + (b)** 2026-07-26: reclassify the 30 historical harness
extractions to `run_kind='benchmark'` (a receipted, idempotent, refuse-on-mixed migration) + a
provenance axis in `merge_fact_runs` ahead of the year axis. The "must exclude the mixed handoff"
caveat was measured FALSE — 0 extractions are mixed; the mixing is at handoff grain. 0 of the 27
carry a gate@8 approval or a Stage-9 event, so no frozen judgment was disturbed. Also decided:
queue-predicate shape left alone (#644 sealed the source), #617 closes at **25/27** (#646 follows),
and `gt://` reps are BADGED at gate@5/6, never filtered.

**Open PRs — all 6/6 CI green, none merged:**
`#663` **#662 — the acceptance test, THEN the fix** (two commits, in that order): the property
declared since §7a, first made executable and failing, then the (c)+(b) fix that makes it pass ·
`#664` fix(617) guard scoping (#651/#653/#654) — where `run_kind='production'` belongs and where it
would fail OPEN; arm 2 added to the mode-stability disabler; the fail-closed catch narrowed to
SQLSTATE 42P01 ·
`#665` refactor(617) one home again (#650/#658/#655/#661) **+ ONE fitness function over the CLASS**
(`tests/test_one_home_fitness.py`, a declared table of 7 rules with falsification corpora) ·
`#666` docs(617) arch-manifest serialization (#656) ·
`#667` fix(617) gate@6 assembles once + gate@8 stops withholding silently (#659/#660) —
Playwright-verified, 26 withheld / 47 queued.

**Next (RESUME HERE — 2026-07-26): (A) review + merge #663-#667.** They are independent of each other
and of #662; #664/#665 touch `common/benchmark.py` so expect a trivial conflict if merged out of
order. · **(B) — done; #662 is fixed in #663.** · **(C) #620 — the epic's ONLY
validation, not its last chore.** `batch_00030/31/32` (25 districts) are approved,
`redo_attempted=true`, **Stage 2 complete**; Stage 3 is next and is UNBLOCKED once #663 merges
(run `reclassify_benchmark_extractions --dry-run` then `--apply` against the live DB first — it is
not run automatically).
Ian drives the console; prepare and verify, don't execute stage runs. Prove ONE district end-to-end,
then 24, then **#646** for 27/27. *Falsifier: if any district needs a hand-edit or a re-adjudicated
gate@8 call, the mechanism is wrong — fix the pipeline, not the district.* · **(D) structural:**
#623 → #622 (needs #623's Node half) → #640 (build INSIDE #623) → #645 (REQ-171 blocker) → #624 →
**#625 LAST** (a REQ sweep over a moving target is wasted). #647's read-side patch gets deleted when
#622 lands. · **(E) epic #92** — nearly closed (#93/#94/#95 done, 38/38 campaign ran). Open: **#614**
(console Stage-9 status view) + adjacent **#615**, **#628**. All land AFTER (C). Verified:
`stage9_incorporate` does NOT trigger a recompute, so #628 is convenience, not a gate.

Read `docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`
first — §10 is the consolidated implementation log (§10.20 = the #662 correction), §11 the revised
plan, **§12 what actually happened in Phases A/B/D**. Durable architecture in
`PIPELINE_GOVERNANCE_AND_STATE.md` **§13**; spec in `docs/REQUIREMENTS.yaml` **REQ-169**
(`in_progress`, now carrying the SCOPE criterion) + **REQ-170**.

**The standing lesson (findings report §10.19/§10.20/§12.4):** three layers shipped green against
measurements that could not fail, and the epic's own consolidation didn't generalize. **When a change
is justified by "it diverges only in the future case," construct that case and test it.** Also: an
adversarial review's raw output is a *candidate* list — roughly a third didn't survive verification,
and two findings this round were materially wrong as filed in ways only measurement could settle.

**Schema invariant (bit us on PR #641):** a `_PRECIOUS_ALTERS` column's DDL must be declared TWICE,
identically — a SQLAlchemy `default=` never reaches the DDL, so a fresh `create_all()` DB diverges
from a migrated one and fails raw `text()` INSERTs **on CI only**. Always pair with `server_default=`.
Enforced DB-free by `tests/test_precious_alters_parity.py`. **Verify a new precious column against a
THROWAWAY governance DB — the local migrated one tests the path that isn't broken.**

**Outstanding:** Playwright-verify the gate@6 + gate@1 console changes AND #647's Stage 2/3/4
status/Run control (static-source-pinned only; #667's gate@8 work IS verified).
**Deferred by design (epic #128):** **#642** (content-derived document vintage — #662 makes this MORE
valuable: the 957 `school_year=NULL` facts are exactly what it would have populated) and **#643**
(the Stage-3 render-facts probe; rides #623's Node seam).
**Retired, do not do:** Phase 2e's retroactive `dispatch_type='benchmark'` tagging — arm 2 derives it.
Banked routing: #112 → epic #128. Parked: #475/#476, #103/#80 (+#110); the SEA integration follow-up
(~9 states) is an opt-in backlog item — ask Ian before filing.
Documented-in-code deferrals: `_satisfied_bands_now` batching; the #522 guardrail's per-rep
keyword/table attribution (needs a server payload change); JS behavioral tests (no JS harness);
the remediation-receipt exception is not STAGE-scoped (30-day expiry since 2026-07-20); attribution
v1 reads each district's LATEST candidate plan.
Resume-essentials (verified on `main` at `af1ce77`, 2026-07-26): `pip install -e .` → Docker up
(`docker-compose up -d`) → `git config core.hooksPath .githooks` (fresh clone only) → `lint-imports`
(expect **4 kept/0 broken**) + `pytest -q -m "not integration"` (expect **2008** pass, 1 skipped
[pyarrow]) + `pytest -q -m govdb` (expect **368**, Postgres up) + `pytest tests/test_*_integration.py`
(expect **255** pass, 149 skipped) + `cd infrastructure/scraper && npm test` (expect **90**).
With all five PRs merged the DB-free count is **2035** and govdb **370 + 2 xfailed**.
Console: reload the browser for `static/*.js`; Playwright-verify UI work against REAL records (Huntington
`4824000:af06722adb` 333k-char handbook; `0602095:6e8db3e114` 258 rasters). Drive the Node Playwright
from `infrastructure/scraper` (a script in /tmp cannot resolve the package).
Stage 9 incorporate CLI: `python3 -m infrastructure.acquisition.stage9_incorporate <did> [--dry-run]`;
sign-off preview: `python3 -m infrastructure.scripts.analyze.per_grade_lct_sample`.
Full detail: `docs/PROJECT_HISTORY.md`, `STAGE1-9_*_DESIGN.md`, `PIPELINE_GOVERNANCE_AND_STATE.md`,
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
