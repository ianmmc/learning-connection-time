> **ARCHIVED 2026-07-02.** The constraint analysis (coverage × human-QC × time-budget) is distilled into
> `docs/PROJECT_HISTORY.md` → "The human-QC constraint: decouple coverage from verification". The
> cost/options table and phased bake-off plan are superseded by the executed multi-provider bake-off and
> per-school pipeline entries in the same doc. Kept here as the original, unmodified source.

# Daily Instructional Minutes: Acquisition Strategy — Decision Record

> **Status:** Historical strategy/options report (2026-06-12, validated 2026-06-13). **The current operational pipeline now lives in `docs/ACQUISITION_PIPELINE.md`** — read that first. This file is retained for two things still worth keeping: (1) the **constraint analysis** (the coverage × human-QC × <1 hr/week conflict and its resolution), and (2) the **options table** (the cost/time/accuracy decision history that explains *why* we chose the cheap-cloud council + per-school path). The phased "bake-off → build" program below is **largely executed**: the bake-off is done (see `EXTRACTION_BENCHMARK_FINDINGS.md`), discovery and extraction are validated, and the live build items moved to `ACQUISITION_PIPELINE.md` *Open decisions*. Treat the Phase 0–3 plan as the record of intent, not the current task list.
>
> **What held:** paid-API extraction is cheap and capable (**Gemini 2.5 Flash leads full-41 at 68.9%, among the cheapest**; ~95–100% on difficulty>0.70 inputs); **input quality, not model choice, is the ceiling**; **domain-scoped search discovery works**. Direction confirmed: cheap-cloud council + tiered capture + per-school targeting + statutory fallback. Companions: `EXTRACTION_BENCHMARK_FINDINGS.md`, `INSTRUCTIONAL_TIME_HARVEST.md`, `docs/technical-notes/models-and-council-composition/EXTRACTION_AND_DISCOVERY_LEARNINGS_2026-06.md`.

## Context

LCT needs **daily instructional minutes per grade band (elementary/middle/high) for ~20,000 districts**, derived from bell schedules that live on district and individual-school websites in varied formats (HTML, linked PDFs, Google Drive PDFs, PNG/JPG/GIF images, and more). The project paused because the local-first approach (Crawlee + Ollama 7B) hit an extraction-accuracy wall (~42% local, ~53% Claude Haiku on the grade-band modal-minutes ±15-min metric). Two facts reframe the problem:

1. **The acquisition half is also unproven.** The Crawlee mapping/capture pipeline has **never been run end-to-end** — every file in `data/raw/` was hand-collected. Steps 1–4 of the workflow (queue → find school sites → find schedules → capture) are *not* solved, despite `ACQUISITION_PIPELINE.md` describing them as "production-ready."
2. **Cheap cloud extraction is effectively free and was never tested.** Gemini 2.5 Flash-Lite / GPT-4o-mini cost ~$0.05–0.30 per 1M tokens; the entire 20K-district extraction run is **tens of dollars**, not the cost wall the project assumed. The "trade money for time with local models" premise was solving a non-problem for the extraction step.

**Goal:** highest accuracy at lowest monetary cost; time is the variable we spend. Hard budget ceiling for any option considered: **$1,000 total**. Working constraints: coverage = **all ~20K districts**; validation = **consensus auto-accept + human QC of disagreements**; human time = **< 1 hr/week**.

---

## The constraint conflict (must be resolved, not papered over)

These three constraints **cannot all be fully satisfied**:

> all 20K districts  ×  human-QC every disagreement  ×  < 1 hr/week

**The math:** two independent extractors each ~40–55% accurate will *disagree* on a large share of districts — call it 30–50%. That puts **6,000–10,000 districts** into the human-review queue. At <1 hr/week and an optimistic ~2 min/district, that clears ~30/week → **4–6 years** to drain the queue once. Pure-manual collection of all 20K is worse (~4,000 hours ≈ decades at this cadence). **The human is the binding constraint, by 2–3 orders of magnitude.**

**Resolution (the central design decision):** decouple *coverage* from *human-verification*. Cover all 20K, but route human time only where it changes the answer:

