# SERP API Provider Comparison for K–12 Bell Schedule Discovery Pipeline

## Executive Summary

The task requires a domain-scoped web search per school — querying something like `"Riverside Unified bell schedule start end times site:riversideunified.org"` — across 17,000+ U.S. public schools, with high recall (missing a real page is costly), and strong cost-sensitivity at scale. The comparison below covers eleven providers across six dimensions. **The bottom line:** Serper.dev is the best single provider for lowest cost with acceptable recall (real Google results, `site:` passthrough, ~$0.75/1K at scale). For a recall-maximizing cascade, pair Serper as the first pass with Bright Data SERP API as the fallback. SerpApi should be avoided for new deployments due to the active Google DMCA lawsuit and existential legal risk. Exa is architecturally wrong for this task. Tavily, LangSearch, and OpenRouter's GPT-4o-mini-search-preview return AI-synthesized answers rather than raw result URLs and are also not appropriate.

***

## Dimension 1: Pricing

### Pricing at a Glance

| Provider | Free Tier | Entry Tier ($/1K) | ~20K–100K/mo ($/1K) | Billing Model | Min Commitment |
|---|---|---|---|---|---|
| **Serper.dev** | 2,500 queries (one-time) | $1.00/1K ($50/50K credits) | $0.75/1K (500K pack, $375) | Credit packs; no monthly sub required | None – buy credits as needed |
| **SerpApi** | 100 searches/mo | $15.00/1K ($75/mo, 5K searches) | ~$9.17/1K ($275/mo, 30K) | Monthly subscription | Month-to-month |
| **SearchApi.io** | 100 requests (trial) | $4.00/1K ($40/mo, 10K searches) | $2.50/1K ($250/mo, 100K searches) | Monthly subscription (pay-per-success) | Month-to-month |
| **Zenserp** | 50 searches/mo | $2.00/1K ($49.99/mo, 25K searches) | $1.50/1K ($149.99/mo, 100K searches) | Monthly subscription | Month-to-month |
| **Brave Search API** | $5/mo free credit (~1K queries) | $5.00/1K (pay-as-you-go) | $5.00/1K (flat; volume discounts only at enterprise) | Pay-as-you-go usage-based | None |
| **Tavily** | 1,000 credits/mo free | $8.00/1K (PAYG) or $6.67/1K ($100/mo Bootstrap, 15K credits) | $5.00/1K ($500/mo Growth, 100K credits) | Monthly plans or PAYG | None for PAYG |
| **Exa** | 1,000 searches/mo free | $7.00/1K (Search endpoint) | $7.00/1K (flat — no volume discount on Search) | Usage-based | None |
| **LangSearch** | **Completely free** (no paid tier published) | Free | Free | None — currently free for individuals/small teams | None |
| **Bright Data SERP API** | 5K requests/mo (free tier) | $1.50/1K (PAYG) | $1.30/1K ($499/mo Scale plan, 380K requests) | PAYG or monthly Scale plan | None for PAYG |
| **Oxylabs SERP Scraper API** | Free trial (limited) | $2.80/1K ($49/mo Micro, 17.5K results) | ~$1.60/1K ($2,000/mo Corporate, 1.25M results) | Monthly subscription | Month-to-month |
| **OpenRouter gpt-4o-mini-search-preview** | None | ~$27.50/1K requests (tool call fee) + token cost | Same flat rate | Per-token + per-request tool fee | None |

**Notes on pricing data:**
- Serper.dev pricing verified June 2026: Starter $50/50K ($1.00/1K), Standard $375/500K ($0.75/1K), Scale $1,250/2.5M ($0.50/1K), Ultimate $3,750/12.5M ($0.30/1K). Credits valid 6 months.[^1][^2]
- SerpApi: Developer $75/mo/5K ($15/1K), Production $150/mo/15K ($10/1K), Big Data $275/mo/30K (~$9.17/1K), Searcher $725/mo/100K ($7.25/1K). Free plan gives only 100 searches/mo.[^3][^4]
- SearchApi.io: Developer $40/mo/10K ($4/1K), Production $100/mo/35K ($2.86/1K), BigData $250/mo/100K ($2.50/1K). Overage at plan rate.[^5][^6]
- Zenserp: $49.99/mo/25K ($2/1K), $149.99/mo/100K ($1.50/1K), $299.99/mo/250K ($1.20/1K).[^7]
- Brave Search API: $5.00/1K flat for the Search endpoint; $5/mo free credit renews monthly (covers ~1K queries). No documented volume discount below enterprise.[^8][^9]
- Tavily: Free 1K credits/mo; PAYG $0.008/credit; Growth plan $500/mo/100K credits ($5/1K for basic search, $10/1K for advanced).[^10][^11]
- Exa: $7/1K for the Search endpoint with up to 10 results; Contents API adds $1/1K pages if needed.[^12][^13]
- LangSearch: No fees, no subscriptions — currently free for individuals and small teams as the company pursues its AGI mission.[^14][^15]
- Bright Data: PAYG $1.50/1K; Scale $499/mo includes 380K requests ($1.31/1K), additional requests at $1.30/1K.[^16][^17]
- Oxylabs: Micro $49/mo/17.5K ($2.80/1K), Venture $499/mo/227K ($2.20/1K), Business $999/mo/526K ($1.90/1K), Corporate $2,000/mo/1.25M ($1.60/1K).[^18]
- OpenRouter gpt-4o-mini-search-preview: $0.15/M input tokens, $0.60/M output tokens, **plus $27.50/K tool call requests** (tool-use fee). At typical query lengths (~500 input tokens, ~300 output tokens), token costs add only ~$0.26/1K, making the tool-call fee dominant at ~$27.76/1K total. This is the baseline, not a competitive option.[^19][^20]

