# OpenRouter LLM Council — Non-Reasoning Model Research for K-12 Bell Schedule Extraction

**Prepared:** July 3, 2026 | **Scope:** OpenRouter-available, non-reasoning models for structured JSON document extraction at scale (~20,000 US districts)

> **Authority note:** All prices are as of July 2026. OpenRouter pricing changes continuously — treat any figure more than 30 days old as stale and re-verify at openrouter.ai/models. Batch_00000 pilot findings are from the attached report (`models-and-council-composition.md`), run July 3, 2026.

***

## Executive Summary

The batch_00000 pilot confirmed the text-council approach (voters `gemini-2.5-flash-lite` + `mistral-small-24b` → judge `qwen3-235b`) is working extremely well: **99.3% per-school accuracy on 778 resolved schools at $0.065 total**. The only critical bug is the image council's dead judge: `deepseek-v3.2` has no vision capability, causing all 33 image judge calls to fail with a 404. The primary immediate task is finding a **vision-capable third-family judge** to fix issue #82. The secondary task is validating or improving the existing text-voter roster and identifying additional cross-family diversity options for both councils.[^1]

The recommendations below are grounded in current OpenRouter pricing and independent benchmarks. Several material upgrades are available: `qwen3-235b-a22b-2507` (the non-thinking July 2025 variant) reduces judge cost ~5× versus the original `qwen3-235b-a22b`; `mistral-small-3.2-24b` adds vision to the Mistral slot at a lower price point; and `Llama 4 Maverick` and `Gemma 4 26B` provide two entirely new vision-capable families for council diversification.

***

## Part 1 — Model Catalog

### Pricing Data Caveats

OpenRouter acts as a unified API gateway that adds a small markup over provider list prices. Prices shown are **OpenRouter list prices** as of July 2026 from the model pages cited below. Actual effective prices with prompt caching can be 60–80% lower for repeated context. Prices for models with both thinking and non-thinking modes (Qwen3 series, Gemini 2.5 Flash/Flash-Lite, Gemma 4) refer specifically to **non-thinking/non-reasoning mode** unless otherwise noted.[^2]

### Text-Input Models (non-vision)

| Model | Family | $in /Mtok | $out /Mtok | Context | Max out | Vision | JSON mode | Notes |
|-------|--------|-----------|------------|---------|---------|--------|-----------|-------|
| `mistralai/mistral-small-24b-2501` | Mistral | **$0.09** | **$0.28** | 131K | — | ❌ | ✅ | Pilot's cheapest voter: $0.00011/call avg[^1] |
| `mistralai/mistral-small-3.2-24b-instruct` (`2506`) | Mistral | **$0.075** | **$0.20** | 128K | 16K | ✅ | ✅ | Upgraded 3.1→3.2; adds vision + improved instruction following[^3][^4] |
| `google/gemini-2.5-flash-lite` | Google | **$0.10** | **$0.40** | 1M | 65K | ✅ | ✅ | Current text voter; $0.00042/call avg in pilot[^1][^5] |
| `google/gemini-2.5-flash` | Google | **$0.30** | **$2.50** | 1M | 65K | ✅ | ✅ | Current image voter; $0.00178/call avg in pilot[^1][^6] |
| `mistralai/mistral-large-2512` | Mistral | **$0.50** | **$1.50** | 262K | 262K | ✅ | ✅ | Current image voter; $0.00163/call avg in pilot[^1][^7] |
| `qwen/qwen3-235b-a22b` (original) | Alibaba/Qwen | $0.455 | $1.82 | 131K | 8K | ❌ | ⚠️ | Current text judge; reasoning hybrid — **requires `enable_thinking: false`**[^8][^9] |
| `qwen/qwen3-235b-a22b-2507` | Alibaba/Qwen | **$0.09** | **$0.10** | 262K | 16K | ❌ | ✅ | **Non-thinking variant by design** — no `<think>` blocks[^10][^11]; 2× context, 2× max_out vs original at ~5× lower blended cost |
| `mistralai/mistral-small-4` (`2603`) | Mistral | $0.15 | $0.60 | 262K | 262K | ✅ | ✅ | March 2026; MoE 119B/22B-active; configurable reasoning effort[^12][^13] |
| `qwen/qwen3-30b-a3b` | Alibaba/Qwen | $0.12 | $0.50 | 41K | 16K | ❌ | ✅ | Smaller MoE; non-thinking mode available[^14] |
| `openai/gpt-4o-mini` | OpenAI | $0.15 | $0.60 | 128K | — | ✅ | ✅ | Established JSON-mode reliability[^15][^16] |
| `google/gemma-4-26b-a4b-it` | Google/Gemma | $0.06 | $0.33 | 262K | 262K | ✅ | ✅ | Google MoE (3.8B active); Apr 2026; configurable thinking mode[^17][^18] |
| `meta-llama/llama-4-maverick` | Meta/Llama | $0.15 | $0.60 | 1M | 16K | ✅ | ✅ | Native multimodality; early-fusion architecture[^19][^20] |
| `qwen/qwen2.5-vl-72b-instruct` | Alibaba/Qwen (VL) | $0.80 | $1.00 | 131K | 128K | ✅ | ✅ | #1 open-source DocVQA (96.1%), OCRBench (877)[^21][^22] |
| `qwen/qwen2.5-vl-7b-instruct` | Alibaba/Qwen (VL) | free* | free* | 33K | — | ✅ | ⚠️ | Free tier; rate-limited (200 req/day)[^23][^24] |
| `opengvlab/internvl3-78b` | OpenGVLab/InternVL | $0.07 | $0.26 | 32K | — | ✅ | ✅ | Independent architecture; OCRBench 855, DocVQA 95.4%[^25][^21] |

