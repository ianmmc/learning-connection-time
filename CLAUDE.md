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

**Batch-scoped stage done-ness has ONE home:** `DS.completed_by_batch(batch_id, stage_name, ids)` —
dispatched by THIS batch AND a stage outcome inside the window that dispatch owns (REQ-182, #671/#885).
Never re-key off `dispatched_by_batch` (retired) or a bare `batch_id = :b` filter (measured to withdraw
36 genuine completions — most historical outcomes predate the stamp). And (#670, REQ-189): a district
whose LATEST capture/process state_event is `failed` never renders `done`, artifact or not — gov_db
outranks disk; the stage-3 completion event carries the capture's intended-vs-achieved counts
(`fingerprints_json.capture_summary`).

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
(the approved gate@8 receipt `stage8_approval.receipt_json` is authoritative; a note here or a
past-conversation breadcrumb is NOT — a terse imperative from present-me to future-me is an instruction
stripped of its rationale, and future-me fills that gap with fresh probabilistic judgment) and the
script's own guards (benchmark wall, TOCTOU, REQ-147 same-vintage staleness, REQ-026 temporal window,
foreign-collision fail-loud) as the ONLY legitimate gates. When an outcome is wrong or fragile, fix the
**pipeline** (a guard, a metadata gap) — never hand-fix the district. **A LOGGED human override is fine
and auditable** — a named human takes responsibility; what's barred is the unlogged hand-fix.
(2026-07-23, Ian.)

**Three batch types (Stage 1):** `first-run`, `follow-up`, and `benchmark` (the 27 curated-GT districts
injected as `batch_00000` — permanently walled off from Stage-9 writes and funnel/enrichment stats; see
`STAGE1_QUEUE_DESIGN.md` §2h).

**Ground truth, hand-verified (gross, per-school):** `data/benchmark/gt_curation_*/gt_proposals.json` —
940/943 schools human-verified across `batch_00000`'s 27 districts. Process: council *proposes*, human
*verifies* (REQ-059). **This set is FIXED — gate@8 approvals do NOT append to it**: Stage 9 writes to the
LCT production DB, never into the GT corpus, and no code path does otherwise. What grows is the
**confirmed-fact base** — every gate@8 approval accrues a `stage8_approval` row + a frozen
closing-argument receipt, and more confirmed facts means more to *learn from and improve with*, realized
as pipeline-improvement work, not as a GT write (Ian, 2026-07-16). The archived
`data/archive/gt-benchmark-20260622T152627Z/` is the OLD noisy pre-pipeline output — the motivation for
the pipeline, NOT a clean baseline; never use it as a yardstick.

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()` +
`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 vision (reads JS/image/scan pages
all text paths miss). Trigger is "did the cheap reader recover usable content," not format.

**SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory
minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition
path. See `INSTRUCTIONAL_TIME_HARVEST.md`.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Keys in gitignored
`config/secrets.local.json` + `.env`. Requirements are tracked in `docs/REQUIREMENTS.yaml` (some
superseded/retired — read that file's own status column, never a list or a ceiling here). **The ledger is
ENFORCED** by `tests/test_requirements_yaml_hygiene.py` (18 checks): five statuses only, `type:` is the
altitude axis (`principle` exempt from the evidence rule), delegation is `enforced_by:`, `tested` must
cite a resolvable test, no phantom REQ ids in the ledger OR in `infrastructure/`, and `last_updated`
must not lag the newest entry. Adding a REQ: spec/invariant only — a review finding AMENDS the REQ it
belongs to rather than getting its own.

---

## Fresh-session essentials

**Start:** `/catchup` → `pip install -e .` → **Docker up** (`docker-compose up -d`) → verify the
baseline. Fresh clone also needs `git config core.hooksPath .githooks` and poppler/tesseract/ghostscript
for Stage 4 (`GETTING_STARTED.md` §1a/§1b).

**Verify the baseline — expected counts live in `GETTING_STARTED.md` §3, which is their ONE home.**
`lint-imports` + `pytest -q -m "not integration"` is the fast gate; add `pytest -q -m govdb` (Docker up)
and `npm test` in `infrastructure/scraper` when touching those layers. A count that DROPS is the signal;
they grow with every merged PR. Stage-5 re-ingest (~8.5 min, only after a scoring change or new
captures): §3a.

**Console:** `python3 -m infrastructure.acquisition.process_governance.server` → :8005. Scratch servers
go on **:8015 — never :8005**, Ian's working console. Playwright-verify UI work against real records
before shipping visuals; runbook, specimen records, and the clone-isolation trap (REQ-176):
`GETTING_STARTED.md` → "Running the governance console".

**Precious state:** `label` (incl. `facets_json`) / `cluster_split` / `followup_flag` / `handoff` + the
gate@8 human-judgment tables (`stage8_approval` incl. frozen receipts, `band_exclusion`,
`human_added_fact`, `slot_assignment`, `gate_mode`) live in the governance DB; `handoff_<hash>_<ts>.json`
under `data/acquisition/handoffs/` is immutable; `saved_view` holds UI prefs. The tracked
`.githooks/pre-commit` sweeps the git-backed JSON twins into every commit — **so any commit carries
whatever console state is live at that moment.**

**Ian drives the console; prepare and verify, don't execute stage runs.** Exceptions: the Stage 9 CLI,
the #716 replay, and the read-only measurement scripts.

**Operator CLIs:** `python3 -m infrastructure.acquisition.stage9_incorporate <did> [--dry-run]` (Stage 9
fires automatically on gate@8 approval — the CLI is the recovery/backfill path) ·
`…process_governance.stage8_sendback route <did> --route 8->1|8->6|unrouted [--dry-run]` ·
`…stage8_aggregate.rereview [<did> …]` · `…scripts.analyze.per_grade_lct_sample` (sign-off preview).

**Measurement scripts** (rerunnable, read-only, import the LIVE functions):
`docs/technical-notes/production-quality-control-research/` — see its README for the standing
watchdogs; each script's docstring carries its own check-map, so run the script rather than trusting
any summary of it.

**Current status (2026-08-25): tracker triage + Wave 0 hygiene COMPLETE — no code changed.**
All 11 epics and every open issue were re-validated against live code and the governance DB.
Open issues **98 → 91**, `sev:major` **12 → 9**, epic orphans **17 → 0** (every open non-epic
issue now has a parent). Closed 7 (#333 #228 #444 #99 #224 #261 #262); re-scoped #623 to
writer-only-deferred; #617 now carries its own closure condition; #706/#482 checklists replaced by
graph-as-truth; #80/#96/#128/#482 marked standing homes. Baseline GREEN: `lint-imports` 4 kept /
0 broken, `pytest -q -m "not integration"` **2490 passed, 1 skipped**. Prior milestone: PR #920
(#670/REQ-189 failed-latest veto + the `CAPTURE_SUMMARY` gov_db contract) and PR #902 (#717
gate@6 already-extracted delta, REQ-186). Full narrative: `docs/PROJECT_HISTORY.md` 2026-08-24
entry + Part 6.

**Five measured findings that change what to do next — three overturned my own triage plan:**
- **#823's remedy is unreachable as designed.** `MAX_TOKENS_CEILING = 32000`
  (`common/model_families.py:127`, applied at `:163`) clamps every call — proved:
  `size_max_tokens(65535) → 32000`. A 65,535-token council would be issued 32k and *measured as
  65k*. Raising that constant hits the ~86% of traffic unrelated to overflow, so it needs its own
  justification; the raster→image-council path reaches 32,768 with no change.
- **#115's demand trigger has NOT fired.** Live DB: **0** Drive *folder* URLs, **0**
  `needs_oauth_reauth`. The 50 Drive/Docs records are opaque `/file/d/` links = **#871's**
  population. #871 should land before #115 is reconsidered.
- **`batch_00044` was stranded, but NOT by the deferral path — RECOVERED 2026-08-25.**
  `stage5_ingest_deferred` events = 0; all 8 districts reached Stage 4 and the 14:32 recapture
  landed clean — Stage 4 was simply never re-run. The batch-wide deferral chain is real *as code*
  (`server.py:1978-1985`, whose own comment says "the autoflow chain has no later run"), but this
  is not its proven instance. **The prescribed remedy ("Stage 4 → Run") turned out to be
  unexecutable — see #921**, and recovery was a full `build_signals --assert-floor` re-ingest.
- **Stage-5 ingest state is DISTRICT-scoped, not batch-scoped** (measured 08-25): `record` has no
  batch column, `label` keys on `rec_key`, and `ingest_batch(district_ids)` already loops
  `ingest_district` per district — the name is the only batch-shaped thing about it. **42% of
  districts (73/172) appear in >1 batch**, max 6. So "re-ingest a batch" is a misleading label on
  a district-grained operation; district is the correct unit, with a batch as a *selector* that
  expands to districts.
- **CLAUDE.md was wrong about batches 46-57** — they are `follow-up`/`redo=True`/**approved**, not
  "12 first-run drafts at gate@1". **There is no first-run batch pending; the last was
  `batch_00036`, 2026-07-28.**
- **#616 role 2 is DONE** (`discover_stage2.py:673`, `process_stage4.py:482`);
  `stage4_process/headless.py:217` is the #347 self-heal (role 1 KEEP), not a leftover.

**Next (RESUME HERE — 2026-08-25). Wave 1 is next; Waves 2-4 in
`docs/scratch-paper/2026-08-25-fresh-triage-and-validation-batch-plan.md` (untracked — scratch-paper
is gitignored).**

1. **DONE 2026-08-25 — `batch_00044` recovered.** All 8 districts now fully ingested (0 URLs
   missing, 0 extra; ADAIR `2905790` was 13 short, HUNTINGTON `4824000` 12). Verified by
   `docs/technical-notes/production-quality-control-research/2026-08-25-batch44-ingest-recovery-measure.py`.
   **The plan's named action — "Stage 4 → Run" — was never executable**: at `resolved == total`
   `stage4.js:78` (`canRun = retriable > 0`) withdraws the Run control, and that is the *only*
   trigger for `_ingest_stage5_if_complete`. Filed as **#921** (epic #706). Recovery was instead a
   full `build_signals --assert-floor` re-ingest (Ian's call: one scoring vintage corpus-wide beats
   per-district vintages coexisting). **`batch_00044` still has 0 `stage=5` events and that is
   expected** — the CLI bypasses the bookkeeping that writes the marker; that gap is #921's
   remaining scope, NOT a failed recovery.
2. **#916 — live `sev:major`, epic #706** (body amended 08-25: its "Stage 4 skips the district"
   claim is FALSE — ORANGE was processed; the real cost is the batch-wide ingest stall above).
   Fix: wrap `_run` in `except subprocess.TimeoutExpired`, then run the four checks that already
   exist (returncode · manifest existence · `CAPTURE_SUMMARY` presence · count match) and accept a
   valid manifest with its real outcome. Falsifier-first. **Audit the Stage-2 wrapper for the same
   short-circuit before fixing only this one** — #670's Stage-4 twin was real, so this shape has
   recurred twice.
3. **Then the first-run validation batch** (5-6 small districts:
   `python3 -m infrastructure.acquisition.stage1_queue.queue_batch 58 --n 6 --dry-run`). Rationale:
   38 PRs merged since the last genuine first-run batch, and a redo batch **cannot** substitute —
   it seeds capture from the prior manifest (#174), so #670's ordinary-batch veto branch and the
   `CAPTURE_SUMMARY` contract have **never executed in production**. Land #916 first (it is the one
   failure mode that would stall the whole batch at Stage 4). Stage-by-stage runbook in the plan
   file; autoflow is follow-up-only.
4. **#620 stays OPEN until all 27 are written** (Ian, 08-25). **16/27.** The 11 left:
   **gate@8 review (4)** Orange · Cleveland · West Ada · Lincoln; **gate@5 tagging (6)** Baldwin ·
   both New Havens · Cedar Rapids · Mobile (69 of 141 unlabeled) · Lewiston (25 of 35);
   **blocked (1)** Broward, on #686. Two live findings unchanged: **Orange is `output_overflow`**
   (6 accepted / 118 unresolved — Council-Lab-gated, see #823 above, NOT a review error);
   **Cleveland returns a degenerate fact** (0 accepted, twice on 08-25) — **check #707 before
   re-dispatching** or a re-send yields the same nothing.
5. **Path to epic #92:** #614 (REOPENED — never built: no `stage9view`, no `stage9.js`; re-scope to
   the REPORTING half, since #682's auto-write means approved/written sit at parity 51/51). Then
   #640 + #625, then **#617 closes at #620's 27th write**. #708 re-check AFTER — fresh extractions
   widen its thin `identity_json` coverage on their own.
6. **#723 track:** #622 → #645 → #624, plus #901. #622 now owns BOTH renames + #623's resolver, and
   inherits three named pins. **#645 to watch:** the frozen handoff's per-record payload is the
   SPEND path's only sent-rep source. **#901's trap:** enumerate the 20 undeclared consumer edges
   or explicitly grandfather them.
7. **Console/measurement queue:** #888 (RE-MEASURE first via
   `2026-08-23-leftpane-vs-stageview-measure.py`) · #887 (Ian's design call) · #890 (Stage-4 tool
   timing; prerequisite to the #890/#891 redundancy finding) · #260 (36 actor literals → one
   accessor + a pin) · #449 (`n_bundled || 1` renders 0 as 1).
8. **Blocked on Ian's design calls:** #685 (the naive reveal recovered NOTHING — the vendor
   open-state class and `max-height` are load-bearing) · #871 (the gate must be able to KEEP an
   off-domain document first; now also gates #115) · #917 (5→1 is per-BATCH but realized
   per-DISTRICT) · epic #80's live-spend experiments (#823-#825).

**Resume essentials:** `pip install -e .` · `docker-compose up -d` (Docker Postgres — never
`brew services`) · verify with `lint-imports` (expect 4 kept / 0 broken) + `pytest -q -m "not
integration"` (2490 passed); add `pytest -q -m govdb` and `npm test` in `infrastructure/scraper`
when touching those layers. Console: `python3 -m
infrastructure.acquisition.process_governance.server` → :8005 (scratch servers on **:8015**).
Expected counts live in `GETTING_STARTED.md` §3 — their ONE home. Governance DB import is
`from infrastructure.acquisition.common import db as gdb` (NOT `gov_db`); council configs are at
`common/config/council_configs.json`.

Ian drives the console; prepare and verify, don't execute stage runs (Stage 9 CLI, the #716
replay, and the read-only measurement scripts are the exceptions). *Falsifier unchanged: if any
district needs a hand-edit or a re-adjudicated gate@8 call, the mechanism is wrong — fix the
pipeline, not the district.*


**Standing method rules** (the operative rules; consolidated instance catalogs + per-instance
detail now live in `docs/PROJECT_HISTORY.md`'s 2026-08-24 entry and the dated entries it indexes):

- **Measure the thing before fixing it** — 17 instances of an issue's (or review finding's)
  proposed fix overturned by measurement (#691 → #885). Re-read an issue's premises against
  today's code before implementing (#672); a "design question" can be a wrong predicate (#671);
  close unreachable-in-practice findings as not-bugs WITH pins (#852/#868); re-run the measurement
  after the fix it motivated; before calling a divergence a bug, check whether it is INTENTIONAL
  (#841); a fix can remove a failure's VISIBILITY instead of the failure (#792); a marker without
  a consequence is decoration (#793).
- **Implemented-twice drifts** — 11 instances. ONE exported function in the base layer per rule
  (REQ-182), never a test locking two copies into agreement; a CLIENT mirror counts as a call site
  (pin it member-for-member); an identity assertion locks the FUNCTION, not its INPUTS — the input
  construction must be one function too, asserted at the call sites (#846).
- **A measurement that cannot fail is not a verdict** — 9 shapes. Every measurement script carries
  an explicit `NOTHING MEASURED` verdict instead of a green zero on an empty sweep; score on the
  axis that decides the question and measure the COMBINED effect; an identity assertion about
  CONSTANTS proves nothing about BEHAVIOUR (#866).
- **Blast radius is part of the fix** — commit the rerunnable script, never the recollection
  (#865/#870); a reassuring sentence in a comment is a claim — measure it or delete it. A
  measurement script is EVIDENCE held to the standard of what it measures: import the production
  predicate, never approximate it (#879), and a PROXY must have the property under test (#873).

**Schema invariant (bit us on PR #641):** a `_PRECIOUS_ALTERS` column's DDL must be declared TWICE,
identically — a SQLAlchemy `default=` never reaches the DDL, so a fresh `create_all()` DB diverges
from a migrated one and fails raw `text()` INSERTs **on CI only**. Always pair with `server_default=`.
Enforced DB-free by `tests/test_precious_alters_parity.py`. **Verify a new precious column against a
THROWAWAY governance DB — the local migrated one tests the path that isn't broken.**


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
| SEA integration guide | `docs/state-integrations/SEA_INTEGRATION_GUIDE.md` |
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
| Data sources, SEA integrations, ID crosswalks, complex districts | `docs/DATA_SOURCES.md` · `docs/state-integrations/SEA_INTEGRATION_GUIDE.md` |
| Data methodology (LCT, sampling, exclusions, temporal) | `docs/METHODOLOGY.md` |
| The acquisition pipeline + per-stage design notes | `docs/ACQUISITION_PIPELINE.md` (map) → `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` |
| Governance / state model / gate model / console | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md` |

**Token Efficiency:** load only what the task needs.

---

## Critical Rules

Data rules 1-5 are enforced in code (`COVID_EXCLUDED_YEARS`, the WAF one-attempt predicate, the
temporal-span migration check) and restated in `GETTING_STARTED.md` §Critical Rules. The two that are
purely behavioural — and therefore only live here — are 6 and 7.

1. **Docker Required**: `docker-compose up -d` before any DB operation. Never `brew services start postgresql` — `.env` points at Docker's Postgres.
2. **COVID Data Exclusion**: Never use 2019-20 through 2022-23 data
3. **Security Blocks**: ONE-attempt rule for Cloudflare/WAF-protected districts
4. **Temporal Validation**: Data from multiple sources must span ≤3 years
5. **Raw Data**: Never modify files in `data/raw/` (convention — nothing mechanically stops you)
6. **Data Verification**: ALWAYS verify data exists in the database before claiming enrichment counts. Never trust dispatch documentation without database verification.
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