- **Auto-accept** where two paths agree within tolerance (no human).
- **Statutory fallback** (already built, `method=statutory_fallback`, REQ-024) for the uncertain long tail — clearly labeled, never counted as "enriched." This *is* coverage for all 20K.
- **Human QC spent enrollment-weighted**: the top few hundred districts hold the majority of U.S. students and dominate every published LCT number. ~500 districts × 2 min ≈ 17 hrs ≈ a few months at <1 hr/week — *feasible*. The tail's exact minutes barely move aggregate findings and don't justify human time.

This keeps all three constraints intact in spirit: 20K covered, disagreements that *matter* get human eyes, <1 hr/week respected.

---

## Significant points missing from the original 7-step workflow

1. **A validation/QC gate** between parse and incorporate (the reason the project paused) — the consensus + statutory-fallback + prioritized-QC layer above.
2. **Format routing before parsing** — detect format and route: table-aware reader for digital PDFs, OCR/vision for image PDFs, targeted DOM scrape for HTML. Plain-text-on-everything is *what caps accuracy* (benchmark finding).
3. **"Is this a schedule, and which band?" classification** — distinct from discovery and from extraction.
4. **A sampling policy** — how many schools per district per band. The data model already supports per-school MODE aggregation (`school_schedules` + REQ-042); the policy isn't pinned. Proposal: 1–3 schools/band, "reasonable sample not census."
5. **Net vs. gross minutes** — subtract lunch/passing/recess and pick a *typical* day (not early-release/block), which means extracting those deductions, not just bell start/end.
6. **An evaluation set to prove accuracy** — today's ground truth is 41 districts, often single-band, some corrupt. Can't claim "good enough" without expanding/cleaning it.
7. **Acquisition validation + anti-bot reality** — Crawlee is untested; CDN blocking is systemic (MI=Cloudflare, VA=Akamai). Needs a real end-to-end test and a managed-scraping fallback for blocked/JS-heavy sites.

---

## End-to-end options: cost vs. time vs. accuracy

**Cost model assumptions:** ~20K districts × ~5 extraction documents each ≈ **100K documents**; ~6K input + ~1K output tokens/doc; **batch pricing (50% off)**. Acquisition assumes ~100K–500K page fetches. Figures are order-of-magnitude estimates to compare options, not quotes. Pricing as of mid-2026 (sources at end).

| # | End-to-end option | Acquisition | Reading | Extraction model | Est. money (20K) | Time profile | Accuracy outlook |
|---|---|---|---|---|---|---|---|
| **1** | **All-local $0** (laptop + Ubuntu server) | Crawlee (unproven) | Docling/Marker (free) + local VLM | Ollama 7B (free) | **$0** | Very high: CPU-only server ≈ months for vision at scale; heavy eng to validate Crawlee | ~42% (benchmarked ceiling) — *the wall that paused the project* |
| **2** | **Cheap-cloud extraction + hybrid acquisition** ⭐ | Local Crawlee + Zyte/Firecrawl for hard sites | Format-routed: Docling/Marker (free) + cloud vision for images | Dual cheap paths: Gemini Flash-Lite ($0.05/$0.20 batch) + GPT-4o-mini ($0.075/$0.30 batch) | **~$100–250** | Weeks eng + unattended batch (cheap); human QC on head only | Unknown, likely > local — **bake-off required** |
| **3** | **Premium-model extraction** | same as #2 | same as #2 | Claude Haiku batch ($0.50/$2.50) single-path, or Sonnet for tiebreak | **~$550** (Haiku) → **~$1,000** (adds Sonnet tiebreak) | same; *smaller* human queue (premium → fewer disagreements) | Haiku ~53% benchmarked; frontier (Sonnet/Opus/Gemini Pro) untested |
| **4** | **Specialized doc-AI reading + cheap LLM reasoning** | same as #2 | AWS Textract ($15/1K pg, best tables) or Azure ($10/1K) on the digital-PDF subset; Docling free elsewhere | Gemini Flash-Lite / GPT-4o-mini | **~$150–500** (Textract scoped to ~30% table-PDF subset) | same | Directly attacks the #1 benchmarked failure (transposed/mangled tables) — high upside on that subset |
| **5** | **Fully manual (human)** | — human visits sites — | human reads | human computes | **$0** | ~4,000 hrs for 20K ≈ infeasible at <1 hr/wk; only top ~500 districts (~100 hrs) is realistic | ~100% where collected, but coverage tiny under the time budget |

