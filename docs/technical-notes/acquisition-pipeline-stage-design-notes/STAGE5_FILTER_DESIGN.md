# Stage 5 — Filter: present state & decision log

> **Authority:** Stage 5's purpose/boundary, the V2 detector/combiner scoring architecture, signals, the
> three-axis labeling object, the learning loop, and the attention-first console — what the code does
> today. Code is ground truth; this note narrates it.
> **Audience:** anyone building on or debugging Stage 5; anyone tracing why a record scored a given
> tier/decision, or why a label field means what it means.
> **Companions:** `PIPELINE_GOVERNANCE_AND_STATE.md` (state model, gates, the console);
> `STAGE5_TUNING_NOTES_2026-06.md` (tuning methods + citations); `docs/technical-notes/filtering-research/`
> (the weak-supervision / labeling-functions research V2 is grounded in); `STAGE4_PROCESS_DESIGN` (upstream);
> `STAGE6_DISPATCH_DESIGN` (downstream — the release decision this stage emits).
> **Update this when:** Stage 5's code behavior changes. Design turns belong in the Change log at the
> bottom, not here. Field observations from labeling that are NOT yet built stay in §3a (a distinct,
> intentionally-not-current section — see its own header).

---

## 0. Receipt from prior stage / Handoff to next stage

**Receipt from prior stage:** Stage 4's `processed.json` + representation text files, arriving via the
**incremental Stage 4→5 ingest** (triggered automatically when a Stage-4 batch resolves — see
`STAGE4_PROCESS_DESIGN` §4b). This is the seam where the batch dissolves: Stage 5 is **district-driven**,
not batch-driven (governance §12) — its console groups/sorts/filters by district and record facets, with
no batch concept in the UI.

**Handoff to next stage:** the release decision, read by Stage 6 directly from the governance DB
(`record`/`representation`/`label` + `release.decide`) — `filtered.json` is the auditable **receipt** of
that decision, not the transport. Stage 5 has no gate of its own that blocks Stage 6; `gate@5` is
per-record human labeling that feeds tier-B/C records into `send` — Stage 6 can dispatch tier-A records
(and any already-labeled target) without waiting for every record in a district to be labeled.

---

## 1. Purpose & boundary

Stage 5 sits between **Stage 4** (local processing — a pile of text/image representations per captured
URL) and **Stage 6/7** (routing + the paid OpenRouter extraction council). **Its job is to decide which
representations are worth the council's money, and to hand Stage 6 the best one per record** — maximizing
the *yield* of the paid stage (correct bell schedules per dollar) by (a) surfacing the true targets, (b)
**suppressing the confident negatives** so they're never dispatched, and (c) routing the genuinely
uncertain middle to a human at **gate@5**.

**The binding constraint (non-negotiable): the runtime filter is deterministic — NO paid/subscription AI
in Stage 5 itself.** The only paid AI in the pipeline are the Stage-2 discovery WebSearch subagents and
the Stage-7 council. Claude-the-agent examines captured files *during design* only to reverse-engineer
deterministic rules — never as the runtime classifier. Division of labor: **scripts classify/tier; the
human supplies ground-truth labels; the agent builds the rules** (see memory `feedback-human-curates-ground-truth`).

**Output = the release decision** (governance §4/§5): per canonical record a `decision` + `reason`, and
for the sent ones the **one best representation** — projected to `filtered.json` (the auditable *receipt*;
the DB is the working store) and consumed by Stage 6. Honestly labeled `gross_bell_to_bell` (REQ-055).

**Completion grain = district × BAND.** Schools/reps are the raw material; a district is "satisfied" when
every claimed band has confident minutes.

---

## 2. The V2 architecture: labeling functions → a combiner (REQ-113)

**The V1 tiering (`tier_and_category`, June 2025) was one long if/elif cascade** with an additive score
used only for intra-tier sort order. It validated at 85% tier-A precision / 0 tier-D targets on the first
12 districts — but **drifted badly at 59 districts** (measured 2026-06-30 over 440 labels): tier-A
precision **69%**, and tier-D — the "safe to auto-drop" floor — **leaked 10 real targets (9%)**. The
drift was not random; it traced to three structural defects of a *sequential* cascade (§2a), which is
exactly the failure mode the weak-supervision literature predicts for a monolithic rule
(`filtering-research/compass_artifact…md`).

