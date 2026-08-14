# The 27 batch_00000 districts: production-acquisition journeys (traced 2026-08-14)

**Date:** 2026-08-14 · **Status:** promoted to the durable record by Ian (2026-08-14) from the
`docs/scratch-paper/` whiteboard where it was drafted · **Campaign:** #620 (epic #617)
**Products:** issues #714-#722, epics #723/#724, and the 9 Stage-9 incorporations of the same day.
**Snapshot caveat:** positions below are as of 2026-08-14 and go stale as the campaign moves —
gov_db + `district_grade_minutes` are the live truth; the *findings* are the durable part.

---

Scope: every district that entered `batch_00000` (the curated benchmark corpus) and is being
re-acquired through the PRODUCTION pipeline under the #620 campaign. Traced live from the
governance DB (`batch_district`, `record`/`label`, `handoff` receipts, `extraction`,
`school_fact`, `extraction_request`, `stage8_approval`) and the LCT DB (`district_grade_minutes`).
Benchmark-run artifacts (handoff `a2bc80c004ca`, 2026-07-03) are excluded from all production
counts below — they are walled off by design.

Issues filed from this trace: **#714 #715 #716 #717 #718** (all → epic #706), plus a second-instance
comment on #709. Earlier trace (dispatch `3004896917ca`, five districts) filed #707–#713.

## Position summary — 27 districts