**Reading the table:** Option 1 is the known dead end. Option 5 can't reach 20K under the time budget. The live contest is **2 / 3 / 4**, and they're not exclusive — the recommended program is a **cascade** that uses the cheap path (2) by default, the doc-AI reading lever (4) on the table-PDF subset, and the premium model (3) only as a disagreement tiebreaker — keeping total spend well under $1,000 while shrinking the human queue.

**Why money is nearly irrelevant for extraction:** even the *premium* single-path run (Haiku, ~$550) fits the budget; the cheap dual-path run is ~$100. The real currency is **accuracy per unit of human QC time**, because human time is the bottleneck. Spend money to *buy accuracy that shrinks the human queue* — that's the only lever that matters.

---

## Recommended approach (phased program)

### Phase 0 — The bake-off (decide the ceiling before building anything) — ~$20–50, days
The fair test (good models on *format-routed* inputs vs. clean multi-band ground truth) **has never been run**. Do it first; it decides everything downstream.
- **Reuse the existing provider-agnostic harness** — `infrastructure/scripts/benchmark/run_manifest_benchmark.py` *(note 2026-06-22: that benchmark harness has since been archived; the live extraction code is at `infrastructure/acquisition/`)* already supports `anthropic:`, `gemini:`, `openai:`, `ollama:` and text/tables/vision modes. Wire real API keys.
- Run a matrix on the 41-district manifest: {Gemini 2.5 Flash-Lite, Gemini Flash/Pro, GPT-4o-mini, Claude Haiku/Sonnet} × {table-aware (Docling/Marker), vision, plain-text}. Add **AWS Textract/Azure DI reading → cheap-LLM reasoning** as a reading variant (targets transposed-table failures).
- **First, fix the ground truth:** the benchmark explicitly blames single-band/corrupt GT. Hand-clean + expand GT to multi-band on ~40 districts before trusting any score.
- **Exit criterion:** identify the cheapest model+reading combo whose accuracy makes the human queue tractable. If nothing clears it, the answer is "enrichment is QC-bound" and we plan statutory-fallback-heavy.

### Phase 1 — Format-aware reading + dual-path consensus extractor — weeks
- Build a **format router**: digital PDF → Docling/Marker (free, local; Docling hit 97.9% on complex tables but watch dense-table hallucination); image PDF/PNG/JPG → vision or OCR; HTML → targeted DOM scrape (not `pandas.read_html` on nav menus — a benchmarked failure).
- **Dual-path consensus**: two independent extractors; auto-accept on agreement within ±tolerance on minutes; flag disagreements. Reuse the production `ExtractionService` prompt/validation the benchmark already wraps.
- Extract **deductions** (lunch/passing/recess) and a *typical-day* flag, not just bell start/end → net minutes (REQ-042 formula).
- Write to `school_schedules` (per-school) → MODE-aggregate to `bell_schedules` per (district, year, band). Schema is ready (migration 016).

