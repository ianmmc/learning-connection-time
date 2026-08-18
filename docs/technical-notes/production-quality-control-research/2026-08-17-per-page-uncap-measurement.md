# Removing the 60-page per-page scan cap — Pass A measurement

**Date:** 2026-08-17 · **Script:** `2026-08-17-per-page-uncap-measure.py` (rerunnable, read-only)
**Verdict: PASS.**

## What was wrong

`compute_signals` built the per-page `pages` signal with one `pdftotext` subprocess *per page*,
capped at `HANDBOOK_MAX_PAGES = 60`. Pages past 60 got no entry at all, so they were invisible to
every downstream consumer — `harvest_pages`, `is_handbook`, `lf_no_times`, tier, `decide()`.

The cap had already been raised once (15 → 60) for exactly this class of miss. Raising it again
would only move the boundary, so it is gone: `pdf_page_texts()` reads the whole document in a single
`pdftotext -layout` call split on form feed, and a guard test asserts the constant stays deleted.

## Results

| check | result |
|---|---|
| **A1** per-page `n_times` vs stored, pages ≤ 60 | **0 mismatches / 22,146 pages** |
| **A2** capped docs | **56**; +223 → thousands of pages recovered; harvest_pages shrank on **1** |
| **A3** `is_handbook` delta | **0**, proven analytically + asserted per doc |
| **A4** `lf_no_times` newly suppressed | **0** (and **10 recovered**) |
| **A5** speed | **2.2× faster** while reading strictly more; peak RSS 112 MB |

**A1 is the load-bearing result.** Exact agreement on every page below the old cap means the
non-capped corpus — 3,476 of 3,532 records — is unchanged *by construction*, so only the 56 capped
docs needed downstream analysis. (The earlier 10/10 spot check normalized whitespace, which is not
proof for `TIME_RE`, whose `\s*` bridges the AM/PM gap. This is the proof.)

### What was hiding past page 60

| record | pages | times | harvest_pages |
|---|---|---|---|
| `4700148:00f553bcfc` | 60 → 319 | **3 → 838** | `[]` → `[89, 90, 91]` |
| `1730540:bcd9c539fb` | 60 → 886 | 250 → 3,211 | `[3]` → 17 pages |
| `4700148:8d0058ac10` | 60 → 154 | 831 → 942 | 11 → 11 |
| `0904830:05d6aab8ae` | 60 → 249 | 1 → 92 | `[]` → `[196, 197]` |

**10 records were being suppressed by `lf_no_times` purely because their times lived past the cap.**
Memphis `00f553bcfc` is the extreme case: it read as a 3-time document; its bell schedule is on
pages 89-91. Largest document in the corpus is 1,017 pages.

Note `1730540:bcd9c539fb` (Northwestern CUSD 2) recovers 3,211 times in a **3-school, 320-student**
district — that is a 886-page Board Policy Book, and the recovery is *noise*, not schools. It is the
scope-error case tracked separately; uncapping makes it more visible, not more correct.

### The one harvest_pages shrink

`0602095:6e8db3e114` went `hp 2 → 1`. Expected and benign: `harvest_schedule_pages` cuts at
`max(6, peak × 0.5)`, so a larger peak discovered past page 60 *raises* the bar and can drop a page
that previously cleared it. This is a property of the relative selector, not of the uncapping —
and it is exactly the behaviour the PR 2 absolute floor exists to stop relying on.

### Direction matters (a flaw caught in the measurement itself)

The first version of A4 counted arming *flips* without checking direction, and reported
"REVIEW REQUIRED" for what turned out to be 10 clean recoveries. A flip count alone reads a mass
recovery as identically alarming to a mass suppression. The script now separates:

- `armed → disarmed` (**10**): times found past the cap; `lf_no_times` stops suppressing. The fix working.
- `disarmed → armed` (**0**): the only way this change could drop a district. Any occurrence blocks the merge.

## Follow-on

`page_time_signals()` now also records `instr` per page (`instructional_declaration()`) — the
colon-free `explicit_instructional_time` class a clock-time count cannot see. Two capped docs carry
such a page with zero times (`4700148:00f553bcfc` p39, `0602095:6e8db3e114` p67). PR 2's absolute
page floor consumes this field; it is computed here because the page text is already in hand.

**A re-ingest is required** for the 56 capped docs to pick up the corrected signal.