***

## Dimension 2: What a Single Request Returns

This is the most critical architectural distinction. The pipeline needs **result URLs**, not AI-generated answers.

| Provider | What You Get | Underlying Index |
|---|---|---|
| **Serper.dev** | Real Google organic-result URLs, titles, snippets, rich results (knowledge graph, PAA, answer box) as structured JSON[^21] | Google (live proxy) |
| **SerpApi** | Real Google organic-result URLs plus rich result blocks as JSON[^22] | Google (live proxy) |
| **SearchApi.io** | Real Google organic-result URLs, ads, rich snippets as JSON; pay only for successful 200-status responses[^6] | Google (live proxy) |
| **Zenserp** | Google organic-result URLs and snippets as JSON[^7] | Google (live proxy) |
| **Brave Search API** | URLs + snippets from Brave's **own independent index** (~30B pages); also returns an optional AI "Answer" endpoint separately[^23][^24] | Independent Brave index |
| **Tavily** | Returns URLs + content snippets **and** an optional AI-generated answer field; URL list is included in results, but the product is AI-search-first[^25] | Tavily's own index + extraction layer |
| **Exa** | URLs + content excerpts from Exa's own neural/embedding-based index; semantic rather than keyword-matched[^26] | Exa's proprietary neural index |
| **LangSearch** | URLs + content summaries from its own hybrid (keyword + vector) index; returns structured JSON[^27][^28] | LangSearch proprietary index |
| **Bright Data SERP API** | Real Google organic-result URLs as structured JSON or HTML; pass-through to Google live results[^29][^30] | Google (live proxy) |
| **Oxylabs SERP Scraper API** | Real Google organic-result URLs and structured JSON; supports `site:` in the `query` field[^31] | Google (live proxy) |
| **OpenRouter gpt-4o-mini-search-preview** | AI-generated text answer with inline citations; **not a URL list** — it is a conversational search model[^32] | OpenAI's proprietary web access |

**Key distinction:** Serper, SerpApi, SearchApi, Zenserp, Bright Data, and Oxylabs are all Google proxies — they return the actual URLs Google would return. Exa, LangSearch, and Brave operate their own indexes, which may miss pages Google indexes but can also surface pages Google deprioritizes. Tavily is a hybrid AI-search layer. OpenRouter's model returns synthesized text, not a URL list — it is architecturally misaligned with this task.

***

## Dimension 3: Domain/Site Restriction

Site restriction fidelity is crucial: you must confine each query to a specific district domain.

| Provider | Mechanism | Notes |
|---|---|---|
| **Serper.dev** | Pass `site:domain.com` in the `q` parameter[^21] | Standard Google `site:` operator passthrough; subdomains included by default via `site:` behavior |
| **SerpApi** | Pass `site:domain.com` in `q`, **or** use the `as_sitesearch` parameter[^33] | Dedicated `as_sitesearch` param is cleaner; subdomains included |
| **SearchApi.io** | Pass `site:domain.com` in `q` parameter[^34] | Standard Google operator passthrough; no separate site-restriction param documented |
| **Zenserp** | Pass `site:domain.com` in `q` parameter | No separate domain param documented |
| **Brave Search API** | No native `site:` equivalent in standard Search endpoint; requires Goggles (custom re-ranking rules) for domain restriction[^35][^36] | Goggles can boost/filter by domain but are not a strict `site:` — recall at a single specific district domain is unreliable |
| **Tavily** | Dedicated `include_domains` array parameter[^37][^38] | Clean API-level support; restricts results to listed domains. **Caveat:** community reports of relevance degradation with multiple domains; single-domain use should be fine[^39] |
| **Exa** | Dedicated `include_domains` array parameter[^40][^41] | Clean API-level support; neural search stays within specified domains |
| **LangSearch** | No domain restriction parameter documented[^14][^27] | General keyword/vector search only; no per-query site scoping found |
| **Bright Data SERP API** | Pass `site:domain.com` in the `query` field; the API proxies raw Google queries[^30][^31] | Full Google operator passthrough |
| **Oxylabs SERP Scraper API** | Pass `site:domain.com` in the `query` field[^31] | Documented in guides as supported; standard Google operator passthrough |
| **OpenRouter gpt-4o-mini-search-preview** | No parameter-level domain restriction; model searches web broadly and you prompt it to focus on a domain[^32] | Not reliable for strict domain scoping |

