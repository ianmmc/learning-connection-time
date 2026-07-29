# #691 — hub-priority candidate-rule measurement over the labeled corpus

**Date:** 2026-07-29 · **Base:** `main` @ `789d097` · **Status:** measurement for a decision — no
behavior change shipped. Ian picks the rule; implementation follows as its own PR (#691 phase B).

## Question

`_hub_priority_holds` (REQ-116, `stage6_dispatch.py`) narrows a district's first dispatch to its
best-labeled hub and holds everything else, with no check that the winner carries schedule content.
#691's observed failure: Essex Westford dispatched a 21-in-window-time news feed and held a
112-time list, a 61-time bell table, and a 57-time bell-schedule Google Doc. Two candidate rules
were proposed; the issue required both be measured against the corpus before adoption.

- **Rule A** (issue option 2): hub-priority never holds a *labeled* target — narrowing suppresses
  only unlabeled tier-A auto-sends.
- **Rule B** (issue option 1, yield floor): narrowing stands, but a labeled sibling whose
  `n_times_in_window` ≥ *k* × the winner's also sends (grid *k* ∈ {2, 3, 5}).

## Method

Read-only replay of the live composer: `district_release_input` (production, `verified_only=False`
— the issue's own methodology) run over **every hub-labeled district**, with `_hub_priority_holds`
wrapped to capture the exact survivor set the live pass sees. Rules simulated offline from that
survivor set plus each record's `signals_json.n_times_in_window` (nitw). Script preserved beside
this report (`2026-07-29-issue691-measure.py`, run from the repo root with the governance DB up);
rerunnable in ~30 s.

## Corpus result

| | districts changed | sends added | vs. baseline 171 sends |
|---|---|---|---|
| **Rule A** | 23 / 23 narrowed | **+197** | **+115%** (more than doubles dispatch volume) |
| **Rule B, k=2** | 9 | **+26** | +15% |
| Rule B, k=3 | 7 | +15 | +9% |
| Rule B, k=5 | 5 | +8 | +5% |

42 hub-labeled districts; 23 narrow to exactly one send today (confirms the §14.7 audit count).

## The separation Rule B (k=2) produces

Every district Rule B touches has a **low-yield winner** (nitw 8–34); every district it leaves
alone has either a genuinely dense hub (nitw 75–196) or no labeled sibling at 2× the winner:

| district | winner nitw | held max nitw | Rule B k=2 adds | reading |
|---|---|---|---|---|
| Essex Westford `5000395` | **21** (news feed) | 112 | **+3** (112/61/57) | the #691 defect — recovered ✓ |
| Bentonville `0503060` | **8** | 52 | +3 (52/49/17) | 8-time page was "the only URL needed" — fixed |
| Broward `1200180` | **12** | 36 | +4 | sent back for thin sample (#686) — would have had 4 more labeled reps |
| Elmbrook `5501770` | 12 | 88 | +5 | same shape |
| Dickinson `3800038` | 29 | 77 | +3 | same shape |
| Columbia `2901000` | 24 | 134 | +4 | same shape |
| Urbana `1739960` | 19 | 70 | +2 | same shape |
| Franklin Co `1803700` | 10 | 59 | +1 | same shape |
| Las Cruces `3501500` | 34 | 72 | +1 | same shape |
| Bridgeport `0900450` | **196** (the honest hub) | 47 | 0 | untouched ✓ |
| Fairbanks `0200600` | **80** (real hub PDF, 2026) | 137 | 0 | untouched — §14.7 verified the held 137 covers schools already sampled (redundant) |
| Bangor `2302820` | 26 | 45 | 0 | still narrows to its genuine hub — the regression pin holds ✓ |
| Gallup, Santa Fe, Prince Edward, Einstein, Northwestern, … | 44–132 | ≤ their winner×2 | 0 | untouched |

## Acceptance-case check (from the issue)

- Essex composes a dispatch containing the 61-time `school_bell_table` AND the 57-time Google Doc:
  **Rule A ✓ · Rule B k=2 ✓ · k=3 ✗** (only the 112 clears 3×21).
- A genuine high-yield hub still narrows (Bangor): **Rule A ✗ — Bangor sends its 45-time sibling
  too (+1); Rule B ✓ at every k.**

## Reading

- **Rule A is doctrine-pure but expensive and indiscriminate.** It changes all 23 narrowed
  districts and adds +197 council sends — the cost lands hardest exactly where the human labeled
  most (Bridgeport +17, Elmbrook +19, Essex +38), including districts whose hub is demonstrably
  sufficient (Bridgeport 196, Fairbanks 80, Gallup 132). It also fails the issue's own Bangor
  regression pin: REQ-116's real case (one good hub, first dispatch cheap) stops existing wherever
  labels exist.
- **Rule B at k=2 is surgical.** +26 sends (13% of Rule A's cost) recover every observed failure —
  Essex, Bentonville, and (retroactively diagnostic) Broward's thin sample — while every
  genuinely-dense hub keeps its one-send first dispatch. The k=2 threshold produced a clean corpus
  separation (changed winners: nitw 8–34; untouched winners: 75–196); k=3 already loses Essex's
  61/57 evidence.
- Caveat: nitw is a text-capture signal. It correctly ranked Essex's image-only news feed low
  here, but a hub whose times live in an unresolved image will look low-yield and lose the
  narrowing it deserves — an over-send in the safe direction (extra labeled sends, never fewer).

**Recommendation: Rule B with k=2**, plus the gate@6 surfacing (both rules need it): "N labeled
targets held by hub-priority" as a server-computed console row, so the reviewer can see what one
label suppressed. Keep hold-never-reject semantics; the yield floor only moves labeled siblings
from `hold` back to `send`.

## Decision (to be filled by Ian)

- [ ] Rule: A / **B (k=2)** / B (other k) / other
- [ ] gate@6 surfacing: yes / defer

---
*Implementation notes for phase B, whichever rule wins: `n_times_in_window` is not on the sendable
dict today (`stage6_dispatch.py:213-220`) — add it from `signals` at sendable construction. Reuse
the #679 named-reason-constant hold pattern. Tests: Essex acceptance (fails today), Bangor
regression pin, deliberate revision of `tests/test_stage6_dispatch_bridge.py` expectations,
REQ-116 text update.*
