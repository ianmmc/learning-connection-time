# Cross-Family External Code Review — effectiveness analysis (2026-07-13)

> **Authority:** the empirical results of the first cross-family external review campaign — 10 non-Claude
> OpenRouter finder families + a rotating 3-family judge cascade over the whole codebase. Numbers are
> computed from the run's persisted receipts (`data/review/crossfam-2026-07-13/`: `raw_findings.json`,
> `adjudications.json`, `raw_replies.jsonl` with per-call `usage.cost`), not estimates.
> **Audience:** anyone tuning the external-review roster for a later sweep, or reasoning about
> cross-family model behavior generally.
> **Companions:** the harness itself (`tools/crossfam_review/`, `README.md`); the council design it
> mirrors (`models-and-council-composition/`, REQ-056); `PROJECT_HISTORY.md` (2026-07-13 entry).
> **Update this when:** a new external-review sweep produces materially different roster behavior.
> Point-in-time findings from a single campaign stay dated.

---

## 0. The run

The harness (`tools/crossfam_review/`) delegates a full read of the codebase to a diverse set of
**non-Claude** models (the project is already reviewed heavily by Claude variants; the value is the
different blind spots of other families), then adjudicates their findings through a **rotating
cross-family judge cascade** — the same REQ-056 mechanism the extraction pipeline uses, applied to code
review. Rationale: this codebase's own council data proved diversity (not count) drives correctness and
that a third-family judge is load-bearing.

**Scope:** 36 shards over `infrastructure/` + `tests/` (~895k tokens of source), each finder reviewing
every shard.