**For this use case**, the Google-proxy providers (Serper, SerpApi, SearchApi, Zenserp, Bright Data, Oxylabs) all support `site:` passthrough, which is the most battle-tested and precise mechanism for domain-scoped Google searches. Exa and Tavily support cleaner dedicated parameters but draw from non-Google indexes. LangSearch and Brave are weak here.

***

## Dimension 4: Rate Limits, Throughput, and Latency

| Provider | Rate Limit (Paid) | Latency | Notes |
|---|---|---|---|
| **Serper.dev** | 50 QPS (Starter), 100 QPS (Standard), 200 QPS (Scale), 300 QPS (Ultimate)[^2][^42] | 1–2 seconds typical; 2–4s if retry needed[^42] | Highest free-tier QPS in the segment; Higher concurrency on request |
| **SerpApi** | 1,000/hr (Developer, ~16.7 QPS), 3,000/hr (Production), 6,000/hr (Big Data)[^3][^43] | Varies; Ludicrous Speed mode available for 2.2× faster results[^44] | Throughput caps are per plan; enterprise plans have higher limits |
| **SearchApi.io** | 20% of monthly allowance per hour (2,000/hr on Developer/10K plan)[^5] | Sub-2 seconds average[^6] | 20% hourly rule can be restrictive for bursts; 99.9% SLA[^45] |
| **Zenserp** | Not publicly documented | Not published | No SLA or throughput specs found |
| **Brave Search API** | 50 requests/second (standard paid tier)[^8] | Not published | Per-project rate limit; enterprise for higher |
| **Tavily** | 20 QPS typical (paid)[^46] | Fast/Ultra-fast/Advanced modes; sub-second for Fast | Strict per-minute limits; per-plan caps |
| **Exa** | 20 QPS typical (paid)[^46] | ~200ms for Instant search mode[^13] | Neural search adds latency on Deep Search |
| **LangSearch** | Free: 1 QPS, 60 QPM, 1,000 QPD; up to 30 QPS on request for free[^47][^15] | Not published | Can request up to 30 QPS and 100K QPD free by email |
| **Bright Data SERP API** | **Unlimited concurrency** on all plans[^16][^17] | Under 1 second[^29] | Most permissive throughput of any provider in this list |
| **Oxylabs SERP Scraper API** | Not published per-plan; async mode available | Async results in minutes; realtime endpoint available | Enterprise-grade infrastructure; async suits batch workloads |
| **OpenRouter gpt-4o-mini-search-preview** | Not a SERP API; model-level rate limits apply | LLM inference latency (2–10s typical) | Not suitable for high-throughput batch |

**For a batch of 17K+ schools**, Bright Data's unlimited concurrency is the most pipeline-friendly. Serper at 50–300 QPS is also highly practical — at 50 QPS, 17K queries complete in ~6 minutes.

***

## Dimension 5: Reliability, SLA, and K–12 Long-Tail Index Coverage

### SLA / Reliability

| Provider | SLA | Notes |
|---|---|---|
| **Serper.dev** | Not formally published | No SLA doc found; credits not deducted on failure[^42] |
| **SerpApi** | 99.97% (Enterprise only)[^44] | Standard plans have no formal SLA |
| **SearchApi.io** | 99.9% documented SLA[^45][^48] | Published SLA; status page shows 99.9% API uptime over 7 days[^49] |
| **Zenserp** | Not published | Medium tier mentions SLA but no percentage found[^7] |
| **Brave Search API** | Not formally published | 50 RPS capacity stated; no uptime SLA found[^8] |
| **Tavily** | Enterprise SLA only | Acquired by Nebius in February 2026 — ownership change raises roadmap uncertainty[^50] |
| **Exa** | Not published | Reputable among AI developers; no formal SLA |
| **LangSearch** | None | Free service with no SLA commitments |
| **Bright Data SERP API** | **99.9% uptime SLA with service credits**[^51] | P0 response within 15 min; strongest formal SLA in this comparison |
| **Oxylabs SERP Scraper API** | Enterprise SLA | Self-service plans lack formal uptime SLA |

### K–12 Long-Tail Index Coverage

This is the most uncertain dimension. School district sites on platforms like Finalsite, Apptegy (typically `district.org/o/` paths), Edlio, and Squarespace are frequently thin on external inbound links and may not appear in smaller or curated indexes.

- **Google-proxy providers (Serper, SearchApi, Zenserp, Bright Data, Oxylabs):** Because they query Google directly, coverage maps precisely to what Google has indexed. Google's crawler is the most comprehensive in existence and indexes virtually every publicly accessible school district CMS page, including Finalsite, Edlio, Apptegy, and Squarespace installs. For recall on long-tail K–12 sites, these are the highest-confidence choice.

- **Exa:** Exa's own index self-describes as having "High" coverage for "Places and things" including schools and "Government and international organization sources." However, Exa openly acknowledges it targets "highest quality web pages" and its index is curated rather than exhaustive. For obscure district sub-pages (e.g., `district.finalsite.com/pages/bell-schedule`), Exa's recall relative to Google is **unknown and likely lower**. Exa's strength is semantic recall (finding semantically-related pages), not exhaustive crawl coverage of thin institutional pages.[^26][^52]

