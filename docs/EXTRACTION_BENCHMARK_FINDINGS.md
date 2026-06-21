# Bell-Schedule Extraction Benchmark — Findings (2026-06-12; updated 2026-06-13)

> ⚠️ **2026-06-13 update — headline revised.** A full 41-district run added the cloud models the first pass lacked. **Gemini 2.5 Flash (68.9%) and Opus 4.8 (62.3%) clearly beat the best local (~37%)** — a *bigger* model lever than first concluded, though still ~69% on the full set (not production-ready unattended). See **"Update (2026-06-13)"** below; the "~35–53% / model strength a modest lever" framing in the original sections is partly superseded. A later sweep (**"Update 2"**) added multi-provider conduits (Perplexity Agent API, OpenRouter) and a top-shelf comparison — **Grok-4.3 ties Gemini 2.5 Flash, and cheap open-weight models (Mistral Small 24B ~$0.05/1M, DeepSeek V3.2) are viable** — pointing to a **Gemini 2.5 Flash + Grok-4.3** independent-consensus pair.
>
> **Question:** which local (and cheap-cloud) model + reading method best recovers **daily instructional minutes per grade band** from captured district documents — the input LCT actually needs?
>
> **Method.** 41-district ground-truth manifest from the DB's `human_provided` schedules (grade-band, 24h-normalized). Scored on the **LCT-relevant metric**: per grade band, does the model's *modal* instructional minutes (end−start) match GT within **±15 min**? Three reading methods × several models, plus one cloud model. Harness: `infrastructure/scripts/benchmark/` (`run_manifest_benchmark.py`, `reading.py`, `extractors.py`, `score_minutes.py`).

## Results

**Reading-method comparison — 15-district subset (local models):**
| Model | Reading | Band match % | Median \|err\| |
|---|---|---:|---:|
| mistral:7b | text (pdftotext/OCR) | **42.3** | 5 min |
| qwen2.5:7b | text | **42.3** | 5 min |
| qwen2.5-VL | **vision** (image) | 36.4 | 24 min |
| llama3.1 / mistral / qwen2.5 | **table-aware** | 34.6 | **0–1.5 min** |
| llama3.1:8b | text | 30.8 | 5 min |
| qwen2.5-VL | table-aware (text) | 23.1 | 0 |

**Apples-to-apples — 5 cloud-test districts, all on table-aware input:**
| Model | Band match % | Median \|err\| | Districts hit |
|---|---:|---:|---:|
| **Claude Haiku** (cloud, via subscription) | **53.3** | 0 | 80% |
| llama3.1:8b (local) | 46.7 | 7.5 | 100% |
| qwen2.5:7b (local, text) | 46.7 | 10 | 60% |
| qwen2.5:7b (local, tables) | 40.0 | 4 | 80% |
| qwen2.5-VL (vision) | 33.3 | 77 | 50% |

**Gemini Flash:** *now run (2026-06-13)* via a direct API key (`gemini:gemini-2.5-flash` through the harness provider). It is the **top performer** — see the update section below.

## Key findings

1. **Everything plateaus at ~35–53%.** No model/reading combo "solves" extraction. **Plain text on a 7B model (mistral/qwen2.5, ~42%) is the best *local* approach.**
2. **Better reading did NOT beat plain text on the aggregate.** Vision (36%) and table-aware (35%) both trailed plain text — *but* table-aware is far more **precise when it hits** (median error ~0 vs 5 min); it just matches fewer bands. Vision reads more but **locks onto early-release columns** (high error, 24 min).
3. **A stronger model is the biggest lever — modestly.** Haiku (53%) beat the best local (47%) on the same inputs, confirming the *model's reasoning* (not just the reading) is a limiter. But 53% is still only ~half the bands.
4. **Much of the remaining gap is input/ground-truth quality, not model capability:**
   - **Corrupt source data** — Montgomery AL's PDF tags end times "AM" (`2:15:00 AM`); no model can fix that.
   - **Wrong HTML extracted** — KIPP DC's schedule isn't in a parseable `<table>`; `pandas.read_html` pulled nav menus.
   - **Transposed tables** — WY's start-row/end-row-by-grade-column defeats 7B models even when `pdfplumber` recovers the cells cleanly (the structure is there; the small model mis-aligns it).
   - **Ground-truth limits** — many districts have GT for only one band; the representative-school + modal-minutes metric undersells correct extractions. **Absolute numbers understate true capability; relative rankings are the reliable signal.**
