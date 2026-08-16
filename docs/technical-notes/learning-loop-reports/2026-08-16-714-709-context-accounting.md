# #714/#709 — per-model context accounting & the council-degraded marker: findings & design

> **Authority:** point-in-time findings + plan for Tranche C step 2 (#714 sizing, #709 silent
> single-family degradation), 2026-08-16. Where this disagrees with `STAGE7_EXTRACT_DESIGN.md`
> after landing, that note is authoritative.
> **Companions:** #714, #709 · #80 (Council Lab — owns the composition half both issues defer) ·
> #169/#180/#187 (the sizing/retry mechanisms this corrects) · #176 (barren-rep suppression) ·
> #716 (the replay that back-fills the marker) · `EXTRACTION_TOKEN_SIZING_2026-07-06.md` (the
> 47-tokens/school output model, unchanged here).
> **Update this when:** never, except §5's implementation log.

## 1. The measured facts

**Real windows (OpenRouter `/api/v1/models`, fetched 2026-08-16)** for the 7 catalogued models:

| model | context | max_out |
|---|---|---|
| google/gemini-2.5-flash(-lite) | 1,048,576 | 65,535 |
| mistralai/mistral-small-24b-instruct-2501 | **32,768** | **16,384** |
| mistralai/mistral-large-2512 | 262,144 | — (shares ctx) |
| deepseek/deepseek-v3.2 | 163,840 | 65,536 |
| qwen/qwen3-235b-a22b-2507 (the low-cost-text **judge**) | 262,144 | **16,384** |
| qwen/qwen3-vl-235b-a22b-instruct | 262,144 | 32,768 |

`MAX_TOKENS_CEILING = 32000`'s stated premise — "inside all six council models' completion
windows" — is **false for three of seven models**. For mistral-small it is doubly false: 32,768
is *total* context, so any prompt beyond ~768 tokens with an at-ceiling `max_tokens` is
auto-rejected (the Orange/Memphis 400), and even a fitting request exceeds its 16,384 completion
cap. The low-cost-text judge shares that 16,384 cap — a mega-roster judge reply cannot fit
either, so escalation cannot rescue what the voter pair loses.

**Corpus population (20,927 usable text reps with `n_times`):** 35 reps (0.2%) size past the
16,384 completion cap · **8 reps across 3 districts** (Chicago `1730540`, Memphis `4700148`,
Orange `1201440`) size into the 400 shape · 7 sit at the 32k ceiling with no retry headroom.
The failure is a tail phenomenon that lands exactly on the richest documents (#709's point) —
and far too small a population to justify guessing a chunking design here. Chunking/routing is
**measured composition work and goes to #80** with these numbers, as both issues instruct.

## 2. The design (runtime only; composition deferred to #80)

1. **`MODEL_WINDOWS`** joins `model_families.py` (the one-home model catalog): per-model
   `{context, max_out}`, values checked in with fetch date + refresh command — deterministic and
   test-visible, no runtime network dependency. A DB-free parity test pins
   `set(MODEL_WINDOWS) == set(FAMILY)` so a model added to the catalog without windows fails
   loudly (councils.validate already forces catalog membership).
2. **Per-call clamp** in `openrouter.call()`: estimated prompt tokens (chars/3, conservative)
   → `cap = min(max_out or context, context − est_prompt − margin)`; `max_tokens = min(sized,
   cap)`. The #169 truncation retry escalates to `min(MAX_TOKENS_CEILING, cap)`, never past the
   model. Unknown models (test fakes, future additions pre-catalog) keep legacy behavior.
3. **Pre-flight refusal**: if `cap` leaves less than a minimum useful output, the call is refused
   *before spending* — `ok=False, error_kind="context"` (the spend-conservative auto-act
   direction: the failure is observable, and the refusal reversible by re-routing).
4. **`error_kind="context"`**: provider 400s matching context-length messages classify as
   structural, distinct from `transient`.
5. **`council_degraded` on the rep** (#709): any *voter* call refused or failed structurally ⇒
   cross-family consensus was impossible by construction; the rep records
   `{models, reasons}` — receipt-visible, distinguishable from barren. Derived identically in
   `reaggregate._rebuild_rep` from stored call records, so **existing receipts (Memphis, Orange)
   gain the marker retroactively at zero spend**.
6. **Barren-rep honesty** (#709 acceptance): a degraded rep's remedies fire with a reason that
   says *council-degraded, re-route* (not "document produced nothing"), and suppressions count
   separately in `explain` — a degraded zero is never evidence a document is empty.
7. **NOT done here**: raising per-model ceilings above 32k (gemini could take 65k — a
   cost/behavior change for #80 to measure), chunking/band-splitting (8-rep population, #80),
   substitute voters (#80), the gate@7 console badge (Tranche D, with #775).

## 3. Acceptance (falsifiable)

- **P1 (must fail today):** a 1,020-time rep composed against mistral-small clamps below
  `32,768 − prompt`; today it sends 32,000 and 400s.
- **P2:** a call whose cap leaves < minimum useful output refuses pre-flight at zero cost with
  `error_kind="context"`.
- **P3:** a provider context-length 400 classifies `error_kind="context"`, not `transient`.
- **P4 (must fail today):** a rep with a structurally-failed voter is marked `council_degraded`
  in the run output and receipt; a replay of Memphis `3004896917ca`'s stored receipt derives the
  same marker.
- **P5:** a degraded rep's 7→6 remedy reason names the degradation; suppression counts land in
  `explain["suppressed_degraded_reps"]`, not the barren count.
- **P6:** the truncation retry never exceeds a model's cap (mistral-small retry ≤ 16,384).
- **P7:** unknown models (test fakes) behave exactly as before — every existing suite green
  untouched.

## 4. Routed to #80 (with the measurement)

Composition candidates for the 35-rep tail, to A/B in the lab, not assert: long-context council
routing by `n_times` (mistral-large 262k + gemini 65k-out both fit Orange whole) · per-band
chunked dispatch · substitute voter on context dropout · per-model ceiling raise. The corpus
numbers above are the lab's starting population.

## 5. Implementation log

*(append as it lands)*
