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
broken") + `pytest -q -m "not integration"`. `build_signals` full re-ingest (**~8.5 min** since 2026-08-18 —
whole documents are scanned, the 60-page cap is gone; idempotent, preserves labels/facets) is only needed
after a scoring/config change or new captures — not just to reboot the app. Run it `--assert-floor`.

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

**Current status (2026-08-18): page scoping is redesigned around an ABSOLUTE floor, both PRs are
MERGED, and the live DB is re-ingested against merged `main`.** **#828** — the per-page signal was
silently truncated at 60 pages (Memphis `00f553bcfc` read 3 times; it has 838, on pp.89-91; 10
records were suppressed by `lf_no_times` purely because their times lived past the cap). Cap
removed, one `pdftotext` call split on form feed, a guard test so it cannot return. **#829** — the
absolute time-bearing page floor (#821): keep a page iff it carries a clock time, or an
instructional-minutes declaration, or is page 1, or neighbours a time-bearing page. Lossless on the
time signal by construction (0/30,848); drops 43% of pages; **16.0% fewer characters dispatched
corpus-wide, 88% on the 166 records it re-routes**. It replaces #796's proposal (widen the
peak-relative harvest), which measured as losing **26.3% of the corpus's times** — 45% on Memphis —
and was closed `not planned`. Two review rounds absorbed before merge (#830-#840, 11 findings, all
real, all fixed). Re-ingest post-merge (8m18s — **not the ~2.5 min this file used to say**; whole
documents are scanned now): recall floor 0.9947 ≥ 0.98, tiers unchanged, precious state verified
row-for-row, 727 `timebearing_slice` + 150 `harvest_slice` reps live.

**Where the output-ceiling work went (Ian was right that it was open):** #714's chunking half was
never built — its "or minimally, mark degraded" clause let it close. Measured against the REAL
council ceilings (the weakest of voter/voter/judge): the text council (16,384) leaves **4 records
with no fitting rep**; **0 records exceed the image council's** 32,768; a 4× text council is
constructible from the approved roster. That is an experiment set, not a scripted rule → **epic #80
children #823 (higher-ceiling routing) / #824 (a model that partitions) / #825 (overflow as
follow-up routing)**, behind **#822** (fail-loud overflow monitoring, the tripwire that says which
experiment matters).

**Next (RESUME HERE — 2026-08-18):**
1. **#822 — output-overflow monitoring.** A rep whose estimated output exceeds its assigned
   council's ceiling (weakest member's `usable_output`, never a global constant) must be a
   first-class degraded kind next to `DEGRADED_REFUSED/TRUNCATED/LOOPED` in
   `common/model_families.py`, surfaced at gate@6/7, and can never record as a clean zero. One
   shared estimate helper — not a second copy of `openrouter.py`'s sizing (the drift class).
   Acceptance: the 4 no-fitting-rep records are flagged today; a rep that fits is not.
2. **#826 — `roster_school_names_hit` via `norm_school`** (Memphis 0→27, Broward 3→42, Orange 1→36),
   with the district-name collision guarded. Also carries #795's P4: Northwestern
   `1730540:bcd9c539fb` is a 320-student, 3-school district whose 886-page policy book now reads
   3,211 clock times — a scope error, better solved by not sending it than by any capacity work.
3. **#841 — the three 7→6 alternates collectors disagree on `segment:main`** (release admits it,
   both Stage-7 sites exclude all `segment:*`). Settle by MEASUREMENT (how often an unsent
   `segment:main` carries `n_times` ≥ the sent full text, and whether any gained facts on retry),
   then one rule in `release.NON_SWAPPABLE_SOURCES`, all three collectors reading it.