5. **Reading-method validation** (independent of scores): table-aware (`pdfplumber`/HTML) genuinely **recovers the structure pdftotext destroys** (grade-column headers, school↔time association). Where the input is clean and the model capable, it's exact (median 0).

## Recommendation

- **No silver bullet.** Best automated combo ≈ **50%** (capable model + table-aware/text reading) — **not production-ready unattended.**
- **The levers that matter now are not model selection:**
  1. **Input quality** — route by format: table-aware for digital PDFs, OCR/vision for image PDFs, *smarter HTML* (KIPP-style schedules need targeted scraping, not `read_html`), and **reject/flag corrupt sources**.
  2. **Ground-truth quality** — better, multi-band GT to reveal the true ceiling (current metric is noisy).
  3. **Dual-path consensus + human review of disagreements** — given ~50% automated accuracy, two independent extractors that auto-accept on agreement and flag disagreements is the realistic quality path at scale.
- **Model choice:** a capable cloud model (Haiku-class) edges local 7B; a larger local model on the planned headless server is the local way to chase that. But the bottleneck is *shared* across models (inputs + GT + reasoning), so don't over-invest in model selection alone.
- **Strategic:** local 7B extraction (~35–42%) isn't accurate enough for unattended scale; plan for human-QC on flagged disagreements regardless of which model wins.

## Update (2026-06-13): full 41-district cloud-model run

Re-ran on **all 41 districts** with the cloud models the first pass lacked: **Gemini 2.5 Flash** (direct API, text + tables) and **Sonnet 4.6 / Opus 4.8** via Claude subagents on identical table-aware input + the same `LEAN_SYSTEM_PROMPT` (the Haiku method — there is no Anthropic API key, so subagents stand in). Same modal-minutes ±15 metric.

| Model | Mode | Districts | Band match | Median \|err\| | Dist hit |
|---|---|---:|---:|---:|---:|
| **Gemini 2.5 Flash** | tables | 39 | **68.9** | 0 | 69% |
| **Gemini 2.5 Flash** | text | 39 | **68.9** | 0 | 67% |
| **Opus 4.8** | tables | 40 | **62.3** | 0 | 70% |
| Haiku 4.5 | tables | 5* | 53.3 | 0 | 80% |
| **Sonnet 4.6** | tables | 40 | **45.5** | 10 | 50% |
| best local (llama3.1:8b) | tables | 17 | 37.5 | 2.5 | 47% |
| locals | text | 39 | 25–28 | 15 | ~36% |

\*Haiku ran only the original 5-district subset.

**Revised conclusions:**
1. **Model strength is a bigger lever than the first pass concluded.** A capable cloud model roughly **doubles** the best local (Gemini Flash 68.9% / Opus 62.3% vs ~37% local tables / ~28% local text). The earlier "~53% cloud ceiling / modest lever" was an artifact of testing only Haiku on 5 districts.
2. **Cheapest = best.** Gemini 2.5 Flash tops the board in *both* reading modes and is the lowest-cost option tested — a strong steer for the cascade's default extractor (REQ-046/048/053).
3. **Still ~69%, not production-ready unattended.** The do-it-right plan stands: format-aware reading + independent-pathway consensus + human-QC of disagreements, with statutory fallback (REQ-046/048/049).
4. **The 5-district subset was NOT representative.** An interim subset put Sonnet at 86.7%; on the full set Sonnet is 45.5%. Don't trust small subsets — this run exists because the subset misled.
5. **The modal-minutes metric penalizes thorough extractors.** Sonnet extracted up to 20 schools/district (9 districts ≥8); its *modal* band value then diverges from GT's single reference school → 45.5% with median error 10, despite individually-plausible reads. Opus stayed conservative (max 12, median err 0). **So "Sonnet < Opus" here is substantially a scoring artifact, not worse reading**, and the metric understates the most thorough extractors. **Next step: a per-school scoring pass** (match each extracted school to its own correct minutes) to rank fairly; single-value GT can't.

