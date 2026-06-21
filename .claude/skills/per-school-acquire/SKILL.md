---
name: per-school-acquire
description: Run the per-school bell-schedule acquisition pipeline for one or more districts — wave discovery (Claude WebSearch -> OpenRouter), tiered capture, Path-1 council extraction, modal aggregation, score/store. Use when acquiring or testing instructional minutes for specific district IDs.
---

# /per-school-acquire — Per-School Acquisition Pipeline

Orchestrates the validated per-school pipeline (see `docs/ACQUISITION_PIPELINE.md`). Exists as a **skill, not a script**, because **Wave 1 (Claude WebSearch) can only run from inside the agent** — it spawns a Haiku WebSearch subagent, which a plain `.py` cannot do. The skill is the glue; the `.py` workers do the deterministic stages.

**Tradeoff to state once per run:** this leverages the Claude subscription (flat-rate, run overnight), so it is **agent-in-the-loop, not lights-out**. Fully unattended runs would require dropping Wave 1 for an API-only path (lower coverage, real per-call cost).

## Discovery wave order (decided 2026-06-20, evidence-based)
1. **Claude WebSearch** via Haiku subagent (sunk subscription cost) — first wave.
2. **OpenRouter `gpt-4o-mini-search`** (API) — only on the **residual** schools Wave 1 didn't satisfy.
3. **Flag for manual** — schools neither wave satisfies.
**Perplexity is dropped** (full-41: 31/41 coverage = lowest, fewest pages, hub-skewed reach).

## Inputs
- Argument: comma-separated NCES LEA district IDs (e.g. `0626910,5605302`).
- Optional: `--max-schools N` (per-band cap, default 12), `--cap K` (candidate URLs/school, default 3).
- Keys: export `OPENROUTER_API_KEY` from `config/secrets.local.json` before wave 2 / extraction.

## Steps (run in order)

1. **Roster + queries.** Run:
   `python3 infrastructure/scripts/benchmark/discovery/per_school_run.py roster <ids> --max-schools 12`
   Writes `data/benchmark_results/per_school/<id>/roster.json` (per-school queries + `allowed_domains`).

2. **Wave 1 — Claude WebSearch (THIS IS THE AGENT'S JOB).** For each district, read its `roster.json` and spawn **one Haiku subagent per district** (chunk if a district has many schools). Instruct the subagent: use ONLY the `WebSearch` and `Write` tools; for each school run WebSearch on its `query` with `allowed_domains` set to the district domain (unscoped if empty); collect result URLs; **Write** `data/benchmark_results/per_school/<id>/claude_urls.json` as a JSON object `{"<school name>": ["url", ...], ...}` keyed EXACTLY by the `school` strings in roster.json. Do not guess URLs — only report what WebSearch returns. (Run subagents in background; they're independent across districts.)
   **Also classify TOPOLOGY** (the subagent's second job) **strictly from the search results — do NOT open/read pages**: add a top-level key `"topology"` to `claude_urls.json` = one of `"hub"` (multiple schools' schedules surface on a single district URL), `"per_school"` (distinct per-school subdomain/pages), or `"none"` (neither found). This routes the downstream branch (capture-hub-once-and-fan vs. extract-each-school). Whether a hub *renders* cleanly vs. is an expanding/accordion edge case is NOT the subagent's call — that's determined at capture.

3. **Wave 2 — OpenRouter residual.** After Wave 1 subagents finish, run:
   `python3 infrastructure/scripts/benchmark/discovery/per_school_run.py wave2 <ids> --cap 3`
   This gates the Claude URLs and runs OpenRouter `gpt-4o-mini-search` ONLY on schools Wave 1 left empty, then writes `per_school_candidates.json`. Reports wave1-satisfied / wave2-ran / manual-flag counts.

4. **Flatten + dedup.** Run:
   `python3 infrastructure/scripts/benchmark/discovery/per_school_run.py flatten <ids>`
   Dedups candidates across schools → `candidates.json` (one capture per distinct page; hub pages collapse).

5. **Capture (tiered, local Playwright).** From `infrastructure/scraper/`:
   `node capture_discovery.mjs <abs path to data/benchmark_results/per_school> 6`
   Text-layer preferred; screenshot+OCR fallback for image pages. Writes `captures.json` + `captures/`.

6. **Extract (Path-1 council) + aggregate + score.** Run:
   `python3 infrastructure/scripts/benchmark/discovery/council_extract.py <id>`
   Voters = Mistral Small 24B + Gemini 2.5 Flash-Lite + Qwen3-235B (3 families); judge = DeepSeek V3.2 (4th family) on no-consensus. **Target = GROSS daily minutes (last-bell end − first-bell start); no lunch/passing/recess deductions, no assumed deductions.** Models extract per-school start/end rows; **code computes the modal band value deterministically** (never ask a model to pick the "typical" schedule). Cross-family agreement (±15 min) → accept; else judge (plausibility gate ~240–510 min); aggregate modal→mean per band; score vs GT if present. Writes `council_result.json`.

7. **Report.** Summarize per district: wave coverage (claude/openrouter/manual), distinct pages captured, judge escalation rate, per-band district values + GT match. Flag capture failures (0-time pages) and hub-routed bands explicitly.

## Notes
- **Cross-family is mandatory** for council acceptance — same-family agreement (two Google, two Mistral) is NOT consensus. See `docs/technical-notes/LLM_COUNCIL_RESEARCH_2026-06.md`.
- **Dedup matters**: hub-dominant districts (e.g. Christina ~20/21 schools share one page) should capture/extract the hub once and fan values to covered schools — `flatten` handles this.
- **Known gates**: capture fidelity (JS/image pages may render empty → manual flag) and unlabeled multi-school hub ambiguity (band row→school unclear). Surface these in the report, don't silently accept.
- For pure plumbing tests without the subscription, Wave 1 can be skipped (empty `claude_urls.json`) and everything falls to Wave 2 — but note in the report that this is NOT the production config.
