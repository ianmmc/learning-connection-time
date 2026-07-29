# Stage 7 — Extract: present state & decision log (REQ-117)

> **Authority:** what the code does today — the OpenRouter council client, per-rep council →
> cross-family consensus → judge, per-school persistence, GT scoring, the deterministic
> request-more-evidence **detection/routing** engine, and the gate@7 console. §0 maps the code (the
> ground truth); §1–§4 hold the design rationale, with items still genuinely open flagged inline.
> **Audience:** anyone building on or debugging Stage 7; anyone tracing extraction/consensus/the
> request loop.
> **Companions:** `ACQUISITION_PIPELINE.md` §7 (the slim map), `PIPELINE_GOVERNANCE_AND_STATE.md`
> §11 (gates/console; §11b the ramp-up model), `models-and-council-composition/LLM_COUNCIL_RESEARCH_2026-06.md`
> (council research), `models-and-council-composition/models-and-council-composition.md` (the
> batch_00000 full-run report), `EXTRACTION_BENCHMARK_FINDINGS.md` (model leaderboard + costs).
> Upstream: `STAGE6_DISPATCH_DESIGN.md` §0a (the exact handoff shape Stage 7 consumes).
> **Update this when:** Stage 7's code behavior changes. Design turns and superseded approaches
> belong in §6 (Provenance / decision log), not here.