### Phase 2 — Acquisition validation + managed fallback — weeks
- **Actually run Crawlee end-to-end** on a stratified sample (cooperative sites, JS-heavy SPAs, Cloudflare/Akamai-blocked). Measure real yield against the manual `data/raw/` baseline.
- Add a **managed-scraping fallback** for JS/blocked sites, budget-bounded: Zyte ($0.13/1K simple requests) or Firecrawl (free 1K/mo, Hobby $16/mo) for the cooperative majority; reserve Bright Data for the worst anti-bot only. Keep the ONE-attempt rule for WAF blocks (Rule #3).
- Implement school-site discovery off district sites (80%+ of districts have no district-wide schedule — data is on school subdomains).

### Phase 3 — Run at scale with the QC strategy — months, unattended
- Batch the cheap dual-path over all 20K via the Batch API (≤24 h turnaround, 50% off).
- **Auto-accept** consensus; **statutory-fallback** the uncertain tail (labeled, REQ-024); **queue human QC enrollment-weighted** (top districts first) within the <1 hr/week budget.
- Premium-model tiebreak (Haiku/Sonnet) only on high-enrollment disagreements — bounds premium spend to a few hundred dollars.
- Enforce **Rule #6**: DB-verify counts; never count statutory as enriched.

### The Ubuntu AI server's real role
CPU-only (no usable GPU) ≈ months for vision at 20K scale — **not** the extraction workhorse. Its fit: always-on **orchestration** (queue, Crawlee, batch submission/polling), free **local second path** in the consensus pair (run a 7B as Path B at $0), and unattended **QC tooling** host. Heavy vision, if needed, is cheaper on rented GPU (A100 80GB ~$0.67–0.79/hr spot) for a bounded run than on the laptop — but the bake-off should show whether vision is even the winning reading mode (it lost on aggregate last time). Briefing: `/Users/ianmmc/Development/ai-server-setup/SETUP_BRIEFING.md`.

---

## Critical files (reuse, don't rebuild)

- **Benchmark harness (Phase 0):** `infrastructure/scripts/benchmark/run_manifest_benchmark.py`, `extractors.py` (4 providers implemented; add Textract/Azure as reading variants), `reading.py` (text/tables/vision routing exists), `score_extraction.py` / `score_minutes.py`.
- **Ground-truth manifest:** `data/benchmark/ground_truth_manifest.json` + `build_ground_truth_manifest.py` (regenerate after cleaning GT).
- **Data model (ready):** `school_schedules` + distribution columns (migration 016), `bell_schedules`, `infrastructure/database/models.py::BellSchedule`.
- **LCT integration (ready):** `infrastructure/scripts/analyze/calculate_lct_variants.py::get_instructional_minutes` (precedence: bell schedule → statutory → 360).
- **Acquisition (validate):** `infrastructure/scraper/` (Crawlee/Fastify), `infrastructure/scripts/enrich/`.
- **Requirements:** REQ-024 (precedence), REQ-042 (MODE aggregation), REQ-032 (all-band extraction); add new reqs for format-routing, consensus, and QC prioritization.

## Verification

- **Phase 0:** harness produces a leaderboard (`compare_runs.py`) ranking model×reading combos on cleaned multi-band GT; pick the combo whose disagreement rate makes human QC tractable.
- **Phase 1:** unit + golden tests on the format router and net-minutes math; consensus agreement rate measured on the GT set; `pytest tests/` green.
- **Phase 2:** Crawlee end-to-end yield vs. the manual `data/raw/` baseline on the stratified sample, with blocked/JS/cooperative breakdown.
- **Phase 3:** `python3 infrastructure/scripts/verify_enrichment.py --quick` + DB-verified enriched-vs-statutory counts (Rule #6); spot-check a random sample of auto-accepted districts by hand.

## Pricing sources (mid-2026)
- Claude pricing / Batch (50% off) / vision: `claude-api` skill reference (cached 2026-06-04) — Haiku 4.5 $1/$5, Sonnet 4.6 $3/$15, Opus 4.8 $5/$25.
- Gemini: [pricepertoken — Flash-Lite](https://pricepertoken.com/pricing-page/model/google-gemini-2.5-flash-lite) ($0.10/$0.40; batch $0.05/$0.20).
- OpenAI: [cloudzero](https://www.cloudzero.com/blog/openai-pricing/), [pecollective](https://pecollective.com/tools/openai-api-pricing/) (GPT-4o-mini $0.15 in; GPT-4.1-mini $0.40/$1.60).
- Doc-AI: [aiproductivity OCR tools 2026](https://aiproductivity.ai/blog/best-ocr-tools-2026/), [braincuber Textract vs Document AI](https://www.braincuber.com/blog/aws-textract-vs-google-document-ai-ocr-comparison) (Azure $10/1K, Textract $15/1K, Google ~$30/1K).
- PDF parsers: [CodeCut Docling vs Marker vs LlamaParse](https://codecut.ai/docling-vs-marker-vs-llamaparse/), [Firecrawl best PDF parsers](https://www.firecrawl.dev/blog/best-pdf-parsers).
- Scraping: [Apify pricing guide](https://use-apify.com/blog/web-scraping-pricing-guide-all-platforms) (Zyte $0.13/1K; Firecrawl free 1K/mo, Hobby $16/mo).
- GPU rental: [Spheron 2026](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/) (A100 80GB ~$0.67–0.79/hr, H100 ~$1.50–2.00/hr).
