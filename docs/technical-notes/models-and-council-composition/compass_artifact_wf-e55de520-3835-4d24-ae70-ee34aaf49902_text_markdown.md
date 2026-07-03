# Model Selection & Council Composition for a K-12 Bell-Schedule Extraction Pipeline (OpenRouter)

## TL;DR
- **Keep the text council largely as-is** (it is already excellent at 95.2% band / 99.3% per-school accuracy for $0.065/205 calls) but swap the judge to a cheaper distinct family and add a table-specialist voter; **the vision council's broken judge is fixable today** by replacing text-only `deepseek/deepseek-v3.2` with a vision-capable third family — best options are `qwen/qwen3-vl-235b-a22b-instruct` ($0.20/$0.88 per M), `google/gemini-2.5-flash-lite` ($0.10/$0.40), or `anthropic/claude-haiku-4.5` ($1/$5).
- **There are at least 9 genuinely-distinct families on OpenRouter** with non-reasoning (or reasoning-disable-able) + strict-JSON + (mostly) vision variants: Google/Gemini, Mistral, Alibaba/Qwen, DeepSeek (text-only), Meta/Llama, OpenAI/GPT, Anthropic/Claude, Amazon/Nova, Z.ai/GLM, plus Cohere and xAI/Grok as flags. This is more than enough to build multiple non-overlapping 3-family councils.
- **Cost is a non-issue at this scale** ($0.065 for 24 districts → roughly $55 total across 20,000 districts for text); prioritize accuracy/coverage. The real leverage question is vision, which structurally costs ~15× text per call because image inputs inflate input-token counts (2,600–3,100 in vs ~1,500), not because vision models are pricier per token.

## Key Findings

### The empirical baseline is strong and should anchor all A/B tests
The pilot text council (voters `google/gemini-2.5-flash-lite` + `mistralai/mistral-small-24b-instruct-2501`, judge `qwen/qwen3-235b-a22b-2507` run non-reasoning) hit 95.2% band accuracy (60/63) and 99.3% per-school accuracy (673/678) for $0.065 across 205 calls. The standout value model was `mistral-small-24b-2501` at ~$0.00011/call with zero errors. The vision council under-covers (486 vs 778 accepted schools) and its judge (`deepseek/deepseek-v3.2`) 404'd on every image call because it is text-only — **confirmed**: DeepSeek V3.2 on OpenRouter reports `modality: text→text`, `input_modalities: ["text"]`.

### Cross-family diversity is achievable and the parentage traps are well-defined
The mandatory constraint — 2 voters + judge all from different base-model families — is satisfiable many times over. The critical traps to avoid are "open" models that are actually fine-tunes/distillations of a listed family's base (they share blind spots and produce false consensus).

### Pricing is current as of July 3, 2026 (verified against OpenRouter model pages and the models API)
All per-token figures below were pulled from live OpenRouter model pages and the OpenRouter models API (`/api/v1/models?supported_parameters=structured_outputs`). Where a model has multiple hosting providers, OpenRouter routes across them and the listed price is the representative "balanced" rate; OpenRouter notes these are averages "after prompt caching" and that repeated context can be "60–80% cheaper than the provider list price" (cache reads are charged at ~0.25–0.50× input price for OpenAI/Gemini and ~0.1× for Anthropic).

---

## 1. Role mapping

Token profiles used for $/call: **text** ≈ 1,500 in / 450–650 out; **vision** ≈ 2,600–3,100 in / 300–350 out. Costs computed as (in_tok × in_price + out_tok × out_price)/1e6.