4. **Then** Tranche C steps 3-4 (#708/#685/#672 · #710/#711) → Tranche D's gate@5 pair (#673/#674)
   → the Stage 2-4 console triple (#669/#670/#671, settle #671 first) → #723.
5. **Ian's call, not a session task:** routing Broward/Cleveland/Essex's send-backs and resuming the
   5→1 composer on West Ada/Lincoln/Baldwin — live pipeline spend, stays console-driven. The epic
   #80 experiments (#823-#825) also spend real money and are Ian's to schedule.
Ian drives the console; prepare and verify, don't execute stage runs (Stage 9 CLI, the #716 replay,
and the **read-only measurement scripts** are the verification exceptions). *Falsifier unchanged: if
any district needs a hand-edit or a re-adjudicated gate@8 call, the mechanism is wrong — fix the
pipeline, not the district.*

**Standing method note (now on its NINTH instance): measure the thing before fixing it.** An issue's
proposed fix has been overturned by measurement nine times (#691, #684, #719, #755, #706's severity
ranking, #721, #794, **#796, #795**). Corollaries: **a fix can remove a failure's VISIBILITY instead
of the failure** (#792); **a marker without a consequence is decoration** (#793); and, new this
session, **re-run the measurement after the fix it motivated** — the design measurement that said
"Memphis keeps 60/60 pages, the floor can't help" was itself computed over the truncated signal (at
154 pages it keeps 101; the conclusion held, the stated reason was wrong). Before calling a fix done,
ask what would now be *observable* if it were wrong.

**The implemented-twice-drifts class (FIVE instances across two sessions — it recurred in the PR
whose commit message named it):** #798/#810/#799/#816 last session; this session, "which slice does
this record get" was a hand-written predicate in ingest and another in `best_send`, disagreeing on
**43 live records** (35 handbooks with a floor slice cut then hidden; 8 human-labelled records
refused by one gate and starved by the other, #834). The P3 byte-identity test only locked the case
where the two copies happened to agree. Countermeasure, applied at its smallest scale:
`select_slice()` in the base layer, ingest cuts what it returns, `best_send` sends only a match —
mutual exclusion as a property of the RETURN TYPE, not of branch order in two files. **A test that
locks agreement proves nothing about where two copies diverge; the only lock is having one copy.**

**The standing lesson (now on its FOURTH shape): a measurement that cannot fail.** §10.11, then the
fix round's own findings, then a merged fix un-run against the live DB (§13.1) — and this session
**Pass B re-run after the re-ingest printed `VERDICT: PASS` with 0 changed / 0% saved**: its baseline
read the live DB, which already held the reps the change had written, so it compared the post-state
with itself, and B6's safety block (inside `if changed`) never ran — every safety number was 0
because nothing was measured. Fixed with an idempotent baseline and `NOTHING MEASURED` instead of
`PASS` on an empty sweep. **A verdict that cannot fail is not a verdict; make the script say so.**
For precious-state migrations, "merged" is not "landed": verify against the live system.

**Schema invariant (bit us on PR #641):** a `_PRECIOUS_ALTERS` column's DDL must be declared TWICE,
identically — a SQLAlchemy `default=` never reaches the DDL, so a fresh `create_all()` DB diverges
from a migrated one and fails raw `text()` INSERTs **on CI only**. Always pair with `server_default=`.
Enforced DB-free by `tests/test_precious_alters_parity.py`. **Verify a new precious column against a
THROWAWAY governance DB — the local migrated one tests the path that isn't broken.**

**Outstanding:** Playwright-verify the gate@6 + gate@1 console changes, #647's Stage 2/3/4 status/Run
control, AND **#840's new gate@5 page-scoping card** (★ harvest / ◆ floor markers, `data-scoping=`
DOM hook — static-source-pinned only so far); #667's gate@8/#662's gate@5 badges, #684's staff-day
surfacing and the three gate@8 arrows ARE verified — rerunnable verifiers
`infrastructure/scraper/verify_684_console.mjs` and `verify_682_console.mjs` (the pattern to extend).
**Deferred by design (epic #128):** #642 (content-derived document vintage) and #643 (the Stage-3
render-facts probe; rides #623's Node seam). **Retired, do not do:** Phase 2e's retroactive
`dispatch_type='benchmark'` tagging — arm 2 derives it. Banked routing: #112 → epic #128. Parked:
#475/#476, #103 (+#110); the SEA integration follow-up (~9 states) is an opt-in backlog item — ask
Ian before filing. Documented-in-code deferrals: `_satisfied_bands_now` batching; the #522 guardrail's
per-rep keyword/table attribution (needs a server payload change); JS behavioral tests (no JS
harness); the remediation-receipt exception is not STAGE-scoped (30-day expiry since 2026-07-20);
attribution v1 reads each district's LATEST candidate plan; the `stage6_handoff/requests.py:17-18`
docstring falsely claims Stage 7 "reads ONLY the flagged pages" — the `pages` hint never scoped
content (the slice FILE is the scoping), a live source of wrong inferences worth a one-line issue.
Resume-essentials (ALL re-verified 2026-08-18 on this checkpoint, post-merge, on `main`): `pip
install -e .` → Docker up (`docker-compose up -d`) → `git config core.hooksPath .githooks` (fresh
clone only) → `lint-imports` (expect **4 kept/0 broken**) + `pytest -q -m "not integration"` (expect
**2371** pass, 1 skipped [pyarrow]) + `pytest -q -m govdb` (expect **396** pass, Postgres up) +
`pytest tests/test_*_integration.py` (expect **257** pass, 149 skipped) + `cd infrastructure/scraper
&& npm test` (expect **91**) + `flake8 . --count --select=E9,F63,F7,F82` (expect **0** — this is CI's
blocking lint; the vulture whitelist is `per-file-ignores`'d for F821, main had been red on it since
ebcc1a1). NB `pytest -m integration` also carries a NETWORK test (`test_model_windows_integration.py`,
#809) that re-fetches OpenRouter and fails with "refresh the catalog" if `MODEL_WINDOWS` has drifted
— skips cleanly offline, excluded from the default suite. **Full re-ingest is now ~8.5 min**
(`python3 -m infrastructure.acquisition.stage5_filter.build_signals --assert-floor`; whole documents
scanned, largest is 1,017 pages) — needed only after a scoring/config change or new captures; run it
with `--assert-floor` so a recall regression rolls back inside the transaction; take a `pg_dump` of
the precious tables first (governance DB is `postgresql://…@localhost:5432/governance`, separate
from the LCT DB).
**pytest is 9.1.1**: `pytest.ini` declares `pythonpath = .` — without it, pytest 9's bare `pytest`
script fails COLLECTION on `tests/test_benchmark_*`. `requirements.txt` floor is `pytest>=9.0`.
Scheduled CI runs nightly (#722).
Console: reload the browser for `static/*.js`; Playwright-verify UI work against REAL records (Huntington
`4824000:af06722adb` 333k-char handbook; `0602095:6e8db3e114` 258 rasters + a floor-slice PDF at
311 pages; Bentonville `0503060:a5f32ff869` staff-day tier B, `0503060` again for gate@8's write
badge; Broward `1200180` for gate@8 send-back routing; **`0904830:71acfa3404` the 1,017-page
handbook whose floor slice was #834's dead-slice case — the record to Playwright #840 against**).
Drive the Node Playwright from `infrastructure/scraper`; scratch console servers on `:8015`, never
Ian's `:8005`.
Stage 9 incorporate CLI: `python3 -m infrastructure.acquisition.stage9_incorporate <did> [--dry-run]`
(fires automatically on gate@8 approval, #682 — the CLI is the recovery/backfill path); gate@8
send-back routing: `python3 -m infrastructure.acquisition.process_governance.stage8_sendback {route
<did> --route 8->1|8->6|unrouted} [--dry-run]` (#689); re-review audit: `python3 -m
infrastructure.acquisition.stage8_aggregate.rereview [<did> …]` (#713); sign-off preview: `python3
-m infrastructure.scripts.analyze.per_grade_lct_sample`. **Measurement scripts (rerunnable,
read-only, import the LIVE functions):**
`docs/technical-notes/production-quality-control-research/2026-08-17-{per-page-uncap,timebearing-floor}-measure.py`.
Full detail: `docs/PROJECT_HISTORY.md` (2026-08-17/18 entry), `STAGE1-9_*_DESIGN.md`,
`PIPELINE_GOVERNANCE_AND_STATE.md`, `docs/REQUIREMENTS.yaml`.

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
vulture infrastructure/acquisition .vulture_whitelist.py    # dead-code sweep vs the audited baseline
                             # (a finding = NEW since 2026-08-17: prove it reachable + whitelist, or delete it)
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
