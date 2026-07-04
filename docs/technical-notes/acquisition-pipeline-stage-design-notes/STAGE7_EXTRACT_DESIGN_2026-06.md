# Stage 7 — Extract: present state & decision log (REQ-117)

> **Authority:** what the code does today — the OpenRouter council client, per-rep council →
> cross-family consensus → judge, per-school persistence, GT scoring, the deterministic
> request-more-evidence **detection/routing** engine, and the gate@7 console. §0 maps the code (the
> ground truth); §1–§4 hold the design rationale, with items still genuinely open flagged inline.
> **Audience:** anyone building on or debugging Stage 7; anyone tracing extraction/consensus/the
> request loop.
> **Companions:** `ACQUISITION_PIPELINE.md` §7 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
> §11 (gates/console; §11b the ramp-up model), `models-and-council-composition/LLM_COUNCIL_RESEARCH_2026-06.md`
> (council research), `models-and-council-composition/models-and-council-composition.md` (the
> batch_00000 full-run report), `EXTRACTION_BENCHMARK_FINDINGS.md` (model leaderboard + costs).
> Upstream: `STAGE6_DISPATCH_DESIGN_2026-06.md` §0a (the exact handoff shape Stage 7 consumes).
> **Update this when:** Stage 7's code behavior changes. Design turns and superseded approaches
> belong in §6 (Provenance / decision log), not here.

