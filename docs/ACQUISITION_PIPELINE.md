# Bell Schedule Acquisition Pipeline

**Status:** Stage 1 (Queue) designed and built end-to-end, through Checkpoint A. Stages 2-9 design validated (discovery + extraction); per-school council rules still to build.
**Last updated:** 2026-06-22.
**Companions:** `docs/diagrams/acquisition_pipeline_flow.md` (Mermaid visual reference, built stage-by-stage alongside this doc), `docs/EXTRACTION_BENCHMARK_FINDINGS.md` (model leaderboard + measured costs), `docs/technical-notes/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md` (full learnings), `docs/INSTRUCTIONAL_TIME_HARVEST.md` (why SEA central data is a dead end), `docs/METHODOLOGY.md` (Rules 6 & 7 — CTC and grade-span-integrity exclusions referenced below). The strategy/options report that preceded this is `docs/INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md` (now a pointer here).

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

### 1 · Queue — designed and built 2026-06-22

Builds a batch of districts (default 12) plus, per district, the per-band school lists to target — the structured input Stage 2 (Discover) and Stage 3 (Capture) consume. Source data: NCES `ccd_lea_029_2425` (district directory + claimed grade span) and `ccd_sch_029_2425` (school directory + per-school grade span), cross-referenced against the DB (`enrollment_by_grade`, `districts.is_shared_service_entity`). Code: `infrastructure/acquisition/discovery/queue_batch.py`, reusing `school_sampling.py` (extended) and the new `district_status.py` registry.

**Pre-queue exclusion filters** (applied in this order to build the eligible pool; all are *live filters recomputed every run*, never a persisted exclusion list — a future policy change lets a district back in for free, no cleanup needed):

