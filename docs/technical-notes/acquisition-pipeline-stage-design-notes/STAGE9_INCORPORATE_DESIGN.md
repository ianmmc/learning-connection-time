# Stage 9 — Incorporate: design (NOT STARTED — landing zone is READY)

> **Authority:** none yet for the write logic itself (§1–§3 below); the **landing zone it writes into**
> (`bell_schedules` schema: `minutes_basis`, `chk_method` incl. `council_extraction`, 24-hour time
> acceptance, the COVID/malformed-year seam guard) is BUILT — see `DATABASE_SETUP.md` and the
> fable-review lct-core hardening (migration 019, `queries.add_bell_schedule`).
> **Audience:** whoever designs/builds Stage 9.
> **Companions:** `ACQUISITION_PIPELINE.md` §9 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE.md`
> §11, `DATABASE_SETUP.md` (the LCT DB schema — the "Two databases" section explains why this write
> crosses into the separate production LCT database). Upstream: `STAGE8_AGGREGATE_DESIGN.md` —
> note that doc is no longer a pure stub: `stage8_aggregate/aggregate.py` has a real, tested prototype,
> and its 2026-07-11 addendum (added after this doc's own content was last substantially edited) covers
> `merge_fact_runs`, directly relevant here — see §1a below.
> **Update this when:** Stage 9 design decisions are made (append below) or the stage is built.

**Status: DESIGN — not started for the write logic; the landing zone is ready.** (tracked: #93) Seeded from the APGA
console user stories (migrated here 2026-06-27 from the retired
`docs/scratch-paper/apga_console_application_stage_view.md`).

---

## 1. Purpose & boundary (provisional)
Stage 9 **delivers** the district's daily instructional minutes by band into the **LCT production database**
(the sanctioned Stage-9 *write* across the acquisition→LCT boundary — one of the two named exceptions in
the import-linter layering contract; the other is Stage 1's read). It is **ungated and mechanical**:
`gate@8` is the last human checkpoint; once results are approved there, Stage 9 auto-writes (governance §11).

The enforcement point for the "sanctioned exception" claim is `pyproject.toml`'s import-linter contract
(`pyproject.toml:31-40`) — CI-enforced via `lint-imports`. Today its `ignore_imports` list carries only
Stage 1's read (`stage1_queue.queue_batch -> database.connection` / `.models`), with a comment noting Stage 9's
write is expected once built. **Stage 9's own `ignore_imports` entry does not exist yet** — adding it is a
small but real to-do for whoever builds this stage (see §3).

## 1a. Prerequisite artifact: `merge_fact_runs` (Stage 8, REQ-122/#232)
`stage8_aggregate/aggregate.py::merge_fact_runs` is real, tested, shipped code (added 2026-07-11 to fix a
gate@7 view bug) that resolves which of a district's per-`(band, school)` facts wins when Stage 7 has been
run more than once (e.g. an initial pass plus a follow-up round targeting coverage gaps). Its policy: an
accepted fact beats an unresolved one regardless of run order; among multiple accepted facts the *earliest*
run wins (a follow-up fills gaps, it never silently overwrites a solid earlier result — correcting one is a
gate@8 human call, not an automatic later-run override); among unresolved-only facts the *latest* run wins
(freshest diagnostic).

This is squarely upstream of Stage 9's write: whatever aggregation feeds the Stage-9 landing zone —
Stage 8 itself, or Stage 9's write logic directly if Stage 8's own gate/console isn't built first — needs
an answer to "which run's facts win" for districts with more than one Stage-7 run, and `merge_fact_runs` is
that answer. Per `STAGE8_AGGREGATE_DESIGN.md`'s own addendum, Stage 9 (or the Stage 8 aggregation
feeding it) should **consume this merge, or its direct descendant, rather than re-deriving cumulative truth
across runs independently**.

## 2. Console view — user stories (seed)
- (No standalone console stories were specified in the APGA review beyond the Stage-8 gate that precedes
  the write — Stage 9 is the mechanical write that follows an approved `gate@8`.)

## 2a. Standing comparison obligation — the 18-district holdback (Ian, 2026-07-02)

`data/benchmark/benchmark_holdback_18.json` records the ORIGINAL band-level findings for the
18 districts of the 41-district benchmark manifest that are NOT in batch_00000's 27. When these
districts eventually flow through the FULL pipeline (fresh discovery → Stage 9), compare the
pipeline's final per-band gross minutes against those recorded values — a then-vs-now check on
where we landed. Drift is expected (live re-capture, different school years) and is part of the
comparison story; their frozen-era source files also survive in
`data/archive/gt-benchmark-20260622T152627Z/raw_bell_schedule_pdfs/` if a drift-free
benchmark-injection tranche (via `stage1_queue/benchmark_batch.py`) is ever wanted.

## 3. Open (to design when we reach this stage)
- The target LCT tables/columns the band-level minutes land in, and how they join the existing
  enrollment/staff data for the LCT calculation (labeled `gross_bell_to_bell`).
- Idempotency + provenance of the write (fail-loud on mismatch, Rule #6 verify-in-DB), and how a re-ingest
  / corrected aggregation updates an already-written value. (tracked: #95)
- Whether Stage 9 emits a `state_event` (`incorporated`) closing the district's per-band lifecycle.
- **Honoring statutory-fallback / never-fabricate integrity at the write (tracked: #94, REQ-049).** A
  district where discovery finds nothing or the council can't agree must land as
  `method=statutory_fallback` — labeled, never counted as enriched (`ACQUISITION_PIPELINE.md` §9, Rule #6,
  REQ-024: "fail loud... Coverage ≠ enrichment"). The landing zone already reserves the vocabulary for
  this: migration 019's `chk_minutes_basis` constrains `minutes_basis` to `gross_bell_to_bell | statutory |
  NULL`, and `chk_method` includes both `statutory_fallback` and `council_extraction`. What's undesigned is
  how Stage 9's write logic decides which of those values to use for a given district-band and how it
  keeps that decision distinguishable downstream (e.g. from LCT queries) from a genuine council result.
- Adding Stage 9's own `ignore_imports` entry to the import-linter contract in `pyproject.toml` once the
  write module exists — the contract's comment already anticipates this, but the entry itself doesn't
  exist yet (see §1).
