# Stage 9 — Incorporate: design (NOT STARTED)

> **Status: DESIGN — not started, not built.** Seeded from the APGA console user stories (migrated here
> 2026-06-27 from the retired `docs/scratch-paper/apga_console_application_stage_view.md`).

**Companions / authority:** `ACQUISITION_PIPELINE.md` §9 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
§11, `DATABASE_SETUP.md` (the LCT DB schema). Upstream: `STAGE8_AGGREGATE_DESIGN_2026-06.md`.

---

## 1. Purpose & boundary (provisional)
Stage 9 **delivers** the district's daily instructional minutes by band into the **LCT production database**
(the sanctioned Stage-9 *write* across the acquisition→LCT boundary — one of the two named exceptions in
the import-linter layering contract; the other is Stage 1's read). It is **ungated and mechanical**:
`gate@8` is the last human checkpoint; once results are approved there, Stage 9 auto-writes (governance §11).

## 2. Console view — user stories (seed)
- (No standalone console stories were specified in the APGA review beyond the Stage-8 gate that precedes
  the write — Stage 9 is the mechanical write that follows an approved `gate@8`.)

## 3. Open (to design when we reach this stage)
- The target LCT tables/columns the band-level minutes land in, and how they join the existing
  enrollment/staff data for the LCT calculation (labeled `gross_bell_to_bell`).
- Idempotency + provenance of the write (fail-loud on mismatch, Rule #6 verify-in-DB), and how a re-ingest
  / corrected aggregation updates an already-written value.
- Whether Stage 9 emits a `state_event` (`incorporated`) closing the district's per-band lifecycle.
