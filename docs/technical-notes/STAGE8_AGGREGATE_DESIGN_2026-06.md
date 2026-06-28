# Stage 8 — Aggregate: design (EARLY — modal aggregation prototyped)

> **Status: DESIGN — early; a modal-aggregation prototype exists** (`stage8_aggregate/aggregate.py`), but
> the stage is not wired end-to-end (it depends on Stage 7, not built). Seeded from the APGA console user
> stories (migrated here 2026-06-27 from the retired `docs/scratch-paper/apga_console_application_stage_view.md`).

**Companions / authority:** `ACQUISITION_PIPELINE.md` §8 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
§11 (gates/console; §11e cyclic back-edges), `METHODOLOGY.md` (the metric: gross bell-to-bell, the mode).
Upstream: `STAGE7_EXTRACT_DESIGN_2026-06.md`. Downstream: `STAGE9_INCORPORATE_DESIGN_2026-06.md`.

---

## 1. Purpose & boundary (provisional)
Stage 8 turns the council's per-school `{start,end}` (or an explicitly-stated minutes figure) into
**daily instructional minutes by band** for the district: deterministic code computes `gross = end − start`
and the **per-band exact mode** across the band's schools (REQ-054; the metric = gross bell-to-bell,
240–510 min plausibility gate, REQ-055). The gate is **`gate@8`** — review per-band results before the
mechanical Stage-9 DB write; this is the **effective old "CP-C."** Completion grain = district × **band**
(schools are instrumental; governance §11d).

## 2. Console view — user stories (seed)
- As a user, I want to **re-queue a district where there are coverage gaps for a given band** — which
  creates a new Stage-1 batch focused on the missing bands (the 8→1 back-edge; the follow-up `batch_*.json`
  is reviewable at `gate@1`).
- As a user, I want to **add a URL to a new handoff** that shows up in Stage 6 (the 8→6 back-edge — re-route
  an existing representation, bypassing Stage 1).
- As a user, I want to see the **start and end times extracted for each representation**, OR the explicitly
  stated instructional minutes; for representations with start/end times, I want to see the **calculated
  daily instructional minutes**.
- As a user, I want to **manually edit/overwrite** the start and end times from each representation, and I
  want to be **required to provide an explanation** of why I'm overwriting the extracted values.

## 3. Open (to design when we reach this stage)
- The per-band satisfaction signal (what makes a band "confident" / "satisfied") — needed for follow-up
  batch creation (Stage 1 §5) and the drift detector (REQ-097).
- The aggregation record schema + how a manual override (with required reason) is stored and audited.
- `gate@8` manual/auto (auto = confidence-escalating; never writes minutes without confidence, governance §11b).