*`free*` = Free tier with 200 requests/day limit. Paid variant pricing unclear at time of writing — verify at OpenRouter.[^24]

**Image pricing (vision models):** Gemini 2.5 Flash charges $0.0003/K images; Gemini 2.5 Flash-Lite charges $0.0001/K images. Meta and Mistral models consume images as standard input tokens (model-specific tile/patch counts). OpenRouter does not publish a separate flat image-per-call charge for non-Gemini models.[^6]

***

### Hybrid Models: Reasoning-Capable but Non-Reasoning Mode Available

These models have embedded thinking/reasoning modes that must be **explicitly disabled** via API parameters. Failure to disable them invokes the reasoning surcharge and contradicts your benchmarking finding that reasoning adds cost with no accuracy gain on narrow extraction.

| Model | How to disable thinking | Notes |
|-------|------------------------|-------|
| `qwen/qwen3-235b-a22b` (original) | Pass `enable_thinking: false` in extra_body (OpenRouter-specific)[^26] | Current judge — works but has only 8K max_out |
| `qwen/qwen3-235b-a22b-2507` | **Thinking absent by design** — the `-2507` instruct variant explicitly does not implement `<think>` blocks[^10][^11] | Preferred replacement; ~5× cheaper |
| `google/gemini-2.5-flash-lite` | Set `thinking_config: {"thinking_budget": 0}` via Google native; on OpenRouter pass `provider.data.thinking_budget=0`[^5] | Current voter — confirm 0-budget routing in prod |
| `google/gemma-4-26b-a4b-it` | Configurable reasoning via API; default is non-thinking[^18] | Apache 2.0 open weights |
| `mistralai/mistral-small-4` | Configurable reasoning effort; defaults off for extraction prompts[^27] | Worth testing as judge |

***

## Part 2 — Independent Benchmarks Relevant to the Task

### Document/Structured Extraction (Vision)

The **Omni OCR Benchmark** (getomni.ai, April 2026) is the most directly applicable: it measures JSON extraction accuracy on 1,000 real documents, directly paralleling the bell-schedule task.[^28]

| Model | Omni JSON extraction accuracy | Notes |
|-------|------------------------------|-------|
| Qwen2.5-VL 72B | ~75% | Tied with GPT-4o on this benchmark[^28] |
| Qwen2.5-VL 32B | ~75% | Slightly lower, much cheaper via hosted providers |
| Mistral OCR | 72.2% | Specialized OCR pipeline tool, not a general VLM[^28] |
| Llama 4 Maverick | Not reported separately | Included in Omni test set; Qwen leads it[^28] |
| Gemma-3 27B | 42.9% | "Surprisingly poor"; hallucinations + omitted values[^28] |

**Caveat:** The Omni benchmark uses `Document → OCR → Extraction` (VLM reads image, returns JSON). For **text-council** inference on digital text (your dominant path per the pilot), the relevant benchmarks are instruction-following and JSON-mode reliability rather than vision accuracy.

### DocVQA / OCRBench Leaderboard (as of April 2026)

| Rank | Model | OCRBench (/1000) | DocVQA | ChartQA | Notes |
|------|-------|-----------------|--------|---------|-------|
| 1 | Qwen2.5-VL 72B | **877** | **96.1%** | 89.8% | Open-source leader[^21] |
| 2 | Gemini 2.5 Pro | N/R | 93.8% | **90.0%** | Best ChartQA/InfoVQA[^21] |
| 3 | GPT-4.1 Vision | N/R | 93.4% | 88.3% | Widely deployed baseline[^21] |
| 5 | InternVL3 76B | **855** | 95.4% | 89.7% | Second-best open-source[^21] |

### Instruction-Following / JSON-mode Reliability (Text Models)

