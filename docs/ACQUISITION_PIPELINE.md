# Bell Schedule Acquisition Pipeline

**Status:** Stage 1 (Queue) designed, built, validated, and CP-A-approved (`batch_00001.json` ready to advance). Stage 2 (Discovery) designed, built, and run live against all 12 districts in `batch_00001` (12/12 `found_all`); billing/auth failure handling hardened afterward. Stage 3 (Capture) designed, built, and run live against all 12 districts (150/150 URLs captured, 0 failures, all 12 `captured_all`) — Drive Tier 1, modal dismissal, unconditional `page.pdf()`, and emergent-candidate link-following all confirmed working on real data; Drive Tier 2 (OAuth) not yet built, deliberately deferred. Per-record hosting/CMS **fingerprinting** added + backfilled across all 12 (150/150) 2026-06-24 — raw signals only, surfaced SharpSchool/Apptegy/Educational Networks as the real platforms (none in the current `CMS_HOSTS`). Stage 4 (Local processing) designed, built, and run live 2026-06-23 — tool roster resolved by a real empirical spike against all 150 captured PDFs in `batch_00001` (keep `pdftotext`/`pdfplumber`-lines/`camelot`-stream/`camelot`-hybrid/`tesseract`; drop PyMuPDF, `pdfplumber`-text, `camelot`-network/lattice, `img2table`; heavy ML tools Docling/EasyOCR/PaddleOCR installed, timed, and deliberately rejected/uninstalled), waterfall design replaced by "run every kept tool against every applicable input, always." Production run against all 12 districts: 150/150 records processed, 0 crashes, 10 `processed_all` + 2 `processed_partial`. **Stage 5 (Local filtering): the CP-B review app, deterministic signals, the full 150-label pass, labeled topology + clustering, the funnel ingredients, the learning-loop infrastructure (config-as-data + measurement harness), and de-chrome are all BUILT; de-chrome MEASURED a strong win (category 0.43→0.60, topology 0.6→0.8). **The operational filter is now built too (REQ-094):** `release.py` emits one traceable **`filtered.json`** per district — an event-driven projection (no manual trigger; generated on the first scoring pass, refreshed on label/split + re-ingest events). Live on `batch_00001`: 12 files, **32 records to send** (the 32 canonical target-labeled records).** Stage 6 (routing/release — which representations → which OpenRouter model set) is REQ-101; Stages 7-9 design validated, per-school council rules still to build. **Console build started 2026-06-27 (REQ-102):** the gate@1 backend is built — the batch is now a first-class governance-DB entity (the working store) with `batch_NNNNN.json` as the regenerated receipt, gate@1 is an in-band batch-level approval with soft+audited editing, and `batch_00002` is the forcing function (created/advanced only through the console). gate@1 frontend next.
**Last updated:** 2026-06-26 (architecture update — see callout below).
**Companions:** `docs/diagrams/acquisition_pipeline_flow.md` (Mermaid visual reference, built stage-by-stage alongside this doc), `docs/EXTRACTION_BENCHMARK_FINDINGS.md` (model leaderboard + measured costs), `docs/technical-notes/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md` (full learnings), `docs/INSTRUCTIONAL_TIME_HARVEST.md` (why SEA central data is a dead end), `docs/METHODOLOGY.md` (Rules 6 & 7 — CTC and grade-span-integrity exclusions referenced below). The strategy/options report that preceded this is `docs/INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md` (now a pointer here).

