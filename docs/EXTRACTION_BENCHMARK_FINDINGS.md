# Bell-Schedule Extraction Benchmark — Findings (2026-06-12)

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

**Gemini Flash:** *not run.* The configured `gemini` MCP is pinned to `gemini-2.0-flash` (retired → 404) and exposes no model selector. Testing Flash 2.5 needs the MCP reconfigured or an API key — deferred by decision.

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

## Caveats
Small/noisy samples (5–15 districts, 9–26 scored bands); modal-minutes ±15-min metric; incomplete GT; vision prompt unoptimized (early-release unsolved) and 2 vision districts incomplete; Haiku on 5 districts only. Treat absolutes as directional.
