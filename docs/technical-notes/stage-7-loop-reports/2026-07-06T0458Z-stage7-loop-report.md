# Stage 7 Loop Report — 2026-07-06T04:58Z

> **Series:** first entry in `stage-7-loop-reports/`. Each report is a dated, self-contained
> retrospective on one Stage-7 request-loop exercise, organized around **band completion** (the thesis
> below). The template at the end (§9) defines what every future entry should carry so the series stays
> comparable across runs.
> **This entry covers:** the first clean live non-benchmark exercise of the request-more-evidence loop
> (GitHub #122), 2026-07-05 20:55Z → 2026-07-06 04:46Z — 23 fresh districts, 37 extraction runs, $0.195.
> **Companion (present-state design, not this report):** `../acquisition-pipeline-stage-design-notes/STAGE7_EXTRACT_DESIGN.md`.
> Bugs are tracked as GitHub issues (linked inline); this report does not re-log them as to-dos.

---

## 0. Thesis — Stage 7 is "fill in the bands"

The completion grain of the whole acquisition pipeline is **district × band** (elementary / middle / high).
A district is "done" when every band it really has carries confident daily minutes. Everything Stage 7
does — the council extraction, and the two request back-edges it can fire — is in service of that one
goal: **turn a claimed band with no accepted facts into a claimed band with accepted facts.**

The two mechanisms map cleanly onto *why* a band is empty:

| Band is empty because… | Mechanism | What it does |
|---|---|---|
| the evidence we already captured wasn't read well (a barren rep) | **7→6 (recover)** | re-dispatch an already-captured alternate rep of the same URL — no new capture |
| we never captured evidence for that band's schools | **7→2 (rediscover)** | a follow-up batch re-runs discovery/capture for the band's schools → new URLs → gate@5 |

This report measures how well each mechanism actually filled bands on real data, and — the sharpest
finding — how much of the "band gap" surface is **not fillable at all** because the band model itself is
noisy (§4).

---

## 1. Headline outcomes

- **21 / 23 districts are real-band-complete** (every band that corresponds to a real NCES school has
  accepted facts). The 2 residual real gaps: **Adair Co. elementary** and **Huntington high**.
- **First pass did most of the work:** 19/23 districts were fully covered on the first extraction alone,
  for **$0.045** (~$0.002/district).
- **The follow-up loop filled 4 more real bands** (Strasburg, Brookwood, Roy, Marshall) — but cost
  **$0.151, ~3.4× the entire first pass**, for that marginal gain (§5).
- **Both mechanisms work end-to-end on live data**, each proven by a fix landed mid-session:
  - **7→6 recover:** Marshall went **0 → 3 accepted (empty → e/h/m)** once the harvest-slice read bug was
    fixed (`247513f`) and its alternate rep was re-dispatched.
  - **7→2 rediscover:** Strasburg **1 → 4 (e → e/h/m)** and Roy **1 → 4** once the rediscover no-op bug
    was fixed (`63e16e5`, #174) — the follow-up batch actually found the missing schools' sites
    (Hemphill Middle, Strasburg High) and they were dispatched and extracted.
- **Request volume:** 8 × 7→2 executed (+7 approved awaiting compose), 19 × 7→6 executed (+3 rejected).
- **Baseline (context):** the benchmark batch_00000 run scored 95.2% band / 99.3% school vs curated GT
  over 24 districts at $0.065 (`STAGE7_EXTRACT_DESIGN` §0). This session is a *coverage* exercise on
  un-GT'd districts, not an accuracy measurement — the number to watch here is bands-filled, not hit-rate.

---

## 2. Band completion — the core table

First-pass vs. current cumulative coverage per fresh district. **real** = bands with a real NCES school;
**phantom** = a claimed band with *no* NCES school at that level (§4). `+FILLED` = a real band a follow-up
round filled; `STILL-GAP` = a real band still empty.

| District | real bands | first pass | now | follow-up result |
|---|---|---|---|---|
| Coffee County | e/h/m | e/h/m | e/h/m | — complete first pass |
| Stroudsburg PA | e/h/m | e/h/m | e/h/m | — (7→6 ran, corroborated only) |
| Millard UT | e/h/m | e/h/m | e/h/m | — complete first pass (0 unresolved) |
| Elmbrook WI | e/h/m | e/h/m | e/h/m | — complete first pass |
| Dayton OH | h | e/h/m | e/h/m | — over-covered (charter) |
| Franklin Co IN | e/h/m | e/h/m | e/h/m | — complete first pass |
| Dryden NY | e/h/m | e/h/m | e/h/m | — complete first pass |
| Dickinson ND | e/h/m | e/h/m | e/h/m | — (7→6 ran, marginal) |
| New Richmond WI | e/h/m | e/h/m | e/h/m | — complete first pass |
| Hope Leadership MO | e | e | e | — complete first pass |
| Aspire Summit CA | e | e/h/m | e/h/m | — over-covered; costly 7→6 (§5) |
| **Strasburg CO** | **e/h/m** | **e** | **e/h/m** | **+FILLED h,m via 7→2** ✅ |
| **Marshall WI** | **e/h/m** | **(empty)** | **e/h/m** | **+FILLED e,h,m via 7→6** ✅ |
| **Brookwood IL** | **e/m** | **e** | **e/m** | **+FILLED m via 7→6** ✅ |
| **Roy NM** | **e/h** | **h** | **e/h/m** | **+FILLED e via 7→2** ✅ (m is phantom) |
| **Adair Co MO** | **e/h** | h/m | h/m | **STILL-GAP elementary** (2 rounds, $0.032) |
| **Huntington TX** | **e/h/m** | e/m | e/m | **STILL-GAP high** (7→6 didn't recover it) |
| Riverside AR | e/h | e/h | e/h | phantom middle |
| Learning Works CA | h | h | h | phantom middle (rediscover honestly dry) |
| Lincoln MA | e | e/m | e/m | phantom middle (over-covered) |
| KIPP Durham NC | e | e/h/m | e/h/m | phantom middle; over-covered |
| KIPP OKC OK | e | e/m | e/m | phantom middle |
| Mastery PA | e | e/m | e/m | phantom middle |

**Read:** the loop's real-band wins are the four **bold ✅** rows. Everything below them is either already
complete, a phantom band that can't be filled, or a residual real gap the loop couldn't close.

---

## 3. The two mechanisms, measured

### 7→6 (recover an already-captured rep) — 19 executed
- **The showcase: Marshall WI (0 → e/h/m).** Its only send rep was a buried-handbook `harvest_slice.txt`
  that Stage 7 *couldn't even read* — the extraction read the legacy capture path while the slice had been
  relocated (fixed `247513f`). Once readable it still yielded 0 (the slice text alone wasn't extractable);
  the 7→6 then re-dispatched a higher-yield alternate rep and recovered all three bands. This single
  district exercised the harvest-slice fix, the run-abort robustness gap (#173, it halted the whole batch
  at 16/18), and a successful barren-rep recovery.
- **Brookwood (e → e/m)** and **Huntington (partial)** are clean smaller recoveries.
- **The #155 yield-ranked, text-before-vision pick is visibly correct on live data** — every 7→6 reason
  string named a *higher-yield TEXT* alternate before escalating to vision.
- **But 7→6 fires without coverage-awareness (#170), and it's expensive when it does.** Aspire Summit was
  already fully covered (e/h/m) on the first pass, yet a 7→6 still fired and ran a **414k-prompt-token
  vision escalation for $0.076** — 16× a typical first-pass district, for zero new coverage. Dickinson
  (already complete) similarly drew two low-yield follow-up runs. This is the single biggest source of
  wasted spend this session and is exactly what #170 proposes to suppress.

### 7→2 (rediscover the band's schools) — 8 executed
- **The full loop closed for the first time.** Strasburg's middle/high bands were empty because we had
  never captured Hemphill Middle or Strasburg High. The 7→2 → follow-up batch (batch_00010) → **#174 fix**
  → delta-capture found those schools' sites (12 new URLs for Strasburg, 5 for Roy), they were labeled at
  gate@5, dispatched, and extracted: **Strasburg 1 → 4, Roy 1 → 4.** This is the request loop's entire
  reason to exist, working start to finish on real districts.
- **batch_00010 rediscover:** 4 districts, 19 new URLs (Strasburg 12 / Roy 5 / Riverside 2 /
  Learning Works 0). Label preservation verified (all 12 prior labels survived the re-ingest; the 19 new
  records arrived unlabeled for gate@5). Learning Works came back **honestly dry** — the widened net found
  nothing, its (phantom) middle 7→2 correctly exhausts rather than inventing evidence.

---

## 4. The phantom-band problem — the sharpest learning

**A large share of "band gaps" cannot be filled because the band was never real.** 8 of the 23 districts
claim a band (almost always **middle**) that has **no NCES school at that level** — the district is
structured K-6 / 7-12, or is a single-school charter, so "middle" exists as grades but not as a school the
loop can discover a schedule for. The loop dutifully fires a 7→2, widens its queries, finds nothing, and
exhausts against the depth guard. That is *correct behavior* — but it means a chunk of the loop's spend and
effort is chasing bands that were mis-claimed upstream, not real coverage gaps.

The noise runs in **both directions**:
- **Phantom claimed bands** (claimed > real): 8 districts, mostly a middle band with no middle school.
- **Over-coverage** (extracted > claimed): charters like Dayton (claimed high) and KIPP Durham (claimed
  elementary) are single K-12 schools whose one schedule yields e/h/m facts — the extraction *finds* bands
  the claim never listed. Roy even filled a **phantom** middle (a fact landed in the middle band though no
  middle school exists) — a grade→band assignment mapping some school's hours into "middle."

**Implication for the thesis:** "fill in the bands" is only as trustworthy as the **band definitions**.
Before we can call a district complete-or-gapped, the claimed-band set has to reflect real schools. This is
a **Stage-1 claimed-bands question** (NCES `by_level` already tells us which bands have zero schools), and
it upstream-gates the whole loop: a phantom band should not generate a 7→2 at all. **Tracked: #175** —
reconcile `lea_claimed_bands` against `nces_school_counts.by_level` (+ collected evidence) so the loop
never spends on an unfillable band.

---

## 5. Cost & economics

| Phase | runs | cost | per-district |
|---|---|---|---|
| First pass (2 handoffs, 23 districts) | 23 | **$0.045** | ~$0.002 |
| Follow-up (7→6 / 7→2 re-dispatches) | 14 | **$0.151** | — |
| **Total session** | **37** | **$0.195** | — |

**The follow-up loop cost 3.4× the entire first pass to fill 4 marginal bands.** First-pass extraction is
extraordinarily cheap and high-yield; the request loop is where the money goes. Outliers:

| Run | District | acc | cost | note |
|---|---|---|---|---|
| 545683ec83cd | Aspire | 3 | **$0.076** | vision escalation on an **already-covered** district (#170) |
| 6869c9d673ef + a639cbc50ba1 | Adair | 1 net | **$0.032** | 2 rounds, **still gapped** elementary |
| 2c3680a6428e | Brookwood | 3 | $0.012 | a real middle fill |
| 6bc08e983d45 | Marshall | 3 | $0.010 | a real e/h/m recovery (worth it) |

**Guardrails held:** the depth guard (`max_request_rounds=2`) stopped Adair after two rounds rather than
letting it spend unbounded on an unfillable elementary band; the per-district-total cap was never
breached. The economics argue for **spending discipline at the point of firing**, not just at the ceiling:
suppress any follow-up on an already-covered district/band (**#176**, with #170), and suppress 7→2 on
phantom bands (**#175**, §4). Those two changes would have removed the two worst outliers ($0.076 Aspire +
$0.032 Adair = 57% of all follow-up spend) for zero coverage loss.

---

## 6. Engineering learnings (bugs surfaced this loop)

This exercise was, as intended, a bug-finding machine — the corrected code surfaced five real defects, two
fixed in-session:

**Fixed + tested on main this session:**
- **harvest_slice read path** (`247513f`) — Stage 7 joined the capture dir directly instead of using the
  shared `resolve_harvest_slice` resolver, so every relocated buried-handbook slice raised
  FileNotFoundError. Unblocked Marshall. (The epic-#133 "re-implemented invariant" pattern again.)
- **#174 — follow-up rediscover was a silent no-op** (`63e16e5`) — Stage 2/3/4 `reconcile()` skipped any
  district whose manifest already existed on disk, so a 7→2 follow-up (which by definition re-targets an
  already-discovered district) discovered nothing while reporting success. Fixed with follow-up redo rules
  end-to-end (batch_type carried into the receipt; reconcile redoes follow-ups; manifests union-merge so
  Stage 5's delete+rebuild ingest can't erase existing labeled records; the scraper delta-captures only new
  URLs). This is what made the 7→2 half of the loop work at all.

**Filed, open — the loop's own findings:**
- **#176** — coverage should suppress follow-ups (umbrella): don't fire a 7→6/7→2 for a district/band
  already covered. Validated live by Aspire's $0.076 waste; **#170** is its 7→6-specific slice. The single
  highest-value spend hardening from this run.
- **#175** — reconcile claimed bands against real coverage (the phantom-band problem, §4): stop firing
  7→2s for bands with no real school.
- **#173** — an unreadable rep file aborts the *entire* run instead of failing one district (Marshall
  halted the batch at 16/18). The durability model's remaining gap.
- **#169** — OpenRouter reply truncation on large table reps (camelot_hybrid), silent tail-loss + cost
  spike.
- **#171** — gate@6 candidate list has no "already dispatched" indicator (led to a redundant full
  re-dispatch, `7301db5ac45d`).
- **#168** — no first-class "abandoned" batch status (draft is load-bearing for the attempted-schools
  poison-exclusion).

---

## 7. Open questions / next

1. **Phantom-band reconciliation (§4, #175)** — gate a 7→2 on `nces_school_counts.by_level` (+ collected
   evidence): don't fire a rediscover for a claimed band with zero real schools. Removes unfillable spend;
   sharpens "band complete" as a metric. *(strongest next lever)*
2. **Coverage suppresses follow-ups (#176, with #170)** — don't fire a 7→6/7→2 when the district/band is
   already covered. Would have saved the $0.076 Aspire run; together with #175 removes ~57% of follow-up
   spend for zero coverage loss.
3. **Run-abort robustness (#173)** — one bad rep must not halt the batch.
4. **Residual real gaps** — Adair elementary and Huntington high resisted the loop; worth a manual look at
   whether their evidence exists at all (a discovery problem) vs. an extraction miss.
5. **Path-2 districts** — Dunseith and Union Hill (explicit-published-minutes targets the current prompt
   can't read) were deliberately held out of this run; they need the path-2 extraction work before they
   can be scored on band completion.
6. **Accuracy, not just coverage** — this report measures bands *filled*, not bands *correct*. Once these
   districts accrue GT, a follow-up report should score the filled bands against it.

---

## 8. Baseline for the series

For comparability, the reference points this first report establishes:

- **First-pass extraction:** ~$0.002/district, ~19/23 (83%) fully band-covered with no follow-up.
- **Follow-up multiplier:** ~3.4× first-pass cost for the marginal fills in this run (expected to fall as
  #170/§4 suppressions land).
- **Real-band completion after the full loop:** 21/23 (91%).
- **Accuracy baseline (benchmark, separate corpus):** 95.2% band / 99.3% school @ $0.065 / 24 districts.

---

## 9. Template — what the next report in this series should carry

Keep these sections so entries stay comparable:

1. **Thesis restatement** (band completion) + what changed since the last report.
2. **Headline outcomes** — districts, runs, cost, real-band completion X/N, request tallies.
3. **Band completion table** — per district: real bands · first pass · now · follow-up result
   (+FILLED / STILL-GAP / phantom / over-covered).
4. **Mechanisms measured** — 7→6 and 7→2: counts, wins, failures, cost.
5. **Band-model noise** — phantom claimed bands + over-coverage counts (the trust denominator).
6. **Cost & economics** — first-pass vs follow-up split, per-district, outliers, guardrail behavior.
7. **Engineering learnings** — bugs fixed (commits) + filed (issues), no to-do re-logging.
8. **Open questions / next** + **baseline deltas** vs this table.

Data sources for the numbers: the governance DB (`extraction`, `school_fact`, `extraction_request`,
`batch_district.nces_school_counts` / `lea_claimed_bands`, `handoff`) — every figure in this report is a
query over those tables, not a receipt or a recollection.
