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
path. See `docs/INSTRUCTIONAL_TIME_HARVEST.md`.

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

**Current status (2026-07-16):** **Epic #119 CLOSED** (Stage 7 quality) and **Stage 8 / gate@8 BUILT**
(#89). **Epic #106 (Stage 5/6) is the live work — design-complete, ready to build.** This session did two
things. (1) **Measured the recency question and refuted a written projection** (`STAGE5_FILTER_DESIGN.md`
§3a **obs. 6**): a stale eligibility veto removes ~0 false-sends for a 17-target cost and *raises* the
false-send rate — obs. 5's "stale = clean unconditional veto / 53-for-6" was mined from human notes, not a
reproducible signal, and never held. Recency is now two rules: a pre-2017-18 **validity floor** (HOLD,
REQ-026 correctness, ~0 money — #241) + **prefer-recent dispatch ranking** (the money half — #107). The
measured money lever is **#519** (re-measured, then closed→**#528** this session), NOT #515. (2) **Ran a full code-grounded doc-tower audit** (7 commits):
corrected the tower to present-state (gate@8 was documented as "unbuilt" in 3 docs; STAGE7 predated #119;
CLAUDE.md had two failing commands), normalized `REQUIREMENTS.yaml` (152 reqs, backfilled REQ-152 for PR
#509), curated memory 23→19 with a **no-`type:project`-status-memories** rule, and filed 4 code-side defects
as issues (#523/#524 Stage-2 docstrings, #525 `gate_mode.py:35`, #526 Stage-2 reads receipt-not-DB).

**Next (RESUME HERE — 2026-07-16): epic #106. The #519 scope call is RESOLVED — #519 closed as
refuted-premise, replaced by #528** (Ian, this session). The buildable-without-a-decision work is the
recency signal (**#241/#107's `content_school_year` extractor** — reuses `school_year.py`, no vocabulary
call, per obs. 6), which is also the shared prerequisite both recency issues consume. The full slate, all
filed as #106 sub-issues:
- **#528** (successor to closed #519) cut confounder false-auto-sends where the combiner can reach them.
  The recompute broke #519's "~40 false-sends, tune the weights" into three mechanisms: (1) **`board`/
  `sports` fire on ~0 tier-A false-sends** — a firing-condition problem (they need neg-class *dominance*,
  which a tier-A page can't meet), unreachable by any weight → **forked OUT** of #528 (own issue or #226);
  (2) **`news_feed` fires on MORE real targets (30) than false-sends (21)** — a blanket weight-up is
  net-negative; the lever is `news_feed × no-strong-positive-structure`, a combiner INTERACTION gated on a
  "what separates the 21 from the 30" separating analysis (explore-first) — **IN #528**; (3) **`calendar`
  (5 gain / 0 cost) is the one clean scalar win** — **IN #528**, ships now. Actionable ceiling = 26, not ~40.
  Facet precision (live #108): `news_feed` 0.89 / `board` 0.52 / `calendar` 0.46 / `sports` 0.32 — the old
  "0.13–0.18" doesn't reproduce. `lf_nonstandard_day` 0.09 stays out of scope (frozen grab-bag = #207).
- **#515** Stage-6 confounder eligibility vetoes — **the "24.5%→~15% money lever" headline is WRONG** (§3a
  obs. 6, measured 2026-07-16: stale contributes **0** — it removes 1 false-send for 17 target-vetoes and
  *raises* the rate 24.1%→24.8%; staleness and target-absence are near-independent). #515's remaining
  basis was the conditional irregular-day veto, but **#207 (its enabling facet) was closed superseded
  2026-07-16** — the irregular-day/wrong-schedule distinction now lives as a coarse facet+detector folded
  into **#522** (per [[project-stage5-labeling-serves-learning]]). So #515 = the *eligibility-gate* question
  only, sequenced **behind #522** (the facet must exist and be learnable before it can gate); news/calendar/
  board/sports stay SOFT (never gates — §3a obs. 5). Shares the eligibility seam with **#83** (narrow-to-hub)
  — they collide in the same file.
- Recency (**#241**/**#107**, re-scoped 2026-07-16): **#241** = a pre-2017-18 validity floor, semantics =
  **HOLD** not hard-reject (Ian) — a **REQ-026 correctness guarantee floored on the CRDC 2017-18 federal
  input, which pays ~0 money**; never justify it on spend. **#107 stays the parent** (§3G: "complementary,
  not duplicates") — it builds the shared `content_school_year` signal (which **does not exist yet**) +
  **prefer-recent** dispatch *ranking*, the half that actually saves money (rank siblings ≥ floor, send the
  newest, hold the rest — zero recall cost by construction).
- Console (the labeling-that-drives-learning surface, per [[project-stage5-labeling-serves-learning]] —
  build order **#522 → #521 → #516**): **#522** (content-adaptive center-pane default: show what the machine
  read; PDFs → embedded viewer, rasters demoted to "available"; **now also carries the folded-in confounder
  facet-vocabulary decision** — one coarse "wrong-schedule / not-the-regular-day" negative, not 6–7 facets),
  **#521** (relevance-density bookmarks + heat-strip for long reps — #522's long-doc mechanism; build the FULL
  version incl. confounder negative-weighting then dial back, per [[feedback-build-best-then-dial-back]]),
  **#516** (FP/FN error-lanes — disagreement is the primary product of labeling — + rec_key as the searchable
  left-pane entry-ID + right-pane reorder).
- Recall: **#517** (schedule_link_only affordance), **#518** (capture-fidelity leak: login walls/0-byte PDFs/truncation, Stage 3/4).
- Older #106 items still open: #107/#109/#110/#75/#83/#192/#226. Triage from the 2026-07-16 epic
  read-through: **#192** is a cheap measured win (0/275 handoff reps carry `n_times` → the gate@6 cost preview
  mis-estimates). **#226** (URL-level `feed`/`live-feed` negative, extends `lf_news_feed`, no new label) is the
  structural signal #528's news_feed interaction — and its forked-out board/sports mechanism — would consume;
  fold the board/sports fork into #226 or spin its own issue. **#110** is blocked behind the parked Council
  Lab (#103/#80), not merely deferred. **#75** is an underspecified triage note — re-scope before building.
  **Closed superseded 2026-07-16** by [[project-stage5-labeling-serves-learning]] (per-confounder detector-build
  issues fail the "a detector must measurably learn from it" test): **#207** (nonstandard-day), **#223** (summer)
  — both folded into #522's facet-vocabulary; **#512** (snake) — its reader-routing/small-voter context-ceiling
  remnant re-homed to Council Lab **#80**, not dropped. Remaining vocabulary call gated on Ian: #107's Axis-3
  `content_school_year` facet (the signal/extractor itself is unblocked).
Guardrail across the console work: the default view must NEVER silently contradict the score (surface a pointer to the scored evidence). Then the sequence continues: **#111** (Stages 1-4) → liveness gate → **#479/#480** → **#92**. Parked: #475/#476, #103/#80 (Council Lab — `MODEL_FIELD_NOTES.md` + the #512 snake context-ceiling finding, re-homed as an #80 comment, are prep). Deferred-by-design from the #499 reviews (documented in
code, revisit on volume): batching `_satisfied_bands_now`'s per-district loads (`ANY(:d)` shape) once
the approved-request backlog grows.
Resume-essentials: `pip install -e .` → Docker up (`docker-compose up -d`) → `git config
core.hooksPath .githooks` (fresh clone only) → `lint-imports` (expect **4 kept/0 broken**) + `pytest -q
-m "not integration"` (expect **~1559** pass) + `pytest -q -m govdb` (expect **~226**, Postgres up).
For the #106 build, the measured findings + the exact design decisions live in
`STAGE5_FILTER_DESIGN.md` §3a **obs. 5 AND obs. 6 — read BOTH, in that order, before touching recency**:
obs. 6 refutes obs. 5's stale-veto projection with measurements on the real corpus and marks the superseded
bullets in place. **The trap it closes:** obs. 5's numbers were mined from *human notes* (records where Ian
had already written "too dated") — that is judgment, not a signal a detector can reproduce, which is why the
53/6 projection never held. Don't re-derive it. The per-issue specs are in the #106 sub-issues (#515–#522).
Full detail: `docs/PROJECT_HISTORY.md`, `STAGE8_AGGREGATE_DESIGN.md`,
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