**Finders (10 families):** deepseek-v4-flash, kimi-k2.5, qwen3.7-plus, xiaomi/mimo-v2.5-pro,
minimax-m2.7, gemini-2.5-flash-lite, gpt-4.1-mini, x-ai/grok-build-0.1, mistralai/devstral-2512,
llama-4-maverick. (z-ai/glm-4.7-flash and gpt-5.1-codex-mini were dropped pre-run — reasoning models
that stream thinking the shared client can't capture and returned empty content; see `roster.py`.)

**Judges (rotating cascade):** google/gemini-2.5-pro, openai/gpt-5.6-luna, deepseek/deepseek-v4-pro —
two cross-family voters per candidate, a third breaks a split, **roles rotate per candidate** so no
model is permanently the tie-breaker.

**Funnel:** 2,949 raw findings → 1,833 unique (dedup by file+line-bucket+category) → **459
corroborated** (≥2 finder families, the council's input; 1,374 singletons held back, never filed) →
**214 confirmed** by the council → filed as GitHub issues #259–#472 under `crossfam-review-2026-07-13`.

**Cost:** ~$22.4 total (finder pass $11.52 + council $3.50 in the first pass, capped at $15; a
resume pass judged the 163 budget-starved candidates for $2.83; ~$4.6 earlier went to staged smoke
tests that surfaced six harness bugs before the real run).

> **Caveat that governs every per-model number below:** because the council only judged the
> **corroborated** set (≥2 families), no confirmed finding was a single-family catch. So "confirmed
> contribution" and "precision" here describe a model's role in *corroborated* discovery, not solo
> discovery. Measuring unique-catch value would require a separate `--min-agree 1` pass.

---

## 1. Diversity is real and quantified (Q: which models agree most?)

Most-overlapping finder pairs, over the 459 adjudicated candidates:

| pair | shared candidates | Jaccard |
|---|---:|---:|
| kimi-k2.5 + qwen3.7-plus | 68 | 0.28 |
| gemini-flash-lite + devstral-2512 | 65 | 0.28 |
| gemini-flash-lite + gpt-4.1-mini | 56 | 0.26 |
| kimi-k2.5 + grok-build-0.1 | 57 | 0.25 |

**The signal isn't the top pair — it's that the maximum Jaccard is only 0.28.** Even the two
most-agreeing models overlap on barely a quarter of what they find. Cross-family models genuinely see
different things; the diversity thesis is confirmed on real data.

## 2. Universal agreement essentially never happens (Q: did all 10 ever agree?)

**No.** Maximum agreement was **8 finders**, on just **2 candidates** — both the "obvious" bugs
(`school_discovery.py:122` domain-redirect substring match; `fetch_nces_ccd.py:297` interactive-input
hang in a non-interactive env), both confirmed. The cluster-size distribution decays steeply:

| finders agreeing | candidates |
|---:|---:|
| 8 | 2 |
| 7 | 6 |
| 6 | 13 |
| 5 | 31 |
| 4 | 53 |
| 3 | 86 |
| **2** | **268** |

Thin corroboration is the norm — which is exactly why `--min-agree 2` retained 459 candidates while a
stricter threshold would have collapsed the set (≥8 would keep 2).

## 3. Finders bring different lenses, not just redundancy (Q: what does each find?)

Most finders are correctness-dominant, but the distinctive category leanings matter for coverage:

| finder | notable lens |
|---|---|
| **mimo-v2.5-pro** | the *only* finder that leads with **data-integrity** (53) over correctness (50) |
| llama-4-maverick | data-integrity heavy (135 — 2nd most) |
| kimi-k2.5 | most **security** (29) |
| grok-build-0.1 | most **race / concurrency** (16) |

Diversity buys *category coverage*, not just repeated confirmation of the same class of bug.

## 4. Value per dollar (Q: most / least value?)

Using each finder's real billed cost (`usage.cost` summed over its 36 shard calls):

| model | confirmed | cost | **conf/$** | precision |
|---|---:|---:|---:|---:|
| **deepseek-v4-flash** | 65 | $0.20 | **325** | 0.43 |
| gemini-flash-lite | 41 | $0.19 | 216 | 0.27 |
| llama-4-maverick | 49 | $0.37 | 132 | 0.41 |
| minimax-m2.7 | 55 | $0.42 | 131 | 0.49 |
| gpt-4.1-mini | 48 | $0.51 | 95 | 0.39 |
| devstral-2512 | 56 | $0.60 | 93 | 0.37 |
| kimi-k2.5 | 106 | $1.22 | 87 | 0.72 |
| qwen3.7-plus | 96 | $1.24 | 78 | 0.60 |
| grok-build-0.1 | 79 | $2.65 | 30 | 0.59 |
| **mimo-v2.5-pro** | 42 | $1.42 | 30 | 0.86 |

- **Most value: `deepseek-v4-flash`** — cheapest and productive (325 confirmed/$).
- **Least value: `mimo-v2.5-pro` and `grok-build-0.1`** (~30/$). Grok is simply expensive; mimo is
  low-volume at high cost.
- **Highest absolute yield: kimi (106) and qwen (96)** — but at ~$1.2 each, only middling efficiency.

## 5. Roster recommendation for the next sweep (Q: exclude anyone?)

Marginal-value check — how many confirmed candidates would fall below ≥2 families if a model were
removed — combined with reliability (empties/errors):

- **`mimo-v2.5-pro` is the clearest exclusion candidate**: worst value/$, lowest marginal value (sole
  corroborator on just **14** confirmed), and the worst reliability (**10 errors + 4 empties**). Its
  only virtues are highest precision (0.86) and the unique data-integrity lens.
- **`minimax-m2.7`** is the runner-up concern (9 errors, mid-everything).
- **Keep `grok`** despite its cost — sole corroborator on **31** confirmed (high marginal coverage),
  unlike mimo.

**Recommendation:** for a cost-conscious sweep, drop `mimo` (lose a niche lens, save the
most-expensive-per-signal, least-reliable slot) and keep the other nine. If breadth outweighs cost,
keep all ten — none is dead weight; they differ in efficiency, not usefulness.

## 6. No family collusion in the judge cascade (Q: judge ↔ family-finder patterns) — **and a
methodology lesson**

Each judge had a same-family finder in the roster (gemini-2.5-pro ↔ gemini-flash-lite; deepseek-v4-pro
↔ deepseek-flash; gpt-5.6-luna ↔ gpt-4.1-mini). Does a judge favor its family's findings?

**The naive test is a trap.** Comparing a judge's confirm rate on {family-finder present} vs {absent}
made all three judges look *harsher* on their own family (two significant) — but that confounds
family with **finder quality**: a noisy finder's candidates (gemini-flash-lite precision 0.27) get
confirmed less by *everyone*, family judge or not.

**The controlled test** — family judge vs the *other* judges on the *same* candidates (holding
candidate quality fixed):

| judge ↔ family finder | family judge | other judges | Δ | verdict |
|---|---:|---:|---:|---|
| gemini-2.5-pro ↔ gemini-flash-lite | 0.38 | 0.28 | +0.11 | n.s. (p=0.079) |
| **deepseek-v4-pro ↔ deepseek-flash** | 0.34 | 0.52 | −0.18 | **significant (p=0.004)** |
| gpt-5.6-luna ↔ gpt-4.1-mini | 0.34 | 0.39 | −0.06 | n.s. (p=0.463) |

**Findings:**
- **No in-group favoritism anywhere.** The one confound-controlled significant effect is the *opposite*
  — `deepseek-v4-pro` is measurably *stricter* on its family finder's work than peers are (plausibly it
  recognizes and discounts its family's failure modes).
- gemini leans very slightly *toward* its family (n.s.); gpt shows nothing.
- **Operationally: the rotating cross-family cascade is not gamed by family collusion.** Same-family
  judging, if anything, adds skepticism rather than a rubber stamp — which validates using the REQ-056
  cascade for code review.

**The lesson threads the whole analysis:** the naive Q6 answer would have been *backwards* without
controlling for finder quality — the same "don't trust the uncontrolled number" discipline as the
ICC/DEFF clustering correction in the promotion gate (`stage5_filter/promotion_gate.py`).

---

## 7. Provenance

Campaign 2026-07-13, harness `tools/crossfam_review/` on branch `chore/cross-family-external-review`.
Receipts: `data/review/crossfam-2026-07-13/` (gitignored — regenerable). Filed issues: #259–#472 under
`crossfam-review-2026-07-13`, each carrying a machine-parseable `<!-- crossfam-meta:… -->` marker
(finder families + judge verdicts) for exactly this kind of triage. Statistics computed with
scipy/pandas (Fisher exact for the family-bias tests). The confirmed set is **vetted candidates
awaiting human triage**, not verified bugs — the council passes some false positives (a `--min-agree 1`
false positive rate was not measured this run).