- **Brave Search API:** Brave claims 30+ billion pages indexed with 100M daily updates. Coverage of small U.S. K–12 district sites is plausible but unverified. Critically, Brave cannot do strict per-domain scoping without Goggles, which is a significant workflow barrier. ⚠️ **Recall risk is high for this use case.**[^24][^23]

- **LangSearch:** A hybrid keyword/vector index of "billions of web documents" with no published crawl scope. No evidence of specific K–12 CMS platform coverage. **⚠️ High recall risk; treat as experimental.**[^27]

- **Tavily:** Returns URLs alongside its AI answer. `include_domains` is supported. Tavily's index is not described; it appears to perform live extraction + synthesis rather than maintaining a full crawl. Recall for domain-restricted queries returning raw page URLs (not just an answer) is **uncertain**.[^37]

***

## Dimension 6: Terms of Service for Automated/Commercial Use and Storing URLs

| Provider | Automated/Commercial Use | Storing Returned URLs |
|---|---|---|
| **Serper.dev** | Explicitly a B2B service; commercial use licensed[^53] | ToS prohibits mirroring or redistributing data "as-is" but permits use within your application; storing discovered URLs for downstream pipeline steps is standard practice and not restricted[^53] |
| **SerpApi** | Commercial use permitted; subject to active Google DMCA lawsuit (filed Dec 2025)[^54][^55] | ToS permits storing results for licensed customers; however, Google alleges the entire business model circumvents DMCA protections — **existential legal risk**[^54][^56] |
| **SearchApi.io** | Automated/commercial explicitly supported; $2M Legal Protection Guarantee on Production+ plans[^6][^45] | ToS permits storing URLs for your application's use[^45] |
| **Zenserp** | Automated use supported (API product) | No specific storage prohibition found in pricing/docs |
| **Brave Search API** | Automated use permitted; **base plan prohibits storing results or using for AI inference**[^57][^58] | Storing results requires "Data w/ Storage Rights" plan ($26–$45/mo base price[^59]); standard Search plan ($5/1K) **prohibits result storage**[^57] |
| **Tavily** | AI/automated use is the primary design use case | No explicit storage prohibition found for discovered URLs in pipeline context |
| **Exa** | AI/automated use is the primary design use case | ToS prohibits downloading, copying, or creating derivative works from data obtained through Services[^57] — **⚠️ storing returned URLs to a database may technically violate ToS; verify before production use** |
| **LangSearch** | AI/automated use is the stated purpose | No ToS restrictions found; free service[^14] |
| **Bright Data SERP API** | Commercial use explicitly licensed[^60][^61] | 99.9% SLA plan; license agreement permits commercial use; standard storage of discovered URLs permitted[^60] |
| **Oxylabs SERP Scraper API** | Commercial use explicitly supported | Commercial license; standard data use permitted |
| **OpenRouter gpt-4o-mini-search-preview** | Per OpenAI/OpenRouter terms; commercial use permitted at cost | Model output licensing per OpenAI terms |

**Storage rights are a genuine concern for Brave (standard plan prohibits storage) and potentially Exa. Bright Data, Serper, SearchApi, and Oxylabs are the cleanest for automated commercial pipelines that store discovered URLs.**

***

## Full Provider Scorecard

| Provider | Price at 17K/mo | Price at 100K/mo | Returns URLs? | `site:` Support | K–12 Recall | Storage OK? | Rec |
|---|---|---|---|---|---|---|---|
| **Serper.dev** | ~$17 (17K @ $1/1K) | $75 (100K @ $0.75/1K) | ✅ Google | ✅ `q` passthrough | ✅ Google-indexed | ✅ | ⭐ Primary |
| **SerpApi** | ~$255 (17K @ $15/1K dev) | ~$725/mo Searcher | ✅ Google | ✅ `as_sitesearch` | ✅ Google-indexed | ✅ but ⚠️ legal risk | ❌ Avoid |
| **SearchApi.io** | $68 ($40/mo + 7K overage @ $4) | $250/mo (BigData) | ✅ Google | ✅ `q` passthrough | ✅ Google-indexed | ✅ w/ Legal Shield | ✅ Strong alt |
| **Zenserp** | $49.99/mo (25K plan) | $149.99/mo (100K plan) | ✅ Google | ✅ `q` passthrough | ✅ Google-indexed | Likely OK | ⚠️ Weak docs |
| **Brave Search API** | $85 (17K @ $5/1K) | $500 (100K @ $5/1K) | ✅ Own index | ⚠️ Goggles only | ❓ Unverified | ❌ Storage prohibited on base plan | ❌ Wrong tool |
| **Tavily** | $100+/mo | $500/mo | ✅ w/ URLs | ✅ `include_domains` | ❓ Non-Google | ✅ | ❌ AI-first; overkill |
| **Exa** | $119 (17K @ $7/1K) | $700 (100K @ $7/1K) | ✅ Own index | ✅ `include_domains` | ❓ Curated index | ⚠️ ToS ambiguous | ❌ Wrong index type |
| **LangSearch** | Free | Free | ✅ Own index | ❌ None found | ❓ Unknown | ✅ | ⚠️ Free tier only; recall risk |
| **Bright Data SERP** | $25.50 (17K @ $1.50/1K) | $130–$150 | ✅ Google | ✅ `q` passthrough | ✅ Google-indexed | ✅ | ⭐ Fallback/cascade |
| **Oxylabs SERP** | $49/mo (17.5K plan) | $499/mo (Venture, 227K) | ✅ Google | ✅ `q` passthrough | ✅ Google-indexed | ✅ | ✅ Enterprise option |
| **OpenRouter mini-search** | ~$470 (17K @ ~$27.76/1K) | ~$2,776 | ❌ AI answer | ❌ Unreliable | N/A | OK | ❌ Baseline only |

