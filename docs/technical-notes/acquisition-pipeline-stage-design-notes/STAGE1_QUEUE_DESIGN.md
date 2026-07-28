# Stage 1 — Queue: present state & decision log

> **Authority:** Stage 1's purpose, I/O, exclusion/sampling/selection logic, output schema, and the
> gate@1 console (batch working store + edit/approve API + frontend) — what the code does today.
> **Audience:** anyone building on or debugging Stage 1; anyone tracing why a district is/isn't in a batch.
> **Companions:** `ACQUISITION_PIPELINE.md` (the 9-stage map + flow diagram), `METHODOLOGY.md` (Rule 6
> CTC / Rule 7 grade-span-gap / the sampling-policy rationale), `PIPELINE_GOVERNANCE_AND_STATE.md`
> (§3 state_event, §11 gates / batch types / district×band grain).
> **Update this when:** Stage 1's code behavior changes. Design turns and superseded approaches belong in
> §7 (Decision log), not here — this doc's body (§1–§6) is present-state only.

**Status: BUILT + run live**, including the gate@1 console (backend + frontend) and the benchmark batch
type (§2h). The batch is a first-class entity in the governance DB (the working store), with
`data/acquisition/queue/batch_NNNNN.json` regenerated from the rows as the auditable receipt (governance
§7a-A). gate@1 is an **in-band console approval** (a batch-row lifecycle transition + per-district events),
never an out-of-band go-ahead (§4, §6).

**Code:** `stage1_queue/queue_batch.py` (`build_batch()` pure construction + `persist_batch()` DB write +
receipt + state events — shared by the CLI and the console), `stage1_queue/benchmark_batch.py` (the
benchmark-batch builder, §2g), `stage1_queue/batch_store.py` + `stage1_queue/models.py` (the working
store), `process_governance/server.py` (the console API). `queue_batch.py` imports
`common.{school_sampling, district_status, paths, discover, db}` + `stage1_queue.batch_store` +
`infrastructure.database.{connection, models}` (`District`, `EnrollmentByGrade`) — it reads both NCES
CSVs **and** the LCT Postgres DB (§1), and writes the **governance** DB batch working store (§6).

---

## 0. Receipt from prior stage / Handoff to next stage

**Receipt from prior stage:** none — Stage 1 is the pipeline's entry point. Its inputs are external:
NCES CCD files on disk and the LCT production database (read-only; the one sanctioned Stage-1 read across
the acquisition→LCT layering boundary, alongside Stage 9's write).

**Handoff to next stage:** an **approved** batch (`batch.status == "approved"`) is Stage 2's input. It
never re-derives band membership from NCES CSVs — that would discard every gate@1 edit. A batch stays in
`draft` until approved; Stage 2 has nothing to consume until then. **Mechanism (#526, closed
2026-07-18):** the console/autoflow resolves the batch **from the DB** via `server._batch_from_db` →
`batch_store.to_working_doc` (the canonical included-only batch_doc + live `batch_status`, off one
`Batch` row fetch) for Stages 2, 3 AND 4 alike — the "JSON is never the transport between stages"
invariant now holds everywhere. `to_working_doc` is deliberately distinct from `to_receipt_doc` (which
feeds only the on-disk receipt file, via `write_receipt`, and stays status-free — see §6b): a review
round on PR #555 (#526's own PR) caught that folding status into `to_receipt_doc` would leak it into
the receipt, contradicting `batch_guard.py`'s documented invariant that a CLI loader must re-check
status against the DB, never trust the file. The on-disk receipt
(`load_batch_any` → `QUEUE_DIR/<batch_id>.json`, still regenerated on every gate@1 edit via
`write_receipt`) serves the CLI/offline path and audit only; the `cli_only_loaders` fitness function in
`arch-manifest.json` fails the suite on any `load_batch_any` reference inside `process_governance/`.

---

## 1. Purpose & I/O

Build a batch of districts plus, per district, the per-band school lists to target — the structured
input Stage 2 (Discover) and Stage 3 (Capture) consume.

- **Inputs — NCES CCD** under `data/raw/federal/nces-ccd/<year>/`: `ccd_lea_029_*` (district directory +
  claimed grade span), `ccd_sch_029_*` (school directory + per-school span/type/level), `ccd_sch_129_*`
  (virtual-school flags). `<year>` is the `--year` CLI arg (default `2024_25`); `school_sampling._sch_file()`
  / `_lea_file()` resolve the file by glob, so a new NCES release or a fallback year is just a different
  `--year` — no code change. *(The wildcard in these references is deliberate, per that resolution.)*
- **Inputs — the LCT Postgres database** (yes, Stage 1 reads it — via `infrastructure.database.session_scope`
  + the `District` / `EnrollmentByGrade` models): `load_ctc_ids()` reads **`districts.is_shared_service_entity`**
  (the CTC / shared-service exclusion), and `load_enrollment()` reads **`enrollment_by_grade.enrollment_k12`**
  (the most recent non-null/non-zero source year — the stratification axis).
- **Output — working store + receipt (2026-06-27).** The batch is now a first-class entity in the
  **governance DB** (`batch` / `batch_district` / `batch_school` — the working store, §6), with
  `data/acquisition/queue/batch_NNNNN.json` (5-digit zero-padded) **regenerated from those rows as the
  auditable receipt** (the receipts reframe, governance §7a-A). Both still carry structured targeting
  only — **no prompt text** (prompt construction belongs to Stage 2; baking it in would couple queue
  review to discovery-prompt wording). Receipt schema: `data/acquisition/queue/batch.example.json`.
- **Gate:** `gate@1` — now an **in-band console approval** (batch-row `draft → approved` transition +
  per-district `gate@1` events), see §4 + §6.

---

## 2. The design (settled)

### 2a. Pre-queue exclusion filters
`eligible_pool()` applies these **in this order** (all are live filters recomputed every run, never a
persisted exclusion list — a future policy change lets a district back in for free, no cleanup needed):

1. **Not operating** — LEA `SY_STATUS_TEXT != "Open"`.
2. **CTC / shared-service entity** — `districts.is_shared_service_entity = True` (the LCT DB; 600 districts;
   `METHODOLOGY.md` Rule 6 — name-pattern on career/technical/vocational/jted/cted **OR** NCES
   `LEA_TYPE_TEXT` in `{Specialized public school district, Service agency, State operated agency}`,
   disambiguated from charters via `LEA_TYPE_TEXT`). Accepted trade-off: the blanket type buckets also
   catch some legitimate special-purpose state schools (deaf/blind institutes, fine-arts academies).
3. **Already attempted** — reached **Stage 3 (Capture) or beyond** (`DS.already_attempted(registry, did)`;
   threshold = `ATTEMPTED_THRESHOLD_STAGE = 3`, over the `state_event` log). **First-run batches only** — a
   Stage 1/2-only district stays eligible for redraw; follow-up batches re-include by design (§2g).
4. **Grade-span integrity (Rule 7)** — exclude **and flag** when the LEA-level claimed span includes a band
   the school-level union covers with **zero** schools (internally inconsistent, untrustworthy to sample).
   `METHODOLOGY.md` Rule 7. ~1,439 districts excluded (2026-06-22, post-`recursive_band_groups`). **This is
   the one exclusion surfaced as a reported list** — `eligible_pool()` returns `gap_excluded` (district +
   missing bands), printed at run time and available to the `gate@1` review; the other three are silent skips.
5. **No usable enrollment** — a district must have a non-null, non-zero `enrollment_k12` (the most recent
   source year; the primary stratification axis) or it's dropped.

### 2b. Stratified sampling
Enrollment is the priority axis; **state** is a secondary per-pick tiebreak (staff/school count dropped —
too collinear with enrollment to buy independent coverage):
1. Sort the eligible pool by `enrollment_k12`, split into **4 equal-count quartiles** (not equal-range —
   NCES enrollment is heavily right-skewed).
2. Target **3 districts/quartile** (4 × 3 = 12) — the fixed-mix-per-stratum shape of the retired
   `training_batch.py`.
3. Each pick prefers a state not yet used in this batch; seeded-shuffle otherwise (`seed = batch_id`).
4. Top up from the remaining pool if a quartile runs short.

### 2c. Per-band school selection
Per selected district, target up to **12 schools/band** (elementary/middle/high) from the **school-level**
NCES roster (never LEA-level — no per-school granularity), full census if ≤12 candidates.

- **`school_index()` admits only `SCH_TYPE_TEXT = "Regular School"`** — excludes Alternative / Career and
  Technical / Special Education (the last a deliberate, deferred gap). A structural-field filter, not name
  matching. Excludes standalone preschool (`GSHI in ("PK","KG")`) and virtual schools (NCES `ccd_sch_129`
  `VIRTUAL_TEXT in {"Exclusively virtual","Primarily virtual"}`; "Supplemental Virtual" kept) — all via the
  shared `_eligible()` predicate, so `school_index()` and the `school_level_counts()` denominator agree.
- **LEVEL-primary classification:** a school with a clean NCES `LEVEL` of `Elementary`/`Middle`/`High`
  goes straight to that band, regardless of grade-range overlap. For whatever LEVEL leaves unresolved
  (ambiguous `Other`/`Secondary`/`Not reported`/`Ungraded`/blank, or a band with zero clean candidates),
  **`recursive_band_groups()`** groups the district's distinct grade spans **when they form a clean
  ascending partition**: consecutive leading segments topping out ≤6 collapse into elementary; the rest is
  resolved **per-segment by its own span** (starts ≤8 → middle; ends ≥9 → high; a segment can join both,
  and never joins elementary merely for being first). Non-clean-partition districts fall back to the
  conservative any-overlap rescue (`bands_for_rescue()`, grade-7 floor for middle). The recognized clean
  partition shapes this was profiled against are tabulated in `METHODOLOGY.md` → "Grade-band classification
  — recognized partition shapes (fallback reference)".
- **Grade 13** (a real NCES code for extra-year HS programs) is part of the high band — 222 open schools
  nationally use `GSHI=13`; omitting it silently mapped them to zero bands.
- **Cross-band overlap minimization:** process a district's bands **most-constrained-first** (ascending by
  pool size); each band samples from schools not yet claimed by an earlier band, reusing only when forced.
