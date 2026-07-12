# Stage 8 — Aggregate: design (algorithm LIVE in gate@7; standalone stage EARLY)

> **Authority:** `stage8_aggregate/aggregate.py`'s fact-based aggregation API is **live production
> code**, not a prototype awaiting a future consumer — it runs directly inside `gate@7`'s read path
> today. `process_governance/stage7_run.py` calls `AGG.consensus_school_facts` and
> `AGG.district_bands_from_facts` during the actual production extraction/aggregation flow
> (`stage7_run.py:172,179,224`); `process_governance/server.py`'s gate@7 district-detail endpoint
> calls `AGG.merge_fact_runs` then `AGG.district_bands_from_facts` on every read
> (`server.py:1542,1547`), and its left-pane cumulative counts re-implement the same merge rule as
> hand-maintained SQL, checked against `merge_fact_runs` on shared fixtures so the two can't drift
> (`server.py:1416-1437`, comment: "the SQL twin of AGG.merge_fact_runs"); `council_lab.py` calls the
> same two functions for offline council-composition comparisons (`council_lab.py:99,108,125,127`).
> What's still unbuilt is the **standalone Stage 8**: its own `gate@8`, console, dedicated
> aggregation-record schema/migration, and the `8→1`/`8→6` back-edges (tracked: #89). Don't conflate
> the two — the algorithm has shipped; the stage-as-a-gated-checkpoint hasn't.
> **REQ-122** (`merge_fact_runs`'s cumulative-merge rule, status: implemented) is the clearest example:
> it was built to fix a gate@7 bug (#232 — a scoped retry could make an earlier run's solid facts
> disappear from the view) and is now gate@7's canonical merge logic, not a stopgap. The eventual
> standalone Stage 8 should keep consuming this function (or its direct descendant) rather than
> re-solve "which run's facts win" independently.
> **Companions:** `ACQUISITION_PIPELINE.md` §8 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
> §11 (gates/console; §11e cyclic back-edges), `METHODOLOGY.md` (the metric: gross bell-to-bell, the mode).
> Upstream: `STAGE7_EXTRACT_DESIGN_2026-06.md`. Downstream: `STAGE9_INCORPORATE_DESIGN_2026-06.md`.
> **Update this when:** the standalone Stage 8 design decisions are made (append below) or the stage
> is built end-to-end.

---

## 1. Purpose & boundary

The aggregation ALGORITHM turns the council's per-school `{start,end}` facts into **daily
instructional minutes by band** for a district: deterministic code computes `gross = end − start`
and the **per-band exact mode** across the band's schools (REQ-054; the metric = gross bell-to-bell,
240–510 min plausibility gate, REQ-055; cross-family consensus REQ-056 — all `status: tested`,
verified by `tests/test_aggregate.py::TestGross`/`TestMode`/`TestConsensus`). This logic lives in
`stage8_aggregate/aggregate.py` and is load-bearing for `gate@7` today (§0 above) — it is not waiting
on Stage 8 to matter.

The **standalone Stage 8** is the still-unbuilt gate downstream of gate@7: its job is to let a human
review/approve the council's extracted TIMES (`school_fact.human_determination`) before the
mechanical Stage-9 DB write — the effective old "CP-C." This scope was narrowed by a 2026-07-10
decision (REQUIREMENTS.yaml REQ-120/REQ-121 notes): approving extracted times is explicitly a
**Stage-8** activity, deferred from gate@7, which only reviews/dispatches *requests* for extraction,
not the times themselves. `district_bands_from_facts` already seeds the field this gate will act on:
each school entry in its output carries a `human_determination` stub (empty string) for the reviewer
to fill in (see §1a below) — gate@8's console is expected to render and write back through that field.
Completion grain = district × **band** (schools are instrumental; governance §11d).

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

**Current (fact-based) — live inside gate@7 today:**
- **`consensus_school_facts(model_rows, judge_rows=None)`** — the production per-school consensus
  function (`stage7_run.py:172,179`, `council_lab.py:99,108`). Input is `{model: [{grade_level,
  start_time, end_time, school_name}, ...]}` per council voter (and optionally a judge's rows).
  Rows are grouped by `(band, normalized-school-name)` — school-name normalization uses
  `common.school_match.norm_school`, the SAME normalizer the Stage-7 GT validator uses, so the two
  must agree identically (REQ-117). Within each group, the council reaches consensus on **START and
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
  order), `band`, `school`, `status`. Per `(band, school)`, the merge rule is:
  - an **accepted** fact beats an **unresolved** fact for the same school, **regardless of run
    order** — a later thin retry can never make an earlier solid extraction disappear;
  - among multiple **accepted** facts, the **earliest** run wins — follow-up rounds fill gaps, they
    never silently overwrite a solid prior fact (correcting one is a gate@8 human determination, not
    an automatic later-run override);
  - among **unresolved-only** facts, the **latest** run wins (the freshest disagreement diagnostic).

  Output is `(accepted, unresolved)`, each deterministically sorted by `(band, school)`. Pure, no I/O;
  the caller is responsible for filtering to `run_kind='production'` rows.

## 1b. Related but distinct: `infrastructure/database/schedule_aggregation.py`

A separate, older module — `compute_instructional_minutes()` (gross minus lunch/passing time, i.e.
**net**, not gross) plus its own `aggregate_grade_band()`/`aggregate_district()` mode-over-a-sample
logic. It predates the gross-bell-to-bell decision (REQ-055) and the per-school-fact consensus model,
and is not part of the Stage 7/8 acquisition pipeline — it's used by the enrichment/reprocessing path
for already-captured school documents. Don't confuse its `aggregate_district` with
`stage8_aggregate.aggregate.aggregate_district` (the legacy vote-based one, §1a above); they're two
different functions in two different modules with overlapping names and similar-but-not-identical
purposes.

## 2. Console view — user stories (seed, for the standalone Stage 8)
- As a user, I want to **re-queue a district where there are coverage gaps for a given band** — which
  creates a new Stage-1 batch focused on the missing bands (the 8→1 back-edge; the follow-up `batch_*.json`
  is reviewable at `gate@1`).
- As a user, I want to **add a URL to a new handoff** that shows up in Stage 6 (the 8→6 back-edge — re-route
  an existing representation, bypassing Stage 1).
- As a user, I want to see the **start and end times extracted for each representation**, OR the explicitly
  stated instructional minutes; for representations with start/end times, I want to see the **calculated
  daily instructional minutes**.
- As a user, I want to **manually edit/overwrite** the start and end times from each representation, and I
  want to be **required to provide an explanation** of why I'm overwriting the extracted values — this is
  the `human_determination` field `district_bands_from_facts` already seeds per-school (§1a).

## 3. Open (to design when we reach this stage)
- The per-band satisfaction signal (what makes a band "confident" / "satisfied") — needed for follow-up
  batch creation (Stage 1 §5) and the drift detector (REQ-097). (tracked: #90) REQ-118's follow-up
  compose machinery is a partial existing answer — #90's own body cites it as adjacent groundwork,
  though it doesn't resolve what "satisfied" means for a band.
- The aggregation record schema + how a manual override (with required reason) is stored and audited.
- `gate@8` manual/auto (auto = confidence-escalating; never writes minutes without confidence, governance §11b).