***

## Recommendations

### (a) Best Single Provider: Serper.dev

Serper is the clear winner for lowest cost at acceptable recall for this specific task. It proxies real Google results, passes through `site:` natively in the query string, offers the most permissive free-trial credits (2,500), the highest throughput at paid tiers (50–300 QPS), and uses a credit-based model with no monthly commitment — credits are valid for 6 months. At 17K queries, the Starter pack ($50/50K credits, $1.00/1K) leaves ample headroom. At recurring 17K–100K/mo scale, the Standard pack ($375/500K, $0.75/1K) drops costs further.[^2][^1]

The ToS is clean for commercial automated use. The only caveat: Serper publishes no formal SLA, though credits are not billed on failures.[^42][^53]

**Suggested query pattern:**
```
q = "<school name> <state> bell schedule start end times site:<district_domain>"
num = 10  (default; 1 credit per query)
```

### (b) Cost-Minimizing Cascade

For maximum recall at minimum cost, run a two-stage pipeline:

**Stage 1 — Serper.dev** (cheap Google results, ~$0.75–1.00/1K)
- Run the domain-scoped query.
- If ≥1 organic result is returned whose URL matches expected bell-schedule path patterns (e.g., `/bell-schedule`, `/schedule`, `/calendar`), accept and pass to the downstream fetch-and-parse step.

**Stage 2 — Bright Data SERP API** (Google proxy, pay-per-success, $1.50/1K PAYG)
- Fire only on misses from Stage 1 (no results returned, or all results clearly irrelevant).
- Bright Data adds value here because: (1) it has unlimited concurrency for faster burst processing of the miss queue; (2) its 99.9% formal SLA provides production reliability confidence; (3) it explicitly handles CAPTCHA-solving and anti-bot unlocking internally, which may improve success on difficult domains; (4) pay-per-success billing means you only pay for actual result pages.[^62][^61][^51]
- Optionally, on Bright Data misses, widen the query (drop `site:` restriction and search broadly for the school name + schedule) to detect cases where the bell schedule is hosted on an unexpected subdomain or third-party service.

**Estimated cascade cost** at 17K schools, assuming ~15% miss rate requiring Stage 2:
- Stage 1: 17,000 × $1.00/1K = **$17.00**
- Stage 2: 2,550 × $1.50/1K = **$3.83**
- **Total: ~$21/batch run** at entry scale. At recurring 100K/mo, Serper Standard ($0.75/1K) + Bright Data PAYG: ~$86.

### (c) Providers to Avoid for This Use Case

**SerpApi — Avoid (legal risk):**
Google filed a DMCA lawsuit against SerpApi in December 2025, alleging circumvention of its SearchGuard anti-bot system and unlawful resale of copyrighted content at massive scale. SerpApi filed a motion to dismiss in February 2026 but the case is actively pending. The lawsuit seeks a permanent injunction that would shut down SerpApi's core business. Committing production infrastructure to a vendor facing potential forced shutdown is a serious operational risk, irrespective of how the legal merits resolve. Pricing is also significantly higher than alternatives ($15/1K at entry tier vs. Serper's $1/1K).[^4][^54][^56][^63][^64][^3]

**Brave Search API — Avoid (wrong tool for this specific task):**
Brave's independent index and its inability to do a strict `site:`-equivalent domain scoping (requiring Goggles instead) makes it unreliable for per-district domain restriction. The base plan also explicitly prohibits storing API results, which conflicts with any pipeline that logs discovered URLs to a database. At $5/1K flat, it is 5× the price of Serper without the recall advantage for Google-indexed K–12 pages.[^35][^57][^24]

**Exa — Avoid (wrong index architecture):**
Exa's neural semantic index excels at broad, fuzzy, meaning-based retrieval. For domain-scoped keyword retrieval of a specific institutional page (`site:district.org bell schedule`), Exa's $7/1K pricing is the highest in the comparison for no recall benefit — the index is curated toward high-quality content and may underindex thin institutional CMS pages on Edlio, Apptegy, or Finalsite platforms. Its ToS restriction on storing output data is also a concern.[^52][^57][^26]