### Role 1 — Cheap reliable text extraction (workhorse voter)
- **`mistralai/mistral-small-3.2-24b-instruct`** — $0.075/M in, $0.20/M out. At 1,500 in / 500 out ≈ **$0.00021/call**. Successor to the pilot's `mistral-small-24b-2501`. Per OpenRouter's model page, v3.2 "delivers gains in tool use and structured output tasks. It supports image and text inputs with structured outputs, function/tool calling, and strong performance across… vision benchmarks (ChartQA, DocVQA)" (128K context). Natural value anchor.
- **`mistralai/mistral-small-24b-instruct-2501`** (the exact pilot model) — confirmed on OpenRouter at **$0.05/M in, $0.08/M out, 32,768-token context** (~$0.00011/call, matching the pilot's measured cost); OpenRouter notes it "achieves 81% accuracy on the MMLU benchmark… competitive with larger models like Llama 3.3 70B and Qwen 32B, while operating at three times the speed." Even cheaper than 3.2.
- **`google/gemini-2.5-flash-lite`** — $0.10/M in, $0.40/M out ≈ **$0.00035/call** at 1,500/500. Thinking is disabled by default (eligible), 1M context, vision + structured outputs confirmed. The pilot's other voter; keep it.
- **`openai/gpt-5-nano`** — $0.05/M in, $0.40/M out ≈ **$0.000275/call**. Distinct family (OpenAI), 400K context, vision + structured_outputs confirmed. Strong cheap alternative for family diversity.

### Role 2 — Dense structured-table extraction specialist (noisy high-yield hub tables)
- **`qwen/qwen3-235b-a22b-2507`** (non-reasoning) — $0.09/M in (some providers $0.071), $0.10/M out ≈ **$0.00019/call** at 1,600/630. Native 262K context (essential for 100+ row tables), no thinking mode, structured_outputs confirmed. The pilot judge; also a strong table voter.
- **`google/gemini-2.5-flash-lite`** — 1M context handles the largest hub tables in one shot; cheap.
- **`mistralai/mistral-large-2512`** (Mistral Large 3, 675B MoE / 41B active) — $0.50/M in, $1.50/M out ≈ **$0.0015/call** at 1,600/630. Higher-capability option for the noisiest tables; 256K context, structured outputs. Use as a table judge rather than everywhere.

### Role 3 — Genuine vision capability + more distinct vision families
Confirmed vision + strict-JSON on OpenRouter, cheapest first:
- **`openai/gpt-5-nano`** — $0.05/$0.40. Vision + structured_outputs confirmed. ≈ **$0.00027/call** at 2,800 in / 330 out.
- **`mistralai/mistral-small-3.2-24b-instruct`** — $0.075/$0.20. Vision + structured outputs; tuned on ChartQA/DocVQA (per OpenRouter page). ≈ **$0.00028/call**.
- **`meta-llama/llama-4-maverick`** — $0.15/$0.60 ≈ **$0.00062/call**. Native multimodal, 1M context, structured_outputs (note: tool-calling not advertised on the listed endpoint).
- **`qwen/qwen3-vl-235b-a22b-instruct`** — $0.20/$0.88 ≈ **$0.00085/call** at 2,800/330; 262,144-token context, 6 providers. OpenRouter's page states it "targets general vision-language use (VQA, document parsing, chart/table extraction, multilingual OCR)," and the Qwen model card adds "advanced OCR in 32 languages… improved long-document structure parsing." Best-in-class doc VLM in this set.
- **`google/gemini-2.5-flash`** — $0.30/$2.50 ≈ **$0.0017/call** at 2,800/330. The pilot vision voter; keep.

### Role 4 — A judge (third distinct family; vision-capable when judging vision)
- **Text judge:** `qwen/qwen3-235b-a22b-2507` (pilot choice, keep) OR cheaper `deepseek/deepseek-v3.2` ($0.23–0.25/M in, $0.34–0.38/M out; text-only — fine for a TEXT judge) to free Qwen for voter duty.
- **Vision judge (fixing the dead judge):** `qwen/qwen3-vl-235b-a22b-instruct`, `google/gemini-2.5-flash-lite`/`gemini-2.5-flash`, `anthropic/claude-haiku-4.5` ($1/$5, vision + structured outputs), or `z-ai/glm-4.5v` ($0.60/$1.80, doc-parsing SOTA but structured-output support unconfirmed).

### Role 5 — Enough distinct families
Confirmed distinct families with non-reasoning + strict-JSON variants: **Google, Mistral, Qwen, DeepSeek (text-only), Meta/Llama, OpenAI, Anthropic, Amazon/Nova, Z.ai/GLM** — plus Cohere (Command A, $2.50/$10) and xAI (Grok-4 family; Grok-4.1-fast lacks structured outputs on OpenRouter). That is ≥9 usable families for non-overlapping councils.

---

## 2. Cross-family analysis

### Genuinely distinct base families on OpenRouter (task-suitable)
1. **Google / Gemini** — `gemini-2.5-flash-lite` ($0.10/$0.40), `gemini-2.5-flash` ($0.30/$2.50). Vision ✓. Thinking off by default on Lite. Structured outputs ✓.
2. **Mistral** — `mistral-small-3.2-24b-instruct` ($0.075/$0.20), `mistral-large-2512` ($0.50/$1.50), `pixtral-large-2411`. Vision ✓. Structured outputs ✓.
3. **Alibaba / Qwen** — `qwen3-235b-a22b-2507` (text, $0.09/$0.10), `qwen3-vl-235b-a22b-instruct` (vision, $0.20/$0.88). Non-reasoning instruct variants ✓. Structured outputs ✓.
4. **DeepSeek** — `deepseek-v3.2` ($0.23–0.25/$0.34–0.38). **TEXT-ONLY** (confirmed: `input_modalities: ["text"]`, explains the pilot's 404s). Structured outputs ✓. Reasoning can be disabled.
5. **Meta / Llama** — `llama-4-maverick` ($0.15/$0.60, vision, 1M ctx), `llama-3.2-90b-vision`. Structured outputs ✓.
6. **OpenAI / GPT** — `gpt-5-nano` ($0.05/$0.40), `gpt-4.1-mini` ($0.40/$1.60). Vision ✓. Structured outputs ✓.
7. **Anthropic / Claude** — `claude-haiku-4.5` ($1/$5, 200K ctx). Vision ✓. Structured outputs GA'd recently (verify live).
8. **Amazon / Nova** — `nova-lite-v1` ($0.06/$0.24, vision, but **no json_schema** — tools/json_object only), `nova-2-lite-v1` ($0.30/$2.50, structured outputs probable, verify).
9. **Z.ai / GLM** — `glm-4.5v` ($0.60/$1.80, vision, doc-parsing SOTA). Hybrid; run non-thinking.

### Parentage / decorrelation traps (NOT truly distinct)
- **`pixtral-large-2411` is built on `mistral-large-2411`** (per OpenRouter's Pixtral page) — same Mistral base as `mistral-large-2512`/`mistral-small`. Do NOT pair Pixtral with another Mistral and call it cross-family.
- **`deepseek-r1-distill-qwen-*`** are Qwen fine-tunes — correlated with Qwen, not DeepSeek's own base.
- **`mistral-small-3.2` vs `mistral-small-24b-2501`** — same base lineage; the pilot's two Mistrals are the same family (fine, but they don't add decorrelation).
- Many "open" leaderboard models are Llama or Qwen fine-tunes underneath; treat any unfamiliar open model as guilty-until-proven-distinct.
- **Amazon Nova, Cohere Command, Z.ai GLM, xAI Grok** are independently-trained bases — genuinely decorrelated from the big four.

Vision-capable distinct families: Google, Mistral, Qwen (VL), Meta/Llama, OpenAI, Anthropic, Amazon/Nova, Z.ai/GLM. **DeepSeek is the notable text-only exception** and cannot be a vision judge.

### Proposed council compositions (2 voters + judge, all distinct families)

**(a) Cheap text councils** (beat/match baseline $0.00011–$0.00054/call)
- **A1 (closest to pilot):** voters `gemini-2.5-flash-lite` (Google) + `mistral-small-3.2-24b-instruct` (Mistral) → judge `qwen3-235b-a22b-2507` (Qwen). ~$0.00021–$0.00035/voter call, $0.00019 judge.
- **A2 (cheapest, new family mix):** voters `mistral-small-24b-instruct-2501` (Mistral, ~$0.00011) + `gpt-5-nano` (OpenAI, ~$0.00028) → judge `deepseek-v3.2` (DeepSeek, text-only, ~$0.00040). Three distinct families, all cheap.
- **A3 (family-diverse):** voters `gemini-2.5-flash-lite` (Google) + `qwen3-235b-a22b-2507` (Qwen) → judge `deepseek-v3.2` (DeepSeek).

**(b) Table-specialist text councils** (optimize dense hub-table accuracy)
- **B1:** voters `qwen3-235b-a22b-2507` (Qwen, 262K ctx) + `gemini-2.5-flash-lite` (Google, 1M ctx) → judge `mistral-large-2512` (Mistral, high-capability tiebreak). Big contexts avoid table chunking.
- **B2:** voters `gemini-2.5-flash-lite` (Google) + `mistral-large-2512` (Mistral) → judge `qwen3-235b-a22b-2507` (Qwen).

**(c) Vision councils with a working vision judge** (fix deepseek dead-judge)
- **C1 (best doc-vision):** voters `gemini-2.5-flash` (Google) + `mistral-small-3.2-24b-instruct` (Mistral, cheap vision) → judge `qwen3-vl-235b-a22b-instruct` (Qwen VL). All three vision-capable, all distinct.
- **C2 (cheapest vision):** voters `gpt-5-nano` (OpenAI) + `mistral-small-3.2-24b-instruct` (Mistral) → judge `gemini-2.5-flash-lite` (Google).
- **C3 (premium tiebreak):** voters `gemini-2.5-flash` (Google) + `llama-4-maverick` (Meta) → judge `claude-haiku-4.5` (Anthropic).

---

## 3. Cost/benefit framing (what to A/B test against baseline)

Baselines: **text** 95.2% band / 99.3% per-school, $0.065 total / 205 calls; **vision** 88.5% band / 98.1% per-school, $0.273 total / 193 calls (broken judge).

| Council | Est. voter $/call | Est. judge $/call | Hypothesis to test vs baseline |
|---|---|---|---|
| A1 (pilot-like) | $0.00021–0.00035 | $0.00019 | Match 95.2%/99.3% at ~same cost; 3.2 vs 2501 Mistral may lift band accuracy slightly. |
| A2 (cheapest) | $0.00011 + $0.00028 | $0.00040 | Hold ≥95%/≥99% while adding OpenAI+DeepSeek family decorrelation; measures whether a cheaper judge preserves the 72% escalation-resolution rate. |
| B1 (table) | $0.00019 + $0.00035 | $0.0015 | On hub-table subset only: raise band accuracy on 100+ school tables above the pilot's noisy-name failure rate; Large-3 judge should cut name-matching errors. |
| C1 (vision fix) | $0.0017 + $0.00028 | $0.00085 | Restore a functioning judge → lift vision from 88.5% band and grow accepted schools toward the text council's coverage; judge resolves disagreements deepseek never could. |
| C2 (cheap vision) | $0.00027 + $0.00028 | $0.00035 | Test whether a sub-$0.001/call all-vision council can close the coverage gap at ~1/3 the pilot vision cost. |

Interpretation: Because absolute cost is negligible (~$55 for text across 20K districts; vision ~15× that), **the tiebreaker is coverage per resolved fact**, not $/call. The vision council's problem is *coverage* (it resolves fewer schools), not per-fact accuracy — so the highest-value change is restoring the judge (C1) and routing more image-only documents into it, not shaving cents.

---

## 4. Input-dispatch insights

### Table format for 100+ row hub tables
Feed **Markdown tables (or Markdown key-value)**, not CSV. Improving Agents' benchmark ("Which Table Format Do LLMs Understand Best?"), testing 1,000 employee records with GPT-4.1-nano, found **Markdown-KV 60.7%** (CI 57.6–63.7%) retrieval accuracy vs **CSV 44.3%** (41.2–47.4%), JSONL 45.0%, and Pipe-Delimited lowest at 41.1% — Markdown-KV "landing roughly 16 points ahead of CSV." CSV/JSONL are weak because CSV training data does not encode which row is the header; Markdown's explicit delimiters let the model bind header→value correctly, directly attacking the pilot's name-matching noise on hub tables. Trade-off: Markdown-KV used **52,104 tokens vs CSV's 19,524 (2.67×)**; a plain **Markdown-Table used only 25,140 tokens**, a good middle ground. Both are acceptable here given negligible costs and large context windows. Caveat: models sometimes reformat Markdown tables on *output*, so keep strict-JSON output enforcement (below) rather than asking for a table back.

### Chunking strategy for very large tables
Prefer **not to chunk**: route big tables to large-context voters (`gemini-2.5-flash-lite` 1M, `qwen3-235b-a22b-2507` 262K, `llama-4-maverick` 1M). If a table exceeds context, chunk on **row boundaries with the full header repeated in each chunk**, never mid-row, and carry a stable row index so the modal-band code can reassemble. Repeating the header per chunk is essential for CSV-like inputs and still helps Markdown.

### Image resolution / tiling for vision
Document-OCR practice converges on **~300 dpi (400–600 dpi for sub-10pt text)** and downscaling very large captures to ~1024–1536 px on the long edge to stay within each model's optimal token budget. Most VLMs (InternVL-style, Qwen-VL) tile internally into ~448–512px tiles; over-supplying resolution inflates input tokens (the main vision cost driver) without accuracy gains. Practical guidance: send one clean full-page image at ~300 dpi / 1024–1536px; avoid manual tiling unless a page exceeds the model's max image size. Note Gemini's document limits: per Google's Gemini API docs, "Gemini supports PDF files up to 50MB or 1000 pages… Each document page is equivalent to 258 tokens," and larger pages "are scaled down to a maximum resolution of 3072 x 3072." Route `tesseract_raster` (worst yield ratio) inputs to vision instead of OCR-of-rasterized-PDF.

### Strict-JSON enforcement
Use OpenRouter **`response_format: json_schema` with `strict: true`** and set `provider: { require_parameters: true }` so requests only route to providers that honor the schema. Confirmed structured_outputs on: `gemini-2.5-flash-lite`, `gemini-2.5-flash` (high-confidence), `qwen3-235b-a22b-2507`, `qwen3-vl-235b-a22b-instruct`, `mistral-small-3.2-24b-instruct`, `mistral-large-2512` (high-confidence), `deepseek-v3.2`, `llama-4-maverick`, `gpt-5-nano`, `gpt-4.1-mini` (high-confidence), `claude-haiku-4.5` (recent GA). NOT supported: `amazon/nova-lite-v1` (json_object/tools only), `x-ai/grok-4.1-fast`. Keep a defensive parser + OpenRouter's `response-healing` plugin as backstop (it strips stray Markdown code fences, a known failure mode; non-streaming only).

### Per-family prompt tweaks worth testing
- **Few-shot leak fix (already applied):** keep few-shot example school names obviously synthetic (e.g., "EXAMPLE_SCHOOL_A") so a model reading garbled input cannot echo a realistic name. Test whether *removing* few-shot entirely and relying on JSON-schema field descriptions is even safer for the judge.
- **Anti-spray framing:** frame the instruction around **page focus** ("Does this page list many schools (a hub/directory) or focus on one school? Only copy a time across multiple schools if the page explicitly states shared/district-wide hours"), NOT around shared-time counts — so legitimate uniform-hours districts (104 schools, one time) are preserved.
- **Qwen/Mistral:** both follow terse schemas well; keep system prompts short.
- **Gemini:** benefits from an explicit "return null for missing fields" instruction to avoid hallucinated fills.

---

## 5. Council Lab experiment backlog (priority order)

1. **Fix the vision judge (highest value).** Hypothesis: replacing text-only `deepseek/deepseek-v3.2` with `qwen/qwen3-vl-235b-a22b-instruct` as the vision judge will resolve ≥60–70% of escalated vision disagreements (matching the text judge's 72%) and lift vision band accuracy above 88.5%, with accepted-school count rising toward the text council's coverage. Test council C1. Metric: escalation-resolution rate and accepted-school delta on the same 24-district set.
2. **Table-specialist voter test.** Hypothesis: on the hub-table subset, a large-context council (B1: Qwen 262K + Gemini 1M voters, Mistral-Large-3 judge) fed **Markdown** tables cuts school-name-matching failures materially vs the pilot, without suppressing legitimate uniform-hours pages. Metric: name-match error rate on 100+ row tables, and confirm the 104-schools-one-time case is NOT suppressed.
3. **Judge-quality / 3-voter-panel test.** Hypothesis: replacing the single judge with a cheaper distinct-family judge (`deepseek-v3.2`, freeing Qwen to be a third voter) either (a) holds resolution quality at lower cost, or (b) a 3-voter modal-vote panel with no judge matches judge accuracy on the 21% of facts currently judge-resolved. Metric: accuracy on the judge-resolved fact subset (was 165/778).
4. **Mistral-small value-anchor across more seeds.** Hypothesis: `mistral-small-24b-2501`'s standout 0-error, $0.00011/call performance generalizes beyond 24 districts. Run it as a fixed voter across many more district seeds before committing it as the permanent workhorse; A/B it against the newer `mistral-small-3.2-24b-instruct` to see if 3.2 improves band accuracy at ~2× the (still trivial) cost.
5. **Route tesseract_raster → vision.** Hypothesis: documents currently read via `tesseract_raster` (worst yield ratio) will yield more correct facts if routed to a vision voter (C2, cheapest all-vision council) instead of OCR-of-rasterized-PDF. Metric: accepted facts per document for tesseract_raster-class inputs, text-council vs vision-council.
6. **(New) Structured-output strictness A/B.** Hypothesis: enabling `json_schema strict:true` + `require_parameters` reduces malformed-JSON retries to ~0 vs prompt-only JSON, at no accuracy cost. Cheap to run and de-risks the 20K-district scale-up.

## Caveats
- **Pricing and capability flags change frequently on OpenRouter.** All figures verified July 3, 2026 against OpenRouter model pages / models API; re-verify `GET /api/v1/models?supported_parameters=structured_outputs` and each slug before production.
- **`claude-haiku-4.5` structured-output support is recent (GA ~Feb 2026)** — confirm it's live on your routed provider; structured-output support can vary by underlying provider even for the same model.
- **`amazon/nova-2-lite-v1` and `z-ai/glm-4.5v` structured-output support is unconfirmed** (priced above the API slice that could be captured) — verify before relying on json_schema. `amazon/nova-lite-v1` supports vision but NOT json_schema.
- **`mistral-large-2512`, `gemini-2.5-flash`, and `gpt-4.1-mini` structured outputs are high-confidence** (native + corroborated) but were not directly seen in the captured filtered API list — treat as verify-before-ship.
- **Hybrid/thinking models** (`glm-4.5v`, `grok-4.1-fast`, `gemini-2.5-flash`, `deepseek-v3.2`) must be run with reasoning explicitly disabled (`reasoning: { enabled: false }` or equivalent) to stay eligible and cheap. `x-ai/grok-4.1-fast` is a poor fit regardless (no structured outputs on OpenRouter and effectively text-only there); use `x-ai/grok-4` if you need xAI with images + JSON schema.
- **Vision cost is structural**, driven by image input tokens (2,600–3,100 in), not model markup; no model choice removes this — only resolution/token discipline does.
- Per-call cost estimates use the pilot's token profiles; actual costs vary with document size and OpenRouter prompt-caching discounts (60–80% on repeated context).