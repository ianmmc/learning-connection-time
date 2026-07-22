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
  the free-string `checkpoint` column — no migration) + `latest_incorporation` (the idempotency read).
- `incorporate.py` — the I/O orchestrator; the **only** file importing `infrastructure.database`.
- `__main__.py` — CLI: `python -m infrastructure.acquisition.stage9_incorporate <did…> [--dry-run|--force|--strict|--batch FILE]`.

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
4. **Governance stamp** (separate txn, *after* the LCT commit): the `incorporated` `state_event`.

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
- `tests/test_stage9_mapping.py` — pure unit (10): council→row, all-3-bands faithful, unsatisfied→statutory,
  year precedence (+ COVID skip), confidence, url dedup, grade-span capture.
- `tests/test_stage9_incorporate_integration.py` — govdb+integration (9): a real ledger round-trip, plus
  the cross-DB write against real Postgres (write+stamp, statutory fallback, reader-labels-statutory,
  idempotent re-run, re-approval correction, council→statutory orphan reconcile, not-eligible writes
  nothing, missing-LCT-district fails loud). The governance READ half is patched at a documented seam
  (it is unit-tested in `test_closing_argument`/`test_stage8_approval` and exercised by the live-DB smoke).

## 2g. Standing walls (PR #607 max-effort review, 2026-07-21)
- **Benchmark wall.** batch_00000 (`batch_type='benchmark'`) districts are REFUSED — "Stage 9
  (non-benchmark only) is the sole promoter to `bell_schedules`" (CLAUDE.md's permanent wall).
  `_is_benchmark_district` mirrors Stage 7's `_benchmark_district_ids` (which Stage 9 cannot import —
  process_governance sits above this layer).
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
