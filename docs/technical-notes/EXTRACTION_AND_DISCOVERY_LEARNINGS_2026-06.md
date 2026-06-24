# Technical Note — Extraction Bake-off & Discovery Architecture (2026-06-13)

> Consolidated learnings from the multi-provider extraction bake-off and the discovery proof-out.
> Companions: `docs/EXTRACTION_BENCHMARK_FINDINGS.md` (full leaderboard tables), `docs/INSTRUCTIONAL_MINUTES_ACQUISITION_STRATEGY.md` (strategy), `docs/REQUIREMENTS.yaml` (REQ-043…053).

## Per-school build + first test (2026-06-20)

Built the per-school path end-to-end and ran a first isolation test (New Haven Unified CA). Scripts: `discovery/school_sampling.py` (NCES `ccd_sch_029_2425` → per-band school counts + 95/±5 sample size), `discovery/per_school_run.py` (roster → per-school domain-scoped search), `discovery/aggregate.py` (cross-family council accept + modal→mean aggregation + mode-stability early-exit; unit-tested), `discovery/council_extract.py` (Path-1 council per page → aggregate → score).

**Findings:**
1. **Sampling: 95/±5 is a near-census (96% of 132,803 band-memberships across 18,158 districts); median district = 4 calls.** The finite-population formula only inflates mega-districts (LA n=496) — wrong shape. Decision: **census small districts, cap large at ~8–12/band with mode-stability early-exit** (cap to be set empirically). See `ACQUISITION_PIPELINE.md` sampling section.
2. **Per-school-page vs district-hub is a spectrum, and it's the key reality.** Top-pick hub-collapse: **Christina 20/21 (hub-dominant), Sweetwater 10/15 (mixed), New Haven 0/13 (per-school-dominant).** Many schools — esp. small/rural — have NO own page; the district publishes a consolidated page. Design consequence: **dedup candidates across schools** (New Haven 39→12 distinct) → capture/extract each page once → fan band values to the schools it covers.
3. **Pipeline is mechanically correct** — search→dedup→tiered capture→Path-1 council (cross-family accept)→modal aggregation all functioned; council agreed with 0 judge escalations on New Haven.
4. **A real per-school page is an excellent input** — Itliong-Vera Cruz MS bell page = clean period grid with **explicit labeled LUNCH** (everything net-minutes needs). Where the page exists and renders, extraction is easy.
5. **Two gates remain (both known):** (a) **capture fidelity** — Searles Elementary's own bell page rendered **0 time-lines** (JS/image the tier missed); (b) **hub ambiguity** — New Haven's elementary band routed to an **unlabeled multi-school hub** (~29 mixed time ranges, no row→school labels); council picked 8:00–2:05=365 vs GT's 8:30–2:05=335 (a different elementary schedule, both plausible). **Not** a net/gross issue — GT is gross (end−start).
6. **Couldn't isolate the per-school *lift* yet** — New Haven's single checkable GT band (elementary) routed through the hub, not a per-school page. Needs test districts with multi-band GT that route to genuine per-school pages, and/or hand-verified GT.

## TL;DR
- **Extraction is essentially solved *on good inputs*** — on tractable districts (difficulty > 0.70) the top models hit **~95–100%**. The full-41 ceiling of ~69% is dragged down almost entirely by **bad/over-stuffed/wrong inputs**, not model capability.
- **Cheap wins.** **Gemini 2.5 Flash** leads the full-41 (68.9%) and is among the cheapest. Bigger ≠ better (DeepSeek V4-Pro, GPT-5.5, Opus all trail cheaper models).
- **The bottleneck is INPUT quality, not the model.** Of the 23 hard districts, 22 already had the schedule as extractable text — they failed on **granularity/noise** (giant multi-school dumps, single-band GT), not OCR. **#1 lever: per-school targeting** — small, focused, current, single-schedule inputs.
- **Discovery search works.** Domain-scoped search (Perplexity `search_domain_filter`, OpenRouter `site:`, Claude `allowed_domains`) eliminates the wrong-district problem and reaches school subdomains. The new bottleneck is **capture fidelity** on JS-rendered school CMS pages → screenshot+OCR/vision fallback.

---

## 1. Extraction model bake-off

**Method.** Provider-agnostic harness (`infrastructure/scripts/benchmark/`), 41-district human-provided ground truth, metric = grade-band **modal instructional minutes within ±15 min**. ~20 models across native APIs + two multi-model conduits.

