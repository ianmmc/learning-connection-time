# Bell Schedule Acquisition Pipeline

**Status:** Design validated end-to-end (discovery + extraction); per-school targeting + council rules still to build.
**Last updated:** 2026-06-20.
**Companions:** `docs/EXTRACTION_BENCHMARK_FINDINGS.md` (model leaderboard + measured costs), `docs/technical-notes/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md` (full learnings), `docs/INSTRUCTIONAL_TIME_HARVEST.md` (why SEA central data is a dead end). The strategy/options report that preceded this is `docs/INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md` (now a pointer here).

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

### 1 · Queue
District list + `WEBSITE` from NCES `data/raw/federal/nces-ccd/2023_24/ccd_lea_029_2324_w_1a_073124.csv` (35/41 GT districts carry a usable domain; the rest get an unscoped search). Queueing strategy will iterate as we observe yield. **Open: sampling policy** — how many schools per band to target (see *Open decisions*).

### 2 · Discovery — *successive waves*, not a council
Discovery is a **recall** problem (find *a* schedule page; capture verifies it), so we run tools in **cost-ascending waves** and stop once a district is satisfied — we do **not** run all tools on every district.
- **Wave order (revised 2026-06-20):** Claude WebSearch (Haiku subagent, via subscription, overnight) → OpenRouter `gpt-4o-mini-search` (API, on the residual only) → **flag for manual**. **Perplexity dropped** — full-41 it was lowest coverage (31/41), fewest pages, and hub-skewed (wrong reach for per-school targeting); its ~2 unique districts were hub-level pages the capture path covers anyway. Net: simpler 2-wave automated cascade + manual tail.
- **Orchestration:** runs via the **`per-school-acquire` skill** (`.claude/skills/`), not a bare script — Wave 1 (Claude WebSearch) requires the agent to spawn a Haiku WebSearch subagent, which Python cannot do. The skill glues the waves; `.py` workers (`per_school_run.py roster|wave2|flatten`, `capture_discovery.mjs`, `council_extract.py`) do the deterministic stages. **Consequence: agent-in-the-loop, not lights-out** — the subscription leverage and unattended operation are mutually exclusive.
- **Topology classification (Wave-1 subagent's second job):** while the Haiku WebSearch subagent is already querying a district's schools, it also classifies the district's **topology — strictly from what the SEARCH RESULTS reveal, never by reading page contents** — into one of: **`hub`** (multiple schools' times surface on one district URL), **`per_school`** (schedules sit on distinct school subdomains/pages), or **`none`** (neither found → flag). This label routes the downstream branch (capture-the-hub-once-and-fan vs. extract-each-school-page). It is a *topology* hint only — whether a hub renders cleanly vs. an expanding/accordion edge case is a **capture-stage** determination, not the subagent's. Recorded in `roster.json`.
- **Domain-scoped** every wave (Perplexity `search_domain_filter` / OpenRouter `site:` / Claude `allowed_domains`) — eliminates the wrong-district problem and reaches school subdomains.
- **Gate out** likely false positives (board agendas/minutes, bare annual calendars, news/aggregators); rank schedule-named URLs first.
- **Measured (full 41):** any-tool found an on-domain schedule page for **37/41 = 90%** (71% on a literally schedule-named URL). OpenRouter 33/41, Claude 32/41, Perplexity 31/41 — close and complementary (union 37). Tool reach differs: **OpenRouter/Claude reach school subdomains; Perplexity skews to district hub/`www`.**
- Code: `infrastructure/scripts/benchmark/discovery/discover.py`.

### 3 · Capture — *tiered* (local Playwright)
- Direct-download PDFs/images; for HTML, render (`networkidle`) and collect **innerText across frames** → `.txt`, **always** also a full-page **screenshot** → `.png`.
- **Tier preference: text layer first, screenshot→OCR/vision only for image pages.** Measured recovery of 152 relevant pages: **116 text, 16 PDF, 20 screenshot-OCR** — the 20 OCR-only pages (eChalk-style images) would be invisible to any text method, so the OCR tier is mandatory but *not* the default.
- **Salvaged from old design:** modal/popup dismissal (CSS-injection → JS dialog handler → dismiss-button click → DOM removal), Google-Drive 3-tier handler, direct-PDF download with Crawlee fallback.
- Code: `infrastructure/scraper/capture_discovery.mjs` (concurrent); `capturer.ts` (modal dismissal); `infrastructure/scripts/enrich/google_drive_handler.py`.

