# Stage 7 — Extract: design (NOT STARTED)

> **Authority:** none yet — this is the seed for Stage 7's future design, not a present-state doc. Nothing
> in §1–§3 below is built.
> **Audience:** whoever designs/builds Stage 7.
> **Companions:** `ACQUISITION_PIPELINE.md` §7 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
> §11 (gates/console), `LLM_COUNCIL_RESEARCH_2026-06.md` (council research), `EXTRACTION_BENCHMARK_FINDINGS.md`
> (model leaderboard + costs). Upstream: `STAGE6_DISPATCH_DESIGN_2026-06.md` (the dispatch package Stage 7
> consumes — its §0a documents the exact handoff shape).
> **Update this when:** Stage 7 design decisions are made (append below) or the stage is built (rewrite
> this doc present-state-first, per every other `STAGE*_DESIGN` note).

**Status: DESIGN — not started, not built.** Seeded from the APGA console user stories (migrated here
2026-06-27 from the retired `docs/scratch-paper/apga_console_application_stage_view.md`).

**Ready and waiting (2026-07-02):** `batch_00000` — the 27 curated-GT districts, injected from frozen
`gt_curation` artifacts (`STAGE1_QUEUE_DESIGN` §2h) — is dispatched through Stage 5 and ready for gate@6.
It exists specifically so Stage 7's first real build can be scored against 940 hand-verified per-school
times with zero site-drift confounding. `batch_type == "benchmark"` marks it; its output must never be
Stage-9-written or counted in enrichment stats (see `STAGE6_DISPATCH_DESIGN` §3C C.6).

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