1. **Not operating** — LEA-level `SY_STATUS_TEXT != "Open"` (closed/inactive/future agencies).
2. **CTC / shared-service entity** — `districts.is_shared_service_entity = True`. Backfilled 2026-06-22 via `infrastructure/database/migrations/apply_ctc_classification.py` (600 districts; name-pattern match on career/technical/vocational/jted/cted **OR** NCES `LEA_TYPE_TEXT` in `{Specialized public school district, Service agency, State operated agency}`, disambiguated from charter LEAs via `LEA_TYPE_TEXT`). Expanded from an initial name-only pass of 152 after Pima County JTED slipped through into a live batch (acronym name, didn't literally spell "technical") — see `METHODOLOGY.md` Rule 6 for the full identification logic and the accepted trade-off (the blanket `LEA_TYPE_TEXT` buckets also catch some legitimate full-time special-purpose state schools, e.g. deaf/blind institutes, that aren't really CTCs). This exclusion was schema-only and silently a no-op in every LCT calculation until 2026-06-22.
3. **Grade-span integrity (Rule 7)** — exclude **and** flag when the LEA-level claimed span (`bands_for()` applied to the district's overall `GSLO`/`GSHI`) includes a band that the school-level union (`bands_for()` applied per-school, via `ccd_sch_029`) covers with **zero** schools. A K-8-only district legitimately has no high band (not claimed, not a gap); a K-12 district with schools spanning only K-5 and 9-12 (nothing covering 6-8) is internally inconsistent and untrustworthy to sample from. See `METHODOLOGY.md` Rule 7. **Impact: ~985 districts excluded** (run 2026-06-22, after the school-level filtering fix below — roughly doubled from an initial 485, since districts whose only "covering" school in a band was a CTC/alternative/special-ed/standalone-preschool school now correctly show that band as uncovered rather than falsely covered).
4. **Already attempted** — any `district_id` present in the `district_status.json` registry (`data/acquisition/status/`, see below) is excluded, **regardless of prior outcome** (success or failure). Don't resample a district that already failed; failures get triaged as a separate, deliberate process, not silently retried.

A district must also have non-null, non-zero `enrollment_k12` (most recent year with usable data) to participate — enrollment is the primary stratification axis (next).

**Stratified sampling** — enrollment is the priority axis, state is a secondary tiebreak (not an independent axis: staff count and school count were considered and dropped, too collinear with enrollment to buy independent coverage beyond what enrollment alone provides):

1. Sort the current eligible pool by `enrollment_k12` and split into 4 equal-**count** quartiles (not equal-value-range — NCES enrollment is heavily right-skewed, so equal-range buckets would be wildly unequal in population).
2. Target 3 districts per quartile (4 × 3 = 12) — same fixed-mix-per-stratum shape as the retired `training_batch.py` (which used 3 school-count tiers instead of enrollment quartiles).
3. Each individual pick (not just each bucket) prefers a state not yet used in this batch, seeded-shuffled otherwise — `seed = batch_id`.
4. If a quartile runs short, top up from the overall remaining pool (which is disproportionately the adjacent quartiles, since exhausted buckets contribute nothing) until the batch reaches its target size or the pool is exhausted.

**Per-band school selection** — per selected district, target up to 12 schools per band (elementary/middle/high) from the school-level NCES roster (never LEA-level — LEA-level grade span has no per-school granularity, see Rule 7 above), full census if a band has ≤12 candidates:

- **School-level filtering (added 2026-06-22, found by human review of a real batch — CP-A doing exactly its job):** `school_index()` only admits NCES `SCH_TYPE_TEXT = "Regular School"` and excludes standalone preschool/early-childhood schools (`GSHI in ("PK", "KG")`, no grade-1+). Surfaced by real schools in `batch_00001`: **Olympic Peninsula HomeConnection** (`SCH_TYPE_TEXT = "Alternative School"` — a homeschool-umbrella program, near-certain bell-schedule-collection failure), **Lake Preschool** (`GSLO=GSHI=PK`, no normal academic day to capture), **Jackson County Vocational Center** (`SCH_TYPE_TEXT = "Career and Technical School"` — a school-level CTC inside an otherwise-normal district, invisible to the LEA-level Rule 6 exclusion since the surrounding LEA isn't a CTC), and **Clinton County Early Childhood Center** (`GSLO=PK, GSHI=KG` — the `GSHI=="PK"` rule alone missed this, extended to also catch `GSHI=="KG"`). NCES's `SCH_TYPE_TEXT` is a structural field (Regular / Special Education / Career and Technical / Alternative), not a name heuristic — deliberately not name-matched, since plausible normal-school names ("Mountain Home Elementary") would collide. **Special Education School is excluded too**, accepted for now as a known, deferred gap (the project's SPED staffing work already flags this as a category needing dedicated attention later, not a clean fit for this filter's rationale).
- **LEVEL-primary classification + recursive grade-range grouping (added 2026-06-22, refined same day after a user-built reference table of recognized grade-band shapes — see decision log in `docs/diagrams/acquisition_pipeline_flow.md`):** band membership is no longer pure grade-range overlap. `school_index()` assigns a school to exactly one band immediately when NCES `LEVEL` is a clean `Elementary`/`Middle`/`High` — full stop, regardless of grade-range overlap with an adjacent band ("our primary tool is to rely on LEVEL before any of this"). For whatever LEVEL leaves unresolved (a band with zero clean candidates, or a school whose own LEVEL is ambiguous — `Other`/`Secondary`/`Not reported`/`Ungraded`/blank), `recursive_band_groups()` groups the district's distinct grade spans by structural position, *when they form a clean ascending, non-overlapping partition*: consecutive leading segments with top grade ≤6 collapse into elementary (handles 1, 2, or 3+ elementary sub-segments — lower/upper elementary, primary/intermediate splits); what remains is middle alone, middle+high merged (no separate middle identity exists at all), or middle alone followed by one-or-more high segments (lower-high/upper-high splits, e.g. a 9th-grade campus + main high school). If the spans *don't* form a clean partition (genuinely different, overlapping/redundant spans — not just multiple buildings sharing one identical span), fall back to the original any-overlap rescue, unvalidated for that messier shape. Two distinct real failure modes drove building this: **dilution** — Fayette County IN's real `Connersville Middle School` was getting diluted 6-to-1 by 5 unrelated K-6 elementary schools that merely clipped the boundary grade; **false-gap risk** — Calhan CO and Breathitt County KY have *no* school labeled "Middle" at all, so a strict LEVEL-only rule would wrongly trip Rule 7. Why not enumerate every district's grade-split convention (K-4/5-8, K-6/7-9, K-8, etc.) by hand? Because NCES has already done that per-school classification for us via `LEVEL` where it applies cleanly, and the recursive structural rule covers the rest without needing a lookup table at all.
- **Why "exactly N schools" is the wrong scoping question, found by profiling the full corpus:** an earlier version of this fix scoped itself to "exactly 2 schools" specifically to avoid touching Breathitt County KY/Chama Valley NM/Northern Tioga PA (3+ schools each). Profiling all 17,265 eligible districts against a reference table of recognized grade-band shapes showed this was the wrong dividing line. Northern Tioga's 3 elementaries share an *identical* `KG-06` span and its 2 secondaries share an *identical* `07-12` span — collapsed to distinct spans, that's the exact same 2-segment shape as Jasper Co. MO, and it now gets the same fix (previously it did not — a real correction, not a refinement). Breathitt County and Chama Valley are genuinely different: their elementary spans are *not* identical and one subsumes another (e.g. `PK-06` entirely contains `PK-02` and `03-06`) — not a clean partition, so they correctly stay on the conservative fallback. The dividing line is "does this district's spans form a clean partition," answerable directly from the data — not school count.
- **Grade-13 bug fix (found in the same review):** `bands_for()` had no entry for NCES grade code "13" (a real, sanctioned code some states use for a continuation/extra-year high school program), so any school coded e.g. `GSLO=09/GSHI=13` silently classified into **zero** bands. This wasn't a hypothetical — it surfaced because Jackson County MS's three real comprehensive high schools (East Central, St. Martin, Vancleave, all `09-13`) were invisible to band selection, leaving the Vocational Center as the *only* visible high-band candidate, which is why `band_processing_order` put "high" first (most-constrained = fewest candidates) in a way that looked wrong until traced back. Fixed by adding grade 13 to `GRADE_ORD` as part of the high band. **222 open schools nationally use `GSHI=13`** — not a one-district issue.
- **Cross-band overlap minimization:** a school spanning multiple bands (a genuine K-8, K-12, or "Middle/High"-combined school — what's left *after* LEVEL-primary classification above removes the false dilution cases) can satisfy more than one band's `bands_for()` classification, so naive independent-per-band sampling can draw the *same* school into multiple bands' selections even when enough distinct single-band schools exist. Fixed by processing a district's bands **most-constrained-first** (ascending by candidate-pool size): each band samples from schools not yet claimed by an earlier-processed band first, only falling back to reuse an already-claimed school if the unclaimed pool can't fill the cap. Validated on real data (Fairbanks AK, 0200600): independent sampling produced 3 overlapping schools between elementary and middle; most-constrained-first reduced this to 1 unavoidable overlap (forced because the high band's full 9-school census left middle only 11 unclaimed against its cap of 12).
- When a band's candidate pool exceeds the cap, the 12 (or fewer, after exclusion) are a **seeded random sample** — `seed = f"{batch_id}:{district_id}:{band}"`. No signal exists yet at queue-time for which schools are "better" to sample, so an unbiased subsample is the most defensible default (same logic as the corpus-wide 95/5 sampling theory below).

**Output** — `data/acquisition/queue/batch_NNNNN.json` (5-digit, zero-padded — e.g. `batch_00001.json` — covers the unlikely case of needing one batch per individual US school district), one file per batch. Structured targeting parameters only (district identity, enrollment, claimed bands, per-band school lists with `n_candidates`/`n_selected` for reviewer transparency) — **no prompt text**. Prompt construction belongs to Stage 2, since Python can't spawn the Haiku WebSearch subagent that Wave 1 discovery needs anyway (agent-in-the-loop, see Stage 2 below) — baking prompts into Stage 1's output would couple queue review to discovery-prompt wording, a different kind of review than "are these the right districts/schools." Schema reference: `data/acquisition/queue/batch.example.json`.

**Checkpoint A (human review)** happens here, **out-of-band** — no `approved`/`reviewed_by` fields in the batch JSON for now (matches the project's current high-touch ramp-up posture; revisit if/when a machine-checkable gate is wanted). The reviewer reads the batch file, confirms the districts/bands/schools are sensible, and gives a verbal/chat go-ahead before Stage 2 runs.

**Status registry** (`data/acquisition/status/district_status.json`, module `infrastructure/acquisition/discovery/district_status.py`) — a single JSON dict keyed by `district_id` (structure prioritized over scan-ability; this is process input read by every future batch-build to exclude already-attempted districts, not primarily a human-read record). Updated at **every** stage 1-9 as a district progresses, with a per-district `history[]` trail so a human can see why a district landed where it did without cross-referencing batch files. Lives under `data/acquisition/status/`, not nested under `queue/`, since "acquisition" is the umbrella term for the whole 9-stage process and every stage writes to it. **Pre-queue exclusions are deliberately not recorded here** — see filter list above. Schema reference: `data/acquisition/status/district_status.example.json`. Replaces the directory-presence heuristic previously used in `training_batch.py` (archived, see *Key files*).

### 2 · Discovery — *successive waves*, not a council
Discovery is a **recall** problem (find *a* schedule page; capture verifies it), so we run tools in **cost-ascending waves** and stop once a district is satisfied — we do **not** run all tools on every district.
- **Wave order (revised 2026-06-20):** Claude WebSearch (Haiku subagent, via subscription, overnight) → OpenRouter `gpt-4o-mini-search` (API, on the residual only) → **flag for manual**. **Perplexity dropped** — full-41 it was lowest coverage (31/41), fewest pages, and hub-skewed (wrong reach for per-school targeting); its ~2 unique districts were hub-level pages the capture path covers anyway. Net: simpler 2-wave automated cascade + manual tail.
- **Orchestration:** runs via the **`per-school-acquire` skill** (`.claude/skills/`), not a bare script — Wave 1 (Claude WebSearch) requires the agent to spawn a Haiku WebSearch subagent, which Python cannot do. The skill glues the waves; `.py` workers (`per_school_run.py roster|wave2|flatten`, `capture_discovery.mjs`, `council_extract.py`) do the deterministic stages. **Consequence: agent-in-the-loop, not lights-out** — the subscription leverage and unattended operation are mutually exclusive.
- **Topology classification (Wave-1 subagent's second job):** while the Haiku WebSearch subagent is already querying a district's schools, it also classifies the district's **topology — strictly from what the SEARCH RESULTS reveal, never by reading page contents** — into one of: **`hub`** (multiple schools' times surface on one district URL), **`per_school`** (schedules sit on distinct school subdomains/pages), or **`none`** (neither found → flag). This label routes the downstream branch (capture-the-hub-once-and-fan vs. extract-each-school-page). It is a *topology* hint only — whether a hub renders cleanly vs. an expanding/accordion edge case is a **capture-stage** determination, not the subagent's. Recorded in `roster.json`.
- **Domain-scoped** every wave (Perplexity `search_domain_filter` / OpenRouter `site:` / Claude `allowed_domains`) — eliminates the wrong-district problem and reaches school subdomains.
- **Gate out** likely false positives (board agendas/minutes, bare annual calendars, news/aggregators); rank schedule-named URLs first.
- **Measured (full 41):** any-tool found an on-domain schedule page for **37/41 = 90%** (71% on a literally schedule-named URL). OpenRouter 33/41, Claude 32/41, Perplexity 31/41 — close and complementary (union 37). Tool reach differs: **OpenRouter/Claude reach school subdomains; Perplexity skews to district hub/`www`.**
- Code: `infrastructure/acquisition/discovery/discover.py`.

### 3 · Capture — *tiered* (local Playwright)
- Direct-download PDFs/images; for HTML, render (`networkidle`) and collect **innerText across frames** → `.txt`, **always** also a full-page **screenshot** → `.png`.
- **Linked PDF files (discovery found a `.pdf` URL) → save the file directly.** This is a plain HTTP GET (`fetch()` → `writeFileSync`, the `bin` branch in `capture_discovery.mjs`) — **no WebFetch/Haiku-subagent needed** (the subagent's job is *discovery*; once we have a PDF URL, capture fetches the bytes). Preserves the original file with its text layer intact (REQ-045 audit artifact). *Exception:* Google-Drive-hosted PDFs need the 3-tier handler. *(Distinguish from `page.pdf()`, which RENDERS an HTML page to PDF for the Tier-2 multi-column case — a different operation than downloading an existing PDF.)*
- **Making a captured PDF API-digestible** is the reader-router's job (see Reader-routing spec): `pdftotext -layout` if it has a usable text layer; **rasterize→vision** if it's a scan (New Haven CT path); **chunk + aggregate** if it exceeds `MAX_TEXT_LEN` (Orange path) — never truncate.
- **Tier preference: text layer first, screenshot→OCR/vision only for image pages.** Measured recovery of 152 relevant pages: **116 text, 16 PDF, 20 screenshot-OCR** — the 20 OCR-only pages (eChalk-style images) would be invisible to any text method, so the OCR tier is mandatory but *not* the default.
- **Salvaged from old design:** modal/popup dismissal (CSS-injection → JS dialog handler → dismiss-button click → DOM removal), Google-Drive 3-tier handler, direct-PDF download with Crawlee fallback.
- Code: `infrastructure/scraper/capture_discovery.mjs` (concurrent); `capturer.ts` (modal dismissal); `infrastructure/scripts/enrich/google_drive_handler.py`.

### 4 · Local processing
OCR image pages (`tesseract`), `pdftotext -layout` digital PDFs, table-aware reads (`pdfplumber`) where structure matters — done locally to minimize cloud load. Keep clean text where it exists (don't OCR a page that already has a text layer).

### 5 · Local filtering (coarse)
Cheap `pdftotext`-density sniff: clock-time count + bell keywords; reject obvious non-schedules (board calendars, administrative pages). Deliberately cheap and high-recall — precision tightening (URL-keyword weighting, time-grid detection) is a later pass. Code: `infrastructure/acquisition/discovery/relevance.py`.

### 6 · Hand to OpenRouter
Extraction standardizes on **OpenRouter** (`google/gemini-2.5-flash` etc.) — even though the first Flash pass used the native Google API. Inputs: OCR'd text / clean text / PDFs / screenshots per the tier.

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

## Sampling policy (stage 1/7) — two separate decisions, queue-time settled, extraction-time still open

Computed per-district per-band school counts and the textbook **95% / ±5% finite-population sample size** from NCES `ccd_sch_029_2425` (classifier `infrastructure/acquisition/discovery/school_sampling.py`; bands by grade span `GSLO`-`GSHI`, so a K-8 counts for *both* elementary and middle; open schools only). **Result kills the survey-formula approach:**

- Across **18,158 districts**, 95/±5 sampling = **127,513 band-extractions = 96% of a full census (132,803)** — the finite-population correction saves only ~4%.
- Reason: the corpus is mostly small districts (**median 4 calls / district across 3 bands; p95 = 22**), which get censused regardless. The formula only inflates a few mega-districts (**LA Unified n=496, Broward 286, Orange 254**) — i.e., maximum effort exactly where the marginal school adds least.
- The formula is statistically correct for the *wrong question*: it estimates a worst-case *proportion* (p=0.5), but we want the **modal band-minutes**, and bell times **cluster by district policy** → the mode stabilizes far below the proportion-formula n.

**Decision 1 — queue-time school cap (decided 2026-06-22, see Stage 1 above):** small districts (≤12 schools/band) get a full census; large districts cap at **12 schools/band**, picked via seeded random sample with most-constrained-first cross-band overlap minimization. This is a fixed *queue-time* commitment — Stage 1 has no extracted minutes yet to judge "is the mode stable," so it must hand Stage 7/8 the full upper-bound candidate list (up to 12/band) rather than try to early-exit itself.

**Decision 2 — extraction-time mode-stability early-exit (still open, blocked on per-school extract→aggregate):** *within* the queued candidates, does extraction need to process all 12, or can it stop once the modal gross-minutes is stable (e.g., unchanged over the last ~5 schools processed)? LA elementary would resolve in ~8 schools, not all 12 queued — but this can only be measured once Stage 7's per-school extract→aggregate is built and run on real captured inputs (Open decision #2 below). The 95/±5 number stands only as the conservative *upper bound* this whole policy replaced.

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

1. **Per-school sampling policy — queue-time half resolved 2026-06-22 (Stage 1, see above); extraction-time half still open.** Queue-time: cap=12/band, seeded random sample, most-constrained-first cross-band overlap minimization — built and validated. Still open: the *extraction-time* mode-stability early-exit (does Stage 7/8 need to process all 12 queued schools, or can it stop once the modal value stabilizes?) — blocked on Open decision #2 (per-school extract→aggregate not yet built).
2. **Per-school extract → modal-aggregate** — **not yet built or tested.** The end-to-end test to date used naive *concatenated* district pages and scored ~50% vs ~100% on clean curated files; the fix is per-school extraction then aggregation. This is the #1 build item.
3. **Council membership + decision rule** — which 2–3 of the 6, agreement tolerance (±15 min), tiebreak, what routes to human QC.
4. **Discovery precision filter** — URL-keyword weighting / time-grid detection to close the 71%↔90% gap (deferred until we see scaled yield).
5. **The 4 discovery misses** (Orange FL, Baldwin AL, Springdale AR, Champlain Valley VT) — deferred.
6. **School-name matching in per-school consensus** — `aggregate.consensus_school_facts` groups a school across models by normalized name; when spellings/OCR differ ("West Valley HS" vs "W. Valley", garbled letters), a school fails to reach cross-family agreement and is held out as `unresolved` (correctly excluded from the band mode, not wrong-counted). Observed on Fairbanks (West Valley) and as the bulk of Orange FL's 102 unresolved. **WATCH-ITEM, do NOT loosen yet** — a looser matcher risks *merging genuinely different schools* (a worse error than holding one out). Only revisit if unresolved rates are demonstrably blocking GT/coverage; first confirm the pattern (are the held-out times actually fine under different names?) before touching the matcher.

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
| **Queue (Stage 1): exclusion filters, stratified sampling, batch writer** | `infrastructure/acquisition/discovery/queue_batch.py` |
| **NCES classification: per-school bands, LEA claimed span, charter lookup** | `infrastructure/acquisition/discovery/school_sampling.py` |
| **Cross-stage district status registry (all 9 stages)** | `infrastructure/acquisition/discovery/district_status.py` |
| **Stage 1 output / status registry schema references** | `data/acquisition/queue/batch.example.json`, `data/acquisition/status/district_status.example.json` |
| **CTC/shared-service classification backfill (Rule 6)** | `infrastructure/database/migrations/apply_ctc_classification.py` |
| Archived: pre-redesign stratified batch picker (superseded by `queue_batch.py`) | `data/archive/training_batch_py-superseded-20260622/training_batch.py` |
| Discovery (waves, domain-scoped) | `infrastructure/acquisition/discovery/discover.py` |
| Tiered capture | `infrastructure/scraper/capture_discovery.mjs` |
| Coarse relevance filter | `infrastructure/acquisition/discovery/relevance.py` |
| Discovery→extraction loop test (archived) | `data/archive/gt-benchmark-*/dead_benchmark_scripts/extract_test.py` |
| Extraction harness + providers | `infrastructure/acquisition/{extractors,reading,score_minutes}.py` (run_manifest_benchmark archived) |
| Modal dismissal / Crawlee one-hop | `infrastructure/scraper/src/capturer.ts`, `mapper.ts` |
| Google Drive handler | `infrastructure/scripts/enrich/google_drive_handler.py` |
| Per-school schema + MODE aggregation | `school_schedules` / `bell_schedules` (migration 016), REQ-042 |
| LCT precedence (bell → statutory → 360) | `infrastructure/scripts/analyze/calculate_lct_variants.py::get_instructional_minutes` |
| Requirements | REQ-024, 032, 042, 043–053 |