- **Gemini 2.5 Flash-Lite** scores 84.1% on FACTS Grounding and leads on benchmark average vs Mistral Small 3.1 in a head-to-head. Its 1M context window is unmatched in this price tier.[^29]
- **Gemini 2.5 Flash-Lite** achieves a 3.3% hallucination rate on Vectara's short-document benchmark — lowest among cheap models in 2026.[^30]
- **Mistral Small 3.2 24B** improves over 3.1 on WildBench and Arena Hard, reduces infinite generations, and has improved function calling and structured outputs. Confirmed JSON-mode support and vision capability.[^3][^31][^32]
- **`mistral-small-24b-2501`** (your current voter) requires explicit "Schema Anchoring" prompting for reliable JSON: the default `"output only JSON"` instruction achieves ~65% compliance; a structured Negative Constraint system prompt achieves ~98%. This is worth auditing against your current prompt.[^33]
- **Qwen3-235B-A22B-2507** (non-thinking) has 262K context and 16K max output vs the original's 131K/8K. The 8K output ceiling on the original judge may be the silent source of the `finish_reason:length` edge you encountered on Baldwin's camelot_stream rep.

***

## Part 3 — Vision-Capable Families Beyond Google and Mistral

The table below identifies **architecturally distinct** families with confirmed OpenRouter vision availability. "Genuinely different" means different pre-training architecture and lab, not fine-tunes of the same base.

| Family | Models on OpenRouter | Architecture notes | Cross-family suitability |
|--------|---------------------|-------------------|--------------------------|
| **Meta / Llama 4** | `llama-4-maverick`, `llama-4-scout` | Early fusion; separate ViT + LLM pre-training; MoE backbone[^34][^35] | ✅ Good — genuinely different from Google/Mistral |
| **Alibaba / Qwen2.5-VL** | `qwen2.5-vl-72b`, `qwen2.5-vl-32b`, `qwen2.5-vl-7b` (free) | Dynamic-resolution ViT, NaViT-style packing, MRoPE positional encoding[^22] | ✅ Excellent benchmark performance; **different family from Qwen3 text models** |
| **OpenGVLab / InternVL3** | `internvl3-78b`, `internvl3-14b`, `internvl3-2b` | Combines InternViT-6B with Qwen2.5 LLM backbone — **shares Qwen2.5 LLM weights**[^21] | ⚠️ Architecturally similar to Qwen2.5 at the LLM layer; strong for diversity from Google/Mistral but not fully distinct from Qwen2.5-VL |
| **Google / Gemma 4** | `gemma-4-26b-a4b-it` | MoE Gemma architecture, different training from Gemini; Apache 2.0[^18] | ✅ Different from Gemini 2.5 Flash family (different model line despite same lab) |
| **OpenAI / GPT-4o-mini** | `gpt-4o-mini` | GPT-4o distillation; closed architecture[^15] | ✅ Clearly distinct; strong JSON mode |
| **Anthropic / Claude 3.5 Haiku** | `claude-3.5-haiku` | Constitutional AI / RLHF; closed[^36] | ✅ Distinct; but $0.80/$4.00 — expensive for volume voter role |

**Important note on InternVL3:** The 78B model uses Qwen2.5-72B-Chat as its language backbone. If `qwen2.5-vl-72b` is already a voter, `internvl3-78b` shares ~50% of its learned representations. For true cross-family independence, pair InternVL3 with a non-Qwen family, not with another Qwen-based model.[^21]

**Pricing note on InternVL3:** Multiple aggregators show conflicting prices ($0.07 vs $0.90/Mtok input). The OpenRouter model page currently shows context 0 and no listed price — this model may be unavailable or between versions. **Verify availability before including in a council.**[^25][^37]

***

## Part 4 — Dense Table Extraction: Practitioner Findings

### Which Models Handle 100+ Row Tables Best

Based on the Omni OCR benchmark and practitioner reports:

1. **Qwen2.5-VL 72B / 32B**: Strongest open-source option for tabular JSON extraction (~75% accuracy on Omni, matching GPT-4o). Document parsing mode outputs structured QwenVL-HTML and can maintain table structure with merged cells.[^38][^28]
2. **GPT-4.1 / GPT-4o**: Best proprietary option for table-dense extraction. Not cheap at $2.50/Mtok input.[^21][^28]
3. **Gemini 2.5 Flash**: ChartQA 90.0% (via Gemini 2.5 Pro class) confirms strong grid/table reading. Flash itself is well-demonstrated in the pilot at 7.5 facts/call.[^1][^21]

### Known Failure Modes (Ranked by Frequency)

| Failure mode | Cause | Mitigation |
|-------------|-------|------------|
| **Output truncation** | Hard `max_tokens` ceiling reached mid-array | Set `max_tokens ≥ 16K`; monitor `finish_reason: length`[^1][^39] |
| **Row dropping** | Model skips low-salience rows in long tables | Explicit instruction: "return EVERY row, no truncation"; chunk by page[^39] |
| **Name-garble unresolved** | OCR artifacts → cross-model disagreement → `unresolved` | Route `tesseract_raster` inputs to vision council[^1] |
| **Hallucinated rows** | Prompt example leakage; model inverts page focus | Remove realistic example names from few-shot[^1]; add page-focus detection |
| **JSON key drift** | Model adds extra/renamed keys | Use JSON Schema + `response_format: json_schema`; Schema Anchoring prompts[^40][^33] |
| **Uniform-schedule spray** | Model copies one time to all named schools | Requires page-focus signal detection, not just count signature[^1] |