**OpenRouter gpt-4o-mini-search-preview — Avoid (wrong product type):**
At ~$27.50/1K tool-call requests plus token costs, this is the most expensive option by far. More critically, it returns AI-synthesized text answers, not a structured URL list. It cannot be reliably domain-scoped, and the synthesized answer may hallucinate or summarize page content rather than providing the actual URL for downstream fetching. It is best understood as a baseline to illustrate why a purpose-built SERP API is the correct category of tool.[^20][^19]

**LangSearch — Experimental only (no domain restriction, unknown K–12 recall):**
The free price is attractive, but LangSearch has no documented domain restriction parameter, which is non-negotiable for this pipeline. Its proprietary index coverage of long-tail U.S. K–12 district pages on niche CMS platforms is entirely unverified. Rate limits at the free tier (1 QPS, 1,000 QPD) are insufficient for batching 17K schools. It could be used as a low-cost exploratory fallback for Tier 3 (after Serper and Bright Data both miss) once the team validates recall empirically.[^47][^14][^27]

***

## Additional Notes

**Apptegy path structure:** Many Apptegy-hosted district sites use paths like `/o/schoolname/` — the `site:` operator will capture these because they are subpaths of the district domain, not subdomains. Verify that your district domain inventory captures the actual registered domain (e.g., `somersd.org`) rather than a subdomain, because `site:somersd.org` will include `www.somersd.org`, `calendar.somersd.org`, etc., while `site:www.somersd.org` will not return subdomain pages.[^65]

**Finalsite and Edlio:** Both platforms host school sites on the district's own custom domain (Finalsite) or on `edlio.com` subdomains (Edlio). For Edlio-hosted schools, the district may appear at `districtname.edlio.com`. Your domain inventory should account for this — a `site:sitesubdomain.edlio.com` query will work normally through any Google-proxy SERP API.[^66]

**Result count:** Request `num=5` or the default 10 results per query. For a domain-scoped `site:` query targeting a specific document type, the true page — if it exists — almost always ranks in positions 1–3. Requesting more results costs additional credits on some plans (Serper counts 100-result pages as 2 credits) and adds no recall benefit at this scope.[^67]

**Recall ceiling:** Even with Google (the best available index), some district bell schedule pages may be excluded from the index if they require authentication, are served as PDF attachments not indexed as pages, or are recently published. Budget for a ~5–10% manual review rate regardless of provider.

---

## References

