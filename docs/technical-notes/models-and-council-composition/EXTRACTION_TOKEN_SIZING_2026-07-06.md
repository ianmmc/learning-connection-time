# Extraction token sizing: why replies truncate, and how to stop paying twice

**Date:** 2026-07-06 · **Context:** #169 (truncation recovery) merged a bounded 16k→32k retry.
This note answers the follow-up: *given how terse we ask the council to be, why does anything
truncate at all — and can we avoid paying for the same document twice?*

**Data:** 840 real council calls across all `data/acquisition/extractions/*.json` receipts
(batch_00000 GT run + the batch_00009/00010 loop sessions).

---

## 1. The finding in one line

**Reply length is set by roster size, not model verbosity.** Output tokens scale ~linearly with
the number of schools in the representation, at a flat **~40–50 completion tokens per school**, with
essentially no verbosity noise. Truncation is a *big-document* event, never a *chatty-model* event.

| completion_tokens | share of 840 calls |
|---|---|
| < 200 (single / few-school reps) | **86%** |
| 200–2000 | 10% |
| ≥ 2000 (big rosters) | 3% |
| = 16000 (**truncated**) | **3 calls (0.4%)** |

- median completion = **50 tokens**; p95 = 1,320; p99 = 5,325.
- **tokens-per-school = 47 median / 48 mean** — dead flat from 1 school to 355. The "no commentary,
  compact JSON, no fences" prompt (`prompts.py`) is doing its job; there is no fat to trim on output.

So `output_tokens ≈ schools × ~47`. The old 16k cap ≈ **340 schools**; the #169 32k retry ≈ **680**.

## 2. The three truncations — and why input size can't predict them

All three `finish_reason="length"` calls were whole-district hub documents:

| district | file | input (pt) | schools (n_facts) | output (ct) |
|---|---|---|---|---|
| Baldwin County | camelot_stream.txt | 10,365 | 355 | 16,000 (cut) |
| Stroudsburg Area SD | camelot_hybrid.txt | **3,391** | 420 | 16,000 (cut) |
| Stroudsburg Area SD | camelot_hybrid.txt | **3,391** | 420 | 16,000 (cut) |

**The critical row is Stroudsburg.** Its *input* is small — 3,391 prompt tokens, below our median-ish
range — yet it carries a **420-school** dense table that explodes to 16k on output. A tight table is
compact on input and huge on output. **Therefore input-token size (prompt_tokens) is NOT a reliable
pre-dispatch predictor** of a truncating reply:

| pre-dispatch rule | flags | catches truncations | collateral |
|---|---|---|---|
| pt ≥ 3000 | 103 / 840 | 3 / 3 | flags 100 calls that were fine |
| pt ≥ 5000 | 34 / 840 | **1 / 3** | misses Stroudsburg entirely |
| pt ≥ 8000 | 24 / 840 | 1 / 3 | misses Stroudsburg entirely |

A prompt-token threshold that catches Stroudsburg (pt≥3000) mis-flags 100 innocent calls; any
threshold loose enough to avoid that mis-flagging *misses* Stroudsburg. Input size is the wrong signal.

## 3. The right signal is `n_times` — and we already persist it