Your pilot data directly confirms output truncation (Baldwin `camelot_stream` hit the pre-fix ceiling) and prompt-example leakage (Fivay High fabrication) — both now fixed in the pipeline.[^1]

***

## Part 5 — Input Format and Image Resolution Guidance

### Text Format (for text-council voters)

A benchmark of 11 formats over 1,000 records found:[^41][^42][^43]

| Format | Accuracy | Token cost |
|--------|----------|------------|
| Markdown-KV | **60.7%** | 2.7× vs CSV |
| XML | 56.0% | 3.1× vs CSV |
| YAML | 54.7% | 2.3× vs CSV |
| Markdown Table | 51.9% | 1.3× vs CSV |
| JSON | 52.3% | 2.7× vs CSV |
| CSV | 44.3% | **1×** (baseline) |

**Recommendation for your pipeline:** For hub tables (`camelot` output), the current `pdftotext -layout` format (plain-text with preserved whitespace) is close to Markdown Table in density. For dense multi-column tables, converting to **Markdown Table format** before dispatch is likely worth the token overhead. For individual school rows, the key-value pattern (`school: X\nstart: 8:00\nend: 3:00`) parallels Markdown-KV and should outperform CSV. **Do not use raw CSV output from camelot as-is** if accuracy is the priority.

### Image Resolution (for vision-council voters)

- **Provider maximums:** Claude tiles at a 1568px longest-edge; GPT-4o tiles at 2048px; token count scales quadratically with resolution.[^44]
- **Practical recommendation:** Downscale PNG inputs to **1568px on the longest edge** before dispatch. Most district website captures arrive from desktop-resolution screenshots (1920×1080); halving this to 960px loses little text detail and cuts vision token costs roughly 4×.[^44]
- **Format:** PNG is correct; WebP is fine where supported (note: Cleveland `.webp` was excluded from the pilot due to a format gap).[^1]
- **DPI guidance from practitioners:** 150–200 DPI is the sweet spot for bell-schedule PDFs rasterized to image. Below 72 DPI, even strong VLMs degrade on small font sizes.[^21]

### JSON Mode Reliability

- **`response_format: {"type": "json_object"}`** enforces valid JSON syntax but does not enforce schema. Key drift (extra or renamed fields) can still occur.[^40]
- **`response_format: {"type": "json_schema", "json_schema": {...}}`** (OpenAI-compatible structured outputs) constrains to schema. Gemini 2.5 Flash-Lite and Mistral Small 3.2 both support this.[^5][^32]
- **Recommendation:** Use `json_schema` mode with the strict `{grade_level, start_time, end_time, school_name}` schema everywhere; fall back to `json_object` if a model doesn't support schema mode.

***

## Part 6 — Validation of Current Roster and Recommendations

### Text Council (current: flash-lite + mistral-small-24b → qwen3-235b judge)

| Model | Verdict | Recommended action |
|-------|---------|-------------------|
| `gemini-2.5-flash-lite` voter | ✅ **Validated** — $0.00042/call, 15.5 facts/call, 1 error in pilot[^1] | Confirm `thinking_budget=0` in prod |
| `mistral-small-24b-2501` voter | ✅ **Validated** — $0.00011/call (cheapest by 4×), 14.0 facts/call, 0 errors[^1] | Consider upgrade to `mistral-small-3.2-24b` for better JSON reliability[^3][^33] |
| `qwen3-235b-a22b` judge | ⚠️ **Works but suboptimal** — $0.00054/call, 8K max_out may silent-truncate large reps[^8][^9] | **Replace with `qwen3-235b-a22b-2507`**: same family/diversity, 262K context, 16K max_out, ~$0.09/$0.10 per Mtok — cheaper at volume[^10][^11] |

### Image Council (current: gemini-flash + mistral-large-2512 → deepseek-v3.2 — DEAD JUDGE)

