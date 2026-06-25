# Stage 5 (Local Filtering) — Design & Data-Collection Plan (2026-06-24)

> Working design note for Stage 5 of the acquisition pipeline. Captures the decisions made
> in the opening Stage 5 design conversation. Status: **data-collection review app BUILT
> 2026-06-24** (`infrastructure/acquisition/stage5_filter/review_app/`, see its README) and run
> against the real 12 `batch_00001` districts; human labeling not yet started; the operational
> Stage 5 filter itself is still to be defined *from* the labels this app collects. Companion to
> `docs/ACQUISITION_PIPELINE.md` (Stage 5 stub) and `docs/diagrams/acquisition_pipeline_flow.md`.
> When the filters are defined, fold the durable parts into `ACQUISITION_PIPELINE.md`'s Stage 5 section.

---

## Purpose

Stage 5 sits between Stage 4 (Local processing — produced a pile of text/image representations
per captured URL) and Stage 6/7 (the paid OpenRouter extraction council). Its job:

1. **Cut Stage 7 cost** by not sending the council files that almost certainly don't contain a
   bell schedule, school start/end declaration, or explicit daily-instructional-time statement.
2. **Hypothesize district topology** (single district-level *hub* page vs. a set of *per-school*
   pages vs. some other configuration) to inform Stage 7.
3. **Deduplicate** so each resource sent to the council is unique (e.g. Stage 2 emergent URLs
   that resolved to the same downloadable file — confirmed real on Marion ISD).
4. Produce a **`filtered.json`** (operational) for human review at **Checkpoint B** before
   anything reaches Stages 6/7.
5. Give the CP-B reviewer an **optional** mechanism to record whether a recommended record
   actually contains the target information.
6. **Generate data** that improves both the inputs and the coarse filtering at earlier stages.

## The binding constraint (non-negotiable)

**The filtering/sorting at runtime is script-driven and deterministic — NO subscription- or
API-based AI in the Stage 5 filter itself.** The only paid AI in the pipeline are the Claude Haiku subagents executing Claude WebSearch in Stage 2 and the Stage 7
extraction council. When Claude (the agent) examines captured text/image files during this design
exercise, it does so **strictly to reverse-engineer deterministic signals** for the scripts —
never as the runtime classifier, and never as a substitute for the human's labels. Division of
labor: **the scripts classify/tier; the human supplies ground-truth labels; the agent only
builds the deterministic rules.** (Consistent with the standing rule that the human curates the
ground truth — see memory `feedback-human-curates-ground-truth`.)

## This exercise vs. the operational stage

This is a **process-building / training exercise** to collect labeled data that *defines* the
deterministic filters. The data-collection artifact built here is **deliberately decoupled from
the eventual operational `filtered.json` schema** — its purpose is to generate information, not
to be the production output. Learnings flow into the operational Stage 5 design later. It is
therefore **premature to apply any filter that isn't yet defined by this process**: the
exercise artifact includes **every** record that has a `processed.json` entry — nothing is
removed, only *tiered* and *hypothesized*.

---

## Label taxonomy (human ground-truth labels)

Two axes. A record gets **one primary label** (its dominant content) plus optional **flags**.

### Primary label — "target present, by shape"
| Label | Definition |
|---|---|
| `school_bell_schedule` | A table or list that breaks the school day into periods. |
| `school_start_end_prose` | One or more sentences declaring the start and end time of the school day. |
| `district_hub_schedule` | A table/list defining start & end times for each school in a district, or each grade band. |
| `explicit_instructional_time` | A declaration to the effect of "Students receive XXX minutes of instruction every day." |
| `nonstandard_format` | Contains bell-schedule / instructional-time info in a shape we haven't enumerated. |

