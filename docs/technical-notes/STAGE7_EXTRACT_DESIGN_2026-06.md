# Stage 7 — Extract: design + partial present state

> **Authority:** §4 (the request-more-evidence loop, DESIGNED 2026-07-03) is authoritative for that
> protocol. The council-extraction CORE (§0) is BUILT (REQ-117) — but the code is ground truth
> (`infrastructure/acquisition/stage7_extract/`, `process_governance/stage7_run.py`); this note is **not
> yet rewritten present-state-first** (a follow-up). §2 (console stories) + §3 (remaining open items) are seed.
> **Audience:** whoever builds the request loop + the gate@7 console; anyone tracing Stage 7's shape.
> **Companions:** `ACQUISITION_PIPELINE.md` §7 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
> §11 (gates/console; §11b the ramp-up model), `LLM_COUNCIL_RESEARCH_2026-06.md` (council research),
> `EXTRACTION_BENCHMARK_FINDINGS.md` (model leaderboard + costs). Upstream: `STAGE6_DISPATCH_DESIGN_2026-06.md`
> §0a (the exact handoff shape Stage 7 consumes).
> **Update this when:** Stage 7 design decisions are made (append below) or the stage is built (rewrite
> this doc present-state-first, per every other `STAGE*_DESIGN` note).

**Status: CORE BUILT (REQ-117); the request-more-evidence loop (§4) + gate@7 console DESIGNED, not built.**
The council extraction — the OpenRouter client, per-rep council → cross-family consensus → judge, per-school
persistence, and GT scoring — is built and validated. The `batch_00000` full **text** run (24 districts /
83 reps, 2026-07-03) scored **95.2% band / 99.3% per-school** hit-rate vs the 940-time curated GT at
**$0.065**; a full **image**-council run (vision on raster PNGs) ran alongside for a text-vs-vision compare.
`batch_type == "benchmark"` output is never Stage-9-written or counted in enrichment stats
(`STAGE6_DISPATCH_DESIGN` §3C C.6).

## 0. As-built (code is ground truth) — REQ-117
- `stage7_extract/` (independent stage, common-only): `openrouter.py` (paid SSE-streaming client — token/cost
  telemetry, generation-id, truncation flag, 401/402 halt); `parse.py` (fence/truncation-tolerant + a
  prompt-example leak guard); `content.py` (image→data-URL, PNG-only); `validate.py` (per-band + per-school
  GT scoring); `models.py` (precious `extraction` + `school_fact` tables — GOVERNANCE DB, never the LCT DB).
- `process_governance/stage7_run.py` (app-layer glue, mirrors `stage6_dispatch.py`): reads a frozen handoff,
  resolves rep content, runs the council **one district at a time** (`run_council_streaming` — durable +
  **resumable**: each district persists as it finishes; a re-run skips districts already extracted for the
  handoff), streams per-rep/per-district progress, persists (`extraction`/`school_fact` + `stage=7`
  state_event), writes a per-district receipt, and GT-scores. Reuses Stage 6 request assembly + Stage 8
  consensus/mode.
- Council consensus is cross-family on the per-school (start,end) pair ±15 min (REQ-056), keyed by full
  OpenRouter model id against the canonical `common.model_families` map; per-band value = the exact mode
  (REQ-055 gross bell-to-bell).

**Ready and waiting → RUN.** `batch_00000` (the 27 curated-GT districts, `STAGE1_QUEUE_DESIGN` §2h) was
Stage 7's first-build scoring corpus; the run results are above.

---

## 1. Purpose & boundary
Stage 7 is the **council extraction**: the assigned OpenRouter model council reads the handed-off
representations and returns per-school `{start_time, end_time, grade_level, school_name}` facts (the
INVARIANT — models read TIMES, deterministic code computes minutes + the mode; REQ-054). Consensus = the
cross-family per-school (start,end) pair, ±15 min (REQ-056). When evidence is insufficient, the pipeline
**gets more** via the **request-more-evidence loop** — but detection + routing are **deterministic scripts**,
not the model (§4). The gate is **`gate@7`** (review the routed requests + the extraction results).

## 2. Console view — user stories (seed)
- As a user, I want to **review requests and recommendations** from the extraction council — e.g. retrieve
  the screen-capped PNG for a given URL, retrieve the PDF for a given URL, recapture a given URL, or redo
  discovery with a different tailored search query.
- As a user, I want to **accept or reject** requests and recommendations from the extraction council.

## 3. Open (to design/build) — status
- The **council-request protocol** → **DESIGNED (deterministic-first), see §4.** Build pending.
- The **judge step** → **BUILT.** The judge is part of the council config (Stage 6); Stage 7 fires it on a
  voter disagreement (re-reads the same rep, consensus re-run with its rows). REQ-056.