1. [Best Serper Alternatives (2026): Google SERP API Pricing](https://www.buildmvpfast.com/alternatives/serper) - Serper sells credit packs with volume discounts: Starter is $50 for 50K credits ($1.00/1K), Standard...

2. [Serper Reviews, Pricing & Alternatives (2026) | Toolradar](https://toolradar.com/tools/serper) - Serper: The fastest and cheapest Google Search API for real-time SERP data. Paid tool. Compare featu...

3. [SerpAPI API Pricing Calculator (2026) | BuildMVPFast](https://www.buildmvpfast.com/tools/api-pricing-estimator/serpapi) - Calculate SerpAPI API costs for your startup. Estimate monthly costs with our free pricing calculato...

4. [High Volume Pricing](https://serpapi.com/high-volume) - SerpApi has high volume plans to satisfy even the most demanding workloads. Choose your plan. Month ...

5. [SearchApi Pricing 2026: Pay-Per-Success SERP API Costs](https://thatmarketingbuddy.com/pricing/searchapi) - SearchApi pricing breakdown: Free 100 searches, then $40-$500/month. Only pay for successful request...

6. [Google Search API for real-time SERP scraping](https://www.searchapi.io) - Real-time SERP API for easy SERP scraping. Pay only for successful searches. Precise coordinate-leve...

7. [Zenserp API Pricing - Affordable Search APIs](https://zenserp.com/pricing-plans/) - Discover Zenserp's pricing for search APIs, including Google, Bing, and Yandex. Affordable plans for...

8. [Pricing - Brave Search API](https://api-dashboard.search.brave.com/documentation/pricing) - $5.00 per 1,000 requests Sign up Includes free $5 in credits every month. $4.00 per 1,000 queries + ...

9. [Brave Search API Pricing 2026: Plans, Costs & Free Tier](https://vibecodedthis.com/pricing/brave-search-api-pricing/) - Brave Search API pricing 2026: Free tier available. Compare all plans, features, and find the right ...

10. [Pricing - Tavily Help Center](https://help.tavily.com/articles/8816424538-pricing) - At Tavily, we offer flexible pricing plans to suit different users, from individual researchers to g...

11. [API Credits Costs](https://docs.tavily.com/documentation/api-credits)

12. [API Pricing - Exa](https://exa.ai/pricing) - Explore Exa AI pricing – flexible plans to scale your AI with powerful, real-time web search.

13. [What Is Exa AI? Search API, Pricing, MCP, and Where It Fits (2026)](https://fastcrw.com/blog/what-is-exa-ai) - What Exa AI actually does, how Exa Search works, what Exa MCP gives you, and when fastCRW is the bet...

14. [LangSearch Pricing | Free access as we build AGI together](https://langsearch.com/pricing) - No fees. No subscriptions. For individuals and small teams, free access as we build AGI together. No...

15. [LangSearch : p/langsearch | Product Hunt](https://www.producthunt.com/p/langsearch/langsearch) - LangSearch offers two Free APIs: Free Web Search API and Free Rerank API, designed to connect your L...

16. [SERP API Pricing Plans - Bright Data](https://brightdata.com/pricing/serp) - SERP API Pricing - Search engine scraping tool pricing explained. Choose your plan and start collect...

17. [Planes de precios de la API SERP - Bright Data](https://brightdata.es/pricing/serp) - Precios de la API SERP: precios de la herramienta de scraping de motores de búsqueda explicados. Eli...

18. [Oxylabs Introduces Self-Service, Adjusts Scraper Pricing](https://proxyway.com/news/oxylabs-self-service-new-plans-web-scrapers) - The provider makes it easier to pick up its web scraping APIs and clarifies enterprise pricing.

19. [GPT-4o-mini Search Preview - API, Providers, Stats](https://openrouter.ai/openai/gpt-4o-mini-search-preview-2025-03-11)

20. [OpenAI: GPT-4o-mini Search Preview – Uptime and Availability](https://openrouter.ai/openai/gpt-4o-mini-search-preview/uptime) - It's priced per token (input and output), making it suitable for high-volume transcription workflows...

21. [Serper API - Fast Google Search Results (SERP) JSON | FreeAPIHub](https://freeapihub.com/apis/serper-api) - Serper returns the actual Google SERP structured as JSON — ideal when you specifically need Google's...

22. [SerpApi: Google Search API](https://serpapi.com) - SerpApi is a real-time API to access Google search results. We handle proxies, solve captchas, and p...

23. [Documentation - Brave Search API](https://api-dashboard.search.brave.com/documentation)

24. [Brave Search API | Brave](https://brave.com/search/api/) - Enterprise-grade Web search API accessing an index of 40+ billion pages. Specialized endpoints to tr...

25. [Web Search Essentials - Tavily Docs](https://docs.tavily.com/examples/quick-tutorials/search-api)

26. [The Exa Index](https://exa.ai/docs/reference/the-exa-index)

27. [LangSearch | Free Web Search API, Free Rerank API. The World ...](https://langsearch.com) - A Web Search API supporting natural language search. Get enhanced search details from billions of we...

28. [LangSearch - Free Web Search API, Free Rerank API, The World ...](https://github.com/langsearch-ai/langsearch) - LangSearch Database is a cutting-edge hybrid search database designed to provide highly relevant and...

29. [Introduction to SERP API - Bright Data Docs](https://docs.brightdata.com/scraping-automation/serp-api/introduction) - Use the Bright Data SERP API to collect structured search results from Google, Bing and other engine...

30. [Google Search API - Free Trial - Bright Data](https://brightdata.com/products/serp-api/google-search) - Bright Data's Google SERP API enables you to get real user search results from all major search engi...

31. [Scraping the Google SERPs with Python and Oxylabs' API](https://www.danielherediamejias.com/scraping-google-serps-python-oxylabs/) - On this post I am going to show you how to use Oxylabs with Python and how to get the most out of it...

32. [GPT-4o-mini Search Preview - API Pricing & Providers - OpenRouter](https://openrouter.ai/openai/gpt-4o-mini-search-preview) - GPT-4o mini Search Preview is a specialized model for web search in Chat Completions. $0.15 per mill...

33. [Advanced Google Query Parameters - SerpApi](https://serpapi.com/advanced-google-query-parameters) - Access additional Google query parameters such as as_dt and as_eq to give you better control over th...

34. [Google Search Scraper API](https://www.searchapi.io/docs/google) - SearchApi builds it for you when you use the location parameter, but you can provide your own if you...

35. [Introducing Drupal Goggles for Brave Search](https://kevinquillen.com/introducing-drupal-goggles-brave-search) - The Brave team has introduced a new feature for their Brave Search engine called "Goggles". Goggles,...

36. [Goggles - Brave Search API](https://api-dashboard.search.brave.com/documentation/resources/goggles)

37. [Controlling Search Results with Include and Exclude Domains](https://help.tavily.com/articles/9712346824-controlling-search-results-with-include-and-exclude-domains) - Tavily allows you to refine your web search results by including or excluding specific domains. This...

38. [Can you make the API endpoint only return results from a specific domain?](https://community.tavily.com/t/can-you-make-the-api-endpoint-only-return-results-from-a-specific-domain/653) - Can you make the API endpoint only return results from a specific domain? If so, which Tavily produc...

39. [Include_domains returning irrelevant results when including multiple domains](https://community.tavily.com/t/include-domains-returning-irrelevant-results-when-including-multiple-domains/276) - Has anyone encountered the issue where including multiple domains using the API returns irrelevant r...

40. [Exa Search Agent Example - LMSystems SDK](https://docs.lmsystems.ai/docs/sdk/graphs/exa-search-agent) - This guide demonstrates how to use the exa-search-react-agent-61 graph for performing targeted web s...

41. [Exa](https://docs.llamaindex.ai/en/v0.10.33/api_reference/tools/exa/)

42. [serper - rramos.github.io](https://rramos.github.io/2024/06/13/serper/) - Higher concurrency limits are available upon request. Real-Time Queries: All API calls query Google ...

43. [SerpApi Pricing 2026](https://www.g2.com/products/serpapi-serpapi/pricing?open_modal_url=%2Fes%2Fproducts%2Fserpapi-serpapi%2Fwishlists%3Fhost_path%3D%252Fproducts%252Fserpapi-serpapi%252Fpricing)

44. [Serper - The World's Fastest and Cheapest Google Search API](https://serper.dev) - Industry-leading SERP API, delivering lightning-fast Google search results in 1-2 seconds, at an unb...

45. [Terms of Service - Google Search API](https://www.searchapi.io/legal/terms) - We are committed to providing you with reliable service, and as part of our commitment, we offer a 9...

46. [SERP API Parallel Throughput - Rate Limits by Provider](https://scavio.dev/glossary/serp-api-parallel-throughput) - SERP API parallel throughput is the maximum concurrent queries a provider handles. Compare QPS limit...

47. [API Limits - LangSearch](https://docs.langsearch.com/limits/api-limits) - We implement rate limiting based on the cumulative recharge amount of the account. The details are a...

48. [Search API - Reviews, Pricing, Features | SERP AI](https://serp.ai/products/searchapi.io/reviews/)

49. [status.searchapi.io - Status](https://status.searchapi.io)

50. [Tavily 2026 : AI Search API for RAG and Autonomous Agents](https://myaiguide.co/tools/tavily) - Tavily is a specialized search engine API for AI agents and RAG pipelines. Get real-time, LLM-optimi...

51. [SLA - Bright Data](https://brightdata.com/sla) - Service Level Agreement. Last Updated: May 24, 2026. This Service Level Agreement (“SLA”) for the se...

52. [FAQs - Exa Docsdocs.exa.ai › reference › faqs](https://exa.ai/docs/reference/faqs)

53. [Terms of Service - Serper](https://serper.dev/terms) - By accessing the Service and Data at serper.dev you agree to be bound by these Terms of Service, all...

54. [Why we're taking legal action against SerpApi's unlawful scraping](https://blog.google/innovation-and-ai/technology/safety-security/serpapi-lawsuit/) - We filed a suit today against the scraping company SerpApi.

55. [SerpApi vs Google and the Future of SEO - Silktide](https://silktide.com/blog/serpapi-vs-google-lawsuit/) - This case will determine whether competitive analysis remains possible or becomes legally prohibited...

56. [Google Sues SerpApi for 'Parasitic' Scraping and Circumvention of ...](https://ipwatchdog.com/2025/12/26/google-sues-serpapi-parasitic-scraping-circumvention-protection-measures/) - On December 19, Google LLC filed a complaint in the U.S. District Court for the Northern District of...

57. [Hacker News](https://news.ycombinator.com/item?id=45378135)

58. [Clarify possible Brave Search TOS violation · Issue #522 - GitHub](https://github.com/modelcontextprotocol/servers/issues/522) - Is your feature request related to a problem? Please describe. When I installed the Brave Search MCP...

59. [Brave Search API Pricing 2026 - TrustRadius](https://www.trustradius.com/products/brave-search-api/pricing) - Plans ; Data for AI - Base. $5. per month / 20 queries/second Up to 20M queries/month ; Data for AI ...

60. [Bright Data License Agreement](https://brightdata.com/license) - This use of the System is available for commercial use under this Agreement. II. During the term of ...

61. [SERP API FAQs - Bright Data Docs](https://docs.brightdata.com/scraping-automation/serp-api/faqs)

62. [SERP Pricing & Billing](https://docs.brightdata.com/scraping-automation/serp-api/pricing-and-billing)

63. [SerpApi Challenges Google's Right To Sue Over SERP Scraping](https://www.searchenginejournal.com/serpapi-challenges-googles-right-to-sue-over-serp-scraping/568084/) - SerpApi filed a motion to dismiss Google's DMCA lawsuit, arguing the search giant lacks standing to ...

64. [SerpApi moves to dismiss Google scraping lawsuit](https://searchengineland.com/serpapi-motion-dismiss-google-scraping-lawsuit-469889) - SerpApi says Google is stretching the DMCA to protect ad revenue, not copyrights — casting the case ...

65. [Searching through a specific list of websites using Google Search](https://stackoverflow.com/questions/78896662/searching-through-a-specific-list-of-websites-using-google-search) - I'm using SerpAPI Google Search to find shopping results and I have been trying to find a way to lim...

66. [Edlio School District](https://district.edlio.com) - Edlio School District, Home of Spike! Address: 12910 Culver Blvd. Suite H, Los Angeles, CA 90066 Pho...

67. [That seems expensive. For 100 results per query, serper.dev is $2 ...](https://news.ycombinator.com/item?id=43921687) - They bill at $50/50,000 credits, so it becomes $1/1000 requests if you are okay with just 10 results...

