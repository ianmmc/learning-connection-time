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
`config/secrets.local.json` + `.env`. Requirements are tracked as REQ-001…184 in `docs/REQUIREMENTS.yaml`
(some superseded/retired — read that file's own status column, never a list here). **The ledger is
ENFORCED** by `tests/test_requirements_yaml_hygiene.py` (18 checks): five statuses only, `type:` is the
altitude axis (`principle` exempt from the evidence rule), delegation is `enforced_by:`, `tested` must
cite a resolvable test, no phantom REQ ids in the ledger OR in `infrastructure/`, and `last_updated`
must not lag the newest entry. Adding a REQ: spec/invariant only — a review finding AMENDS the REQ it
belongs to rather than getting its own.

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

**Current status (2026-08-24 evening): PR #920 OPEN (`fix/670-loud-capture-timeout`) — #670 done,
both halves, closes on merge (REQ-189).** The failed-latest veto: a district whose latest
capture/process state_event is `failed` never renders `done` — any batch type, populated artifact
or not — and the Stage-4 twin was proven real (its comment claimed the state couldn't exist) and
fixed the same way, both sets including the upstream capture gate. Capture completeness is now a
gov_db fact: Node's `captureSummary()` → the `CAPTURE_SUMMARY` stdout line → a loud raise on
missing/mismatch → counts stamped on the stage-3 completion event
(`fingerprints_json.capture_summary`). Receipts stay pipeline-write-only (AST-pinned). #623's
writer half DEFERRED by design (commit-before-receipt ordering); its resolver re-homed to #622,
which inherits three named pins — issue comments posted on both. Earlier today: **PR #902 MERGED**
(#717 gate@6 already-extracted delta live, REQ-186; REQ-187/188 backfilled) + the
documentation-tower sweep (996dba0; defects filed as #918/#919, not silently patched). Ian's
console drained #620's send-back tail same-day: Essex Westford through Stage 9 (written); Orange
County re-captured cleanly; Broward/Cleveland re-run to Stage 5, gate@5 tagging in progress.
Batches 46-57 (12 first-run drafts, 34 districts) sit at gate@1 — the exact population the #670
veto now protects. Baseline GREEN (see resume-essentials). Full day narrative:
`docs/PROJECT_HISTORY.md` 2026-08-24 entry.

**Next (RESUME HERE — 2026-08-24). Path to epic #92 unchanged (#92 → #614; #723 is its own track
and does not gate it).**

1. **Merge PR #920** (#670 closes on merge). The first post-merge Stage-3 run is the live proof of
   the `CAPTURE_SUMMARY` contract — expected uneventful (both falsifiers ran red-then-green, plus
   a real-browser smoke), but watch it. Batches 46-57 should run Stage 3 AFTER the merge.
2. **#620 tail residue, console-driven, no new code:** dispatch Broward/Cleveland (+ Orange
   County) at gate@6 once gate@5 tagging completes — Essex Westford is already written (Stage 9).
   Then the 5→1 composer for West Ada/Lincoln/Baldwin, plus Lewiston and Mobile.
3. **Close in order:** **#614** (Stage-9 console view — **#92 closes here**, build proven by 12+
   production writes and growing); **#640 + #625**, then **#617 closes** at #620's 27th write;
   **#708** re-check AFTER — the campaign's fresh extractions widen its thin `identity_json`
   coverage on their own.
4. **#723 track: #622 → #645 → #624, plus #901.** #622 now carries #623's resolver half and three
   pins named in its issue comment (the #670 veto falsifiers · the ordinary-batch disk-rule test
   it must consciously rewrite · the receipts-write-only AST pin), plus a new datum: the
   completion event's `capture_summary` counts — district-grain done-ness with no batch conjunct.
   **#645 is the one to watch:** the frozen handoff's per-record payload is the SPEND path's only
   sent-rep source (a data-model gap — `extraction`/`handoff`/`school_fact`/`extraction_request`
   none hold the rep list); when it lands, `already_extracted_reps` switches to the DB in ONE call
   site (REQ-182). **#901's trap unchanged:** the retrofit must ENUMERATE the 20 undeclared
   consumer edges or explicitly grandfather them — a green suite over an unenumerated baseline is
   a measurement that cannot fail.
5. **Console/measurement queue:** **#887** (in-flight vs stranded badge — Ian's design call, epic
   #96); **#888** (left-pane fix — RE-MEASURE first via
   `2026-08-23-leftpane-vs-stageview-measure.py`, the corpus moves under it; the residue is
   #622's job, not a second disk check); **#890** (Stage-4 tool timing, epic #128 — the seam is
   `process_record`'s `add()` closure; prerequisite before acting on the #890/#891
   tool-redundancy finding, since cost is unmeasured and the most valuable tool is likely the most
   expensive).