- **Over the cap:** a **seeded random sample** (`seed = f"{batch_id}:{district_id}:{band}"`) — no
  queue-time signal exists for which schools are "better," so an unbiased subsample is the defensible
  default (cf. the sampling-policy analysis, §3).

### 2d. NCES school-count denominator
The batch records per district `nces_school_counts: {total, by_level}` — schools meeting our eligibility
(the shared `school_sampling._eligible()` predicate, so denominator and band index can't disagree),
grouped by the **raw `ccd_sch` `LEVEL`**. A **denominator/provenance** field, NOT a selection input and
NOT `ccd_lea`'s self-report: the 12/band cap means "we have data for k schools" must never read as "the
district *has* k schools," so the true count travels with the batch (stamped with `nces_year`). Consumed
by Stage 5's `labeled_topology` (`single_school` = total 1; `incomplete_coverage` = one school-bell target
while total > 1) and the targeted-vs-got funnel.

### 2e. Output schema
`batch_NNNNN.json`, one file per batch (the `batch_doc` in `queue_batch.main()`):
- **Batch-level:** `batch_id`, `created` (UTC), `n`, `nces_year`, `nces_school_counts_criteria` (a prose
  note on the denominator), `stratification` (`{priority, method}`), `school_cap_per_band` (= 12),
  `school_selection_when_over_cap` (the most-constrained-first rule, in prose), and `districts[]`.
- **Per district:** `district_id`, `name`, `state`, `domain` (the LEA website host, via `discover.host_of`),
  `enrollment_k12`, `lea_claimed_bands`, `nces_school_counts {total, by_level}`, `band_processing_order`,
  and `schools_by_band`.
- **Per band** (in `schools_by_band`): `n_candidates`, `n_unclaimed_at_selection`, `n_selected`, and
  `schools[]` (the selected school records) — the `n_*` counts give the reviewer at-a-glance visibility into
  where the cap or cross-band claiming kicked in.

Structured params only, **no prompts**. Schema reference: `data/acquisition/queue/batch.example.json`.

### 2f. Status registry → `state_event` (REQ-099)
Cross-stage per-district state lives in the Postgres **`state_event` append-log** (current-state a SQL
view); `district_status.py`'s `load()`/`save()` read/write it while `record_stage()`/`already_attempted()`
stay pure in-memory dict ops (so the stage scripts are unchanged). `district_status.json` is the
regenerable, version-controlled backup. **Pre-queue exclusions are deliberately NOT recorded** — they're
live filters. See `PIPELINE_GOVERNANCE_AND_STATE.md` §3.

