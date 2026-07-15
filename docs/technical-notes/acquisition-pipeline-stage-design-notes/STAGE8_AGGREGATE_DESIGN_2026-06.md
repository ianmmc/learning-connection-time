# Stage 8 — Aggregate: design (algorithm LIVE in gate@7; standalone stage DESIGNED 2026-07-13, unbuilt)

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

The **standalone Stage 8** is the still-unbuilt gate downstream of gate@7 (its design is now settled —
§2 below, decided 2026-07-13): its job is to let a human
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

**Current (fact-based) — live inside gate@7 today** (five functions: `consensus_school_facts`,
`district_bands_from_facts`, `aggregate_band`, `merge_fact_runs`, `detect_single_school_over_extraction`):
- **`consensus_school_facts(model_rows, judge_rows=None)`** — the production per-school consensus
  function (`stage7_run.py:172,179`, `council_lab.py:99,108`). Input is `{model: [{grade_level,
  start_time, end_time, school_name}, ...]}` per council voter (and optionally a judge's rows).
  Rows are grouped by `(band, normalized-school-name)` — school-name normalization uses
  `common.school_match.norm_school`, the SAME normalizer the Stage-7 GT validator uses, so the two
  must agree identically (REQ-117; and, since PR #247 deleted Stage 5's own separate duplicate, all
  three stages now share the one function — see `STAGE7_EXTRACT_DESIGN_2026-06.md`). `norm_school`'s
  stripping rules were tightened in that same PR (suffix-anchored district-qualifier stripping,
  hyphen word-splitting, NFKD, ES/MS/HS): this grouping step is directly affected — e.g. "Meridian
  Consolidated School" and "Meridian School" now group as DIFFERENT schools here, where the old
  anywhere-strip wrongly merged their council facts into one consensus group. Within each group, the
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
  order), `band`, `school`, `status`. Per `(band, school)`, the merge rule is:
  - an **accepted** fact beats an **unresolved** fact for the same school, **regardless of run
    order** — a later thin retry can never make an earlier solid extraction disappear;
  - among multiple **accepted** facts, the **earliest** run wins — follow-up rounds fill gaps, they
    never silently overwrite a solid prior fact (correcting one is a gate@8 human determination, not
    an automatic later-run override);
  - among **unresolved-only** facts, the **latest** run wins (the freshest disagreement diagnostic).

  Output is `(accepted, unresolved)`, each deterministically sorted by `(band, school)`. Pure, no I/O;
  the caller is responsible for filtering to `run_kind='production'` rows.

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

## 2. The standalone Stage 8 — design (DECIDED 2026-07-13)

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
closing argument while evidence is still being gathered. The queue also **excludes benchmark
(`batch_type='benchmark'`) districts** — the same wall Stage 9 / the dispatch preview use (server.py's
`is_benchmark` rule): gate@8 authorizes the Stage-9 LCT write, and benchmark stays walled off. This is
also consistent with how the GT yardstick grows — a *non-benchmark* district approved here becomes verified
ground truth, whereas benchmark districts are *already* the yardstick, so they don't re-flow through this
gate. Keyed on `batch_type`, not the `batch_00000` id literal, because the GT corpus grows into new
benchmark batches. (Live: 62 production-fact districts → 36 after the quiesced + benchmark filters.)

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
5. **The verdict + back-edges.** Approve → Stage 9 writes mechanically. Or route **8→1** (re-queue an
   unsatisfied band via a follow-up batch reviewable at gate@1) or **8→6** (add a URL to a new dispatch,
   bypassing Stage 1). Both back-edges are **NOT built** (governance §11e) and are designed as stubs first;
   they parallel the existing 7→1 / 7→6 edges, which are the template.
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
6. **the auto-vs-human agreement datum** — the **gate@8 calibration hook, deferred today** (governance §11b
   explicitly excludes gate@8 from the calibration wiring until Stage 8 lands). Per the #108 lesson ("you
   cannot measure a threshold you never instrumented"), it should start logging the moment the MANUAL gate
   ships — long before auto — into the existing `calibration_event` table (`common/calibration.py`, ITEM
   grain), the same substrate gate@5/6/7 already feed.

The through-line: the receipt must also carry **the provenance of the denominator itself** (the NCES
per-band count + any contamination disposition) — if the denominator is wrong (the #237 single-school-LEA
class), every downstream sufficiency statistic lies.

### 2d. Sequencing — manual-first; #90 ("satisfied") deferred and LEARNED through the manual gate (DECIDED)
The per-band **"satisfied" signal (#90) is the keystone**: simultaneously the confidence threshold that
gates the write, the target for the 8→1 re-queue, and the input to the survivorship check (2b). It is
**undesigned, and deliberately stays so** — the decision (Ian, 2026-07-13) is to **build the MANUAL gate
first and learn the shape of "satisfied" from watching real districts pass through it**, rather than guess
the threshold up front (the ramp-up model, governance §11b; the #108 accrual lesson). The manual gate does
NOT need #90 — a human eyeballs sufficiency — so Stage 8 ships manual-first with "satisfied" as a human
judgment, the calibration hook (2c.6) logging from day one, and the auto path (confidence-escalating,
governance §11b) blocked on #90 + gate-mode part b (#104). This is the same high-supervision-first posture
every other gate shipped under.

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
  the dispatch preview and the gate@8 queue; Stage 9's write boundary reuses it when built.
- **Single-source stated-minutes read as agreement** — `stated_minutes_agree` is three-state: True only
  with ≥2 models stating the same number, None (rendered "single source") when only one read it.
- **Falsy-zero `fact_id`** — the override endpoint validates `is None`, and the console guards
  `Number.isInteger` before posting. (Plus small adjacents: `_has_evidence` zero-safe, the exporter
  guard-wiring test extended to `_backup_stage8_approvals`, a dead ternary removed.)

## 3. Still open (post-2026-07-13 design)
- **#90 — the per-band "satisfied" signal** (confidence/coverage threshold): deferred by decision (§2d),
  to be characterized from manual-gate experience. REQ-118's follow-up compose machinery is partial adjacent
  groundwork (it does not define "satisfied").
- **The aggregation-record / approval-receipt schema + migration** (§2c) — the precious approval table +
  its JSON backup, and how a required-reason override is stored and audited (§2a.3). *(First build step.)*
- **The 8→1 / 8→6 back-edges** (§2a.5, governance §11e) — designed as stubs first, built after the
  read/approve path.
- **`gate@8` manual/auto** — auto = confidence-escalating, never writes minutes without confidence
  (governance §11b); blocked on #90 and #104 part b.
- **Stage 9 write** (#93) — the mechanical upsert into the LCT DB downstream of an approval (its own stage;
  `STAGE9_INCORPORATE_DESIGN_2026-06.md`).
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