6. **Blocked on Ian's design calls:** #685 (active-tab-only capture — NB the naive reveal
   recovered NOTHING; the vendor open-state class and `max-height` are load-bearing); #871 (geo's
   second job, REQ-184 `proposed` — the gate must be able to KEEP an off-domain document first).
   **Ian's call, live spend:** epic #80's experiments (#823-#825), now with batch_00043's six
   fresh GT-district extractions to work against.

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

**Cloning the governance DB does NOT isolate the git-tracked JSON twins (REQ-176).** They are files
on disk and every exporter rebuilds them WHOLESALE from the connected DB's log, so a scratch console
on a clone writes its throwaway drafts into `district_status.json` (this happened during #822's
verification) and a scratch server on an EMPTY governance DB would blank all twelve — measured, the
tracked status file holds 175 districts and an empty-DB export produces 0. `guard_tracked_backup`
now quarantines under EITHER cause (pytest, or a non-canonical DB) with a one-time note.
**Seeing that quarantine line while running against a clone is the guard working.**
**Outstanding:** Playwright-verify the gate@6 + gate@1 console changes (incl. #853's third `benchmark-only held` badge arm — seed a clone with an `out_of_window` gt:// label), **#869's gate@5 "densest" badge** (it now excludes chrome, so a footer with unique times must read `adder`, not `densest` — `0103390:fb71b7cc63` is the record, footer 12 times vs page.txt 0; source-pinned only so far), #647's Stage 2/3/4 status/Run
control, AND **#840's new gate@5 page-scoping card** (★ harvest / ◆ floor markers, `data-scoping=`
DOM hook — static-source-pinned only so far); #667's gate@8/#662's gate@5 badges, #684's staff-day
surfacing, the three gate@8 arrows, and **#673's gate@5 vintage surface** ARE verified — rerunnable
verifiers `infrastructure/scraper/verify_684_console.mjs`, `verify_682_console.mjs`,
`verify_822_console.mjs` (#822's gate@6 overflow badge + gate@7 degraded banner, 15/15 — it also
documents the clone-and-seed runbook, since the gate@7 banner reads a STORED column and every live
row is `{}` until a post-#822 Stage-7 run happens), and **`verify_673_console.mjs`** (12/12 PASS on
the real TAOS records; its own first run caught a live bug — see the 2026-08-22/23 history entry).
The pattern to extend, next to #887/#888.
**Deferred by design (epic #128):** #642 (content-derived document vintage) and #643 (the Stage-3
render-facts probe; rides #623's Node seam — now ALSO the spine of epic #864). **Retired, do not do:** Phase 2e's retroactive
`dispatch_type='benchmark'` tagging — arm 2 derives it. Banked routing: #112 → epic #128. Parked:
#475/#476, #103 (+#110); the SEA integration follow-up (~9 states) is an opt-in backlog item — ask
Ian before filing. Documented-in-code deferrals: `_satisfied_bands_now` batching; the #522 guardrail's
per-rep keyword/table attribution (needs a server payload change); JS behavioral tests (no JS
harness); the remediation-receipt exception is not STAGE-scoped (30-day expiry since 2026-07-20);
attribution v1 reads each district's LATEST candidate plan; the `stage6_handoff/requests.py:17-18`
docstring falsely claims Stage 7 "reads ONLY the flagged pages" — the `pages` hint never scoped
content (the slice FILE is the scoping), a live source of wrong inferences worth a one-line issue.
Resume-essentials (re-verified 2026-08-24 on `fix/670-loud-capture-timeout`; post-#920 numbers —
baseline GREEN, no known-red command; the integration figures carry from the same-day `main`
verification, unchanged by #920): `pip install -e .` → Docker up (`docker-compose up -d`) →
`git config core.hooksPath .githooks` (fresh clone only) → `lint-imports` (expect **4 kept/0
broken**) + `pytest -q -m "not integration"` (expect **2490** pass, 1 skipped [pyarrow]) +
`pytest -q -m govdb` (expect **409**, Postgres up) + `pytest tests/test_*_integration.py` (expect
**257** pass, 149 skipped) + `cd infrastructure/scraper && npm test` (expect **105**) +
`flake8 . --count --select=E9,F63,F7,F82` (expect **0** — CI's blocking lint; the vulture whitelist
is `per-file-ignores`'d for F821). NB `pytest -m integration` also carries a NETWORK test
(`test_model_windows_integration.py`, #809) that re-fetches OpenRouter — skips cleanly offline,
excluded from the default suite. **Full re-ingest is ~8.5 min**
(`python3 -m infrastructure.acquisition.stage5_filter.build_signals --assert-floor`) — needed only
after a scoring/config change or new captures; run it with `--assert-floor` so a recall regression
rolls back inside the transaction; `pg_dump` the precious tables first (governance DB is
`postgresql://…@localhost:5432/governance`, separate from the LCT DB).
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
read-only, import the LIVE functions)** — all under
`docs/technical-notes/production-quality-control-research/` (filenames end `-measure.py`); each
script's docstring carries its own check-map (C1/C2/…), so run the script, don't trust a summary:
`2026-08-17-{per-page-uncap,timebearing-floor}` · `2026-08-18-output-overflow` (#822) ·
`2026-08-18-roster-hit` (#826) · `2026-08-18-segment-main-alternate` (#841 — re-run post-re-ingest;
S1 should report 0 NULL) · `2026-08-19-chrome-first-send` (#862/#870; C3 is #863's watchdog) ·
`2026-08-21-read-timing-split` (#863; C5 is #873's login_wall watchdog — corpus property clears
only on RE-CAPTURE, `NOTHING MEASURED` until then is the honest state) ·
`2026-08-21-geo-ladder-regression` (#672 — quote the plan-aware column, never the raw count) ·
`2026-08-22-batch-done-predicate` (#671/#885 — C5's cross-batch window must stay 0) ·
`2026-08-23-leftpane-vs-stageview` (#888 — re-run before fixing; the corpus moves under it) ·
`2026-08-23-tool-redundancy` (#890/#891 — verdicts are REDUNDANCY, never speedup, until #890 lands
timing) · `2026-08-24-failed-latest-veto` (#670 — C2 must stay 0 violations / 0 newly-asserted).
Full detail: `docs/PROJECT_HISTORY.md` (dated entries), `STAGE1-9_*_DESIGN.md`,
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
