# Stage 9 — Incorporate: design (NOT STARTED — landing zone is READY)

> **Authority:** none yet for the write logic itself (§1–§3 below); the **landing zone it writes into**
> (`bell_schedules` schema: `minutes_basis`, `chk_method` incl. `council_extraction`, 24-hour time
> acceptance, the COVID/malformed-year seam guard) is BUILT — see `DATABASE_SETUP.md` and the
> fable-review lct-core hardening (migration 019, `queries.add_bell_schedule`).
> **Audience:** whoever designs/builds Stage 9.
> **Companions:** `ACQUISITION_PIPELINE.md` §9 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
> §11, `DATABASE_SETUP.md` (the LCT DB schema — the "Two databases" section explains why this write
> crosses into the separate production LCT database). Upstream: `STAGE8_AGGREGATE_DESIGN_2026-06.md`.
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