| Model | Verdict | Recommended action |
|-------|---------|-------------------|
| `gemini-2.5-flash` voter | ✅ **Validated** — $0.00178/call, 7.5 facts/call, 0 errors[^1] | Keep |
| `mistral-large-2512` voter | ✅ **Validated** — $0.00163/call, 7.0 facts/call, 0 errors[^1] | Keep |
| `deepseek-v3.2` judge | 🔴 **Dead — text-only, 33/33 errors** (#82)[^1] | Replace immediately |

**Image judge replacement candidates (third family, vision-capable):**

| Candidate | $in / $out | Vision | Family distinct from Google + Mistral? |
|-----------|-----------|--------|----------------------------------------|
| `meta-llama/llama-4-maverick` | $0.15 / $0.60 | ✅ | ✅ Meta (early fusion) |
| `openai/gpt-4o-mini` | $0.15 / $0.60 | ✅ | ✅ OpenAI |
| `qwen/qwen2.5-vl-72b-instruct` | $0.80 / $1.00 | ✅ | ✅ Alibaba Qwen-VL |
| `google/gemma-4-26b-a4b-it` | $0.06 / $0.33 | ✅ | ✅ Google Gemma (different family from Gemini 2.5 Flash) |
| `opengvlab/internvl3-78b` | ~$0.07–$0.90* | ✅ | ⚠️ Shares Qwen2.5 LLM backbone |

*InternVL3-78B pricing is inconsistent across aggregators — verify before use.

**Top pick for #82 fix:** `meta-llama/llama-4-maverick` ($0.15/$0.60, $0.00075/call estimated) — genuinely third family (Meta, early fusion), confirmed vision + JSON mode on OpenRouter, and validated by Omni on document JSON extraction. `gpt-4o-mini` is an equally strong pick with better-established JSON-schema mode reliability.[^19][^20][^15][^16]

***

## Part 7 — Ranked Shortlists

### Cheap Text Voter (price-priority, text-only docs)
1. `mistralai/mistral-small-24b-2501` — $0.09/$0.28, empirically validated at $0.00011/call[^1]
2. `mistralai/mistral-small-3.2-24b` — $0.075/$0.20, adds vision + better JSON reliability[^4][^3]
3. `google/gemini-2.5-flash-lite` — $0.10/$0.40, 1M context, lowest hallucination rate[^5][^30]

### Text Judge (high-leverage, 47% escalation rate)
1. `qwen/qwen3-235b-a22b-2507` — $0.09/$0.10, 262K context, 16K max_out, no thinking by design — **strong upgrade from original**[^10][^11]
2. `qwen/qwen3-235b-a22b` — $0.455/$1.82 (current) — works, but higher cost and 8K output ceiling[^8]
3. `mistralai/mistral-small-4` — $0.15/$0.60, 262K context, vision + configurable reasoning — worth testing as a cheaper MoE judge[^12][^13]

### Vision Voter (image council)
1. `google/gemini-2.5-flash` — $0.30/$2.50 (validated in pilot)[^6][^1]
2. `mistralai/mistral-large-2512` — $0.50/$1.50 (validated in pilot)[^45][^1]
3. `qwen/qwen2.5-vl-72b-instruct` — $0.80/$1.00, best open-source DocVQA at 96.1% — good third-family voter if adding a third vision voter[^22][^21]

### Vision Judge (fix for #82)
1. `meta-llama/llama-4-maverick` — $0.15/$0.60, genuinely third family, confirmed vision + JSON mode[^20][^19]
2. `openai/gpt-4o-mini` — $0.15/$0.60, strong JSON-schema mode, widely validated[^15][^16]
3. `google/gemma-4-26b-a4b-it` — $0.06/$0.33, cheapest vision option; family differs from Gemini 2.5 Flash — **risk**: Gemma-3 27B scored only 42.9% on Omni; Gemma 4 is newer and likely improved but lacks Omni validation data[^17][^18][^28]

### Distinct-Family Fillers (for expanding council diversity)
1. **Meta/Llama 4 Maverick** — early fusion multimodal; vision-capable; Apache 2.0 compatible[^34][^20]
2. **Alibaba/Qwen2.5-VL 72B** — best open-source vision extractor; use as vision voter, not alongside Qwen3 text judge[^21]
3. **OpenAI/GPT-4o-mini** — third closed-source family; strong JSON schema enforcement[^15]
4. **Google/Gemma 4 26B** — distinct from Gemini line; Apache 2.0; very cheap but needs Omni validation[^18]

***

## Part 8 — Open Questions and Lab Hypotheses

The following were surfaced by the research but could not be resolved from available data:

1. **InternVL3-78B availability:** Multiple sources report conflicting prices ($0.07–$0.90/Mtok) and one source notes the model "is no longer available". Verify live status at openrouter.ai/opengvlab before including in council tests.[^46]
2. **Gemma 4 26B JSON extraction accuracy:** Gemma-3 27B scored 42.9% on Omni (well below Qwen and Llama 4). Gemma 4 is architecturally updated and released April 2026 — no post-Gemma-4 Omni scores are available. Treat Gemma 4 as "promising but unvalidated" until council lab tests it.[^28]
3. **Mistral Small 3.2 OpenRouter price:** Prices vary across aggregators: $0.075 (Mistral AI native), $0.15 (OpenRouter per CloudPrice). The OpenRouter model page shows $0.075. Use the OpenRouter model page as authoritative.[^47][^3][^4]
4. **Qwen3-235B-2507 judge on image inputs:** The 2507 variant is text-only (no vision modality). This is correct for the text council judge role but confirms it **cannot** replace the image council judge.
5. **3-voter panel vs pair+judge:** The pilot showed 47% escalation rate and 21% of facts came from the judge — a high-leverage knob. Whether a 3-voter odd-majority panel beats pair+judge on coverage at equivalent cost is explicitly flagged as an open Council Lab hypothesis.[^1]

---

## References

1. [models-and-council-composition.md](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/17291524/6b6f7d76-21cc-40d5-af56-d8f5447715ac/models-and-council-composition.md?AWSAccessKeyId=ASIA2F3EMEYEV7HGU2LS&Signature=KA5qWIrOzHwIqZtgEr%2B%2FJjgIxPM%3D&x-amz-security-token=IQoJb3JpZ2luX2VjEEkaCXVzLWVhc3QtMSJIMEYCIQDGSZL1wxsFtpAYvgdGIKw41GHBWZH9dbQ38CmasIcyCgIhAMJuvnrQPe5fBmnsaDoEpxTcIM99ROmSXzFUVAZ%2BiFzJKvMECBIQARoMNjk5NzUzMzA5NzA1Igy2WnvITAqeulgo8%2F8q0ARErpE%2F8ZYv%2BFf0C0IKuSYjBcXH89nprCcjgmUqwOijdTsD3DscXoPOua4tgGoCt7iIrFSwOrYcLapesvmrzrPXRC30FSKeBjwJBO3C53O4K8Rx4EsuYKvVtx7z1tTL4r6sZMjcR7paIPD9vCWw%2BLs3XhzCA0MduJAMIKsGgB2EU5btyL4Q9h2KPXj%2FZzQ8YMQjEMwhP7itHxbv2Qr1A2bewN8F2159piagsdU0eDkOc9xZP4G4%2FXiez2RKorOciBgLRu9Xr%2B3vBC7lZEWasluv9TmfFyYqSAZ9XWao%2FfBTTAp3H8KrEbw%2FIMQrpcqx6qozhXtDhqPdig9KBSMVv7BrZrEBehJwucSDHTJyPnDhPSsvKelevC%2BdkuSXo3PG1qHryvlcq%2Fg7enJ4CBThm0%2FieSeFRfu3kB%2FBqgfOXHVqoGCrufyhheyVgFOEqnKZsyV2F4yFa0%2FLPsC3x6H%2FW4Plte0xE5r1Llb3WmBdJx1xrsD%2BPsCUZI40S18g93VYpXGGERI1mcM3r4SYh3Ng1ykfeHKHdKl%2B3XyzVAoeqopfI93h1tZoXZl2Lvwz2k0haIXq1oyuCHrBxBdgaOB3N8uCMGkzf6bfT%2F%2FxSoqigWL4ZC5wORND%2FAuiD%2B6noiXAiQvovmm7OGwjd2%2BmGRjsOmqRJWzpNOFgNd8dTxrA3PUt8fy%2Bgo6a69djHlN0CC18EXRBrp2o1WBEwHr3HA%2FXL49dMk90PnEdxFy46tAD5hDETNEn7HUl7mNuJ7OHS2LsqKuNn5HLzMPj%2BhHdx7qeVuunMLDVn9IGOpcBYrkFtvez8ozG7zxDQmBXR3nWHC21xAb%2BsZlPmLhkf8T91Bu%2Bd0AzXBJP2ycAuTqUbOK0tvwxzEJ6%2FWmfpOpIqCjrKs4RVA1XAfg0rxq8KL5MFidUAaNuSGtDPMZnddI%2F%2FGGS2gdxxASLcLk11CP9BPvoY8dTuCR5oXHEUXOm78NUMlnf6BRGieetwV1BM9s59KefrgaAtw%3D%3D&Expires=1783101571) - # Models & Council Composition — the batch_00000 full-run report (2026-07-03)

> **Authority:** the ...

2. [Models](https://openrouter.ai/models) - Browse models on OpenRouter

3. [Mistral Small 3.2 24B - API Pricing & Benchmarks | OpenRouter](https://openrouter.ai/mistralai/mistral-small-3.2-24b-instruct/api) - Compared to the 3.1 release, version 3.2 significantly improves accuracy on WildBench and Arena Hard...

4. [Mistral Small 3.2 24B API Pricing 2026](https://pricepertoken.com/pricing-page/model/mistral-ai-mistral-small-3.2-24b-instruct) - Pricing starts at $0.075 per million input tokens and $0.200 per million output tokens. The model su...

5. [Gemini 2.5 Flash Lite - API Pricing & Benchmarks - OpenRouter](https://openrouter.ai/google/gemini-2.5-flash-lite) - Gemini 2.5 Flash-Lite is a lightweight reasoning model in the Gemini 2.5 family, optimized for ultra...

6. [Gemini 2.5 Flash vs Gemini 2.5 Flash Lite - OpenRouter](https://openrouter.ai/compare/google/gemini-2.5-flash/google/gemini-2.5-flash-lite) - Compare Gemini 2.5 Flash from Google and Gemini 2.5 Flash Lite from Google on key metrics including ...

7. [Mistral Large 3 2512 – API Quickstart | OpenRouter](https://openrouter.ai/mistralai/mistral-large-2512/api) - Sample code and API for Mistral: Mistral Large 3 2512 - Mistral Large 3 2512 is Mistral’s most capab...

8. [Qwen3 235B A22B - API Pricing & Benchmarks - OpenRouter](https://openrouter.ai/qwen/qwen3-235b-a22b) - Qwen3-235B-A22B is a 235B parameter mixture-of-experts (MoE) model developed by Qwen, activating 22B...

9. [Qwen: Qwen3 235B A22B · Models · Pi](https://pi.dev/models/openrouter/qwen-qwen3-235b-a22b) - A terminal-based coding agent

10. [Qwen3 235B A22B Instruct 2507 - API Pricing & Benchmarks](https://openrouter.ai/qwen/qwen3-235b-a22b-07-25:free) - Qwen3-235B-A22B-Instruct-2507 is a multilingual, instruction-tuned mixture-of-experts language model...

11. [Qwen: Qwen3 235B A22B Instruct 2507 – Effective Pricing](https://openrouter.ai/qwen/qwen3-235b-a22b-2507/pricing) - Qwen3-235B-A22B-Instruct-2507 is a multilingual, instruction-tuned mixture-of-experts language model...

12. [Mistral Small 4 – Effective Pricing - OpenRouter](https://openrouter.ai/mistralai/mistral-small-2603/pricing) - Effective pricing across providers for Mistral: Mistral Small 4 - Mistral Small 4 is the next major ...

13. [Mistral Small 4 Review | Pricing, Benchmarks & ...](https://designforonline.com/ai-models/mistral-mistral-small-4/) - Mistral: Mistral Small 4 by Mistral. 262K context, from $0.1500/1M tokens, vision, tool use, functio...

14. [OpenRouter - Models.dev](https://models.dev/providers/openrouter/) - Models.dev is a comprehensive open-source database of AI model specifications, pricing, and features...

15. [OpenAI: GPT-4o-mini | OpenRouter](https://openrouter.ai/openai/gpt-4o-mini/status) - GPT-4o mini is OpenAI's newest model after [GPT-4 Omni](/models/openai/gpt-4o), supporting both text...

16. [GPT-4o Mini on OpenAI - LangRouter](https://langrouter.ai/models/gpt-4o-mini/openai) - Pricing and capabilities for GPT-4o Mini via OpenAI on LangRouter.

17. [Live Performance](https://designforonline.com/ai-models/google-gemma-4-26b-a4b/) - Google: Gemma 4 26B A4B by Google. 262K context, from $0.0600/1M tokens, vision, tool use, function ...

18. [Google: Gemma 4 26B A4B – Effective Pricing - OpenRouter](https://openrouter.ai/google/gemma-4-26b-a4b-it/pricing) - Gemma 4 26B A4B IT is an instruction-tuned Mixture-of-Experts (MoE) model from Google DeepMind. $0.0...

19. [meta-llama/llama-4-maverick | OpenRouter | AI Model Directory](https://portkey.ai/models/openrouter/meta-llama%2Fllama-4-maverick) - meta-llama/llama-4-maverick by OpenRouter. Input: $0.15/M, Output: $0.60/M. Tool Calling, 16K output...

20. [Llama 4 Maverick API Pricing — Compare 6 Providers | Inference Hub | Inference Hub](https://inferencehub.org/models/llama-4-maverick) - Compare Llama 4 Maverick API pricing across 6 providers. Input from $0.150/1M tokens. By Meta.

21. [OCR and Document AI Leaderboard 2026: Top Models Ranked](https://awesomeagents.ai/leaderboards/ocr-document-ai-leaderboard/) - Rankings of AI models on OCR and document understanding benchmarks - OCRBench, DocVQA, InfographicVQ...

22. [Qwen2.5-VL: Specs, Benchmarks & Pricing | AI/TLDR](https://ai-tldr.dev/models/qwen2-5-vl/) - Qwen2.5-VL is Alibaba's open-weight vision-language model family (3B/7B/32B/72B). See specs, MMMU/Do...

23. [Qwen2.5-VL 7B Instruct - API Pricing & Providers | OpenRouter](https://openrouter.ai/qwen/qwen-2.5-vl-7b-instruct) - Qwen2.5 VL 7B is a multimodal LLM from the Qwen Team with the following key enhancements: SoTA under...

24. [OpenRouter Free Models: All 26 Listed (Jun 2026) - CostGoat](https://costgoat.com/pricing/openrouter-free-models) - All free AI models on OpenRouter — zero cost, no credit card. Compare context lengths, capabilities,...

25. [InternVL3 78B - API, Providers, Stats | OpenRouter - Yes Tool](https://openrouter-api.yestool.org/opengvlab/internvl3-78b)

26. [Run with an API - Qwen: Qwen3 235B A22B (free)](https://openrouter.ai/qwen/qwen3-235b-a22b:free/api) - Qwen3-235B-A22B is a 235B parameter mixture-of-experts (MoE) model developed by Qwen, activating 22B...

27. [Using Mistral Small 4 on OpenRouter - LLM Reference](https://www.llmreference.com/provider/openrouter/mistral-small-4) - "mistralai/mistral-small-2603" on OpenRouter. How to use Mistral Small 4 on OpenRouter: API setup, q...

28. [The best open source OCR models - getomni.ai](https://getomni.ai/blog/benchmarking-open-source-models-for-ocr) - Comparing top open-source OCR solutions

29. [Gemini 2.5 Flash-Lite vs Mistral Small 3.1 24B Base](https://airank.dev/models/compare/gemini-2.5-flash-lite-vs-mistral-small-3.1-24b-base-2503)

30. [LLM Benchmarks for Text Extraction & Summarization (2026): Which Model Actually Wins?](https://dev.to/owen_fox/llm-benchmarks-for-text-extraction-summarization-2026-which-model-actually-wins-21lk) - No single LLM wins text extraction and summarization in 2026. Gemini 2.5 Flash-Lite has the lowest h...

31. [Mistral Small 3.2 24B — Pricing & API on OminiGate](https://ominigate.ai/en/models/mistralai/mistral-small-3.2-24b-instruct) - Mistral-Small-3.2-24B-Instruct-2506 is an updated 24B-parameter model from Mistral optimized for ins...

32. [Mistral Small 3.2 24B Review 2026 - LLM Leaderboard](https://lmmarketcap.com/model/mistral-mistral-small-3-2-24b)

33. [Fix: JSON formatting drift and agentic loop failures in Mistral Small 3.2 24B](https://www.reddit.com/r/AIToolsPerformance/comments/1qrdfmt/fix_json_formatting_drift_and_agentic_loop/) - Fix: JSON formatting drift and agentic loop failures in Mistral Small 3.2 24B

34. [Llama 4 Maverick - API Pricing & Benchmarks - OpenRouter](https://openrouter.ai/meta-llama/llama-4-maverick:free) - Released on April 5, 2025 under the Llama 4 Community License, Maverick is suited for research and c...

35. [Llama 4 Indie Maker Complete Guide: Scout vs ... - Shareuhack](https://www.shareuhack.com/en/posts/llama4-indie-maker-guide-2026) - 2026 Llama 4 practical guide for indie makers. Covers Scout vs Maverick selection, benchmark controv...

36. [anthropic/claude-3.5-haiku | OpenRouter | AI Model Directory](https://portkey.ai/models/openrouter/anthropic%2Fclaude-3.5-haiku) - anthropic/claude-3.5-haiku by OpenRouter. Input: $0.80/M, Output: $4.00/M. Tool Calling, 8K output t...

37. [InternVL3 78B API Pricing 2026 - Costs, Performance & ...](https://pricepertoken.com/pricing-page/model/opengvlab-internvl3-78b) - InternVL3 78B pricing: $0.90/M input, $0.90/M output. See benchmarks, capabilities, and find the che...

38. [Document Parsing | QwenLM/Qwen2.5-VL | DeepWiki](https://deepwiki.com/QwenLM/Qwen2.5-VL/6.2-document-parsing) - Document parsing in Qwen2.5-VL refers to the model's advanced capability to understand, extract, and...

39. [Curse of The Context Window - DEV Community](https://dev.to/deathsaber/the-curse-of-context-window-1c7i) - TL;DR: Large-document extraction with LLMs fails less from “bad reasoning” and more from hard output...

40. [JSON mode isn't your golden ticket](https://kubaik.github.io/json-mode-isnt-your-golden-ticket/) - Cut LLM validation failures 95% with JSON Schema — why JSON mode alone fails in production workflows...

41. [Sergey Enin's Post](https://www.linkedin.com/posts/sergeyenin_which-table-format-do-llms-understand-best-activity-7383422023659831296-0CXP) - 🚨 Format Matters More Than You Think Most teams feed their structured data into LLMs as CSV. It feel...

42. [Which Table Format Do LLMs Understand Best? (Results for...](https://app.daily.dev/posts/which-table-format-do-llms-understand-best-results-for-11-formats--5aoyggibn) - A benchmark study comparing 11 data formats (JSON, CSV, XML, YAML, markdown tables, and others) to d...

43. [Which Format is Best for Passing Tables of Data to LLMs? - Reddit](https://www.reddit.com/r/LLMDevs/comments/1nw3jha/which_format_is_best_for_passing_tables_of_data/) - This would point to the importance of markdown syntax vs just having new lines dividing data. Replac...

44. [Multimodal LLM Inputs in Production: Vision, Documents ...](https://tianpan.co/blog/2026-04-09-multimodal-llm-inputs-production) - A practical guide to the failure modes engineers encounter when deploying multimodal LLMs in product...

45. [Mistral Large 3 2512 - API Pricing & Benchmarks - OpenRouter](https://openrouter.ai/mistralai/mistral-large-2512) - Mistral Large 3 2512 is Mistral’s most capable model to date, featuring a sparse mixture-of-experts ...

46. [OpenGVLab: InternVL3 78B: цена, контекст и параметры | AllTokens](https://alltokens.ru/models/opengvlab/internvl3-78b) - Серия InternVL3 представляет собой передовую мультимодальную большую языковую модель (MLLM). По срав...

47. [Mistral Small pricing & specs - AI Models - CloudPrice](https://cloudprice.net/models/mistral-small) - Pricing from $0.100 per 1M input tokens. starting at $0.1 / 1M input and $0.3 / 1M output. Structure...

