# Narrowed-dispatch audit: which written districts rest on evidence a selection rule withheld?

**Date:** 2026-07-29 · **Decision owner:** Ian · **Status:** decided (no re-review now) + audit specified
**Context:** #691 (`sev:critical`, epic #695); findings report §14.7 raised the question, this note answers it.

---

## 1. The question

#691 established that REQ-116 hub-priority narrows a district's first dispatch to a single labeled hub
**with no check that the winner carries any yield**, holding every other send. Measured across the
corpus: **23 of 42 hub-labeled districts are currently narrowed to exactly 1 send.**

Some of those districts have already been approved at gate@8 and written to `lct_db`. That raises a
question the campaign's falsifier does not cover — it says *fix the pipeline, not the district*, but is
silent on districts already published **through** a mechanism since found defective:

> When a defect is found that silently narrowed the evidence behind an already-published district, is
> re-composition and re-review warranted?

## 2. The decision (Ian, 2026-07-29)

**No re-review at this time.** Rationale, in Ian's framing: the districts were reviewed at gate@8, the
daily instructional minutes are trusted, and future information will bring the campaign back around to
them.

**Amendment adopted:** "we'll come back eventually" is an intention, not a mechanism. Nothing currently
detects that a written district rests on a narrowed dispatch — the district is in no queue, carries no
flag, and `district_grade_minutes` records nothing about held reps. Per REQ-165 (auditability: a claim
must be re-derivable from the record), the return trip is made **mechanical** by the audit in §5:
a query, not a re-review, runnable at any time and specified here so it survives this conversation.

## 3. What the challenge testing found — the decision is better supported than §14.7 implied

§14.7 framed the risk as *"the district was never given the chance to contradict itself."* Measured
against Fairbanks `0200600` (the flagship case, 13 held reps incl. one carrying 137 in-window times),
that framing **overstated the risk by reasoning from what was withheld rather than what was covered**:

| band | value | coverage | plurality | distinct values among sampled |
|---|---|---|---|---|
| elementary | 390 | **18/20 (90%)** | 0.889 | 300, 355, **390** |
| high | 390 | **4/5 (80%)** | 1.00 | 390 |
| middle | 390 | 4/12 (33%) | 1.00 | 390 |

Elementary and high are well-sampled, and elementary **did** contradict itself — three distinct gross
values appeared and 390 still won 16 of 18 schools. That is a mode that earned its place.

### The middle band, which looked like the one real weak spot, is not one

Middle showed 33% coverage (4 of 12 roster entries), and the three highest-yield held reps were
per-school bell schedules — so the live question was whether they covered unsampled middle schools.
They do not:

- Held reps: `ryn.k12northstar.org` (137), `tan…` (109), `rsm…` (82) → **Ryan, Tanana, Randy Smith**.
- Middle schools with accepted facts: **Ryan, Tanana, Randy Smith, North Pole**.
- The Stage-1 roster's `middle` band contains **exactly those four** schools.

**The held evidence is redundant, not missing** — the same four schools, read from a different page.
(The 12-vs-4 gap is a denominator artifact: `n_total=12` counts band *candidates* from Stage-1
selection, while the roster's true middle set is 4. Worth noting as a separate coverage-denominator
question, not a Fairbanks problem.)

**Conclusion for Fairbanks: no re-review warranted, and now positively verified rather than assumed.**

## 4. The residual challenges (recorded, not resolved by the above)