| Position | N | Districts |
|---|---|---|
| **Written** (gate@8 approved + Stage 9 rows in LCT DB) | 3 | Fairbanks `0200600`, Bangor `2302820`, Worcester `2513230` |
| **Approved, unwritten** (#682: approve→write unwired) | 9 | Bridgeport `0900450` (07-29!), Mat-Su `0200510`, Memphis `4700148` (both 08-04), Mesa `0404970`, Bentonville `0503060`, Springdale `0512660`, San Diego `0634320`, Waterbury `0904830`, Appoquinimink `1000080` (all 08-14) |
| **Sent back** (#689: send-back routes nothing) | 3 | Broward `1200180`, Cleveland `3904378`, Essex Westford `5000395` (all 07-29) |
| **Mid-loop** (extracted; follow-ups active) | 9 | Mobile `0102370`, Little Rock `0509000`, New Haven Unified `0626910`, New Haven CT `0902790`, Orange `1201440`, Cedar Rapids `1906540`, Lewiston `2307320`, Washoe `3200480`, Sweetwater `5605302` |
| **Unreachable by the loop** (#718) | 3 | Baldwin `0100270`, Joint SD No.2 `1602100`, Lincoln `3172840` |

## Per-district journeys

Format: production dispatches → production extraction (accepted/unresolved distinct band:school
pairs) → directive state → gate@8 → Stage 9. "targets" = A/B-tier labeled target records
(including gt:// where noted).

### Written — the full path has been walked 3 times

- **Fairbanks `0200600`** — hub narrowed to 1 rep; 07-29 run: 26 accepted → approved 07-29 →
  **13 grade rows written 07-29**. Then re-dispatched 08-04 (`3004896917ca`) and fully
  re-extracted (26 accepted again; fact rows doubled): the already-approved-and-written district
  had no re-dispatch guard (#717) and its fresh facts have no delivery path (#713).
- **Bangor `2302820`** — 1 rep, 3 accepted → approved 07-29 → **written 07-29**. The genuine-hub
  narrowing regression pin of #691.
- **Worcester `2513230`** — 26 reps, 16 school-pairs accepted → approved 07-28 → **written 07-28**.
  Cleanest large-district run of the campaign.

### Approved, unwritten — the #682 backlog (9 districts, oldest 07-29)

- **Bridgeport `0900450`** — 1 hub rep → **38 schools accepted** (best yield/rep of the campaign);
  approved 07-29. **Approved 16 days without incorporation.** Its 10 held per-school pages are
  #691-audit territory.
- **Mat-Su `0200510`** — 40 reps, 32 school-pairs; approved 08-04.
- **Memphis `4700148`** — 2 reps; 42 accepted / **112 unresolved** (the #712 recall asymmetry:
  gemini 153 facts vs mistral 37 on the long table; among the 36 schools both voters read,
  end-times are 36/36 exact-equal — clean of #716's signature). One voter 400 (#709). Approved 08-04.
- **Mesa `0404970`** — 128 sendables dispatched 08-06; extraction stopped at 24 reps via the #120
  mode-stability early-exit (104 skipped `mode_stable`, all three bands stable — **working as
  designed, not a defect**); 14 school-pairs accepted; approved 08-14.
- **Bentonville `0503060`** — 1 rep (post-#684 the staff-day handbook no longer auto-sends);
  4 accepted; approved 08-14.
- **Springdale `0512660`** — 7 reps, 7 accepted; approved 08-14.
- **San Diego `0634320`** — the 08-14 morning dispatch's anchor: 50 reps, 46 school-pairs
  accepted; approved same day.
- **Waterbury `0904830`** — 1 hub rep → 37 schools accepted; approved 08-14.
- **Appoquinimink `1000080`** — 1 hub rep → 16 schools; approved 08-14.

### Sent back — waiting on the hand-executed requeue (#689)

- **Broward `1200180`** — 6 schools from 1 rep; sent back 07-29 ("massive district, thin sample");
  #686 tracks its data-app source. **No dispatch since.**
- **Cleveland `3904378`** — 7 accepted; sent back 07-29 (thin coverage + #693 duplicate entities,
  flagged in #674). Its post-#694 middle-band 7→2 is `approved` and lands in the next compose
  (batch_00043 per the live dry-run).
- **Essex Westford `5000395`** — 8 accepted; sent back 07-29 (#691 hub-priority suppression).
  **No dispatch since** — the #691 composition fix has never been exercised on the district whose
  case drove it. Needs a re-dispatch to benefit.

### Mid-loop — the request-more-evidence machinery at work

- **Mobile `0102370`** — dispatched 08-06 (9 reps, 7 accepted) then **re-dispatched 08-14 with the
  same 9 reps and fully re-extracted** (8 accepted; fact rows near-doubled) — the #717 headline
  case. A third dispatch (`96edcbf7141c`, 3 reps incl. the 08-09-labeled bell PDF) went out 08-14
  17:20, extraction pending. 3 pending 7→2s.
- **Little Rock `0509000`** — 3 accepted 08-04; the ladder then burned two 7→6 rungs on a 429
  (#711) and a nameless document (#710). `batch_00037` (12-school rediscovery) is now **approved**
  — worth pausing before its Stage-2 spend: #707 argues the target fact (`07:40–14:55`) is already
  in `school_fact`, refused only by the degenerate-name guard. One 7→2 `approved` awaiting the
  next compose; one 7→6 pending (depth-dead zombie, reject-only).
- **New Haven Unified `0626910`** — 1 rep, 3 accepted / 3 unresolved; both 7→2s executed →
  **batch_00039** (approved 08-14). Its 1 unsent target is the gt:// rep — correctly held.
- **New Haven CT `0902790`** — 6 reps, 5 school-pairs, zero unresolved; 7→2s → **batch_00041**.
- **Orange `1201440`** — the #714 case: hub narrowed to a 1,020-time bell-table PDF; both voters
  failed on size (gemini at-ceiling truncation with zero salvage; mistral total-context 400 —
  second #709 instance) → clean-looking zero. Stage 7 recovered: 7→6 retry (`pdftotext.txt`,
  n_times=691, sized ~24k — fits) executed 08-14 as `5d756fa57a52`, **extraction pending**;
  3 per-band 7→2s pending review.
- **Cedar Rapids `1906540`** — 4 reps, 2 accepted; 7→2s ×3 executed → **batch_00042**; second
  dispatch (`3c0d98cb9117`, 2 reps) 08-14 15:39, extraction pending.
- **Lewiston `2307320`** — 1 accepted / 8 unresolved across 3 runs (roster N=1 refusals — #707's
  second arm); two 7→2s `approved` 08-14 but invisible to the console's compose button (**#715:
  count district-wide, sweep run-scoped**) — the unscoped compose plans them into batch_00043.
  One depth-dead 7→6 pending (reject-only).
- **Washoe `3200480`** — the #716 case: voters agreed on ~104 schools; ambiguous 12-hour
  afternoon end-times parsed as AM minted 67 false disagreements; only the judge's 39 re-emissions
  survived. **Re-aggregation after the #716 fix should recover ~100+ schools from the existing
  receipt with zero model spend.** 7→2 → **batch_00040** — arguably unnecessary spend if
  re-aggregation lands first.
- **Sweetwater `5605302`** — 5 reps, 7 school-pairs; 7→2 → **batch_00038**.

### Unreachable — the #718 hole

- **Baldwin `0100270`** — 12 A-tier targets, **all `gt://` curation artifacts**; production
  discovery yielded no A/B target; excluded (by hand) from draft_00005; zero production runs, so
  the Stage-7 loop can never fire. Sat 19 days reading as "clean" in every target count —
  including my own 08-14 dispatch-gap sweep, which this trace corrects.
- **Joint SD No.2 `1602100` / Lincoln `3172840`** — the #646 pair: one gt:// record each, zero
  `discovery_school` rows; #567 recovered their `website_url`s but discovery has never run.
  Same hole, more extreme.

## Defect roll-up from the full campaign (both traces)

| # | Finding | Status |
|---|---|---|
| #707 | degenerate-name guard refuses resolvable consensus (Little Rock, Lewiston) | open; batch_00037 spend hinges on it |
| #708 | OCR name-mangling ships fidelity-clean | open |
| #709 | context-ceiling 400 silently degrades council | open; 2nd instance (Orange) commented |
| #710 | nameless document defeats the rep ladder | open |
| #711 | transient 429 recorded as clean zero-yield | open |
| #712 | long-table recall asymmetry (Memphis 153 vs 37) | open (Council Lab #80) |
| #713 | no re-review path for written district w/ new facts (Fairbanks) | open (epic #92) |
| #714 | no per-model context accounting; mega-roster has no chunking path (Orange) | **new** |
| #715 | compose button counts district-wide, sweeps run-scoped (Lewiston) | **new** |
| #716 | ambiguous 12h afternoon times parse as AM → false disagreement (Washoe, −67 schools) | **new** |
| #717 | no already-extracted delta at gate@6 (Mobile, Fairbanks re-buys) | **new** |
| #718 | gt://-only district reads ready + unreachable by loop (Baldwin, #646 pair) | **new** |
| #719 | **geo escalation rung blanks the domain → #229 refuses 100%; 6 batches, 70 schools, 0 resolved** | **new, sev:critical** |

Verified NOT defects: Mesa's 104 "missing" reps (#120 mode-stability early-exit, by design);
Memphis's unresolved flood is #712, clean of the #716 time signature.

## Pending operational state (no code needed, in priority order)

1. ~~9 approved districts await Stage-9 incorporation~~ **DONE 2026-08-14 (later same day):**
   all 9 dry-ran clean, incorporated, and verified in `district_grade_minutes` (117 grade rows;
   12 of the 27 now written).
2. **Next compose sweeps Lewiston + Cleveland + Little Rock** (batch_00043 plan verified live) —
   use the unscoped path until #715 lands.
3. **Little Rock batch_00037 is approved but arguably moot** (#707) — decide before Stage 2 runs.
4. **Washoe: hold batch_00040's spend** until #716's re-aggregation-from-receipt is assessed.
5. **Essex + Broward** still need their send-back re-dispatches (#689 manual routing).
6. **Orange + Mobile + Cedar Rapids** have extractions pending on today's dispatches.
7. **Baldwin + the #646 pair** need a discovery route that #718 defines.