Method: Gemini via direct API; Sonnet/Opus via subagents grounded only on the captured artifact text (no web, no prior knowledge — REQ-053). Leaderboard: `data/benchmark_results/leaderboard_minutes.md`.

## Update 2 (2026-06-13): multi-provider conduits + "top-shelf" sweep

After the full-41 cloud run we added two **multi-model conduits** to the harness so any frontier or open-weight model can be benchmarked through the same pipeline — with **search kept separate from the LLM** (REQ-053; the model only reads the captured artifact, web search off):

- **`pplx:` — Perplexity Agent API** (SDK `responses` resource → `POST /v1/agent`). `tools` omitted ⇒ no web search ⇒ grounded extraction. Note: Perplexity's `chat/completions` is **Sonar-only** (search-fused) and rejects third-party model ids; the **Agent API** is the multi-model surface. Catalog: `GET /v1/models`.
- **`openrouter:` — OpenRouter** (OpenAI-compatible, `base_url=https://openrouter.ai/api/v1`); ~337 models, one key — a *second independent conduit*, useful for cross-family consensus. **Free-tier (`:free`) models are too rate-limited (429s) to benchmark — use the paid endpoints (pennies).** Both providers live in `extractors.py`.

**Top-shelf sweep — 7-district sample, modal-minutes ±15 (identical 7 districts for every model):**

| Model | Band match | Median \|err\| | $/1M in/out |
|---|---:|---:|---|
| Gemini 2.5 Flash (text) | **88.2** | 0 | cheap |
| **xai/grok-4.3** (pplx) | **88.2** | 0 | 1.25/2.50 |
| Gemini 2.5 Flash (tables) | 76.5 | 0 | cheap |
| openai/gpt-5.4 (pplx) | 76.5 | 0 | — |
| Opus 4.8 / gpt-5.5 / Sonnet 4.6 | 70.6 | 0 | — |
| deepseek-v3.2 / llama-3.3-70b / **mistral-small-24b** | 64.7 | 0–5 | 0.23 / 0.10 / **0.05** |
| qwen3-30b / qwen3-next-80b | 58.8 | 0 | 0.05 / 0.09 |
| openai/gpt-oss-120b | 35.3 | 5 | 0.04 |
| z-ai/glm-4.7-flash | 0\* | — | — |

\*GLM produced no parseable output — an integration/format issue to fix, **not** a clean accuracy fail.

**What it tells us** (relative ranking only — the 7-set inflates absolute %s; the full 41 is the truth):
1. **Grok-4.3 ties Gemini 2.5 Flash at the top**, and it's a *different lab* — making **Gemini 2.5 Flash + Grok-4.3 the standout independent consensus pair** for REQ-048 (peer accuracy, decorrelated errors; two Gemini variants would not give that). DeepSeek V3.2 is the cheaper cross-family alternative.
2. **Bigger ≠ better:** gpt-5.4 (76.5%) beat gpt-5.5 (70.6%); Opus tied Sonnet.
3. **Cheap open-weight is viable and self-hostable:** DeepSeek V3.2, Llama-3.3-70B, and **Mistral Small 24B (~$0.05/1M)** all hit 64.7% — candidates for the Ubuntu server's local path.
4. The over-extraction/modal confound persists (Update finding 5); at n=7, a band or two is noise.