**Status: BUILT through gate@7 review + request EXECUTION.** Council extraction, per-school persistence,
GT scoring, the deterministic request-more-evidence **detection + routing + review** engine, and the
gate@7 console are all built and validated against real `batch_00000` data. Request **execution** — an
approved directive firing the target stage's back-edge — is now **built** (REQ-118): the 7→6 direct
alternate-rep re-dispatch, and the 7→2/7→3/7→1 → Stage-1 follow-up-batch path, both gated by the REQ-051
budget governor + a per-district×band depth guard; see §3F. **Not yet run end-to-end on live non-benchmark
data** (batch_00000 is benchmark-walled) — the execution paths are unit/govdb-tested, not yet exercised
against a real request round-trip. (tracked: #122)

---

## 0. As-built (code is ground truth) — REQ-117

**Package:** `stage7_extract/` (independent stage, common-only imports, import-linter enforced):
- `openrouter.py` — the paid OpenRouter chat client. SSE-streaming (`stream: true`), accumulates
  deltas, reads `usage` (tokens/cost) off the final chunk, captures `finish_reason` (a `length` value
  is the truncation tripwire) and `generation_id` (for `/api/v1/generation` audit correlation) on every
  path including errors. `DEFAULT_MAX_TOKENS = 16000`. Raises `BillingAuthError` on 401/402 (halts the
  run rather than burning further calls on a dead key).
- `parse.py` — tolerant JSON parser: markdown-fence stripping, salvage-on-truncation, and a
  prompt-example-leak guard (`_is_prompt_leak`) that drops any row whose `school_name` matches a
  **self-evident bracketed placeholder** (e.g. `"[school name]"`) in both the clean-parse and
  salvage paths. `"fivay high"` was REMOVED from this set (#144) — it is a real Pasco County FL
  school, and blacklisting it permanently blinded extraction to it; the prompt itself no longer
  contains the string (replaced with `[SCHOOL NAME]`), so that specific leak cannot recur. Never
  add a real school name here — fix the prompt instead.
- `content.py` — `image_data_url()` (base64 data-URL; `.webp`→PNG conversion exists but the picker never
  selects `.webp` — PNG-only, per Ian) and `is_image_kind()`.
- `requests.py` — the request-more-evidence **detection/routing engine** (§4): pure, no DB/network,
  fully unit-testable.
- `validate.py` — the GT-scoring harness: `load_gt()`, `score_district()` (per-band hit/miss/gap/extra +
  per-school hit/miss via the shared `common.school_match.norm_school`), `score_run()` (aggregate).
- `models.py` — SQLAlchemy models on the governance DB (`gdb.Base`), all **precious** (append-only,
  human-reviewed, never touched by Stage-5's drop+rebuild ingest): `Extraction` (rollup + telemetry per
  run), `SchoolFact` (per-school accepted/unresolved facts), `ExtractionRequest` (the request-more-evidence
  directives — `altitude`, `route`, `target`, `band`, `params_json`, `reason`,
  `status` ∈ {pending, approved, rejected, executed}, `reviewed_by`/`reviewed_at`/`review_note`).

**App-layer glue:** `process_governance/stage7_run.py` (mirrors `stage6_dispatch.py`):
- `run_council_streaming()` — the production entry point. Processes **one district at a time**,
  persists immediately per-district (not batched at the end), so a crash mid-run loses at most one
  district's work. **Resumable** (`resume=True`, the default): re-running a handoff skips districts
  already present in `extraction` for that `handoff_hash` (`_already_extracted`). Prints per-rep and
  per-district progress lines as it runs — a snag is visible at the district/rep where it happened, not
  only at the end.
- `_run_district()` — the shared per-district council-run core: 2 voters → `AGG.consensus_school_facts`
  (cross-family, per-school (start,end) pair, ±15 min, REQ-056) → judge fires only on disagreement →
  `AGG.district_bands_from_facts` (the per-band exact mode, REQ-055 gross bell-to-bell). Reuses Stage 6's
  request assembly and Stage 8's consensus/mode code — Stage 7 does not re-derive either.
  Model-family membership is read from the single canonical `common/model_families.py` (keyed on full
  OpenRouter ids), also used by Stage 8 — see the decision log (§6) for the bug this fixed.
- `image_handoff_variant()` — rewrites a text handoff to route PNG reps to the vision council for a
  text-vs-vision compare; `_pick_png()` prefers `raster_p-1.png`, else any `.png`, never `.webp`/`.jpg`.
  Gives the image variant a **distinct `handoff_hash`** (`<base>-<council_id>`, e.g. `-image`) so its
  resume logic can't collide with the source text handoff's already-persisted districts (§6).
- `detect_and_persist_requests()` — runs `requests.detect_requests()` against a just-persisted district
  result and writes `ExtractionRequest` rows, natural-key deduped on `(handoff_hash, target, altitude,
  route, band)`; re-detecting an already-reviewed request preserves its human review status rather than
  resetting it to pending. `backfill_requests()` does the same from receipts already on disk, without
  re-extracting (for retrofitting requests onto a run persisted before the detector existed).
- `write_receipt()` / `write_district_receipt()` — per-run and per-district JSON under
  `data/acquisition/extractions/` (regenerable, auditable — never the transport; governance's
  DB-is-the-working-store rule).
- `main()` CLI: `--mode {plumbing,council,image}`, `--persist`, `--validate --gt <path>`, `--no-resume`,
  `--no-judge`, `--limit`.

**gate@7 console** (`process_governance/server.py` + `static/stage7.js`):
- `GET /api/extract/districts` — attention-sorted (most pending requests first) list; excludes
  `-image` probe handoffs (the district-first view shows the primary/text extraction).
- `GET /api/extract/district/{district_id}` — the latest non-image extraction: computed band rollup
  (via `AGG.district_bands_from_facts`), accepted/unresolved facts, and the request directives for
  that district.
- `POST /api/extract/request/{request_id}` — approve/reject/reopen, recording `reviewed_by`/
  `reviewed_at`/`review_note`.
- `stage7.js` — district-first left pane (Ian's UI call: "organize by district with requests related to
  them"), attention-sorted with an "N REQ" badge; detail pane shows the band rollup (labeled as
  Stage-8-owned/authoritative — Stage 7's rollup is a preview), request cards with Approve/Reject/Reopen,
  accepted-school and unresolved-fact tables. **Fact/band editing is out of scope for gate@7** (Ian:
  "Fact/band review is Stage 8: Aggregation") — gate@7 is read + the request accept/reject action only.

**Results (the `batch_00000` full-batch validation run, 24 districts / 83 reps, 2026-07-03):**
- **Text council** (Gemini 2.5 Flash-Lite + Mistral Small 24B → Qwen3-235B judge): **95.2% band /
  99.3% per-school** hit-rate vs. the 940-time curated GT, **$0.065** total.
- **Image council** (Gemini 2.5 Flash + Mistral Large 2512 → **DeepSeek V3.2** judge, as configured for
  this original run): **88.5% band / 98.1% per-school**, run alongside for a text-vs-vision compare.
  DeepSeek V3.2 is **non-vision-capable** and 404'd on every image judge call (0/33 resolved) — a real
  bug, filed as GitHub #82. **Fixed 2026-07-04**: the judge was swapped to the vision-capable
  `qwen/qwen3-vl-235b-a22b-instruct` (third family, distinct from the Google/Mistral voters) + a
  `councils.validate()` vision-capability guard was added so a text-only model can never again be
  assigned to an image-input council. A judge-replay measurement (Council Lab, `council_lab.py`) over
  the same 33 escalated reps confirmed the fix: **32/33 calls succeeded**, resolving **21/145**
  disagreements and improving accuracy to **89.1% band / 98.2% school** (see
  `COUNCIL_LAB_DESIGN_2026-06.md` §0 for the full scorecard). #82 is closed.
- Full findings (per-model cost profiles, reader-source yield, the 3 real band misses root-caused, the
  spray-fabrication interaction with the request detector) are in
  `models-and-council-composition/models-and-council-composition.md`.
- `batch_type == "benchmark"` output is never Stage-9-written or counted in enrichment stats
  (`STAGE1_QUEUE_DESIGN` §2h; `STAGE6_DISPATCH_DESIGN` §3C C.6).

**The request-more-evidence detection engine, validated on real data:** `requests.py` run over the
batch_00000 text results correctly flagged exactly the **4 genuine coverage gaps** the scorecard showed
(Mat-Su middle, Mesa high, Bangor elementary, Cleveland middle — the K-8 band-split quirk), each routed
`7→2` with the band's known schools, and **7 barren-rep alternate-exists cases** routed `7→6` — with
**zero false positives** across the 20 covered districts.

---

## 1. Purpose & boundary

Stage 7 is the **council extraction**: the assigned OpenRouter model council reads the handed-off
representations and returns per-school `{start_time, end_time, grade_level, school_name}` facts (the
INVARIANT — models read TIMES, deterministic code computes minutes + the mode; REQ-054). Consensus is
the cross-family per-school (start,end) pair, ±15 min (REQ-056). When evidence is insufficient, the
pipeline **gets more** via the **request-more-evidence loop** — detection + routing are deterministic
scripts, not the model (§4). The gate is **`gate@7`**: review the routed requests + the extraction
results, approve/reject.

## 2. Console — what's built vs. still open

Built (§0): district-first list, band rollup, accepted/unresolved facts, request cards with
approve/reject/reopen. **Still open** (deferred, not designed):
- Retrieve the screen-capped PNG / PDF for a given URL and view it inline from the console (currently a
  reviewer would go to disk). (tracked: #99)
- Recapture or redo-discovery actions triggered *directly* from the console UI, rather than via the
  request-approval → (future) execution path.

## 3. Escalation & gate posture

- **The judge step is built.** The judge is part of the council config (Stage 6); Stage 7 fires it on a
  voter disagreement (re-reads the same rep, consensus re-run with its rows). REQ-056.
- **Escalation on no-consensus** (cascade to a stronger config vs. flag) is **open** — ties to the
  Stage 6 cross-config cascade lever (`STAGE6_DISPATCH_DESIGN` §3B). Today a no-consensus (band,school)
  is simply held as `unresolved`, surfaced at gate@7, not auto-escalated.
- **`gate@7` is manual today** (review + approve/reject requests; no fact/band editing). It follows the
  ramp-up model: manual now, auto-with-confidence-escalation later, once reliability is proven
  (governance §11b).

---

## 4. The request-more-evidence loop

**When the council can't confidently answer, the pipeline gets more evidence via cyclic back-edges
(7→6/3/2/1).** Detection + routing are **built and validated** (§0); **execution is now built too**
(REQ-118, §3F). The whole loop — detect → route → gate@7 review → execute — is code; what remains is a
live non-benchmark run to exercise it.

**(a) Routing = deterministic scripts, not the model — the REQ-054 read-vs-decide split, extended.** The
council reads/assesses; deterministic local code decides what to do about insufficiency. Rationale
(Ian): scripts are more auditable, run locally, and cost zero OpenRouter tokens/calls — "the more we can
rely on scripts, the better." Same split as REQ-054 (extractors read TIMES; code computes minutes/mode),
now applied to routing. The need→route map is config-as-data the Council Lab tunes (GitHub #80).

**(b) Three altitudes — the pipeline's own hierarchy (district → URL → representation).** Each is a
deterministic post-extraction check with its own back-edge, implemented in `requests.py`:

| altitude | insufficiency signal (script-detected) | route |
|---|---|---|
| **representation** | this rep yielded 0 usable facts / wrong modality — parse returned nothing, `visual_text_gap`, `n_times == 0`, or the council call errored, and an alternate already-captured rep of the same URL exists | **7→6** — re-dispatch the alternate rep (e.g. text→vision). No new capture. |
| **URL** | all reps of this URL are exhausted and still yield no facts for its band(s) | **7→3** — recapture the URL differently, or mark it barren |
| **district** | a claimed band (from the NCES grade span) has **0 accepted facts** across all its URLs | **7→2** targeted rediscover for that band, or **7→1** a follow-up batch adding specific schools |

**(c) Deterministic-first (zero model involvement) — the approach taken.** The loop is *triggered by*
the council run (you only learn a rep is unreadable by trying to extract it) but detected and routed
entirely by scripts reading the extraction OUTCOME + existing signals. The council emits nothing new. A
narrow model "referenced-but-unread" assessment (a page that clearly *links to* a schedule it doesn't
itself contain — the one case a script can't derive) is **deferred**; add it only if a measured pass
shows scripts miss real cases (memory `feedback-explore-before-scoring-changes`).

**(d) The spray/detector interaction (validated on real data, 2026-07-03).** The detector correctly
stays silent when a band's coverage is fabricated rather than genuinely absent: Essex High's band
*looked* covered in the batch_00000 run because a prompt-spray defect copied another school's hours onto
it (a fact, just a wrong one) — the 0-facts detector can't distinguish a fabricated fact from a real one,
so it didn't flag the gap. This is not a detector bug; it's a real dependency. **The anti-spray fix
(GitHub #81) and the request loop are complementary, in this order:** fix the spray → Essex High becomes
a genuine 0-fact gap → the loop then catches it via `7→6` (swap in the held vision rep). Confirmed against
real detector output, correcting an earlier assumption that `7→6` would catch Essex directly (it can't
while the fabrication stands).

### 3F. Request execution — BUILT (REQ-118)

An approved directive now fires the target stage's back-edge. The key architectural collapse (Ian,
2026-07-03): **anything needing NEW capture/discovery routes through a Stage-1 follow-up batch, so there
are only TWO execution mechanisms, not four** — matching governance §11d ("directions route through
Stage 1; only re-routing EXISTING representations bypasses it"):

- **`7→6` — DIRECT alternate-rep re-dispatch** (`stage7_execute.execute_alternate_dispatch`). The
  alternate reps are **already captured, processed, AND labeled** — the gate@5 label attaches to the
  *record* (the URL/`rec_key`), not to an individual rep, so every rep of an already-reviewed record
  inherits it (`filtered.json` even carries "winner + alternates", the REQ-094 follow-up). So 7→6 needs
  **no new capture and no Stage-5 round-trip**: it synthesizes a one-record dispatch input from the named
  alternate rep (`build_alternate_input`, prefers the image rep for the text→vision escalation, defaults
  it to the `image` council), builds a NEW immutable Stage-6 dispatch via the pure `package.assemble_package`
  / `handoff.freeze` / `stage6_dispatch.record_dispatch` path (the prior dispatch untouched — history
  preserved), and it re-enters Stage 7 through the normal extract path. This is the one back-edge that
  bypasses **both** Stage 1 and Stage 5.
- **`7→2` / `7→3` / `7→1` — via a Stage-1 FOLLOW-UP BATCH** (`stage7_execute.compose_followup_batch` +
  `stage1_queue.build_followup_batch`). These need NEW discovery/capture → NEW representations that have
  **never been labeled** → they MUST flow through gate@5, so they are wrapped in a targeted, DRAFT
  follow-up batch (batch_type='follow-up', reviewable at gate@1) that walks 1→2→3→4→5→6→7 normally. A
  **compose step** (kept separate from gate@7 approval — Ian: gate@7 stays pure review) sweeps all
  approved NEW-work directives into ONE batch (union of districts + unsatisfied bands; a band-less 7→3/7→1
  expands to the district's claimed bands), honoring the **12-district hard cap** (overflow spills to the
  next compose), then flips the swept directives to `executed` with the batch_id as their `executed_ref`
  (lineage + idempotency). `build_followup_batch` is TARGETED (not stratified) and deliberately
  re-includes already-attempted districts; **`build_batch` (first-run) is untouched.**

**Guards (the must-haves, built):** the **REQ-051 budget governor** (`common/budget.py` +
`common/config/budget.json`) bounds OpenRouter spend/effort on **four caps** — three money axes plus a
depth guard: **per-run** (halts the run), **per-district per-run** (skips the district in this handoff),
**per-district TOTAL** (cumulative across ALL handoffs — the real request-loop guard: a hard district that
keeps failing + re-requesting can't run up unbounded spend over many follow-up rounds, since each round is
a fresh handoff), and **`max_request_rounds`** (the non-spend depth guard, below). The three money caps are
enforced pre-district in `run_council_streaming`, seeded from durable `SUM(extraction.cost_usd)` (per-run
scoped to the handoff, total across all of the district's handoffs) so resume stays under the same
ceilings. Its
`max_request_rounds` is the **per-district×band depth guard** (derived from executed-directive history) so
the cyclic loop provably terminates. The paid 7→6 re-extraction is budget-gated when its new handoff is run.

**Surfaces:** CLI `python3 -m infrastructure.acquisition.process_governance.stage7_execute
{compose-followup|execute <request_id>}` (CLI-first per the ramp-up model) + the server endpoints
`POST /api/extract/compose-followup` and `POST /api/extract/execute/{request_id}`. Console buttons on
`stage7.js` are deferred (the review console renders the directives; execution is CLI/API today). (tracked: #99)

- **Still open — not built:** the console execute buttons; the narrow model "referenced-but-unread"
  detector signal (deferred per the measured-pass discipline); a live non-benchmark end-to-end run.
- **Open research question, unresolved:** the OpenRouter session/context question — can an API session
  stay open across a request round-trip, or must every re-entry re-pass frozen context (the immutable
  dispatch) into a fresh call? See `STAGE6_DISPATCH_DESIGN` §3F. (Today the re-entry re-passes the frozen
  dispatch — a fresh call — which is correct regardless of the answer; a persisted session would only be
  an optimization.)

---

## 5. References
- `STAGE6_DISPATCH_DESIGN_2026-06.md` §0a (the handoff shape), §3F (the loop as first sketched from the
  Stage 6 side).
- `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §11 (gates/console), §11b (the ramp-up model), §11d
  (follow-up batches route through Stage 1).
- `models-and-council-composition/LLM_COUNCIL_RESEARCH_2026-06.md`,
  `models-and-council-composition/models-and-council-composition.md` (the batch_00000 report),
  `EXTRACTION_BENCHMARK_FINDINGS.md`.
- REQ-054 (read-times invariant), REQ-055 (gross metric), REQ-056 (cross-family consensus), REQ-051
  (budget governor), REQ-117 (this build).
- **Council Lab** (the producer that tunes the councils/prompts/cost the request loop routes on): design in
  `COUNCIL_LAB_DESIGN_2026-06.md`; GitHub #80 (infra), #81 (spray A/B), #82 (image-council vision judge —
  fixed), #85 (camelot reader-routing).

---

## 6. Provenance / decision log

**2026-07-02/03 — the full Stage 7 build (REQ-117).** Built in vertical slices against real
`batch_00000` data: plumbing → council run → persistence → GT scoring → durability/resume →
image-vs-text comparison → the request-detection engine → gate@7 console. Key decisions along the way:

- **Model-family map unified.** `aggregate.py`'s short-name family map and `councils.py`'s full-id map
  were two independent tables; for a full OpenRouter id, the short-name map silently treated every id as
  its own unique "family," defeating cross-family false-consensus protection. Fixed by hoisting a single
  canonical `common/model_families.py`, keyed on full OpenRouter ids (Ian: "I'm inclined to use full
  OpenRouter ids"), both callers now import from it.
- **Durability over end-of-batch collection.** The first cut of the batch runner persisted only after
  the entire batch completed. Ian challenged this directly during a long-running batch showing no
  incremental output: "Is there some benefit to collecting everything at the end that I'm not seeing?"
  No benefit was found; the running job was killed and `run_council_streaming` was built — one district
  at a time, persisted immediately, resumable by querying already-extracted districts for the handoff
  hash. Per-rep/per-district progress lines were added on request ("If we hit a snag, we'll at least be
  able to know when it happened").
- **OpenRouter SSE streaming + telemetry**, added after a live audit against the official docs
  (`openrouter.ai/docs/api/reference/overview`, `/streaming`) found three gaps: no `stream: true` (now
  fixed), `max_tokens=2000` risking silent truncation on large documents (raised to 16000, `finish_reason`
  captured as a tripwire), and no `generation_id` capture (added, incl. on error paths, for
  `/api/v1/generation` audit correlation).
- **Image variant hash collision.** `image_handoff_variant()` originally reused the source text
  handoff's hash, so the streaming runner's resume logic would see the text run's persisted districts
  and skip the entire image pass. Fixed by suffixing the hash with the council id (`-image`).
- **Prompt-leak guard.** Fivay High's extraction included the prompt's own example school name as a
  fabricated row. Fixed with `_is_prompt_leak()` in `parse.py`, applied in both the clean-parse and
  salvage paths.
- **Request-loop shape decided (Ian, 2026-07-02/03):** routing must be deterministic scripts, not model
  calls ("the more we can rely on scripts, the better... more auditable and reduces token consumption");
  three altitudes (district/URL/representation) map onto the pipeline's own hierarchy; the request loop
  is **council-initiated**, not human-initiated — human review at gate@7 is a ramp-up-model supervision
  layer on top of a script-originated request, not the request's source (Ian, confirming this
  interpretation explicitly). Deterministic-first was approved over adding a model "referenced-but-unread"
  signal up front, per the measured-pass discipline.
- **gate@7 console UI scope, decided by Ian:** organize the left pane by district with requests nested
  under their district (not a flat request queue) — "that will be a better UI organization for me when
  I'm reviewing"; fact/band editing is explicitly Stage 8's job, not gate@7's ("Fact/band review is
  Stage 8: Aggregation").
- **DeepSeek V3.2 assumed vision-capable for the image council's judge — incorrect.** Every image judge
  call 404s (0/33 resolved in the full run); Ian: "Whoops! Incorrect assumption on my part." Filed as
  GitHub #82; the image-council accuracy numbers in §0 stood despite this at the time (the judge simply
  never resolved a disagreement, leaving those cases at 2-voter agreement or unresolved). **Fixed
  2026-07-04** — see the entry below.
- **Request execution built (REQ-118, 2026-07-03), two mechanisms not four.** Ian's framing collapsed
  the design: "Any requests that go to stages 2, 3, or 4 will probably need to be wrapped in a batch using
  Stage 1." That resolved the §3F-vs-governance-§11d tension — only 7→6 (existing, already-labeled reps)
  is a true direct back-edge; 7→2/7→3/7→1 all converge on a Stage-1 follow-up batch (new evidence must
  pass gate@5). Ian's four build decisions: build BOTH mechanisms + all four routes; **collect** approved
  NEW-work directives into ONE follow-up batch (12-cap, spillover); keep gate@7 approval **pure review**
  with a **separate compose step**; build **REQ-051 first** as a hard prerequisite. Ian also confirmed the
  Stage-5 question directly ("all of the alternate representations are already available in Stage 6… am I
  understanding correctly?" — yes: the label is on the record, so alternates inherit it). Built additively:
  `common/budget.py` + `budget.json` knob (REQ-051), `stage1_queue.build_followup_batch` (targeted;
  `build_batch` untouched), `process_governance/stage7_execute.py` (the app-layer executor), two
  `extraction_request` lineage columns via the sanctioned `_PRECIOUS_ALTERS` additive migration, server
  endpoints + a CLI. Full suite + govdb green; first-run flow proven intact.
- **GT quality questions surfaced, not yet resolved:** New Haven Unified High and West Ada/Joint SD2
  showed extraction misses that on inspection look like they may trace to GT-derivation issues (New Haven
  Unified's GT high band appears to cover only the continuation school, not the comprehensive HS; West
  Ada's derived band average may include human-rejected schools) rather than extraction defects — flagged
  for Ian to revisit the ground truth for these two districts; not a Stage 7 code change.
- **2026-07-04 code-review hardening (13 findings, all folded into the request-execution build).** A
  multi-angle review of the REQ-118 branch found the new execution path had re-implemented several
  invariants instead of inheriting them from code that already enforced them — the unifying lesson,
  captured as its own epic (GitHub #133) for future reviews. Fixes, all in the single merge:
  - **#134 — the benchmark wall wasn't enforced in execution.** `batch_00000` districts could be swept
    into a `follow-up` batch and escape the "never Stage-9-written" wall. Fixed: `_benchmark_district_ids`
    excludes them in both `compose_followup_batch` and `execute_alternate_dispatch`.
  - **#135 — `executed` wasn't a terminal status.** The review endpoint allowed re-opening an executed
    directive, which would silently decrement the depth-guard's round count. Fixed: the API now guards
    `WHERE status != 'executed'` and returns 409 on a reopen attempt.
  - **#136 — a partially-built follow-up batch flipped ALL swept directives to executed**, including
    districts the batch builder actually skipped (no coverage that year). Fixed: only directives whose
    district made it into the built batch are flipped.
  - **#137 — gate@7 pending-request visibility was pinned to the latest extraction's `handoff_hash`**,
    hiding older pending directives once any newer handoff's extraction landed for a district. Fixed:
    visibility is district-scoped, not handoff-scoped.
  - **#138 — a frozen handoff embeds its council config**, so a pre-fix handoff could still route to the
    dead DeepSeek judge on resume/re-run even after #82 was fixed. Fixed: `_check_image_councils` in
    `stage7_run.py` refuses a frozen handoff whose image reps route to a non-vision-capable model.
  - **#139 — the follow-up-batch compose wasn't atomic** (batch rows + directive flip were separate
    commits). Fixed: one transaction.
  - **#140 — the 7→6 alternate-rep picker could select a binary/PDF rep** for an image council. Fixed: a
    defensive kind filter.
  - **#143 — `district_status.json`'s export ran inside the same transaction as the dispatch record**,
    so an export failure (e.g. a missing `current_state` view, hit in CI) would roll back an otherwise
    successful dispatch. Fixed: the export runs post-commit, on a separate session — the exact
    "best-effort side effect must never share the load-bearing transaction" lesson the review itself named.
  - **#144 — the prompt-leak guard blacklisted `"fivay high"`**, a real Pasco County FL school, forever
    dropping its real extractions. Fixed: removed from the blacklist — only bracketed placeholders
    (`"[school name]"`) remain, now that the prompt itself no longer echoes a real name.
  - **#145 — only the first sent file per `rec_key` was tracked**, so a second sent-but-barren rep could
    be offered back to itself as its own "alternate." Fixed: all sent files per `rec_key` are tracked.
  - **#147 — route strings were re-spelled as literals** instead of importing the canonical constants
    from `requests.py`. Fixed. **#148 — the executed-rounds depth-guard query scanned the full table**
    instead of scoping to districts under consideration. Fixed.
  - Full detail + regression tests for each: PR merging commit `b8eec03` (main); the `#143` transaction
    fix landed as a same-day follow-up (`27dc8a7`/`c4e1ac1`) after CI caught it live.
- **Qwen-VL image-judge swap measured + #82 closed (2026-07-04).** The Council Lab's judge-replay harness
  (`council_lab.py`) replayed the new `qwen/qwen3-vl-235b-a22b-instruct` judge over the same 33 escalated
  reps DeepSeek V3.2 had 404'd on: **32/33 calls succeeded**, resolving **21/145** prior disagreements and
  improving image-council accuracy to **89.1% band / 98.2% school** (from 88.5%/98.1%) without regressing
  it. Two follow-on reads, both already tracked: resolution concentrates on small disagreements — dense
  hub-table pages still mostly unresolved (#85, #121) — and the image council still trails the text
  council on native-digital reps, reinforcing the route-by-modality experiment (#132). Full scorecard:
  `COUNCIL_LAB_DESIGN_2026-06.md` §0; persisted record at
  `data/acquisition/council_lab/judge_replay_a2bc80c004ca-image_partial.json`.