Each school row has ~2 clock times (start + end). The count of time-of-day matches on a page —
**`n_times`** — is the pre-dispatch quantity that tracks roster size, and it is **already stored per
representation** (`representation.n_times`, written by `build_signals._rep`; also on each
harvest-slice's `rep_kwargs`). Unlike prompt_tokens it doesn't care about table density:

> **estimated schools ≈ n_times / 2  →  estimated output tokens ≈ (n_times / 2) × 47 ≈ n_times × 24.**

Stroudsburg's 420-school table has ~840 times → the estimator predicts ~20k output and would have
sized the very first call correctly. Baldwin's 355 → ~700 times → ~17k. Both caught, from a signal we
have *before* spending a cent, with no collateral on the 86% of reps that are small.

## 4. Answering the two proposals

**Q: "Pre-emptively up the cap if we believe we have a district-hub page from characteristics we
*do* know (e.g. number of times on the page)?"**
→ **Yes — and this is the recommended fix.** Size `max_tokens` per call from the rep's `n_times`:

```
max_tokens = clamp( ceil(n_times × 24 × 1.5), DEFAULT_MAX_TOKENS, HARD_CEILING )
```

The ×1.5 is headroom for grade-band splitting (a K-12 campus emits >1 row/school) and long names.
This pays **once**, at the right size, and the #169 retry becomes the rare safety net it should be —
firing only when `n_times` under-counts (image/scan reps where times weren't text-extractable).
Small reps (86% of traffic) keep the 16k cap; nothing regresses. This is the low-risk win.

**Q: "Or could we slice the content into chunks based on where the times are?"**
→ **Technically yes, and it removes the ceiling entirely, but it's the heavier option and not needed
yet.** Time-anchored chunking (split at time-position gaps, dispatch each chunk, union the facts)
never pays twice *and* has no roster ceiling — but it adds real risk and cost:
- a split can bisect one school's row (name above the split, times below) → lost or malformed school;
- union/dedup logic must run across chunks and reconcile the council per chunk;
- N chunks = N× the fixed per-call prompt overhead (the system prompt re-sent each time).

Given the measured reality — **0 reps exceed the 32k (680-school) ceiling; only 4 of 840 calls even
reach 8k** — chunking solves a problem we effectively don't have yet. Hold it as the escalation path
for the day a >680-school single document appears (none has), or if we ever want per-school cost
attribution. **`n_times`-based cap sizing is the right tool now.**

## 5. On "paying twice"

The #169 retry's double-charge is real but **rare and cheap**: 3 truncations in 840 calls (0.4%), on
low-cost-text-council models (~$0.0001–0.006/call). The `n_times` estimator converts almost all of
those into a single correctly-sized call. The retry stays as the honest backstop for the residual
(a scan/image rep whose times weren't countable up front), where paying twice genuinely buys recovery
we couldn't have sized for. Net: we stop pre-paying for the *predictable* big rosters, and keep the
retry only where prediction is impossible.

## 6. Recommendation

1. **Do now (small, low-risk):** thread the rep's `n_times` into the Stage-7 dispatch so `call()`
   receives an `n_times`-derived `max_tokens` instead of the flat 16k. Keep #169's retry as the
   backstop; keep the 16k floor for small reps. Raise `HARD_CEILING` to 32k so the estimator and the
   retry agree. Measured before/after: expect the 3 known truncations to size correctly on the first
   call and the double-charge to go to ~0 on text reps.
2. **Defer (heavier):** time-anchored chunking — hold as the escalation path for a genuine
   >680-school single document (none observed) or for per-school cost attribution.

This is a natural companion to **Batch 3** (loop correctness & spend). Filed as an issue for tracking
rather than folded silently into #169's PR.

### SHIPPED — #180 / #187 (Batch 3B)

Item 1 landed with one refinement vs. the plan: sizing recomputes the time-count from the RESOLVED
CONTENT at dispatch (`stage7_run._content_n_times` → `build_signals.time_positions`) rather than
threading `n_times` off the handoff — because `n_times` is dead-plumbed through freeze (0 of 275
handoff reps carry it; the cost-model's own scaler is affected too, tracked as #192). Recomputing from
content is more robust (works on every frozen handoff, old and new) and uses the exact signal that
*defines* `n_times`. `size_max_tokens(n_times)` = `clamp(ceil(n_times/2 × 47 × 1.5), 16000, 32000)`;
the retry now escalates to the SAME `MAX_TOKENS_CEILING` constant (`ESCALATED_MAX_TOKENS` renamed) so
sizing and retry can't drift (#187). **Measured replay over all 840 calls:** the 3 truncations size
enough on the first call (Baldwin 25028≥16685, Stroudsburg 29610≥19740); 0 calls would newly truncate
(the floor prevents regression); 0 image-rep truncations (so the retry backstop only covers the
genuinely-unpredictable residual). The replay is conservative — real dispatch counts *input* times,
which for a truncated call exceed the surviving `n_facts`, so real sizing is even more generous.

---

*Method: `data/acquisition/extractions/*.json`, per-call `prompt_tokens` / `completion_tokens` /
`finish_reason` / `n_facts`; `n_times` from `representation` (`build_signals.py`). Reproduce with the
inline scripts used to generate the tables above.*
