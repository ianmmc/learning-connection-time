# Models & Council Composition — the batch_00000 full-run report (2026-07-03)

> **Authority:** the empirical findings from Stage 7's first full runs against the curated ground truth
> — what the data says about model behavior, council composition, reader/rep-source yield, and the
> failure modes that survived into extraction. Numbers are from the persisted `extraction`/`school_fact`
> rows + the per-district receipts (`data/acquisition/extractions/extraction_a2bc80c004ca*_*.json`), not
> estimates. Where a finding implies a config change, it is a **hypothesis for the Council Lab (#80) to
> test**, not an adopted decision.
> **Audience:** anyone tuning council composition, routing, or the extraction prompt; the Council Lab.
> **Companions:** `STAGE7_EXTRACT_DESIGN_2026-06.md` (the stage), `STAGE6_DISPATCH_DESIGN_2026-06.md` §2a
> (the lab), §3A (council seeds — the composition this report tests), `EXTRACTION_BENCHMARK_FINDINGS.md`
> (the pre-pipeline model leaderboard this supersedes for clean data), GitHub #80 (Council Lab), #81
> (spray A/B), #82 (image-judge bug).
> **Update this when:** a new full run produces materially different numbers, or a composition change is
> adopted (record the before/after). Point-in-time findings from a single run stay dated.

---

## 0. The run

`batch_00000` = the 27 curated-GT districts (hand-verified per-school times), of which 24 were
send-eligible. Two full Stage-7 runs over the **same frozen gate@6 dispatch** (`handoff_a2bc80c004ca`):

- **TEXT** — the `low-cost-text` council (voters `gemini-2.5-flash-lite` + `mistral-small-24b` → judge
  `qwen3-235b`) over the text representations release/routing selected. 24 districts, 83 reps.
- **IMAGE** — the `image` council (voters `gemini-2.5-flash` + `mistral-large-2512` → judge
  `deepseek-v3.2`) over the in-store `raster_p` PNGs of the *same* documents, PNG-only (Cleveland is
  `.webp`-only, excluded → 23 districts, 80 reps). A controlled text-vs-vision probe on identical docs.

Both persisted per-district (durable + resumable) and were GT-scored per band (our modal gross vs GT
`_derived_band_gross`, ±15 min) and per school (matched by shared `norm_school`).

---

## 1. Headline results

| | TEXT | IMAGE |
|---|---|---|
| districts / reps | 24 / 83 | 23 / 80 |
| **band accuracy (GT)** | **95.2%** (60/63) | **88.5%** (46/52) |
| **per-school accuracy (GT)** | **99.3%** (673/678) | **98.1%** (418/426) |
| coverage gaps (GT band, no fact) | 3 | 12 |
| schools resolved (accepted) | **778** | 486 |
| unresolved (held-out disagreements) | 202 | 145 |
| model calls (judge) | 205 (39) | 193 (33) |
| **call errors** | **1** | **33** |
| cost | **$0.065** | **$0.273** |

*Not perfectly apples-to-apples:* image ran 23 districts, and its accuracy % is over a smaller denominator
(52 vs 63 compared bands) precisely because it resolved fewer bands (more gaps). The honest read is the
raw counts, not the ratio: **text resolved 778 schools across 60 hit bands; image 486 across 46.**

**The one-line finding:** on this corpus of *native-digital* documents, the text council is decisively
better — more coverage, ~4× cheaper, 33× more reliable — while both are ~98-99% *accurate on what they
resolve*. Vision is not inaccurate; it under-covers native text. This is the reader-routing thesis
confirmed at scale: **route digital text to the text council; reserve vision for the image-only/scan
cases it exists for.**

---

## 2. Council composition findings

### 2a. The judge is load-bearing — the 2-voter-pair-→-judge template earns its keep (text)

- **47% of reps escalated to the judge** (39/83). With only two voters, *any* cross-family disagreement
  fires the judge — and nearly half of reps disagreed.
- Of those 39 judged reps, **28 (72%) produced a judge-resolved accepted fact.** The judge is not a
  formality; it converts genuine disagreements into answers.
- **165 of 778 accepted facts (21%) came via the judge.** Remove it and text drops from 778 to 613
  resolved schools. **The pair+judge cascade (STAGE6 §2) is validated empirically** — the third-family
  judge materially expands coverage over a bare 2-voter pair.

Implication for composition: the high escalation rate (47%) also says the two voters *disagree a lot* —
so the judge quality matters as much as voter quality, and a stronger/cheaper judge is a high-leverage
knob. It's an open question whether a third *voter* (a 3-model panel) would beat pair+judge here; the
research prefers the cascade for cost, and this run shows the cascade working, but the lab should measure it.

### 2b. The image council's judge is DEAD — `deepseek-v3.2` has no vision (→ #82)

- **All 33 image call errors were the judge**, identical: `404 — No endpoints found that support image
  input`. **DeepSeek V3.2 is text-only.**
- Consequently the image judge **resolved 0 of 33 disagreements (0%)** vs the text judge's 72%. Every
  image disagreement that should have gone to the judge instead fell to `unresolved`.
- So a real share of image's under-coverage (12 gaps, 145 unresolved) is **this broken judge, not vision's
  reading ability** — fixing it (a vision-capable third-family judge) would likely recover ~⅔ of those 33
  judged reps by analogy to the text judge's 72% success. Tracked as **#82**; the fix belongs to the lab.
- Silver lining: the error handling worked exactly as designed — captured honestly, non-fatal per call,
  run completed, and a dead judge degraded *coverage*, not *accuracy* (image held 98.1%).
- **Preventable:** `councils.validate()` has no per-model *capability* check — it enforces cross-family
  diversity but not "an image council's members can all read images." A vision-capability catalog +
  validation guard would have caught this at config-load. (Candidate lab/hardening task.)

### 2c. Per-model cost + productivity profile (the Council Lab's real data)

Measured per call, both runs (`avg_in`/`avg_out` = native tokens; `$/call` from OpenRouter `usage.cost`):

| model | role | $/call | avg_in tok | avg_out tok | avg facts/call | errors |
|---|---|---:|---:|---:|---:|---:|
| `mistral-small-24b-2501` | text voter | **$0.00011** | 1493 | 450 | 14.0 | 0 |
| `gemini-2.5-flash-lite` | text voter | $0.00042 | 1490 | 676 | 15.5 | 1 |
| `qwen3-235b-2507` | text judge | $0.00054 | 1612 | 631 | 17.8 | 0 |
| `mistral-large-2512` | image voter | $0.00163 | 2608 | 271 | 7.0 | 0 |
| `gemini-2.5-flash` | image voter | $0.00178 | 3076 | 343 | 7.5 | 0 |
| `deepseek-v3.2` | image judge | — | 0 | 0 | 0 | 33 (dead) |

- **`mistral-small-24b` is the standout value voter** — cheapest by far ($0.00011, ~4× under flash-lite,
  ~15× under the image voters) at comparable productivity (14 facts/call). A strong anchor for cheap text councils.
- **Vision costs ~15× a text voter per call** for *fewer* facts — image input tokens dominate
  (2600-3100 in vs ~1490 for text), and the reads are sparser (7 facts/call vs 14-16). The cost gap is
  structural, not incidental: it's the whole reason to route digital→text.
- These are the first real token/cost rates from *clean pipeline* reps — they supersede the pre-pipeline
  `EXTRACTION_BENCHMARK_FINDINGS` numbers for cost purposes and seed the lab's token model (§3C).

---

## 3. Reader / rep-source yield (which representations actually pay off)

TEXT accepted-facts by source-file family (the reader that produced them):

| reader | reps | accepted | unresolved | acc/rep | read |
|---|---:|---:|---:|---:|---|
| `pdftotext -layout` | 48 | 320 | 32 | 6.7 | the workhorse — clean, low-noise, most reps |
| `camelot` (stream/hybrid) | 9 | **301** | 92 | **33.4** | **highest yield** on big hub *tables* (Orange, Washoe, Waterbury) — but the **noisiest** (most unresolved), OCR/table structure churns names |
| `tesseract_image` | 6 | 84 | 38 | 14.0 | OCR of *direct* image captures (Cleveland, San Diego) — solid |
| `pdfplumber` (lines) | 8 | 45 | 5 | 5.6 | cleanest ratio, low volume |
| `tesseract_raster` | 12 | 28 | 35 | **2.3** | **worst ratio** — OCR of a rasterized PDF page; garbled school names → unresolved. The reader of last resort. |

IMAGE was uniformly `raster_p` PNG → vision (478 accepted / 139 unresolved) + 3 native PNGs (8 accepted).

**Reader takeaways:** `pdftotext` earns its default status; `camelot` is worth keeping *for hub tables*
despite its noise (301 facts it alone recovered) — the noise is name-matching failures, not wrong times,
so it inflates *unresolved* not *error*; `tesseract_raster` (rasterized-PDF OCR) is the weakest reader and
a candidate to route *away from* toward vision when a page is genuinely image-bearing. This is direct
input for the Stage-6 routing/fidelity gate.

---

## 4. Failure-mode survey (what survived into extraction)

The value of GT scoring is the systematic map of *how* extraction fails. Ranked by what's actionable:

1. **Prompt-example leak (`"Fivay High"`) — a MODEL failure, FIXED (commit `4bc1d67`).** A judge reading a
   garbled table echoed the prompt's few-shot example school name at `confidence:high`, fabricating an
   accepted fact that pulled New Haven Unified's high band off GT. The example is now a bracketed
   placeholder + a parse-side leak guard. *Lesson: a realistic few-shot example name is unsafe — a model
   under-informed by garbled input falls back to it.*

2. **School "spray" — a PROMPT failure, real but NARROW (→ #81).** On a page that *names* many schools but
   carries *one* school's hours (Essex: the Westford homepage), both voters copied that one time across all
   named schools, fabricating a high-band row that passed cross-family consensus (shared-input false
   consensus — the New Haven CT lesson, induced by instruction-following not OCR). **Important nuance the
   data forced:** the naive "N schools share one exact time" signature is a **poor detector** — it is
   dominated by *legitimate uniform-district-hours*. Of 10 spray-suspect text reps, the big ones are all
   correct: Orange 104/104, Bridgeport 38/38, Fairbanks 26/26 schools **hit GT** at a shared time. The real
   fabrication (Essex) is *subtler* — a small cluster on a *single-school-focused* page — and the count
   signature didn't even flag it. So spray detection needs the **page-focus signal** (hub-lists-all-schools
   vs one-school-page), not a shared-time count. This sharpens #81's design.

3. **GT-derivation artifacts — NOT model failures (curation-side; Ian revisiting).**
   - **West Ada high** — the council read the main HS, the Academy, and the alternative program each
     *correctly* (per-school all HIT), but GT's `_derived_band_gross` **averaged in schools the human had
     marked `reject`** (419 confirmed + 360 rejected + 450 rejected → 410). The band "miss" is two
     *derivation* policies disagreeing; the confirmed-only value (419) is neither. → recompute GT band
     values over confirmed-only schools.
   - **New Haven Unified high** — GT's high band contains only the *continuation* school (354); the
     flagship comprehensive HS isn't in GT at all. Our 391/395 is a real school GT doesn't cover — a
     coverage gap in the yardstick, not our error. (The image run independently confirmed this by reading
     395 with *no* Fivay leak.)

4. **Confounder classes — real content, wrong schedule (defer + measure; kin of STAGE5 §3a).**
   Alternative/academy/specialty programs (West Ada), K-8 band-splitting (Cleveland files K-8 under
   elementary only → no middle band), and summer-school pages (STAGE5 obs. 4) are all *genuine* schedules
   that shouldn't feed the *comprehensive* band's mode. Our exposure is small-n only: at n≥3 schools the
   mode washes a single confounder out; misses occur where n falls to `mean_tiebreak` (West Ada high, n=2).

5. **School-name matching → `unresolved`, not error (working as intended).** Most of the 202 text / 145
   image unresolved are name-variance across models (OCR garble, `"w e s t v a l l e y"`, abbreviations)
   or genuinely different reads — correctly *held out* rather than wrong-counted. `tesseract_raster` and
   `camelot` produce the most (noisy readers). This is the consensus mechanism protecting accuracy at the
   cost of coverage — exactly its job, and the request loop (STAGE7 §4) is the intended recovery path.

6. **Output truncation — 1 case, now visible.** Baldwin's `camelot_stream` rep hit the (pre-fix) token
   ceiling once; caught by the `finish_reason:length` tripwire, `max_tokens` since raised to 16k. No silent
   tail-loss in either full run after the fix.

---

## 5. Cost

Total for both full runs: **$0.34** (text $0.065 + image $0.273) — 398 model calls over 47 districts-worth
of dispatch. Money is not the constraint (as the pipeline has held throughout); the constraints are
input quality, coverage, and human-QC time. The per-model rates in §2c are the real inputs for the
Council Lab's cost model (STAGE6 §3C) — notably that vision is a structural ~15×/call premium, which is
what makes format-routing (not blanket vision) the cost-correct design.

---

## 6. Recommendations → Council Lab backlog

Hypotheses to *test* (not adopt), in leverage order:

1. **Fix the image council's judge (#82)** — pick + validate a vision-capable third-family judge; measure
   the coverage recovered. Add a per-model vision-capability catalog + a `councils.validate()` guard so an
   image council can't ship with a text-only member again.
2. **Route by modality, measured (reader-routing at the dispatch layer).** Digital-text reps → text
   council; genuinely image-only/scan reps → vision. This run shows text dominates on native digital; the
   lab should quantify the crossover (which Stage-5 signals — `visual_text_gap`, `tesseract_raster`-only,
   `cms_hint` — predict "vision will beat text here").
3. **The spray prompt A/B (#81)** — but with the corrected detector: measure the **page-focus**-conditioned
   spray, not a shared-time count (which is mostly legit uniform hours). The anti-spray prompt rule must
   not suppress correct uniform-band extraction (Orange's 78 elementary schools).
4. **Judge quality is high-leverage** (47% escalation, 21% of facts). Worth testing cheaper/stronger judge
   candidates and whether a 3-voter panel beats pair+judge on this corpus.
5. **`mistral-small-24b` as a value anchor** — cheapest voter at full productivity; test it in more council
   seeds.
6. **De-weight/route-away-from `tesseract_raster`** (worst reader) — prefer vision when a page is genuinely
   image-bearing rather than OCR-ing a rasterized PDF.

Cross-cutting: several misses (West Ada, NHUSD) are **GT-derivation/coverage** issues, not model issues —
so the *yardstick* itself needs a confirmed-only re-derivation pass before the next accuracy comparison, or
those "misses" will keep penalizing correct extraction.

---

## 7. Provenance

Both runs 2026-07-03 against `handoff_a2bc80c004ca` (text) and `handoff_a2bc80c004ca-image` (vision probe).
Raw evidence: `data/acquisition/extractions/extraction_a2bc80c004ca*_*.json` (per-call model/facts/tokens/
cost/generation-id) + the `extraction`/`school_fact` governance tables. GT: `data/benchmark/
gt_curation_20260621T060008Z/gt_proposals.json`. Scoring: `stage7_extract/validate.py`. `batch_type ==
"benchmark"` — none of this is Stage-9-written or counted in enrichment stats.