**Full-41 leaderboard (tables mode), top to bottom:** Gemini 2.5 Flash **68.9%** · Mistral Large 2512 / Qwen3.7-Max 67.6% · DeepSeek V3.2 66.2% · **Mistral Small 24B 63.5% ($0.05/1M)** / Grok 4.3 63.5% · Opus 62.3% · Llama 3.3 70B 59.5% · Command R+ / Qwen3-235B 58.1% · **Granite 4.1 8B 51.4%** · DeepSeek V4-Pro 45.9% · Sonnet 45.5% · best local (llama3.1:8b) ~37%.

**Lessons:**
- A capable cloud model **~doubles** the best local (~37%). The earlier "no silver bullet / ~53% cloud ceiling" was an artifact of testing only Haiku on 5 districts.
- **Cheap = best.** Gemini 2.5 Flash and Mistral Small 24B (≈$0.05/1M) outscore Opus.
- **Bigger ≠ better.** The flagship DeepSeek V4-Pro landed near the bottom (over-extraction, low district-hit); GPT-5.5 < GPT-5.4.
- **Granite 4.1 8B (51%)** — a tiny, Apache-licensed, self-hostable model beat Sonnet → strong candidate for the headless-server local path.
- **Validate on the full set.** A 7-district smoke had Grok at 88%; full-41 was 63.5%. Small subsets mislead.
- **Metric caveat.** Modal-minutes penalizes thorough multi-school extractors (Sonnet, V4-Pro). A `max`/"longest-day" re-score did NOT recover hidden accuracy for the leaders (it's strictly worse for them) → their scores are genuine. A proper **per-school scoring pass** is the right fairness fix but won't re-rank the leaders much.

## 2. Input quality is the ceiling (crosstab / difficulty analysis)

Per-district × per-model crosstab (`data/benchmark_results/crosstab_{mode,max}.{csv,json}`, dashboard `crosstab_dashboard.html`), cell = matched/GT-bands, plus a derived **difficulty** = avg band-match-rate across all models.

- **8 of 40 districts (20%) are solved by ZERO models**; ~11 under 25%. **20 are "easy" (>60%).**
- On **difficulty > 0.70** districts, the top models re-score to **~95–100%** (Gemini 2.5 Flash & Mistral Large = 100%). The size of each model's jump separates **input-limited** (DeepSeek V4-Pro +33 pts) from **model-limited** (Sonnet +6 — its over-extraction persists even on clean inputs).
- **No condition→model routing signal.** The same ~4 models lead on both pdf and html; per-modality cells are too small to justify per-modality tool routing. A single cheap model (Gemini 2.5 Flash) generalizes. The routing that *is* justified is **confidence-based** (auto-accept on consensus; flag the hard).

**Failure-mode analysis (the key finding).** For the 23 hard districts, checking whether the input artifact even contained the schedule:
- **22/23 already had the times as extractable text** — often hundreds. Only 1 (Carson City, empty Office doc) lacked them. **So failure was almost never "needs OCR."**
- Real failure modes: **over-stuffed/wrong-granularity** (giant multi-school dumps hitting the 12k read cap with hundreds of times for a single-band GT), **single-band GT vs multi-school doc** (modal mismatch), **thin/wrong page** (the captured artifact wasn't the real schedule page — e.g. Christina), and **empty/corrupt** (Carson City; Montgomery AM/PM corruption).
- **Implication:** the path past ~69% is **better inputs**, dominated by **targeting/granularity** — capture the *specific school's focused schedule page*, not a district dump.

## 3. Multi-provider conduits (infra)

Two conduits added to `extractors.py` (model spec `provider:model`):
- **`pplx`** — Perplexity **Agent API** (SDK `responses` resource → `POST /v1/agent`); `tools` omitted ⇒ web search OFF ⇒ grounded extraction (REQ-053). Note: Perplexity `chat/completions` is Sonar-only and rejects 3rd-party model ids; the Agent API is the multi-model surface. Catalog: `GET /v1/models`.
- **`openrouter`** — OpenAI-compatible gateway (`base_url=https://openrouter.ai/api/v1`), ~337 models, one key, a second independent conduit. **Free-tier (`:free`) is too rate-limited (429s) to benchmark — use paid endpoints (pennies).**
- Native providers also present: `anthropic` (Claude; no API key in this env → Claude run via **subagents**), `gemini` (`google.generativeai`), `openai`, `ollama`.

**SDKs / keys.** Installed: `perplexityai` (import `perplexity`), `openai`, `google-genai` (new SDK; the deprecated `google.generativeai` can't call the current `google_search` tool). Keys live in **gitignored** `config/secrets.local.json` (Perplexity, OpenRouter, Gemini) and `.env` (Gemini, Postgres). The `gemini` MCP server (separate repo) was repointed 2.0→2.5-flash, but the harness uses the **direct API**, not the MCP.

## 4. Discovery proof-out

Harness in `infrastructure/scripts/benchmark/discovery/` (`discover.py`, `capture_discovery.mjs`, `relevance.py`). Probe (`infrastructure/scraper/probe_acquisition.mjs`) earlier proved **blind Crawlee crawling fails** (URL-glob targeting matched zero links; broad crawl slow/noisy and missed every schedule).

**Settled design:**
1. **Search-led discovery** (not crawling). Validated paths: Perplexity Search API (cleanest — returns real URLs incl. school subdomains), Claude WebSearch (subagent), OpenRouter `gpt-4o-mini-search`. **Google grounding DROPPED** — `GoogleSearch` tool exposes only `exclude_domains`, no include/site restriction (its site-scoped products are Custom Search JSON API / Vertex AI Search, separate setup).
2. **Domain-scoped search solves the wrong-district problem** (previously surfaced Knott-County-KY etc. for a WY district). Perplexity `search_domain_filter=[host]` (includes subdomains; surfaced `pbe./sce.…/bell_schedule`), OpenRouter `site:`, Claude `allowed_domains`. District host from the NCES LEA `WEBSITE` column.
3. **Smart URL gate** as backstop: accept on-domain + subdomains, or CMS-host-with-district-slug (finalsite/echalk/sites.google/gdrive); drop news/aggregators.
4. **Tiered capture** (Playwright, local): always render + screenshot (cheap audit artifact); prefer the text layer; **escalate to screenshot+OCR/vision only when the text layer is empty.** This is the current bottleneck — JS-rendered school CMS pages (eChalk/Finalsite) return text=0 via `page.pdf()` + pdftotext, so the schedule must be read visually.
5. **Relevance gate = deliberately-cheap plain `pdftotext`** (clock-time density + bell keywords). High-fidelity reading (pdfplumber/vision) belongs in *extraction*, not the gate.
6. **Crawlee's role = terrain-mapper / school-enumerator + one-hop off-site fetcher** (feed it an on-domain page → follow to a linked CDN/GDrive PDF; no domain restriction needed since we control the seed). NOT a schedule-finder.

## 5. Council-of-models direction (cost-aware consensus)
Per REQ-048, two independent paths, auto-accept on agreement, human-QC disagreements. Candidates: **default = Gemini 2.5 Flash**; cross-family partner = **DeepSeek V3.2** or **Mistral**. Cheap members validated on good inputs: **Gemini 2.5 Flash-Lite** (91%, $0.10/1M) and **Mistral Medium 3.1** (97%, $0.40/1M). Open work: pairwise **agreement/independence** analysis — a cheap model that *agrees* adds little; one that catches *different* errors adds a lot.

## 6. Recommended architecture (where this points)
```
Discovery (domain-scoped search; per-school targeting)
  → Capture (Playwright: text-layer preferred; screenshot+OCR/vision fallback; Crawlee one-hop for off-site PDFs)
  → Relevance gate (cheap pdftotext: real, current schedule?)
  → Reading (pdfplumber for digital PDFs; vision for image/JS screenshots)
  → Extraction council (Gemini 2.5 Flash + an independent cross-family model; consensus auto-accept, flag disagreements)
  → Fail-loud → statutory fallback for the residual (REQ-049)
```

## 7. Open next steps
- (a) Bake the screenshot+OCR tier into capture; re-run the discovery smoke for the first real hit-rate.
- (b) Prototype **per-school targeting** (Crawlee enumerate → scoped search per school → focused capture) on a multi-school district — prove the granularity thesis end-to-end.
- (c) Council composition: agreement/independence analysis.
- (d) Per-school scoring pass (fairer extraction ranking).

## Reproduce
- Extraction: `python3 infrastructure/scripts/benchmark/run_manifest_benchmark.py --model <provider:model> --mode tables` (keys via `.env`/`config/secrets.local.json`); score `score_minutes.py`; crosstab `crosstab.py`; dashboard `build_dashboard.py`.
- Discovery: `discovery/discover.py` → `infrastructure/scraper/capture_discovery.mjs <discovery-dir>` → `discovery/relevance.py`.
