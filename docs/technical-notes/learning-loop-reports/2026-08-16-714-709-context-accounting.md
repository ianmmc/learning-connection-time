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

**2026-08-16 — implemented in one pass** (`MODEL_WINDOWS`/`usable_output` in `model_families`,
the clamp/pre-flight/classification/retry-cap in `openrouter.call`, `council_degraded` in
`stage7_run` shared with the #716 replay, the degraded-vs-barren split in `requests.detect`).
P1–P7 pinned in `tests/test_model_windows.py` + the `explain` split in `test_stage7_requests`.
P4 verified end-to-end against BOTH filed receipts: Memphis `3004896917ca` rep `00f553bcfc` and
Orange `0e1bf02c3ea6` rep `b8f930171d` each derive `council_degraded: mistral-small` on a dry
replay — with the roster-identity fix (Tranche C step 1) compounding on Memphis's sibling rep
(42 accepted). Faked-client tests reuse the httpx-backed `APIStatusError` construction from
`test_stage7_openrouter.py`. No live re-replay run here: the marker changes receipts/`explain`
only — no consensus outcome shifts — so receipts backfill naturally the next time any replay or
follow-up touches them.

**2026-08-16 (same day) — #793: the clamp had to be paid for.** Reviewing the hub-page question
(#795/#796) turned up the cost of §2's own fix. §2.2's clamp is right, but on the Orange shape it
does not *prevent* the failure, it **changes its shape**: instead of requesting 32,000 and taking a
provider 400 (`error_kind='context'` → marked, remedy says re-route), the call now requests 16,384,
**succeeds**, and truncates. Reproduced against this branch's code:

```
sizing asked for 32000; max_tokens actually sent: [16384]
ok=True  truncated=True  finish_reason='length'  retried=False  error_kind=None
council_degraded(...) -> None
```

No retry, because `retry_ceiling = min(MAX_TOKENS_CEILING, cap) = 16384` and the call was already
sent at 16,384. And a grep of every consumer of `finish_reason`/`truncated` outside `openrouter.py`
returned **three hits, all display**: a per-rep progress line, a telemetry counter, a `[done]` line.
So a partial roster entered consensus indistinguishably from a complete one — §2.6's "a degraded
zero is never evidence a document is empty" had an unguarded twin: *a partial is never evidence
that was the whole roster*.

Already in shipped data, from a scan of all 2,586 stored call records: 9 truncated calls in 4
districts, including **Baldwin `0100270` keeping 355 facts** and **Stroudsburg `4222860` keeping
420** (×3 runs) from replies that ran out of room. Those read as clean.

Fix (P8/P9): `council_degraded` gains `kinds` — `context_refused` vs `window_truncated` — with the
vocabulary in `common/model_families.py` because the layering contract forbids `stage7_extract`
importing `process_governance`. Since #169 retries whenever headroom remains and keeps the retry's
content, a `length` finish on the final result is terminal, so no new state is needed to detect
"headroom exhausted". Refusal outranks truncation for a model in both states; a recovered retry
does not mark; a judge truncation does not mark. `explain` splits
`suppressed_truncated_reps` from `suppressed_degraded_reps`, and the remedy wording says PARTIAL,
not empty.

Verified against the corpus rather than asserted: **22 (district, rep, shape) degradations are now
derivable from shipped receipts at zero spend**, four of them the new truncation shape (Orange
`1201440`, Stroudsburg `4222860`, Baldwin `0100270`, Bentonville `0503060`).

One nuance found and deliberately left alone: the marker fires on a lost VOTER even when a
third-family **judge** covered the gap — Broward `1200180` accepted 201 facts via `method='judge'`
with mistral refused, so REQ-056 held and nothing was lost. That is honest (a voter *was* lost) and
harmless (degraded remedies only fire on zero-yield records). Whether gate@8 should distinguish
"degraded but judge-covered" is a surface question for #775.

**The lesson this adds to §10.11's tally:** a fix that removes a failure's *symptom* has to be
checked for whether it removed the failure or only its **visibility**. The clamp was justified as
"the 400 shape becomes unrepresentable" — true, and the reason the 400 stopped appearing was that
the same event now succeeded quietly.

**2026-08-16 (review round #797-#811) — 15 findings on this branch, all 15 confirmed real, all
fixed before merge.** The headline (#797) was #793's own fix repeating #793's mistake one level
up: the truncation marker landed, but remedies consulted it only on the ZERO-YIELD path — a gate
that catches refusals (zero by construction) and structurally misses truncations (partial is
their normal case). Baldwin's 355-fact partial was marked and then ignored: no remedy, no count,
district reads DONE-ENOUGH. Fixed by remedying `window_truncated` on fact-count evidence (7→6
when a gap + alternate exist; counted in `explain` otherwise). Three findings (#798/#799/#810)
were one defect family — the refusal-outranks-truncation rule and the absent-`kinds` default
expressed in two idioms at two grains — collapsed into `model_families.strongest_kind` (absent
defaults to the STRONGER refusal; per-record kinds merge across ALL of a record's reps, never
last-write-wins, the #785 shape again). #800: the zero-spend replay derived markers that changed
nothing downstream — `reaggregate` now runs `detect_and_persist_requests` (idempotent, #234
dedup, production-only per #148). The rest: per-model cap in the run-log truncation lines via
`CallResult.max_tokens_sent` (#801) · `error_kind` authoritative over text markers (#802) ·
mid-stream SSE errors classify through the shared `classify_error` (#803) · the per-rep except
branch attaches the marker (#804) · image parts cost `IMAGE_PART_EST_TOKENS` so the clamp isn't
inert for vision (#805) · `CallResult.was_billed` stops crossfam booking $0 refusals at estimate
(#806) · the new `explain` counters print (#807) · the REQ-174 duplicate-`notes:` YAML key that
silently discarded this very narrative, now guarded ledger-wide (#808) · a nightly value-drift
detector for MODEL_WINDOWS (#809) · exact-value pins on both terms of the clamp's min() (#811).
The batch-diff countermeasure held: #799 was this batch's own #785 shape caught crossing files,
and #808 was the ledger's first parse-loss — both now have class-level guards, not spot fixes.