**Discovery (separate problem, encouraging):** the Perplexity **Search API** (`search.create`) returned a school-subdomain `/schedules` page for Sweetwater in **one call** — a page the Crawlee crawl (126 s, 49 pages) never reached. First concrete evidence that **search-led discovery works where blind crawling failed** (REQ-043; see also the acquisition probe).

**Full-41 open-weight + frontier run — see Update 3 below** (completed; cheap open-weight holds up).

Infra notes: Gemini MCP model fixed (`config.js` 2.0→2.5-flash) but the harness uses the **direct API**, not MCP. Keys in gitignored `.env` / `config/secrets.local.json`. Leaderboard: `data/benchmark_results/leaderboard_minutes.md`.

## Update 3 (2026-06-13): definitive full-41 leaderboard (~14 models, OpenRouter + native)

Ran DeepSeek V3.2 + V4-Pro, Llama-3.3-70B, Mistral Small 24B + Large 2512, Command R+, Granite 4.1 8B, Qwen3-235B-2507 + Qwen3.7-Max, Grok 4.3, and Gemini 3.5 Flash + 3.1 Pro — all on the **full 41**, tables mode, modal-minutes ±15. (The 7-district Perplexity-Agent sweep numbers are excluded here as inflated.)

| # | Model (tables) | Band match | Med \|err\| | Dist hit | $/1M in·out |
|---|---|---:|---:|---:|---|
| 1 | **Gemini 2.5 Flash** (text & tables) | **68.9** | 0 | 67–69% | 0.30·2.50 |
| 2 | Mistral Large 2512 | 67.6 | 0 | 72% | 0.50·1.50 |
| 2 | Qwen3.7-Max | 67.6 | 0 | 74% | 1.25·3.75 |
| 4 | DeepSeek V3.2 | 66.2 | 0 | 72% | 0.23·0.34 |
| 5 | **Mistral Small 24B** | 63.5 | 0 | 74% | **0.05·0.08** |
| 5 | Grok 4.3 | 63.5 | 0 | 67% | 1.25·2.50 |
| 7 | Opus 4.8 | 62.3 | 0 | 70% | 5·25 |
| 8 | Llama 3.3 70B | 59.5 | 0 | 67% | 0.10·0.32 |
| 9 | Command R+ / Qwen3-235B-2507 | 58.1 | 0 | 62–74% | 2.50·10 / 0.09·0.10 |
| 11 | **Granite 4.1 8B** | 51.4 | 10 | 64% | 0.05·0.10 |
| 12 | DeepSeek V4-Pro | 45.9 | 0 | 46% | 0.43·0.87 |
| 13 | Sonnet 4.6 | 45.5 | 10 | 50% | 3·15 |
| — | best local (llama3.1:8b) | 37.5 | — | 47% | free |

**Conclusions:**
1. **The 7-district smoke was inflated** — Grok 4.3 fell 88%→**63.5%** at full scale; Gemini 2.5 Flash held **68.9%**. Always validate on the full set.
2. **Cheap wins.** Gemini 2.5 Flash leads; **Mistral Small 24B ($0.05/1M) ties Grok 4.3 and beats Opus**; the top is a tight ~58–69% cluster of mostly-cheap models.
3. **Bigger ≠ better.** The *biggest* DeepSeek (V4-Pro) landed near the bottom (45.9%, 46% district-hit); Opus (62%) trails several far-cheaper models; GPT-5.5 < GPT-5.4 (smoke).
4. **Granite 4.1 8B (51.4%)** — an 8B, ~$0.05/1M, **self-hostable** model beat Sonnet and all locals → strong candidate for the headless-server local path.
5. **~69% is the full-41 ceiling** — no model is production-ready unattended; the consensus + human-QC plan (REQ-048/049) stands.
6. **Metric confound persists** — modal-minutes penalizes over-extraction (Sonnet/Granite med-err 10; V4-Pro low district-hit). The **per-school scoring pass** would likely re-rank these and is the recommended next scoring fix.