### 4 · Local processing
OCR image pages (`tesseract`), `pdftotext -layout` digital PDFs, table-aware reads (`pdfplumber`) where structure matters — done locally to minimize cloud load. Keep clean text where it exists (don't OCR a page that already has a text layer).

### 5 · Local filtering (coarse)
Cheap `pdftotext`-density sniff: clock-time count + bell keywords; reject obvious non-schedules (board calendars, administrative pages). Deliberately cheap and high-recall — precision tightening (URL-keyword weighting, time-grid detection) is a later pass. Code: `infrastructure/scripts/benchmark/discovery/relevance.py`.

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

## Extraction council design (stage 7) — candidate configs, to be selected empirically

Grounded in the council research (`docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`) and the measured leaderboard/costs (`EXTRACTION_BENCHMARK_FINDINGS.md` Update 3–4). **Principles, fixed:**
- **Consensus must be cross-family.** Agreement only counts between different model families — same-family agreement (two Gemini, two Mistral) is weak evidence (correlated blind spots). Family buckets: **Google** (Flash, Flash-Lite) · **Mistral** (Small 24B, Large 2512) · **DeepSeek** (V3.2) · **Qwen** (235B-2507).
- **"Agree" = within ±15 min** on a band's gross minutes (route on agreement *width*, not just vote count).
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

## Sampling policy (stage 1/7) — decided 2026-06-20: capped sequential + mode-stability, NOT 95/±5

Computed per-district per-band school counts and the textbook **95% / ±5% finite-population sample size** from NCES `ccd_sch_029_2425` (classifier `infrastructure/scripts/benchmark/discovery/school_sampling.py`; bands by grade span `GSLO`-`GSHI`, so a K-8 counts for *both* elementary and middle; open schools only). **Result kills the survey-formula approach:**

- Across **18,158 districts**, 95/±5 sampling = **127,513 band-extractions = 96% of a full census (132,803)** — the finite-population correction saves only ~4%.
- Reason: the corpus is mostly small districts (**median 4 calls / district across 3 bands; p95 = 22**), which get censused regardless. The formula only inflates a few mega-districts (**LA Unified n=496, Broward 286, Orange 254**) — i.e., maximum effort exactly where the marginal school adds least.
- The formula is statistically correct for the *wrong question*: it estimates a worst-case *proportion* (p=0.5), but we want the **modal band-minutes**, and bell times **cluster by district policy** → the mode stabilizes far below the proportion-formula n.

**Policy:**
1. **Small districts (the majority): census the band** (≤ ~6–8 schools/band → process all; cheap and exact).
2. **Large districts: cap ~8–12 schools/band with mode-stability early-exit** — process in small batches, stop when the modal gross-minutes is stable (e.g., unchanged over last ~5 schools or clear plurality). LA elementary resolves in ~8, not 223.
3. **The cap is to be set empirically** — measure how fast the modal band-minutes stabilizes as n grows on large GT districts (LA, Broward, Mesa, Cleveland); part of the per-school build. The 95/±5 number stands only as the conservative *upper bound*.

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

1. **Per-school sampling policy** — proposal: 95%/±5% finite-population sample from NCES per-band school counts, *checked* against an empirical mode-stability test (bell times cluster by district policy, so the mode likely stabilizes well below the survey-formula n). Needs a grade-span→band classifier (K-8/K-12/6-12). Small districts census naturally.
2. **Per-school extract → modal-aggregate** — **not yet built or tested.** The end-to-end test to date used naive *concatenated* district pages and scored ~50% vs ~100% on clean curated files; the fix is per-school extraction then aggregation. This is the #1 build item.
3. **Council membership + decision rule** — which 2–3 of the 6, agreement tolerance (±15 min), tiebreak, what routes to human QC.
4. **Discovery precision filter** — URL-keyword weighting / time-grid detection to close the 71%↔90% gap (deferred until we see scaled yield).
5. **The 4 discovery misses** (Orange FL, Baldwin AL, Springdale AR, Champlain Valley VT) — deferred.

---

## Human-QC strategy (the binding constraint)

Two independent extractors disagree on a large share of districts; at <1 hr/week, human review can't drain a 20K queue. Resolution: **decouple coverage from verification** — auto-accept on council agreement, statutory-fallback the uncertain tail (labeled), and **spend human QC enrollment-weighted** (the top few hundred districts dominate every published LCT number; ~500 × 2 min ≈ feasible). See `INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md` for the full constraint analysis.

---

## Key files

| Concern | File |
|---|---|
| Discovery (waves, domain-scoped) | `infrastructure/scripts/benchmark/discovery/discover.py` |
| Tiered capture | `infrastructure/scraper/capture_discovery.mjs` |
| Coarse relevance filter | `infrastructure/scripts/benchmark/discovery/relevance.py` |
| Discovery→extraction loop test | `infrastructure/scripts/benchmark/discovery/extract_test.py` |
| Extraction harness + providers | `infrastructure/scripts/benchmark/{run_manifest_benchmark,extractors,reading,score_minutes}.py` |
| Modal dismissal / Crawlee one-hop | `infrastructure/scraper/src/capturer.ts`, `mapper.ts` |
| Google Drive handler | `infrastructure/scripts/enrich/google_drive_handler.py` |
| Per-school schema + MODE aggregation | `school_schedules` / `bell_schedules` (migration 016), REQ-042 |
| LCT precedence (bell → statutory → 360) | `infrastructure/scripts/analyze/calculate_lct_variants.py::get_instructional_minutes` |
| Requirements | REQ-024, 032, 042, 043–053 |