### Primary label — "non-target, by reason"
| Label | Definition |
|---|---|
| `board_schedule` | Scheduling/agenda info for the School Board / Board of Trustees. |
| `sports_schedule` | Scheduling for athletics/sports teams. |
| `academic_calendar` | A school/district calendar (year, holidays, early-release days) — time-bearing but not a schedule. **Common confusable, added 2026-06-24.** |
| `transportation_schedule` | Bus/transport times. **Tricky boundary** — "pick-up 7:15 / drop-off 2:30" mimics legitimate `school_start_end_prose`; labeled separately to measure the confusion. Added 2026-06-24. |
| `other_schedule` | Scheduling for some other school activity (extracurriculars, performing arts, community meetings, …) — the residual non-target bucket. |
| `none` | No discernible schedule or instructional-time info. |
| `unusable` | Garbled, effectively empty, or otherwise impossible for a human to interpret. |

### Flags (optional, orthogonal to the primary label)
| Flag | Meaning |
|---|---|
| `duplicate` | Byte-identical content to another record; `duplicate_of` references the canonical record. Labeled once on the canonical; duplicates inherit. |
| `buried_in_long_doc` | Target info is present but inside a multi-topic document (e.g. a student/parent handbook). See the handbook-harvesting open item below. |

**Naming note:** standardized on `district_hub_schedule` (the conversation also wrote
`district_hub_table` — same thing).

**Multi-label posture:** primary-label-plus-flags rather than "pick all that apply," because
the two-axis structure means a page is usually *either* a target-shape *or* a non-target-reason;
genuinely mixed pages (a handbook containing a bell schedule) are captured by the flag.

---

## Deterministic signals to compute (the script's raw material)

All computed with no AI, from Stage 4 text + the on-disk binaries. **Computed at PAGE
granularity for multi-page PDFs, not just per-record** (see handbook harvesting):

- `n_times` — count of `hh:mm (AM/PM)?` matches (already in `processed.json` per representation).
- `n_times_in_window` — times within the plausible school-day window (~07:00–16:00).
- `time_proximity_pairs` — ≥2 times within a small text window (handles both tables *and*
  prose like "starts at 8:00 … ends at 2:30"; a real upgrade over the old `relevance.py`'s flat
  `n_times >= 4`).
- `times_before_5pm` / `times_after_5pm` — a soft discriminator: all-after-5pm leans
  sports/board. (Note: never fires on the current 12 — everything is pre-5pm — so it's
  insurance for unseen districts, validated when it actually triggers.)
- `positive_kw` — bell / school hours / start time / dismissal / arrival / first bell /
  `period \d` / homeroom / "minutes per day" / "minutes of instruction" …
- `negative_kw` — board / trustees / agenda; athletic / sports / "vs." / tournament; calendar /
  holidays / early release; bus / transportation.
- **"minutes" overload caveat:** the `explicit_instructional_time` detector must anchor on
  "instructional/class minutes" or "minutes per day" — **bare "minutes" near board/agenda/meeting
  is a board-meeting-minutes false positive and should count *against*, not for.**
- `table_structure` — presence/size of a real table (from the camelot/pdfplumber Markdown reps);
  period-row tables suggest `school_bell_schedule`/`district_hub_schedule`.
- `roster_school_names_hit` — count of distinct targeted-roster school names appearing in the
  text (the **hub-vs-per-school topology signal**: many names on one page → hub candidate; one →
  per-school).
- `visual_text_gap` — **a PDF/image representation exists but its extracted text is thin/zero**
  → flag "inspect visually, possible missed content." Directly serves the goal of catching info
  that never made it into a text file.

---

## Two output axes (kept separate)

1. **Likelihood tier** (the sortable thing the script computes with real confidence):
   - **Tier A** — strong target candidate: a time-proximity pair in-window + positive keyword,
     low negative-keyword pressure.
   - **Tier B** — plausible: in-window times present, weaker keyword evidence.
   - **Tier C** — unlikely/negative-leaning: times present but board/sports/calendar/after-5pm
     dominant.
   - **Tier D** — drop-candidate: no times / unusable.
   *(Starting hypothesis — revised against the labels.)*
