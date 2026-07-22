# Model field notes — observed per-model characteristics (living doc)

> **Authority:** the accumulating record of what THIS project has observed about specific models'
> behavior, across every place we use them — the extraction councils (Stages 6/7), the discovery
> cascade (Stage 2), the local-Ollama era benchmarks, and the cross-family external code-review
> harness (PR #477). Started 2026-07-15 in anticipation of the **Council Lab** (#80/#103) so
> composition decisions start from field evidence, not vendor claims.
> **Audience:** whoever composes a council, tunes the external-review roster, or evaluates a new model.
> **Update this when:** any run surfaces a new per-model behavior (a failure mode, a lens, a cost
> surprise). Append with a date; never silently revise an old observation — supersede it.
> **Companions:** `LLM_COUNCIL_RESEARCH_2026-06.md` (the literature: diversity > count, judge > vote,
> cascades); `../CROSSFAM_EXTERNAL_REVIEW_2026-07-13.md` (the review campaign's full per-model
> analysis — numbers here are distilled from it, not re-derived); `docs/technical-notes/learning-loop-reports/EXTRACTION_BENCHMARK_FINDINGS.md`
> (the 2026-06 extraction leaderboard); `EXTRACTION_TOKEN_SIZING_2026-07-06.md` (output-ceiling
> behavior). Receipts: `data/review/crossfam-2026-07-13/` (raw_findings/adjudications/raw_replies with
> per-call `usage.cost`).

---

## 0. How to read this

Three different jobs have generated model evidence, and a model's character differs by job:
- **Extraction voter/judge** (read a captured page, return per-school times — REQ-054's read-only role);
- **External review finder/judge** (read code shards, file findings; adjudicate others' findings);
- **Discovery** (not a model job anymore — the SERP cascade decision stands: the *index* predicts
  recall, and own-index providers crater on long-tail K-12; Claude WebSearch survives only as the
  Wave-2 residual sweep).

A recurring meta-lesson across all three: **per-model numbers are snapshots against a moving target**
(a fixed codebase, one GT vintage) — re-measure before acting on any of them (the CROSSFAM doc's §5
framing; the Stage-5 V1→V2 drift lesson).

---

## 1. Per-family notes

### google/gemini
- **gemini-2.5-flash** — the 2026-06 extraction leaderboard's top performer (68.9% band-match on the
  41-district GT, beating Opus 4.8's 62.3% and every local model). Vision-council voter today.
- **gemini-2.5-flash-lite** — text-council voter (`low-cost-text`). As a review finder: cheap and
  productive ($0.19 for 36 shards, 216 confirmed/$) but the **lowest precision of the roster (0.27)**
  — a volume finder whose candidates need corroboration. 49% of its raw findings were single-family
  (median-ish for the roster).
- **gemini-2.5-pro** (review judge) — no family favoritism detected (leans +0.11 toward its family
  finder, not significant under the controlled test).

### mistralai
- **mistral-small-24b-instruct-2501** — text-council voter. Cheap (~$0.05/1M — the "cheap open-weight
  models are viable" finding). **Hard 32k context ceiling, and it BITES on snake/hub docs
  (2026-07-15, Broward #121 re-test):** the Stage-7 output pre-sizing (`size_max_tokens()` from the
  roster time-count, #180/#187) requested 26,790 output tokens for the 760-time snake PDF — 33,041
  total vs the 32,768 limit → hard 400 error, zero facts from this voter. The cross-family design
  absorbed it (Gemini + Qwen judge reached consensus; E=360/M=400/H=420 all correct), but on the
  largest hub docs this voter is **systematically absent**, quietly degrading the council to
  voter+judge. **Council-Lab consideration: a voter's context ceiling should be a council-assignment
  input** — route mega-docs to large-context voters, or accept the judge-fallback shape knowingly.
- **mistral-large-2512** — vision-council voter. No incident on file.
- **devstral-2512** (review finder) — mid-pack everything (56 confirmed, 0.37 precision, 93/$);
  highest overlap with gemini-flash-lite (Jaccard 0.28) — the two most redundant finders.
- *(Local era, archived)* mistral:7b — best *local* text extractor (42.3%), long superseded.

### qwen
- **qwen3-235b-a22b-2507** — the text council's JUDGE (third family, re-reads the page on voter
  disagreement). Carried the Broward re-test when Mistral errored out.
- **qwen3-vl-235b** — vision-council judge.
- **qwen3.7-plus** (review finder) — 2nd-highest absolute yield (96 confirmed) at good precision
  (0.60), but ~$1.24/sweep = middling efficiency. Second-lowest singleton rate (42%) — what it finds,
  others tend to find too.

### deepseek
- **deepseek-v4-flash** (review finder) — **the value king: 325 confirmed/$** (65 confirmed for
  $0.20). Moderate precision (0.43). Notable from the singleton probe: **37 critical-severity
  singletons** — the most of any finder — i.e., it flags severe-looking issues no other family
  corroborates; whether those are unique catches or severity inflation is exactly the
  `--min-agree 1` question the CROSSFAM doc defers.
- **deepseek-v4-pro** (review judge) — the one statistically significant family effect, and it's
  *negative*: measurably **stricter on its own family's findings** than peer judges (p=0.004) —
  family judging adds skepticism, not collusion.

### moonshotai
- **kimi-k2.5** (review finder) — **highest absolute yield (106 confirmed) and best finder precision
  (0.72)**; the security lens (most security findings, 29). Cost ~$1.22/sweep. The premium
  all-rounder of the review roster.

### meta-llama
- **llama-4-maverick** (review finder) — data-integrity heavy (135). **The idiosyncrasy outlier from
  the singleton probe: 68% of its raw findings were single-family** — two-thirds of what it reports,
  nobody else sees. Combined with decent confirmed precision (0.41) on the corroborated set, it reads
  as a high-noise finder whose overlapping fraction is solid — corroboration is doing the filtering.

### openai
- **gpt-4.1-mini** (review finder) — mid-pack (48 confirmed, 0.39 precision); **zero critical-severity
  singletons** — the most conservative severity-assigner of the roster.
- **gpt-5.6-luna** (review judge) — no family-favoritism signal (−0.06, n.s.).

### x-ai
- **grok-build-0.1** (review finder) — the race/concurrency lens (most, 16). Expensive ($2.65/sweep,
  worst-tier 30/$) **but earns the slot on coverage: sole corroborator on 31 confirmed** — the finder
  whose removal would cost the most confirmed findings.
- *(Extraction era)* Grok-4.3 tied Gemini 2.5 Flash on the 2026-06 leaderboard — the original
  "Gemini + Grok independent-consensus pair" recommendation predates the current cheap-council design.

### minimax / xiaomi
- **minimax-m2.7** (review finder) — best precision-per-noise profile in the singleton probe (36%
  singleton rate, lowest) but 9 call errors (runner-up reliability concern). Mid-everything.
- **xiaomi/mimo-v2.5-pro** (review finder) — the paradox model: **highest precision (0.86) + the only
  data-integrity-first lens**, yet worst value/$ (30), worst reliability (10 errors + 4 empties),
  lowest marginal value (sole corroborator on just 14). The CROSSFAM doc's "scrutinize but don't
  drop without re-measuring" case.

### Reasoning-model caveat (roster-level)
z-ai/glm-4.7-flash and gpt-5.1-codex-mini were dropped from the review roster **pre-run**: reasoning
models that stream thinking the shared client can't capture → empty content. A model that can't
return plain completions through the OpenRouter client is unusable in these harnesses regardless of
quality (`tools/crossfam_review/roster.py`).

---

## 2. Cross-cutting lessons (the ones composition decisions hang on)

1. **Diversity buys category coverage, not just redundant confirmation** — finders have measurably
   different lenses (security/kimi, concurrency/grok, data-integrity/mimo+llama). Same conclusion as
   the extraction council's cross-family rule (REQ-056), measured in a second domain.
2. **Universal agreement essentially never happens** (0 of 459 candidates hit all 10 families) —
   demanding high agreement is a recall killer; ≥2 cross-family is the working corroboration bar.
3. **The judge cascade is collusion-free** — and family judges skew *stricter* if anything. REQ-056's
   rotating third-family judge validated in a second domain.
4. **Corroboration masks solo value both ways**: singleton rates run 36–68% by model. The uncorroborated
   pile (1,374 of 1,833 unique findings) holds either each model's noise or its unique catches — the
   deliberately-unmeasured `--min-agree 1` question. Don't read "confirmed contribution" as solo skill.
5. **Context/output ceilings are a composition constraint, not a footnote** — the Mistral 32k incident
   (§1) shows output pre-sizing can push a small-context voter out of exactly the documents where a
   second voter matters most (mega hub docs). Pair voters with complementary ceilings.
6. **Uncontrolled per-model numbers lie** — the family-collusion test flipped sign once finder quality
   was controlled; precision comparisons need denominators from the same candidate pool. (Same
   discipline as the promotion gate's ICC/DEFF correction.)
7. **Snapshots go stale by construction** — review numbers were measured against a codebase whose
   confirmed bugs are now being fixed; extraction numbers against a GT vintage that grows (gate@8).
   Re-measure before every roster/composition decision. That re-measurement harness IS the Council
   Lab's job (#80/#103, `cost_benchmark`).

---

## 3. Provenance

| claim class | source |
|---|---|
| Review-campaign per-model numbers | `../CROSSFAM_EXTERNAL_REVIEW_2026-07-13.md` §§1–6 + `data/review/crossfam-2026-07-13/` receipts |
| Singleton probe (36–68% rates, crit-singleton counts) | computed 2026-07-15 from `raw_findings.json` (family-bucketed by file + line-decade + category, the harness's dedup key) |
| Extraction leaderboard (Gemini 68.9% etc.) | `docs/technical-notes/learning-loop-reports/EXTRACTION_BENCHMARK_FINDINGS.md` (2026-06-12/13) |
| Mistral 32k snake-doc incident | #121 re-test 2026-07-15 (Broward, `camelot_hybrid.txt`, 760 times; OpenRouter 400: 33,041 requested vs 32,768 max) |
| Council composition + diversity rule | `common/config/council_configs.json` (REQ-056; validated in `stage6_handoff/councils.py`) |
| Discovery = index-not-model | `stage2-discovery-provider-decision` (2026-06-28 five-provider bake-off) |
