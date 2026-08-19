# OpenRouter Platform Features for the Council Lab (2026-08-18)

> **Authority:** exploratory research done ahead of epic #80 (Council Lab), triggered by Ian noticing
> OpenRouter's "Ori Eval" feature. Findings are from two parallel web-research passes (WebSearch/WebFetch
> against openrouter.ai docs/benchmarks/rankings, plus a scan of Vercel AI Gateway, Perplexity's API, and
> other unified-LLM-gateway players) — not from hands-on testing against this pipeline. Nothing here is
> adopted; it's an options survey for #80 to draw on when that epic's children get scoped.
> **Audience:** whoever picks up Council Lab composition/eval tooling work.
> **Companions:** `LLM_COUNCIL_RESEARCH_2026-06.md` (general council-design literature), `models-and-council-composition.md`
> (the batch_00000 empirical report — the existing, more rigorous GT-scoring methodology this doc's
> findings should complement, not replace), GitHub #80 (Council Lab epic).
> **Update this when:** OpenRouter ships an API-accessible eval surface for Ori Eval, or the team actually
> spikes one of these features and has a verdict to record. **2026-08-18 addendum (§7) added same-day** —
> Ian's forward-looking judgment on the Stripe acquisition and auto-selection vs. the validated-council
> approach, ahead of #80's composition work.

---

## 1. Ori Eval

OpenRouter's new (~Aug 3, 2026) model-selection tool. It's an **agent-driven eval harness, not a
dashboard widget or a REST API**: it scans your codebase for every place a model is called, interviews
you about priorities (cost/latency/accuracy/tool-calling precision), and auto-writes a `*.eval.ts` file
(Bun-compatible TypeScript) that runs your actual agent against ~5 candidate models in parallel through
OpenRouter, then reports a comparison table.

**Methodology:** tool-call assertions (correct tools invoked), LLM-as-judge grading for open-ended
answers, code-based assertions for regression cases. Docs mention a `structuredOutput` rubric and
`test.each` support for labeled question/answer pairs — so custom eval sets and some form of
structured-output grading and ground-truth comparison appear supported, though it's **unverified whether
it does field-level structured comparison** (a JSON-schema diff against GT, which is what our per-school
scoring in `stage7_extract/validate.py` already does) versus just pass/fail assertions. It pins one
harness+model per run so score deltas are attributable only to the model swap — the same isolation
principle our frozen-handoff methodology uses.

**Access:** CLI/agent-driven only (`curl -fsSL https://openrouter.ai/skills/spawn-ori-eval`), plus an MCP
server. **No standalone REST API found.** It's meant to be run by an agent (e.g. Claude Code) inside your
repo, which is awkward for a fully headless, scheduled Council Lab — you'd be shelling out to an
agent-orchestrated tool rather than calling an API from `stage7_run.py --persist --validate`-style
tooling. Cost is normal per-call OpenRouter rates for the underlying model calls; no separate eval fee
disclosed.

**Verdict:** conceptually close to what the Council Lab already does (test multiple models against a real
task, rank by score/cost/speed) but weaker on rigor — our existing GT-scored, frozen-handoff methodology
(`models-and-council-composition.md` §0) is already more principled than LLM-as-judge grading. Worth a
small spike to see if it's useful as a *fast pre-screen* before spending GT-eval budget on a new
candidate; not a foundation to build the lab's ledger on, given the API gap.

