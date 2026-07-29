# #694 — Stage-7 slot-grain follow-up detection: the measured corpus delta

**Date:** 2026-07-29 · **Script:** `2026-07-29-issue694-slot-grain-measure.py` (read-only replay;
rerunnable) · **Branch:** `fix/694-stage7-slot-grain-followup`

## What was measured

For every district with ≥1 production accepted fact (64 districts), the REAL detector inputs were
assembled via `stage7_run._district_request_inputs` and the pure detector ran twice: with
`slot_gaps=None` (the pre-#694 per-band boolean) and with the #694 slot-gap summary (the gate@8
projection compressed by `requests.slot_gap_summary`). The diff below is district-altitude
directives only; nothing was persisted.

## Headline

| | |
|---|---|
| Districts with production facts | **64** |
| Districts gaining ≥1 new district-altitude directive | **36** |
| New directives (bands the boolean called "done") | **58** |
| Pool schools named to pursue | **196** |
| Span-only mode-check targets (#696 class, ≤2/band) | **12** |
| Districts with no slot view (boolean fallback) | **0** |
| Est. Stage-2 spend if every named school gets one targeted query | **$0.21–$0.31** |

The spend estimate uses the documented Stage-2 basis (~$0.001–0.0015/query,
`ACQUISITION_PIPELINE.md` §Stage-2 cost reframe). Downstream capture/extraction is the larger
cost and remains fronted by gate@7 manual approval — every one of these directives is a
recommendation, not an auto-spend.

## The acceptance cases (issue #694 / #692)

- **Cleveland `3904378` middle** — boolean: silent (band "covered"). Slot grain: **0/65 roster
  slots filled → pursue the 12 Stage-1 pool schools + 2 span-only mode-checks**, named in
  `params.unfilled_schools` / `params.mode_check_schools`. Elementary likewise (0/64 → 12+2).
  (The issue's table said 1/12 and 2/64 "with facts" — those facts exist and make the bands
  *covered*, but none name-matches a roster slot, so slot-grain honestly reads them as unheard
  slots plus extras awaiting disposition.)
- **Essex Westford `5000395` middle** — boolean: silent. Slot grain: 0/3 → pursue 2 + 1
  mode-check; high 0/1 → pursue 1.
- **Fairbanks `0200600`** — raises **nothing** (every band satisfied via REQ-149 plurality),
  the regression pin.

## Finding worth review: the extra-only band class

Several of the 58 are 1-school districts (charters: Avalon, KIPP Freedom, Mastery Pastorius,
Brownsville Ascend…) whose single band fact is an **unmatched extra** — evidence exists but
name-matches no roster slot, so the slot reads unheard and the band can never reach REQ-149
satisfied (n=1 < min_sampled). These will keep one open directive each until a human disposes the
extra (assign → slot fills → auto-withdraw #233; reject → slot excluded from targets). That is the
designed human path, but it is new gate@7 load: **29 of the 58 directives are single-slot bands
of exactly this shape** (`filled 0/1, pursue 1` on a band that already holds a fact).
If it proves noisy, the tunable is a summary-level rule ("a band whose every roster slot has a
same-named extra candidate is pending-disposition, not unheard") — deliberately NOT built now
(no measurement says it's needed, and it would hide real gaps behind fuzzy name matching).

## Guard status

- **#175 phantom / #176 barren-rep / Las Cruces partial / #147 depth** — all pre-existing pins in
  `tests/test_stage7_requests.py` pass unchanged (the boolean path is byte-identical when
  `slot_gaps` is None). Slot grain deliberately WIDENS the barren-rep window: a
  covered-but-unsatisfied band keeps its 7→6/7→3 remedies (re-reading reps in hand is the cheap
  evidence a thin band needs; the 7→2 defers behind them, #159).
- **Withdraw (#233) aligned:** `withdraw_satisfied_requests` now reads the SAME `band_done`
  predicate — without this, every covered-but-unsatisfied directive above would churn
  (emit → withdraw → re-emit) each round.
- **Zero-slot bands are omitted, not "done"** — a facts-only projection band (no CCD roster)
  falls back to the covered boolean (the #702 empty-pool lesson, pinned in
  `test_694_slot_grain_requests.py`).