> **⚑ Architecture update (2026-06-26) — governance app, state model & Postgres. Authority: `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`.** Five decisions reshape how the back half of the pipeline is governed; where this doc's older prose conflicts, the governance note wins (it supersedes; this doc is being reconciled to it, not rewritten):
> 1. **The Stage-5 review app becomes the *Acquisition Pipeline Governance App*** — a stage-selectable console spanning the **5 stage-numbered gates (2026-06-27, governance §11): `gate@1` (queue) · `gate@5` (per-URL review) · `gate@6` (handoff) · `gate@7` (council requests) · `gate@8` (results — the effective old CP-C; Stage 9 then auto-writes)**, with tuning + funnel dashboards. Stages 2/3/4 are ungated; each gate is manual/auto (Settings: global default + per-gate overrides, confidence-escalating). It moves to `infrastructure/acquisition/process_governance/`.
> 2. **DB: SQLite → Postgres**, an **isolated `governance` database** in the existing `lct_postgres` container (own user; drop+rebuild can't reach the production LCT tables). It becomes a **cross-stage cache** (ingests all stages' artifacts, not just Stage 5). *(**REQ-103 COMPLETE 2026-06-26** — governance DB + `common/db.py` + precious models; Stage-5 ingest + readers migrated SQLite→Postgres; cross-stage cache `discovery_school`/`candidate`/`capture`/`processed_doc` built. See `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §1b.)*
> 3. **STATE vs DATA.** The cross-stage *registry* migrated from `district_status.json` into a Postgres **event log** (`state_event`; current-state a SQL view). The per-stage *JSON artifacts* (`discovery/candidates/captures/processed/batch`) **stay authoritative on disk** — their role shifts from data-carriers to **auditable receipts**. Precious state keeps the version-controlled JSON-backup pattern (like `labels.json`). *(**REQ-099 COMPLETE 2026-06-26** — see Stage 1 registry note + governance §3.)*
> 4. **The Stage 5→6 release:** `filtered.json` per district = a **regenerable export** of the DB's release decision (one best representation per qualifying canonical record); Stage 6 emits an **immutable `handoff_<hash>_<timestamp>.json`** naming which districts go to the council, freezing fingerprints so "what we sent" is always recoverable.
> 5. **Stage 2 discovery goes headless** via the Claude Code CLI (`claude -p`, subscription-billed) — **no chat / no subagent-in-the-loop**; search providers are a **pluggable layer** (see Stage 2). This overturns the "Python can't spawn the subagent" framing throughout this doc.

> **What this replaces.** The Jan-2026 "production ready" design on this page — Crawlee *blind-maps* a district site → Ollama *ranks* URLs → Ollama *triages* PDFs — was superseded on 2026-06-13 after benchmarking. **Blind crawling does not find schedules; local Ollama extraction topped out ~37%; the Ollama models were deleted.** The validated design is **search-led discovery → tiered capture → local filtering → cheap-cloud council extraction → modal aggregation → fail-loud statutory fallback.** The salvageable implementation detail from the old design (modal dismissal, Google-Drive handling, edge-case/anti-bot rules, the Crawlee service itself re-cast as a *one-hop fetcher / school enumerator*) is retained below; the dead parts (blind mapping, Ollama rank/triage, the learning loop) are archived in git history.

---

## Goal

Per district, **daily instructional minutes per grade band (elementary / middle / high)** — the LCT numerator — for ~20,000 U.S. districts. We optimize for **school-level bell-schedule collection** (express per-band minute statements are rare), then aggregate to a district band value.

---

## The 9-stage pipeline

```
1 Queue    → 2 Discover (waves) → 3 Capture (tiered) → 4 Local process (OCR/text)
          → 5 Local filter (coarse) → 6 Hand to OpenRouter → 7 Extract (council, per-school)
          → 8 Aggregate (modal→mean) → 9 Incorporate (DB, or statutory fallback)
```

### 1 · Queue — built 2026-06-22 · gate@1 console backend built 2026-06-27 (REQ-102) · deep design + decision log: `docs/technical-notes/STAGE1_QUEUE_DESIGN_2026-06.md`

**Purpose:** build a batch of districts + per-band school lists to target — the structured, `gate@1`-reviewed input Stage 2/3 consume. **In:** NCES `ccd_lea_029` / `ccd_sch_029` + DB enrollment/staffing/`is_shared_service_entity`. **Out:** the batch as a first-class entity in the **governance DB** (the working store — `batch`/`batch_district`/`batch_school`), with `data/acquisition/queue/batch_NNNNN.json` **regenerated from the rows as the receipt** (structured targeting only, no prompts; schema `batch.example.json`). Code: `stage1_queue/queue_batch.py` (`build_batch()` pure + `persist_batch()`), `stage1_queue/batch_store.py` + `models.py` (working store), `process_governance/server.py` (gate@1 API) (+ `common/school_sampling.py`, `common/district_status.py`).

- **Pre-queue exclusion filters** (all live, recomputed every run — never a persisted list): not-operating · CTC/shared-service (`METHODOLOGY.md` Rule 6) · grade-span integrity (Rule 7, exclude **and** flag) · already-attempted (reached Stage 3+, **first-run batches only**). Plus non-null `enrollment_k12`.
- **Stratified sampling:** 4 equal-count enrollment quartiles × 3 districts (= 12), state as a per-pick tiebreak, `seed = batch_id`.
- **Per-band school selection:** up to 12 schools/band (census if ≤ 12) from the **school-level** roster — **LEVEL-primary classification** + `recursive_band_groups()` for ambiguous spans; Regular-School-only (no preschool/virtual/CTC/SpEd); grade-13 in the high band; most-constrained-first cross-band overlap minimization; seeded random sample over the cap.
- **NCES denominator:** `nces_school_counts {total, by_level}` (our-criteria count by raw `LEVEL`) travels with the batch — provenance for Stage 5 topology + the funnel, never a selection input.
- **`gate@1` (was Checkpoint A) — now an in-band console approval (backend built 2026-06-27):** approval is a **batch-level** transition (`batch.status: draft → approved`) + per-district `gate@1` events; editing is **soft + audited** (reject district/school, add school — `included` flips / inserts, locked once approved, `reopen` to edit). The **batch-of-record is created + advanced only through the console** (hand-run `queue_batch.py` = dev/test). Frontend queue view is next. (governance §11h.)
- **Two batch types + completion grain = district × BAND** (governance §11d): **first-run** (excludes already-attempted) vs **follow-up** (re-includes, targeting unsatisfied bands); 12-district hard cap; schools are instrumental — a district is "satisfied" per *band*, not per school (Dunseith). Follow-ups are created at the return to Stage 1, reviewable at `gate@1`.
- **Cross-stage state** lives in the Postgres `state_event` log (REQ-099); `district_status.json` is its regenerable backup; `already_attempted` = furthest stage ≥ 3.

### 2 · Discovery — built 2026-06-23 · deep design + decision log: `docs/technical-notes/STAGE2_DISCOVER_DESIGN_2026-06.md`

**Purpose:** find *a* bell-schedule page per targeted school (a **recall** problem — Capture/Extraction verify). **In:** Stage 1's `batch_NNNNN.json` — read directly, **never** re-deriving band membership from NCES CSV (that would discard every Stage 1 `gate@1` fix). **Out:** per district `discovery.json` (full per-school audit trail) + `candidates.json` (flattened, deduped, capture-ready URL list) under `data/raw/lea-website-captures/<id>_<slug>/`. Code: `stage2_discover/discover_stage2.py` + the `.claude/skills/stage2-discover/SKILL.md` orchestration; supersedes the manifest-reading `discover.py`/`per_school_run.py` (utility pieces `host_of`/`gate`/`openrouter_search` carry forward).

- **Orchestration:** Wave 1 is the only agent step (one Haiku WebSearch subagent **per district**, returns one strict JSON block); everything else is deterministic Python (`reconcile` → `roster` → `finish`). Subagents never write to `data/raw/`.
- **Cost-ascending waves:** Wave 1 (Claude WebSearch) → gate → **residual** check → Wave 2 (OpenRouter `gpt-4o-mini-search`) **only over schools Wave 1 left unsatisfied** (empty residual ⇒ no OpenRouter call at all).
- **Gate** (`common.discover.gate`): reject no-host/news/aggregator always; scoped (district has a domain) keeps **on-domain** or **CMS-slug** (approved `cms_hosts` suffix + slug in URL) only; unscoped keeps any non-news result.
- **Flatten/dedup** by normalized URL collapses a shared hub page into one capture target — which is *why* **topology classification was dropped** (not enough pre-content signal; the dedup keeps the efficiency, the per-school audit trail survives for later).
- **Reconcile = filesystem-authoritative:** `discovery.json` on disk IS "done"; registry-ahead-of-disk is a hard-stop CONTROL FAILURE. **Redo is versioned, never an overwrite, always manual.** One registry write per district at completion.
- **Failure handling:** Wave 2 degrades per-school on a normal error, but **HTTP 401/402/429 (billing/auth) raises `SystemExit`** and halts the whole run (every later call would fail identically).
- **Ungated** (no `gate@2`; Stages 2/3/4 are ungated) — the next human gate is `gate@5` (Filter). Outcomes: `found_all` / `found_partial` / `manual_flag_all`.
- **Headless + pluggable-provider reframe (2026-06-26, DESIGNED, not built — REQ-104):** shell out to `claude -p` per district (full headless agent, schedulable), providers a pluggable layer behind a common candidate-URL contract; wave/gate/residual logic unchanged. Discovery is ≈free; Stage 7 extraction is the paid stage (governance §7a). See the design note §3.

### 3 · Capture — *tiered* (local Playwright) — built 2026-06-23 · deep design + decision log: `docs/technical-notes/STAGE3_CAPTURE_DESIGN_2026-06.md`

**Purpose:** fetch + persist every candidate page — capture everything available, trust downstream. **In:** each district's `candidates.json` (read, never modified). **Out:** `captures/<hash>/` (one dir per URL, `hash=md5(url).slice(0,10)`) + `captures.json` (per-candidate record). Code: Python orchestration `stage3_capture/capture_stage3.py` (reconcile/rollup/registry, mirrors Stage 2) + Node `infrastructure/scraper/capture_discovery.mjs` (browser work) + `capture_drive.mjs` (Drive Tier 1).

- **Per-candidate branch** (`stripFragment`-deduped): **Drive/Docs** Tier-1 export URLs (Docs→PDF+MD, Slides→PDF, Sheets→CSV+PDF) — Tier-2 OAuth designed-not-built, a Drive failure is a per-item `needs_oauth_reauth` flag (never a run halt); **direct PDF/image** byte-fetch (never `page.pdf()` an existing PDF); **generic HTML** `goto`+modal-dismissal+innerText/screenshot/**unconditional `page.pdf()`** + one-hop **emergent-candidate** link-following (`SCHED_KW`, CDN PDFs included).
- **Hosting/CMS fingerprint** (per record, raw signals only — `final_host`/`server`/`resource_hosts`/`cms_hint`/…), URL-level; `backfill-fingerprints` + `recompute-cms-hint` apply it to captured data with no re-capture.
- **De-chrome** (REQ-091, built+measured): `segmentChrome()` writes additive `page.main/header/footer/nav.txt` alongside the untouched `page.txt` — the fix must live here (render time) since only innerText is persisted. Measurement → Stage 5 note (category 0.43→0.60, topology 0.6→0.8).
- **Reconcile** filesystem-authoritative (registry-ahead-of-disk = CONTROL FAILURE); **redo versioned**, never overwritten. **Ungated.** Outcome: `captured_all`/`captured_partial`/`capture_failed_all`. **Superseded, don't revive:** `mapper.ts`'s `PlaywrightCrawler`, `google_drive_handler.py`'s Playwright/Gemini tiers.

### 4 · Local processing — built + run live 2026-06-23 (150/150 records) · deep design + decision log: `docs/technical-notes/STAGE4_PROCESS_DESIGN_2026-06.md`

**Purpose:** spend free local compute so Stage 7 (paid council) never pays to find a page has no text. Asks only *is there machine-readable text* — not relevance (Stage 5), not best-table (Stage 7). **In:** `captures.json` + `captures/<hash>/` files (read, never modified). **Out:** `processed.json` (per-record `texts[]`, `text_file` a filename reference never inline) + `extracted.txt`/`<tool>.txt`/`raster_p-<N>.png` per dir. Code: `stage4_process/process_stage4.py` (does the extraction itself — fast local tools, no browser/LLM).

- **Run every kept tool against every applicable input, always** (no waterfall — a real test showed short-circuiting discards signal): **PDF** → `pdftotext -layout` + `pdfplumber`-lines + `camelot` stream/hybrid (tables as Markdown); **image** → tesseract ×3 distinct reps (`screenshot`/`image`/`raster` via `pdftoppm`); **existing .txt/.md/.csv** referenced, never rewritten. Every attempted rep gets an entry (success/below-bar/errored).
- **Usable bar** (`is_usable`): ≥120 chars + ≥0.85 printable — deliberately weaker than & separate from Stage 5's relevance check.
- **Tool roster from an empirical spike** (all 150 PDFs): kept pdftotext/pdfplumber-lines/camelot-stream/camelot-hybrid/tesseract; **heavy ML (Docling/EasyOCR/PaddleOCR) timed, rejected, uninstalled** — that work goes to the paid council. A time-count is supporting evidence, not proof of quality.
- **Two fail-loud reconcile checks:** registry-ahead-of-disk **and** a manifest-claims-a-missing-file consistency check. **No vision escalation, no dup-PDF dedup** (deliberate non-goals). **Ungated.** Outcome: `processed_all`/`processed_partial`/`no_usable_text_any`.

### 5 · Local filtering (coarse)
Cheap `pdftotext`-density sniff: clock-time count + bell keywords; reject obvious non-schedules (board calendars, administrative pages). Deliberately cheap and high-recall — precision tightening (URL-keyword weighting, time-grid detection) is a later pass. Code: `infrastructure/acquisition/stage5_filter/relevance.py` (stale draft, predates the Stage 1-4 redesign — see Key files).

> **Stage 5 as actually built (2026-06; authority `docs/technical-notes/STAGE5_FILTER_DESIGN_2026-06.md`).** The coarse `relevance.py` sniff was superseded by the **CP-B review app** + deterministic signals (de-chromed), likelihood tiers, weak category hypothesis, near-duplicate clustering, labeled topology, handbook page-harvest, the funnel ingredients, and the **learning-loop infrastructure** (config-as-data + measurement harness + tuning ledger + frontier search). **The output, `filtered.json`, is the human-confirmed *release* of CP-B** (not the old "candidate list the human reviews" — the app *is* the review surface). Per the 2026-06-26 architecture: `filtered.json` per district is a **regenerable, traceable export** (built REQ-094, `release.py`) — **every canonical record with a `decision`+`reason`**, and for the sent ones **one best representation** (densest usable text; image when `visual_text_gap`/`target_image_only`; PDF + `harvest_pages` for handbooks), carrying tier/topology/`emergent`/`intended_schools`/cost-estimate + per-district `(config,labels,data)` fingerprints, honestly labeled `gross_bell_to_bell`. **It is EVENT-DRIVEN, not a manual button** (governance §6, revised): generated on the first scoring pass (`build_signals` ingest) and refreshed on label/split events + re-ingest. CP-B is the per-URL representation review; the *release/routing* (which package → which model set) is Stage 6 / REQ-100.

### 6 · Hand to OpenRouter
Extraction standardizes on **OpenRouter** (`google/gemini-2.5-flash` etc.) — even though the first Flash pass used the native Google API. Inputs: OCR'd text / clean text / PDFs / screenshots per the tier.

> **Stage 6 = routing + release (design in progress: `docs/technical-notes/STAGE6_HANDOFF_DESIGN_2026-06.md`).** Stage 6's job is deciding *which package of representations* goes to *which OpenRouter council config* (`gate@6`), then dispatching. It reads the per-district `filtered.json` exports (the winner **+ alternate target-flagged reps**, so a reviewer can swap the representation) and emits an **immutable `handoff_<hash>_<timestamp>.json`** naming the chosen districts and **freezing** each one's content/fingerprints + assigned config at dispatch time — so "what we actually sent on date X" is always recoverable (required by the Stage-7 "council can request more evidence" loop), even after a later regenerate. The handoff carries the council config(s) + total cost estimate; a `dispatched` state-event references its hash. **Open (the design-note agenda):** the council-config object, signals→routing/assignment, cost estimation, per-district-vs-per-rep config grain.

### 7 · Extraction — council, **per-school**
- Extract **each school page separately** (not a concatenated district dump — that's the over-stuffing failure mode), pulling the **first-bell START and last-bell END** time per band. **Target = GROSS daily instructional minutes (end − start), bell-to-bell.** We do **NOT** subtract lunch/passing/recess, and we do **NOT** apply assumed deductions — gross is the honest, simple target (it only needs two numbers nearly every schedule states plainly). Net minutes is a deferred future enhancement; "gross-with-assumptions" is dropped (assumed deductions add fake precision). **Ignore early-release/block days** — standard full day only. (Note: our existing GT was already gross — `instructional_minutes` = end − start — so this removes a spec/GT contradiction rather than lowering the bar.)
- **Council = the 6 non-reasoning candidates** (Update 4 of the benchmark doc): default **Gemini 2.5 Flash**; cross-family partners **DeepSeek V3.2 / Mistral Large 2512**; near-free members **Mistral Small 24B / Gemini 2.5 Flash-Lite / Qwen3-235B-2507**. Grok 4.3 and Qwen3.7-Max removed (reasoning-token cost 4–70×; not 100% on difficulty>0.70). **Exact membership + decision rule: open.**
- Accuracy context: top models hit **~95–100% on good inputs (difficulty>0.70)** but ~68% on the full 41 — **input quality is the ceiling, not the model.**

### 8 · Aggregation — modal, then mean
Across the sampled schools in a district, the band value is the **modal** (most common) gross minutes; if the mode is inconclusive/uncertain, fall back to the **arithmetic mean** for that band. **Models extract per-school start/end rows; deterministic code computes the mode** — never ask the model to pick the "typical" schedule (that hides the distribution and offloads statistics to the LLM). (`school_schedules` per-school rows → MODE-aggregate to `bell_schedules`; schema ready, migration 016, REQ-042.)

### 9 · Incorporation — fail loud
Write the district band values to the DB. A district where discovery finds nothing or the council can't agree lands as **`method=statutory_fallback`** — **labeled, never counted as enriched** (Rule #6, REQ-024). Coverage ≠ enrichment.

---

## Architecture distinction (carry this forward)

| Stage | Shape | Why |
|---|---|---|
| **Discovery (2)** | **Waves** (cost-ascending, stop when found) | Recall problem — any tool finding the page is success; capture verifies. Running all tools on every district is pure waste (26/37 found by all three). |
| **Extraction (7)** | **Council** (independent cross-check) | Correctness problem — agreement between decorrelated models buys confidence in the *answer*; disagreements route to human QC. |

**Crawlee is re-cast:** not a schedule-finder (blind crawling failed) but a **school enumerator** (off NCES, to drive the per-band sample) and **one-hop off-site fetcher** (CDN/Google-Drive-linked PDFs).

---

## Extraction failure modes → pipeline checkpoints (planning artifact, from the 2026-06 GT exercise)

The real value of the GT-curation exercise turned out to be a **systematic survey of how district schedules fail to extract** — each curated district surfaced a distinct, namable failure mode. A collection pipeline with checkpoints needs a gate for each. (Detail on each is in the per-finding sections below; this is the consolidated planning view.)

| # | Failure mode | Surfaced by | Required checkpoint / gate | Status |
|---|---|---|---|---|
| 1 | Image/canvas-rendered page, **OCR fails** (styled/low-contrast) | Mat-Su (whs/pjm) | capture screenshot → reader-route to **vision** when OCR returns nothing | reader-route spec'd; vision spiked ✓ |
| 2 | **Multi-column scan**, OCR scrambles columns → false consensus | New Haven CT | route to **vision**; **down-weight confidence** on garbled-capture sources | spec'd; vision validated ✓ |
| 3 | **Clean image flier** (works via OCR) | Cleveland .webp | **Tier 2.5 OCR** (cheap); no vision needed | handled ✓ |
| 4 | **Multi-page column-snake** drops tail bands (high) | Broward | use **band-from-school-name** signal; layout-aware/vision reading | FIX CANDIDATE — open |
| 5 | **Input-cap truncation** (`MAX_TEXT_LEN`) silently drops tail | Orange | **chunk + aggregate large inputs, never truncate** | FIX — open |
| 6 | **K-8 school assigned to only one band** (should cover elem+middle) | Cleveland K-8 | **queueing applies NCES `bands_for`** (grade-span → bands) before extraction | production queueing handles; GT-artifact limit |
| 7 | **Charter** schools present, untagged | Fairbanks | **tag** from NCES `CHARTER_TEXT` (never exclude) | handled ✓ (REQ-060) |
| 8 | **School-name matching** holds schools out as `unresolved` | Fairbanks, Orange | watch unresolved rate; **do NOT loosen matcher** until it demonstrably blocks | WATCH — open (Open-decision #6) |

**On #6 (Cleveland K-8) specifically — a GT-artifact limit, not a pipeline gap:** the GT proposer (`gt_propose`) reads a flier/PDF and guesses band from the school *name* on the page, so it has no grade-span and files a K-8 under `elementary` only. The **production pipeline starts from the NCES roster**, where queueing applies `school_sampling.bands_for(GSLO, GSHI)` → a K-8 deterministically maps to `{elementary, middle}` *before* extraction. So the production path already has the signal the GT exercise lacked. **Watch-item:** confirm the live wiring carries `bands_for` band-assignment through to per-school output. (Consequence in the GT: Cleveland's `middle` band is undercounted — its K-8 schools sit in `elementary` only; minor asterisk for review.)

---

## Extraction council design (stage 7) — candidate configs, to be selected empirically

Grounded in the council research (`docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`) and the measured leaderboard/costs (`EXTRACTION_BENCHMARK_FINDINGS.md` Update 3–4). **Principles, fixed:**
- **INVARIANT — extractors read TIMES; deterministic code computes MINUTES and the MODE.** A council model only ever returns per-school `{start_time, end_time, grade_level, school_name}` *facts it read from the artifact*. It never computes instructional minutes, never subtracts anything, and never picks a "typical"/modal schedule. All arithmetic (`gross = end − start`) and all aggregation (the per-band mode over schools) are done in Python (`aggregate.py`). This keeps the distribution visible and auditable, and keeps the LLM doing the one thing it's good at (reading) and code doing the one thing it's reliable at (counting). *(Decided 2026-06-21; a prior design let models return pre-aggregated minutes and a triage prompt even asked the model to pick the typical schedule — both removed.)*
- **Consensus is on the per-school (start_time, end_time) PAIR**, evaluated per school within ±15 min, cross-family — NOT on the computed minutes or the band rollup. Two models "agreeing on 380 minutes" via *different* start/end pairs is a false agreement; agreeing on `08:00–14:20` for *this school* is a real one.
- **Consensus must be cross-family.** Agreement only counts between different model families — same-family agreement (two Gemini, two Mistral) is weak evidence (correlated blind spots). Family buckets: **Google** (Flash, Flash-Lite) · **Mistral** (Small 24B, Large 2512) · **DeepSeek** (V3.2) · **Qwen** (235B-2507).
- **The band value is the deterministic MODE** (exact most-common gross over consensus schools; genuine tie between distinct values → arithmetic mean). The mode is the *exact* most-common value, not a tolerance-cluster mean (a cluster-mean bug once turned {380×26, 390×2, 345×1} into 381 instead of 380).
- **Disagreements go to a JUDGE that re-reads the captured page** + applies a plausibility gate (school day ~240–**510** min — the upper bound raised from 480 because real full days run to ~8.5h, e.g. LA at 500; start ~6:30–9:30), not to more voters — a judge can catch a *shared* trio error that voting cannot. Judge is a distinct family from the voters.
- **~3 diverse voters + 1 judge** is the sweet spot; do not call all 6. **Log which models formed the consensus** for each school (DB change — see below) to audit for monoculture.
- **Run the council per *school*, not per district** (concatenating schools is the over-stuffing failure); cheap path per school, escalate only on disagreement; aggregate across schools in stage 8.

**The two candidate configs (A/B — the decision is the measured escalation rate):**

| | **Path 1 — cheap trio** | **Path 2 — accuracy pair** |
|---|---|---|
| Voters | Mistral Small 24B + Gemini 2.5 Flash-Lite + Qwen3-235B-2507 | Mistral Large 2512 + Gemini 2.5 Flash |
| Families in accept-path | 3 | 2 |
| Judge (if needed) | DeepSeek V3.2 (4th family) | **DeepSeek V3.2** (3rd family; preferred over Qwen — higher accuracy 66.2% vs 58.1%) |
| Base cost / school | ~$0.0013 | ~$0.0043 (~3×) |
| Voter accuracy (full-41) | 63.5 / 60.8 / 58.1% | 67.6 / 68.9% |
| Expected escalation | higher (weaker voters disagree more on hard inputs) | lower (best models agree-and-right more often) |
| Judge role | tiebreak on a split (1–1–1 or 2–1 cross-family) | **decider on every disagreement** (a 2-voter pair has no internal majority → judge breaks every 1–1 tie) |

**Accept rule (both paths):** accept when the required cross-family voters agree within ±15 min; otherwise invoke the judge; if the judge's value fails the plausibility gate or no defensible value emerges → **statutory fallback** (small/single-school districts where no alternate school exists get flagged for human review instead).

**Why not decided yet:** the winner hinges on the **escalation rate** on *real captured inputs*, which can't be reasoned out — it depends on how often the cheap trio actually converges. That measurement is **blocked on building per-school extract→aggregate** (Open decision #2). Until then, both configs stand as candidates.

---

## Edge cases / anti-bot (salvaged, still in force)

| Scenario | Detection | Action |
|---|---|---|
| Google Drive URL | `drive.google.com` / `docs.google.com` | 3-tier: direct download → Playwright preview → manual flag |
| Direct PDF link | URL ends `.pdf` | HTTP download → Crawlee fallback |
| Auth/login wall | login form or 401/403 | mark `blocked`, flag manual |
| Cloudflare/WAF | challenge page | mark `blocked`, **ONE-attempt rule** (Rule #3), flag manual |
| Site unreachable | timeout/error | mark `unreachable`, flag manual |

A managed-scraping fallback (Zyte/Firecrawl, budget-bounded) is available for JS-heavy/blocked sites if yield demands it; not yet wired.

---

## Cost (measured, 2026-06-20)

Per extraction call (one captured document), from OpenRouter activity logs — see `EXTRACTION_BENCHMARK_FINDINGS.md` Update 4:

| Model | $ / call | | Model | $ / call |
|---|---:|---|---|---:|
| Mistral Small 24B | $0.00022 | | Gemini 2.5 Flash | ~$0.00168 |
| Gemini 2.5 Flash-Lite | $0.00050 | | Mistral Large 2512 | $0.00265 |
| Qwen3-235B-2507 | $0.00060 | | *(removed)* Grok 4.3 | $0.00680 |
| DeepSeek V3.2 | $0.00102 | | *(removed)* Qwen3.7-Max | $0.01571 |

District cost = (schools sampled) × (per-call) × (council size). A 3-model non-reasoning council ≈ $0.0029/call → **~$0.15 for a 50-school district, ~$1 for a 340-school Broward.** **Money is not the constraint** — input quality and downstream human-QC time are. Discovery/search/capture are local or fractions of a cent.

---

## Open decisions (not yet built or pinned)

1. **Per-school sampling policy — queue-time half resolved 2026-06-22; extraction-time half still open.** Queue-time (cap=12/band, seeded sample, most-constrained-first overlap minimization) is built and validated — see `METHODOLOGY.md` "Bell Schedule Sampling Policy" (the *why*) + `STAGE1_QUEUE_DESIGN_2026-06.md` §3 (the Stage-1 implementation). Still open: the *extraction-time* mode-stability early-exit (does Stage 7/8 need to process all 12 queued schools, or can it stop once the modal value stabilizes?) — blocked on Open decision #2 (per-school extract→aggregate not yet built).
2. **Per-school extract → modal-aggregate** — **not yet built or tested.** The end-to-end test to date used naive *concatenated* district pages and scored ~50% vs ~100% on clean curated files; the fix is per-school extraction then aggregation. This is the #1 build item.
3. **Council membership + decision rule** — which 2–3 of the 6, agreement tolerance (±15 min), tiebreak, what routes to human QC.
4. **Discovery precision filter** — URL-keyword weighting / time-grid detection to close the 71%↔90% gap (deferred until we see scaled yield).
5. **The 4 discovery misses** (Orange FL, Baldwin AL, Springdale AR, Champlain Valley VT) — deferred.
6. **School-name matching in per-school consensus** — `aggregate.consensus_school_facts` groups a school across models by normalized name; when spellings/OCR differ ("West Valley HS" vs "W. Valley", garbled letters), a school fails to reach cross-family agreement and is held out as `unresolved` (correctly excluded from the band mode, not wrong-counted). Observed on Fairbanks (West Valley) and as the bulk of Orange FL's 102 unresolved. **WATCH-ITEM, do NOT loosen yet** — a looser matcher risks *merging genuinely different schools* (a worse error than holding one out). Only revisit if unresolved rates are demonstrably blocking GT/coverage; first confirm the pattern (are the held-out times actually fine under different names?) before touching the matcher.
7. **Wave-cascade vs. always-run-both, and which/how-many search providers.** Stage 2's first live run on `batch_00001` (2026-06-23) split exactly 6/12 districts Wave-1-only vs. 6/12 needing Wave 2 for every school, with zero mixed cases — see the diagram decision log. Open question raised by the user: once Capture/Extraction exist and we can judge candidate-page *quality* (not just presence), does it make sense to run both providers unconditionally for every district rather than stopping at the first wave that returns anything? **Partially resolved 2026-06-26 — the provider set is now an explicitly *extensible* layer** (Claude CLI WebSearch = Wave 1, OpenRouter `gpt-4o-mini-search` = Wave 2) **designed so new providers slot in** behind the common candidate-URL contract: a dedicated search/scrape API (Bright Data, the Brave Search API), or a new cheap web-search model on OpenRouter, can be added or reordered without touching gating/flatten/dedup. Still open: *how many* to run and *when* (cascade vs. always-run), to be tuned once page-quality signal exists. Related sub-option surfaced the same session: Gemini's `GoogleSearch` grounding tool was dropped for lacking a domain-restriction *parameter* (only `exclude_domains`) — but a literal `site:<domain>` token appended to the query text itself (the same trick a human typing into google.com uses) might achieve scoping without needing the parameter at all, worth a cheap test if Gemini grounding is ever revisited. **Deliberately deferred** — "we'll see how far we get with what we've got" — revisit after Capture gives us page-quality signal, not before.

8. **`CMS_HOSTS` list scope — RESOLVED 2026-06-24 (option a, with a governance rule).** Stage 3 fingerprinting's `resource_hosts` data revealed the dominant K-12 platforms in the first 12 districts are **SharpSchool** (51 records), **Apptegy/Thrillshare** (~24), and **Educational Networks** (25) — none in the original 8-entry `CMS_HOSTS`, so `cms_hint` was `null` across all 150. **Decision: grow `CMS_HOSTS`** (chosen over giving fingerprinting its own separate list), adding `sharpschool.com` / `apptegy.net` / `thrillshare.com` / `educationalnetworks.net` to both `discover.py` and `capture_discovery.mjs` (hand-synced). This is the load-bearing path — it also makes Stage 2's `gate()` *keep* slug-matched URLs on those hosts that it previously rejected as off-district, closing a possible discovery-recall gap. **Governance rule, going forward (the user's standing instruction): every `CMS_HOSTS` addition is a human-in-the-loop decision, never automated** — each entry must be a vendor that *specifically serves school districts*, never a general hosting/CDN provider. Concretely excluded for exactly this reason: `amazonaws.com`, despite `core-docs.s3.amazonaws.com` appearing in the real data (S3 hosts everything; whitelisting it would invite pollution). Regression test added (`TestDiscoveryGate`). **This was also the first instance of the fingerprint-driven refinement loop the user wants to run continuously — and an explicit topic to carry into Stage 5 design.** The existing 12 districts' `cms_hint` was then re-derived in place via `capture_discovery.mjs recompute-cms-hint` — a **pure recompute over the already-stored `resource_hosts`, no browser, no re-capture** (the "refine retroactively over raw facts" design paying off concretely): 107/150 records updated, now **SharpSchool 59 / Educational Networks 25 / Apptegy 19 / Thrillshare 4 / null 43**. That `recompute-cms-hint` mode is the standing mechanism for applying any future human-approved `CMS_HOSTS` change to already-captured data cheaply.

### Reader-modality head-to-head (2026-06-21) — THREE input classes, format-route the reader
Two tests. **CORRECTION:** an initial test wrongly concluded "`page.pdf()` is useless" — but that test was **biased by construction** (it sampled only pages with innerText≈0, i.e. already-image-based pages, so of course PDF inherited the emptiness). A corrected test on **text-RICH** pages overturns it. Net finding: there are **three input classes**, each with a different best reader:

1. **Clean single-column text** (e.g. Pueblo HS) — `innerText` and `pdftotext -layout` tie; cheap text reader is fine.
2. **CSS multi-column schedules** (e.g. Washoe McQueen — three schedule variants side-by-side) — **`innerText` FLATTENS the columns into a vertical list (loses which column a row belongs to), but Playwright `page.pdf()` + `pdftotext -layout` PRESERVES the column alignment.** This is a real, cheap (no-vision) win — validates the "Save as PDF keeps structure" intuition. *(NB: the right PDF reader here is `pdftotext -layout`, NOT `pdfplumber` — these are CSS-laid-out pages with no ruling-line `<table>` borders, so pdfplumber pulls nav chrome, not the schedule. Caveat: print-CSS can reflow/clip on some hub pages and HURT — so route, don't blanket-apply.)*
3. **Image/canvas-rendered schedules** (e.g. Mat-Su whs/pjm — innerText, pdftotext, pdfplumber, AND screenshot-OCR all 0) — **only VISION reads these** (Gemini Flash got `Wasilla HS 08:45–14:15`, `Palmer Jr 08:00–14:30`). 107 zero-innerText candidates exist in the discovery set; vision isn't competing with text here, it's the only reader that works.

**Implications:** (a) **DO capture `page.pdf()`** (Chromium print path ≈ Chrome "Save as PDF") in addition to innerText + screenshot — it cheaply rescues CSS-multi-column structure that innerText destroys, keeping those pages on the *cheap text council* instead of escalating to vision. (b) **Vision is a first-class reader for the image class** (escalate when text/pdftotext return empty/garbled — cost-gated per the user's logic). (c) The "vision underperformed" bake-off was on clean-text inputs and does NOT apply to the image class. (d) This is **format-routing** (cheap text → pdftotext-layout-on-PDF → vision), not a blanket switch. *(All from 2-3 page spikes — directional; confirm at scale against the new GT before wiring.)*

#### Reader-routing spec (formalized 2026-06-21) — try the cheapest reader that works, escalate only on failure
The router is **outcome-based**, not format-based: it runs the cheap reader, checks whether the output is *usable*, and escalates only when it isn't. (Format only *hints* the starting tier; the success check decides escalation. Tiers are fallbacks, not parallel — vision is never paid for if text already worked.)

```
TIER 1 — plain TEXT (cheapest):  send TEXT to the cheap council
  WHEN innerText OR pdftotext yields usable schedule content
       (≥1 plausible start/end time, or an explicit "starts at hh:mm … ends at hh:mm" phrase)
  COVERS single-column period schedules; paragraph prose

TIER 2 — PDF with structure (still cheap, no vision):  send the PDF (read via `pdftotext -layout`) to the cheap council
  WHEN text is present but its STRUCTURE was lost (multi-column flattened) AND
       page.pdf()/source-PDF + `pdftotext -layout` recovers the column alignment
  COVERS CSS multi-column tables; side-by-side schedule variants
  (reader = pdftotext -layout, NOT pdfplumber, for CSS-laid-out pages)

TIER 2.5 — OCR an image (cheap, between text and vision):  OCR the image, send recovered TEXT to the cheap council
  WHEN the source is a raster image (.png/.jpg/.webp/.gif — NO text layer) but OCR recovers usable content
  COVERS clean image fliers (e.g. Cleveland .webp: tesseract got 176 times, 93 schools cleanly)

TIER 3 — VISION (most expensive, last resort):  send the SCREENSHOT/image to the vision council
  WHEN OCR also fails or scrambles (styled/low-contrast text, e.g. Mat-Su; or multi-column scans, e.g. New Haven CT)
  COVERS styled-graphic text OCR can't read; multi-column scans OCR scrambles
```
*(Note: a raster image — `.png`/`.jpg`/`.webp`/`.gif` — has **no text layer** (unlike a PDF), so it always needs OCR or vision. But "image" is NOT monolithic: a **clean image flier OCRs fine and cheaply** (Cleveland .webp), while **styled/low-contrast** images (Mat-Su) or **multi-column scans** (New Haven CT) defeat OCR → vision. So the Tier-3 trigger is "**did OCR recover usable content**," not "is it an image.")

**Escalation gates:**
- **Tier 2→3 (well-defined):** "no usable content" = count plausible times in all text outputs; below threshold → vision.
- **Tier 1→2 (OPEN — not yet a buildable trigger):** detecting *"text present but structure lost"* is the hard, unsolved part. Washoe's page had 122 innerText times yet the columns were flattened/ambiguous — so the trigger is **not** "few times." Candidate signals (undecided): low band-coverage despite many times; inability to bind times→bands; or the council itself returning low confidence. **Left open deliberately — define before wiring Tier 2.**

#### Broward (2026-06-21) — multi-PAGE column-snake is a SEPARATE failure axis from multi-column
Broward (1200180, a `hub` district) captured **elementary (111 schools, gross 360) and middle (10, 400) accurately — but ZERO high schools** (proposal has no high band). Diagnosis (user-observed): the schedule is a **multi-page, multi-column continuous flow** — Page1 cols1&2 → cols3&4 → Page2 cols1&2 → … — with the elem/middle/high section breaks living *inside* that snaking stream, not as clean per-band blocks. When `pdftotext -layout` / innerText linearizes a multi-*page* multi-*column* doc, reading order tangles across page boundaries, and the **tail of the stream (high schools) degrades most** → high dropped while elementary (front of stream) came through clean. **CONFIRMED in source:** the 3-page PDF has 132 "elementary", 37 "middle", 28 "high" mentions with clean times — high schools ARE present (`Anderson Boyd H. High 7:40–2:40`, `Coconut Creek High 6:50–1:35`), so they were **dropped from a present, readable signal**, not absent. The layout puts **two schools side-by-side per row** (e.g. `Tropical Elementary 8:25–2:25 │ Anderson Boyd H. High 7:40–2:40`) — elementary and high interleaved across column-pairs; extraction captured the left pair (elementary) and lost most of the right pair (middle/high).
- **Two distinct axes:** PDF capture **solved multi-COLUMN** (the captured schools were accurate — strong evidence for `page.pdf()`). Multi-**PAGE continuous flow** is a *separate, unsolved* axis; PDF/pdftotext handles columns-on-one-page but not columns-snaking-across-pages.
- **Strong unused signal — band is encoded in the school NAME** (Broward names schools "… High School" / "… Middle"). Extraction relied on positional grouping and missed this. **FIX CANDIDATE: use band-from-school-name as a disambiguation/recovery signal** in extraction+aggregation (we already have `school_sampling.bands_for` for NCES rosters; the *council extraction* should also lean on the name signal, not just page structure).
- **Topology routing implication (reinforces REQ-057):** per-school queueing **sidesteps** this for `per_school` districts (each HS discovered/captured individually). But Broward is `hub` — per-school queueing can't save it; the hub path needs the **name signal and/or layout-aware reading** (vision handles multi-page layout natively). So hub-vs-per_school routing sends these down different solution paths.

#### Orange (2026-06-21) — INPUT TRUNCATION (`MAX_TEXT_LEN`), a different bug than Broward
Orange (1201440, `hub`) lost the second half of its middle schools (all → unresolved) and **all page-4 high schools**. Root cause is **our own input cap, not the models and not an API/context limit**: `gt_propose`/`extractors` truncate the document to `MAX_TEXT_LEN = 12000` chars (`txt[:MAX_TEXT_LEN]`). Orange's source is **16,618 chars**; the consensus "fell apart at Howard Middle" because **"Howard" sits at char 11,890 — right at the 12,000 cutoff.** Everything after (rest of middle + all high) was **never sent to the models** — not mis-read, *unsent*.
- **Distinct from Broward:** Broward's high schools were *inside* the 12K window but lost to column-snaking; Orange's were *cut off entirely* by the char cap. Different fixes.
- **FIX (deterministic, cheap): chunk large inputs, don't truncate.** Since we aggregate per-school anyway, feed a multi-page hub in page/section chunks and union the per-school facts — loses nothing, removes the silent tail-drop. (Raising `MAX_TEXT_LEN` is a stopgap; chunking is the real fix and also helps Broward by keeping per-page column structure local.) **`MAX_TEXT_LEN` truncation must not silently drop schedule content — any source exceeding the cap must be chunked + aggregated, never sliced.**

### Deferred hard input cases (come back to — expensive, low priority for now)
These source formats are *known to contain schedules* but are costly to extract reliably; explicitly out of scope for the current build, recorded so they aren't forgotten:
- **Bell schedules buried in Parent/Student Handbooks** — long multi-topic PDFs where the schedule is a few lines among dozens of pages. Needs locating the right page/section before extraction (a retrieval step our current "the captured page IS the schedule" assumption skips). Several manually-collected sources turned out to be this.
- **Expanding/accordion hub pages** (e.g. Anchorage `School Start List` — collapsible sections that only render fully on interaction). The tiered capture's screenshot misses collapsed content; would need scripted expansion before capture. Excluded from the curated GT for this reason.
- **Image-only schedules requiring layout reasoning** (rotated tables, multi-column posters) beyond what OCR linearizes cleanly.
General principle: these are **retrieval/rendering** problems upstream of extraction, not model-quality problems — defer until the core per-school path is proven on clean inputs.

- **Multi-column layouts that OCR linearizes wrong (NOTE — confidence signal, not solved).** A page with side-by-side school|times column *pairs* (e.g. New Haven CT 0902790: cols 1&2 = school/time, cols 3&4 = school/time) is read by `tesseract` as separated *runs* — all names lumped together, times elsewhere — destroying the row→school binding. Models then *guess* the school↔time pairing from the scrambled stream and **make the SAME mis-pairing** (Col-3 names paired with Col-2 times; Col-1 names dropped entirely). Critically, this produces a **FALSE consensus**: the council agrees not because each model independently read it right, but because the shared bad input misled them identically — and "confirmed" values can be right only by coincidence (e.g. Col-2 times happening to equal Col-4 times where the district uses uniform hours). **Implication: cross-model agreement on a known multi-column/garbled-OCR source is weak evidence — it must DOWN-weight confidence, not auto-accept** (when reading OCR *text*).
**RESOLVED by vision (spike 2026-06-21):** sending the *rendered page PNG* (not OCR text) to **Gemini 2.5 Flash + Mistral Large 2512 in vision mode** read New Haven CT's 4-column layout **spatially correct** — recovered the Column-1 names OCR-text dropped, paired each school with its own times, and the two cross-family models *agreed on the correct reads* (real consensus, since the input was no longer scrambled). Flash 59 / Mistral 56 schedules vs the broken OCR-text result. **Takeaway: for multi-column / scanned sources, vision-read the rendered PNG — it's a working fix we already have (the harness `extract(images=[...])` + OpenRouter `image_url` path), not deferred research.** Vision defeats the shared-bad-input false-consensus because a legible image is no longer a shared *bad* input. (Caveat: vision underperformed in the earlier text-vs-vision bake-off on *clean* inputs — so use vision as a **format-routed reader for image/scan/multi-column sources**, not a blanket replacement for clean digital text.)

**Now handled (2026-06-21): scanned / image-only PDFs (no text layer).** A PDF that is a printed-then-scanned page (JBIG2/CCITT raster, empty `pdffonts`, `pdftotext`→~0 chars) cannot be read by `pdftotext` *or* by `tesseract` directly (tesseract needs a raster image, not a PDF). Fix: the OCR fallback **rasterizes each PDF page to PNG via `pdftoppm -r 200` first, then OCRs** (`gt_propose._ocr_pdf`). Recovered New Haven CT (0902790) from `no_readable_times` to a full 3-band per-school list (125 time patterns). Note: OCR of scans is noisier → more `unresolved` schools from garbled school names (matching misses), but resolved schools still drive solid band values. The same rasterize-then-OCR step must exist anywhere the pipeline OCRs PDFs.

---

## Human-QC strategy (the binding constraint)

Two independent extractors disagree on a large share of districts; at <1 hr/week, human review can't drain a 20K queue. Resolution: **decouple coverage from verification** — auto-accept on council agreement, statutory-fallback the uncertain tail (labeled), and **spend human QC enrollment-weighted** (the top few hundred districts dominate every published LCT number; ~500 × 2 min ≈ feasible). See `INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md` for the full constraint analysis.

---

## Key files

| Concern | File |
|---|---|
| **Queue (Stage 1): exclusion filters, stratified sampling, batch writer** | `infrastructure/acquisition/stage1_queue/queue_batch.py` |
| **NCES classification: per-school bands, LEA claimed span, charter lookup** | `infrastructure/acquisition/common/school_sampling.py` |
| **Cross-stage district status registry (all 9 stages)** — *migrating to a Postgres event log (governance DB), 2026-06-26* | `infrastructure/acquisition/common/district_status.py` |
| **Stage 1 output / status registry schema references** | `data/acquisition/queue/batch.example.json`, `data/acquisition/status/district_status.example.json` |
| **CTC/shared-service classification backfill (Rule 6)** | `infrastructure/database/migrations/apply_ctc_classification.py` |
| Archived: pre-redesign stratified batch picker (superseded by `queue_batch.py`) | `data/archive/training_batch_py-superseded-20260622/training_batch.py` |
| **Discovery (Stage 2): deterministic half, built + tested 2026-06-23** | `infrastructure/acquisition/stage2_discover/discover_stage2.py` |
| **Discovery (Stage 2): orchestration skill (Wave 1 subagent dispatch)** | `.claude/skills/stage2-discover/SKILL.md` |
| Discovery utility functions only (manifest-reading/roster parts superseded) | `infrastructure/acquisition/common/discover.py` |
| Archived 2026-06-24: GT-manifest-era per-school discovery (bypassed Stage 1's batch) | `data/archive/gt-benchmark-era-tools-superseded-20260624/per_school_run.py` |
| Superseded skills (built on the above, pre-Stage-1 design) | `.claude/skills/per-school-acquire/`, `.claude/skills/per-school-acquire-training/` |
| **Capture (Stage 3): built + run live 2026-06-23, 150/150 captured** | `infrastructure/scraper/capture_discovery.mjs` (active) |
| **Capture (Stage 3): orchestration (reconcile/outcome-rollup/registry)** | `infrastructure/acquisition/stage3_capture/capture_stage3.py` |
| Drive Tier 1 export-URL handling (built, tested) | `infrastructure/scraper/capture_drive.mjs` |
| Hosting/CMS fingerprint helpers + backfill mode (built, tested, run live 2026-06-24) | `infrastructure/scraper/capture_discovery.mjs`, `capture_fingerprint.test.mjs` |
| Drive Tier 2 (OAuth) — deliberately deferred, not built | REQ-078 |
| **Local processing (Stage 4): built + run live 2026-06-23, 150/150 records processed** | `infrastructure/acquisition/stage4_process/process_stage4.py` |
| **Stage 4 PDF-tool spike (real data, 150 PDFs) — kept/dropped tool decision evidence** | `data/benchmark_results/stage4_pdf_tool_spike/run_spike.py`, `summary.jsonl` |
| Existing pdftotext→OCR fallback pattern Stage 4 ports from (`_ocr_pdf`, `PDF_MIN_TEXT_CHARS`) — archived 2026-06-24, no live code imports either | `data/archive/gt-benchmark-era-tools-superseded-20260624/reading.py`, `.../gt_propose.py` |
| Modal dismissal + page.pdf() options ported in (verified pure-Playwright, no dead-architecture coupling) | `infrastructure/scraper/src/capturer.ts` |
| Superseded: abandoned Jan-2026 blind-site-mapping (do not revive) | `infrastructure/scraper/src/mapper.ts` |
| Stale: coarse relevance filter — pre-Stage-1-3-redesign, reads the old `data/acquisition/discovery/` layout and old tool names (perplexity/openrouter/claude); not yet ported to the new `captures.json` shape | `infrastructure/acquisition/stage5_filter/relevance.py` |
| **Stage 5: CP-B review app + deterministic signals/tier/topology/clustering/harvest/de-chrome ingest** — *app → `process_governance/` (governance app); `build_signals.py` → `stage5_filter/`; DB → Postgres governance DB (2026-06-26)* | `infrastructure/acquisition/stage5_filter/build_signals.py`, `server.py` |
| **Stage 5: measurement harness + tuning ledger + frontier search (config-vs-labels scorecard, fingerprinted)** | `infrastructure/acquisition/stage5_filter/{harness,tuning_ledger,frontier}.py` |
| **Learning-loop: config-as-data layer (per-entry provenance) + loader + paths/DATA_ROOT** | `infrastructure/acquisition/common/{config_loader,paths}.py`, `infrastructure/acquisition/common/config/*.json` |
| **Stage 3 de-chrome: segmentChrome + backfill-segments (REQ-091, built+measured)** | `infrastructure/scraper/capture_discovery.mjs`, `config/de_chrome_landmarks.json` |
| **Governance app, state model & Postgres (architecture authority, 2026-06-26)** | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` |
| **NEXT: operational Stage 5 filter → `filtered.json` (DB-backed release export, not yet built)** | see `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md` §9 sequencing + `STAGE5_FILTER_DESIGN_2026-06.md` → "Path to filtered.json" |
| Discovery→extraction loop test (archived) | `data/archive/gt-benchmark-*/dead_benchmark_scripts/extract_test.py` |
| Extraction harness + providers — archived 2026-06-24 (GT-benchmark era, no live code imports either) | `data/archive/gt-benchmark-era-tools-superseded-20260624/{extractors,reading,score_minutes,council_extract}.py` |
| Google Drive handler | `infrastructure/scripts/enrich/google_drive_handler.py` |
| **Aggregation (Stage 8): mode-then-mean logic, pure logic/no I/O** | `infrastructure/acquisition/stage8_aggregate/aggregate.py` |
| Per-school schema + MODE aggregation | `school_schedules` / `bell_schedules` (migration 016), REQ-042 |
| LCT precedence (bell → statutory → 360) | `infrastructure/scripts/analyze/calculate_lct_variants.py::get_instructional_minutes` |
| Requirements | REQ-024, 032, 042, 043–053 |
