# Stage 7 — Extract: design (NOT STARTED)

> **Status: DESIGN — not started, not built.** Seeded from the APGA console user stories (migrated here
> 2026-06-27 from the retired `docs/scratch-paper/apga_console_application_stage_view.md`). This is the
> place Stage 7 will be designed when we get to it — same role STAGE6's note started in.

**Companions / authority:** `ACQUISITION_PIPELINE.md` §7 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
§11 (gates/console), `LLM_COUNCIL_RESEARCH_2026-06.md` (council research), `EXTRACTION_BENCHMARK_FINDINGS.md`
(model leaderboard + costs). Upstream: `STAGE6_DISPATCH_DESIGN_2026-06.md` (the dispatch package Stage 7 consumes).

---

## 1. Purpose & boundary (provisional)
Stage 7 is the **council extraction**: the assigned OpenRouter model council reads the handed-off
representations and returns per-school `{start_time, end_time, grade_level, school_name}` facts (the
INVARIANT — models read TIMES, deterministic code computes minutes + the mode; REQ-054). The council may
**request more evidence** rather than answer blind. The gate is **`gate@7`** (review the council's requests
/ recommendations). Consensus = the cross-family per-school (start,end) pair, ±15 min (REQ-056).

## 2. Console view — user stories (seed)
- As a user, I want to **review requests and recommendations** from the extraction council — e.g. retrieve
  the screen-capped PNG for a given URL, retrieve the PDF for a given URL, recapture a given URL, or redo
  discovery with a different tailored search query.
- As a user, I want to **accept or reject** requests and recommendations from the extraction council.

## 3. Open (to design when we reach this stage)
- The council-request protocol (what a model can ask for, how a request routes back: PNG/PDF retrieval →
  the existing capture dir; recapture → Stage 3; tailored re-discovery → Stage 1, per the cyclic back-edges
  7→1 / 7→6, governance §11e).
- The judge step (research: judge > extra voter) — part of the council config (Stage 6) vs a fixed Stage-7 step.
- Escalation on no-consensus (cascade to a stronger config vs flag) — ties to the Stage 6 cascade.
- `gate@7` manual/auto (auto = confidence-escalating, governance §11b).