**V2 replaces the cascade with a set of independent, individually-measurable DETECTORS ("labeling
functions", Snorkel-style) combined by a shallow COMBINER.** Each detector answers one narrow question
over the signals and emits a vote (`YES` / `NO` / `ABSTAIN`) with a confidence and a short reason. The
combiner reduces the votes to a **routing decision** — the thing Stage 6 actually consumes:

| routing decision | meaning | when |
|---|---|---|
| **send** | dispatch to the council | ≥1 high-confidence target detector fires, nothing high-confidence contradicts |
| **suppress** | confident negative — never dispatch | no target detector fires **and** a negative detector fires (or zero time evidence anywhere) |
| **review** | the ambiguous middle → gate@5 | anything else (competing detectors, weak evidence, low-fidelity input) |

`review` is the human queue (the attention model, §5, orders it). This maps 1:1 onto the two-stage
"cheap deterministic → route only the ambiguous middle to the LLM" pattern the research documents as best
practice (FrugalGPT / SUPG); **the tier letters A–D are retained as a derived, human-legible summary of the
decision + the strongest detector**, not as the decision mechanism.

**Why detectors, not a longer cascade.** Each detector is (1) independently testable ("how accurate is
`lf_footer_hours` alone?"), (2) independently tunable without silently perturbing a sibling branch — the
exact bug that produced the drift — and (3) the natural unit the human labels against (§4) and the harness
scores (§5). Adding a content pattern is a new detector + its config, never a surgical edit to a shared
if/elif. Code: `stage5_filter/detectors.py` (pure functions over the signal vector) + `combiner.py`.

### 2a. The three V1 defects V2 fixes (each measured, zero recall cost on the 382 canonical labels)

1. **De-chrome discarded real target evidence (false negatives).** V1 computes time signals over
   `page.main.txt` *exclusively* when de-chrome fires — but school hours very often live in the **footer**
   (`"Hours: 8:24 AM – 3:30 PM"`) or only survive in an **OCR/raster** rep the DOM text missed. 15 of 24
   footer-noted records had their real times zeroed; the Henning/Dickinson targets sat at tier D with
   `n_times=0` while `tesseract_raster.txt` held 4–9 times. **Fix: time signals compute over the
   MAX-evidence source** (`main` ∪ footer/header ∪ best raw rep), never an exclusive either/or — de-chrome
   stays for *keyword/category* signal (its measured win) but never suppresses time evidence. This becomes
   the `lf_footer_hours` detector + a corrected `n_times`.
2. **Tier B had no positive requirement (false positives).** V1 tier B = `n_times_in_window ≥ 2`, full
   stop — two unrelated times anywhere on a big page. **Requiring a `proximity_pair` (two times within
   ~220 chars, both in-window) removes 13 of 38 tier-B non-targets; all 3 real tier-B targets already have
   one.** Becomes the `prox` requirement in the weak-target detector.
3. **Tier-D "safe to drop" floor was too narrow (leaked negatives into review/send).** V1 drops only
   `n_times == 0`. A page whose only times are **all outside 07:00–16:00** is equally droppable.
   **Redefining the suppress floor as `n_times_in_window == 0` reclassifies 35 of 61 tier-C non-targets to
   suppress; 0 targets affected.**

### 2b. The detector set (labeling functions)

Each is a pure function `(signals) -> {vote, confidence, reason}`, config-driven where a threshold/keyword
list is involved (config-as-data, §5). Seed set — the polarity is the direction it pushes:

| detector | fires on | polarity | fixes / notes |
|---|---|---|---|
| `lf_footer_hours` | a time-range in the footer/header segment near an hours-intent word (`school hours`/`start`/`dismissal`) | **+target** (the list-shape) | §2a-1; a distinct information *shape* (footer list), not table/prose |
| `lf_time_table` | a real table (camelot/pdfplumber Markdown) with ≥2 in-window times / period rows | **+target** | table time-*density*, not just `has_table` boolean |
| `lf_prose_pair` | a proximity pair in-window + a positive keyword, no negative dominance | **+target** | the V1 tier-A core, retained |
| `lf_explicit_minutes` | `INSTRUCTIONAL_RE` (minutes/day) | **+target (strong)** | the "golden nugget" path (see memory `two-paths-to-instructional-minutes`) |
| `lf_weak_times` | ≥1 in-window proximity pair but weak keywords | **+weak** → review | §2a-2 (was tier-B noise) |
| `lf_news_feed` | URL/DOM feed pattern (`live-feed`/`/announcements`/`page_no=`) or an embed to a social/feed host | **−negative** | the #1 tier-A pollutant (20/42 FPs); a *down-weight*, not a hard reject (some carry real hub hours) |
| `lf_calendar_widget` | a calendar embed/iframe host, or `NEG_CALENDAR` dominance with no proximity pair | **−negative** | the Pittsylvania month-view cluster |
| `lf_board` / `lf_sports` / `lf_transport` | the respective negative-keyword class dominant | **−negative** | V1 neg classes, now independent votes |
| `lf_nonstandard_day` | weather/remote/delay/early-dismissal-only schedule language | **−negative (soft)** | genuine bell-shape but the *wrong* schedule (Stroudsburg `?id=`, TCUSD2 weather articles) |
| `lf_no_times` | zero in-window times anywhere (incl. raw reps) | **−suppress** | §2a-3, the corrected suppress floor |

**`lf_office_hours` is not a 14th standalone detector** — there is no `lf_office_hours` function in the
`DETECTORS` registry (`detectors.py`). It is a shared **negative Vote** that `lf_footer_hours` and
`lf_heading_hours` each emit inline, as a side effect, when their own evidence (a time-range whose
nearest heading/segment reads `office`/`staff`/`workday`) points to building/office hours rather than the
school day — the office-vs-school-hours confusable (research §5.2; the LCPS staff-hours page). Both
producing functions are already counted above; this row exists so a reader doesn't go hunting for a
`def lf_office_hours(...)` that doesn't exist.

**The combiner** (`combiner.py`) is deliberately transparent — a **weighted vote** first (weights =
config-as-data), *not* a learned model, per the research's "start with weighted majority vote; only
graduate to a `LabelModel` if diagnostics show heterogeneous accuracy at medium label density" (§5). It
records **which detectors fired** on each record (into `signals_json`), which is what makes per-detector
scoring (§5) and UI pre-fill (§4) possible.

---

## 3. Signals — the raw material (deterministic, no AI)

Computed from Stage-4 text + the on-disk binaries + the **Stage-3 DOM segments** (`page.{main,header,footer,nav}.txt`),
at page granularity for multi-page PDFs. Existing (V1, retained): `n_times`, `n_times_in_window`,
`times_before/after_5pm`, `proximity_pairs`, `positive_kw`, `negative_kw` (board/sports/calendar/transport),
`instructional_time`, `has_table`, `period_hits`, `roster_school_names_hit`, `visual_text_gap`, per-page
`n_times`, `is_handbook`, `harvest_pages`, `dechromed`.

**New in V2 (from data we already capture — no re-capture needed):**
- **`footer_times` / `header_times`** — time positions found in the segment reps (fixes §2a-1; feeds `lf_footer_hours`).
- **`heading_hours_hits`** — a time-range whose nearest preceding heading matches an hours-intent regex
  (`office|school|hours|schedule|start|dismissal`), with the **matched heading label captured** (turns the
  office-vs-school confusable into a structured field, per research §2.2/§5).
- **`table_time_density`** — in-window time count + period-row count within the best table rep (feeds `lf_time_table`).
- **`cms_hint`** — **promoted from Stage-3-only to a first-class record signal** (REQ-115). Today `cms_hint`
  is computed at Stage 3 but buried in `captures.json` `fingerprint_json` and only rolled up to a console
  count — Stage-5 scoring is structurally blind to it. V2 threads it into `signals_json`, **not as a score
  input** but as the **grouping key** for per-detector accuracy (§5): a detector may be reliable on one CMS
  template and noisy on another, visible only if CMS is tracked (matches the tuning note's VPC-by-vendor thesis).
- **`embed_hosts`** — categorized iframe/embed `src` hosts (social/feed · calendar · doc-viewer · other),
  from the Stage-3 capture upgrade (REQ-115, §6) — a structural, vendor-agnostic replacement for guessing
  "this is a feed" from URL/keyword patterns.

**Trigger discipline (recall-bias stance).** Hard `suppress` fires only on high-precision negatives
(no in-window times anywhere; a confident negative detector with no target detector). Everything with any
target evidence flows to `send` or `review` — the expensive error is silently dropping a real schedule
before the human sees it; a borderline page reaching gate@5 costs only review time.

### 3a. Field observations from labeling — candidate refinements (RECORDED, not yet built)

> A running log of patterns Ian spots during gate@5 review that should sharpen the detectors/signals later.
> **Written down, not implemented** (per `feedback-explore-before-scoring-changes`): fold in deliberately and
> measure against the labels, never tune by eye. New observations append here.

**(1) A footer time-range on a DISTRICT page leans building/office hours**; on a SCHOOL page it leans the
student day (2026-07-01). An unlabeled footer range (the `school_start_end_list` shape) is more likely
`office_building_hours` when the page is district-focused, and more likely a real target on a single-school
page. → would down-weight `lf_footer_hours` / up-weight `lf_office_hours` when the page is a district page.
- **Open sub-problem — we lack a reliable "page focus: district vs school" signal, and the domain/TLD is NOT
  it** (schools may or may not have their own subdomains). Candidate signals already on hand:
  `roster_school_names_hit` (many distinct school names on one page → district/hub), `intended_schools` (the
  candidates.json school[s] a URL was discovered for — exactly one → school-focused), the URL path. None is
  decisive alone; this needs its own small page-focus classifier before the observation can be used.

**(2) Off-the-hour minutes are a POSITIVE instructional signal — asymmetrically (2026-07-01).** A range with an
oddly-specific minute (e.g. **8:24**–3:30) is far more likely a real bell schedule (times computed from actual
period boundaries) than a tidy stated office-hours range. **The asymmetry is the whole point:** it's the `:24`
that's positive — a round range like **8:00–4:00** is **NEUTRAL, not negative** (round times say nothing either
way). So the candidate signal is "≥1 in-window time has a non-round minute (not :00/:15/:30/:45)" → a small
positive nudge for `lf_footer_hours` / `lf_weak_times`; round times must **never** be read as evidence *against*
a target.

**Motivating case — Dickinson 1, ND (one district, the same footer SHAPE meant different things).** The
**district** page and **Dickinson High School** carried building/office hours in the footer; **Dickinson Middle
School** carried the real instructional start/stop — disambiguated by page focus (obs. 1) and the off-the-hour
minutes (obs. 2). This is exactly the office-vs-school-hours confusable (the research's #1 danger) and where
both observations would pay off.

**(3) Registration, open house, back-to-school, and last day of school information may merit facets.** Content about these sorts of events seem to come up a lot. There may be associated keywords to look at for downweighting. They may merit adding facet checkboxes to the console view for Stage 5.

**(4) SUMMER SCHOOL pages are a confounder shape the detectors don't distinguish (2026-07-02).** Marshall
WI (5508790, batch_00008): `…/students-families/summer-school.cfm` auto-sent as **tier-A** — it carries a
genuine-looking start/end pair and schedule keywords, but summer hours are NOT the regular instructional
day (shorter day, subset of students, different calendar). Same family as `lf_nonstandard_day`'s
weather/delay cases: real bell-shape, wrong schedule. Candidate signal: a `summer` keyword class
(summer school / summer session / ESY / extended school year) as a soft negative and/or a `summer_school`
confounder facet on Axis 2 (pairs naturally with obs. 3's event-content facets). Also relates to the
recency/dispatch question — see `STAGE6_DISPATCH_DESIGN` §3G.

**(5) Comprehensive review 2026-07-15 (epic #106) — measured the money leak, re-specified the vetoes,
and mined the un-attributed absents.** A full pass over the 1,473 labels × the live scorer. The findings
are the ground for the epic-#106 slate (issues filed 2026-07-15); recorded here because several are
candidate refinements, not-yet-built. Method: DB confusion matrix + note/facet mining + text-representation
grep + a 5-way Haiku subagent clustering of the un-attributed absents. All numbers are on the labeled corpus.

- **The leak is on the SEND side, not suppress.** Decision-level confusion (tier A auto-sends, B/C→review,
  D→suppress): auto-suppress miss = **3/659 = 0.5%** (already safe; recoverable via 7→ loops), auto-send
  false-send = **115/473 = 24.3%** (the money leak). Review (B/C) is 84% absent — the human-time sink. So
  "how close are we to auto" is asymmetric: suppress is ready, send is not.
- **The false auto-sends decompose into two DIFFERENT problems.** (a) ~60 driven by detectors that don't
  exist or can't be measured — irregular-day (`lf_nonstandard_day` frozen at 0.17 precision because its
  facet has no checkbox, #207) + recency (**no temporal signal at all** — real schedules from 2001/2015/
  COVID-era auto-send) + summer (#223). (b) ~40 carry existing confounder facets (news_feed/calendar/board/
  sports) that LOSE the vote — #108 measured those detectors at 0.13–0.18 precision. (a) is "build a
  detector"; (b) is "tune weights against the facets we already have," NOT new labels.
- **Stage-6 eligibility is a UNION and a changeable lever:** `tier==A OR human_label∈target`. The confounder
  detectors are therefore candidate **negative eligibility gates on the auto path**, and the union makes an
  aggressive veto safe (a false veto is recovered by the human path + 7→ loops; a false send is money gone).
  Simulated vetoes on the auto path: ~~**stale + irregular** removes 53 false sends for 6 target-vetoes →
  24.5%→15.2%~~ — **the STALE half of this is REFUTED, see obs. 6**: measured on the real tier-A records, a
  stale veto removes **1** false-send for **17** target-vetoes (and 0-for-4 at the pre-2017-18 floor), i.e.
  stale contributes ~nothing to the 24.5%→15.2% and the combined figure never reproduced. The *irregular*
  half is untested and remains the candidate (#207). Still sound and unaffected: adding the
  existing-confounder facets removes 99 but **wrongly vetoes 49 real targets** (they co-occur with real
  hubs — Las Cruces). So news/calendar/board/sports must stay SOFT (combiner weight), never eligibility
  gates — that is the basis for #519.
- **The irregular veto MUST be conditional.** Text grep (not notes): **37% of real single-school-bell-schedule
  targets also contain an irregular-day term** (Early Release / Minimum Day / Inclement / Late Start / two-hour
  delay / remote). An unconditional veto would false-negative 37% of targets. Veto only when an irregular
  signal is present AND no regular-day structural signal is — the existing `lf_nonstandard_day` philosophy.
  Term class to add: Early Release, Minimum Day, Inclement (Ian, 2026-07-15) + Late Start, Delayed Opening/
  two-hour delay, Remote/Virtual Learning, Half Day.
- ~~**The stale veto's "recall cost" is mostly illusory**~~ — **SUPERSEDED by obs. 6 (2026-07-16): this
  bullet is WRONG and its projection did not reproduce.** It read: of the 6 vetoed targets, 5 are stale
  schedules the human's own notes say don't-use ("From 2001. Should not use," "COVID-19 years," "more recent
  handbook at [url]"), so recency should be the SAME temporal rule (`school_year.py`) applied one gate earlier
  (Stage-6 eligibility). **Two defects:** (a) the 6/53 figures were mined from *human notes* — records where
  the human had already written "too dated" — which is judgment, not a signal any detector can reproduce; and
  (b) "the same temporal rule" is ambiguous across two very different floors, and at the recency floor
  (`ACCEPTABLE_BELL_YEARS`, 2023-24+) a veto is actively harmful. Measured refutation + the corrected
  two-floor design: **obs. 6**. Retained (not deleted) because the superseded projection is what a reader
  would otherwise re-derive. The caveat below still stands: a templated handbook/PDF footer date must not be
  read as the schedule's vintage.
- **Ian's footer/densest-zero-times heuristic confirmed:** "if the densest representation shows 0 times, no
  schedule." Only 2 tier-A/B records have max n_times==0 across all reps (both true absents) — the
  `n_times_in_window==0` suppress floor already honors it. A valid cross-check, small lever.
- **The 228 un-attributed absents (target_absent, no facet, no note = 23% of absents) are NOT a labeling
  debt.** 218/228 are already tier-D-suppressed; the Haiku cluster: ~76% structurally EMPTY pages (generic
  nav 31%, policy/handbook 12%, staff/HR 7%, staff directory 5%, registration 7%) with no times — correctly
  suppressed, no rich facet warranted. **Don't census-label easy negatives**; grade the suppress detectors on
  the 783 absents that DO carry facets/notes. The one pattern worth formalizing is **`schedule_link_only`
  (~14%)** — a page that names a bell schedule whose times aren't in the capture; a RECALL affordance
  (follow-the-link / capture-retry), not a confounder facet. A distinct **capture-fidelity recall leak**
  surfaced too (login walls, 0-byte PDFs, truncation — a Stage 3/4 problem, not scoring). ~3 records flagged
  as possible human false-negatives / buried-handbook (e.g. `4824000:af06722adb` — tier A, 7 in-window times,
  2025-26 handbook, labeled absent) — pending human re-inspection.

**(6) RECENCY IS TWO RULES AT TWO FLOORS, NOT ONE VETO — obs. 5's stale-veto projection REFUTED by
measurement (2026-07-16).** Attempting to build the recency veto (#241) surfaced that the enabling signal
§3G names — a per-record `content_school_year` — **does not exist in the codebase** (zero hits). Built a
throwaway URL-year extractor to measure what a stale veto would actually do, against the live labeled corpus
(1,474 records / 1,621 labels; 473 tier-A labeled = the exact auto-send population #515 targets). Method:
URL-decode → year-pair regex (`2018-2019` / `2025-26` / `25-26`, consecutive-pair validated) → guard out
GUID/asset-id false years → judge the year with `school_year.py`. **Read this before rebuilding any recency
veto.**

- **At the recency floor (`ACCEPTABLE_BELL_YEARS`, 2023-24+) a veto is HARMFUL — it makes the metric worse:**

  | tier-A veto @ 2023-24 floor | count |
  |---|---|
  | false-sends removed (the point) | **1** |
  | real targets vetoed (the cost) | **17** |
  | false-send rate | **24.1% → 24.8%** (it RISES) |

  The rate rises because the veto strips real targets out of the denominator while removing ~no waste.
  **Root cause — staleness and target-absence are near-INDEPENDENT:** a stale handbook usually still
  *contains* a real bell schedule, which is exactly why 17 of them are human-labeled targets. Vetoing on
  age therefore hits targets, not waste. The human notes said so before the measurement did: *"Dated, but
  **not ruled out**"* (`4220130:458fd47cc7`), *"Not ideal given COVID-19 years, but it certainly looks like
  the handbook reflects their [day]"* (`762b79b017`), and `5501770:96bba5deeb` [2018-19] carries a clean
  answer — *"Our school day is from 7:18 a.m. to 2:31 p.m."*
- **At the validity floor (pre-2017-18) the rule is CORRECT but pays ~0 money.** Ian's actual intent
  (2026-07-16): "stale" = *before the 2017-18 school year* — floored on the **CRDC 2017-18 federal input**
  we already use for LCT (`DATA_SOURCES.md`), because a 1999 newsletter breaks the REQ-026 ≤3-year span
  against it no matter how good its times look. Measured: **12 pre-floor records in the whole corpus** (9 of
  them one district — Dickinson `3800038` school-board minutes); the tier-A slice is **4 records, all real
  targets, 0 false-sends**. The 8 absents are already tier-D/B (suppressed or in review) — the veto has
  nothing to save. **So this is a CORRECTNESS guarantee (don't extract what REQ-026 forbids us to use), not
  a cost lever — justify it on rule-compliance, never on money.**
  - **Semantics: HOLD, not hard-reject (Ian, 2026-07-16).** Suppress-to-review + weight it into scoring;
    human can override. Rationale: preserves options if a non-trivial volume of districts turn out to have
    *nothing* newer available (`2905790:d953e92385`, Brashear's 2012-13 HS Timetracker, is that district's
    real bell table — and is also #512's column-snake case). Same risk-asymmetry test as
    `project-auto-act-when-failure-observable`: a hold is reversible and its failure is visible; a
    hard-reject silently destroys a district's only evidence. Resolves the "hard-reject vs. hold" question
    §3G left open.
- **Prefer-recent (§3G / #107) is the half that saves money, and it is a RANKING, not a gate.** Among
  siblings ≥ the 2017-18 floor covering the same school/band, dispatch the most recent and **hold** the
  stale sibling (available for a cheap 7→6 re-dispatch if extraction fails). Zero recall cost *by
  construction*: no fresher sibling ⇒ the old doc still sends. Marshall WI is the proof — the 2025-26,
  2021-22 and 2018-19 handbooks are ALL real targets; the recent one makes the others redundant, not wrong
  (the human's own note on `0a2839a21f`: *"More recent handbook at [url]"*). Misreading a year only
  reorders siblings instead of discarding evidence, which is why the extractor's FP cost collapses in this
  role — the same signal is unsafe as a gate and safe as a sort key.
- **Consequence for the epic: #515's headline number is WRONG.** "24.5%→~15%, the money lever" came from
  *stale + irregular together*; stale contributes **0**. #515's remaining value rests entirely on #207's
  irregular-day veto (which is gated on a human facet decision), so **#515 is not the money lever and should
  not be the resume point**. The measured money lever is **#519** (tune the existing news/calendar/board/
  sports detectors — ~40 of the 115 false-sends, existing facets, the built #108 harness, no new labels).
- **Scope (Ian, 2026-07-16):** **#241** = the pre-2017-18 validity floor (hold + scoring weight) — its
  Brashear origin. **#107** stays the parent and remains whole per §3G ("complementary, not duplicates"):
  it builds the shared `content_school_year` signal + prefer-recent dispatch; #241 consumes that signal.
- **Extractor caveats for whoever builds `content_school_year`** (all hit during this measurement):
  **URL-decode first** — `Bell%20Schedule%2025-26` parses as the year `2025-26` raw (the `20` is an encoded
  space) and as `25-26` decoded; it lands on the right answer for the wrong reason and won't generalize.
  **Guard GUIDs/asset-ids** — `live_feed_image/17728374`, `uploaded_file/5125`, and hex UUIDs yield phantom
  years (10 false hits on targets alone). **A CMS upload path is not a vintage** — `/wp-content/uploads/
  2021/05/` dates the upload, not the schedule (158 bare-YYYY hits, mostly noise). **A date is not a school
  year** — `4-20-21-Minutes.pdf` is April 20 2021. **Validate the pair is consecutive** (`2020-2023` is a
  plan span). And the Brashear newsletters that motivated #241 (`September01.htm`, `October98.htm`) carry
  their year as a **month-word + 2-digit suffix** — pair-matching cannot see them at all, so the pre-floor
  population above is *what this regex catches*, not the population #241 is actually about.

---

## 4. Labeling — a THREE-AXIS object (v2.1, REQ-114)

**V1 forced two bad single-choices:** pick one target shape *or* one non-target reason. Real pages
(homepages, feeds) break both — a homepage carries a news feed *and* a footer hours block *and* a board
notice. **v2.1 (Ian, 2026-07-01) makes the label a multi-axis object** that mirrors the detectors, so each
human answer scores exactly one detector (§5) and multi-module pages are represented honestly:

- **Axis 1 — the target SHAPE (radio, single):** distinct because each derives minutes / routes to Stage 6/7
  differently. `school_start_end_list` (footer-style "Hours: 8:30–3:30") · `school_bell_table` (Period 1…N;
  start of 1st period → end of last) · `school_start_end_prose` · `district_hub_by_school` (per named school)
  · `district_hub_by_band` (Elem/Middle/High ranges) · `explicit_instructional_time` · `target_other_shape`.
  Plus terminals **`target_absent`** and **`unusable`** (kept distinct: "no target" vs. "can't read it").
- **Axis 2 — confounding signals PRESENT (checkbox, multi):** the former non-targets, now non-exclusive —
  `board` · `sports` · `academic_calendar` · `community_calendar` · `transportation` · `news_feed` ·
  `office_building_hours`. Usable whether or not a target is present (Las Cruces: a real `district_hub_by_school`
  *delivered in* a news feed). These are the ground truth for the negative detectors.
- **Axis 3 — where / how it hides (checkbox):** `buried_handbook` (+ a **print-dialog page range** "4, 7-9"
  parsed to `[4,7,8,9]` for the harvester — the guessed `harvest_pages` vs. labeled pattern) · `needs_vision`
  (image/PDF only, missing from all text) · a structured `where` picker (main/footer/header/table/image/feed).
- **Free-text note stays** as color commentary.

**Pre-fill is a HINT, never persisted.** A fired detector shows a "flagged" chip next to its facet, but the
box is not auto-checked — only human checks persist. Auto-seeding "facet := detector vote" would make
agreement trivially 100% and destroy the per-detector measurement (§5), so facets accrue only through gate@5.

**Migration, not reset (`migrate_label_v21`).** The 440 v2.0 labels + 202 notes stay valid evidence: clean
target renames (`school_bell_schedule`→`school_bell_table`, `district_hub_schedule`→`district_hub_by_school`
(by-band re-confirmed by hand), `nonstandard_format`→`target_other_shape`); non-targets → `target_absent` +
the confounder facet; v2.0 flags fold into Axis-3 facets. 128 targets preserved. git holds the v2.0
`labels.json` as the restore point. The detail pane also reordered **text-first** (footer/header first) with a
per-rep "unique-times-vs-densest" readout, so the human confirms the target is in a TEXT rep (the council
reads text) before the image can anchor a premature check-off.

**Every confident label also writes a gate-decision calibration row (REQ-121/#210, built 2026-07-10).**
Saving a label with a real target-shape or terminal non-target decision (status `labeled` — never a
`unsure`/hedged review, and never more than once per cascade: a label that cascades to cluster members
logs exactly one row, for the representative the human actually looked at) calls
`process_governance.gate_calibration.gate5_label_record`, which compares the human's accept/reject against
what the record's tier says auto would currently do (`release.decide`'s tier gate: A→accept, B/C→escalate
(no unilateral-auto data point), D→reject) and persists it via `common.calibration.record_calibration` on
the same DB transaction as the label write. This is the mechanism that surfaces the survivorship signal
directly: a tier-D record (auto would reject) that a human labels a real target logs `agreed=False` — a
false negative auto would have made. See `PIPELINE_GOVERNANCE_AND_STATE.md` §11b for the full
calibration-log design; gate@6 and gate@7 get the analogous hooks.

**Reset labels — an honest path back to `unlabeled` (#228).** A label can be wrong in a way neither
`target_absent` nor `unusable` can truthfully represent: a page that IS target-shaped but belongs to the
**wrong entity** (a real bell schedule pulled in from another district — the #227 Millard contamination,
where unscoped discovery mixed same-named schools nationwide into the candidate set). Mislabeling a real
schedule as a non-target to get it out of the way would corrupt the detectors' training signal, so the
only truthful state is unlabeled. `POST /api/reset-labels` (`{scope: "record"|"district", target_id}`)
clears `primary_label`/`facets_json`/`note` and sets `status='unlabeled'` via the single shared bulk
helper `build_signals.reset_labels_bulk` — the one definition of what "reset" means, reused by both the
console endpoint and the remediation tooling (below) so the two never drift apart. It mirrors
`save_label`'s side-effect set (topology + attention recompute, then a post-commit `labels.json`
export + `filtered.json` refresh) so derived state stays coherent, and it **reverses the cluster
cascade**: resetting a cluster representative resets every current member the same way labeling a rep
cascades a label onto them. A reset carries no terminal decision, so it deliberately logs **no** gate@5
calibration row (consistent with `gate5_label_record` returning `None` for an unlabeled status) and never
rewrites prior calibration history — past human decisions stay on the log (auditability). Two console
entry points: a district-level reset button (`static/app.js`'s `.dist-resetbtn` → `resetLabels("district",
...)`) and a record-detail reset button (`#resetLabelBtn` → `resetLabels("record", ...)`).

**Upstream of Stage 5: closing the empty-domain contamination chain that motivated #228 (#229/#227).**
The Millard case above was possible because a district could enter a batch with a blank or junk NCES
`WEBSITE` value, flipping Stage 2 discovery to its unscoped national-scope branch. `common/discover.py`
now centralizes `domain_of()` (normalizes a raw NCES cell to a bare host, or `""` if blank) and
`is_scoping_domain()` (true only for a real dotted hostname with no whitespace — rejects blank, `N/A`,
`none`, address-like junk), and Stage 1 batch admission refuses a district that fails the check rather
than silently letting it through to the unscoped branch. `process_governance/remediate_contamination.py`
is the paired remediation tool for districts that got through before this guard existed (the #227 Millard
case is its default): a manifest-first, dry-run-by-default CLI that resets the contaminated labels via
the same `reset_labels_bulk` helper, purges the district's regenerable signal/cache rows, corrects the
batch's stored domain, and records a `state_event` — without touching the precious `label`
history it didn't reset or re-spending on discovery (the scoped re-run is a separate, gated console
action). Both fixes land upstream of Stage 5 (Stage 1 admission, a Stage-1/2 remediation tool) but are
noted here because Stage 5 labeling is what surfaced the contamination and what #228 exists to repair.

---

## 5. The learning loop (REQ-113 harness extension; scale endgame deferred)

The machinery already exists and V2 **extends** it — it does not replace it: `harness.py` (fingerprinted
scorecards), `frontier.py` (recall-constrained grid/coordinate search over `detectors.DEFAULT_DETECTOR_PARAMS`
+ LOGO-by-district CV guard — re-pointed at the live V2 combiner path 2026-07-02; the V1 `tier_and_category`
cascade it originally tuned is deleted, not just superseded), `tuning_ledger.py` (append-only before→after
episodes), config-as-data with `provenance`.

1. **NOW (this REQ): per-detector precision/recall.** The harness scores **each detector against its
   matching facet** (not just one aggregate tier-A number) — Snorkel's LF diagnostics: **coverage** (how
   often it fires), **accuracy** (precision when it fires), **polarity**, **overlap/conflict** (where two
   detectors disagree). This is the prerequisite for tuning anything, and it's what makes "you and me
   having chats to adjust weights" a data-grounded conversation instead of guesswork.
2. **BUILT (#91, 2026-07-14): outcome feedback.** With Stage 8/gate@8 landed, the *did the representation
   we sent actually extract* signal is now wired into this harness: `harness.score()` emits an
   `extract_outcome` section — per dispatched-and-extracted rep (production `school_fact` rows joined
   back on `rec_key`, probes excluded), the any-accepted/mixed/all-unresolved outcome, the headline
   P(any_accepted), the per-tier calibration table, the per-detector grid recomputed against the paid
   outcome, the two disagreement cells (labeled-target-but-all-unresolved; rejected-but-accepted), and
   an `unjoined` count (no-silent-caps). A fourth `outcome` fingerprint keeps scorecards re-derivable
   as outcomes accrue, and the ledger diffs `extract_outcome_calibration` per episode. It flows into the
   **same** ledger/harness (not a separate system), exactly as planned: the deterministic decision is a
   *proxy* whose calibration against the paid outcome is measured. Measurement only — v1 changes no
   scoring config; the outcome signal is per-rep `school_fact.status`, not gate@8 approval (which lags).
   The read is raw SQL on the shared governance DB — stage5 never imports stage7 (the layering contract).
3. **LATER (documented, deferred — the scale endgame, `STAGE5_TUNING_NOTES`):** a learned combiner
   (Snorkel `LabelModel`, inferring per-detector accuracy from agreement without gold labels for every
   point) replaces the hand-weighted vote **once diagnostics justify it**; hierarchical partial-pooling
   **by CMS vendor** (the natural structure, since detector accuracy plausibly varies more by template than
   geography); ADDIS online-FDR drift across per-vendor/per-state streams; VPC/ICC to decide which knobs
   live at which level. **None of this runs at n≈440** — built only when label coverage warrants.

---

## 5a. The anti-survivorship exploration quota — a revocable autonomy license (#211, REQ-120)

**The one-sentence thesis:** *the filter may run only as autonomously as its reject audit is currently
validating it — and the moment that validation lapses, autonomy falls back one supervision level rather
than the pipeline halting.* This is not a metric we watch; it is a **control law** that licenses gate@5's
autonomy and revokes it automatically. Full governance context: `PIPELINE_GOVERNANCE_AND_STATE.md`
§11b; decision record: `production-quality-control-research/FINDINGS-AND-DECISIONS.md` §0/§1.

**Why it is NOT a current hole (the census-labeling immunity).** The selective-labels / "illusion of
improvement" risk — tuning the filter and measuring before/after only on the *approved* set, blind to
recall collapse in the reject pile — is real in general but **inactive here today**, because of how the
queue is actually worked: districts are attention-sorted, but **within a district every URL is labeled,
all tiers, rejects included.** That is a *census*, not a filter-gated sample. `harness._labeled_records`
pulls every labeled record regardless of tier, so a tier-D page labeled `school_bell_table` already counts
as a false negative in the A+B recall denominator — **the recall we defend (A+B 0.9961, §5b/#208) is
therefore already honest.** The hole opens at exactly one moment: **when gate@5 goes auto and
census-labeling stops.** So the quota is the instrument that *replaces* census-labeling, switched on before
it switches off — the gate on relaxing Stage-5 supervision, not a fix for today. (Root cause the instrument
is mandatory, not optional: the gate is **deterministic** — Swaminathan & Joachims, counterfactual
correction is impossible under deterministic filtering even with infinite data; only injected stochasticity
recovers the signal.)

**Core mechanism = a human label on a random reject sample (Tier A, ZERO cash).** A human label answers the
load-bearing question ("was this a target we wrongly dropped?") and, stratified, tells random loss from
**correlated** bias. Paid reject→Stage-7 extraction (the old "route rejects to the council") is a distinct,
costlier measurement (Tier B — "could the council *extract* it," narrow marginal signal over Tier A) that
is **deferred, likely never a separate build:** the instant Tier A confirms a false-negative, that record
rejoins the normal Stage-6 → Stage-7 dispatch like any confirmed target — no new plumbing.

**The invariant (a COUNT over a rolling window, not a cumulative %).**

> Auto-suppression at gate@5 stays licensed only while a rolling window holds **≥ N randomly-selected,
> human-labeled rejects drawn from the CURRENT config generation.** N is a count (rule of three:
> ~300 zero-miss rejects ⇒ 95% confidence the reject FN-rate is < 1%), fed by a **p%-of-flow sampler**
> (p sets the flow, N the sufficiency). Below the bar, **gate@5 auto DEMOTES to manual** (census mode)
> until the audit sample refills — **the restart bar is the sample, not the whole reject backlog.**
> A **deadband** (demote < N; re-promote only above ~1.2·N or a full clean window) prevents auto↔manual
> flapping.

Why not "5% of all rejects, always": a cumulative % floats above the bar on stale labels; % is
statistically too thin on small streams and re-imports the manual-inspection-at-100k-scale problem
(commandment 2) on big ones; and "labeled" must mean **"*randomly* labeled"** — selection randomness is
enforced at *draw* time (a dedicated `run_kind = exploration_audit` queue the human works top-down, never
cherry-picks), or the estimate is biased and the license is theater. Every draw is logged
(seed, rec_key, score/tier, outcome) so an outsider can replay "you rejected class X; your own random audit
surfaced it N times" (the auditability north star, concrete). The honest recall signal is
**Rejection-Quality = TNR on the exploration cohort**, computed each cycle.

**Design criteria that fall out.** (a) **Demote, don't halt** — losing the signal pushes the gate *toward
more* supervision, the safe direction; self-healing (manual review regenerates exactly the labels that
restore coverage); scoped to Stage-5 auto-suppress alone (other stages keep draining). (b) **Windowed +
current-config-scoped** — a reject audited under an old config says nothing about the live one.
(c) **Stratify the diagnostics, gate on the aggregate** — break the audit down by suspected bias axes
(reader-tier / CMS-family / doc-format) to *catch correlated misses*, but hard-gate on the aggregate plus
flagged strata only (per-stratum hard gates multiply human cost). (d) **Enforcement ships DORMANT** — the
demote-hook is a no-op until gate@5 is actually set to auto (the `--assert-floor` pattern, §5b/#208: the
guard ships *with* the capability it guards).

**Calibrate NOW against census truth (the cheap, closing window).** Build the pure control-law core
(license state-machine, count-sufficiency, reproducible sampler, TNR metric) and the coverage meter now,
and **validate the sampler retrospectively against the census we already have:** run a 3–5% random draw
over completed (fully-labeled) districts and confirm it *reproduces* the reject-quality the full labels
report. If it does, we've earned trust in it before the census stops; if not, we learn N must be larger
*first* (measured-pass discipline applied to the instrument). Only works while census labels still accrue —
build the gauge while the truth is observable (same logic as the calibration meter, #210). Caveat:
completed districts are attention-sorted (messiest-first) → this is a **worst-case** calibration, labeled
as such.

**Build order.** The pure core + its invariant tests land first (no DB, no cash — the harness/frontier
precedent); the live wiring (querying the reject population, presenting the randomized audit queue in the
console, the demote-hook on the gate@5 auto toggle) follows in the full #211 build, and its enforcement
stays dormant until gate@5 auto exists. **Explicitly NOT:** never impute reject labels (reject-inference
entrenches / can reverse the bias); no active/uncertainty sampling as the primary mechanism (it
under-covers the confident-reject region — the exact region that entrenches a wrongly-rejected class).

**As BUILT (`exploration_audit.py`, PR #216 + its review round, 2026-07-10):** `rule_of_three_upper_bound`,
`rejection_quality`, `select_audit_sample`, `next_license_state`/`resolve_gate_mode` — 17 tests, no DB, no
cash. Sampling is `random.Random(f"{seed}:{key}").random()`, **not** a hand-rolled hash — the same
deterministic string-seeded pattern `stage1_queue.queue_batch` already uses for `stratified_pick`/
`select_schools` (one precedent in the codebase, not two). The review round hardened three invariants a
first draft got wrong: `promote_threshold`/`next_license_state` now **raise** if the deadband factor is
`<= 1` or an explicit `promote_n <= floor_n` (a caller could otherwise collapse or invert the deadband and
get the exact auto↔manual flapping it exists to prevent); `next_license_state`/`resolve_gate_mode` **raise**
on an unrecognized mode string instead of silently routing it into the manual branch (a typo'd stored state
must surface, not masquerade as a conservative decision); `rejection_quality`'s two published fields
(`false_negative_rate`/`rejection_quality`) are now complements of the *rounded* rate so they always sum to
exactly 1.0 (independent rounding had let them drift to 0.999999 at some counts).

**As BUILT — the live wiring (`exploration_live.py`, #211/REQ-120, 2026-07-12).** The DB half named above
now exists, binding the pure core to the governance store; enforcement still ships DORMANT (gate@5 is
configured manual, so the hook returns "manual" and writes nothing). Three pieces + a calibration probe:
- **`reject_population(con)`** — the audit universe: the current **tier-D (SUPPRESS)** bucket, representative
  + non-duplicate rows only (one audit unit per physical page, matching the label cascade). The reject
  decision is read live from `record.tier`, so the population IS the current-config reject set.
- **`audit_sample` / `coverage`** — the pure `select_audit_sample` bound to that live population, partitioned
  into the audited **window** and the **pending** queue, plus `rejection_quality` over the audited labels.
- **`resolve_gate5_mode(con, *, persist, cov=None)`** — THE gate@5 demote-hook and the (finally) live caller
  of `exploration_audit.resolve_gate_mode`. Reads `configured_mode` FIRST via a cheap point-read; a PR #248
  review fix added a **dormant fast path**: when configured manual (today, always) and no `cov` was
  precomputed, it returns immediately WITHOUT running `reject_population`'s query at all — `window_count`
  etc. come back `None` (skipped, not computed-and-discarded), since the hook fires on every gate@5 label
  save (below) and the full tier-D scan was dead work while dormant (`build_signals.py` also gained
  `ix_record_tier` for when a gate actually is auto). When configured auto, it computes the live
  `window_count`, applies the deadband law, and **persists the transition back to `license_state`** (the
  hysteresis memory). Wired into `save_label` AND `reset_labels` (self-healing in both directions: labeling
  or un-labeling a reject re-evaluates the license), both inside a `con.begin_nested()` SAVEPOINT + swallow
  (another PR #248 fix — the hook is advisory and must never roll back the human's write on a transient
  failure). Surfaced read-only at **`GET /api/exploration-audit`** → a Settings-console coverage meter
  (window vs floor, reject-cohort quality with the rule-of-three ceiling, the pending draw) — one
  `audit_sample` draw now serves the whole response (a third PR #248 fix; it used to query twice).
- **`calibrate_against_census(con)`** — the retrospective validator feeding #214's measured-pass: does a p%
  draw over the fully-labeled reject bucket reproduce the census reject-quality?

**Current-config scoping is STRUCTURAL, not a stored fingerprint** (the key design call): the window is
recomputed over the live tier-D set every call, so a reject *rescued* to tier B by a config change simply
leaves the population — no reject-audit table, no persisted config generation. The sampler is pure +
growth-stable, so the draw replays from `(seed, the DB's current reject set)` and the outcome is the human's
label already in `label` (precious, git-backed) — the auditability replay needs nothing more persisted.
Verified live: 566 tier-D rejects, 24 sampled @5%, all 24 census-labeled with zero misses → quality 1.0,
window 24/300 (informational, as expected while census-labeling is still on). 7 govdb tests + an endpoint
smoke. **Still deferred:** a *dedicated* `run_kind=exploration_audit` queue MODE in the Stage-5 tree (the
pending list in Settings is the working surface today, sufficient while census-labeling means every reject
is already labeled); Tier B (paid reject→Stage-7 extraction); the doubly-robust retrainer fast-follow.

---

## 5b. The canonical recall floor — enforced at the re-ingest actuation point (#208, built 2026-07-10)

**One constant, one enforcement point.** `harness.py` defines `RECALL_FLOOR = 0.98` and `FLOOR_TIER = "A+B"`
as the single source of truth — `frontier.py` and `tuning_ledger.py` both import it (previously frontier
used 0.97 and the ledger used 0.98, independently, both pinned to tier-A recall, which sits ~0.89 by design
since borderline targets route to review — an **unmeetable, non-binding** floor). The floor defends **A+B
recall** (reaches-review: no target silently dropped to tier D), not the tier-A auto-send bucket.

**Enforcement is transactional, not advisory.** `harness.assert_floor(con)` scores the labeled set and
raises `SystemExit` if `FLOOR_TIER` recall is below `RECALL_FLOOR`. `build_signals.ingest(root,
assert_floor=True)` calls it **from inside** the same `with gdb.session_scope() as sess:` block that does
the full drop-and-rebuild re-ingest — so a violation aborts *before* `session_scope`'s commit, and the
entire re-ingest (every record's re-tiered signals) rolls back atomically. This closes a real gap an
earlier draft of the flag had: checking the floor *after* the transaction committed only reported a
violation post-hoc, leaving the bad config's tiers already live in the DB (the working store every console
read hits). `--assert-floor` is off by default (a routine batch ingest isn't gated); a deliberate config
change should pass it.

**Helper functions** (`harness.py`): `floor_recall(scorecard)` reads the A+B recall from a harness
scorecard (tolerant of a malformed/legacy shape — returns `None`, never raises, since the tuning ledger
loads scorecards from arbitrary on-disk JSON); `floor_satisfied(scorecard, floor=None)` compares against
the canonical (or an explicit) floor; `assert_floor(con, floor=None)` is the actuation-point gate.

---

## 5c. The group-aware promotion gate + safe-promotion machinery (#212/#213, epic #209 Phase 2)

**The problem.** The recall floor (§5b) is a *hard, single-number* guard — it stops a re-ingest that drops
A+B recall below 0.98. It is necessary but not sufficient the moment config promotion becomes even
semi-automated: it can't tell a *real* improvement from a within-noise wiggle, and at n≈440 records over
~90 districts the clustering makes the naive test lie. The **design effect** DEFF = 1+(m̄−1)·ICC ≈ 2.4
(m̄≈4.9 targets/district, ICC~0.3) means a naive paired t-test understates variance ~2.4× — it manufactures
false wins. And a challenger can rarely be *proven better* at this n; the decision we can actually make is
**"provably not-worse within a pre-declared margin Δ."** So Phase 2 adds a real statistical gate + reversible
promotion machinery, both **advisory / dormant** now (nothing auto-promotes, nothing reads the champion
pointer to drive live scoring) — built with the automating feature per the #206 shift-left lesson. Decision
record: `production-quality-control-research/FINDINGS-AND-DECISIONS.md` §2.

**Proven libraries, zero unverified estimators (Ian, 2026-07-10; ICC exception documented below).**
Statistical math is the wrong thing to hand-roll — `statsmodels` (TOST `ttost_paired`, McNemar exact),
`scipy` (Wilcoxon, the seeded cluster bootstrap), `sklearn` (LOGO folds). The only arithmetic written is the
DEFF *definition*, per-district precision/recall, and — the one exception, forced by the PR #220 review —
**ICC(1)** as the textbook one-way random-effects ANOVA estimator with the unbalanced-cluster `k0`
correction: `pingouin.intraclass_corr` was tried first and REJECTED for this input, because its long→wide
pivot + `nan_policy="omit"` **listwise-deletes every district shorter than the largest one** (verified
empirically: sizes [5,5,5,4,4] silently computed the ICC from 3 of 5 districts while the report's metadata
claimed all 5), and our corpus is unbalanced by construction (m̄≈4.9). The estimator is **anchored to
pingouin as the test oracle**: on balanced data (where k0 = n and the two formulas coincide) a regression
test requires machine-exact agreement with `ICC(1,1)`. The **Nadeau–Bengio corrected-t was dropped** — no
canonical Python impl, and LOGO-CV's disjoint eval folds make the CV-overlap correction unnecessary
(Wilcoxon + the cluster bootstrap cover it). This same pandas+statsmodels+pingouin stack is what the
eventual cross-dimensional LCT-by-district/state analysis will stand on.

**The gate — `promotion_gate.py` (#212), pure + tested.** Consumes the same per-district re-score the
frontier grid uses (`frontier._retier` → `[(district, rec_key, tier, is_target)]`; no re-ingest, no cash).
`promotion_verdict(champion_rows, challenger_rows, *, margin, ...)` runs the layered gate (FINDINGS §2 order):
**(1)** a LOGO fold guard — no single held-out district degrades more than `fold_margin` (default 2·Δ);
**(2)** Wilcoxon signed-rank on the per-district deltas + McNemar exact on the send/suppress decision-flip
concordance (reported); **(3)** a cluster ("cases") bootstrap over the per-district deltas → the
cluster-honest one-sided lower bound; **(4)** TOST parametric corroboration; **(5)** ICC + DEFF beside every
verdict. `promote` = the LOGO guard holds AND the bootstrap lower bound > −Δ. The gated metric is **A+B
recall** (the harm direction — the same thing §5b's floor defends); **tier-A precision** is the reported
*benefit*. `margin` (Δ) is **required** — the verdict raises without a positive, pre-declared margin (set Δ
on domain grounds *before* seeing the challenger; a non-significant p-value is insufficient power, never
evidence of equivalence). Wired advisory into `frontier gate()` + `frontier --gate --margin Δ [--challenger
'<json>']`, and recorded into a `tuning_ledger` episode's new `promotion_gate` block (`verdict_summary`).

**The machinery — `config_artifact.py` + `promotion_pointers.py` + `promotion_flow.py` (#213), dormant.**
- **`config_artifact.py`** closes a real gap: `detectors.DEFAULT_DETECTOR_PARAMS` is a Python constant
  `harness.fingerprints` never hashes, so a detector-param change doesn't move the config fingerprint — two
  materially different configs can share one. An **artifact** is a self-contained immutable JSON capturing the
  WHOLE tunable surface (detector params INLINE + a snapshot of every `CONFIG_DIR` knob doc) + the GT version
  it was validated against, content-addressed by a `version` fingerprint that finally *includes* the detector
  params. `classify_change` → patch/minor/major sets the validation burden (`requires_full_gate`: patch =
  cheap gates only; minor/major = the full #212 battery); `verify_on_load` is the refuse-to-run guard
  (fingerprint or GT mismatch → raise — the COUNCIL_LAB §5a twin).
- **`promotion_pointers.py`** — promotion/rollback as **pointer swaps over immutable artifacts**. Storage split
  (the 2026-07-10 decision): artifacts as git files under `CONFIG_DIR/promotion/artifacts/<version>.json`;
  pointer STATE as a governance-DB singleton row (`ConfigPointer`) so a swap is one atomic upsert. A pure
  state-machine (`initial_state`/`set_challenger`/`promote`/`rollback`/`evictable`/`prune`/`active_versions`)
  with **N-cycle retention**: a demoted champion is retained as `@fallback`, `evictable` only *reports*
  past-window versions, `prune` is the sole deletion path — a prior artifact is **never deleted inside its
  window**, so rollback stays exact and cheap.
- **`promotion_flow.py`** composes them: `shadow_evaluate` classifies the change and runs the
  level-appropriate shadow — **patch** → the cheap in-memory #212 gate (valid: only detector params moved);
  **minor/major** → routed to a deferred **full re-ingest shadow** (knob docs are baked into the stored
  signals at ingest, so an in-memory re-score would silently use the champion's knobs — the flow refuses to
  fake it). `actuate` freezes both artifacts + atomically swaps the champion pointer *only* on a promote,
  with GT + staleness guards. `record_episode` writes the ledger episode carrying the verdict.

**Dormant boundary (remember to activate — #219).** Nothing loads the champion pointer to drive live scoring;
the pipeline still reads `CONFIG_DIR` directly. Actuation (pointer-drives-live-config) is gated on the unbuilt
gate-mode persistence, tracked with every other dormant guardrail in the **guardrail-activation checklist
(#219)**. The minor/major re-ingest shadow is likewise deferred (knob changes are human-curated + rare; the
automated tuning path is detector-params). Authority: this section; `PIPELINE_GOVERNANCE_AND_STATE.md`
§11b; issues #212/#213/#219.

**Review-hardened (PR #220's max-effort round, 2026-07-10 — 11 findings, all fixed).** The highest-severity:
**(1)** the ICC listwise-deletion bug above (pingouin → the anchored ANOVA estimator); **(2)** the CLI's
default `--gate` challenger could be an **infeasible** grid config when nothing cleared the recall floor
(grid_search falls back to the full infeasible list) — `default_challenger()` now refuses, never gating
against a floor-violating config by default. **`actuate`'s guard chain was rebuilt:** it now actually calls
`verify_on_load` on both artifacts (the fingerprint-tamper check the docstring had only *named*), refuses a
decision whose recorded champion/challenger versions don't match the pair being actuated (a stale verdict
must never promote a different pair), enforces `challenger.semver == bump_semver(champion.semver,
classify_change(...))` (the semver audit trail can't diverge from the content classification), and runs the
staleness check **before** any disk write (a rejected promotion leaves no orphaned artifact files). Also:
`alpha` is now actually threaded through `frontier.gate`/`shadow_evaluate`/`--alpha` (it was accepted and
silently dropped); a **gt_version-only diff classifies `none`, not `patch`** (it previously fell through the
version-inequality shortcut and could route a cross-GT pair into the cheap gate — `shadow_evaluate` also
gained an explicit up-front GT guard returning `shadow="gt_mismatch"`); `active_versions` uses `is not None`
(the issue-#63 discipline — it is the never-delete set); the `config_pointer` singleton is **DB-enforced**
(`CHECK (id = 1)` on the model + an idempotent `_PRECIOUS_ALTERS` entry); and `_h`/`_r` now delegate to
`harness`'s single copies instead of carrying clones that could drift.

---

## 5d. Every measured-pass evaluates against the exploration cohort (#214, built 2026-07-12)

**The hole this closes (FINDINGS §0 — the single highest-value finding).** Our measured-pass discipline and
the #108 facet-scoring measured-pass evaluate before/after **only on the approved/labeled set** — which is
*structurally blind to recall collapse*. Under a **deterministic** filter (Swaminathan & Joachims:
counterfactual correction is provably impossible even with infinite data), the wrongly-rejected docs never
enter the measurement, so a tuning pass can certify a **regression as a win** — approved-set precision rises
at the exact moment true-population recall falls (the "illusion of improvement"). More labels can't fix it;
only the injected stochasticity of the reject audit (§5a) can. So a cross-cutting rule falls out: **every
scoring measured-pass must ALSO report Rejection-Quality/TNR on the exploration cohort** (the pruned tail),
or the discipline itself blesses the illusion.

**As built.** One pure instrument, threaded through all three measured-pass surfaces:
- **`harness.exploration_cohort(rows)`** — pure over `(rec_key, tier, is_target)`: takes the tier-D
  sub-cohort, draws the SAME reproducible+growth-stable audit sample the live quota uses
  (`exploration_audit.select_audit_sample`), and reports `rejection_quality` (TNR + the rule-of-three
  ceiling). Config-relative: pass the live tiers for the scorecard, or a candidate's re-tiered rows for a
  measured-pass — the cohort is always that config's OWN pruned tail. Added as a **new scorecard section**
  (`build_scorecard`→`exploration_cohort`) + a `print_summary` line.
- **`frontier.reject_cohort_quality(records, params)`** — the candidate-config twin (in-memory `_retier`,
  no re-ingest/cash); every grid result carries `reject_quality`, and `frontier --gate` prints the
  champion→challenger reject-quality with a **⚠ REGRESSED** warning (a challenger that lifts tier-A
  precision by suppressing more real targets shows a lower reject-quality here — caught).
- **`tuning_ledger`** — a `reject_cohort_quality` metric getter (diffed like every other metric) + an
  advisory `constraint.reject_quality_regressed` flag, so a tail regression is **self-incriminating in the
  episode** even when the approved-set deltas look like a win. A missing section (legacy scorecard) reads
  as `None`, never as a pass.

**Retroactive #108 re-verification (the issue's explicit ask).** #108's facet-scoring measured pass
(tier-A precision 0.8382→0.8444) was measured on the approved set only. Re-checked against the exploration
cohort under the live config: **reject-quality/TNR = 1.0** (zero false negatives in the audited reject
sample, rule-of-three ceiling FN-rate <~11% @95%) — the approved-set win does **not** hide a pruned-tail
recall collapse. Confirmed clean. (Note two internally-consistent denominators: the harness scorecard
counts all labeled tier-D records incl. cluster members; frontier counts canonical reps only — each
before/after comparison is like-with-like.) Enforcement is advisory here (the hard gate is the live quota's
demote-hook, §5a); this is the *measurement* fix — the discipline can no longer bless a regression.

---

## 6. Upstream capture — iframe/embed detection (REQ-115)

Two V2 findings are structural, not heuristic, and best fixed at **Stage 3** (`capture_discovery.mjs`):
the `embedded_feed` pollution and the embedded-calendar cluster are usually an `<iframe>`/`<embed>` or a
JS-hydrated widget pointing at a known third-party host. **Stage 3 records `iframe_srcs[]` (categorized:
social/feed · calendar · doc-viewer · other) + `embed_present`** alongside the existing fingerprint —
cheap, additive, doesn't touch any capture path. This gives §3's `embed_hosts` signal a **structural,
vendor-agnostic** basis, far more robust than the URL-pattern/keyword guess.

**Capture-completeness question — ANSWERED (REQ-115).** The capture reads `document.body.innerText` of the
**top document only** — `innerText` does not recurse into iframe documents (and cross-origin frames are
browser-blocked outright), so a schedule rendered *inside* an iframe is absent from `page.txt`. **But it is
NOT silently lost:** the visual path (full-page screenshot → raster → `tesseract` OCR) renders iframe content,
so an iframe-embedded schedule is recoverable via the vision/OCR tier — consistent with tier-3 reader routing.
So this is left as-is (traversing frames adds complexity + hits cross-origin limits; the vision backstop already
covers it); the new `embed_present`/`embed_hosts` signal *flags* such pages so routing can prefer the visual rep.

**Deliberately NOT chased (research-settled, `filtering-research/`):** schema.org / `OpeningHoursSpecification`
microdata as a primary signal — both research passes converged on **<5% coverage on K-12 CMS platforms**
(no vendor auto-emits it), so it's cheap to detect opportunistically but not worth designing around. The
existing plain-text footer capture is already sufficient for the heading-proximity technique (§3).

---

## 7. Retained & still-authoritative (condensed — unchanged by V2)

- **Topology** — two values kept separate: `guessed_topology` (from `roster_school_names_hit`, noisy, kept
  to measure the heuristic) vs. `labeled_topology` (from human labels + the NCES school count — the truth
  for Stage 7). Formal set: `single_school` / `per_school` / `district_hub` / `mixed` / `incomplete_coverage`
  / `none_found` / `unknown`, with the derivation precedence + the narrow `incomplete_coverage` rule in
  `derive_labeled_topology()`. **NCES count is the authority, never "what capture yielded"** (Stage 1 caps
  the sample). Completeness (both bell-ends for every band) is a separate orthogonal dimension, not a topology value.
- **Near-duplicate clustering** — content-similarity (word-3-shingle Jaccard, `CLUSTER_THRESHOLD=0.90`,
  conservative on purpose), connected-components within a district; label the representative → cascades to
  unsplit members; **`cluster_split`** is a durable human override (precious, JSON-backed, re-applied before
  re-clustering). The operational filter sends the cluster *representative* only.
- **Funnel ingredients** — the NCES denominator (our-criteria `ccd_sch` schools by raw `LEVEL`, captured at
  Stage 1) + `candidates.json` provenance (`intended_schools`, `candidate_tools`, `is_emergent`).
- **Attention model (REQ-112)** — the district-driven console spine: attention = the *inverse* of
  automatable-confidence ("where my judgment moves us forward", NOT target-likelihood; clean tier-A = LOW),
  `{score, reasons[]}` per record rolled up per district, config-as-data + frontier-compatible. **V2 makes
  the `review` bucket the attention queue**, and the attention reasons largely become detector outputs.
- **The DB is the working store; JSON files are receipts** (governance §1). Precious human data
  (`label` / `cluster_split` / `followup_flag`) is never dropped on re-ingest, keyed on stable `rec_key`,
  and JSON-backed. Signal tables are drop+rebuilt (full `ingest()`) or per-district DELETE+INSERT (`ingest_batch()`).

---

## 8. Status

| piece | status |
|---|---|
| De-chrome, clustering, topology, funnel, attention, harness/tuning_ledger | **BUILT** (pre-V2) |
| V1 tiering (`tier_and_category`, `DEFAULT_TIER_PARAMS`) | **DELETED 2026-07-02** — fully superseded by the combiner; grimp-verified zero callers before removal |
| V2 detectors + combiner (`detectors.py`/`combiner.py`); the 3 fixes; new signals (footer/heading/table-density/cms_hint) | **BUILT (REQ-113)** |
| Per-detector harness diagnostics (coverage/accuracy/overlap/conflict) | **BUILT (REQ-113)** |
| `frontier.py` re-pointed at the V2 combiner path (`DEFAULT_DETECTOR_PARAMS`) | **BUILT 2026-07-02** |
| **v2.1 three-axis labeling** (target shapes + confounder facets + location) + label migration + text-first detail pane | **BUILT (REQ-114)** |
| flags→facets convergence (release descent reads `facets_json`; `flags_json` an inert archive) | **BUILT 2026-07-02** |
| `migrate_labels_v21` re-run guard (refuses a second real run without `force=True`) | **BUILT 2026-07-02** |
| Harvest slices relocated out of `data/raw/` to `data/acquisition/harvest_slices/` (read-fallback to legacy location) | **BUILT 2026-07-02** |
| Stage-3 iframe/embed capture + `cms_hint` promotion + iframe-innerText check | **BUILT (REQ-115)** |
| **Facet-level per-detector scoring** (negative detectors vs. their Axis-2 confounder facets — `harness.DETECTOR_FACET` + `facet_detector_diagnostics`, scored over the 339/667 labels that carry facets) | **BUILT (#108, 2026-07-09)** — surfaced low confounder-precision the coarse target-accuracy hid (office_hours 0.18, sports 0.13 — provisional; nonstandard_day 0.17 — FROZEN, its facet has no live checkbox, tracked #207) |
| **`lf_footer_hours` footer/header evaluated independently** (an office footer no longer downgrades a school header) | **BUILT (#61, 2026-07-09)** — a bug guard; 0 current-corpus triggers, no metric change |
| **`lf_nonstandard_day` soft-gate** (an incidental prose-pair + a weather/remote/delay soft negative → review, not auto-send; structural targets still send) | **BUILT (#60, 2026-07-09)** — measured pass: tier-A precision 0.8382→0.8444, tier-A + A+B recall held (0.8906 / 0.9961); 6 pages routed to review, 72 structural preserved |
| **Canonical recall floor** (`harness.RECALL_FLOOR=0.98`/`FLOOR_TIER="A+B"`, `floor_recall`/`floor_satisfied`/`assert_floor`) — one source of truth replacing frontier's/the ledger's prior inconsistent 0.97/0.98-on-tier-A floors | **BUILT (#208, 2026-07-10)** — **enforced INSIDE `build_signals.ingest()`'s transaction** via `--assert-floor`: a violation raises and rolls back the *whole* re-ingest (not a post-hoc report) — see §5b |
| **Anti-survivorship exploration quota** (`exploration_audit.py` pure core + `exploration_live.py` live wiring — rule-of-three sufficiency count, deadband, demote-not-halt) | **BUILT + tested (REQ-120/#211): pure core 2026-07-10, live wiring 2026-07-12** — reject-population query, randomized draw/coverage meter, gate@5 demote-hook wired into `save_label` + `GET /api/exploration-audit` Settings meter. Enforcement DORMANT (gate@5 configured manual). See §5a |
| **Group-aware non-inferiority promotion gate** (`promotion_gate.py` — LOGO guard + cluster bootstrap + TOST + ICC/DEFF; proven libs, no hand-rolled stats) wired advisory into `frontier gate()`/`--gate` + the `tuning_ledger` episode | **BUILT + tested (#212, epic #209 Phase 2, 2026-07-10)** — advisory; `margin` (Δ) required; see §5c |
| **Safe-promotion machinery** (`config_artifact.py` immutable fingerprinted artifact — closes the unhashed-detector-params gap; `promotion_pointers.py` @champion/@fallback swap + N-cycle retention; `promotion_flow.py` shadow→gate→swap→record) | **BUILT + tested (#213, epic #209 Phase 2, 2026-07-10)** — DORMANT (nothing reads the champion pointer live; minor/major re-ingest shadow deferred); activation tracked #219 — see §5c |
| **Reset labels** (`POST /api/reset-labels` + `build_signals.reset_labels_bulk`, record/district scope, reverses the cluster cascade, no calibration row) | **BUILT (#228, 2026-07-11)** — see §4 |
| **Empty-domain admission guard** (`common/discover.py` `domain_of()`/`is_scoping_domain()`, refuses blank/junk-domain districts at Stage-1 batch build) | **BUILT (#229, 2026-07-11)** — see §4 |
| **Millard contamination remediation** (`process_governance/remediate_contamination.py`, manifest-first dry-run-by-default cleanup tool) | **BUILT (#227, 2026-07-11)** — see §4 |
| **Stage-7/8 outcome feedback** (`harness.extract_outcome_calibration` — P(any_accepted) headline + per-tier calibration + detectors-vs-outcome + the two disagreement cells + `unjoined`; fourth `outcome` fingerprint; `extract_outcome_calibration` ledger delta) | **BUILT (#91, 2026-07-14)** — measurement only; see §5 item 2 |
| Learned `LabelModel` combiner · hierarchical/vendor pooling · online-FDR drift | **DEFERRED (scale endgame)** |

---

## Change log

- **2026-07-16 — §3a obs. 6: the stale-veto projection REFUTED by measurement; obs. 5's stale bullet marked
  superseded.** Building #241 surfaced that its enabling signal (`content_school_year`, §3G) does not exist.
  A throwaway URL-year extractor measured what the veto would actually do on the 473 labeled tier-A records:
  at the recency floor (2023-24+) it removes **1** false-send while vetoing **17** real targets and *raises*
  the false-send rate 24.1%→24.8% — staleness and target-absence are near-independent, because a stale
  handbook usually still contains a real schedule. At Ian's actual floor (pre-2017-18, the CRDC federal-input
  baseline) the rule is correct but pays **0** — 4 tier-A hits, all real targets, no false-sends — so it is a
  REQ-026 correctness guarantee, not a cost lever. Decisions (Ian): pre-2017-18 = **hold**, not hard-reject
  (reversible; preserves districts whose only evidence is old); **#241** = that validity floor, **#107** stays
  the parent (shared signal + prefer-recent ranking, which is the half that saves money). Consequence:
  **#515's "24.5%→15% money lever" headline is wrong** (stale contributes 0 of it) and it is no longer the
  resume point; the measured money lever is **#519**. Full tables, the human-note evidence, and the extractor
  caveats (URL-decode first, guard GUIDs/asset-ids, an upload path is not a vintage) in §3a obs. 6.

- **2026-07-11 (later) — #228 "Reset labels" shipped, alongside #229/#227 (commit 7655277, PR #242).**
  `POST /api/reset-labels` + the shared `build_signals.reset_labels_bulk` helper now let a record or
  whole district return to `unlabeled` (see §4 for the design rationale and both console entry points).
  In the same commit: **#229** closes the empty-domain contamination chain at its source — Stage-1 batch
  admission now hard-refuses a district with a blank/junk NCES domain via `common/discover.py`'s new
  `domain_of()`/`is_scoping_domain()` guards, rather than letting it reach Stage 2's unscoped branch; and
  **#227** (the Millard Public Schools, NE cross-district contamination that motivated #228) has a
  dedicated remediation tool, `process_governance/remediate_contamination.py` — manifest-first,
  dry-run-by-default, reusing `reset_labels_bulk` for the label side of the cleanup. All three tested
  (`tests/test_stage5_facets_api.py`, `tests/test_remediate_contamination.py`, `tests/test_domain_guard.py`).

- **2026-07-11 — three findings logged from the batch_00013 live shakedown (#122's second pass), still
  open.** Found by the human at gate@5 while labeling in parallel with the shakedown, not by a
  planned review:
  - **#223 — "Summer School" has no Axis-2 confounder checkbox/negative detector**, so a summer-program
    page (e.g. a district's `students-families/summer-school.cfm`) has nowhere honest to be labeled.
  - **#224 — 0-link districts sort to the top of "Needs Attention" even with "Hide Resolved" on**
    (Denton Elem MT, East Chicago Urban Enterprise Academy IN) — a district with nothing left to
    evaluate shouldn't compete for attention against districts that do.
  - **#226 — "feed"/"live-feed" in a URL is not yet a negative scoring signal**, though it correlates
    with the news/social-feed confounder that already has a detector for other shapes.

- **2026-07-10 — PR #220 max-effort review round: 11 findings, all fixed — see §5c "Review-hardened".**
  Headline: pingouin's ICC silently listwise-deletes unbalanced districts (replaced with the
  pingouin-anchored ANOVA ICC(1) estimator); the CLI's default gate challenger could be an infeasible
  (recall-floor-violating) grid config; `actuate` now runs the real `verify_on_load`, binds the decision to
  its exact artifact pair, enforces semver-vs-classification, and checks staleness before any disk write.
  Plus: alpha threading, gt-only classify fix, `active_versions` is-not-None, the DB-enforced
  `config_pointer` singleton CHECK, and `_h`/`_r` deduplication. +12 tests.
- **2026-07-10 — Runtime guardrail Phase 2 (#212/#213), epic #209 — see §5c for the built detail.** The
  group-aware non-inferiority promotion gate (`promotion_gate.py`) + the safe-promotion machinery
  (`config_artifact.py` / `promotion_pointers.py` / `promotion_flow.py`), built + tested, ADVISORY/DORMANT.
  The gate replaces the naive paired t-test (invalid at DEFF≈2.4) with LOGO-CV + a cluster bootstrap + TOST
  non-inferiority against a pre-declared Δ, ICC/DEFF reported — proven libraries (statsmodels/pingouin/scipy/
  sklearn), zero hand-rolled estimators (Ian's redirect; Nadeau–Bengio dropped as unnecessary under LOGO).
  The machinery closes the unhashed-detector-params gap (an immutable, fingerprinted, GT-verified artifact)
  and makes promotion/rollback atomic pointer swaps with N-cycle fallback retention. Added deps:
  statsmodels + pingouin (the same stack the future cross-dimensional LCT analysis needs). Nothing reads the
  champion pointer to drive live scoring yet; activation tracked in the guardrail-activation checklist (#219).
- **2026-07-10 — Runtime guardrail Phase 0/1 groundwork (#208/#211/#210), epic #209.** Three pieces, all
  documentation refresh only here (see §5a/§5b for the built detail): (1) the canonical recall floor
  (`harness.RECALL_FLOOR`/`FLOOR_TIER`) now enforced INSIDE `build_signals.ingest()`'s transaction via
  `--assert-floor` — a violation rolls back the whole re-ingest, not a post-hoc report; (2) the
  anti-survivorship exploration quota's pure control-law core (`exploration_audit.py`) built + tested,
  hardened through a review round (deadband/mode-string validation, complementary rounding, the codebase's
  own `random.Random(seed)` sampling pattern) — live wiring still deferred; (3) the gate-decision
  calibration log (`common/calibration.py` + `process_governance/gate_calibration.py`) now WIRED LIVE at
  gate@5 (`save_label`) — see §4 — logging a shadow-mode row per confident label, the corpus accruing
  forward from every gate action.
- **2026-07-09 — Batch 6 detector/combiner hygiene + facet-level scoring (#60/#61/#108), a measured pass.**
  Three interrelated Stage-5 scoring items, shipped through the harness discipline (before→after re-ingest,
  recorded in `tuning_ledger`). **#108 (facet-level per-detector scoring):** the harness now scores each
  NEGATIVE detector against its Axis-2 *confounder facet* (`DETECTOR_FACET` map + `facet_detector_diagnostics`),
  not just the coarse "fired on a non-target" accuracy — a page can be a target AND carry a confounder
  (Las Cruces), so the coarse metric conflates confounder-ID error with target co-occurrence. Scored over the
  339/667 labels that carry facets; immediately surfaced low confounder-precision the coarse view hid
  (`lf_office_hours` 0.18, `lf_sports` 0.13 — provisional, a lower bound as facets under-accrue;
  `lf_nonstandard_day` 0.17 — **frozen, not provisional**: its `other_schedule` facet has no live checkbox
  in the v2.1 questionnaire, so its denominator is stuck at the one-time-migration rows until a
  nonstandard-day checkbox is added — tracked: #207). `lf_no_times` is deliberately unmapped (a suppress
  floor claims *absence* of signal, not a confounder shape). **#61 (`lf_footer_hours`):** the footer and header segments are now evaluated INDEPENDENTLY —
  the old code OR-ed the two `office` flags, so an office-hours footer downgraded a genuine school-hours header
  to the office negative. A real logic bug; **0 current-corpus triggers** (no page presently has both segments
  hit with differing office flags), so it's a guard locked by a unit test, no metric change. **#60
  (`lf_nonstandard_day`):** an incidental prose start/end pair + a weather/remote/delay soft negative now routes
  to **review** instead of auto-sending tier-A (the extraction prompt's "ignore early-dismissal" was the only
  backstop); STRUCTURAL targets (footer block / table / explicit minutes) still auto-send — structure is the
  standard day even amid delay language. **Measured:** tier-A precision **0.8382→0.8444** (2 fewer labeled
  false-positives in auto-send), tier-A recall **held 0.8906** (no target dropped), A+B recall **held 0.9961**
  (the true reaches-review floor); 6 pages moved to review, 72 nonstandard-day+structural preserved. See §3
  detector table, §5, §8.
- **2026-07-01 (later) — flags→facets convergence completed (fable review findings 2.1/2.2/2.3).**
  The v2.0 `flags_json` column is now an **inert archive**: no live reads or writes anywhere. The
  label save (`server.UPSERT_LABEL`) no longer touches it (it had been wiping historical flags to
  `[]` on every v2.1 save — the UI posts no `flags` key); the release descent
  (`release.load_district_records`/`decide`/`best_send`) reads **`facets_json`**, with the human
  **`needs_vision == "yes"`** facet driving image routing (was the `target_image_only` flag); the
  label-set fingerprints (harness + `release.district_fingerprints`) hash `facets_json`. The human
  **`duplicate` flag is retired without a successor** — programmatic dedup (`record.duplicate_of`
  exact-hash + near-dup clustering with `cluster_split`) owns duplicates; the 9 legacy `duplicate`
  flags remain readable in the DB column and `labels.json` git history. Also: `ingest_batch` now
  runs `import_labels` before `export_labels` (mirroring `ingest()`), so an incremental ingest on a
  fresh/wiped DB can never truncate the precious `labels.json` backup.
- **2026-07-01 — v2.1 labeling (REQ-114).** The label became a **three-axis object** (§4): target SHAPE
  (7 shapes + `target_absent`/`unusable`) · confounder facets (multi) · location facets (buried+page-range,
  needs-vision, where). `migrate_label_v21` moved all 440 labels (128 targets preserved; git = restore point).
  Detail pane reordered **text-first** with a per-rep unique-times readout. Tier/decision logic unchanged
  (tier-A precision/recall held 0.794/0.875, tier-D 0 targets); category-guess rose 0.32→0.49 (combiner
  `target_absent` aligns with the migrated primaries). Stage 6 verified clean (everything reads `TARGET_LABELS`
  dynamically; candidates/preview/verified-only all work on the migrated labels — grimp-confirmed blast radius).
- **2026-07-01 — V2 (REQ-113/114/115).** Clean rewrite. Cascade → labeling-functions + combiner; the three
  measured V1 defects fixed (de-chrome max-evidence time signal; tier-B proximity requirement; suppress
  floor = no in-window times); new deterministic signals (footer/header times, heading-adjacent hours,
  table time-density, `cms_hint` promotion, `embed_hosts`); facet-questionnaire labeling; per-detector
  harness diagnostics; Stage-3 iframe/embed capture. Grounded in `filtering-research/` (weak supervision;
  K-12 hours markup is near-absent → don't design around schema.org). Prior June 24–29 build history in git.
- **Pre-V2** (June 24–29, in git): the CP-B review app + deterministic signals; de-chrome measured win
  (category 0.43→0.60, topology 0.6→0.8); tiers A–D; clustering + durable splits; handbook harvest;
  funnel ingredients; the learning-loop infra (config-as-data + harness + ledger + frontier); the
  district-driven attention-first console rework (REQ-112).
- **2026-07-02 — frontier re-pointed at V2; V1 tier_and_category deleted; migration re-run guard; harvest
  slices relocated (fable review issues #56, #59, #58).** `frontier.py` was still grid-searching the
  deleted-in-spirit V1 cascade (`tier_and_category`) even though the live scoring path had moved to the
  combiner months earlier — no tuning had been run against it since, so nothing was silently mistuned, but
  the tool itself pointed at dead code. Re-pointed at `combiner.score_record` over
  `detectors.DEFAULT_DETECTOR_PARAMS`, same LOGO-CV harness; `tier_and_category`/`DEFAULT_TIER_PARAMS` then
  had zero remaining callers (grimp-verified) and were deleted outright rather than left as an unused
  landmine. `migrate_labels_v21`'s real-run mode now refuses a second run (any label already in the v2.1
  vocabulary with non-empty facets) unless `force=True` is passed with a loud warning — closes the risk of
  silently re-folding a legacy flag over a human's newer facet edit. `harvest_slice.txt` materialization
  moved from inside `data/raw/` (a write-once-in-spirit directory) to `data/acquisition/harvest_slices/`,
  with a read-fallback to the legacy location so already-materialized slices keep working without a
  re-ingest.