- **Escalation on no-consensus** (cascade to a stronger config vs flag) — still open; ties to the Stage 6
  cascade lever (`STAGE6_DISPATCH_DESIGN` §3B). Today a no-consensus (band,school) is simply held as
  `unresolved` (surfaced for gate@7), not auto-escalated.
- **`gate@7` manual/auto** — the gate itself (a review surface + the accept/route decision) is unbuilt; when
  built it follows the ramp-up model: manual now, auto-with-confidence-escalation later (governance §11b).

---

## 4. The request-more-evidence loop — DESIGNED 2026-07-03 (deterministic-first)

**When the council can't confidently answer, the pipeline gets more evidence via the cyclic back-edges
(7→6/3/2/1).** Two framing decisions (Ian, 2026-07-03) fix the shape; the third is the build posture.

**(a) Routing = deterministic scripts, NOT the model — the REQ-054 read-vs-decide split, extended.** The
council reads/assesses; **deterministic local code decides what to do about insufficiency.** Rationale
(Ian): scripts are more **auditable**, run **locally**, and cost **zero OpenRouter tokens/calls** — "the
more we can rely on scripts, the better." Same split as REQ-054 (extractors read TIMES; code computes
minutes/mode), now applied to routing. The need→route map is **config-as-data the Council Lab tunes**
(GitHub #80).

**(b) Three altitudes — the pipeline's own hierarchy (district → URL → representation).** Each is a
deterministic post-extraction check with its own back-edge:

| altitude | insufficiency signal (script-detected, from data we already hold) | route |
|---|---|---|
| **representation** | this rep yielded 0 usable facts / wrong modality — parse returned nothing, `visual_text_gap`, `n_times == 0`, or the council call errored | **7→6** — re-dispatch a *different already-captured rep* of the SAME URL (e.g. text→vision). No new capture. |
| **URL** | *all* reps of this URL are exhausted and still yield no facts for its band(s) | **7→3** — recapture the URL differently, or mark it barren |
| **district** | a *claimed band* (from the NCES grade span) has **0 accepted facts** across all its URLs | **7→2** targeted rediscover for that band, or **7→1** a follow-up batch adding specific schools |

**(c) Deterministic-FIRST (start with ZERO model involvement) — APPROVED (Ian, 2026-07-03).** The loop is
*triggered by* the council run (you only learn a rep is unreadable by trying to extract it) but **detected
and routed entirely by scripts** reading the extraction OUTCOME + existing signals (fact counts,
`visual_text_gap`, `n_times`, band-coverage vs NCES claims, per-call errors). **The council emits nothing
new.** A narrow model "**referenced-but-unread**" assessment (a page that clearly *links to* a schedule it
doesn't itself contain — the one case a script can't derive) is **deferred**; add it only if a measured
pass shows scripts miss real cases (the measured-pass discipline — memory `feedback-explore-before-scoring-changes`).

### 4a. Shape of the build (when we get to it)
- **Where:** `stage7_extract/requests.py` — pure, deterministic, local, **zero paid calls**, fully
  unit-testable. Input: a `run_council_streaming` per-district result + the district's reps/signals.
  Output: routed **request objects**.
- **Request object + persistence:** a precious governance table (`extraction_request` — GOVERNANCE DB):
  `{altitude, route (7→6/3/2/1), target (district_id / url / rec_key), params (the rep to swap to; the
  band + keywords for a search; the school names to add), reason, status (pending/approved/rejected/executed)}`.
- **Review = gate@7** — human now (ramp-up: manual-first), auto-with-confidence-escalation later
  (governance §11b). This is the review surface the gate@7 console (§2) will host.
- **Execution (re-entry):** an approved request triggers the target stage's *existing* machinery — 7→6 = a
  new Stage-6 re-dispatch (STAGE6 stories 58/59); 7→3 = Stage-3 capture of one URL; 7→2 = a targeted
  Stage-2 query; 7→1 = a reviewable follow-up batch (created at the return to Stage 1, gate@1). Results
  re-enter Stage 7.
- **Termination (must-have):** a per-district **request-depth guard** (max re-request rounds) + the
  **budget governor** (REQ-051) on any paid re-extraction — the loop must provably terminate and never run
  up unbounded OpenRouter spend.

### 4b. Motivating evidence (batch_00000 full run, 2026-07-03)
Two of the three band misses were coverage/routing gaps this loop would **self-correct**:
- **Essex high** — the real EHS bell-schedule rep (`Essex High School Bell Schedule.jpeg`) was **held at the
  5/6 seam** (tier-B, unlabeled) and never dispatched; the council fabricated a high row by spraying another
  school's hours. A **representation/7→6** request swaps the held image rep in.
- **New Haven Unified high** — the flagship comprehensive HS was absent from what was sent (GT's high band
  is only the continuation school). A **district/7→2 (or 7→1)** request goes and gets it.

The loop is the mechanism that would have caught both — which is why it's the highest-value next Stage-7
build after the gate@7 console (which is its review surface).