**Status: BUILT through gate@7 review + request EXECUTION + console maturation (epic #163) + extraction
quality (epic #119, CLOSED 2026-07-15).** Council extraction, per-school persistence, GT scoring, the
request-more-evidence **detection → routing → review → execution** loop, and the gate@7 console are all
built. **Epic #119 added** (PRs #508–#511): a `json.JSONDecoder().raw_decode` salvage rewrite that no
longer truncates on braces-in-strings (#508/#276) + a non-list `schedules` guard (#362); the gate@7
**cross-LEA contamination banner** rendering the #237 single-school-LEA flag (#509/#246, REQ-152); and
**mode-stability early-exit** — Stage 7 stops paying for council calls on a district once every fillable
band's running mode is stable (#510/#120, REQ-151; `Extraction.n_reps_skipped`). The extraction **schema is
now v4**, not the v1 four-field shape (§0/§1 below): the council also returns `evidence_quote`,
`source_locus`, **`stated_minutes`/`stated_minutes_quote` (path 2 — an explicitly-published daily-minutes
number)**, `school_year` (#254), `applies_to` (#253), and `campus_names` (#499). Eight prompt ids are
registered (four text + four vision), production runs **v4**. Request **execution** fires the target stage's
back-edge (REQ-118): **7→6 bundles a district's approved alternate-rep re-dispatches into ONE round**
(#153) and picks the **yield-ranked** alternate, not image-first (#155); **7→2/7→3/7→1** collect into a
Stage-1 follow-up batch that now **shapes** its own discovery (untried-schools-first, else a widened SERP
query set — #160/#162 — plus dormant 7→3 seed-URL plumbing, #161) and **auto-flows** through gate@1 +
Stages 2→3→4 to gate@5 (#157); a 7→2 **defers** live while the district's 7→6s are un-executed (#159).
The console now drives the whole loop: a "Run extraction" trigger on a dispatched handoff (#152), gate@7
request cards with **lineage** (where an executed directive went + its live state) and **blocked/deferred**
badges (#154), and an in-Stage-7 **preview modal** before composing (#154). All gated by the REQ-051
budget governor + a per-district round depth guard (rounds, not rows — the #153 fix).

**Live-exercised across TWO full shakedowns.** The epic #163 build shakedown ran real (non-benchmark)
districts — Marion, Pittsylvania, Las Cruces — through much of this loop repeatedly while building it,
surfacing and fixing real bugs (the #158 release cluster-drop, the image-first picker, the row-vs-round
depth guard, a live defer-deadlock); **issue #122 (the first clean end-to-end pass) closed 2026-07-06**
(23 fresh districts, 37 runs, $0.195, both back-edges proven — full report:
`docs/technical-notes/learning-loop-reports/2026-07-06T0458Z-stage7-loop-report.md`).

**A SECOND live shakedown ran 2026-07-11** (batch_00013, 12 districts) to re-validate the loop against
the epic #200/#209-hardened pipeline. It surfaced two real request-loop regressions, both fixed
on this pass:
- **#232 — gate@7's view/rollup read latest-extraction-only**, so a scoped `7→6` retry made an earlier
  run's solid facts (Brownsville: 7 accepted) disappear from the console (read as 0). Facts were never
  lost, only the read was wrong. Fixed: `aggregate.merge_fact_runs` — a pure, deterministic per-`(band,
  school)` merge across ALL production runs (accepted beats unresolved in either run order; among
  duplicate accepteds the EARLIEST wins — fill gaps, never silently overwrite; among unresolved-only the
  latest diagnostic wins). Codified as **REQ-122** (*follow-up rounds fill gaps, never regress solid
  signal*) — see §0 below.
- **#231 — the `7→6` alternate list shown at DETECTION excluded only the current dispatch's sent reps**,
  not the record's whole round history, so a NEW pending request's displayed top alternate could name a
  rep already tried and failed in an earlier round (live: Union Hill's new request re-named round-1's
  `tesseract_raster.txt`; Brownsville's re-named round-1's `page.txt`). This was a detection/display bug,
  not an execution one — `stage7_execute._sent_files_by_rec` already unions every prior round's
  `sent_file` at EXECUTION time (a pre-existing "F4" protection, §0), so approving and firing the stale
  display would still have picked a genuinely-untried rep live; the defect was that gate@7's own review
  surface showed the human a misleading "next step." Fixed on BOTH sides for full detect/execute
  consistency: `stage7_run._district_request_inputs` now unions every prior `7→6`/`7→3` request's
  `sent_file`/`sent_files` into the DETECTION-time exclusion set (the record's own request lineage IS its
  dispatch history); the detector now records `sent_files` — ALL files of a multi-rep send, not just the
  first-seen — on every emitted request; and `stage7_execute._sent_files_by_rec` now also reads
  `sent_files`, closing the one real gap that survived from before: a dispatch sending TWO reps of one
  record left the second, un-named rep re-offerable at EXECUTE time too (the legacy single `sent_file`
  field couldn't record it).

**#231/#232 merged 2026-07-11** (PR #221, alongside epic #200). Tracing the shakedown's own follow-up
batches then surfaced two MORE regressions (**#234**, **#235**) and resolved the **#230**/**#233** open
findings above — all four fixed together in **PR #240** (merged 2026-07-12; REQ-123 codifies #233's
auto-withdraw rule). See the decision-log entry below for the full mechanism.

**Epic #617 (2026-07-26/27) touched three Stage-7 mechanisms — none of them the extraction loop
itself, all of them the benchmark/provenance plumbing around it.** `Extraction.run_kind` is now
**THREE-valued** — `production` | `probe` | `benchmark` — not the two-valued `{production, probe}`
described below and in §0/§6; `benchmark` (#662) marks a run against a benchmark-type dispatch (stamped
going forward by `persist_run_session`; 30 historical harness runs across `batch_00000`'s 27 districts
were migrated by a one-time script, `maintenance/reclassify_benchmark_extractions.py`) and is a
DIFFERENT axis from `probe` (a council-variant measurement, e.g. the `-image` vision compare) — the two
must never be conflated, since every `run_kind`-scoped reader (gate@7's console filters here, gate@8's
queue, the Stage-9 wall) would otherwise miscount. Second: the **mode-stability early-exit's**
benchmark exemption (REQ-151, `stage7_run.py`) moved from asking "is this district EVER a
`batch_type='benchmark'` member" (permanent, district-grain — #619's bug in a different guard) to
`dispatch_type != 'benchmark'` read off the frozen handoff — a run-level property, extracted into
`_early_exit_enabled` so a test pins the live predicate rather than a copy of it. Third: the **7→6
back-edge freeze paths** (`stage7_execute._bundle_alternate` and `_dispatch_recover_band`) were found
to bypass `assert_dispatch_type_allowed` entirely — `HND.freeze()` called directly, defaulting to
`dispatch_type='production'` — meaning a `7→6` naming a `batch_00000` district's injected `gt://` rep
by `rec_key` could mint a *production* dispatch holding benchmark-provenance evidence (#618's refusal
exists to prevent exactly this, and it had never fired only because the now-retired district-membership
wall kept benchmark districts out of these paths first). **Fixed same day (#644):** both sites now call
the guard through a `_refuse_benchmark_reps` adapter, and a fitness test walks the AST of every function
containing `HND.freeze` to assert the guard precedes it. None of this changed council extraction,
consensus, or the request-detection engine — it is entirely about which dispatches/runs may exist, not
what they contain. Full account: `docs/technical-notes/learning-loop-reports/2026-07-25-epic617-benchmark-model-findings.md`
§10.9–§10.20, §12.5.

**A real, OPEN correctness bug in the request-history union (#333, `sev:major`, re-verified
2026-07-28):** `stage7_run.py:887` — `hist = p.get("sent_files") or ([p["sent_file"]] if
p.get("sent_file") else [])` — treats an explicitly-empty `sent_files: []` (meaning "nothing sent this
round") as falsy and falls back to the legacy singular `sent_file`, which can resurrect a stale
filename into a request's sent-history and cause the composer to skip a rep it should retry — the
exact #122/#231 recall-loss class this code exists to prevent. **`stage7_execute.py`'s equivalent
site (`_sent_files_by_rec`, ~line 815) already unions correctly** (`files = set(p.get("sent_files") or
[]); if p.get("sent_file"): files.add(...)`) — only the detection-side read in `stage7_run.py` still
has the falsy-empty-list defect. Not yet fixed; fold into the next Stage-7 touch.

**batch_00013's 7→2 follow-up journey ran to completion.** The four-district follow-up (Union Hill ISD,
Brownsville Ascend, Redbank Valley, Aspen Ridge) that this second shakedown spawned went through Stage 7
round 3 and concluded **still barren on model disagreement, not missing data** — i.e. the loop terminated
correctly rather than looping forever or masking a real gap as resolved. The open thread from here is
aggregation-quality, not request-loop mechanics: a same-physical-school double-count under name variants
(**#236**, open) and NCES's school-count column overriding a multi-campus charter network's real topology
(**#237**, open) — both tracked as Stage 5/7 aggregation-quality issues, separate from the request-loop
regressions this shakedown was built to exercise. **Issue #122 itself (the first clean end-to-end pass)
closed 2026-07-06**, on the FIRST shakedown described above; this second shakedown was a re-validation
exercise against the #200/#209-hardened pipeline, not a distinct issue awaiting its own closure.

---

## 0. As-built (code is ground truth) — REQ-117

**Package:** `stage7_extract/` (independent stage, common-only imports, import-linter enforced):
- `openrouter.py` — the paid OpenRouter chat client. SSE-streaming (`stream: true`), accumulates
  deltas, reads `usage` (tokens/cost) off the final chunk, captures `finish_reason` (a `length` value
  is the truncation tripwire) and `generation_id` (for `/api/v1/generation` audit correlation) on every
  path including errors. `DEFAULT_MAX_TOKENS = 16000` (the floor — every roster seen fits it; a small
  rep, ~86% of traffic, is never sized below it). `MAX_TOKENS_CEILING = 32000` — one constant shared by
  two mechanisms so they can never disagree (#187): `size_max_tokens(n_times)` (#180) pre-sizes a call's
  `max_tokens` from the rep's clock-time count (schools ≈ n_times/2, output ≈ schools × 47 tokens —
  `EXTRACTION_TOKEN_SIZING_2026-07-06.md`, 840 real calls) and clamps UP to the ceiling, so a big roster
  is sized right on the FIRST call (no truncate-then-retry double prompt-charge); a truncated reply
  (`finish_reason == "length"`) below the ceiling is retried ONCE at the ceiling to recover the dropped
  tail (#169) — a call already sent AT the ceiling that still truncates gets no retry (nowhere higher to
  go, >680 schools, never observed in 840 calls), and the ⚠ flag persists. The retry's cost/tokens/
  latency are SUMMED onto the returned `CallResult` (both attempts were real billed calls, #182), so the
  REQ-051 budget governor sees true spend. `_client()` (the OpenAI SDK client) is `functools.lru_cache`d
  per `(key, timeout)` (#148) so consecutive calls in a batch reuse one httpx connection pool instead of
  a fresh TLS handshake each call (was ~30-60s/batch of pure handshake); an autouse conftest fixture
  clears the cache per test. Raises `BillingAuthError` on 401/402 (halts the run rather than burning
  further calls on a dead key).
- `parse.py` — tolerant JSON parser: markdown-fence stripping, **salvage-on-truncation via
  `json.JSONDecoder().raw_decode`** (#508/#276 — the real tokenizer scans from each `{`, so braces inside
  string values (school names/notes) and nested objects no longer truncate the salvage; the old `[^{}]*`
  regex silently dropped valid schedules on the very path meant to rescue them; `_salvage` at `parse.py:74`,
  `_sched_items` at `:59` also harvests a `{"schedules":[…]}` wrapper stranded in prose), a **non-list
  `schedules` guard** (#362 — a valid reply with `schedules: null`/scalar/dict returns `[]`, not a
  TypeError; `parse.py:113`), a v4 `_scrub_campus_names` (#499), and a
  prompt-example-leak guard (`_is_prompt_leak`) that drops any row whose `school_name` matches a
  **self-evident bracketed placeholder** (e.g. `"[school name]"`) in both the clean-parse and
  salvage paths. `"fivay high"` was REMOVED from this set (#144) — it is a real Pasco County FL
  school, and blacklisting it permanently blinded extraction to it; the prompt itself no longer
  contains the string (replaced with `[SCHOOL NAME]`), so that specific leak cannot recur. Never
  add a real school name here — fix the prompt instead.
- `content.py` — `image_data_url()` (base64 data-URL; `.webp`→PNG conversion exists but the picker never
  selects `.webp` — PNG-only, per Ian) and `is_image_kind()`.
- `requests.py` — the request-more-evidence **detection/routing engine** (§4): pure, no DB/network,
  fully unit-testable (confirmed import-pure by grimp during epic #163 — no `infrastructure.*` imports).
  `rank_alternates()` orders a 7→6's alternate reps best-first (#155): higher-yield TEXT (by `n_times`,
  descending) → IMAGE (the vision escalation, tried only once text is exhausted) → zero-yield text last;
  `_alt_reason()` names the actual top pick honestly ("higher-yield TEXT…" vs "escalate to VISION…", never
  a blanket "try another modality"). `detect_requests()` takes an optional `covered_bands` (district-wide
  accepted bands across ALL prior extractions, not just this result) so a **partial** result — e.g. a
  1-record 7→6 re-dispatch — can't fabricate a band gap for bands already covered elsewhere. A district
  band-gap 7→2 carries `params.pending_alt_reps` + a **DEFER** reason when the district has barren records
  with an unexhausted 7→6 remedy (#159) — deliberately a **district-level** signal, not per-band
  attribution (the motivating case, an emergent record, has no `intended_schools` to attribute a band from).
  `detect_requests()` also takes an optional `real_bands` (the bands SERVED by ≥1 real NCES school, via
  the shared `common/school_sampling.real_bands_for_district` — the SAME logic Stage 1 uses to assign a
  school's band) that gates the loop against **coverage-blind spend** (#176, measured: ~57% of follow-up
  spend on the #122 run added zero new coverage): a claimed band absent from `real_bands` is a **phantom**
  (no school serves those grades) and never emits a 7→2 (#175); once every FILLABLE target band
  (claimed ∩ real) already has facts — or none is fillable at all — a barren-rep 7→6/7→3 can add no net-new
  coverage either, so it is **suppressed** too (#170/#176). `real_bands=None` disables the gate (back-compat)
  and a phantom claimed band never blocks the "fully covered" check. `stage7_execute.plan_followup` re-runs
  the identical gate **live** at compose time (defense-in-depth, since coverage can change between detect
  and compose) via the shared `_fillable_gap` predicate, suppressing into a new `suppressed` bucket
  surfaced in the #154 compose modal.
- `validate.py` — the GT-scoring harness: `load_gt()`, `score_district()` (per-band hit/miss/gap/extra +
  per-school hit/miss via the shared `common.school_match.norm_school`), `score_run()` (aggregate).
  **`norm_school` itself was rewritten (PR #247, 2026-07-12)**: district-type qualifiers
  (unified/consolidated/independent/community/county) now strip only in a trailing run ending in a hard
  marker (district/ISD/USD/…/SD) — never bare or mid-name — so "Meridian Consolidated School" and
  "Meridian School" score as DIFFERENT schools where the old anywhere-strip wrongly merged them, while
  "Union Hill ISD" still merges with "Union Hill" as intended. Also fixed: hyphenated suffixes word-split
  before stripping, ES/MS/HS join the level-word stopwords, and unicode NFKD transliteration — all closing
  false-positive/false-negative GT-matching gaps. The function is now idempotent (a fixed-point strip loop),
  which matters beyond Stage 7: Stage 8's `merge_fact_runs` and `detect_single_school_over_extraction`
  re-normalize PERSISTED `school_fact.school` keys through the current function at read time to self-heal
  against exactly this kind of stopword-list version drift (`STAGE8_AGGREGATE_DESIGN.md`).
  `stage5_filter/build_signals.py`'s own separate, weaker duplicate of `norm_school` was deleted in the same
  PR — Stage 5's topology denominator now shares the identical function with Stage 7/8, closing a
  three-stage drift risk the module's own docstring had warned about ("They MUST use the SAME function or
  matching silently drifts — hence one home in `common`").
- `models.py` — SQLAlchemy models on the governance DB (`gdb.Base`), all **precious** (append-only,
  human-reviewed, never touched by Stage-5's drop+rebuild ingest): `Extraction` (rollup + telemetry per
  run — incl. `run_kind` ∈ {production, probe, benchmark}, first-class since #148/4D, third value added
  by #662 (see the epic #617 note above); see below), `SchoolFact`
  (per-school accepted/unresolved facts), `ExtractionRequest` (the request-more-evidence
  directives — `altitude`, `route`, `target`, `band`, `params_json`, `reason`,
  `status` ∈ {pending, approved, rejected, executed, withdrawn}, `reviewed_by`/`reviewed_at`/`review_note`).
  `withdrawn` (#233/REQ-123) is machine-set by `withdraw_satisfied_requests` when the cumulative
  production state already satisfies an open directive's premise — see below — and renders as its own
  badge at gate@7 (`stage7.js`).

**App-layer glue:** `process_governance/stage7_run.py` (mirrors `stage6_dispatch.py`):
- `run_council_streaming()` — the production entry point. Processes **one district at a time**,
  persists immediately per-district (not batched at the end), so a crash mid-run loses at most one
  district's work. **Resumable** (`resume=True`, the default): re-running a handoff skips districts
  already present in `extraction` for that `handoff_hash` (`_already_extracted`). Prints per-rep and
  per-district progress lines as it runs — a snag is visible at the district/rep where it happened, not
  only at the end. **Per-district failure isolation (#173):** a per-district failure (a malformed rep
  group, an aggregation bug) is caught, recorded into `results["failed"]`, and the batch CONTINUES to the
  next district — the original #122 symptom (one `FileNotFoundError` reading Marshall's harvest_slice
  stranded districts 16→18) is fixed. `BillingAuthError`/`SystemExit`/`KeyboardInterrupt` (the
  `HALTING_EXCEPTIONS` tuple) still propagate and halt the run — every later paid call would fail
  identically, so these must never degrade to a per-district skip. The background job (`server.py`)
  surfaces a partial run as `state:'partial'` (`n_failed` + `failed[]`), not a silent success.
  Seeds the REQ-051 budget governor's three money ceilings from ONE spend-definition query
  (`_spend_by_district`, #147) so per-run/per-district/per-district-total can never disagree on what
  "spend" means. Stamps each run's `run_kind` (`doc.get("run_kind") or "production"`) onto every
  district's `Extraction` row via `persist_run_session` — request-detection (`detect_and_persist_requests`)
  runs only for `run_kind == "production"`, so a probe's directives never surface as reviewable
  production work.
- `_run_district()` — the shared per-district council-run core: 2 voters → `AGG.consensus_school_facts`
  (cross-family, per-school (start,end) pair, ±15 min, REQ-056) → judge fires only on disagreement →
  `AGG.district_bands_from_facts` (the per-band exact mode, REQ-055 gross bell-to-bell). **Per-rep
  isolation (#173):** an unreadable/unprocessable rep (e.g. a relocated harvest_slice) becomes a recorded
  failed rep (no calls, the error captured, counted in `telemetry.rep_errors`) while the district's OTHER
  reps still extract — this is where the #122 Marshall failure actually originated, one altitude below the
  district-level guard above. Post-loop band aggregation is guarded too (#183): an aggregation bug keeps
  the already-billed reps and marks the district errored with empty bands, rather than discarding billed
  work. Reuses Stage 6's
  request assembly and Stage 8's consensus/mode code — Stage 7 does not re-derive either.
  Model-family membership is read from the single canonical `common/model_families.py` (keyed on full
  OpenRouter ids), also used by Stage 8 — see the decision log (§6) for the bug this fixed.
- `image_handoff_variant()` — rewrites a text handoff to route PNG reps to the vision council for a
  text-vs-vision compare; `_pick_png()` prefers `raster_p-1.png`, else any `.png`, never `.webp`/`.jpg`.
  Gives the image variant a **distinct `handoff_hash`** (`<base>-<council_id>`, e.g. `-image`) so its
  resume logic can't collide with the source text handoff's already-persisted districts (§6). Also stamps
  `run_kind = "probe"` on the variant doc (#148/4D) — a **first-class column** on `Extraction`
  (`run_kind` ∈ {production, probe, benchmark} since #662 — `probe` means a council-VARIANT
  measurement like this one, `benchmark` means a run against a benchmark dispatch, never conflated;
  `models.py`), not a string match on the hash suffix. The earlier
  design relied on the console filtering `handoff_hash NOT LIKE '%-image'`, which only ever caught the
  literal `image` council id; a second vision council (e.g. `council_id="vision2"` → hash `…-vision2`)
  would sail past that filter and shadow the district's real production run in the gate@7 review pane —
  a real bug, not a hypothetical (the existing custom-council-id test already produced exactly such a
  suffix). Fixed: the hash suffix now serves ONLY resume-isolation + lineage; `run_kind` is the sole
  console-visibility discriminator, threaded `doc → run_council_streaming → persist_run_session` and
  checked by both gate@7 console queries (`WHERE run_kind = 'production'`). An additive migration
  (`common/db.py`'s `_PRECIOUS_ALTERS`) adds the column NOT NULL / `server_default='production'` and
  backfills existing `-image` rows to `run_kind='probe'`, guarded and idempotent.
- `detect_and_persist_requests()` — runs `requests.detect_requests()` against a just-persisted district
  result and writes `ExtractionRequest` rows. Dedup is two-layered (#234, PR #240): same-handoff ANY
  status (idempotent re-detect/backfill — an already-reviewed request keeps its human status rather than
  resetting to pending) OR any-handoff while still OPEN (`pending`/`approved`) — a still-open ask is the
  SAME logical ask, so a fresh round triggered by executing a sibling request can't duplicate it (the
  live symptom: 0602559's `high`-band `7→2` pending twice, 4220130's across four handoffs). An executed/
  rejected/withdrawn prior round does NOT block re-emission — depth-guarding rounds is `budget.py`'s job,
  never dedup's. The check-then-insert has no DB unique constraint behind it (impractical given the
  conditional identity + NULL band, and the live table already held pre-fix duplicates); a
  `pg_advisory_xact_lock` per district serializes concurrent writers instead, and a composite index
  (`district_id, target, altitude, route`) keeps the natural-key lookup fast now that it can no longer be
  served by a tight handoff-scoped scan. `backfill_requests()` does the same from receipts already on
  disk, without re-extracting (for retrofitting requests onto a run persisted before the detector
  existed) — and now also runs the withdraw pass below for every district it touches.
- `withdraw_satisfied_requests()` — auto-retires OPEN directives whose premise the CUMULATIVE production
  state has already satisfied (#233/REQ-123, PR #240): requests only ever grew per round in the live
  shakedown (Redbank 5→6, Aspen 3→5, Union Hill 4→7 pending) with nothing retiring one a LATER round had
  already fixed. A band-scoped directive withdraws once that band has a cumulative accepted fact; a
  record-scoped one (band `NULL`: `7→6`/`7→3`) withdraws only when no FILLABLE band remains uncovered —
  fillable = claimed ∩ real, the SAME predicate `detect_requests` uses (#175), so the two can never
  disagree; vacuously true (withdraws) when NOTHING is fillable, mirroring detect's own permanent
  suppression of an all-phantom district. A missing `district_target` row means unknown, never satisfied.
  Called in the same transaction right after `detect_and_persist_requests` (production runs only) and
  from `backfill_requests`; a human Reopen re-runs this exact check server-side, so a still-satisfied
  directive re-withdraws immediately with a fresh note instead of silently resurrecting finished work.
  **Deliberately unauthorized by a human** — the one exception to the ramp-up model's manual-until-proven
  posture (governance §11b) — justified by risk asymmetry: not withdrawing risks unbounded, non-
  self-correcting PAID spend (approving/executing an already-satisfied request), while a wrong withdrawal
  only ever leaves a band gap that stays VISIBLE, re-emits next round, and is one Reopen away from
  returning. *Auto-act in the spend-conservative direction when the failure mode is observable and
  reversible* (Ian, 2026-07-11) — see the decision log for the review that found and closed the gap
  between this stated rule and the first draft's actual fillable-band fallback.
- `write_receipt()` / `write_district_receipt()` — per-run and per-district JSON under
  `data/acquisition/extractions/` (regenerable, auditable — never the transport; governance's
  DB-is-the-working-store rule). `write_district_receipt()` also drops a `stage7_extract` per-district
  audit receipt into the capture dir (REQ-164, 2026-07-22 — always-stamped via
  `common/receipts.py::write_receipt`), pointing at this central file + gov_db `school_fact`.
- `main()` CLI: `--mode {plumbing,council,image}`, `--persist`, `--validate --gt <path>`, `--no-resume`,
  `--no-judge`, `--limit`.

**Execution layer:** `process_governance/stage7_execute.py` (REQ-118, hardened epic #163) — turns
APPROVED directives into real back-edge work. Two mechanisms (§3F):
- **7→6 bundle** (`execute_alternate_dispatch` → `compose_alternate_bundle` → `_bundle_alternate`): fires
  a district's **whole approved 7→6 set as ONE Stage-6 dispatch = one depth-guard round** (#153) — approve
  several, execute once. `pick_alternate()` + `live_alternates()` derive the candidate from the record's
  **live** representation rows (not the request's stored params, so a pre-#155 request still picks
  correctly) and rank yield-first; `_sent_files_by_rec()` unions every already-failed file across ALL of
  the district's 7→6 history (F4; both the `sent_files` list and the legacy single `sent_file`, #231) so
  a round never re-offers a rep that already failed. `_run_bundle_or_own`
  is the inject-or-own idiom + post-commit best-effort `district_status` export (mirrors `dispatch_handoff`'s
  commit-order lesson, #143). **N+1 fix (#148/4C):** `_bundle_alternate` used to load EVERY district
  record (1 query + a rep-query PER record) just to look up the handful named by the approved 7→6s; it now
  calls the new `stage5_filter/release.py:load_records_by_key` — only the requests' `rec_key`s, in 2
  queries total (records + batched reps). `load_district_records` was refactored onto the same shared
  shaper so its rep fetch is batched too.
- **7→2/7→3/7→1 follow-up batch** (`compose_followup_batch` → `plan_followup` (pure) →
  `stage1_queue.build_followup_batch`): collects approved NEW-work into one targeted DRAFT batch. `plan_followup`
  now also **defers** (holds) a district's NEW-work while it has an un-executed 7→6 that could still fire —
  computed from `_defer_76_districts`, which excludes **rounds-exhausted** districts (a district whose 7→6s
  are depth-blocked zombies must not defer forever; #159). `compose_followup_batch(dry_run=True)` runs the
  full gather→plan→build pipeline **read-only** (no `create_batch`, no directive flip) for the console's
  preview modal (#154) — returns `preview` (districts × target bands × `query_strategy` × seed-URL count).
  `_attempted_schools()` feeds the follow-up builder which schools were already tried, **excluding draft
  batches** (an abandoned draft must not poison the untried set — review finding, epic #163).
- **Depth guard is rounds, not rows, everywhere**: `_executed_rounds`/`_executed_rounds_76` count
  `COUNT(DISTINCT executed_ref)` — a bundle flips N directives to one `executed_ref`, so counting rows
  would trip the guard after a single bundled round.

**gate@6/7 console** (`process_governance/server.py` + `static/stage6.js`/`stage7.js`):
- `GET /api/handoffs` — dispatched handoffs, now carrying `n_extracted` + `running` (#152) so Stage 6's
  list shows Run / Resume / **✓ extracted** per handoff (never a "Re-run" that would silently no-op —
  the run is resume-by-default).
- `POST /api/extract/{handoff_hash}/run` + `GET /api/extract/run/{handoff_hash}` (#152) — a background job
  (the issue-#47 thread + job-board pattern) runs `run_council_streaming` for a **dispatched** handoff; the
  gate@6 approval IS the go-ahead, no separate approval gate.
- `GET /api/extract/districts` — attention-sorted (most pending requests first) list; excludes
  `run_kind='probe'` extractions (#148/4D — a first-class column, not a `-image` hash-suffix match; the
  district-first view shows the primary/production extraction). `run_kind='benchmark'` rows (#662) are
  excluded the same way `probe` rows are — neither is a production extraction.
- `GET /api/extract/district/{district_id}` — the LATEST `run_kind='production'` extraction supplies the
  header (cost/handoff/timestamp, per-run telemetry only); accepted/unresolved facts and the band rollup
  are the **CUMULATIVE merge across every production run** (`AGG.merge_fact_runs` → `district_bands_from_facts`,
  REQ-122/#232 — a scoped `7→6` retry's own barren extraction row must never make an earlier run's solid
  facts disappear from the console). Each fact carries its originating `extraction_id`/`handoff_hash` so a
  reviewer can trace which round produced it. The request directives for that district each carry a
  `lineage` object (#154, `_request_lineage` + `_district_loop_ctx`,
  computed once per detail call from the SAME live checks compose runs, so the card can never disagree
  with what compose would actually do): an executed 7→6 → its handoff + live extraction state; an executed
  7→2/3/1 → its follow-up batch + auto-flow state; an approved 7→6 with rounds exhausted → `blocked` +
  reason; a 7→2 held behind a live un-executed 7→6 → `deferred` + reason.
- `POST /api/extract/request/{request_id}` — approve/reject/reopen, recording `reviewed_by`/
  `reviewed_at`/`review_note`. `executed` is terminal (#135) — a reopen attempt 409s.
- `POST /api/extract/compose-followup/preview` (#154, dry-run) + `POST /api/extract/compose-followup` —
  the modal previews before it commits.
- `POST /api/extract/execute/{request_id}` — fires the district bundle (see above).
- `GET /api/followup/autoflow/{batch_id}` (#157) — status of a follow-up's gate@1-auto-pass →
  Stage 2→3→4 auto-run, landing at gate@5 (§3F).
- `stage7.js` — district-first left pane (Ian's UI call: "organize by district with requests related to
  them"), attention-sorted with an "N REQ" badge; detail pane shows the band rollup (labeled as
  Stage-8-owned/authoritative — Stage 7's rollup is a preview), request cards with Approve/Reject/Reopen
  **+ lineage/blocked/deferred badges**, accepted-school and unresolved-fact tables, and the **compose
  preview modal** (cancel/ESC/click-outside all dismiss with no side effect). **Fact/band editing is out
  of scope for gate@7** (Ian: "Fact/band review is Stage 8: Aggregation") — gate@7 is read + request
  review/execute + compose-preview, never fact/band edits.

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
  `COUNCIL_LAB_DESIGN.md` §0 for the full scorecard). #82 is closed.
- Full findings (per-model cost profiles, reader-source yield, the 3 real band misses root-caused, the
  spray-fabrication interaction with the request detector) are in
  `models-and-council-composition/models-and-council-composition.md`.
- `batch_type == "benchmark"` output is never counted in Stage 1's funnel/enrichment stats
  (`STAGE1_QUEUE_DESIGN` §2h; `STAGE6_DISPATCH_DESIGN` §3C C.6) — batch-grain, unchanged by #617/#619.
  The separate Stage-9-write question is **not** batch/district-grain any more: since #619 (epic #617,
  2026-07-26) the wall asks about the FACT's own provenance (`handoff.dispatch_type='benchmark'` or the
  fact's rep carrying `capture.source='benchmark_gt'`), not district membership in a benchmark batch —
  see `STAGE9_INCORPORATE_DESIGN.md`.

**The request-more-evidence detection engine, validated on real data:** `requests.py` run over the
batch_00000 text results correctly flagged exactly the **4 genuine coverage gaps** the scorecard showed
(Mat-Su middle, Mesa high, Bangor elementary, Cleveland middle — the K-8 band-split quirk), each routed
`7→2` with the band's known schools, and **7 barren-rep alternate-exists cases** routed `7→6` — with
**zero false positives** across the 20 covered districts.

---

## 1. Purpose & boundary

Stage 7 is the **council extraction**: the assigned OpenRouter model council reads the handed-off
representations and returns per-school facts. The v4 schema (`stage6_handoff/prompts.py`) is
`{start_time, end_time, grade_level, school_name, confidence, evidence_quote, source_locus,
stated_minutes, stated_minutes_quote, school_year, applies_to, campus_names}` — but the **INVARIANT holds
across all of it: models read TIMES (and copy explicitly-stated facts verbatim), deterministic code computes
minutes + the mode; REQ-054.** Note `stated_minutes`/`stated_minutes_quote` are **path 2** — a daily
instructional-minutes number *only if the document states one outright* ("instructional day: 435 minutes"),
never computed from the times (the "golden nugget"/Dunseith case; Stage 5's `lf_explicit_minutes` is its
upstream detector). Persisted in `SchoolFact.evidence_json` (`stage7_extract/models.py:75-78`), aggregated
by `stated_minutes_agree` in `closing_argument.py`. Consensus is the cross-family per-school (start,end)
pair, ±15 min (REQ-056). When evidence is insufficient, the
pipeline **gets more** via the **request-more-evidence loop** — detection + routing are deterministic
scripts, not the model (§4). The gate is **`gate@7`**: review the routed requests + the extraction
results, approve/reject.

## 2. Console — what's built vs. still open

Built (§0): district-first list, band rollup, accepted/unresolved facts, request cards with
approve/reject/reopen/execute, lineage/blocked/deferred visibility, the compose preview modal, a
"Run extraction" trigger on gate@6's dispatch list, and the follow-up auto-flow to gate@5.
**Still open** (deferred, not designed):
- Retrieve the screen-capped PNG / PDF for a given URL and view it inline from the console (currently a
  reviewer would go to disk). (tracked: #151, split from the original #99)
- A narrower recapture/redo-discovery trigger scoped to ONE record/URL directly from the console, as
  distinct from the district-level compose/execute actions already built.

## 3. Escalation & gate posture

- **The judge step is built.** The judge is part of the council config (Stage 6); Stage 7 fires it on a
  voter disagreement (re-reads the same rep, consensus re-run with its rows). REQ-056.
- **Escalation on no-consensus** (cascade to a stronger config vs. flag) is **open** — ties to the
  Stage 6 cross-config cascade lever (`STAGE6_DISPATCH_DESIGN` §3B). Today a no-consensus (band,school)
  is simply held as `unresolved`, surfaced at gate@7, not auto-escalated.
- **`gate@7` is manual today** (review + approve/reject requests; no fact/band editing). It follows the
  ramp-up model: manual now, auto-with-confidence-escalation later, once reliability is proven
  (governance §11b). **Gate taxonomy (Ian, 2026-07-04, governance §11b):** the canonical design was only
  three gates — 1/5/8 (the old CP-A/B/C) — which decide something genuinely *new* each time and are
  permanent. **gate@6 and gate@7 are supervision gates**, added later from API-spend caution during a
  context-clear cycle, not first-principles design; they're the first candidates to relax as reliability
  is proven. This is why a **follow-up** batch (which carries an already-approved gate@7 decision) can
  auto-pass gate@1 and auto-flow Stages 2→3→4 (§3F, #157) while gate@5 (new URLs = data quality, a
  structural gate) and gate@6 (spend, a supervision gate Ian still wants manual) do not auto-advance.
- **gate@7's review decision also feeds the calibration corpus (REQ-121/#210, wired live 2026-07-10).**
  Every terminal approve/reject of a request-more-evidence directive (not a `pending` reopen) calls
  `process_governance.gate_calibration.gate7_request_record`, logging the district's council **agreement
  ratio** (`n_accepted/(n_accepted+n_unresolved)`, read from the run this directive's `handoff_hash`
  actually produced — filtered to `run_kind='production'` so a later probe run's stats can't leak in,
  #218 review) against the human's accept/reject of the directive itself (auto's implicit recommendation is
  "accept" — the deterministic detector proposed the directive in the first place). This is the
  **highest-value** of the three wired calibration hooks per the module's own design note: it directly
  tests whether low council agreement predicts a human overriding the detector. **Not the same thing as
  gate@8:** approving the council's extracted TIMES (`school_fact.human_determination`) is a Stage-8
  activity and is explicitly deferred until Stage 8 exists (#88/#89) — gate@7's calibration hook only
  scores the request-more-evidence directive, never the extracted values themselves. See
  `PIPELINE_GOVERNANCE_AND_STATE.md` §11b for the full calibration-log design.

---

## 4. The request-more-evidence loop

**When the council can't confidently answer, the pipeline gets more evidence via cyclic back-edges
(7→6/3/2/1).** Detection + routing are **built and validated** (§0); **execution is built and hardened**
(REQ-118, §3F, epic #163). The whole loop — detect → rank/defer → gate@7 review (with lineage) → bundled
execute / previewed compose → auto-flow to gate@5 — is code, and has been exercised repeatedly against
real districts during the epic #163 shakedown. The clean end-to-end pass ran (#122, **closed 2026-07-06** —
23 fresh districts, 37 runs, both back-edges proven).

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
| **district** | a claimed band is not DONE — **slot grain since #694 (2026-07-29)**: not SATISFIED (REQ-149) and holding open unfilled slots in the gate@8 projection (read via `requests.slot_gap_summary` — the ONE slot-state home, `slot_spine` via the closing argument); the directive names the specific unfilled schools, human dispositions are live (`reject` excludes a slot, `confirm_extra` fills), span-only schools are bounded to `MODE_CHECK_MAX` #696 assumption-checks, and emission, withdrawal (#233) AND compose's suppression gate (`plan_followup`, #703 review) share the one `band_done` predicate. Slot view unavailable ⇒ the prior boolean (**0 accepted facts** across all URLs) | **7→2** targeted rediscover for that band, or **7→1** a follow-up batch adding specific schools |

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

**(e) Rediscover DEFERS while a cheaper existing-evidence remedy is unexhausted (#159, epic #163).** A
district-altitude 0-facts band doesn't automatically mean "spend on new discovery" — if the district also
has a barren record with an unexhausted 7→6 alternate, `requests.py` tags the 7→2 with
`params.pending_alt_reps` and a DEFER reason (§0). Deliberately a **district-level**, not per-band, signal:
the motivating case (an emergent record, no `intended_schools`) can't be attributed to a band
pre-extraction, and name-matching the ~76% of records that do carry intended schools was considered and
rejected as fragile. `stage7_execute.plan_followup`/`_defer_76_districts` re-check this **live** at
compose time (never the request's stale detect-time params — a live-vs-cached-state bug found + fixed
during epic #163) and exclude districts whose 7→6s are rounds-exhausted, so the defer can't deadlock a
district's rediscovery forever.

**(f) Coverage-aware suppression — the loop stops firing follow-ups that can't add coverage (#176/#170/
#175, batch 3A).** The #122 live-run report measured that **~57% of follow-up spend produced zero new
coverage**: 7→2 rediscovers fired for **phantom** bands (a claimed band with no real school able to serve
it — unfillable by definition) and 7→6 re-dispatches fired on districts that were already **fully
covered** for every real band (the Aspire $0.076 vision-escalation-for-nothing). The loop was
coverage-blind at the point of firing. Fixed with one new shared signal, gated at **both altitudes** and
**both enforcement points** (detect-time + compose-time, defense-in-depth):
- **`real_bands`** — the bands a district can actually satisfy (≥1 real NCES school serving them),
  derived by `common/school_sampling.real_bands_for_district` (by_level's clean levels, rescued per-school
  for an ambiguous `Secondary`/`Other` span) — the SAME logic Stage 1 uses to assign a school's band, so
  the loop's gates can never disagree with how bands were assigned upstream. One shared helper, imported
  by both the detector and the compose planner (DRY, so they can't drift).
- **`requests.detect_requests(..., real_bands=...)`** — a claimed band absent from `real_bands` is a
  phantom; no 7→2 is ever emitted for it (#175). Once every FILLABLE target band (claimed ∩ real) already
  has facts district-wide (or none is fillable at all), a barren-rep 7→6/7→3 is suppressed too — it
  cannot add claimed coverage (#170/#176). `real_bands=None` disables the gate (back-compat: an
  all-unknown district keeps its remedies).
- **`stage7_execute.plan_followup`** re-checks the identical predicate **live** at compose time (the #159
  lesson generalized: never trust the request's stale detect-time state) — a 7→2 whose band was filled by
  another round between approval and compose, or that's now recognized as phantom, is moved into a new
  `suppressed` bucket (auto-rejected with a machine actor + reason, human-reversible at gate@7) rather than
  composed into a wasted batch.
- **Measured before/after (live DB, 88 districts):** 24 districts (27%) carry a phantom claimed band —
  every one `middle` (the K-6/7-12 structural split pattern) — each of which had fired an unfillable 7→2.
  `real_bands ⊆ claimed` held for all 88 districts, confirming the gate is purely subtractive (no real band
  is ever suppressed). The 3 phantom 7→2s already in the DB were all `executed` (the measured waste); none
  were pending/approved, so no request cleanup was needed.
- **Deliberately deferred:** correcting `lea_claimed_bands` at Stage 1 itself (the single-source-of-truth
  fix) — complicated by the over-coverage case (real bands may need to *grow* from extracted evidence, not
  only shrink). The detector/compose gate is the measured, reversible step; a Stage-1 correction can build
  on it later.

### 3F. Request execution — BUILT + HARDENED (REQ-118, epic #163)

An approved directive fires the target stage's back-edge. The architectural collapse (Ian, 2026-07-03):
**anything needing NEW capture/discovery routes through a Stage-1 follow-up batch, so there are only TWO
execution mechanisms, not four** — matching governance §11d ("directions route through Stage 1; only
re-routing EXISTING representations bypasses it"):

- **`7→6` — a district's approved alternate-rep re-dispatches, BUNDLED into ONE round** (#153,
  `stage7_execute.execute_alternate_dispatch` → `compose_alternate_bundle` → `_bundle_alternate`). The
  alternate reps are **already captured, processed, AND labeled** — the gate@5 label attaches to the
  *record*, not an individual rep, so every rep of an already-reviewed record inherits it. So 7→6 needs
  **no new capture and no Stage-5 round-trip**. Originally one dispatch per approved directive (each its
  own depth-guard round); reworked so **the whole district's approved 7→6 set rides ONE Stage-6 dispatch
  = one round** — approve several alternate-rep requests, execute one, they all go together
  (`build_alternate_bundle_input` merges per-record inputs into a single multi-record package). Each
  record's alternate is chosen **yield-ranked** (`pick_alternate`/`live_alternates`, #155: higher-yield
  text before vision, never image-first), reading the record's **live** representation rows so a request
  persisted before ranking landed still picks correctly, and excluding **every already-failed file across
  the district's whole 7→6 history** (`_sent_files_by_rec`, F4) so a later round never re-offers a rep
  that already failed. Builds a NEW immutable Stage-6 dispatch (the prior dispatches untouched — history
  preserved) and re-enters Stage 7 through the normal extract path. This is the one back-edge that
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
  re-includes already-attempted districts; **`build_batch` (first-run) is untouched.** Compose now also
  **defers** (holds) a district's NEW-work while it has a live, still-executable 7→6 (§4-e below) — checked
  LIVE at compose time, never from the request's stale detect-time params.
- **Follow-up shaping (#160/#161/#162, epic #163):** `build_followup_batch` prefers **untried NCES
  schools** for a re-targeted band (schools not yet selected in any non-draft batch — an abandoned draft
  must never count as "attempted"); when every eligible school was already tried, it falls back to the
  full set and tags the band `query_strategy='widen_queries'`. Stage 2's `build_roster` reads that tag and
  runs the school's default query **plus** a differentiated SERP set
  (`common/config/stage2_query_templates.json` — phrasing variations only; they compose with the existing
  `site:{domain}` scoping, so they never hardcode a search operator that would collide); `run_wave1` runs
  every query per school and unions the URLs. A 7→3's `params.target_urls` (dormant — no producer yet)
  carry through as `seed_urls` on the district entry into Stage 2's `write_discovery`, which injects them
  into `candidates.json` (tool `seed_7to3`) so Stage 3 captures them through the existing pipe, no Stage-3
  change.
- **Follow-up auto-flow (#157, epic #163):** composing a follow-up batch now **auto-flows** it —
  `POST /api/extract/compose-followup` kicks off a background supervisor that auto-approves gate@1 (a
  follow-up carries an already-approved gate@7 decision, so re-gating it is redundant — governance §11b)
  then runs Stage 2 → Stage 3 → Stage 4 in sequence, **stopping at gate@5** (data quality — new URLs still
  need human review) with **gate@6 never auto-crossed** (the spend gate stays manual). Holds the per-batch
  run lock across the whole chain; any stage failure halts the chain and records where. `GET
  /api/followup/autoflow/{batch_id}` streams the live stage.

**Guards (the must-haves, built + hardened):** the **REQ-051 budget governor** (`common/budget.py` +
`common/config/budget.json`) bounds OpenRouter spend/effort on **four caps** — three money axes plus a
depth guard: **per-run** (halts the run), **per-district per-run** (skips the district in this handoff),
**per-district TOTAL** (cumulative across ALL handoffs — the real request-loop guard: a hard district that
keeps failing + re-requesting can't run up unbounded spend over many follow-up rounds, since each round is
a fresh handoff), and **`max_request_rounds`** (the non-spend depth guard, below). The three money caps are
enforced pre-district in `run_council_streaming`, seeded from durable `SUM(extraction.cost_usd)` (per-run
scoped to the handoff, total across all of the district's handoffs) so resume stays under the same
ceilings. `max_request_rounds` is the **per-district×band depth guard** — counted as `COUNT(DISTINCT
executed_ref)` **everywhere** (a live bug found + fixed during epic #163: counting rows instead of distinct
refs would trip the guard after a single bundled round of several 7→6s), so the cyclic loop provably
terminates. The paid 7→6 re-extraction is budget-gated when its new handoff is run. A district whose 7→6
rounds are exhausted is excluded from the compose-defer set (`_defer_76_districts`) — otherwise its
un-executable ("zombie") 7→6s would hold its rediscovery forever, a live deadlock found + fixed on Las
Cruces during the shakedown.

**Surfaces:** CLI `python3 -m infrastructure.acquisition.process_governance.stage7_execute
{compose-followup|execute <request_id>|execute-bundle <district_id>}` (CLI-first per the ramp-up model) +
the server endpoints `POST /api/extract/compose-followup[/preview]` and
`POST /api/extract/execute/{request_id}` + **console UI**: gate@7's "Execute re-dispatch" per approved
7→6 card fires the whole district's bundle; "Compose follow-up batch" opens the **preview modal**
(`dry_run=True` — no persistence) before committing; Stage 6's dispatch list carries a "Run extraction"
trigger (§0) — all surfaces call the same underlying functions.

- **Still open — not built:** the narrow model "referenced-but-unread" detector signal (deferred per the
  measured-pass discipline); a clean live non-benchmark end-to-end run of the FULLY-CORRECTED loop in one
  pass (#122) — the shakedown that produced epic #163 exercised most of this loop repeatedly against real
  districts (Marion, Pittsylvania, Las Cruces) while finding and fixing the bugs above, but hasn't yet run
  start-to-finish on a fresh batch with the corrected code.
- **Open research question, unresolved:** the OpenRouter session/context question — can an API session
  stay open across a request round-trip, or must every re-entry re-pass frozen context (the immutable
  dispatch) into a fresh call? See `STAGE6_DISPATCH_DESIGN` §3F. (Today the re-entry re-passes the frozen
  dispatch — a fresh call — which is correct regardless of the answer; a persisted session would only be
  an optimization.)

---

## 5. References
- `STAGE6_DISPATCH_DESIGN.md` §0a (the handoff shape), §3F (the loop as first sketched from the
  Stage 6 side).
- `PIPELINE_GOVERNANCE_AND_STATE.md` §11 (gates/console), §11b (the ramp-up model), §11d
  (follow-up batches route through Stage 1).
- `models-and-council-composition/LLM_COUNCIL_RESEARCH_2026-06.md`,
  `models-and-council-composition/models-and-council-composition.md` (the batch_00000 report),
  `EXTRACTION_BENCHMARK_FINDINGS.md`.
- REQ-054 (read-times invariant), REQ-055 (gross metric), REQ-056 (cross-family consensus), REQ-051
  (budget governor), REQ-117 (this build), REQ-118 (request execution).
  **Ledger drift to note (mostly resolved 2026-07-22):** `docs/REQUIREMENTS.yaml`'s REQ-117 and REQ-118
  `status:` fields now both read `tested`, matching this doc's status banner (REQ-118 previously lagged at
  `in-progress`). One cosmetic residual remains inside the REQ-117 entry: its last acceptance-criterion
  line still reads request-EXECUTION as "NOT MET" even though the entry's overall status is `tested` and
  execution was built + hardened across epic #163 and PR #240 (2026-07-12). This doc remains the accurate
  present-state source; that stray AC line is the only follow-up left, tracked separately from this rewrite.
- **Council Lab** (the producer that tunes the councils/prompts/cost the request loop routes on): design in
  `COUNCIL_LAB_DESIGN.md`; GitHub #80 (infra), #81 (spray A/B), #82 (image-council vision judge —
  fixed), #85 (camelot reader-routing).
- **Epic #163** (request-loop hardening + gate@7 console maturation, PR #167, closed) and its sub-issues:
  #158 (release cluster-drop, HIGH), #165 (current_state null-state), #160 (query-template config),
  #155/#159 (detector ranking + defer), #153/#161/#162 (bundle + seed-URL/eligible-schools shaping),
  #152/#156/#157 (console run-extraction, gate@1 refresh, follow-up auto-flow), #154 (lineage + compose
  modal). Follow-on, still open: #151 (inline PNG/PDF viewer), #164 (geo-scoped rediscover queries,
  future). (#122 the live end-to-end run — CLOSED 2026-07-06. Epic #119 quality work later closed
  #121/#276/#362/#120/#246 — see the status banner + change log.)
- **Hygiene batches 2–3B** (PRs #179, #191, #193, #196, #197 — commit range `4d31b77~1..d44ab24`), all
  merged: #173 (run-abort robustness) + #169 (truncation retry), PR #179; #176/#170/#175 (coverage-aware
  request loop), PR #191; #180/#187 (token-sizing + retry-ceiling unification), PR #193; #148 parts
  4A–4C (spend-seed consolidation, N+1 fix, lru-cached OpenRouter client, and other efficiency items),
  PR #196; #148 part 4D (`run_kind` first-class column), PR #197. #192 (dead `n_times` handoff-plumbing,
  surfaced by #180) tracked, not yet fixed.

---

## 6. Provenance / decision log

**2026-07-15 — epic #119 (Stage 7 extraction quality), CLOSED (PRs #508–#511).** Four changes, folded
into §0/§1 above: **#508** rewrote the truncation salvage in `parse.py` to `json.JSONDecoder().raw_decode`
(#276 — braces-in-strings and nested objects no longer truncate valid schedules) and guarded a non-list
`schedules` reply (#362 → `[]`); **#509** rendered the #237 single-school-LEA contamination flag as the
gate@7 warning banner (#246, backfilled as REQ-152) — a detect-and-flag signal the reviewer previously
couldn't see; **#510** added district-grain **mode-stability early-exit** (#120, REQ-151 — stop paying for
council calls once every fillable band's mode is stable; `Extraction.n_reps_skipped`); **#511** re-tested
the snake/column-hub class and CLOSED #121 (per-school extraction recovers all three Broward bands). Note:
#122 (the first clean end-to-end pass) had already closed 2026-07-06, predating this epic. Also confirmed
current in this pass: the extraction schema is **v4** (adds `evidence_quote`/`source_locus`/`stated_minutes`
(+`_quote`, path 2)/`school_year`/`applies_to`/`campus_names`), **8** prompt ids registered, production runs
v4 — the note previously described the v1 four-field schema.

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
  hub-table pages still mostly unresolved (#85; the snake/column-hub class re-tested and CLOSED as #121 via
PR #511, per-school extraction recovering all three Broward bands) — and the image council still trails the text
  council on native-digital reps, reinforcing the route-by-modality experiment (#132). Full scorecard:
  `COUNCIL_LAB_DESIGN.md` §0; persisted record at
  `data/acquisition/council_lab/judge_replay_a2bc80c004ca-image_partial.json`.
- **Epic #163 — request-loop hardening + gate@7 console maturation (2026-07-04/05), PR #167 merged.**
  Triggered by Ian's manual shakedown of the request loop against real (non-benchmark) districts — the
  first live exercise since REQ-118 landed. Built as 6 sequenced, independently-reviewed chunks (each
  functional commit followed by an adversarial review pass; findings fixed with regression tests before
  moving on) — the discipline itself a direct response to the #133 "re-implemented invariants" lesson.

  **Chunk 1 — #158, [HIGH], the load-bearing find.** Investigating why Marion/Pittsylvania's high/middle
  bands stayed empty despite discovered bell tables traced to a genuine data-loss bug, not a Stage-7
  problem: content-hash dedup (`duplicate_of`) and shingle clustering (`is_cluster_rep`) pick their
  canonical keeper INDEPENDENTLY; when they disagreed (a cluster rep whose `duplicate_of` pointed at a
  sibling), release's `CANONICAL_RECORD_WHERE` matched NEITHER member and the whole cluster silently
  never reached dispatch. Triggers on the common pattern of a schedule PDF mirrored at two URLs (site +
  a `5il.co`/thrillshare host). Fixed at the write sites (not the 4 read-side consumers, per a grimp
  dependency check first); backfill-repaired the 7 existing bad clusters. **Verified live:** re-dispatching
  Marion's now-reachable tier-A bell tables recovered its middle band from empty to 425 min — a real
  before/after on real data, not a unit test. A code review of the first-pass fix caught scope bugs (would
  have wiped legitimate singleton content-dedup on every re-ingest); corrected before merge.

  **Chunk 2 — #160 (config foundation).** A differentiated SERP query-template set
  (`common/config/stage2_query_templates.json`) for a 7→2 rediscover to cast wider than the default query.
  Ian's review catch, mid-build: an initial draft dropped a `filetype:pdf` template on the mistaken belief
  it conflicted with domain scoping — it doesn't (`site:` composes fine with a search operator); restored
  after Ian pushed back directly ("why drop filetype:pdf? That's not in conflict with domain scoping").

  **Chunk 3 — #155, #159 (pure detector intelligence, zero paid calls).** Root-caused from the Chunk-1
  recovery: Marion's now-dispatched MHS bell table STILL returned 0 facts because the release layer sent
  the noisy OCR rep over the clean full-text rep, and the detector's alternate-rep pick was image-first
  regardless of yield — Pittsylvania showed the identical shape (a truncated handbook slice sent instead
  of the full `pdftotext.txt`, n_times 86 vs. 42, ignored). Fixed via `rank_alternates()` (yield-ranked,
  text-before-vision) + an honest reason string. Also: a district-altitude 7→2 now DEFERS while a cheaper
  7→6 remedy is unexhausted (§4-e). A live evidence trail (Marion's own re-extraction, Las Cruces's
  partial re-dispatch results) grounded both fixes in real detector output, not hypothesis.

  **Chunk 4 — #153, #160/#161/#162 exec (the biggest chunk).** Bundled a district's 7→6s into one round
  (depth guard counts rounds, not components — the original #153 complaint); wired the query-strategy
  signal and seed-URL plumbing from Stage 1 through Stage 2/3 consumption, verified live (Pittsylvania's
  Chatham High: 1 query → 5). Two review rounds found real defects: the compose-side depth-guard query
  still counted ROWS after the executor moved to counting ROUNDS (would have depth-blocked a follow-up
  after one real bundled round); the live-defer check didn't exclude rounds-exhausted districts, which
  would have DEADLOCKED Las Cruces's rediscovery forever (verified: it was already in that state);
  `_attempted_schools` counted schools from DRAFT batches, so the abandoned `batch_00009` was poisoning
  the untried-schools set for Pittsylvania.

  **Chunk 5 — #152, #156, #157 (console orchestration).** A "Run extraction" trigger (reusing the
  issue-#47 background-job pattern verbatim); the gate@1 stale-list bug (`loaded1` guard fetched once per
  page load); and the follow-up auto-flow, which encodes a governance decision made mid-epic: the
  canonical gate design was only **1/5/8** (permanent, structural); **gate@6/7 are supervision gates**
  that emerged later from API-spend caution during a context-clear cycle — the first to relax as
  reliability is proven (governance §11b). So a follow-up (carrying an already-approved gate@7 decision)
  auto-passes gate@1 and auto-runs Stages 2→3→4, landing at gate@5 (still manual — new URLs, data
  quality) with gate@6 untouched (still manual — spend, Ian's explicit call). Review caught a done handoff
  still offering "Re-run extraction" — a resume-by-default run that would silently no-op; fixed to an
  honest "✓ extracted" marker.

  **Chunk 6 — #154 (closing the loop's visibility gap).** The literal complaint that named epic #163:
  "I'm not sure what status is" after firing executions from the console. Added per-request lineage
  (executed → its handoff/batch + live state), a ⛔ blocked badge for depth-exhausted zombies, a ⏸
  deferred note, and an in-Stage-7 preview modal before composing (cancel/ESC/click-out all no-op) — Ian's
  standing preference for reviewable derived actions, without leaving Stage 7's view. Review caught the
  deferred note reading the request's stale detect-time params instead of the same live check compose
  runs — exactly the class of bug lineage exists to prevent, since a stale card would disagree with what
  compose actually does.

  **Verification discipline held throughout:** every functional commit got its own adversarial review pass
  before the next chunk started (not batched at the end); real bugs found in 4 of 6 chunks despite each
  commit shipping with its own tests and a green suite — the review step, not the tests alone, is what
  caught them. Final: 974 DB-free + 64 govdb tests, `lint-imports` 3 kept/0 broken, console changes
  Playwright self-verified live against the running server. 21 commits, ~2.4k lines, PR #167.

- **Batch 2 — #173 (run-abort robustness) + #169 (truncation recovery), PR #179, merged.** The #122 live
  shakedown's own symptom motivated the fix: a single `FileNotFoundError` reading Marshall's
  `harvest_slice` stranded districts 16→18 mid-run. Fixed at two altitudes: per-rep isolation in
  `_run_district` (an unreadable/unprocessable rep becomes a recorded failed rep; the district's OTHER
  reps still extract — Marshall would have recovered them) and per-district isolation in
  `run_council_streaming` (any other per-district failure lands in `results['failed']`, batch continues).
  `BillingAuthError`/`SystemExit`/`KeyboardInterrupt` still halt, never swallowed — hoisted into the
  canonical `HALTING_EXCEPTIONS` tuple so a future halting type is added in one place. The background job
  now reports `state:'partial'` (`n_failed` + `failed[]`) instead of a false clean success. Separately,
  #169 fixed silent tail-loss: a truncated reply (`finish_reason=length`) now retries ONCE at
  `MAX_TOKENS_CEILING` (32k then; the constant was later renamed and unified with #180/#187, below) —
  successful retry replaces the original, a still-truncated retry keeps the ⚠ flag, an erroring retry
  keeps the first attempt's salvaged head; both attempts' cost/tokens/latency are summed onto the returned
  result so the REQ-051 governor sees true spend (#182). 988 DB-free + 64 govdb + 120 integration green.
- **Batch 3A — #176/#170/#175, coverage-aware request loop, PR #191, merged.** See §4(f) for the mechanism.
  Root cause was the #122 loop report measuring ~57% of follow-up spend added zero new coverage — phantom
  bands and already-fully-covered districts still fired paid remedies. The `real_bands` gate (from the new
  shared `school_sampling.real_bands_for_district`, mirroring Stage 1's own band-assignment logic) is
  applied both at detect-time (`requests.detect_requests`) and, defense-in-depth, at compose-time
  (`stage7_execute.plan_followup`, live re-check — never the stale detect-time state, the #159 lesson
  generalized). Measured live: 24/88 districts (27%) carried a phantom claimed band (always `middle`, the
  K-6/7-12 split), all already `executed` (the measured waste); `real_bands ⊆ claimed` held for every
  district, confirming the gate is purely subtractive. Correcting `lea_claimed_bands` at the Stage-1 source
  was considered and deliberately deferred (complicated by the over-coverage case — real bands may need to
  *grow* from extracted evidence). 1010 DB-free + 65 govdb + 567 integration green.
- **Batch 3B — #180 (pre-size max_tokens) + #187 (unify the retry ceiling), PR #193, merged.** #169
  (Batch 2) shipped the truncation *safety net*; this is the *optimization* — size the FIRST call right so
  the retry rarely fires and the run stops paying the prompt twice on predictable big rosters. Signal:
  reply length is roster-bound at ~47 completion tokens/school, flat, no verbosity noise, measured over 840
  real receipt calls (`EXTRACTION_TOKEN_SIZING_2026-07-06.md`); each school ≈ 2 clock times, so
  `size_max_tokens(n_times) = clamp(ceil(n_times/2 × 47 × 1.5), 16k floor, 32k ceiling)`. One design
  refinement vs. the issue's original plan: `n_times` is dead-plumbed through freeze (0 of 275 handoff reps
  carry it — filed as #192, affecting the Stage-6 cost model too), so sizing instead **recomputes the
  time-count from the resolved content at dispatch** (`stage7_run._content_n_times` →
  `build_signals.time_positions`) — more robust (works on every handoff, old and new) and uses the exact
  signal that defines `n_times`; image/scan reps stay at the floor with the #169 retry as backstop. #187
  closed by construction: the retry ceiling was renamed `ESCALATED_MAX_TOKENS` → `MAX_TOKENS_CEILING`, ONE
  constant shared by sizing (clamps to it) and the retry (escalates to it, only when below it), so the two
  mechanisms can never disagree. Measured before/after, replayed over all 840 receipt calls: the 3
  historical truncations (Baldwin 355 schools, Stroudsburg 420) would size enough on the first call; 0
  calls newly truncate (the floor prevents regression); 0 image-rep truncations (retry backstop untouched).
  Time-anchored chunking (for documents that would exceed the 32k/680-school ceiling) was considered and
  deferred — 0/840 real documents hit that ceiling, so it solves a problem not yet observed. 1022 DB-free +
  66 govdb + 567 integration green.
- **Batch 4C/4D, efficiency + run_kind — #148, PR #196 (4C) and PR #197 (4D), merged.** The
  2026-07-04 code-review's efficiency tier, split into two PRs since the `run_kind` schema change +
  backfill warranted separate review. #196: the OpenRouter client (`_client`) is now `lru_cache`d per
  `(key, timeout)` instead of built fresh per paid call (was ~30-60s/batch of pure TLS handshake); the
  execute-path N+1 (`_bundle_alternate` loading every district record to find a handful named by approved
  7→6s) is fixed via the new `release.load_records_by_key` (2 queries total); the REQ-119 SDK-streaming
  guard gained an import-linter `forbidden` contract as a structural complement to its AST walk (which only
  covers function bodies, not module-level calls); plus smaller fixes to `council_lab` receipt scanning,
  `stage7.js` refresh deduplication, and 27-GT completeness test coverage. #197 (closing #148): promoted
  the `handoff_hash NOT LIKE '%-image'` console filter — which only ever caught the literal `image` council
  id and would let a second vision council (e.g. `council_id="vision2"`) shadow a district's real
  production run in the gate@7 pane — to a first-class `run_kind` column (`'production'` default |
  `'probe'`), stamped by `image_handoff_variant` for ANY council_id, threaded through
  `persist_run_session`, and filtered by both gate@7 console queries. The `-image` hash suffix stays (it
  still does its other job: resume-isolation + lineage); `run_kind` is purely the visibility discriminator
  now. Additive migration + guarded, idempotent backfill of legacy `-image` rows. Post-merge adversarial
  review of both PRs caught real defects before landing: 4C's `council_lab.load_receipts` dropped a
  district entirely if its newest receipt file was truncated (fixed to fall back to the older valid one);
  4D's `run_kind` fix stopped extraction ROWS from leaking into the console but left
  `detect_and_persist_requests` running unconditionally — a persisted probe would still write reviewable
  `extraction_request` directives, inflating a production district's pending count and risking a paid
  follow-up sweep of a probe's own findings (fixed: the request loop is now production-only). 1043
  DB-free + 69 govdb, 567 integration green; `lint-imports` 3-4 kept/0 broken.
- **2026-07-11 — second live shakedown (batch_00013) against the epic #200/#209-hardened pipeline, two
  request-loop regressions found and fixed (#231, #232, REQ-122).** With #122 (the first clean
  end-to-end pass) closed 2026-07-06, a fresh live non-benchmark batch was run to re-validate the loop
  after the epic #200 shift-left/epic #209 guardrail work landed. The batch's 7→2 follow-up journey
  (Union Hill ISD, Brownsville Ascend, Redbank Valley, Aspen Ridge) ran through Stage 7 round 3 and
  concluded still barren on model disagreement, not missing data — the open thread from here is
  aggregation-quality (#236/#237), not the request loop. Findings:
  - **#232 — gate@7's district view and band rollup read the LATEST production extraction only.** A
    scoped `7→6` retry creates a NEW extraction row holding just the retried rep; reading only that row
    made an earlier round's solid facts invisible (Brownsville Ascend: 7 accepted middle-school facts
    vanished from the console after a barren vision retry, though never deleted). Fixed with a new pure
    core, `stage8_aggregate.aggregate.merge_fact_runs` — deterministic per-`(band, school)` merge across
    every production run for a district (accepted beats unresolved in either run order; among duplicate
    accepteds the EARLIEST wins, since a follow-up round fills gaps and never silently overwrites solid
    signal — correcting one is a gate@8 human determination; among unresolved-only the latest diagnostic
    wins) — codified as **REQ-122**. `extract_district`/`extract_districts` now read across all
    production runs with per-fact provenance (extraction_id + handoff_hash); the latest run's header
    (cost/handoff/timestamp) stays per-run telemetry. Remediation needed zero data surgery — the merge
    restores visibility by construction. 8 pure merge tests (incl. the named Brownsville case) + an
    endpoint regression test.
  - **#231 — the `7→6` alternate list shown at gate@7 could re-offer an already-failed rep.** Detection
    (`stage7_run._district_request_inputs`) built its sent-file exclusion set from the CURRENT dispatch's
    reps only, so a NEW pending request's displayed "next alternate" could name a file already tried and
    failed in an earlier round (Union Hill, Brownsville). The pre-existing execution-side protection
    (`stage7_execute._sent_files_by_rec`, "F4") meant approving the stale display would still have picked
    a genuinely-untried rep — the bug was a misleading review surface, not a real re-dispatch — but
    auditing it surfaced a genuine second gap: a dispatch sending TWO reps of one record only names the
    first-seen file in `sent_file`, so the second could still be re-offered at EXECUTE time too (the
    single-field history had no way to record it). Fixed on both sides for full detect/execute
    consistency: the detector now emits `sent_files` (the complete send) alongside the legacy
    `sent_file`; both `_district_request_inputs` (detection) and `_sent_files_by_rec` (execution) union
    it into their exclusion sets. 2 pure + 4 govdb tests.
  - Two further findings logged at the time, not yet fixed: **#230** (Stage 6's initial rep pick doesn't
    apply the retry loop's yield-ranking) and **#233** (whether/how to auto-withdraw a pending request
    once its target is no longer barren under the cumulative state — an open design question, not a bug).
    Both resolved below, alongside two MORE regressions the shakedown's own follow-up batches surfaced.
  - #231/#232 merged 2026-07-11 (PR #221, alongside epic #200). Also logged from this pass, upstream of
    Stage 7 (Stages 1/2/3/5/6): #222/#223/#224/#225/#226/#227/#228/#229 — see the respective stage docs.

- **#230/#233/#234/#235 — request-loop integrity, PR #240, merged 2026-07-12.** Continuing to trace the
  batch_00013 shakedown's OWN 7→2 follow-up batches (14–17) surfaced two more regressions beyond #231/
  #232, alongside resolving the two open findings above:
  - **#234 — executing one request duplicated its still-open siblings.** `detect_and_persist_requests`'s
    dedup key was `(handoff_hash, target, altitude, route, band)` — scoped to ONE handoff. Executing a
    single `7→6` (`_bundle_alternate`) spins a brand-new handoff for the whole district, so any OTHER
    directive still open from an earlier round could never match its own prior row and got re-detected as
    "new" (live: 0602559's `high`-band `7→2` pending twice; 4220130's across FOUR handoffs). Fixed with
    the two-layered dedup described in §0 above.
  - **#235 — a Stage 4→5 hand-off silently vanished for single-district follow-up batches.** Root cause
    (definitively traced, not guessed): the follow-up autoflow (`server.py`) ran Stages 2→3→4 then
    **stopped** — it never called the Stage-5 ingest at all, so batches 00014–00017's new
    candidates/captures/processed docs never reached the `record`/`label` tables gate@5 reads. The console
    showed zero new URLs; nothing was actually lost (recovered live via a manual `BS.ingest_batch`
    backfill during triage). Fixed at the SOURCE, not the symptom: `run_stage4_with_ingest()` is now the
    ONE operation both the autoflow and the manual `/api/process/{batch_id}/run` paths use — a CI-enforced
    test asserts nothing in `server.py` calls `H4.run_batch` directly anymore, closing the recurrence
    class (autoflow was simply a SECOND `run_batch` caller that forgot the ingest the first one
    remembered) rather than just the one instance.
  - **#230 — Stage 6's initial rep pick ignored yield.** `release.best_send`'s handbook-slice branch now
    sends the slice only when its `n_times` matches or beats the district's best general text rep (ties to
    the slice); a cross-layer test pins this to `rank_alternates`' own ordering (the two can't share code
    — stage5_filter/stage7_extract are import-linter-separated siblings — so a live-drift guard substitutes
    for direct reuse).
  - **#233 — auto-withdraw, resolved.** See §0's `withdraw_satisfied_requests` entry above and REQ-123 for
    the mechanism; the design call (auto, not human-gated) is Ian's, with the full risk-asymmetry rationale
    captured there and in `PIPELINE_GOVERNANCE_AND_STATE.md` §11b.
  - **The adversarial review of the first draft found real defects in the fixes themselves** — the kind a
    green test suite doesn't catch: (1) `withdraw_satisfied_requests` and `detect_and_persist_requests`'s
    covered-bands check could not see the SAME transaction's own just-persisted facts, because production
    sessions run `autoflush=False` and `persist_run_session` never flushed before returning — #233's
    stated primary case (a round's own facts satisfying an earlier round's directive) was silently inert
    in production while every test passed on an `autoflush=True` fixture; (2) the fillable-band fallback
    (`if real_bands else claimed`) collapsed "unknown" and "known-empty" into the same branch, silently
    reproducing the exact un-withdrawable-forever bug #233 was fixing whenever a district's real-school
    data came back genuinely empty. Both fixed, both now proven by dedicated tests that exercise the real
    session config / the empty-set and all-phantom corners specifically — not just the happy path the
    first draft's own tests covered. Also closed in the same pass: a UI Reopen button that could silently
    resurrect a withdrawn directive with no re-check (now re-runs the premise check server-side); a false
    audit-trail risk in withdraw's per-row UPDATE (now rowcount-checked, matching `extract_request_review`'s
    existing pattern); `backfill_requests` missing the withdraw pass entirely (a third entry point that
    would have accumulated stale directives forever); and an over-broad `except` in the Stage-5 ingest
    failure handler that could mislabel a genuinely-committed ingest as failed.
  - Full mechanism: §0 above (`detect_and_persist_requests`, `withdraw_satisfied_requests`). REQ-123
    (auto-withdraw). 8 new/hardened tests across `test_stage7_persist.py`/`test_stage7_api.py`/
    `test_release.py`, incl. a production-session-parity test with no test-side flush.