Sources: [Ori Eval blog](https://openrouter.ai/blog/announcements/ori-eval/), [Ori Eval docs](https://openrouter.ai/docs/guides/ori/eval)

---

## 2. openrouter.ai/benchmarks

Runs 6 benchmarks (as of 2026-08-18; ~2.46M task evals) across three groups: **Agents & Tools** (τ²-Bench
Airline — multi-turn tool-calling under policy constraints), **Reasoning** (GPQA Diamond), and **Search**
(BrowseComp, DeepSearchQA, HLE-as-search, WideSearch). Scored on quality (accuracy), value (cost/task),
and speed.

**These are general reasoning/agentic/search benchmarks — none target structured JSON extraction from
documents.** τ²-Bench (tool-call correctness under constraints) is the closest analog for judging
structured-output discipline, but it's not our task.

**API access:** yes — `GET /benchmarks`, bearer-token auth, filterable by `source`, `task_type`,
`benchmark_type`, rate-limited (30/min, 500/day). Returns aggregate scores (accuracy/ELO/composite index),
**not granular per-task records** — useful for "is model X generally decent at tool use" pre-screening,
not for measuring our extraction task directly.

**Verdict:** a coarse, free, API-pullable pre-filter for candidate council voters (e.g. screen out models
scoring poorly on τ²-Bench tool-calling) before spending GT-eval budget — not a substitute for our own
batch_00000-style scoring.

Sources: [Benchmarks page](https://openrouter.ai/benchmarks), [Benchmarks API docs](https://openrouter.ai/docs/api/api-reference/benchmarks/list-benchmarks)

---

## 3. openrouter.ai/rankings

Pure **usage/adoption rankings**, explicitly not quality rankings (OpenRouter's own docs distinguish this
from Benchmarks). Computed from actual token volume through OpenRouter's API, bucketed daily UTC, 1/7/30
day windows, with task-category cuts (languages, tool calls, context length, image, etc.) by spend share.
API-accessible via OpenRouter's Data API (JSON, CC BY 4.0).

**Verdict:** tells you what's popular, not what's good at bell-schedule extraction — popularity is
confounded by price and general-purpose fit, neither of which predicts our accuracy. Value is limited to
**discovery**: a feed of new/trending models worth adding to the council-lab candidate pool, never a
quality signal on its own.

Sources: [Rankings page](https://openrouter.ai/rankings)

---

## 4. Other OpenRouter features relevant to the lab

- **Provider routing controls** (`openrouter.ai/docs/guides/routing/provider-selection`, fully
  API-accessible via the `provider` object on chat completions): `sort` by price/throughput/latency,
  `preferred_min_throughput`, `order`/`only`/`ignore` allow/deny lists, **`require_parameters`** (only
  route to providers supporting tools/JSON mode), `max_price` ceilings, `zdr`/`data_collection` flags.
  **Directly actionable**: `require_parameters` would have caught #82's dead image-council judge
  (`deepseek-v3.2` has no vision endpoint) at request time, complementing the static
  per-model-vision-capability catalog already proposed as a `councils.validate()` guard.
- **Structured outputs**: `response_format` JSON-schema enforcement support **varies per provider
  endpoint, not just per model** — filterable via `supported_parameters=json_schema`. Some providers
  silently fall back to loose `json_object` mode if schema mode isn't supported. This is a real gotcha
  worth an explicit guard given REQ-054's strictness about what extraction models are allowed to return.
- **Prompt caching**: automatic for most providers; Anthropic/Alibaba require explicit per-message opt-in;
  OpenRouter uses "sticky routing" to keep repeat requests on the same cached provider endpoint (bypassed
  if `provider.order` is set manually). Relevant if council runs repeatedly re-send the same
  document/prompt scaffold.
- **Batch processing**: no dedicated batch/discount API found — client-side concurrency (5-10 parallel) is
  the recommended pattern, which is already what the pipeline does.
- No dedicated systematic A/B-testing product beyond Ori Eval was found.

Sources: [Provider selection docs](https://openrouter.ai/docs/guides/routing/provider-selection), [Structured outputs docs](https://openrouter.ai/docs/guides/features/structured-outputs)

---

## 5. Alternative ecosystems (Vercel AI Gateway, Perplexity API, others)

Scanned to check we aren't missing a capability worth the added integration complexity. **Verdict: no
concrete gap justifies moving off OpenRouter or adding a second provider.**

**Vercel AI Gateway** — architecturally the same idea as OpenRouter (200+ models, 40+ providers, single
endpoint, `provider/model` addressing). Pricing (as of 2026-08-01): **zero markup, zero platform fee** —
provider list price even with BYOK, vs. OpenRouter's ~5.5% fee on credit purchases (5% after 1M BYOK
requests/month). Ships a "leaderboards" feature, but it's **production-usage telemetry** (daily-aggregated
usage share, live P50/P95 latency+throughput), not an evaluation/accuracy harness — it shows what other
people use and how fast providers respond, not whether a model is good at our extraction task. No
support for scoring against ground truth. Its real differentiator — native AI SDK integration
(`@ai-sdk/gateway`, provider ordering inside `streamText`/`generateText`) — matters for a Next.js/Vercel
app, not this Python pipeline. Multiple independent comparisons describe it as "framework-native,
curated" vs. OpenRouter's "broadest catalog, marketplace-style," recommended only if already on Vercel.

**Perplexity API** — two things exist: (a) proprietary Sonar models (search-augmented, every call does
live web search, billed on tokens), and (b) a newer Agent API that proxies third-party models
(`provider/model` strings, JSON-schema structured outputs) but is architected around "search then
generate," not raw model access, with no evidence of a model catalog comparable to OpenRouter's. **Low
relevance**: our task extracts structured facts from already-acquired PDFs — it needs strong
document/vision comprehension and JSON-schema fidelity, not live web search. Using Perplexity's Agent API
as a pass-through would mean paying for search-grounding overhead we don't need, on a narrower roster,
duplicating what OpenRouter already provides directly.

**Other gateways (brief scan only)** — LiteLLM (self-hosted proxy, no eval tooling, adds ops burden);
Portkey (enterprise control-plane: prompt management, guardrails, rule-based routing, not an eval lab);
**Not Diamond** and **Martian** (the closest conceptual match — both train an automated *router* that
picks a model per request from labeled examples, which is adjacent to council-composition tuning, but
neither offers a voter/judge consensus framework — they're routing-decision products, not council
infrastructure); Requesty (comparable aggregator, nothing distinguishing found. None of the scanned
alternatives offer anything resembling multi-model council infrastructure (concurrent voters + judge,
consensus measurement) — that logic stays bespoke in every case, including ours.

Sources: [vercel.com/docs/ai-gateway/pricing](https://vercel.com/docs/ai-gateway/pricing) (2026-08-01),
[vercel.com/docs/ai-gateway/models-and-providers](https://vercel.com/docs/ai-gateway/models-and-providers)
(2026-07-28), [vercel.com/ai-gateway/leaderboards/models](https://vercel.com/ai-gateway/leaderboards/models),
[truefoundry.com/blog/vercel-ai-gateway-vs-openrouter](https://www.truefoundry.com/blog/vercel-ai-gateway-vs-openrouter),
[inworld.ai/resources/ai-gateway-comparison](https://inworld.ai/resources/ai-gateway-comparison),
[pricepertoken.com Sonar/Sonar Pro pages](https://pricepertoken.com/pricing-page/model/perplexity-sonar),
[docs.perplexity.ai structured-outputs](https://docs.perplexity.ai/docs/grounded-llm/output-control/structured-outputs),
[omidsaffari.com/blog/openrouter-pricing](https://omidsaffari.com/blog/openrouter-pricing) (2026),
[agentmarketcap.ai LLM gateway market 2026](https://agentmarketcap.ai/blog/2026/04/06/llm-gateway-market-2026-litellm-portkey-martian-intelligence-router)

---

## 6. Recommendations → Council Lab backlog

Not adopted — candidate hypotheses for #80's children to test, in leverage order:

1. **`require_parameters`-based capability-aware provider routing** as a stronger, request-time
   complement to the static per-model-vision-capability catalog already proposed for `councils.validate()`
   (#82's dead-judge class of bug).
2. **A time-boxed spike on Ori Eval** as a candidate fast pre-screen tool — evaluate whether its
   structured-output grading is rigorous enough to be useful at all, but plan to keep the existing
   frozen-handoff + GT-scoring methodology as the system of record given Ori Eval's lack of a
   headless-friendly API.
3. **Benchmarks API as a pre-filter, not a scorer** — pull τ²-Bench tool-calling scores to screen new
   candidate models before spending GT-eval budget on them.
4. **Rankings as a discovery feed only** — periodically check for new/trending models to add to the
   candidate pool; never treat ranking position as a quality signal.
5. **Structured-output support verification per provider endpoint** — before adding a new council member,
   confirm `supported_parameters=json_schema` on the specific endpoint OpenRouter would route to, not just
   the model in the abstract (the silent-fallback-to-`json_object` gotcha).
6. Stay on OpenRouter as the sole provider — no alternative surfaced a capability gap worth the added
   integration complexity of a second gateway.
7. **A lightweight council-roster staleness check** (§7.3) — cheaper and more targeted than ceding
   selection to OpenRouter's auto-router, and addresses the one real gap that motivates it.
8. Possible longer-term experiment: run OpenRouter's auto-selector in **shadow mode only** (§7.3) — never
   production-facing — feeding its picks into the Council Lab's measured composition process as candidate
   hypotheses, not as a routing decision.

---

## 7. 2026-08-18 addendum — Stripe acquisition, Vercel's model, and auto-selection vs. validated council

Ian's forward-looking judgment calls, recorded ahead of #80's composition work so they're on record when
that epic's children get scoped — not yet acted on.

### 7.1 OpenRouter acquired by Stripe

Flagged by Ian as a standing watch item, not an action now: OpenRouter was acquired by Stripe. Stripe has
a strong trust/reliability track record, but this doc's pricing/feature picture (§0-§6) is a 2026-08-18
snapshot and should not be assumed current without a check. **Watch for:** markup/pricing changes, any
narrowing of the model catalog toward Stripe-preferred partners, and API stability — re-verify before
leaning on any pricing- or catalog-breadth claim from this doc in future work. Also keep half an eye on
marketplace alternatives generally, per Ian's standing preference to not be single-vendor-blind, even
while staying on OpenRouter as primary (§5's verdict is unchanged by the acquisition itself).

### 7.2 Vercel AI Gateway's business model — is it the opposite of what this project wants?

Ian's read: Vercel's business model is to **own core services** — more flexible than a full-stack tool
like Replit or Lovable, but still a platform-lock-in play, not a marketplace. Since OpenRouter was
adopted specifically as a time/money trade-off *away from* the burden of self-hosting (Ollama proved too
heavy locally), Vercel's model — bundle a zero-markup gateway into the Vercel platform, monetize the
platform (hosting, AI SDK, observability add-ons) rather than the routing — pulls in the opposite
direction: paying with platform lock-in/surface-area instead of dollars, for a product whose real
differentiators (leaderboards-as-telemetry, native AI SDK integration) target a Next.js/Vercel-hosted app,
not this Python pipeline. **Assessment: reasonable conclusion, confirmed by §5's research** — Vercel's
zero-markup pricing only makes sense as a loss-leader/retention play for platform adoption, not as a
gateway offering on its own merits. Not a fit for this project; no action needed beyond noting the
reasoning for future reference.

### 7.3 Auto-selection (OpenRouter's live cost-optimizing router) vs. the validated, self-contained council

Ian's stance: the Council Lab's intentionally-selected, GT-validated council model (two models from two
families, escalating to a third-family judge — REQ-056) is in better alignment with REQ-165/166 than
OpenRouter's on-the-fly model auto-selector, even though the auto-selector's cost-adaptivity looks like it
serves REQ-167. OpenRouter would report back which models an auto-selection run actually used.

**Counterarguments considered, and why they don't overturn the stance:**

- **"Auto-selection is just an automated cheapest-viable-first cascade, which is what REQ-167 wants."**
  Doesn't survive contact with REQ-167's own acceptance criteria: *"council composition is measured in the
  cost_benchmark lab, never guessed."* OpenRouter's router optimizes across its own opaque criteria
  (likely latency/uptime/price), not the pipeline's actual objective — accuracy against batch_00000 GT
  (REQ-166). Optimizing the wrong objective function isn't cost-discipline, it's guessing with extra
  steps.
- **"OpenRouter tells us after the fact which models it picked, so provenance is preserved."** This is a
  REQ-165 regression dressed as a win. Knowing *which* model doesn't tell you *why* — the routing decision
  itself isn't inspectable the way `councils.validate()`'s cross-family diversity check is, and the
  selection criteria can change without notice on OpenRouter's side. A versioned, git-tracked council
  config is a stronger auditability story than a downstream report of an opaque decision.
- **The one counterargument with real weight: model churn/deprecation resilience.** New models appear and
  old ones get deprecated or silently degrade (a provider endpoint disappears, pricing shifts) faster than
  the Council Lab's measurement cadence can track by hand. An auto-selector adapts to that churn
  inherently; a validated roster requires someone to notice a model went stale. This is a real operational
  cost of the validated-council approach — **but it's better solved by a lightweight staleness guard**
  (does every council-configured model still resolve to a live, capable endpoint? — the Backlog §6 item 7
  above) than by ceding runtime selection to the router.
- **A narrow legitimate role for the auto-selector:** not as a production council member, but as a
  **shadow-mode candidate-discovery signal** feeding the Council Lab — let it run non-production, log what
  it would have picked and at what cost, and feed that as a hypothesis into the measured composition
  process (the same pattern as treating the rankings page as a discovery feed, §3/§6 item 4). This
  preserves REQ-165/166 (nothing auto-selected reaches production without measurement) while capturing
  some of REQ-167's cost-adaptivity without the auditability cost.

**Net:** the stance holds. The auto-selector's one genuine strength (catalog-churn adaptivity) is better
addressed with a staleness guard than with ceding selection, and "it still tells us what it picked" does
not rescue REQ-165's auditability bar because the *why* stays opaque.
