# Stage 9 — Incorporate: design (BUILT — the write AND the per-grade projection)

> **Authority:** `infrastructure/acquisition/stage9_incorporate/` (the code) + this note. The **landing
> zone** it writes into (`bell_schedules` schema: `minutes_basis`, `chk_method` incl. `council_extraction`,
> 24-hour time acceptance, the COVID/malformed-year seam guard) is BUILT — see `DATABASE_SETUP.md` and
> migration 019 / `queries.add_bell_schedule`.
> **Audience:** whoever maintains Stage 9, the per-grade projection (§4), or `per_grade_lct_sample`'s
> sign-off preview.
> **Companions:** `ACQUISITION_PIPELINE.md` §9 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE.md` §11,
> `DATABASE_SETUP.md` (the "Two databases" section — why this write crosses into the separate production LCT
> DB). Upstream: `STAGE8_AGGREGATE_DESIGN.md` (`merge_fact_runs`, §1a below).
> **Update this when:** Stage 9 behavior changes, or the per-grade projection (§4) is built.

**Status: BUILT — 2026-07-21 (epic #92; #93 write, #94 never-fabricate, #95 provenance, #605 per-grade
projection, #606 LCT consumption).** The 9-stage map is closed end to end: Stage 9 writes the approved
minutes AND projects them to per-grade so LCT consumes them (§4). Remaining is the one-time methodology
recompute, gated on human sign-off of the before/after sample (§4). Seeded from the APGA console user
stories (migrated here 2026-06-27).

**Campaign status (verified live 2026-07-28):** the incorporation campaign that started at 6/38 on
2026-07-22 has continued; `bell_schedules` now holds `council_extraction` rows for **38 districts**
(38/38 of what was then the approved backlog, superseding the "6 incorporated, 32 in backlog" 2026-07-22
snapshot this section previously recorded). Separately and more recently (epic #617, §2g below): 25 of
`batch_00000`'s 27 benchmark districts were re-run honestly under `batch_00030/31/32` and, as of
2026-07-28, are in gate@5 review on the way to their FIRST-EVER non-benchmark write — the wall this
section documents was retired at fact-provenance grain specifically to make that possible (#619), and
Stage 9's own campaign is what the epic calls its "only validation" (see the note below and
`docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md` §11.2, §13).
CLAUDE.md's Current-Status entry has the running narrative — this note stays mechanism-first.

---

## 1. Purpose & boundary
Stage 9 **delivers** a district's approved daily instructional minutes by band into the **LCT production
database** — the sanctioned Stage-9 *write* across the acquisition→LCT boundary (one of the two named
exceptions in the import-linter contract; the other is Stage 1's read). It is **ungated and mechanical**:
`gate@8` is the last human checkpoint; once a district is approved there (and not stale), Stage 9 writes.

**Two import-linter facts (both enforced, `lint-imports` = 4 kept / 0 broken):**
- **Layering:** Stage 9 is modeled as a layer *above* the independent stages 1–8 (it CONSUMES the gate@8
  determination — `stage8_aggregate.approval` + `closing_argument`, the canonical readers of that state,
  whose `fingerprint` logic Stage 9 must match exactly rather than duplicate). Nothing earlier may import
  Stage 9 (it is terminal). See `pyproject.toml`'s layers contract.
- **Cross-DB exception:** only `stage9_incorporate.incorporate` imports `infrastructure.database`
  (`.connection`/`.queries`/`.models`) — the hole stays one file wide, mirroring Stage 1's read. The
  `ignore_imports` entry now exists (it did not when this note was a design stub).

## 1a. Prerequisite consumed: `merge_fact_runs` (Stage 8, REQ-122/#232)
Stage 9 writes from the **frozen gate@8 receipt** (`stage8_approval.receipt_json`), which is itself the
`merge_fact_runs` product (`load_closing_argument` runs the merge before freezing). So Stage 9 consumes the
canonical cumulative-truth resolution **without re-deriving** it — the design obligation from
`STAGE8_AGGREGATE_DESIGN.md`'s addendum is met by writing the signed artifact, never a live re-derivation
(which would risk drift from what the human approved).

## 2. Module layout (`infrastructure/acquisition/stage9_incorporate/`)
PURE/IO split mirroring `closing_argument.py`, so the cross-DB hole is one file wide:
- `provenance.py` — **pure**: year resolution (band-consensus school_year → content-URL year →
  current-year key), confidence bucketing, `#95` provenance / `notes` / `raw_import` builders, and
  `band_grade_span` (the grade→band substrate — §4).