2. **Category hypothesis** (the script's weak first stab at the primary label, via
   keyword/structure heuristics): **noisy by design.** The human's corrections to it are the
   training signal. Never presented as a claim.

## Recall-bias stance (for the eventual operational filter)

Because a human reviews `filtered.json` at CP-B, the operational auto-filter will be
**recall-biased**: hard filters are *high-precision rejects only* (zero plausible times;
all-after-5pm; unambiguous board agenda); everything else flows through **scored and ranked**
for the human to confirm or cut. The expensive error is silently dropping a real schedule before
the human sees it; a borderline page reaching the human costs only review time. The score's
evidence (which times matched, which keywords, the split) is surfaced so the human audits fast.
**N.B. this stance governs the *operational* stage — the *data-collection exercise* applies no
filtering at all and surfaces everything.**

---

## The data-collection artifact

A local review/labeling tool, **not** the operational `filtered.json`.

**Requirements:**
- Lists **every** record with a `processed.json` entry across all districts — by district & URL,
  nothing filtered out.
- **Glossary + instructions at the top** (the label definitions, flag meanings, tier
  definitions) so the reviewer can refresh without leaving the tool.
- Per record: links/inline rendering to **all representations in the URL directory** — the
  extracted text reps *and* the binaries (`page.png`, `page.pdf`, `original.*`, `raster_p-*.png`).
  The reviewer must be able to spot info present in the PDF/image that never reached a text file.
- Shows the computed deterministic signals, the script's tier, and the category hypothesis.
- **Optional** human labeling: primary label + flags + free note, persisted. Not required.
- Duplicates shown-but-marked (`duplicate_of` with a link to the canonical), labeled once.
- Excludes incidental metadata that doesn't help judge content (e.g. `cms_hint`/fingerprint —
  not useful for "does this artifact contain the info we want").

**Architecture — DECIDED & BUILT 2026-06-24: SQLite + a thin local FastAPI review app**
(`infrastructure/acquisition/stage5_filter/review_app/`). SQLite is a single file that cannot
touch the production LCT DB, needs no container/port, and suits the tiny single-user dataset;
schema can migrate to Postgres later if scale demands. The DB cleanly separates **regenerable
script-computed signals** (districts/records/representations/signals tables — dropped + rebuilt
each ingest) from **precious hand-entered labels** (the `label` table — never dropped; labels key
on `district_id:hash` and survive re-ingest, verified). Styled with the user's **MMM Design
System** (claude.ai/design) tokens, vendored under the app's `static/tokens/`. UI confirmed
rendering correctly against the real 12 districts.

**Successive-batch + Checkpoint-B intent (user, 2026-06-24).** This app is explicitly intended for
use across **successive batches**, not just these 12 — and may well become the actual **CP-B**
review surface. The architecture supports this directly: the `captures/` directory accumulates all
districts across batches, each ingest rebuilds the full record set from disk grouped by `batch_id`,
and labels persist across re-ingests. Nothing here precludes the operational CP-B send/hold
decision being layered on later (the operational `filtered.json` stays decoupled per the exercise
vs. operational split above).

---

## Continuous-improvement loop (the point of all this)

```
script computes signals  →  human labels a sample (ground truth)
        →  measure which signals separate the labels (precision/recall per rule)
        →  define hard-filters + score weights from evidence (not guesses)
        →  re-tier; measure against held-out labels
        →  labels accumulate across batches; thresholds refine; feed back to
           Stage 2 (which queries/hosts yield schedule pages) and Stage 1 (which districts)
```

The DB is the durable store for this loop. Each record keeps its full raw signal vector so any
later rule can be evaluated retroactively over already-labeled data (same "refine over raw facts"
principle that paid off in the Stage 3 fingerprint → CMS_HOSTS loop).

## Topology hypothesis

