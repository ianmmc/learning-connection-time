# Stage 8 — Aggregate: present state & design (algorithm LIVE; standalone gate@8 BUILT #89, 2026-07-14)

> **Authority:** what the code does today. Two things are built and load-bearing: (1) the **aggregation
> ALGORITHM** (`stage8_aggregate/aggregate.py`) — live in `gate@7`'s read path since early July; and (2)
> the **standalone gate@8 console + approval write** (`#89`, shipped 2026-07-14), plus the `#499` slot
> program (PRs A–F, REQ-144…150) and epic `#478`'s human-judgment overrides. What is **still genuinely
> unbuilt: gate@8 **auto** mode**. The `8→1`/`8→6` back-edges shipped 2026-08-15 (#689 — §3c);
> approve→write shipped the same day (#682). The **Stage-9 write (#93) shipped 2026-07-21** (epic #92) — an approved
> district is now mechanically incorporated into the LCT DB (`STAGE9_INCORPORATE_DESIGN.md`).
>
> The algorithm is not a prototype awaiting a consumer. `stage7_run.py` calls `AGG.consensus_school_facts`
> and `AGG.district_bands_from_facts` in the production extraction flow (`stage7_run.py:172,179,224`);
> gate@7's district-detail endpoint calls `AGG.merge_fact_runs` then `AGG.district_bands_from_facts` on
> every read, and its left-pane counts re-implement the same merge rule as hand-maintained SQL checked
> against `merge_fact_runs` on shared fixtures so the two can't drift (comment: "the SQL twin of
> AGG.merge_fact_runs"); `council_lab.py` uses the same two functions for offline comparisons.
> **REQ-122** (`merge_fact_runs`'s cumulative-merge rule, status: tested): built to fix a gate@7 bug (#232 —
> a scoped retry could make an earlier run's solid facts disappear) and now gate@7's canonical merge logic.
>
> **The standalone gate@8** (§0a, §2 below) is BUILT: the review-queue + district-detail endpoints, the
> per-school override, the four human-judgment tables, the approve/send-back verdict with a frozen
> fingerprinted receipt, and the gate@8 calibration hook. It is the effective old "CP-C" — a human signs
> off the district's picture before the mechanical Stage-9 write (BUILT 2026-07-21, `STAGE9_INCORPORATE_DESIGN.md`).
> **Companions:** `ACQUISITION_PIPELINE.md` §8 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE.md`
> §11 (gates/console; §11e cyclic back-edges), `METHODOLOGY.md` (the metric: gross bell-to-bell, the mode).
> Upstream: `STAGE7_EXTRACT_DESIGN.md`. Downstream: `STAGE9_INCORPORATE_DESIGN.md`.
> **Update this when:** Stage 8's code behavior changes (the back-edges land, a precious table changes).
> Design turns belong in the change log at the bottom.

---

## 0a. As-built: the standalone gate@8 (BUILT #89, 2026-07-14)

**Console:** `static/stage8.js` ("gate@8, the 'closing argument'") + the `# Stage 8 / gate@8 — Aggregate`
endpoint block in `process_governance/server.py:2083-2462`. The pure closing-argument assembler is
`stage8_aggregate/closing_argument.py`; the approval write is `stage8_aggregate/approval.py`.

**Endpoints (all live):** `GET /api/aggregate/districts` (the review queue — production-fact districts whose
gate@7 loop is quiesced, badged with the latest gate@8 disposition via a LATERAL join on
`stage8_approval`; since epic #617/#660 (2026-07-26) it also SURFACES benchmark-provenance districts
rather than silently excluding them — see §2 below) · `GET /api/aggregate/district/{id}` (detail: `closing_argument` + `fingerprint` as the
review token) · `POST /api/aggregate/override` (per-school times override, reason required, validated through
`gross_from_times`) · `POST /api/aggregate/exclude` (+ `/restore`) · `POST /api/aggregate/human-add`
(+ `/remove`) · `POST /api/aggregate/slot-assign` (+ `/remove`) · `POST /api/aggregate/recover-band` (#473 —
stages a re-extraction of a named captured rep as a 7→6 request; spends nothing) · **`POST
/api/aggregate/decision/{id}`** — the verdict.

**The verdict flow (approve / send-back) is BUILT.** `aggregate_decision` → `approval.record_decision`:
dispositions `approved | sent_back` (`sent_back` requires a reason); it re-loads the closing argument
server-side and enforces `expected_fingerprint` (409 on a TOCTOU mismatch), freezes the receipt +
fingerprint, fires the gate@8 calibration hook (`gate8_decision_record`), and backs up the tracked JSON.

## 0b. The five precious gate@8 tables

Four are in `stage8_aggregate/models.py`; `gate_mode` is in `common/gate_mode.py`. All are registered for
`init_precious_schema()` and each has a JSON-backup writer swept into commits by `.githooks/pre-commit`.
(They arrive via `init_precious_schema()`, NOT a migration — see §3.)

| table | what it stores / why precious | key columns | written by |
|---|---|---|---|
| **`stage8_approval`** | one human gate@8 verdict per district; **authorizes the Stage-9 write and freezes the exact picture signed off** (auditability) | `disposition` (approved\|sent_back), `actor`, `reason`, `facts_fingerprint`, `receipt_json` | `approval.record_decision` |
| **`band_exclusion`** (#257) | a standing "exclude this school from this band" call; **district-grain so the knowledge survives a follow-up minting new fact rows** | `band`, `norm_school`, `reason` (req.) | `POST /api/aggregate/exclude` |
| **`human_added_fact`** (#474) | a hand-entered (school, band, start, end) — **last-resort when re-extraction can't recover a visible band**; requires a cited source | `band`, `norm_school`, `start_time`, `end_time`, `source_url` (req.) | `POST /api/aggregate/human-add` |
| **`slot_assignment`** (#499) | a standing human slot disposition (`assign\|reject\|confirm_extra`) the auto projection won't make; **moves which slot a vote lands on / the denominator** | `band`, `roster_school_id`, `norm_school_fact`, `disposition`, `reason` (req.) | `POST /api/aggregate/slot-assign` |
| **`gate_mode`** | per-gate manual/auto control; **upsert-only settings, never dropped** | `gate` (PK), `configured_mode` (null=inherit), `license_state` (#211) | `set_configured_mode` / `set_license_state` |

**band_exclusion** and **human_added_fact** are the human-judgment overrides: at gate@8 a reviewer can strike
a school out of a band whose membership is stale (correct observation, wrong band — the #257 grade-reconfig
case; the fact stays visible, struck-through, out of the mode) or hand-enter a fact with a required source
when re-extraction can't recover a band they can see (#474). Both are district-grain (survive re-extraction),
reversible-before-freeze via hard DELETE (history lives in the frozen receipts), and both enter the staleness
fingerprint.

**The frozen receipt (auditability north-star):** `stage8_approval.receipt_json` is the closing argument
frozen at decision time; `facts_fingerprint` is `closing_argument.fingerprint()` then. The fingerprint hashes
the *determination* (per band: the gross value + the sorted accepted schools, each carrying override /
exclusion / human-add markers, plus the band-exclusion and slot-assignment sets), deliberately excluding
volatile provenance. Staleness (REQ-147, the 2026-07-14 incident) re-hashes the **frozen receipt** under the
**current** `fingerprint()` and compares to the live hash — both sides one code vintage — so a
fingerprint-basis evolution can never fake staleness on an unchanged picture. A re-decision after a back-edge
is a new append-only row, never a rewrite.

Every decision (both dispositions) also drops a `stage8_aggregate` per-district audit receipt into the
capture dir (REQ-164, 2026-07-22 — always-stamped via `common/receipts.py::write_receipt`,
`approval.gate8_receipt_payload`), paired with an in-path `district_status.json` twin refresh — closing
the gap where the twin used to lag until an incidental later export.

## 0c. The #499 slot program (BUILT, REQ-144…150 all tested)

"Slots" (`common/slot_spine.py`, PURE — no DB/disk): each band's **live NCES roster** (never frozen) is
projected as slots, crossed with the band's included facts, so a coverage gap becomes an *identified school*
(an unfilled slot), not count arithmetic. Slot states: `filled` · `unfilled` · `ambiguous` (a fact key
collides with ≥2 slots — fills none, waits for a human) · `unmatched-extra` (a fact matches no slot — the
`confirm_extra` escape hatch) · `projected` (a band-grain statement covers an unfilled slot, REQ-146).
Resolution *weights, never overrides*: human disposition > exact 1:1 name match > intent-tie-broken
ambiguity; the Stage-2 discovery-intent prior tie-breaks but **never creates** a match. Consumed in
`closing_argument.build_closing_argument` (`SP.project_slots`), rendered by `stage8.js:renderSlots`. REQ
map: REQ-144 spine v1 + roster-drift (PR-A) · REQ-145 attribution + dispositions in the fingerprint (PR-B) ·
REQ-146 band-grain facts + conflict ladder as advice (PR-C) · REQ-147 staleness-from-receipt (PR-C review) ·
REQ-148 v4 `campus_names` (PR-E) · REQ-149 per-band SATISFIED signal, supersedes #90 (PR-D) · REQ-150 full
roster spine from gate@1, slot-grain pursuit, closes #499 (PR-F).

---

## 1. Purpose & boundary

The aggregation ALGORITHM turns the council's per-school `{start,end}` facts into **daily
instructional minutes by band** for a district: deterministic code computes `gross = end − start`
and the **per-band exact mode** across the band's schools (REQ-054; the metric = gross bell-to-bell,
240–510 min plausibility gate, REQ-055; cross-family consensus REQ-056 — all `status: tested`,
verified by `tests/test_aggregate.py::TestGross`/`TestMode`/`TestConsensus`). This logic lives in
`stage8_aggregate/aggregate.py` and is load-bearing for `gate@7` today (§0 above) — it is not waiting
on Stage 8 to matter.

The **standalone Stage 8** is the gate downstream of gate@7 (**BUILT #89, 2026-07-14 — see §0a/§0b**):
a human reviews/approves the council's extracted TIMES (`school_fact.human_determination`) before the
mechanical Stage-9 DB write — the effective old "CP-C." This scope was set by a 2026-07-10
decision (REQUIREMENTS.yaml REQ-120/REQ-121 notes): approving extracted times is explicitly a
**Stage-8** activity, deferred from gate@7, which only reviews/dispatches *requests* for extraction,
not the times themselves. `district_bands_from_facts` seeds the field this gate acts on:
each school entry carries a `human_determination` stub the reviewer fills in via `POST
/api/aggregate/override` (§1a). Completion grain = district × **band** (schools are instrumental;
governance §11d). The `8→1`/`8→6` back-edges are BUILT (#689, §3c): a `sent_back` district is routed by
the human at the gate, and the routing is recorded against the approval that caused it. (The mechanical
Stage-9 write, #93, shipped 2026-07-21, and fires on approval since #682 — §0/§3 note.)

## 1a. The live functions (aggregate.py)

`aggregate.py` currently contains **two eras of aggregation logic**. Grep across the repo (excluding
the module's own tests) shows the legacy functions have no live caller outside
`tests/test_aggregate.py`, `tests/test_schedule_aggregation.py`, and REQUIREMENTS.yaml — nothing in
`stage7_run.py`, `server.py`, or `council_lab.py` calls them. They are effectively superseded, kept in
place (with tests) rather than deleted; treat them as legacy unless/until they're formally removed.

**Legacy (vote-based) — no live caller:**
- **`council_school(votes, judge=None)`** — the original model: models vote `{band: minutes}`
  directly (not per-school start/end facts). Accepts a band value when >=2 cross-family votes cluster
  within `TOL`; falls back to a judge re-read, then to `None`.
- **`aggregate_district(per_school)`** — rolls a list of `{band: accepted_minutes}` per-school votes
  into a district value via `aggregate_band` (below).
- **`mode_stable(values, window=5, min_n=3, min_share=0.6)`** — an early-exit heuristic for large
  districts: stop sampling a band once the last `window` schools' cumulative mode (snapped to the
  `TOL` grid) has stopped changing AND that mode actually commands a plurality (`>= min_share`) of all
  values so far. The plurality check exists specifically so a mode that locked in early doesn't mask a
  genuinely scattered band where later schools keep disagreeing. No caller outside its own tests today
  (i.e. the early-exit is not wired into the live sampling loop).

**Current (fact-based) — live inside gate@7 today** (five functions: `consensus_school_facts`,
`district_bands_from_facts`, `aggregate_band`, `merge_fact_runs`, `detect_single_school_over_extraction`):
- **`consensus_school_facts(model_rows, judge_rows=None)`** — the production per-school consensus
  function (`stage7_run.py:172,179`, `council_lab.py:99,108`). Input is `{model: [{grade_level,
  start_time, end_time, school_name}, ...]}` per council voter (and optionally a judge's rows).
  Rows are grouped by `(band, normalized-school-name)` — school-name normalization uses
  `common.school_match.norm_school`, the SAME normalizer the Stage-7 GT validator uses, so the two
  must agree identically (REQ-117; and, since PR #247 deleted Stage 5's own separate duplicate, all
  three stages now share the one function — see `STAGE7_EXTRACT_DESIGN.md`). `norm_school`'s
  stripping rules were tightened in that same PR (suffix-anchored district-qualifier stripping,
  hyphen word-splitting, NFKD, ES/MS/HS): this grouping step is directly affected — e.g. "Meridian
  Consolidated School" and "Meridian School" now group as DIFFERENT schools here, where the old
  anywhere-strip wrongly merged their council facts into one consensus group.
  **REQ-173 (2026-08-15, #693/#721): before grouping, every voter/judge row's name is resolved
  against the district's NCES slot spine** (`school_match.resolve_school_identity`, fed by
  `context["roster_recs"]` — `consensus_context_for_district` threads it, so the #716 replay
  inherits it). A uniquely-resolved name groups under the ROSTER school's norm key (variant
  spellings meet: acronyms, grade-span suffixes, leading-initial artifacts, token subsets);
  2+ candidates = ambiguous, kept split and marked (never a guess — #681). After grouping, a
  school_id claimed under 2+ bands is band-adjudicated by roster placement: a multiband campus
  pools its cross-band votes and emits one fact per claimed-and-rostered band
  (`band_adjudication: roster_multiband`); a single-band-rostered school's wrong-band claim folds
  into the roster band (`roster_band`); an UNMATCHED name's cross-band singletons collapse to one
  explicit `band_disagreement` unresolved row (strict-degenerate names are exempt — they belong
  to the #245/#707 path). At emission, an unmatched name is screened for excluded school types
  (→ `unresolved` reason `excluded_school_type`) or survives marked `{"roster": "unmatched"}`.
  All marking persists via `school_fact.identity_json` (v5 additive column) for gate@8; the
  entire mechanism is context-gated — a no-roster caller (council lab) is byte-identical to
  pre-REQ-173 behavior. `grade_level` STAYS in the grouping key: the 2026-08-15 measurement found
  35 level-collapse districts (APOPKA ELEMENTARY/MIDDLE/HIGH all norm to `apopka`) where the band
  is the only discriminator between real schools. Full evidence:
  `learning-loop-reports/2026-08-15-693-721-roster-anchored-identity.md`.
  Within each group, the
  council reaches consensus on **START and
  END separately** (cross-family, `>=2` families within `TOL=15` min each) — same-family agreement is
  not consensus (REQ-056). On disagreement, an optional judge's `(start,end)` pair breaks the tie.
  `gross = end - start` is computed only after times are agreed, then gated to `PLAUSIBLE = (240,
  510)`. Returns `(accepted, unresolved)`: `accepted` is a list of `{band, school, start, end, gross,
  models, method}`; `unresolved` carries the raw per-model start/end strings (or an `"implausible"`
  reason) so a reviewer can see exactly where/why consensus failed — this is the bookkeeping gate@7's
  UI shows for unresolved (band, school) pairs.
- **`district_bands_from_facts(accepted)`** — the live per-band rollup (`stage7_run.py:224`,
  `server.py:1547`, `council_lab.py:125,127`) that turns `consensus_school_facts`'s accepted rows into
  the schema gate@7 actually renders: `{band: {gross_minutes, start_time, end_time, n_schools, method,
  schools: [...]}}`. Each school entry also carries a `human_determination: ""` stub — a field the
  aggregation logic already seeds but gate@7 doesn't yet let anyone write to; it's there for the
  eventual gate@8 review UI (§1) to populate.
- **`aggregate_band(school_values)`** — the shared exact-mode-with-mean-tiebreak primitive both
  `aggregate_district` (legacy) and `district_bands_from_facts` (current) call: the district value is
  the single most-common gross value among accepted schools; only on a genuine tie between two
  *distinct* values does it fall back to the arithmetic mean. This replaced an earlier version that
  returned a tolerance-cluster's mean center, which is NOT the mode (e.g. `{380:26, 390:2, 345:1}`
  wrongly produced 381 instead of 380 — the docstring keeps this regression case as its own comment).
- **`merge_fact_runs(facts)`** — the cumulative cross-run merge (REQ-122, #232), live at
  `server.py:1542` and mirrored as hand-checked SQL at `server.py:1416-1437`. Input is `school_fact`
  rows from ANY number of a district's production Stage-7 runs, each carrying `extraction_id` (run
  order), `band`, `school`, `status` (+ the v3 `school_year` reading). Per `(band, school)`, the merge
  rule, in precedence order:
  - an **accepted** fact beats an **unresolved** fact for the same school, **regardless of run
    order** — a later thin retry can never make an earlier solid extraction disappear;
  - **provenance precedence (#662, 2026-07-26 — runs BEFORE the year axis, added by epic #617):**
    among multiple **accepted** facts, one from honest production work supersedes one whose
    representation was benchmark-injected (`benchmark_provenance` truthy on the row, set by the
    caller from `capture.source='benchmark_gt'`), for the same school, **regardless of run order or
    year** — and it must run first, because the injected artifacts are deliberately-older curated
    documents that overwhelmingly carry no parseable year at all (measured: 957 of 957), so they would
    never lose on the year axis below. This is the durable forward rule adopted when #662 found that a
    re-run district's fresh facts were losing to stale injected `batch_00000` facts at this exact
    precedence chain — see the design note at the end of this list. Applies only when a `(band,
    school)` group holds BOTH kinds; an all-injected group is left alone. Rows with no
    `benchmark_provenance` key (every pre-#662 caller) leave this axis inert;
  - **school-year precedence (#254/REQ-146):** among multiple **accepted** facts, a fact whose
    `school_year` parses to a *known newer* year supersedes one with a known *older* year, regardless of
    run order (a genuinely more-recent schedule wins over a stale one). Unknown-year facts don't compete
    on this axis. **Year-superseded facts are KEPT, not dropped** — returned in a third list when called
    `with_superseded=True` — so the closing argument can still show them; year precedence only ever
    compares accepted-vs-accepted;
  - when neither axis decides (both unknown, or equal), among multiple **accepted** facts the
    **earliest** run wins — follow-up rounds fill gaps, they never silently overwrite a solid prior fact
    (correcting one is a gate@8 human determination, not an automatic later-run override);
  - among **unresolved-only** facts, the **latest** run wins (the freshest disagreement diagnostic).

  Output is `(accepted, unresolved)` — or `(accepted, unresolved, superseded)` with `with_superseded=True`
  — each deterministically sorted by `(band, school)`. Pure, no I/O; the caller filters to
  `run_kind='production'` rows (a THREE-valued column since #662: `production` | `probe` | `benchmark` —
  see `STAGE7_EXTRACT_DESIGN.md`; `probe` and `benchmark` are both excluded here, and are different axes
  from each other).

  **Why provenance precedence exists, and why the alternative (striking the stale fact at gate@8 via
  `band_exclusion`) was considered and withdrawn (#662, 2026-07-26):** #619 moved the Stage-9 write wall
  from district-membership to fact-provenance grain, but a re-run district's honest facts still lost to
  the historical `batch_00000` harness's injected `benchmark_gt` facts right here, in the merge that
  precedes the wall — `extraction`/`school_fact` are append-only, so an old injected fact can never be
  retracted, and (measured) 957 of 957 of the affected rows carry `school_year = NULL`, so the year axis
  never engaged and precedence fell through to earliest-`extraction_id`, which the injected artifact
  always wins. Striking the stale winner at gate@8 (`band_exclusion`, #257) was proposed as the fix and
  withdrawn: this merge collapses to ONE row per `(band, school)` **before** exclusions apply, so
  excluding the injected winner would **delete the school from the band** — the fresh reading never
  surfaces — rather than superseding it. `band_exclusion` remains what #257 built it for: a per-case
  hatch for a school that genuinely shouldn't count, not a way to unwind this merge's own precedence.
  The historical `batch_00000` harness extractions were separately reclassified to `run_kind='benchmark'`
  (a one-time migration, `maintenance/reclassify_benchmark_extractions.py`, applied to the live DB
  2026-07-27) so they no longer enter this merge as `production` rows at all — provenance precedence is
  now defence in depth for any FUTURE injection mechanism, not the primary fix.

  **The dedup key RE-NORMALIZES `school` through the CURRENT `norm_school` at read time** (PR #247
  review), not the raw persisted string: `school_fact.school` is written at extraction time, so a run
  predating a `norm_school` stopword-list change carries a stale-vintage key (e.g. the pre-#236
  `'lincoln unified district'` vs. today's `'lincoln'`). Exact-string matching on the raw column would
  silently fragment the merge — the SAME physical school reading as two — with no backfill path since
  `school_fact` rows are never rewritten. `norm_school` is idempotent (a fixed-point strip loop), so
  re-normalizing an already-current key is a no-op; this makes the merge self-healing across any future
  stopword-list change, for free.

- **`detect_single_school_over_extraction(accepted, nces_school_count, roster_names=None)`** — the #237
  cross-LEA contamination detector, live at `server.py:1649` (called immediately after
  `district_bands_from_facts`, in the same gate@7 read path, surfaced in the response as
  `"contamination"`). A **single-school NCES LEA** (`nces_school_count == 1`) whose accepted facts
  span MORE THAN ONE distinct school is contaminated — a charter-network campus whose siblings'
  schedules were pulled from a shared CMO domain (e.g. `ascendlearning.org` serving all 12 Ascend
  campuses), or a blank-domain unscoped capture (the Millard #227 class). Detection is reliable (a
  1-school LEA cannot legitimately have >1 school); picking WHICH school is the real one is not
  (shared network names like "ascend" recur across every sibling, acronyms like "DECA" =
  "Dayton Early College Academy" fail a name match) — so this **flags for human review at gate@7 and
  never auto-rejects**, matching the manual-gate ramp-up posture. `roster_matched` is the one
  trustworthy keeper hint (the LEA's own Stage-1 roster, when available), filtered through
  `norm_school_strict` (not the plain `norm_school`) so an all-stopword junk roster entry (a scraped
  "School District" header) can't pass as a legitimate keeper. Like `merge_fact_runs`, `accepted`'s
  school keys are re-normalized through the CURRENT `norm_school` before counting distinct schools —
  the same stale-vintage-key self-healing, here preventing a false contamination flag when two facts
  for the SAME school were persisted under different `norm_school` vintages. #237 spun off a
  structure-aware charter track (#243/#244/#245/#246) as the current forward-looking backlog in this
  area — see `docs/PROJECT_HISTORY.md`'s 2026-07-12 entry for the full investigation (the original
  hypothesis — NCES undercounting a real multi-campus network — was wrong; this detector is the
  correct fix that replaced a reverted topology-reclassification attempt).

## 1b. Related but distinct: `infrastructure/database/schedule_aggregation.py`

A separate, older module — `compute_instructional_minutes()` (gross minus lunch/passing time, i.e.
**net**, not gross) plus its own `aggregate_grade_band()`/`aggregate_district()` mode-over-a-sample
logic. It predates the gross-bell-to-bell decision (REQ-055) and the per-school-fact consensus model,
and is not part of the Stage 7/8 acquisition pipeline — it's used by the enrichment/reprocessing path
for already-captured school documents. Don't confuse its `aggregate_district` with
`stage8_aggregate.aggregate.aggregate_district` (the legacy vote-based one, §1a above); they're two
different functions in two different modules with overlapping names and similar-but-not-identical
purposes.

## 2. The standalone Stage 8 — design rationale (DECIDED 2026-07-13, BUILT #89 2026-07-14)

> This section is the *design rationale* the built gate@8 (§0a/§0b/§0c) realizes — kept because the "why"
> is still the reference for the parts not yet built (back-edges, auto mode; the Stage-9 write shipped
> 2026-07-21 — `STAGE9_INCORPORATE_DESIGN.md`). Where it reads in the future tense, read §0a/§0b for what
> actually shipped.

Design settled with Ian in a 2026-07-13 session. The guiding metaphor: **gate@8 is an attorney's closing
argument.** A closing argument states the claim, marshals the evidence, confronts the gaps honestly, and
asks for a verdict — and Stage 8's job is to make all four legible for one district so a reviewer (later, an
auto-gate) can reconstruct the chain **from a published LCT minute number all the way back to the pixels on
a district webpage, without re-running anything.** That offline-reconstructability is the auditability
north-star (the four commandments, governance §0) made concrete at the last structural gate before the
mechanical Stage-9 write.

**Boundary vs. gate@7 (the entry condition).** The aggregation ALGORITHM already runs inside gate@7's read
path (§0/§1a); the two gates ask different questions. gate@7: *"are these extractions good / do we need more
evidence?"* gate@8: *"is the whole district's per-band picture complete and defensible enough to PUBLISH?"*
So a district is **eligible for gate@8 only once gate@7's request loop has quiesced** — no open
request-more-evidence directives (all satisfied or auto-withdrawn, #233/REQ-123). You don't deliver a
closing argument while evidence is still being gathered.

**The benchmark wall (revised by epic #617's #619, 2026-07-26 — supersedes the district-membership
description below).** The queue used to exclude any district that had EVER been a `batch_type='benchmark'`
batch member (permanent, district-grain, via `server.py`'s `is_benchmark`/`IS_BENCHMARK_SQL`) — the
same district-permanent bug #619 retired at the Stage-9 wall (`STAGE9_INCORPORATE_DESIGN.md`). It is
now keyed at **fact-provenance grain** via the shared `IS_BENCHMARK_PROVENANCE_SQL` (`common/benchmark.py`),
the SAME two-arm predicate the Stage-9 wall uses — arm 1: `handoff.dispatch_type='benchmark'`; arm 2:
the fact's own rep carries `capture.source='benchmark_gt'`. A re-run district whose fresh production
facts no longer trace to benchmark-provenance evidence now clears the queue instead of being refused
forever. **The queue also changed from silently EXCLUDING to SURFACING** (#660, 2026-07-26): districts
still walled by the predicate now appear in the queue (visibly withheld, with their evidence traced to
its `gt_curation_*.pdf` source) rather than having no route to review at all — this is what makes the
`band_exclusion` escape hatch (§2b below / #662) reachable for a re-run district that still carries a
stale injected school. `IS_BENCHMARK_SQL` (plain district-membership) is kept as the gate@6 console
BADGE only ("part of the yardstick corpus" — display, not a gate). This is still consistent with how
the GT yardstick grows — an approved district's facts become part of the confirmed-fact base, while
benchmark-provenance facts are already the yardstick and don't re-flow through this gate. Full account:
`docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md` §10.9–§10.13,
§10.20, §12.5. (Live 2026-07-26: 47 queued / 26 withheld by the provenance predicate — supersedes the
"62 → 36" district-membership count this section previously reported.)

### 2a. What the stage accomplishes
1. **Dereference the band rollup into an evidence chain — via the IMMUTABLE handoff, not a fragile live
   join.** `district_bands_from_facts` gives the claim + per-school `{band,school,start,end,gross,models,
   method}` + `human_determination:""`. The supporting URL + rep files come from the **immutable Stage-6
   handoff**: `school_fact → extraction.handoff_hash → handoff_<hash>_<ts>.json`, whose per-record shape is
   `{rec_key, url, decision, reason, reps:[{file,kind,councils,route_reason}]}` — the actual discovered URL
   and exact files sent to the council, frozen with a `created_at`. That URL traces back to Stage 2
   (`discovery.json` / `discovery_school`: the `query` used, `wave1_raw_urls`, gate reason). **Capture time**
   comes from the gov_db working store `state_event` (`stage=3` `captured_all`, `created_at`, district-grain;
   multi-valued across recaptures) — with the capture-binary file **birth-time** (`page.pdf`/`page.png`, NOT
   the later-regenerated reader outputs like `camelot_*.txt`) as the per-URL-precise, best-effort refinement.
   NONE of this needs the regenerable `record→capture` join that can dangle after a Stage-5 re-ingest; the
   handoff and `state_event` are precious/immutable, satisfying §2c's offline-reconstructable requirement
   directly. *(An earlier draft of this note wrongly called a live `school_fact→representation→capture` join
   the stage's "load-bearing new data work" — the immutable receipts already carry it; corrected 2026-07-13
   after tracing real handoff/state_event data.)*
2. **Make sampling-sufficiency a first-class shown fact** per band: the NCES denominator (Y — captured at
   Stage 1 by raw LEVEL), the sampled count (X), the mode's **plurality share**, and whether early-exit
   fired. NOTE `mode_stable` currently has **no live caller** (§1a) — Stage 8 is where the sampling story
   stops being a latent heuristic and becomes a displayed, auditable statistic.
3. **The one write the stage adds: human override of extracted times, with a REQUIRED reason** — the
   `human_determination` field, already seeded. Precious (JSON-backed, re-importable, never dropped on
   re-ingest — same class as `label.facets_json`); it is exactly the "correcting a solid prior fact is a
   gate@8 human determination, not an automatic later-run override" carve-out that `merge_fact_runs` already
   defers to (§1a). **The override is OPERATIVE at display time, not deferred to Stage 9 (revised
   2026-07-13, from a live Santa Fe review):** `closing_argument._effective_times` applies the override
   over the council's reading and the band **mode is computed over the override-effective gross** — the
   reviewer is correcting the number they are about to approve, so the displayed determination (and the
   fingerprint they sign) must reflect it, else the override is cosmetic. The council's original times stay
   on the fact (`council_start_time`/`council_end_time`/`council_gross` in the receipt) for audit; Stage 9
   writes the effective value. Only a times-override recomputes; a note-only override annotates without
   moving the mode. (This was the v1 "Stage-9 applies it" deferral, reversed: a human tried it and
   reasonably expected the band to move.) **Hardened by its own review round (commit 15c67c4's review,
   2026-07-13):** the override path now goes through the CANONICAL `AGG.gross_from_times` — the shared
   REQ-055 PLAUSIBLE gate + HH:MM parser (`aggregate.is_plausible` is the one predicate both the council
   and human paths use) — after the first draft's inline arithmetic was found to (a) bypass the 240–510
   gate (a typo'd override yielding gross=125 became a district's modal determination) and (b) silently
   revert to the stale council gross on an unparseable time ("3pm") while still displaying as applied.
   Now: the endpoint VALIDATES the effective pair before storing (400 with the reason — immediate
   feedback), and `_effective_times` is defense-in-depth for legacy rows (an invalid stored override is
   NOT applied — council values stand, `override_error` renders a loud console warning). The console also
   renders an applied override's whole times/gross cell in the override treatment (not a trailing glyph),
   so a reviewer scanning the column can't mistake a human correction for a council reading, and
   `override_applied` is server-computed once rather than re-derived client-side.
4. **Adjudicate the negative space explicitly** — unresolved `(band,school)` pairs, implausible-gated facts,
   and the #237 contamination flag (`detect_single_school_over_extraction`, already surfaced in gate@7's
   read path). The human's disposition ("keep school X, drop the CMO siblings") is **recorded**; never
   auto-reject (the detect-and-flag posture, §1a).
5. **The verdict + back-edges — BUILT 2026-08-15 (#682 approve→write, #689 send-back→route; §3c).**
   Approve → Stage 9 writes mechanically, fired by the approval itself. Send back → the human routes
   **8→1** (a targeted DRAFT follow-up batch, gate@1-reviewable) or **8→6** (a new gate@6 draft
   dispatch). They parallel the existing 7→1 / 7→6 edges, which were the template.
6. **Strengthen what the council OUTPUTS, going forward — SHIPPED 2026-07-13 (`stage6.extract.v2`).** The
   inputs to Stage 7 (the handoff chain in item 1) are sufficient evidence of *what we asked*; what's thin is
   the council's evidence of *what it read*. Bounded by the REQ-054 invariant (models READ times, never
   compute/judge), the v2 extraction prompt adds per schedule: a verbatim **`evidence_quote`** (the exact
   source text the start+end were read from — one span, not split start/end), an optional **`source_locus`**
   (page/section), and a formal **path-2 `stated_minutes` + `stated_minutes_quote`** for the explicit-minutes
   "golden nugget" (Dunseith; the v1 start/end-only schema dropped it — the second acquisition path). Path-2
   is **corroboration only**: computed `gross = end − start` stays canonical (REQ-055); the stated number is
   shown as a cross-check, never a competing value. Deliberately **NOT** a per-model confidence score —
   cross-family agreement (REQ-056) already IS the confidence mechanism, so a self-report double-counts it.
   Pure reading outputs, cheap (still streams per REQ-119), **not backfillable** (a re-read is paid) — hence
   instrument-now. **As built:** `stage6.extract.v2` + `.vision.v2` (`stage6_handoff/prompts.py`), switched
   on via `council_configs.json` (v1 retained for old-handoff reproducibility); `consensus_school_facts`
   carries the consensus models' evidence onto each accepted fact (v1 facts stay byte-identical — attached
   only when non-empty); persisted to the new `school_fact.evidence_json`; `closing_argument` renders it as
   `council_evidence` per school (a representative quote + the full per-model map + path-2 agreement flag).
   **Live-validated** (2 reps, both voter models, $0.0003): models returned verbatim quotes, consensus
   unchanged, `stated_minutes` correctly null when unstated — and the quotes made a real start-time
   disagreement (homeroom-bell vs tardy-bell) legible, which is the whole point.

**Console shape** mirrors Stage 5: a **district-driven, attention-first** left pane (districts awaiting
approval sorted contamination-flagged / unsatisfied-bands / low-plurality first — not alphabetical), a
**band-first** detail pane (the claim), drilling into the per-school evidence chain. The seed user-stories
(retained from the original §2):
- re-queue a district with a band coverage gap (the 8→1 back-edge; follow-up `batch_*.json` reviewable at gate@1);
- add a URL to a new handoff visible in Stage 6 (the 8→6 back-edge, bypassing Stage 1);
- see per-representation start/end times OR the explicitly-stated minutes, and the computed daily minutes;
- manually edit/overwrite times, **required to supply a reason** (the `human_determination` write, item 3).

### 2b. Guardrails
gate@8 is structural AND the last gate before a published number, so its guardrails are load-bearing for the
whole automation program (governance §11b: gate@8's calibrated confidence gate must exist **before** the
supervision gates 6/7 relax).
- **No minutes reach the LCT DB without confidence** (§11b, explicit). Auto is auto-with-confidence-
  escalation: high-confidence bands auto-write, low-confidence escalate to manual.
- **A completeness guard, not only a correctness guard.** Stage 5's recall floor guards "did we lose real
  schedules"; Stage 8's band-level analogue: don't publish a district whose *claimed* bands are unsatisfied.
  A band resting on 1 of 30 schools is a different animal than 25 of 30 — the denominator statistic (2a.2)
  IS the guardrail input, not just display.
- **A statutory sniff test.** Cross-check each band's minutes against its state's statutory minimum
  (`state_requirements`, already held) — a band below the floor is either a real finding or an extraction
  error; **flag, don't block**. A district-level plausibility layer above the per-fact 240–510 gate (REQ-055).
- **Override auditability + the re-write boundary.** Every override is a precious `state_event` with actor +
  reason. The approval is **frozen and fingerprinted** at `(facts,config)` — the immutable-handoff pattern
  (governance §5) — so a re-approval after a back-edge round is a NEW record that never silently rewrites a
  published picture. Stage 9's write is a deterministic **upsert** (re-approval-safe, no duplicate rows).
- **The survivorship analogue.** A band accepted on a thin sample that reached "modal stability" early is a
  MODELED assumption about the unsampled schools. When the district recurs with more sampled schools, check
  the realized mode against the earlier lock so a **false early lock** becomes observable — the Stage-8
  sibling of Stage-5's exploration quota (governance §11b). `mode_stable`'s plurality check is the in-sample
  version; this cross-round check is new.

### 2c. The approval receipt (what the low-supervision future needs)
When the human leaves gate@8, the receipt is the **frozen closing argument** — it must let a later auditor
challenge any published number OFFLINE, without a live DB. Per district × band it carries:
1. **the claim** — gross minutes, start/end, band, method;
2. **the evidence chain, fully dereferenced** — per contributing school: the supporting URL + rep files
   (frozen from the immutable Stage-6 handoff via `extraction.handoff_hash`), the capture time (`state_event`
   stage-3 `created_at`, refined by capture-binary birth-time), the Stage-2 discovery lineage (query + wave),
   the extracting models + consensus method (families agreed, ±tol, judge), and — going forward — the
   council's verbatim `evidence_quote` / `stated_minutes` (§2a.6). Self-contained values **snapshotted into
   the receipt** at approval, not live-DB IDs (the immutable-handoff discipline, governance §5);
3. **the sufficiency statistics** — N_sampled / N_total, plurality share, early-exit window if it fired;
4. **the negative space** — the honest half: unresolved pairs + why, implausible-gated facts, contamination
   flags AND their disposition, bands claimed-but-unsatisfied, denominator schools never captured. A receipt
   showing only what we found reads as "we covered everything"; **log what was dropped** (the no-silent-caps rule);
5. **the decision record** — actor, timestamp, the confidence value auto WOULD have acted on, any override +
   reason, and the frozen `(facts,config)` fingerprint;
6. **the auto-vs-human agreement datum** — the **gate@8 calibration hook, now BUILT** (`gate8_decision_record`,
   fired inside `aggregate_decision` at `server.py:2454`, logging from day one — as the #108 lesson demanded,
   "you cannot measure a threshold you never instrumented"). It writes to the existing `calibration_event`
   table (`common/calibration.py`, ITEM grain), the same substrate gate@5/6/7 feed. (This section is the
   design target; §0a/§0b above record what actually shipped — most of this receipt is realized in
   `stage8_approval.receipt_json` + `closing_argument.fingerprint()`.)

The through-line: the receipt must also carry **the provenance of the denominator itself** (the NCES
per-band count + any contamination disposition) — if the denominator is wrong (the #237 single-school-LEA
class), every downstream sufficiency statistic lies.

### 2d. Sequencing — manual-first (SHIPPED); "satisfied" learned through the manual gate, then built as the slot vocabulary
The plan (Ian, 2026-07-13) was to **build the MANUAL gate first and learn the shape of "satisfied" from
watching real districts pass through it**, rather than guess the threshold up front (the ramp-up model,
governance §11b; the #108 accrual lesson). **That is what happened.** The manual gate shipped (#89), and the
per-band "satisfied" signal — originally #90, the keystone that gates the write / targets the 8→1 re-queue /
feeds the survivorship check — was then **built as REQ-149's per-band SATISFIED signal in the #499 slot
vocabulary** (`band_satisfied` over the slot spine; REQ-149 supersedes #90). So "satisfied" is no longer
undesigned: it is a slot-grain computation a human still signs off. What remains blocked on the auto path
(confidence-escalating, governance §11b) is gate@8 **auto mode** — gate-mode part b (#104) — but the
calibration hook (2c.6) has logged from day one, exactly as the high-supervision-first posture intended.

### 2e. Approval commit grain — PER-DISTRICT, all-or-nothing (DECIDED 2026-07-13)
The completion grain is district × band (governance §11d), but the **approval/write commit grain is the
whole district** (Ian, 2026-07-13). Rationale: LCT is a **district-level** metric — daily instructional
minutes over the district's enrollment/staffing. Publishing some bands while others are still thin would
force a partial-numerator-against-whole-denominator reconciliation the LCT model can't support; all-or-
nothing keeps every written number coherent. This does **not** discard the per-band view: bands are still
tracked/satisfied individually (the negative space §2a.4, the sampling sufficiency §2a.2), and an
**unsatisfied band BLOCKS district approval** and routes an 8→1 re-queue (§2a.5) — the district simply isn't
approvable until whole. Consequences: **(1)** the approval record is one row per district (a frozen receipt
of the whole closing argument), not per band; **(2)** the gate@8 calibration datum (§2c.6) is district-grain
(the confidence proxy is a district roll-up — e.g. min band coverage / council agreement); **(3)** the
per-school `human_determination` override (§2a.3) is still per-fact — a reviewer corrects individual school
times (with a reason) and then approves the district as a coherent whole. Stage 9 (#93) writes all of an
approved district's bands together, mechanically.

### 2f. PR #252 review round (2026-07-13) — 8 findings, all fixed pre-merge
A max-effort multi-angle review of the manual-gate build confirmed and fixed, before merge:
- **The staleness fingerprint ignored human overrides** — `fingerprint()`'s basis now includes each
  school's `human_determination` (an override recorded after approval is a new determination the
  approval never covered; excluding it left `is_stale` False after exactly the change the check exists
  to catch).
- **Review→decision TOCTOU** — the detail GET now returns the closing argument's `fingerprint` as a
  review token; the decision POST REQUIRES `expected_fingerprint` and 409s if the live facts moved
  after page-load (server-side re-load alone guarded a tampered payload, not a legitimate DB write —
  a Stage-7 follow-up completing — landing in the reviewer's think-time window).
- **Evidence attached on the wrong axis** — the handoff-evidence dedup sorted content-hash strings
  lexicographically ("earliest wins" — false), while `merge_fact_runs` picks winners by `extraction_id`.
  Evidence now resolves from the **winning fact's own run's handoff** (fallback: run-chronological
  order), and `source_file` rides the winning fact, not an unordered sibling row; the facts query also
  gained a deterministic ORDER BY.
- **Model-registration gap (the #217 `calibration_event` bug class recurring)** — `approval.py` now
  imports `stage8_aggregate.models` itself, so ANY entry point creating/using approvals registers the
  table; reproduced pre-fix via an isolated `pytest tests/test_stage8_approval.py` on a fresh table
  (`UndefinedTable`), passing post-fix.
- **`javascript:` URI XSS reintroduced** — the evidence-URL href had no scheme gate (the exact PR #248
  Settings bug, which had been fixed as a settings.js-LOCAL helper); `safeUrl` is now a SHARED
  `window.LCT` helper used by both views — one home, like `esc()` itself.
- **The benchmark wall inlined a third time** — now ONE `IS_BENCHMARK_SQL` fragment (server.py) used by
  the dispatch preview and the gate@8 queue; Stage 9's write boundary enforces the same benchmark wall
  (built 2026-07-21 — via its own `_is_benchmark_district`, since Stage 9 sits below `process_governance`).
  **Superseded 2026-07-26 (epic #617's #619):** both `IS_BENCHMARK_SQL` (district-membership) and
  `_is_benchmark_district` were themselves district-permanent — the SAME shape of bug this consolidation
  fixed, one level up. The gate@8 queue now runs `IS_BENCHMARK_PROVENANCE_SQL` and Stage 9 now runs
  `_is_benchmark_receipt`, both re-keyed to fact provenance and both living in the one shared
  `common/benchmark.py` home. `IS_BENCHMARK_SQL` survives only as the gate@6 display badge. See §2 above.
- **Single-source stated-minutes read as agreement** — `stated_minutes_agree` is three-state: True only
  with ≥2 models stating the same number, None (rendered "single source") when only one read it.
- **Falsy-zero `fact_id`** — the override endpoint validates `is None`, and the console guards
  `Number.isInteger` before posting. (Plus small adjacents: `_has_evidence` zero-safe, the exporter
  guard-wiring test extended to `_backup_stage8_approvals`, a dead ternary removed.)

## 3c. The verdict's two arrows, wired (#682 approve→write, #689 send-back→route; 2026-08-15)

Both arrows were documented for months while nothing consumed either. They failed the same way — **a
state with no owner responsible for exiting it** — so they are fixed the same way: execute the edge, and
give the miss a record.

**Approve → the Stage-9 write (#682).** `POST /api/aggregate/decision/{did}` with
`disposition='approved'` calls the SAME `incorporate_district` the CLI calls, post-commit (Stage 9
re-validates the decision from the DB in its own session — the TOCTOU re-check — so it must read a
committed world). The approval is precious and stands regardless: a blocked or faulted write is
reported and stamped as an `incorporation_blocked` `state_event`, never rolled back. See
`STAGE9_INCORPORATE_DESIGN.md` §2c.

**Send back → 8→1 / 8→6 (#689, `process_governance/stage8_sendback.py`).** Nothing fires on send-back:
the human picks the route at the gate (or neither) — the ramp-up posture — and the console *executes*
the choice instead of leaving the operator to translate their own reason into another stage's UI.

| route | what it composes | when |
|---|---|---|
| **8→1** rediscover | ONE targeted DRAFT Stage-1 follow-up batch via `Q1.build_followup_batch`, shaped by the same #162 untried-schools / #499 unfilled-slot inputs the 7→2 composer uses. gate@1-reviewable, **never auto-flowed** (like the 5→1 escalation). | "go find better/newer evidence" — Broward `1200180`: 231 schools on one dispatched rep, *"the sample is thin"*. |
| **8→6** redispatch | a new gate@6 DRAFT dispatch seeded with the district, via the existing draft store. No new discovery. | "the evidence is there; the wrong reps were sent" — mirrors 7→6. |

Target bands for an 8→1: the closing argument's UNSATISFIED bands when it names any (the send-back's own
diagnosis), else every band the district really serves — a send-back with nothing unsatisfied *is* the
thin-evidence shape, where "which band is wrong" is exactly what the human could not say. `real` bands
are the authority (the same definition the 7→2 compose gate uses), so a phantom band can never be
re-discovered.

**The linkage is the point.** Each routing appends a `send_back_routed` `state_event` carrying the
approval_id and the artifact — so "what did approval 1568 produce?" has an answer, a second click on the
same send-back names the existing artifact instead of minting a second batch, and
`unrouted_send_backs` turns "sent back and never re-routed" into a list (`GET
/api/aggregate/send-backs`, and the gate@8 badge) instead of a silence. Keyed on the approval_id, not
the district: a district sent back AGAIN after an earlier routing correctly reappears, because the
routing belongs to the instruction.

## 3d. The third arrow: RE-REVIEW of a decided district that gained evidence (#713, 2026-08-15)

`stage8_aggregate/rereview.py`. Fairbanks `0200600` was incorporated 2026-07-29 off a **one-rep**
dispatch, re-dispatched on 08-03 once #691 landed, gained **26 accepted facts for $0.004** — and
nothing happened. Its approval row was still July's, its `district_grade_minutes` still July's write,
and no surface said so. The narrowed-dispatch audit says which districts to re-dispatch; the pipeline
had nowhere to put the answer when one came back richer. #662's shape one layer up: **written is not
current.**

**Settled design questions** (the issue asked them; these are the answers, with the measurement that
decided the important one):

| question | answer |
|---|---|
| new row, or a new disposition? | a **new `stage8_approval` row** — the table is precious and append-only, `latest_decision` already means "the live decision", no schema change, every prior decision stays readable. |
| what TRIGGERS a re-review? | **REQ-147 staleness**, never "new facts". **Measured:** Fairbanks' 26 new facts moved *nothing* — identical modes, identical school sets — because `merge_fact_runs` is earliest-run-wins, so re-extracting the SAME schools cannot change the picture. A badge keyed on new facts would have cried wolf on the only district the mechanism has ever seen. |
| what does Stage 9 do on the second pass? | nothing new was needed: its idempotency key is (facts fingerprint, mapping version), so a re-approval on a moved picture re-writes, the orphan reconcile converges the band set, and #682 fires it from the approval. |
| how is the delta presented? | `delta_against_decision` — PURE, band-grain: approved vs live gross, and which schools joined or left, bands unioned across both vintages so an APPEARED band (Fairbanks' shape) is visible. A re-review reviews **what changed**; re-adjudicating the whole district is what the standing falsifier forbids. |

**Why a two-stage trigger.** The authoritative check costs a closing-argument assembly per district
(~28 ms × 53 decided = 1.5 s) against a queue that answers in ~27 ms. `CHANGED_SINCE_DECISION_SQL` is
a **sound superset in one round trip** (~3 ms warm): the fingerprint is derived from accepted
production facts plus the four human-judgment tables, so nothing can move the picture without a row
newer than the decision in one of them — including the per-school override, which is an UPDATE onto
`school_fact` and is therefore dated by its own embedded `at` stamp, not by `created_at`. The real
staleness check then runs only on the survivors. Measured live 2026-08-14: **53 decided districts → 1
candidate (Fairbanks) → 0 actually stale**; the queue endpoint went 27 ms → 33 ms warm.

**Where it shows:** a `re-review` badge on the queue row (sorted to the TOP — a district production
already holds, resting on facts nobody signed off, is the most actionable row in the list) and the
delta panel above the verdict controls. CLI:
`python3 -m infrastructure.acquisition.stage8_aggregate.rereview [district_id …]`.

**The audit answer this produced (issue acceptance 1):** Fairbanks' 26 facts change no band mode —
elementary/middle/high all 390 min, 18/4/4 schools before and after — so the risk across the other 16
narrowed-and-written districts is, on this evidence, mostly theoretical. The mechanism exists now to
catch the case that isn't.

## 3. Still open (post-2026-07-13 design)

**Genuinely still open:**
- **`gate@8` manual/auto** — auto = confidence-escalating, never writes minutes without confidence
  (governance §11b); blocked on #104 part b. Manual shipped; the calibration hook logs from day one (§2c.6).

**Since CLOSED (were open in the 2026-07-13 list):**
- ~~The 8→1 / 8→6 back-edges~~ → **BUILT 2026-08-15 (#689 — §3c below).**
- ~~#90 — the per-band "satisfied" signal~~ → **BUILT as REQ-149** (per-band SATISFIED over the #499 slot
  spine; REQ-149 supersedes #90). See §2d/§0c.
- ~~The approval-receipt schema + migration~~ → **BUILT** (`stage8_approval` + the frozen `receipt_json` /
  `facts_fingerprint`; arrives via `init_precious_schema()`, not a migration — §0b, §3 note below).
- ~~Stage 9 write (#93)~~ → **BUILT 2026-07-21** (epic #92 — the mechanical cross-DB upsert from the frozen
  gate@8 receipt + the per-grade projection; its own stage, `STAGE9_INCORPORATE_DESIGN.md`). Stage 9
  consumes the frozen `stage8_approval.receipt_json` (the `merge_fact_runs` product) without re-deriving it.
  A real incorporation campaign is underway (see that note for the live count).
- **Modal-aggregation quality (from the live Santa Fe review, 2026-07-13)** — two distortions that made a
  human override necessary where automation should have handled it: **#253** combined-scope facts
  (`k8 schools`, `milagro and ortiz schools`) counting as distinct schools + the K-8-topology-blind
  coverage denominator (Santa Fe middle read "4 of 2 · 200%"); **#254** school-year precedence in
  `merge_fact_runs` — **as-built (2026-07-14)**: the `stage6.extract.v3` prompt reads two new per-schedule
  READINGS (`school_year` normalized to "YYYY-YY", null when the page doesn't state one — never inferred
  from URL/domain/date; `applies_to` = "multiple" when the page's own text states a group scope, feeding
  the #253 flag surface). Consensus (`consensus_school_facts`) treats both as categorical corroboration —
  never in the grouping key, never voting on times: year = all-parseable-readers-agree (disagreement →
  null + per-model readings in `evidence_json`), scope = OR. Persisted as nullable
  `school_fact.school_year`/`applies_to` (the `evidence_json` going-forward pattern, no backfill).
  `merge_fact_runs` inserts year precedence between ACCEPTED facts only, above earliest-accepted-wins: a
  known NEWER parseable year supersedes a known older one regardless of run order; unknown-year facts
  COEXIST (never auto-oldest — every pre-v3 fact is unknown); the deterministic `parse_school_year`
  window is [2023, current+1] with the COVID wall, off `infrastructure.utilities.school_year`.
  Superseded facts are kept and surfaced in `negative_space.superseded_facts` (both years, both grosses);
  `negative_space.year_conflicts` flags every group mixing year knowledge, each side's `source_file`
  riding along as a format HINT for the reviewer, never an automatic rule (Santa Fe's stale facts came
  from a live webpage). Override-feeds-mode (§2a.3) remains the manual backstop for the undated-mix case.