- `mapping.py` — **pure**: frozen receipt → `list[BandWrite]`. One council `BandWrite` per determined band
  + one statutory-fallback `BandWrite` per claimed-but-unsatisfied band. No DB import; unit-tested against
  real receipts minted by `build_closing_argument`.
- `ledger.py` — governance-side: `record_incorporation` (the `incorporated` `state_event`, stage=9, via
  the free-string `checkpoint` column — no migration) + `latest_incorporation` (the idempotency read),
  plus `record_incorporation_blocked` / `latest_attempt` (#682 — see §2c).
- `incorporate.py` — the I/O orchestrator; the **only** file importing `infrastructure.database`.
- `__main__.py` — CLI: `python -m infrastructure.acquisition.stage9_incorporate <did…> [--dry-run|--force|--strict|--batch FILE]`.

## 2c. What TRIGGERS the write (#682)
Two callers, **one entry point** (`incorporate_district`) — they can never drift into two behaviours:
- **gate@8 approval** (the documented "Stage 9 then auto-writes" arrow, wired 2026-08-15). `POST
  /api/aggregate/decision/{did}` with `disposition='approved'` calls `_incorporate_after_approval`
  **after** the approval's session commits — Stage 9 opens its own governance session and re-validates
  the decision from the DB (the TOCTOU re-check), so it must be reading a committed world.
- **the CLI**, which stays the recovery/backfill/re-run path (the write is idempotent).

The approval is **precious and stands regardless**: a blocked or faulted write is reported in the
response and stamped as an `incorporation_blocked` `state_event` (status in `outcome`, the guard's own
words in the note) — never rolled back, never allowed to fail the human's decision. That stamp is the
point of the issue: without it, "approved but never written" is a *silence* (Worcester `2513230` sat
unwritten for 25 minutes in July with nothing in any surface saying so). `latest_attempt` reads the
newest outcome of either kind and drives the gate@8 header badge — *written* / *written — from earlier
facts* (fingerprint moved) / *approved, not written*. Wiring this does not weaken a gate: gate@8 IS the
human gate and the write behind it is ungated + deterministic, so the approval is exactly the
authorization the write acts on, and the write's own guards remain the only other gates.

## 2b. Control flow (`incorporate_district`, fail-loud)
1. **Governance read** (`gdb.session_scope`): `load_closing_argument` → live fingerprint;
   `decision_status(..., current_fingerprint=fp_live)` gates on `approved AND not stale` → else
   `not_eligible`. Pull the frozen `receipt_json` + `approval_id`. `ledger.latest_incorporation`
   short-circuits to `already_incorporated` when the incorporated fingerprint == live fp (unless `--force`).
2. **Pure map** (`plan_writes`) → council + statutory `BandWrite`s. `--dry-run` returns here.
3. **LCT write** (`connection.session_scope`, single txn): `add_bell_schedule` per band (statutory minutes
   resolved here from `StateRequirement`); `_reconcile_stage9_orphans` (delete this district's prior
   Stage-9 rows — `method IN ('council_extraction','statutory_fallback')` — whose `(year, grade_level)`
   dropped out, the year-change case; legacy rows untouched); **`_verify_written` re-queries and asserts
   minutes/method/minutes_basis before commit (Rule #6).**
4. **Governance stamp** (separate txn, *after* the LCT commit): the `incorporated` `state_event`, paired
   with an in-path `district_status.json` twin refresh and a `stage9_incorporate` per-district audit
   receipt (REQ-164, 2026-07-22 — always-stamped via `common/receipts.py::write_receipt`, written after
   BOTH commits) — closing the gap where the twin used to lag until an incidental later export and
   Stage 9 had no per-district disk receipt at all.

**Two-DB safety is ORDERING, not a distributed transaction** (the DBs are deliberately decoupled): LCT
commits before the governance stamp, so a crash between leaves LCT rows + a lagging ledger the next run
reconciles (its UPSERT is a no-op, verify passes, the stamp is re-written). A stamp with no LCT row cannot
occur.

## 2c. Never-fabricate integrity (#94 / REQ-049)
A **claimed** band absent from `receipt["bands"]` (present in `negative_space.unsatisfied_bands`) →
`method='statutory_fallback'`, `minutes_basis='statutory'`, minutes from `StateRequirement.get_minutes`
(or the 360 default), **no start/end**, `confidence='low'`, and a derived failure reason in `notes`.
Because both `method` and `minutes_basis` are statutory, `calculate_lct_variants.py::_is_statutory` keeps
the row labeled `source='statutory_fallback', year=None`, never counted as enriched — distinguishable from
a genuine council row. (Relies on #582's minutes_basis-aware reader.)

## 2d. Provenance (#95 / REQ-050)
Council band → `bell_schedules`: `grade_level`←band, `instructional_minutes`←`gross_minutes`,
start/end←representative school, `method='council_extraction'`, `minutes_basis='gross_bell_to_bell'`,
`schools_sampled`←fact-side per-school list, `source_urls`←deduped evidence URLs, `confidence`←coverage
bucket, `raw_import`←the re-verify bundle `{facts_fingerprint, approval_id, receipt_band, provenance,
sampling, year_basis, band_grade_span, incorporated_at, actor}`. The one LCT-side change was a
`raw_import` kwarg on `add_bell_schedule` (create-set; update only when non-None, per the #26
preserve-on-None discipline).

**`band_grade_span` is sourced from the LIVE roster at incorporation, NOT the frozen receipt** — the roster
is explicitly unsigned (excluded from the fingerprint; roster drift must never stale an approval; "derive
from ccd_sch live, never freeze", Ian 2026-07-14), and pre-#499 frozen receipts carry no `slot_projection`
at all, so freezing it would leave every existing approval's span empty. Recorded `basis="unhashed (live
roster at incorporation)"`. It is span-aware and merged-shape-correct (a PK-12 / K-8 school appears in every
band its grades reach) — the substrate the §4 projection weights by.

## 2e. Idempotency / correction
UPSERT on `(district_id, year, grade_level)` (byte-identical re-run); a corrected re-approval (new
fingerprint) overwrites in place; a council↔statutory flip overwrites `method`/`minutes_basis`; a
year-change is handled by `_reconcile_stage9_orphans`; the governance ledger short-circuits an unchanged
fingerprint.

## 2f. Tests
- `tests/test_stage9_mapping.py` — pure unit (11): council→row, all-3-bands faithful, unsatisfied→statutory,
  year precedence (+ COVID skip, + no-signal default), confidence buckets, url dedup, grade-span capture
  (present + absent-projection), and the CLI `--batch` indented-comment guard.
- `tests/test_stage9_incorporate_integration.py` — govdb+integration (21): a real ledger round-trip, plus
  the cross-DB write against real Postgres — write+stamp, statutory fallback, reader-labels-statutory,
  idempotent re-run, re-approval correction, council→statutory orphan reconcile, the **per-grade projection**
  (written, reprojects/reconciles on re-approval, weighted-secondary minutes, verified-in-DB), the standing
  **walls** (benchmark refused, legacy-row collision fails loud + surfaced in `--dry-run`, TOCTOU
  decision-changed writes nothing), statutory-flip clears council times, statutory-minutes
  case-insensitive/zero-safe, `--dry-run` resolves statutory minutes + flags a retraction, and
  missing-LCT-district fails loud. The governance READ half is patched at a documented seam (it is
  unit-tested in `test_closing_argument`/`test_stage8_approval` and exercised by the live-DB smoke).

## 2g. Standing walls (PR #607 max-effort review, 2026-07-21; the benchmark wall RE-KEYED 2026-07-26)
- **Benchmark wall — now FACT-PROVENANCE grain, not district membership (epic #617's #619).** The
  original wall (built PR #607, described below the line) refused any district that had EVER been a
  `batch_type='benchmark'` batch member — permanent, because `batch_district` rows are never deleted,
  which walled off all 27 `batch_00000` districts FOREVER, including correct minutes from later honest
  production re-runs (`_is_benchmark_district` mirrored Stage 7's then-`_benchmark_district_ids`, which
  Stage 9 cannot import — process_governance sits above this layer). **Retired 2026-07-26** and replaced
  by `_is_benchmark_receipt` (`incorporate.py`): it asks whether the APPROVED RECEIPT's own write-bearing
  evidence (`rec_key`/`fact_id` from `bands[*].schools[*]`, read via `provenance.
  collect_write_bearing_sources`, this stage's own module) carries benchmark provenance — via the shared two-arm predicate in
  `common/benchmark.py::is_benchmark_provenance` (arm 1: `handoff.dispatch_type='benchmark'`; arm 2: the
  fact's rep traces to a `capture.source='benchmark_gt'` injection) — THE SAME predicate the gate@8 queue
  now uses (`STAGE8_AGGREGATE_DESIGN.md` §2). The check moved to run AFTER the receipt loads, so it
  interrogates the very artifact Stage 9 writes from rather than a parallel district lookup, and it
  refuses on ANY benchmark-provenance evidence in the receipt (never drops just the tainted fact — an
  approved number is never silently changed; #618's "refuse, never coerce"). Measured behaviour-preserving
  at re-key time (83/83 district agreement between the two rules, 0 disagreements) — the two rules diverge
  only once a re-run mints fresh reps for a district that ALSO holds injected ones, which is exactly
  `batch_00000`'s re-run case and the reason the re-key exists. The escape hatch for a re-run district that
  still traces to a stale injected school it no longer relies on is a human `band_exclusion` (#257) at
  gate@8, applied BEFORE mode computation — not a code exception (`STAGE8_AGGREGATE_DESIGN.md` §2/`merge_fact_runs`
  documents why a blanket "drop the injected fact" mechanism was considered and withdrawn as #662's fix
  instead). Full account: `docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`
  §10.9–§10.13, §10.20, §12.5.
- **Foreign-row collision → FAIL LOUD.** A Stage-9 write whose `(year, grade_level)` key is already
  held by a NON-Stage-9 method (`human_provided`, `tier_*`, legacy) raises — human/legacy work is
  never silently overwritten; a person resolves the conflict (remove the manual row, or exclude the
  band at gate@8) and re-runs. `--dry-run` surfaces the conflict (and any retraction) instead of
  raising, so the preview shows it. (R2 replaced an earlier "silently skip protected bands", which
  orphaned the skipped band's per-grade rows and left the human value invisible to the LCT calc.)
- **TOCTOU re-check.** The receipt Stage 9 writes from is re-validated (still approved, same
  `approval_id`) against the decision the eligibility gate saw — a concurrent gate@8 action between the
  two governance reads cannot smuggle a different determination into production (the PR #252 class).
- **Retract-on-empty.** An approved receipt that carries zero bands, for a previously-incorporated
  district, falls through to Phase C so the prior rows are reconciled away (an empty re-approval
  retracts, it doesn't linger).
- Misc: district-id normalized before every governance read (id-drop → wrong verdict fixed);
  `_statutory_minutes` uses the canonical case-normalized lookup and treats only NULL (not 0) as absent;
  `init_precious_schema()` on entry so a standalone/cron run against a fresh governance DB doesn't crash;
  council→statutory flip clears the retracted council clock times; `--dry-run` resolves statutory
  minutes read-only so the preview shows real numbers.

## 3. Standing comparison obligation — the 18-district holdback (Ian, 2026-07-02)
`data/benchmark/benchmark_holdback_18.json` records the ORIGINAL band-level findings for the 18 districts
of the 41-district benchmark manifest NOT in batch_00000's 27. When they flow through the FULL pipeline to
Stage 9, compare final per-band gross minutes against those recorded values (drift expected — live
re-capture, different school years). Frozen-era sources survive in
`data/archive/gt-benchmark-20260622T152627Z/raw_bell_schedule_pdfs/`.

## 4. The LEA-level per-grade minutes projection — BUILT (#605/#606, 2026-07-21)
The link that makes approved minutes actually move LCT numbers, dissolving the 3-band-minutes vs
2-band-staffing mismatch (bands float per district — a "middle" may be 5-8 or 7-9; merged K-8 shapes
exist). All LEA-grain, no new data.

**#605 — projection + table (`stage9_incorporate/per_grade.py`, migration 025).** For each district,
`project()` maps **grade → owning band** from the live `raw_import.band_grade_span` (`gslo..gshi` per
band), falling back to the band's canonical range only when a span is absent. Each grade takes its
band's modal minutes (council or statutory, label preserved). Non-clean LEAs (a grade served by ≥2
bands — e.g. a floating 7-9 middle overlapping a 9-12 high at grade 9) → a deterministic tie-rule: the
grade's canonical band wins when it is among the serving set; when it is NOT (a noisy-span shape), the
fallback deterministically prefers the lowest band (arbitrary but stable), honestly recorded as such in
`overlap_flag` (never silent). Materialized into **`district_grade_minutes`** (one current row per
district×grade, `KG`..`12`; `method` chk-constrained per migration 026) in the LCT DB, written +
reconciled AND **verified-in-DB (Rule #6, like bell_schedules)** inside Stage 9's write transaction.
Reproject = re-incorporate (`--force`).

**#606 — LCT consumption (`scripts/analyze/per_grade_lct.py`).** `calculate_lct_variants.py` now derives
each scope's minutes as `minutes_scope = Σ_g (minutes[g]·enroll[g]) / Σ_g enroll[g]` over the scope's
grades (base K-12, elementary K-5, secondary 6-12), weighting by `EnrollmentByGrade.enrollment_grade_*`.
The secondary variant no longer reuses the high-band value — it weights mid+high. **Guarded:** only
districts with a projection change; the legacy band cascade is untouched for everyone else, so the
recompute is a no-op until real districts are incorporated. Sources: `per_grade_bell` /
`per_grade_mixed` (tier 2, and they populate `bell_schedule_source_year` so the migration-008 temporal
trigger sees the bell year) / `per_grade_statutory` (tier 3, year=None — stays distinguishable, #582).
Temporal window (REQ-026): **every** distinct measured year in a scope (not just the modal one) must
form a ≤3-consecutive-year set with staff/enrollment, else the whole scope drops to statutory. A grade's
statutory value is Stage 9's stored value (resolved against its REAL serving band) — never re-derived
from the canonical band.

**`human_vouched` — a gate@8 determination exempts a band from the REQ-026 window (#626/#636, built
alongside the incorporation campaign).** `provenance.py::band_human_vouched(band)` is true when any
INCLUDED school in the band carries a human determination at gate@8 — a `human_override` (incl. a
note-only approval), an applied times-override, or a hand-added cited fact (`human_added`, #474);
excluded (struck-through) schools never count. A human sign-off is durable + auditable (a named actor
took responsibility), so it renders the band's value acceptable past the window on the same footing as
an in-window schedule (Ian, 2026-07-24). `bell_schedules.human_vouched` is the source of truth (set at
Stage 9 write time); `district_grade_minutes.human_vouched` is its **projection**, inherited per grade
from the grade's owning band (`per_grade.py::project`, migration 028). `per_grade_lct.py` excludes a
human-vouched grade's year from `window_years` entirely before the REQ-026 check runs, so it can never
by itself force a scope to statutory.

**SPED scope consequence (documented, not a separate override).** The SPED-segmented variants
(`core_sped` / `teachers_gened` / `instructional_sped`) follow the shared K-12 `minutes` value by the
standing "base scopes use the K-12-wide value" convention — so an incorporated district's SPED LCT uses
the per-grade-weighted K-12 minutes. This is intentional and consistent with every other base scope; the
`per_grade_lct_sample` before/after surfaces the secondary scope specifically, but the K-12 delta it
reports is the same value SPED inherits.

**Sign-off gate:** the methodology change recomputes every secondary value once districts are
incorporated. `python -m infrastructure.scripts.analyze.per_grade_lct_sample` prints the legacy-vs-
per-grade before/after (minutes + secondary LCT) for review before a full recompute.

**"Legacy" is a stored-row read, not a live re-derivation (bug found + fixed 2026-07-22, PR #610).**
The first version of `per_grade_lct_sample` reconstructed "legacy" live via `get_instructional_minutes()`,
whose pre-existing REQ-024 fallback (high → middle → elementary, for K-8 districts) picks up ANY measured
`bell_schedules` row — including one Stage 9 had *just* written for the district being sampled. So the
moment a district was incorporated, "legacy" silently stopped meaning "what's live in `lct_calculations`
right now" and started meaning "what the old formula computes today, contaminated by today's own write" —
caught reviewing district 3601002: the contaminated comparison reported Δ=0, while the true stored
production value was 330min/9.35 LCT vs. the real 455min/12.88 per-grade result. Fixed by reading the
stored `lct_calculations.teachers_secondary` row directly — the real current production baseline,
unaffected by anything Stage 9 writes afterward — via a bulk `_legacy_secondary_by_district()` fetch (no
N+1), ordered by `year DESC` then `calculated_at DESC` (not `calculated_at` alone: a TARGET_YEAR recompute
clears only its own year, so an out-of-order backfill of a stale year must not outrank the newest year).
Because legacy (stored vintage) and per-grade (today's enrollment/staff picks) can now draw from different
data vintages, each row carries a `denom_refreshed` flag when the stored row's staff/enrollment years
differ from today's — so a reviewer never mistakes a data refresh for the per-grade methodology effect.
`main()` also gained a None-guard on the Δ subtraction: a never-computed district (no prior
`lct_calculations` row at all — the common case for a *freshly* incorporated district, e.g. Lincoln MA)
now prints cleanly instead of crashing the whole report. Live-validated against three real districts
(Brownsville Ascend NY, Lincoln MA, Coffee County AL — see PROJECT_HISTORY.md 2026-07-22).

**Caveats (documented):** both minutes and enrollment are LEA-grain — within-LEA school-to-school
variation is a deliberate simplification, not a per-school split; `band_grade_span` is
live-at-incorporation, so a persisted span can lag a later roster change (acceptable for a weight). A
district's staff/enrollment data COMPLETENESS also gates whether its per-grade minutes clear the REQ-026
temporal window — issue #611 found the 2024-25 NCES ingest had silently dropped ~3,125 districts (every
FIPS<10 state, a LEAID leading-zero normalization bug), which stranded their staff/enrollment at 2023-24
and pushed them 4 years from the bell key, dropping the per-grade minutes to statutory. Fixed + re-ingested
(see `docs/REQUIREMENTS.yaml` REQ-002); a district whose per-grade minutes unexpectedly read as
`per_grade_statutory` despite real council data being incorporated is a symptom worth checking against
NCES coverage, not assumed to be a Stage 9 bug.