Produced at the **district level** from the `roster_school_names_hit` signal (one multi-school
page → `hub`; ~one page per school → `per_school`; mixed/none → flag) plus the human labels once
available. Explicitly a **hypothesis for Stage 7**, not a fact. Marion ISD is a clean
`per_school` example to validate against (per-school `/o/<school>/page/school-hours` pages +
per-school bell PDFs). This is where the topology question Stage 2 deferred ("revisit once CP-B
capture results are in hand") finally gets answered.

---

## Open items / things still to decide or explore

1. ~~**DB-vs-Postgres architecture**~~ — **RESOLVED & BUILT 2026-06-24:** SQLite + thin FastAPI,
   labels-survive-reingest, batch-aware (see Architecture above). Topology remains the noisiest
   signal (CMS school-switcher nav pollutes `roster_school_names_hit`) — a refinement target for
   the labels, not blind tuning now.
2. **Handbook page-harvesting (promising — elevate, don't just flag).** Detect a student/parent
   handbook (`"handbook"` in URL/title/text + document length), then use the **per-page** signal
   scoring to harvest only the schedule-bearing page(s) rather than sending the whole (expensive)
   handbook to the council. We already rasterize per page and can `pdftotext` per page, so this
   is deterministic and reuses existing machinery; it also helps the known multi-page failures
   (Broward/Orange). **Build per-page signals into the exercise to test the harvest on real data;
   defer only if it doesn't pan out** (the user's standing call).
3. **`explicit_instructional_time` is rare** — the deterministic detector is high value but
   low frequency; we may find zero in these 12. A negative result is still data.
4. **`transportation_schedule` ↔ `school_start_end_prose` confusable** — measure how often bus
   times masquerade as school start/end; it shapes how aggressive the prose detector can be.
5. **Exact-hash dedup only** for now; fuzzy near-duplicate detection (the hub page captured under
   two URLs with slightly different text) deferred.

## Decisions locked in this conversation (2026-06-24)

- Label taxonomy above (two axes; primary + flags), incl. `academic_calendar` and
  `transportation_schedule`; `district_hub_schedule` naming standardized.
- Scripts/deterministic-only at runtime; agent examines files only to build heuristics; human
  owns the labels.
- Exercise artifact is decoupled from the operational `filtered.json`; includes everything (no
  filtering), tiered + category-hypothesized.
- Review tool must show ALL representations incl. binaries, with glossary/instructions at top.
- Per-page signal granularity (enables handbook harvesting + multi-page handling).
- Dedup: byte-identical, shown-but-marked, `duplicate_of` links to canonical, label once.
- Recall-bias + human-as-precision-backstop governs the operational filter (not this exercise).

---

# batch_00001 review — first full labeling pass (2026-06-24)

The user labeled **all 150 records** in the review app. Labels are the ground truth; the script's
tier + category guess are what we measure against. (Labels backed up to `labels.json`, committed.)

**Label distribution:** none 56 · school_bell_schedule 35 · board_schedule 23 · other_schedule 12 ·
unusable 10 · sports_schedule 5 · district_hub_schedule 3 · academic_calendar 3 ·
explicit_instructional_time 2 · school_start_end_prose 1. (Targets = 41 of 150.)

## Headline: the TIER works; the CATEGORY GUESS does not

| tier | targets | non-targets | precision |
|---|---|---|---|
| A | 40 | 7 | **85%** |
| B | 0 | 6 | 0% |
| C | 1 | 38 | 3% |
| D | 0 | 58 | 0% |

- **An "A → council" filter recalls 40/41 targets (98%) at 85% precision.** Tier D (58 records, 39%
  of the batch) contains **zero** targets — safe to drop, big cost win. **Tier B caught zero
  targets** (6 false) — the B definition is currently noise (it's catching building-hours red
  herrings + special-day schedules). The single target in C is an Urbana bell schedule ("in the
  Bell Schedule block").
- **The category hypothesis is wrong almost everywhere a real bell schedule exists** — it guessed
  `sports_schedule`/`board_schedule` on most true `school_bell_schedule` records (all of
  Stroudsburg, Urbana, ROY, HOPE, Marion, Pittsylvania handbooks). **Root cause: negative keywords
  (board/sports/athletic) live in the CMS nav + footer chrome present on *every* page**, so the
  "which negative class wins" logic fires on chrome, not content. **Positive signals (time
  proximity + positive keywords) are robust to chrome; negative-class disambiguation is not.** This
  is the same nav-chrome pollution that fools the topology hypothesis (roster-name count). **The
  single highest-leverage fix for Stage 5: strip nav/header/footer chrome before computing signals
  (or weight positive structure over mere negative-keyword presence).**

## By the standard per-batch learning questions

### 1 · Refinements to the CP-B application
- **Add `community_calendar`** as a non-target label (distinct from `academic_calendar` — community
  events; seen at Stroudsburg). *(user)*
- **Add a `building_hours_visible` flag** — a recurring red herring: "Building Hours 7:15a–3:15p" in
  footers (Urbana, Sojourner Truth) mimics a real start/end pair but is building-open hours, not the
  student day. Flag to monitor + eventually detect. *(user)*
- **Consider an `embedded_feed` flag** — several districts embed social-media/blog feeds that emit
  date/time stamps and confuse the signals (DUNSEITH "embedded social media feed" guessed sports;
  HOPE blog). *(user)*
- **Variant grouping** — Stroudsburg generated ~6 CMS URL variants per school the user had to label
  individually; a "related variants" grouping (by URL template) would cut review effort.

### 2 · Immediate scoring / earlier-stage updates
- **De-chrome the signals (Stage 5) — the big one.** Negative keywords from nav/footer must not
  drive categorization. Strip boilerplate (nav, header, footer, school-switcher) before scanning.
- **Detect instructional time in HOURS, not just minutes (Stage 5).** DUNSEITH buries gold in an
  academic calendar: "147 days × 7.5 hrs/day" (HS) and "× 7.25 hrs/day" (elem) → 450 / 435 min/day.
  Our `INSTRUCTIONAL_RE` only anchors on "minutes." Add hours patterns (and "hrs per day").
- **Do NOT hard-drop `academic_calendar`** — DUNSEITH proves a calendar can carry explicit
  instructional time. Calendars stay eligible; the instructional-time detector is what rescues them.
- **Add "class schedule" (and equivalents) to positive keywords (Stage 5)** — ROY titles its bell
  schedule "Class Schedule." Not bare "class." *(user)*
- **Building-hours handling (Stage 5).** A start/end pair in a "building hours"/"office hours"
  context should be separated/down-weighted, not counted as the bell schedule.
- **URL-template dedup for CMS apps (Stage 5/3).** Stroudsburg: `/apps/bell_schedules/` ≡
  `…/index.jsp` ≡ `…/printerfriendly.jsp` are the same content; our byte-identical dedup caught
  **zero** of these (each variant has a slightly different HTML wrapper). Need near-dup / URL-pattern
  collapsing, not just content-hash.
- **Stage 4 watch (Hoboken):** the user noticed `.txt` captured *more* than the graphic extractions
  on one record — worth checking why representations disagree (embedded slides?).

### 3 · Emerging patterns / hypotheses (collect evidence across batches)
- **CMS-templated schedule apps.** `educationalnetworks.net` (Stroudsburg) exposes a
  `/apps/bell_schedules/` app per school subdomain with: the directory/index/printerfriendly variants
  (same content), `?id=NNNN` alternates (id 7100 = normal day → target; 7101–7105 = 2-hr-delay /
  early-dismissal / special → `other_schedule`), and a `cross.jsp?...crossPath=/apps3/bell_schedules`
  **district-wide rollup that appears under each school subdomain** (a *school* URL that is actually a
  *hub*). HYPOTHESIS: per-CMS URL templates can drive targeted capture, variant dedup, and "pick the
  Normal schedule" logic. Collect across more `educationalnetworks.net` districts. **High
  false-positive risk** (many valid-but-non-standard bell schedules).
- **CMS nav-chrome pollution (Apptegy/SharpSchool/etc.).** School-switcher nav + footer building-hours
  inflate roster-name counts (topology) and negative keywords (category). HYPOTHESIS: chrome-stripping
  materially improves both. Ties to the Stage 3 `cms_hint` fingerprint.
- **Academic calendars carrying instructional time** (DUNSEITH). HYPOTHESIS: a minority do; don't drop.
- **Handbooks carry bell schedules** (Pittsylvania, PROVEN this batch). The per-page time-count signal
  located the schedule page (p2/p3/p4); buried_in_long_doc flag + per-page harvest is viable.
- **Building-hours red herring.** Footers state building-open hours that mimic start/end. Recognizable;
  collect to define a detector.

### 4 · Follow-on districts / queries
- **Stroudsburg:** (a) among each school's `?id=` variants, identify the *Normal/Regular* schedule and
  collapse the rest; (b) the `cross.jsp` rollups are the district-hub source; (c) `/about-us/bell-schedule`
  pages came back empty ("missing file") — the `/apps/bell_schedules/` app is the real source.
- **Marion:** the two Tier-D "Documents" pages are file-lists linking to the real VMS/MHS bell-schedule
  PDFs — which discovery *did* capture via the emergent (thrillshare) path; the list pages themselves
  are noise. Confirms the emergent path earned its keep here.
- **DUNSEITH:** the instructional-hours calendar is a target we'd otherwise filter — the canary for the
  "don't drop calendars" rule.
- **Urbana:** one record is a *partial* district hub — start+end for the 5 elementary schools, but only
  the start (prose) for middle/high. Partial-band extraction is its own edge.

## Pipeline-level questions (positions, for discussion)
- **"Will the script's district guesses update from my labels?"** — **No**, by current design.
  Topology + category are recomputed deterministically from *signals* on every ingest; labels never
  feed back. PROPOSAL: compute a **separate "labeled topology"** from the user's labels (if the
  bell-schedule records are per-school → per_school; if one record covers all schools → hub) and show
  both — the guess (pre-label) and the truth (post-label). Same for category: keep the guess for
  measuring the heuristic; the label is truth.
- **Should the SQLite DB ingest the earlier-stage JSONs (discovery/captures/processed) per district?**
  Leaning **yes** — it turns the DB into a cross-stage analysis hub: we could then query "which CMS /
  discovery wave / fingerprint correlates with targets," which is exactly the feedback-to-earlier-stages
  engine. Low cost; high analytical value.
- **Is SQLite still the right tool?** For single-user local analysis at this scale (thousands of rows),
  yes. Revisit Postgres-in-Docker only on a concrete pressure (multi-user CP-B, very large scale,
  concurrent web hosting). Schema is portable; don't migrate ahead of need.
- **Feed deterministic start/end guesses INTO the council as input?** **Recommend against** — anchoring
  risk: the council could rubber-stamp our guess, manufacturing false consensus and propagating our
  errors. **Instead, the user's own better framing: compute deterministic guesses INDEPENDENTLY and
  compare against the council POST-hoc (Stage 7+).** That yields (a) an agreement signal (agree →
  confidence; disagree → human review) and (b) the learning data for the next question — with zero
  biasing of the council.
- **Eventually skip the council for high-confidence deterministic extractions?** Possible, but only
  after the post-hoc comparison above accumulates evidence. Tests to pass before trusting a skip:
  on a council-verified set, the deterministic extractor must hit a high agreement bar (e.g. ≥99% on a
  specific, narrow content class — say a clean single-school bell table on a known CMS template),
  scoped to that class, with disagreements always routed to human/council. Collect the comparison data
  first; that IS the evidence base.