1. **"Reviewed at gate@8" describes the closing argument, not the evidence base.** A reviewer assesses
   facts extracted from the reps that were *sent*; evidence held at gate@6 never becomes a fact and
   cannot appear at gate@8. The console surfaced only a `hub-priority:first-dispatch-narrowed-to:…`
   reason string — not "13 records held, including a 137-time bell schedule." So gate@8 confidence is
   well-founded about what was extracted and is simply **silent** about what was withheld. (This is
   itself an argument for #691's fix to surface holds at gate@6 — see that issue's option 4.)
2. **Fairbanks is the best-covered case, not the typical one.** §5's audit shows written districts with
   16 and 19 held reps and max held yields of 134 and 88. Those have not been examined.
3. **Cheapness cuts both ways.** Re-composing a district costs ~$0.005. The real cost of re-review is
   not money but the precedent of re-opening published districts — which is exactly what the audit is
   designed to make a deliberate, evidence-triggered act rather than a reflex.

## 5. The audit (the mechanism replacing "eventually")

**What it answers:** which districts written to `lct_db` rest on a dispatch that hub-priority narrowed,
and how much yield was held back from each.

```python
import json
from sqlalchemy import text
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import stage6_dispatch as H6
from infrastructure.database.connection import session_scope as lct_scope

with lct_scope() as l:
    written = {r[0] for r in l.execute(text("SELECT DISTINCT district_id FROM district_grade_minutes"))}

with gdb.session_scope() as s:
    hub_districts = {r[0] for r in s.execute(text(
        "SELECT DISTINCT r.district_id FROM record r JOIN label l ON l.rec_key = r.rec_key "
        "WHERE l.primary_label IN ('district_hub_by_school','district_hub_by_band')"))}
    for did in sorted(written & hub_districts):
        out = H6.district_release_input(s, did)
        if not out:
            continue
        _, recs = out
        held = [x for x in recs if 'hub-priority' in (x['reason'] or '')]
        if not held:
            continue
        sigs = {r['rec_key']: json.loads(r['signals_json'] or '{}') for r in s.execute(text(
            "SELECT rec_key, signals_json FROM record WHERE district_id = :d"), {"d": did}).mappings()}
        mx = max((sigs.get(h['rec_key'], {}).get('n_times_in_window') or 0) for h in held)
        print(f"{did}: {len(held)} held, max in-window among held = {mx}")
```

### Baseline result, 2026-07-29 (`main` @ `6b62273`)

41 districts written · 22 also hub-labeled · **17 rest on a narrowed dispatch**:

| district | held reps | max in-window held | note |
|---|---|---|---|
| **2901000** | 16 | **134** | highest held yield among written |
| **0200600** Fairbanks | 13 | **137** | §3 — verified redundant |
| **5501770** | 19 | 88 | most held reps |
| 3800038 | 14 | 77 | |
| 3501500 Las Cruces | 16 | 72 | |
| 1739960 | 6 | 70 | |
| 2200283 | 1 | 64 | |
| 1803700 | 2 | 59 | |
| 3502370 | 9 | 55 | |
| 2302820 Bangor | 1 | 45 | |
| 5103060 | 13 | 36 | |
| 1730540 | 2 | 29 | |
| 1737350 | 4 | 10 | |
| 2506900 | 1 | 8 | |
| 2507080 | 1 | 5 | |
| 5510620 | 2 | 3 | |
| 3501110 | 6 | 90 | |

**Note the audit's own limitation:** `n_times_in_window` counts time-*shaped strings*, not verified
schedules, and a high count can be a calendar or a news feed (Essex Westford's narrowing winner had 21
and was a stale social-media feed). The audit **ranks candidates for inspection; it does not measure
error.** Only a re-composition settles whether a held rep would change a band — which is why the
decision above is "no re-review," not "no risk."

## 6. Re-run triggers

Run §5's audit and revisit this decision when any of these occurs:

- **#691 lands** — re-run to produce the definitive list under the fixed selection rule, and diff
  against the §5 baseline (districts that drop off were narrowed only by the defect).
- **A written district is contradicted** by later evidence (a follow-up batch, an SEA import, a
  correction), which is Ian's "future information" trigger made concrete.
- **A second selection-layer defect is found** — the pattern would then be a class, not an instance, and
  the argument for a systematic sweep strengthens.
- **Before any external publication** of LCT figures that includes these districts.

## 7. Why this note exists rather than a comment on #691

Per REQ-165 the *reasoning* behind a decision must be as recoverable as the decision itself. #691 will
close when the selection rule is fixed; this question — what to do about output already published
through the defect — outlives it and will recur with every future selection-layer fix. Recording it
here keeps the reasoning, the measurement, and the re-run mechanism together in one durable place.

*Authority: live governance DB + LCT DB reads on 2026-07-29 (`main` @ `6b62273`); Fairbanks closing
argument and `school_fact` rows; Stage-1 `schools_by_band_json` roster; #691's corpus-wide hub-priority
sweep; findings report §14.2 / §14.7.*