**Practical read for the pipeline:** default extractor = **Gemini 2.5 Flash** (top + cheap); independent cross-family consensus partner = **DeepSeek V3.2** or **Mistral Large/Small** (peer accuracy, decorrelated, cheap); local/self-host path = **Granite 4.1 8B** or a Qwen3. Leaderboard data: `data/benchmark_results/leaderboard_minutes.md`.

## Update 4 (2026-06-20): real per-call cost from OpenRouter activity logs

Replaced chars/4 cost *estimates* with **measured `tokens_prompt`/`tokens_completion`** from the OpenRouter activity export (2026-06-14 extraction runs; web-search rows excluded). Council candidate set narrowed to **6 non-reasoning models** — **Grok 4.3 and Qwen3.7-Max removed** (neither scored 100% on difficulty>0.70, and both are reasoning models whose hidden reasoning tokens make them 4–70× pricier; see below).

**Measured per extraction call** (median tokens; one captured document in):

| Model | in (med) | out (med) | reasoning (med) | **$ / call (measured)** |
|---|---:|---:|---:|---:|
| Mistral Small 24B | 2,583 | 345 | 0 | **$0.00022** |
| Gemini 2.5 Flash-Lite | 1,982 | 434 | 0 | **$0.00050** |
| Qwen3-235B-2507 | 2,424 | 185 | 0 | **$0.00060** |
| DeepSeek V3.2 | 2,361 | 318 | 0 | **$0.00102** |
| Gemini 2.5 Flash † | ~1,982 | ~434 | 0 | **~$0.00168** (est.) |
| Mistral Large 2512 | 3,424 | 314 | 0 | **$0.00265** |
| *(removed)* Grok 4.3 | 3,162 | 944 | **742** | $0.00680 |
| *(removed)* Qwen3.7-Max | 3,344 | 2,582 | **2,322** | $0.01571 |

† Gemini 2.5 Flash was run on the **native Google API** (not in the OpenRouter log); derived from the Flash-Lite token profile at Flash pricing ($0.30/$2.50). Going forward, extraction standardizes on **OpenRouter** (`google/gemini-2.5-flash`).

**Per-district cost = (schools processed) × (per-call) × (council size).** Single non-reasoning model, one call per sampled school:

| District size | Mistral Small | Flash-Lite | Gemini Flash | Mistral Large |
|---|---:|---:|---:|---:|
| 10 schools | $0.002 | $0.005 | $0.017 | $0.027 |
| 50 schools | $0.011 | $0.025 | $0.084 | $0.133 |
| 100 schools | $0.022 | $0.050 | $0.168 | $0.265 |

A **3-model non-reasoning council** (Gemini Flash + DeepSeek V3.2 + Mistral Small ≈ **$0.0029/call**): a 50-school district ≈ **$0.15**; a 340-school Broward ≈ **$1.0**.

**Cost conclusions:**
1. **The real cost cliff is reasoning-vs-not, not sticker price.** Qwen3.7-Max burns ~2,322 hidden reasoning tokens/call → **$0.0157/call (~70× Mistral Small)**; Grok 4.3 ~742 → $0.0068. The 6 retained models are all **≤ $0.0027/call**.
2. **Output (schedules JSON) drives cost for high-out-price models** — a model that over-extracts schools costs more, so concise/targeted per-school inputs are cheaper *and* more accurate.
3. **Money is not the constraint.** Even the priciest sensible council stays **~$1/district** at the largest districts; the binding limits are input quality and (downstream) human-QC time, not API spend.

## Caveats
Small/noisy samples (locals on 17 table / 39 text districts; Haiku on 5 only); modal-minutes ±15-min metric that penalizes thorough multi-school extraction (see Update finding 5); incomplete/single-value GT; vision prompt unoptimized (early-release unsolved). Treat absolutes as directional; relative rankings are the reliable signal.