### 2g. Batch types + completion grain = district × BAND (governance §11d)
Batches are **first-run** (cold-start stratified draw; excludes already-attempted districts),
**follow-up** (re-discovery / band-gap fill; deliberately re-includes attempted districts, targeting their
**unsatisfied bands**), or **benchmark** (the special case — §2h). A district can recur across batches;
first-run and follow-up are both hard-capped at **12 districts** (a stages-1–4 blast-radius control). The
goal is daily instructional minutes per district **per band** — **schools are instrumental** (raw material
for queries + expected sampling units), so a district is "satisfied" when every claimed band has confident
minutes, not when every school is covered (e.g. Dunseith: one captured page stated "elementary 435 min /
high 450 min" and the schools became moot). Follow-up batches are created at the **return to Stage 1**
from a `gate@8`/`gate@7` direction (never minted straight to discovery by 7/8), so they stay reviewable at
`gate@1`. **BUILT (REQ-118, 2026-07-04):** the concrete builder is `build_followup_batch(year,
batch_id, targets)` in `queue_batch.py` — distinct from `build_batch()`'s stratified cold-start draw —
called by `stage7_execute.compose_followup_batch()` when a human approves a 7→2/7→3/7→1 directive at
gate@7 (`STAGE7_EXTRACT_DESIGN.md` §3F).

**Renamed in role, not in name (epic #617 Phase 2c, 2026-07-25):** `build_followup_batch` is now
documented as **THE TARGETED BUILDER**, not "the follow-up builder" — the name is historical. It
composes ANY batch whose district list is NAMED rather than drawn, which is follow-up **and**
benchmark alike (a benchmark batch composed this way re-runs specific districts as a Stages-2/3/4
A/B, the same shape as a follow-up, just a different `batch_type` at `persist_batch`).
`POST /api/queue/create` now routes any non-`first-run` `batch_type` through this targeted composer
(`server.py` — `if batch_type != BT.FIRST_RUN: ... build_followup_batch(...)`); `build_batch` (the
stratified draw) remains first-run-only. `batch_type` is now validated at `create_batch`
(`common/batch_types.py::validate_batch_type` — a legal-value check, previously an unconstrained
string with its legal values living only in a code comment) and redo-eligibility is a **declared**,
nullable batch attribute (`redo_attempted`, `common/batch_types.py::redoes_attempted`), not derived
from `batch_type` — a pre-#617 batch with no declared value falls back to the historical
`batch_type == 'follow-up'` rule, byte-identical behavior, so `batch_00000`'s frozen artifacts stay
untouchable by default while a freshly-composed benchmark batch can declare `redo_attempted=True`.
See the epic's findings report (`docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`)
for the full "district-keyed wall → batch/provenance-keyed wall" story.

### 2h. `batch_type="benchmark"` — the special case (`batch_00000`, 2026-07-02)
A third batch type, built for the 27 curated-GT districts: `stage1_queue/benchmark_batch.py` builds a
batch over a **fixed district list** (not a stratified draw — the pre-queue exclusion filters are
bypassed by fiat) and injects each district's frozen `data/benchmark/gt_curation_*` artifacts directly at
the Stage-3 seam (discovery.json/candidates.json/captures.json + copied files, all Stage-4-ready) — no
discovery, no fetching. Created + approved in one step (`create_and_inject()`), not through gate@1's
normal draft→edit→approve flow. `batch_00000` itself (the batch row) is permanent — never deleted or
reused — and its injected extractions must never be Stage-9-written or counted in funnel/enrichment
statistics: they are an accuracy yardstick (per-school times hand-verified against these exact files),
not coverage, and several source documents are deliberately older school years. See
`COUNCIL_LAB_DESIGN.md` §3 (the cost-benchmark harness design C.1–C.6 migrated there from
`STAGE6_DISPATCH_DESIGN.md` §3C).

**The wall is now keyed on run/extraction PROVENANCE, not on district membership in `batch_00000`
(epic #617, closing #662, 2026-07-26/27).** The original mechanism asked "has this district EVER been
in a `batch_type='benchmark'` batch" — since `batch_district` rows are never deleted, that permanently
refused a Stage-9 write for all 27 `batch_00000` districts, including correct minutes from a later,
honest production run. The fix moved the wall's grain from district to provenance
(`IS_BENCHMARK_PROVENANCE_SQL`, `common/benchmark.py`, keyed on `extraction.run_kind='benchmark'`) —
a district can now freely move between a benchmark harness run and a normal production run; what's
walled is the injected extraction itself, not the district's ability to ever incorporate. A follow-on
fix (#662) found the grain change alone wasn't sufficient — the gate@8 queue and `merge_fact_runs`
were still scoped to "ever produced a benchmark extraction," which is permanently true once true on
append-only tables. Closed via a receipted, idempotent migration
(`infrastructure/acquisition/maintenance/reclassify_benchmark_extractions.py`, **run against the live
DB 2026-07-27**) that moved the 27 districts' 30 historical harness extractions from
`run_kind='production'` (the pre-#148 default, never corrected) to `run_kind='benchmark'`, plus a
provenance axis in `merge_fact_runs` so honest work supersedes an injected fact for the same school,
plus a write-path stamp (`stage7_run.py`) so any *future* benchmark run is stamped `run_kind='benchmark'`
at write time and never needs another one-off migration. Full account: the epic's findings report
(`docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`) §7/§10/§11/§13.

**#620 (in progress, 2026-07-27):** re-running `batch_00000`'s 27 districts through the now-fixed
pipeline is the epic's validation. Three targeted batches (`batch_00030`/`00031`/`00032`, composed via
the targeted builder above, 25 of the 27 districts) have cleared Stage 2 (discovery) and Stage 3
(capture)/Stage 4 (process): 2,124 documents, 97.6% usable, and — measuring fresh vs. injected
time-bearing evidence — 80.9% of time strings are FRESH (production) provenance across the 25, with 0
districts landing gt://-only. This is the empirical proof the district-keyed wall was blocking
legitimate re-runs, not protecting a real invariant. **The remaining 2 of 27 are a separate, open gap
(#646):** a district that is both domain-less AND already-attempted (`furthest_stage >= 3`) is
unreachable by any Stage-1 composer — `eligible_pool()`'s first-run draw excludes it as attempted
(§2a #3), and the targeted builder needs a domain to scope discovery. Not fixed as of this writing;
does not hold #620 open (tracked separately).

`create_and_inject()` never calls `reserve_next_batch()` — it goes straight `create_batch()` +
`approve_batch()` back-to-back, so the batch is created and approved in one step rather than passing
through the normal reserve → draft → edit → approve lifecycle §6b/§6c describe (there's nothing to
review at gate@1: the district list and per-school facts are frozen curation inputs, not a fresh draw).
The same fixed-list rationale extends benchmark's exemption beyond the pre-queue exclusion filters
(line above) to the **#229 domain-scoping guard** too (`build_batch_doc()`'s own comment: "Benchmark is
EXEMPT from the #229 domain guard... discovery never runs, so the domain is cosmetic") — a blank/bogus
NCES `website` can't cause the unscoped-discovery contamination #229 guards against when discovery is
skipped entirely.

---

## 3. Sampling policy (queue-time)

> **Methodology lives in `METHODOLOGY.md` → "Bell Schedule Sampling Policy"** — *why* we sample the
> **mode** (not a proportion), and why the textbook 95%/±5% finite-population survey formula is the wrong
> tool (it saves only ~4% over a full census across 18,158 districts; the corpus is mostly small districts
> censused regardless, and bell times cluster by district policy so the mode stabilizes far below the
> proportion-formula n). This section is just the **Stage-1 implementation** of that stance.

**Decision — queue-time school cap (2026-06-22):** ≤ 12 schools/band → full census; larger → cap at
**12/band** (seeded random sample, most-constrained-first overlap minimization — §2c). A fixed queue-time
commitment: Stage 1 has no extracted minutes to judge mode stability, so it hands Stage 7/8 the full
upper-bound candidate list rather than trying to early-exit itself.

The companion **extraction-time mode-stability early-exit** is a Stage-7 decision (open) — see §5 and
`METHODOLOGY.md`.

---

## 4. `gate@1` — the in-band console approval

`gate@1` (human review) is **in-band**: approval is a **batch-row lifecycle transition**
(`status: draft → approved`, stamping `approved_at`/`approved_by`) plus a **per-district `gate@1
"approved"` `state_event`** for the auditable timeline. The reviewer acts in the console, and the action
is recorded — never an out-of-band "go." The unit of approval is the **batch** (the thing that advances to
discovery), not the individual district; rejecting districts/schools happens *before* approval via editing
(§6c). Manual/auto is per Settings (governance §11b); **auto mode is not wired — gate@1 is manual-only.**

---

## 5. Open decisions
- **Manual batch construction** (hand-pick untouched NCES districts; APGA story 32) and **follow-up /
  re-queue batches** (stories 33–35; need the Stage-8 per-band satisfaction signal, not built) — deferred. (tracked: #98)
  First-run stratified draw + soft edits is what's built.
- **gate@1 auto mode** — confidence-escalating auto-approve (governance §11b); manual-only today. Not
  "no auto-anything has been justified" — a narrower carve-out doctrine now exists elsewhere in the gate
  model (gate@7's #233/REQ-123 auto-withdraw: auto-act in the spend-conservative direction only when the
  failure mode is both observable and reversible). gate@1 hasn't been shown to fit that doctrine yet;
  this stays an open decision, not a settled no.
- **Extraction-time early-exit** — §3, deferred to Stage 7.

---

## 6. The batch working store + gate@1 console (REQ-102)

The batch is a first-class entity in the **governance DB** (the working store); `batch_NNNNN.json` is the
receipt regenerated from the rows on every change (governance §7a-A — the JSON shifted from a
data-transmission vehicle to an auditable receipt).

### 6a. Schema (normalized, PRECIOUS — `stage1_queue/models.py`)
Created by `gdb.init_precious_schema()`, **never** in the Stage-5 ingest's `REBUILD_DDL` drop list, so a
re-ingest can't wipe a queued/approved batch. Normalized (not a JSON blob) so edits are real row ops and
the cross-batch queries the user stories need (a district in multiple batches; per-batch yields) fall out.
- **`batch`** — lifecycle: `batch_id` (PK), `batch_type` (`first-run`|`follow-up`|`benchmark` — §2h;
  `models.py:30`'s column comment matches), `status`
  (`draft`|`approved`|`abandoned`|`reserving` — `reserving` is the id-reservation placeholder, §6b;
  `abandoned` is a TERMINAL, never-approved-only status, #168, below), `nces_year`, `created_at`/`_by`,
  `approved_at`/`_by` (CURRENT approval — cleared by `reopen_batch`), `first_approved_at`/`_by` (the
  DURABLE first-ever-approval stamp, never cleared by reopen — the honest "were this batch's schools
  committed to discovery" discriminator `abandon_batch` gates on), `abandoned_at`/`_by`/`abandon_reason`,
  `meta_json` (the batch-level prose carried to the receipt: stratification method, denominator criteria,
  cap, over-cap rule).
- **`batch_district`** — one row per district; `ord` (stratified-pick order, for a stable receipt),
  the denominators + per-band selection-time counts (`band_meta`), and `included` (the soft-reject flag).
- **`batch_school`** — one row per (district, school); `bands` lists every band it's selected into (a
  multi-band school is ONE row), `included` (soft-reject), `source` (`stratified`|`manual_add`).

### 6b. doc ↔ rows (`stage1_queue/batch_store.py`)
- **`reserve_next_batch(sess, actor=)`** — reserves the next batch id up front, in its own short
  transaction, by inserting a `status="reserving"` placeholder row. The console's create path spends
  10–20s inside `build_batch()` between computing the number and persisting; without a reservation two
  concurrent creates could compute the *same* number and collide 20s later. A concurrent `reserve` of the
  same number fails fast on the PK instead. **`release_reservation(sess, id)`** deletes the placeholder if
  the build then fails (never burns the number on a dead reservation).
- **`create_batch(sess, batch_doc, …)`** — three branches (#264): if a `reserving` placeholder exists for
  the id, upgrades it in place; if a **non-reserving** batch already owns the id, raises `BatchLocked`
  (`"... already exists (status); pick another id or reopen/abandon the existing batch"`) instead of a
  bare PK `IntegrityError` traceback (a CLI-path scenario — the console always reserves first); otherwise
  a fresh insert.
- **`to_receipt_doc(sess, id)`** — the canonical batch_doc (INCLUDED rows only, original shape) —
  **deliberately status-free**, feeding only the receipt file (`write_receipt`) and `common.batch_guard`'s
  invariant that a CLI loader must re-check status against the DB, never trust the file; `n_selected` is
  **recomputed live** from included rows (counts stay honest after edits).
- **`to_working_doc(sess, id)`** — `to_receipt_doc`'s shape **plus** live `batch_status`, off one `Batch`
  row fetch — the console's batch resolve for Stages 2/3/4 (`server._batch_from_db`, #526). Split from
  `to_receipt_doc` on purpose (a #555 review-round catch): folding status into the receipt-doc function
  would leak it into the on-disk file, contradicting the status-free invariant above.
- **`to_view(sess, id)`** — the gate@1 review payload: lifecycle fields + ALL rows (included *and*
  soft-rejected) with their flags, so the human sees what was proposed and what they dropped.
- **`write_receipt(sess, id)`** — regenerate `batch_NNNNN.json` from the rows (the receipt always mirrors
  the working store); writes via tmp-file + `os.replace` so a crash mid-write can never leave a truncated
  receipt. Every function takes a Session and does **not** commit — the caller owns the txn.
- **`list_batches(sess)`** — the queue-list rows. Each carries a **`progress`** block (REQ-110): per-batch
  district counts `{total, discovered, captured, processed, flagged}`, so every stage view's left pane can
  render a stage-contextual fraction (Stage 2/3/4) instead of the stale gate@1 status. **Batch-scoped, not
  `current_state`-derived (#339, fixing the mechanism this doc previously described):** `_batch_progress`
  aggregates directly from the `state_event` log via a `DISTINCT ON (batch_id, district_id)` subquery
  (`max_stage`/`last_outcome` per batch) — the global one-row-per-district `current_state` view was
  attributing a district's first-run progress to every later batch containing it (a freshly-created
  follow-up batch showed `discovered/captured/processed = total` before its own discovery ever ran).
  Best-effort (degrades to `null` if the query fails). `n_districts` (the included-district count) is a
  **separate, deliberately redundant** grouped query (#338: one query for every batch, not a COUNT
  per-batch — a real console-latency problem at ~1000+ batches) so it survives `_batch_progress`
  degrading to `{}`. The shared frontend `progressBadge` (`static/outcomes.js`) consumes the `progress`
  block.

### 6c. gate@1 edit operations (soft, audited, REVERSIBLE — APGA stories 29–31)
- **`reject_district`** / **`reject_school`** → flip `included = False` (never a delete — the full
  proposed batch stays auditable). **`restore_district`** / **`restore_school`** → flip it back, so a
  mis-reject during draft isn't a dead end (added 2026-06-28). **`add_school`** → insert a `BatchSchool`
  (`source="manual_add"`), or re-include a previously-rejected row. All blocked when `status="approved"`
  (`BatchLocked`); `reopen_batch` returns to draft. Each edit re-emits the receipt **and** records a
  per-district `gate@1 "edited"` event (transparency/auditability — the standing principle).
- **`abandon_batch`** (#168, built 2026-07-09) — a DIFFERENT exit from `reject_*`: retires a whole
  **never-approved draft** to the TERMINAL `status="abandoned"` (e.g. a batch superseded before it was
  ever run). Gated on the DURABLE `first_approved_at` being `None` — an approved-then-reopened batch cannot
  be abandoned, because its schools already committed to discovery (counted as attempted) the moment it
  was first approved; abandoning it would silently drop them back out of the attempted-set and re-queue
  them (the #162 poison this status exists to prevent). `abandoned` is TERMINAL: `reopen_batch` explicitly
  refuses it (`BatchLocked`) — recovering one is a deliberate un-abandon action, not an incidental reopen.
  Both `draft` and `abandoned` batches are excluded from `stage7_execute._attempted_schools` on the premise
  that neither ever ran discovery.

### 6d. The console API (`process_governance/server.py`)
The Stage-5 review app grows into the stage-selectable governance console; gate@1 is one of its surfaces:
`POST /api/queue/create` (synchronous stratified draw — `build_batch` reads the full NCES corpus + DB,
~10–20s; the UI shows a progress affordance), `GET /api/queue` (list), `GET /api/queue/{id}` (review),
`POST /api/queue/{id}/edit` (reject/restore district+school, add_school), `POST .../approve` + `.../reopen`,
`GET .../district/{did}/candidates` (remaining eligible schools for "add school"). Tests:
`tests/test_stage1_batch_store.py` (the working store) + `tests/test_gate1_api.py` (the HTTP wiring).

### 6e. The console frontend (`process_governance/static/`)
The first stage view, built on the **MMM Design System** (imported via the **DesignSync** tool from the
`claude.ai/design` project — Badge status pills, Select, Card, Button + the shared `tokens/`/`app.css`):
**`index.html`** — a **stage selector** in the topbar + a `stage1view` container; **`gate1.js`** — the
view (batch list, the district→band→school tree with `included` flags + each school's LEVEL/grade-range
surfaced for classification review, the soft edit controls, a loading overlay for the synchronous
~10–20s create, Approve/Reopen, Abandon); **`app.css`** — gate@1 styles (badges, the selector, the two-pane
layout, the overlay/spinner). The create path reads NCES CSVs and the LCT DB password via
`paths.DATA_ROOT` / the repo-root `.env` — CWD-independent regardless of launch directory.

The lifecycle controls rendered depend on batch state: a **draft** batch shows Approve **and**
Abandon…; an **approved** batch shows only Re-open (abandon is draft-only — §6c's DURABLE-stamp
rationale); an **abandoned** batch shows no action buttons at all — a `q-locked` banner reports who
abandoned it, when, and the optional reason, and states plainly that the batch can't be edited,
approved, or re-opened. The Abandon button itself prompts for an optional reason before firing
`POST /api/queue/{id}/abandon`.

---

### 6f. Console view — user stories (APGA, seed; migrated 2026-06-27 from the retired apga doc)
- Start a new batch of districts — **✅ built** (`create`).
- gate@1 (was CP-A) review: look at proposed districts + schools — **✅**; reject districts — **✅**; reject
  schools — **✅**; add schools to a district that has more to queue — **✅** (§6c, APGA stories 28–31).
- Manually construct a batch from hand-picked untouched NCES districts — **DEFERRED** (story 32; a second
  creation mode beyond the stratified draw — also the home for "add district").
- Re-queue districts already in the pipeline (action Stage-5 `none-found`/`insufficient-coverage`); a
  district can exist in multiple batches with different school sets; select schools already-submitted vs
  not-yet-submitted to discovery — **DEFERRED** (stories 33–35 = follow-up batches, REQ-109; needs the
  Stage-8 per-band satisfaction signal).
- Create multiple batches that only advance when approved — **✅** (per-batch `status`, independent approval).
- All batches capped at ≤ 12 districts — **✅** (§2g).

---

### 6g. `common/batch_guard.py` — enforcing `abandoned` outside the console (#168/#206)
The console's own Stage-2 run endpoint already refuses a non-approved batch, but the headless CLI
runners (`python3 -m infrastructure.acquisition.stageN.headless run <batch_id>`, plus the older
per-district Stage 3/4 CLIs) load the on-disk receipt, which carries no status field — without a shared
guard they would happily keep running a stage on a batch retired via `abandon_batch` (§6c), recording
discovery/capture events for districts already excluded from `stage7_execute._attempted_schools` (the
#162 double-queue poison `abandoned` exists to prevent). `batch_guard.py` closes that gap with two
entry points, one per grain a caller might hold:
- **`assert_runnable(sess, batch_id)`** — batch-grain, for the headless `run_batch` runners and the
  Stage-2 legacy CLI, which take a batch id directly.
- **`assert_district_runnable(sess, district_dir)`** — district-grain, for the Stage-3/4 legacy CLIs
  (`finish`/`reconstruct`/`run`), which operate on one on-disk district directory with no batch argument;
  it reads the batch id out of that directory's `discovery.json` and defers to `assert_runnable`.

Both raise `SystemExit` on an `abandoned` batch (matching the headless tooling's existing hard-stop
convention for a missing batch) and no-op for every other status, including a batch this DB has never
seen (a receipt-only dev batch stays runnable). The module lives in `common`, not in Stage 1 or any
consuming stage, because the acquisition stages are import-linter-enforced siblings that may not import
each other (§ architecture tools, top of `CLAUDE.md`) — a guard shared across Stage 2/3/4 entry points
has to sit in the shared base layer. It queries the `batch` table by raw SQL rather than importing
`stage1_queue`'s models, for the same layering reason. Called from `stage2_discover/{headless,
discover_stage2}.py`, `stage3_capture/{headless, capture_stage3}.py`, `stage4_process/{headless,
process_stage4}.py`, and `stage5_filter/harness.py`.

---

## 7. Decision log (chronological — moved here from the flow diagram, 2026-06-27)

_The turn-by-turn record of how Stage 1 was designed and hardened. Preserved verbatim; `gate@1` was
"Checkpoint A / CP-A" at the time of writing (see governance §11 for the current gate model)._

**2026-06-22 — Stage 1 design session:**
- Band/school selection must come from **school-level** NCES data (`ccd_sch_029`, via `school_sampling.bands_for()`), not LEA-level — LEA-level `GSLO`/`GSHI` only gives the district's overall claimed span, no per-school granularity.
- Grade-span gap (LEA-level span claims a band, school-level union shows zero coverage) is a data-integrity **flag + exclude**, not just a note — documented as Rule 7 in `METHODOLOGY.md`. General rule (any claimed-but-uncovered band, edge or middle), not scoped to "middle gap" only. Scoped to the acquisition queue, not the core LCT enrollment/staff calculation (which doesn't consume per-school grade-span data).
- Stratification axes: **enrollment (priority) + state**. Staff count and school count dropped as separate axes — too collinear with enrollment to buy independent coverage. **Algorithm confirmed 2026-06-22:** enrollment quartiles computed fresh from the current eligible pool each run, 3 districts/quartile target (mirrors `training_batch.py`'s fixed-mix-per-stratum pattern), seeded shuffle within each quartile preferring an unused state as tiebreak, top up from adjacent quartiles if one runs short.
- School selection when a band exceeds the 12-per-band cap (e.g. Fairbanks: 23 elementary / 15 middle candidates): **seeded random sample** (seed = `f'{batch_id}:{district_id}:{band}'`) — no signal yet at queue-time for "better" schools, so an unbiased subsample is the most defensible default (same logic as the project's 95/5 sampling theory).
- **Cross-band overlap minimization (confirmed 2026-06-22):** multi-band schools (K-8, K-12, alternative schools) can satisfy more than one band's `bands_for()` classification, so independent per-band sampling can pick the *same* school into multiple bands' selections even when enough distinct single-band schools exist. Fixed by processing bands **most-constrained-first** (ascending by candidate-pool size) per district, each band excluding schools already claimed by an earlier-processed band before sampling, only falling back to reuse if the unclaimed pool can't fill the cap. Validated on real Fairbanks data: went from 3 overlapping schools (elementary↔middle) under independent sampling to 1 unavoidable overlap (high↔middle, forced because high's full 9-school census left middle only 11 unclaimed against its cap of 12) — confirms the heuristic minimizes overlap where avoidable and accepts it only where the roster genuinely forces it.
- CP-A review is **out-of-band** — no `approved`/`reviewed_by` fields in the queue JSON for now; matches the project's current high-touch ramp-up posture. Revisit if/when we want a machine-checkable gate.
- Drafted the actual Stage-1 queue output schema (`data/acquisition/queue/batch.example.json`) — array-of-districts (human-scannable, unlike the dict-keyed status registry, since this is the CP-A review artifact), with `n_candidates`/`n_selected` per band so a reviewer can see at a glance when the cap kicked in.
- "Through Stage 3" exclusion = **attempted, regardless of outcome** — don't resample districts that failed; triage failures separately. *(Corrected 2026-06-22 — see the dedicated entry below: this was implemented as "any presence in the registry," not "reached Stage 3+," and the literal name "Through Stage 3" was the intended threshold all along, just not what the code did.)*
- **Status registry drafted** (`data/acquisition/status/district_status.example.json`): a single JSON dict keyed by `district_id` (structure prioritized over human-scan convenience for this one — it's process input, not just a record), updated at **every** stage (1-9, not just through capture) as a district progresses, with a per-district `history[]` trail. Lives under `data/acquisition/status/` — "acquisition" is the umbrella term for the whole 9-stage process per `ACQUISITION_PIPELINE.md`, so a cross-cutting, all-stages-write-to-it registry belongs there, not nested under a single stage's folder. Replaces the directory-presence heuristic in `training_batch.py`. **Pre-queue exclusions (CTC, not-operating, grade-span gap) are deliberately NOT recorded in this registry** — they're live filters recomputed every run from `is_shared_service_entity`/`LEA_TYPE_TEXT`/grade-span, never a frozen list, so a future policy change lets a district back in for free with no cleanup needed.
- CTC/shared-service exclusion applied **at queue time**, using NCES `LEA_TYPE_TEXT` to disambiguate from charter LEAs with career/tech branding (39 of 191 raw name matches were charters, wrongly caught by name pattern alone — see `METHODOLOGY.md` Rule 6/7). Backfilled DB flags for 152 real CTCs via `apply_ctc_classification.py`; LCT recalculated.
- Stage-1 JSON output holds structured targeting params only (district, schools-per-band) — **no prompt text**. Prompt construction belongs to Stage 2, since Python can't spawn the Haiku WebSearch subagent anyway (agent-in-the-loop).
- `data/acquisition_queue/` (old Crawlee-era FastAPI job queue, confirmed dormant) cleared out. `data/acquisition/` doesn't exist yet on disk despite being referenced in docs/code — nothing has actually been queued under the new design yet.
- Reusable logic from `training_batch.py` (seeded-shuffle reproducibility, band-counting via `school_sampling.py`) to be harvested into the real Stage 1 implementation; `training_batch.py` itself then archived per the project's existing convention (cf. `gt-exercise-complete` git tag).

**2026-06-22 — Stage 1 implementation session (docs → scripts):**
- Built `district_status.py` (registry module), extended `school_sampling.py` (`lea_info()`, `school_index()` — refactored `load()` to derive from `school_index()` rather than duplicating the CSV read), and `queue_batch.py` (the real Stage 1 orchestrator) exactly per the design above. `training_batch.py` harvested then archived to `data/archive/training_batch_py-superseded-20260622/`.
- **Found and fixed a real CTC-exclusion gap while testing for real:** the first dry run queued Pima County JTED (Joint Technical Education District, AZ) — the name-pattern filter missed it because "JTED" doesn't literally spell "technical." Investigating turned up a cluster of similarly-named AZ JTEDs/CTEDs and led to checking NCES `LEA_TYPE_TEXT` more broadly. Expanded the exclusion to also blanket-catch `LEA_TYPE_TEXT` in `{Specialized public school district, Service agency, State operated agency}` — accepting the known trade-off that this also sweeps in some legitimate full-time special-purpose state schools (deaf/blind institutes, fine-arts academies) that aren't really CTCs. 152 → 600 districts excluded; documented in full in `METHODOLOGY.md` Rule 6. Re-ran the LCT calculation after the fix — pass rate improved 99.47% → 99.63%, `ERR_IMPOSSIBLE_SSR` dropped 828 → 314.
- **Validated the grade-span-gap filter (Rule 7) isn't a bug** — spot-checked sample exclusions against the raw NCES files; confirmed e.g. "Alabama Youth Services" claims KG-12 at LEA level but has *zero* schools listed anywhere in `ccd_sch_029` (not even closed ones) — a real data-integrity gap, not a logic error. ~3% of the eligible-pool candidates excluded this way on the first real run.
- **Generated and validated a real `batch_00001.json`** (12 districts, 12 distinct states, zero unforced cross-band school overlaps — the few overlaps present are all genuinely forced by small total school counts, e.g. a single school covering all three bands in a tiny district). Confirms the full Stage 1 pipeline — exclusion filters, stratified sampling, per-band selection, registry write — works end to end on real data, not just the Fairbanks spot-check used during design.
- **Batch file naming: 5-digit zero-padded (`batch_00001.json`, not `batch_01.json`)** — covers the unlikely-but-possible case of needing one batch per individual US school district (~19K LEAs).
- Added a stale-pointer note to the `per-school-acquire-training` skill (still references the archived `training_batch.py` path/schema) since CLAUDE.md already flags that skill as reference-only, not the active runbook, and not in scope to rewrite today.

**2026-06-22 — CP-A human review of `batch_00001` caught three real bugs, none of which automated checks (Rule 7) would have found:**
- **Olympic Peninsula HomeConnection** (a homeschool-umbrella program) and **Jackson County Vocational Center** (a school-level CTC inside an otherwise-normal district) both got selected as band representatives. Fix: `school_index()` now only admits NCES `SCH_TYPE_TEXT = "Regular School"` (excludes Alternative / Career and Technical / Special Education — the latter accepted as a deferred gap, not a clean fit for this filter's rationale). Deliberately a structural-field filter, not name-matching — "Mountain Home Elementary"-style names would collide with a naive keyword approach.
- **Lake Preschool** (`GSLO=GSHI=PK`) got selected for the elementary band. Fix: exclude standalone preschools (`GSHI == "PK"`) — narrower than excluding all PK-serving schools, so a normal K-5 school that also offers PK still counts normally.
- **The real bug, found by tracing *why* the Vocational Center was the sole high-band candidate:** `bands_for()` had no entry for NCES grade code "13" (a real, sanctioned code some states use for an extra-year high school program), so any school coded e.g. `09-13` silently mapped to zero bands. Jackson County's three real high schools all use this coding and were completely invisible to band selection — not a name/type issue at all, a parser gap. 222 open schools nationally use `GSHI=13`. Fixed by adding grade 13 to `GRADE_ORD` as part of the high band.
- Rule 7 (grade-span-gap) exclusions roughly doubled (485 → 985) after these fixes — expected and correct: districts whose only "covering" school in a claimed band was one of the now-excluded types correctly show that band as uncovered instead of falsely covered.
- Regenerated `batch_00001.json` with all three fixes applied; confirmed none of the three flagged schools appear anywhere in the new batch.

**2026-06-22 — second CP-A finding on the same batch: pervasive elementary/high duplication into middle.** Eyeballing `batch_00001` further (still the same review pass) showed real elementary and high schools showing up in middle's candidate list throughout — not isolated, present in nearly every multi-school district. Root cause: band membership was pure grade-range overlap (`bands_for()`), and our hardcoded K-5/6-8/9-12 split doesn't match how many real districts organize grades (K-6/7-8, K-4/5-8, 6-12 combined secondaries, etc.) — a real "Elementary" school extending to grade 6 got counted toward middle even when a genuine, correctly-labeled middle school existed for that district, diluting the sample (confirmed concretely: Fayette County IN's middle pool was 6 schools, 5 of which were K-6 elementaries and only 1 — `Connersville Middle School` — was the real thing).
- **Fix: LEVEL-primary classification with a per-band rescue fallback**, not a literal "LEVEL primary, fall back only when LEVEL=Other" rule as first proposed — that literal version would have traded the dilution bug for a false-gap bug. Confirmed two real districts (Calhan CO, Breathitt County KY) have **no school labeled "Middle" at all** — just a K-5/K-6 Elementary and a 6-12/7-12 combined High secondary — so a strict LEVEL-only rule would show zero middle candidates and wrongly trip Rule 7. The rescue pass (grade-range fallback, but only for bands left empty by the LEVEL-primary pass, not for every school) preserves these legitimate cases while still fixing the dilution.
- Validated against all 7 concrete real-data examples surfaced during the investigation (Calhan, Breathitt County, Fayette County, Hammarskjold Upper Elementary [named "Elementary" but NCES LEVEL is actually "Middle" — grades 5-6], Quitman County, Universal Academy, Jackson County) — every one resolved correctly. Re-ran the full batch afterward: 12 remaining cross-band overlaps, all individually traced and confirmed genuinely forced (e.g. Chama Valley NM and Northern Tioga PA both have zero schools labeled "Middle," same pattern as Breathitt County).
- Reinforces the same lesson as the first finding: Rule 7 (an automated check) would not have caught dilution at all — a diluted-but-nonzero candidate pool looks identical to a healthy one from the gap-checker's point of view. Only a human looking at actual school names found it.

**2026-06-22 — third and fourth CP-A findings, same review pass: GSLO/GSHI added to the JSON for inspection, which immediately surfaced two more real cases.**
- **Exactly-2-school rescue tie-break:** Jasper Co. MO and Jefferson-Morgan PA each have exactly 2 schools (a KG-06/PK-06 elementary, a 07-12 secondary — Jefferson-Morgan's literally named "MS/HS"). Both overlap middle under the rescue pass, so both got included — diluting middle with the elementary even though the secondary (2 middle-grades covered) is clearly the dominant representative vs. the elementary (1 middle-grade). Fix: when exactly 2 schools exist and both would rescue into the same band, keep only the larger-overlap one. **Deliberately scoped narrowly** — when offered the more general "largest overlap wins everywhere" version (which would also have changed Breathitt County/Chama Valley/Northern Tioga's already-validated 3+-school rescue results), the call was to keep those three as-is and only fix the literal 2-school pattern described. Martins Mill ISD's earlier "this one's fine" status turned out to be incidental, not by design — its elementary happens to stop at grade 5, so it never even reaches the ambiguous-overlap situation in the first place.
- **Early-childhood exclusion extended:** Clinton County Early Childhood Center (`GSLO=PK, GSHI=KG`) was missed by the `GSHI=="PK"`-only preschool filter. Extended to `GSHI in ("PK","KG")`.
- Both fixes landed alongside adding `level`/`gslo`/`gshi` to the school JSON for human inspection — exactly the visibility that surfaced them. Also fixed a smaller inconsistency: `row.get("GSLO")`/`row.get("GSHI")` were missing the `""` default every other field in the dict uses.
- 4 new tests added (27 total now passing); `REQUIREMENTS.yaml` REQ-065/REQ-066 updated in place to cover both extensions rather than adding new requirement IDs, since they're refinements of the same capability, not new capabilities.

**2026-06-22 — the exactly-2-school tie-break replaced entirely with a general recursive rule, after profiling the full corpus.** The narrow 2-school scoping above didn't sit right (raised directly: "I don't want a case where the two districts we named are handled by specific exception" / "I don't like the rule of largest grade overlap wins... it seems better off for us to specify more explicit rules than an overly general one"). Resolution: build a markdown reference table of recognized grade-band shapes by hand (now `METHODOLOGY.md` → "Grade-band classification — recognized partition shapes"), then profile it against the full 2024-25 NCES corpus (17,265 eligible districts) instead of theorizing.
- **Corrected the N=2 threshold**: "does the lower segment's top grade reach 7?" (not 8, my earlier guess) — verified against every row of the reference table.
- **Found the real general rule, no enumeration needed**: consecutive leading segments with top ≤6 collapse into elementary (1, 2, or 3+ sub-segments); what remains is middle alone, middle+high merged, or middle followed by one-or-more high segments (lower/upper-high splits). Validated against 1,114 real N=4 districts (1,053 matched cleanly), plus real N=5/N=6 examples (elementary split into 3 tiers — Albertville City AL; high split into two campuses — Aledo ISD TX, a 9th-grade campus + main high school).
- **The "exactly 2 schools" scoping was itself the wrong dividing line**, confirmed by this profiling: Northern Tioga PA's 3 elementaries share an *identical* span and its 2 secondaries share an *identical* span — collapsed to distinct spans, structurally identical to Jasper Co.'s 2-school case. It should have gotten the same fix and previously did not; this was a real correction, not a refinement. Breathitt County/Chama Valley remain correctly different (genuinely non-identical, overlapping/redundant elementary spans — not a clean partition).
- **Implementation, stress-tested against a non-production single-user system** (the user's framing): two real bugs surfaced and were fixed during implementation, not just design — (1) a lone segment spanning the full range with nothing following (e.g. Universal Academy MI, a K-12 "Other"-LEVEL school) was wrongly losing its "high" membership; (2) an ambiguous-LEVEL school (Aledo's 9th-grade campus, LEVEL="Secondary") was being dropped from a band that already had LEVEL-clean coverage, when it should join as an additional candidate. Both fixed; full re-validation against all 15+ previously-confirmed cases plus the new ones passed cleanly afterward.
- `_band_overlap_size` (the old tie-break) removed entirely, superseded by `recursive_band_groups()`. 10 tests now cover this requirement (REQ-066, updated in place); 31 total passing.

**2026-06-22 — `recursive_band_groups()` rewritten a second time: position-based middle/high assignment replaced by a per-segment overlap check, after a CP-A reviewer spotted The Bridge Academy (CT) wrongly in `batch_00001`'s elementary band.** The first rewrite (above) fixed elementary's *prefix* correctly but still assigned middle/high to whatever segments were left by **position** ("first remaining = middle, rest = high"; for the `elem_end == -1` single/no-leading-run case, segment 0 was *unconditionally* put in elementary too). Real-data trace found two genuine bugs from that positional assumption, plus one case confirmed already correct:
  - **The Bridge Academy CT (0900015)** — a single LEVEL=High, 07-12 school, the district's only segment. `elem_end == -1` (no leading run), so the old rule's `if not remaining: return {"elementary": [0], ...}` fired and put the 07-12 high school in elementary purely because it was segment 0 — confirmed live in `batch_00001.json` before the fix (`schools_by_band.elementary` listed "The Bridge Academy" despite `lea_claimed_bands` correctly excluding elementary). **Real bug, now fixed.**
  - **Sequoia Union Elementary CA (0636360)** — LEVEL=Elementary KG-07 school + LEVEL=Middle 08-08 school (confusingly named "...Elementary" despite its LEVEL). Old rule: `elem_end == -1`, `remaining = [1]`, unconditionally `"high": remaining` — pulled the 08-08 middle school into the **high** candidate pool just for coming last, even though its own span never reaches grade 9. **Real bug, now fixed** — traced by hand against the old code's literal branches, not just observed in output.
  - **Quitman County GA (1304290)** — LEVEL=Elementary PK-08 + LEVEL=High 09-12, the case motivating "does a PK-08 elementary's middle-coverage also pull in the trailing high school?" Traced the old code's `elem_end == -1` branch by hand: `remaining = [1]`, `"high": remaining` — already gave `high=[1]` only, never added segment 1 to middle. **Already correct under the old rule**; kept as a validation/regression case for the new rule, not a bug fix.
- **Fix:** elementary stays a *positional* prefix-collapse (unchanged), but middle/high are now resolved by checking **each segment's own grade span**, independent of position: a segment joins middle if it starts at grade <=8, joins high if it ends at grade >=9 (can join both, or just one). A segment never joins elementary just because it's first — only if its own span actually starts within elementary's range.
- 3 new tests added (`test_lone_secondary_segment_does_not_join_elementary`, `test_trailing_segment_stays_middle_not_high_by_position`, `test_pk08_elementary_does_not_over_claim_into_trailing_high`); REQ-066 acceptance criteria updated in place to describe the per-segment rule. 34 total passing (2 pre-existing skips unrelated).

**2026-06-22 — `already_attempted()` threshold bug found while trying to re-queue `batch_00001` with the `recursive_band_groups()` fix applied.** Attempting to regenerate `batch_00001.json` to confirm the Bridge Academy fix landed in place revealed all 12 of its districts were silently excluded — `district_status.already_attempted()` was implemented as "any presence in the registry" (any stage), even though Stage 1's own design intent, stated plainly in this doc's decision log above ("'Through Stage 3' exclusion = attempted, regardless of outcome"), was always **Stage 3 (Capture) or beyond**. None of `batch_00001`'s districts had progressed past Stage 1 (`furthest_stage: 1`, never captured) — excluding them was masking the bug fix, not protecting against a real re-attempt.
- **Fix:** added `ATTEMPTED_THRESHOLD_STAGE = 3` to `district_status.py`; `already_attempted()` now returns `True` only when `furthest_stage >= 3`. A district that only reached Stage 1 (queue) or Stage 2 (discover) stays eligible for redraw.
- Updated `TestDistrictStatusRegistry::test_record_and_check_attempted` (previously asserted `already_attempted` True right after a Stage-1 record — now asserts it stays False through Stage 1 and only flips True at Stage 3); added `TestPreQueueExclusion::test_stage1_only_district_stays_eligible_for_redraw` and `test_captured_district_is_excluded_from_redraw`. REQ-062/REQ-067 updated in place. 36 tests passing (2 pre-existing skips unrelated).
- `batch_00001.json` regenerated with both fixes (per-segment `recursive_band_groups()` + the corrected threshold). **Turned out NOT to reproduce the same 12 districts** — the per-segment fix changes `school_index()` output nationally (not just for Bridge Academy's own district), which shifts which districts pass Rule 7 (grade-span integrity): the gap-exclusion count rose from the previously-recorded ~985 to **1,439**. The old bug had been *masking* real Rule-7 gaps elsewhere in the corpus (a district whose only "elementary" coverage came from a wrongly-reclassified non-elementary segment now correctly shows that band as uncovered) — so the eligible pool itself changed shape, and the same `seed=batch_id` draws a different 12 from a different pool. A fresh batch (Dayton Athletic Vocational Academy OH, North Country Charter Academy NH, Colfax Township MI, Bemus Point NY, Jefferson County North KS, Jenkins Independent KY, Caswell County NC, West Bonner County ID, Manteno CUSD 5 IL, Greenfield Union CA, Scott County VA, Dover Area SD PA) was reviewed in its place: all cross-band overlaps traced and confirmed genuinely forced (single-school districts, explicit Jr/Sr-combined or Elem/Middle-combined school names, West Bonner's 3 elementary spans genuinely overlapping/redundant like Breathitt County, and Virginia Connections Academy — LEVEL=Secondary, grades 06-11 — correctly joining both middle and high as an ambiguous multi-band school). No Bridge-Academy-style false positive found. Batch judged ready to advance to Stage 2.

**2026-06-22 — CP-A review of that batch caught two more real bugs: a virtual school and a grade-6 dilution case the any-overlap fallback had never been fixed for.**
- **Virtual school not excluded:** Virginia Connections Academy (Scott County VA) — confirmed via NCES `ccd_sch_129` `VIRTUAL_TEXT = "Exclusively virtual"` (a Pearson-operated full-virtual school) — has no real in-person bell-to-bell day, yet was being rescued into both middle and high via the ambiguous-LEVEL=Secondary path. **Fix:** new `school_sampling._virtual_ids()` excludes `VIRTUAL_TEXT` in `{"Exclusively virtual", "Primarily virtual"}`; `"Supplemental Virtual"` (a normal school that also offers a virtual option) and `"Missing"`/`"Not reported"` are left alone (no positive evidence to exclude on).
- **West Bonner County ID (any-overlap fallback dilution):** IDAHO HILL and PRIEST RIVER ELEMENTARY (both PK-06) were wrongly rescued into middle, while PRIEST LAKE ELEMENTARY (PK-07) and PRIEST RIVER LAMANNA HIGH (07-12) correctly belong there. Root cause: the any-overlap fallback (for districts whose spans don't form a clean partition) still used plain `bands_for()`, which treats grade 6 as inherently part of middle's nominal 6-8 range — the exact dilution shape the LEVEL-primary/per-segment fixes already solved for the *clean-partition* path, just never carried over to this fallback. **Fix:** new `bands_for_rescue()` requires a school to actually reach grade 7 to count as touching middle; used only in the any-overlap fallback (`bands_for()` itself is unchanged for other callers, e.g. Rule 7's LEA-level claimed-band check). Re-running this against Breathitt County KY (an existing test fixture using this same fallback) surfaced the identical latent bug there — Sebastian and Highland-Turner Elementary (both top out at grade 6) no longer dilute middle; the test assertion was corrected to match.
- 5 new tests; REQ-065/REQ-066 updated in place. 39 tests passing (2 pre-existing skips unrelated); full suite 864 passing.
- `batch_00001.json` regenerated again: Blue Water Middle College MI, HOPE LEADERSHIP ACADEMY MO, ROY NM, Hoboken Dual Language Charter School NJ, Sojourner Truth Academy MN, DUNSEITH 1 ND, Marion ISD IA, Mt. Abraham USD #61 VT, Fort Scott KS, Stroudsburg Area SD PA, Urbana SD 116 IL, Pittsylvania County VA. Reviewed in full: every overlap is a single named school genuinely covering two bands (e.g. Stroudsburg JHS, LEVEL=Secondary 08-09, correctly joins both middle and high alongside the LEVEL-clean MS and HS) — no dilution, no virtual/CTC/alternative/preschool leaks found.

**2026-06-22 — investigated Stroudsburg JHS (LEVEL=Secondary, 08-09) joining both middle and high, before deciding whether it needed special-casing.** Scanned the full 2024-25 NCES corpus for the exact shape (a `...-07` middle segment + an `08-09` junior-high segment + a `10-12` high segment). Found **39 distinct districts** nationally with an exact `08-09`-span school (46 schools total) — **33** in the full clean 3-tier shape (uniformly flanked by a `10-12` high; the "before" segment almost always starts at grade 6), 6 in messier shapes. **Every one of the 46 is NCES `LEVEL="Secondary"`** — NCES has no dedicated junior-high category, so this always falls to the ambiguous/per-segment path, never the LEVEL-clean one. **Decision: leave it alone.** At 39/~17,000 districts, and since a grade-8-9 school genuinely has students in both bands with one real bell schedule covering both, dual-band membership is correct behavior, not a bug — not worth a special case.

**2026-06-28 — gate@1 console end-to-end validation (`batch_00002`).** `batch_00002` was created →
edited (1 district rejected) → approved entirely through the console UI — the forcing-function milestone
(the first batch-of-record advanced without a hand-run CLI). Confirmed consistent across all three
surfaces: `batch.status='approved'` (by `ian`), **11/12 districts** in the receipt (canonical =
included-only, regenerated from rows), and the `state_event` log carrying **11 `gate@1 "approved"` + 1
`gate@1 "edited"`**. The rejected district stayed at `furthest_stage=1` — *not* disqualified from future
draws (only Stage-3+ capture disqualifies; §2a).

**2026-07-02 — duplicate-batch-id race fixed (issue #46, fable review).** The console's create path
computes the next batch number, then spends 10–20s inside `build_batch()` before persisting anything — a
second concurrent create in that window could compute the *same* number. Fix: `reserve_next_batch()`
inserts a committed placeholder row up front, in its own short transaction, so a concurrent reserve of the
same number fails fast on the primary-key constraint instead of colliding 20s later; a failed build
releases the reservation so the number isn't burned. `write_receipt()` also gained tmp-file +
`os.replace` atomicity (issue #50) — a crash mid-write can no longer leave a truncated receipt.

**2026-07-02 — `batch_type="benchmark"` added; `batch_00000` created (fable review, Ian approved
in-chat).** The 27 curated-GT districts (hand-verified per-school bell times, `data/benchmark/gt_curation_*`)
needed to enter the pipeline as an accuracy yardstick for Stage 7/8, without going through normal
discovery (which would re-fetch pages that may have since changed, poisoning the comparison with drift
instead of measuring the council). Built `stage1_queue/benchmark_batch.py`: a third batch type over a
fixed district list, injecting each district's frozen curation files directly at the Stage-3 seam and
freezing the batch as created+approved in one step. `batch_type` is the enforcement key for the wall
(never Stage-9-written, never counted in enrichment stats) that Stages 7–9 must respect. See §2h.

**2026-07-11 — two findings logged from the batch_00013 shakedown.** (#229 FIXED — PR #242, 2026-07-12;
the guard is live at `queue_batch.py`, as §2h now describes. #222 still open.)
- **#222 — juvenile-justice / alternative-facility "schools" can enter a district's draw and get
  matched to the wrong conventional school.** Surfaced when Jackson County Juvenile Ctr (MO) appeared
  matched to DeLaSalle Charter School — a juvenile-justice facility's day is a fundamentally different
  thing from a conventional school day and should never stand in for one. Fix direction: an exclusion
  filter recognizing juvenile-justice/alternative-facility NCES types at the draw, not a per-district
  hand-fix.
- **#229 — batch creation should refuse (or loudly flag) any selected district with a blank NCES
  `website` column.** Root cause of #227 (Stage 2 unscoped-discovery contamination — see that doc): an
  empty `website` produces `domain=''`, which flips discovery to its unscoped branch and lets common
  school names collide nationwide. A Stage-1 pre-flight guard closes this at the source; `batch_00000`
  (benchmark) is exempt since its curated GT files bypass discovery entirely.

**2026-07-18/19 — epic #111 Phase 1 correctness sweep (PR #550, #264/#338/#339): batch-scoped progress,
a collision message, and an N+1 fix.** #339 was the load-bearing one: `_batch_progress` (backing the
`list_batches` left-pane fraction) had been LEFT JOINing the global one-row-per-district `current_state`
view, so a freshly-created follow-up batch containing an already-processed district showed
`discovered/captured/processed = total` before its own discovery ever ran — wrong exactly where an
operator relies on it. Fixed by aggregating from the `state_event` log scoped to `(batch_id,
district_id)` instead (§6b). #264: `create_batch` on an existing non-`reserving` id now raises
`BatchLocked` with a clear message instead of a bare PK `IntegrityError` traceback. #338: `list_batches`'
included-district counts moved from one `COUNT` query per batch to one grouped query — a real
console-latency problem at ~1000+ batches, kept deliberately independent of `_batch_progress` so it
survives that aggregate's best-effort degrade. See §6b for the present-state description.

**2026-07-19 — #222: facility-named schools get a gate@1 review flag (epic #111 Phase 6).** The
batch_00013 shakedown's manual reject ("Jackson County Juvenile Ctr." drawn under DeLaSalle 2900593)
traced to an NCES mis-code: the facility carries `SCH_TYPE=1 "Regular School"`, so the Regular-School-only
draw filter cannot see it. No reliable CCD indicator exists → per the issue's triage, this lands as
FLAG-for-review, never hard-exclude: `school_sampling.facility_name_flags(name)` (token list:
juvenile/detention/correctional/youth-center …) is computed at VIEW time in `batch_store._school_dict`
(never stored — a token tuning applies retroactively to every batch) and the gate@1 school row shows a
"facility?" badge (`data-feat="s1-facility-flag"`, UI-visibility-pinned). METHODOLOGY Rule 6b records
the methodology stance.

**2026-07-19 — #164 PR 2: geo-scoped batch composition + dual-source #229 admission (epic #111
Phase 5).** `build_batch` gains the scope axis (`scope="domain"|"geo"`, pure — the POLICY check and
the confirmed-discovered-domains map are the caller's to supply): domain-scoped batches now admit on
NCES domain OR a human-CONFIRMED discovered domain (`common/discovered_domain`, the third clearly-
labeled source — per-district `domain_source: nces|discovered` in the doc; NCES data never modified),
and the #229 refusal population is exactly the geo draw pool (`geo_pool="blank"`; `"all"` = the
geo_all experiment position). Geo district docs carry `geo: {city, zip}` from the extended `lea_info`
(LCITY/LZIP, mailing fallback). The console create endpoint gates geo composition on
`discovery_scope_policy` (409 under domain_only) and threads the confirmed map; POST
/api/discovered-domain records a confirmation (+ the git-twin backup). REQ-157.

**2026-07-19 — #164 PR 3b: the escalation ladders land (epic #111 Phase 5, closes #164).**
`build_followup_batch` gains `force_widen_dids` (a ladder rung forces `query_strategy=
'widen_queries'` on every band of a listed district — vocabulary by rung, school selection
untouched). New pure helpers: `scope_pool_counts` (the blank-vs-domained eligible split, the
geo_interleaved draw weights) and `draw_interleaved_scope` (seeded per-batch scope draw; the
recorded `{policy, weights, drawn}` lands in `Batch.meta_json.scope_draw` via queue-create).
Queue-create also detects the POOL-DRAINED moment (a domain-scoped first-run drawing zero
districts while blank-domain districts remain) and auto-advances `discovery_scope_policy` exactly
one step (domain_only → geo_for_blank, event-logged + twin-backed, 409 notice to the operator).
Composers: stage7_execute's compose now SCOPE-SPLITS 7→1 targets by derived ladder position
(`batch_store.followup_rounds`): 0 rounds → domain batch (unchanged), ≥1 → geo+widened batch,
geo already ran → auto-reject + `followup_flag` (manual); up to TWO batches per compose, each
directive's `executed_ref` = its district's batch, one transaction. New app-layer
`process_governance/stage5_followup.py` = the 5→1 zero-yield geo composer (predicate: zero
dispatchable/held Stage-5 records AND no retryable errs AND no fidelity flags; ladder 0 geo →
geo+standard, 1 → geo+widened, ≥2 → manual flag; draft at gate@1, never auto-flowed).
Tests: tests/test_escalation_ladders.py + tests/test_queue_create_scope.py. REQ-157 implemented.

**2026-07-19 — #572: the #164 console control surface (REQ-158).** Surfaced by Ian's first attempt
at the live Millard NE run: the backend gating existed but no operator control did. New
`GET/POST /api/discovery-policy` + a Settings card (positions, audited set, event history);
a scope-aware gate@1 create dialog (geo offered when policy allows; drawn-by-policy under
geo_interleaved; an `n` input; optional path-4 **target district IDs** — `build_batch(district_ids=…)`
restricts AFTER the scope filters, records `targeted` meta, and a full miss 409s WITHOUT tripping
the pool-drained auto-advance); scope visibility everywhere (list scope tag, GEO badge +
containment note, `scope_draw`, per-district geo tokens + discovered-domain badge); and the
**5→1 zero-yield check** button on ran batches (its output is a gate@1 draft — dry-run survey
modal → compose; fuller gate@5 surfacing stays #518). Key operational fact this surfaced: Millard
NE (3173740) is already-attempted, so NO first-run draw can include it — its geo repair runs via
the 5→1 button on batch_00013 (live-verified eligible, rung geo+standard, with Playwright).
Tests: tests/test_discovery_policy_console.py.

**2026-07-20 — five present-state items added to §1/§2/§6, verified against current code
(`queue_batch.py`, `batch_store.py`, `server.py`), for the #164/#572 landing:**
- **`resolve_scoping_domain(website, did, discovered_domains)`** (`queue_batch.py:174-186`) — the
  ONE dual-source domain-resolution helper, shared by `build_batch` and `build_followup_batch`:
  NCES `website` when usable, else a human-CONFIRMED discovered domain
  (`common/discovered_domain`), else `("", "")`. Added to fix a drift bug where the follow-up
  path's own inline copy could label a domain's source `"discovered"` even when the confirmed-domain
  lookup came back empty.
- **`validate_scope_combo(scope, batch_type)`** (`queue_batch.py:211-217`) — guards that
  `scope="geo"` composes `batch_type="first-run"` batches only; benchmark and follow-up batches are
  never geo-composed via this path (follow-up's geo loops are the #164 PR-3 escalation composers'
  own job, not free-form `queue_create` composition). Wired into `server.py`'s `queue_create`
  (governance §11k has the full `queue_create` picture).
- **`geo_pool="all"` experiment mode** — `build_batch`'s `geo_pool` kwarg (default `"blank"`)
  controls the geo draw population. Under `"blank"`, the geo draw is restricted to districts with
  no usable domain from either source — the #229-refused class. Under `"all"` (the `geo_all`
  discovery-scope policy position, governance §11j), the geo draw ignores whether a district
  already has an NCES domain, drawing from the full eligible pool — the measured geo-vs-domain
  comparison mode.
- **`queue_create`'s snapshot semantics** (`server.py`, the `# SNAPSHOT SEMANTICS` comment ahead of
  the policy/discovered-domains read) — the discovery-scope policy and the confirmed-domains map
  are read ONCE at the start of the ~10-20s `build_batch` call; a policy flip or a domain
  confirmation mid-build is not reflected in that specific batch. Deliberately bounded and
  self-healing (the district is simply pooled per the snapshot for one compose; the next create
  sees the new state) — no lock taken.
- **The shared escalation-ladder threshold** — `batch_store.followup_rounds(sess, district_ids)`
  (`batch_store.py:287-305`) derives each district's ladder position (ever-APPROVED follow-up
  batches containing it, split by `discovery_scope`) straight from batch history, never a stored
  counter. `GEO_LADDER_EXHAUSTED_AT = 2` + `geo_ladder_exhausted(rounds_row)`
  (`batch_store.py:313-320`) is the ONE shared exhaustion check both escalation composers now call,
  extracted after a #575 review found the 5→1 and 7→1 composers disagreeing on a district sitting
  at exactly one approved geo round. This is Stage-1-owned code (`batch_store.py` lives in
  `stage1_queue/`) even though the composers that consume it — the 5→1 zero-yield composer and the
  7→1 scope-split — live in `process_governance/`; see governance §11e for how they actually use it.

**2026-07-25/27 — epic #617 generalizes the benchmark model; district-keyed wall retired in favor of
provenance.** See §2h (updated in place) for the present-state description: `build_followup_batch` is
now the targeted builder (not just "follow-up"), `batch_type` is validated at `create_batch`,
`redo_attempted` is a declared batch attribute, the Stage-9 wall keys on extraction `run_kind` rather
than district membership in `batch_00000`, and the historical harness extractions were reclassified to
`run_kind='benchmark'` via a receipted migration (run against the live DB 2026-07-27). #620 (re-running
`batch_00000`'s 27 districts) is the epic's validation and is IN PROGRESS, not planned — 25 of 27 have
cleared Stage 2/3/4 with 80.9% fresh (non-injected) time evidence; the remaining 2 are a separate open
gap, #646 (domain-less AND already-attempted, unreachable by any Stage-1 composer — see §2h). Full
detail: `docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`.

**Known live defect, flagged not fixed (#672, opened 2026-07-28, epic #128):** the 5→1 zero-yield
escalation ladder (`process_governance/stage5_followup.py::compose_zero_yield`, using
`batch_store.py`'s shared `geo_ladder_exhausted` above) was measured to sometimes make things WORSE,
not strictly better, when it widens — on a real district (Wyandanch UFSD NY, `3631800`), the widened
geo rung tripled result volume and diluted the district's own domain's vote share below the
geo-derivation threshold, causing total derivation failure and discarding URLs (including on-domain
hits) a standard rung had already used successfully; the ladder terminated the district at
`manual_flag`, a mechanically-caused failure rather than necessarily evidence of no published
schedule. So **the ladder's built-in exhaustion order (standard → widened) is not a proven
strictly-improving escalation** — treat a `manual_flag` outcome from the widened rung as suspect,
not conclusive, until #672 lands a fix.

**Known console caveat (#671, opened 2026-07-28, epic #96):** the gate@1/2/3/4 status views can show a
district as prematurely `done`, carrying a PRIOR run's cached numbers, for the entire duration of an
in-flight re-run (measured windows up to 38 minutes; on one occasion the display showed the OPPOSITE of
the run's actual outcome). Root cause is a batch-dispatch timing conjunct that goes true at run START,
not completion — do not trust a console status view as authoritative for a district mid-re-run; verify
against the DB/`state_event` log instead. Not yet fixed.
