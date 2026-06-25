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
| `academic_calendar` | A school/district calendar (year, holidays, early-release days) — time-bearing but not a schedule. Common confusable. |
| `community_calendar` | A community / events calendar (school or community events) — distinct from the academic calendar, and not a schedule. Its event date/times are spurious time signal. |
| `transportation_schedule` | Bus/transport times. **Tricky boundary** — "pick-up 7:15 / drop-off 2:30" mimics legitimate `school_start_end_prose`; labeled separately to measure the confusion. |
| `embedded_feed` | An embedded social-media / blog feed is the dominant content — its post date/timestamps are spurious time signal, not a schedule. |
| `other_schedule` | Scheduling for some other school activity (extracurriculars, performing arts, community meetings, …) — the residual non-target bucket. |
| `none` | No discernible schedule or instructional-time info. |
| `unusable` | Garbled, effectively empty, or otherwise impossible for a human to interpret. |

### Flags (optional, orthogonal to the primary label)
| Flag | Meaning |
|---|---|
| `duplicate` | Byte-identical content to another record; `duplicate_of` references the canonical record. Labeled once on the canonical; duplicates inherit. Now **generalized by near-duplicate clustering** — label the cluster representative and it cascades to members. |
| `buried_in_long_doc` | Target info is present but inside a multi-topic document (e.g. a student/parent handbook). See the handbook-harvesting open item below. |
| `building_hours_visible` | The page shows building/office hours (often a footer "Building Hours 7:15–3:15") that mimic a student start/end pair but are **not** the student day — a red herring to monitor. The motivating case for the planned **Stage 3 DOM de-chroming** (header/footer segmentation). |
| `target_image_only` | The target is visible in the image/PDF but **no** text extractor captured it → this record needs **vision** at Stage 6/7. Only meaningful on a record that *is* a target. |

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

---

# Topology — formal set + derivation (current; NCES-confirmed, built 2026-06-25)

Every district carries **two** topology values, kept **separate** (don't conflate):
- **`guessed_topology`** — computed from *signals* (`roster_school_names_hit`) at ingest. Noisy (CMS
  school-switcher **nav** pollutes the roster count → false `hub`, e.g. Marion). Kept only to **measure**
  the heuristic against the truth — its divergence from `labeled_topology` is the learning signal (and a
  prime motivator for the Stage 3 nav/chrome de-chroming).
- **`labeled_topology`** — derived **deterministically from the human labels + the NCES school count**.
  **The truth**; this is what informs Stage 7. Recomputed at ingest **and** on every label save.

## Formal `labeled_topology` set

| value | meaning | derivation |
|---|---|---|
| `single_school` | the LEA genuinely has one school | **NCES-confirmed** — the LEA's NCES school count is 1, **and** ≥1 target was labeled. **Not** inferred from discovery/capture yielding one page. |
| `per_school` | school-level schedules covering ~all the district's schools | school-level target labels present (`school_bell_schedule`/`school_start_end_prose`), not the `incomplete_coverage` case |
| `district_hub` | one page covers all schools / grade bands | `district_hub_schedule` label present, no school-level targets |
| `mixed` | both a district hub **and** school-level targets | both present (Stroudsburg: `cross.jsp` district rollups + per-school bell pages) |
| `incomplete_coverage` | exactly one bell schedule for a district NCES says has >1 school | **exact criterion below** |
| `none_found` | records were labeled, none is a target | no target labels anywhere in the district (→ likely needs re-discovery) |
| `unknown` | not yet labeled, or labeled-but-unclassifiable | fallback |

**Derivation precedence (the canonical ordering the code applies):**
`unknown` (nothing labeled yet) → `none_found` (labeled, zero targets — *before* `single_school`, since
"we found nothing, re-discover" is the salient state even for a 1-school LEA) → `single_school`
(NCES count == 1, ≥1 target) → `mixed` (hub + school-level) → `district_hub` (hub only) →
`incomplete_coverage` (exact rule) → `per_school` (school-level targets) → `unknown`.

**`incomplete_coverage` — exact initial criterion, deliberately narrow & clear-cut:** assign it when
**(a)** the district has exactly **one** target record, **(b)** that record is labeled
**`school_bell_schedule`**, **and (c)** NCES shows the district has **more than one school**. One clean
rule to start; expected to be **revised upward later** (e.g. "we have k of N schools" for k>1, once
per-school "got" matching exists) — the first cut is this single unambiguous case.

**Binding rule: the NCES count is the authority, never "what discovery/capture happened to yield."**
Stage 1 caps the sample at 12 schools/band, so "we have data for 1 school" must never be read as "the
district *has* 1 school." The count is the **our-criteria, by-`LEVEL` denominator captured at Stage 1**
(`batch_*.json` `nces_school_counts.total`, see ACQUISITION_PIPELINE.md Stage 1); Stage 5 reads it from
the batch (provenance, `nces_year`-stamped), with a live `school_sampling` lookup as the fallback when a
district has no batch entry.

**Naming note.** `incomplete_coverage` (names the *observed state* — a coverage gap vs NCES) was chosen
over `more_discovery_needed` (names an *action*), consistent with "we're not deciding what to *do* with
these yet." `incomplete_coverage` and `none_found` are recorded for later routing/feedback design; no
action attached yet.

**Not a topology value: completeness.** Whether we got **both** bell ends for **every** band is a
*separate, orthogonal dimension* from the hub/per-school *shape* — Urbana's hub was complete for its 5
elementary schools but had only the start time (prose) for middle/high. Captured as a record/district
field, never folded into the topology value.

**Implementation (built).** `build_signals.py`: `derive_labeled_topology()` + `recompute_labeled_topology()`
over the `label` table + the stored `district.nces_school_count`; `server.py` recomputes on every save.
Both badges render in the district header (labeled solid, guessed outlined). Validated on the 12-district
batch: HOPE→`single_school`, ROY (NCES 2, one `school_bell_schedule`)→`incomplete_coverage`,
Urbana→`mixed`, Marion **guess `hub` vs labeled `per_school`** (the CMS-nav divergence, now measurable).

---

# Proposal (under discussion, 2026-06-25): collect fingerprints at Stage 2, for upstream dedup

**The proposal (user).** Along the `D_RECON -->|doesn't exist|` path in Stage 2, after reconciliation
but before `D_FLATTEN`, have Playwright probe each *discovered* URL and collect the same
hosting/CMS **fingerprint** we currently grab in Stage 3 — at per-discovered-URL granularity (right for
dedup; district CMS may differ from school CMS). Store fingerprints in `discovery.json` (changes the
shape of the planned SQLite ingest). Motivation: get environment data **visible before capture**, so we
can define CMS/URL-template-aware dedup (e.g. the `educationalnetworks.net` variant explosion at
Stroudsburg — ~30 records, many printer-friendly/`?id=`/`cross.jsp` near-dups) *before* paying to
capture redundant pages. Stage 3 still fingerprints emergent URLs (unchanged); Stage 3 would also need
conditional gating so emergent URLs don't reintroduce already-deduped URLs.

**Assessment (agent).** The *direction* is right and the per-URL granularity is correct. Three things to
weigh before moving it upstream:

1. **The double-visit.** Stage 3 already collects the fingerprint *during* capture — it rides the render
   essentially for free. A Stage-2 fingerprint probe is a **second page-load** per URL (probe, then
   capture). A probe can be lighter than a full capture (skip screenshot/`page.pdf()`/the 2.5s settle/
   modal dismissal — just `goto` + headers + one DOM `evaluate`), but the `goto`/render is the expensive
   part, so a probe is ~half a capture, not free. Net compute is a win **only if** pre-capture dedup is
   aggressive (unique M ≪ discovered N). Stroudsburg yes; low-dup districts net-negative.
2. **"Visibility earlier" is already achievable without moving anything.** We *already* capture
   fingerprints in Stage 3. For **analysis** — the stated immediate goal — we just ingest the existing
   Stage-3 fingerprints into the SQLite DB (already planned) and study CMS-vs-dedup patterns there. By DB
   time, all stages have run, so Stage-3 timing costs nothing for analysis. Moving to Stage 2 pays off
   **only** if we want to *act* (dedup) before capture — which is where the double-visit cost lands.
3. **Emergent URLs argue for one dedup point downstream, not split.** Emergent URLs are discovered
   *during* Stage 3, so Stage-2 dedup can't see them — hence the proposal's own "conditional gating in
   Stage 3" caveat. By contrast, **Stage 4/5 sees ALL records (discovered + emergent) in one place**, so
   the variant-collapsing that most reduces the *human* CP-B burden can happen there — with full content
   + fingerprints + URL patterns — as a single dedup pass, no split logic, no double-visit. And capture
   is local/cheap, so avoiding redundant *captures* (the Stage-2 probe's only unique win) is a small prize.

**Recommended path (phased, evidence-first):**
- **Now:** ingest the existing Stage-3 fingerprints into the DB and measure how often CMS/URL-template
  dedup would actually help, across this batch and the next few. Gets the visibility the user wants with
  **no pipeline change**.
- **Later, only if the data shows pre-capture dedup is worth it:** add the Stage-2 fingerprint probe
  (the user's design) — by then we'd have evidence it pays for the double-visit and dedup rules learned
  from more than one CMS/example. Matches the user's own "premature to tighten on Stroudsburg alone."
- Either way, **dedup of the human-facing record set belongs at Stage 5** (all URLs converge there).
  Stage-2 fingerprinting is an *optimization to avoid captures*, not the dedup mechanism itself.

---

# Near-duplicate CLUSTERING in the CP-B app (proposed + **BUILT 2026-06-25**)

> **BUILT (2026-06-25).** All three open decisions resolved as recommended: (1) **content-similarity**
> (word-3-shingle Jaccard, no CMS rules); (2) **conservative threshold `CLUSTER_THRESHOLD=0.90`**
> (under-cluster; split is the only remedy); (3) **durable split override** — a `cluster_split` table
> (never dropped) + `cluster_splits.json` backup (tracked, like `labels.json`), re-applied before
> clustering on every ingest. Connected-components within each district; representative = best
> tier→score→key. **Labeling the rep cascades to unsplit members** (`server.py` save_label). **Split is
> DB-only** (detach + promote new rep / collapse), no re-shingling. UI: tree shows rep with a `+N` badge
> that expands members; right-panel banner lists members with per-member "split out". **Validated:**
> Stroudsburg `index.jsp?id=`-vs-directory variants + 3 `cross.jsp?wREC_ID=5711` subdomains collapsed;
> **Pittsylvania 19 per-school `/calendar` pages** (all `board_schedule`, ~0.9+ similar) collapsed to one
> labeling action; split tested end-to-end incl. survival across re-ingest. 37/150 records in 9 clusters.

## Original proposal (under discussion, 2026-06-25): near-duplicate CLUSTERING in the CP-B app

**Goal (user-confirmed):** group high-likelihood duplicate records so the reviewer labels the cluster
**once** instead of clicking through many near-identical pages (the Stroudsburg `educationalnetworks.net`
variant explosion: printer-friendly / `?id=` / directory-vs-`index.jsp` versions of the same schedule).
**Hard requirement: the reviewer can SPLIT a member out** of a proposed cluster if it turns out to be
genuinely unique. (No Stage-2 fingerprint probe — clustering happens in Stage 5, where all records,
discovered + emergent, already converge.)

**Proposed design (agent):**
- **Cluster within a district, by content similarity (deterministic, no AI, no CMS-specific rules).**
  Compute a normalized-text signature from each record's best extracted text (lowercase, collapse
  whitespace) and cluster records with similarity ≥ a **conservative** threshold (word-shingle Jaccard,
  or simhash Hamming; within-district n is tiny so pairwise is fine). **Exact byte-duplicates
  (`content_hash`) are the certain subset (similarity 1.0).** Generic similarity — not URL-template rules
  — keeps us from over-fitting to one CMS (consistent with "premature to tighten on Stroudsburg alone").
- **Conservative threshold on purpose:** the only correction is *split* (no easy re-merge), so we'd
  rather under-cluster (a few extra clicks) than over-cluster (wrongly hide a unique page). Notably,
  Stroudsburg's "normal" vs "2-hour-delay/early-dismissal" subsets share structure but are genuinely
  different (labeled `school_bell_schedule` vs `other_schedule`) — a high threshold should keep them
  apart; if it doesn't, the human splits.
- **Labeling:** label the cluster **representative** (highest-tier / richest) → applies to all members.
  Members show as collapsed under it with a "+N similar" badge.
- **Split = a durable human override** (precious, like a label): a `cluster_split` table survives
  re-ingest, so a record the reviewer pulled out stays out even when clustering recomputes. Re-ingest
  recomputes `cluster_id` deterministically, then re-applies the human splits.
- **UI:** tree shows the representative with a "+N similar" badge; expand to list members; per-member
  "this one's different — split out" button; labeling the representative cascades to unsplit members.

**Open decisions to confirm before building:** (1) content-similarity clustering vs. URL-template — I
recommend content-similarity (general); (2) conservative threshold (split-only remedy) — agree?;
(3) the split override is durable across re-ingest (stored like labels) — agree?

# Stage-1/2 funnel ingredients in the DB + LEVEL-based denominator (**BUILT 2026-06-25**)

The Stage 5 DB now ingests two upstream artifacts so "schools we targeted vs. schools we actually
got" (a later funnel analysis — *ingredients only, not built yet*) and the topology denominator are
first-class. Two parts:

**1. NCES denominator = our-criteria school count, grouped by raw ccd_sch LEVEL (not ccd_lea).**
`school_sampling.school_level_counts(year)` counts schools meeting our eligibility — open · regular ·
non-virtual · non-preschool, the **shared `_eligible()` predicate** now used by *both* it and
`school_index()` so they can never disagree — grouped by the **raw ccd_sch `LEVEL`** field
(Elementary/Middle/High/Secondary/Other/Not reported/…). `total` == `school_index()`'s distinct count.
Captured at **Stage 1** into `batch_*.json` (`nces_year` + per-district `nces_school_counts:{total,
by_level}`); `queue_batch.py` emits it, `batch.example.json` documents it, `batch_00001.json` patched
in place (selections untouched). **Stage 5 prefers the batch value over the live CSV** (provenance, no
year-drift); live `nces_school_counts()` remains the fallback when a district has no batch entry. This
**retires the hardcoded-`NCES_YEAR` live-CSV read** flagged when topology was first built.

**2. `candidates.json` (Stage 2 D_FLATTEN) ingested → per-record provenance + emergent flag.**
`candidates.json` is the only artifact with the **URL→school map**. Each record now carries
`intended_schools` + `candidate_tools` (from the URL join) and `is_emergent` (captured but never a
planned candidate → discovered mid-capture). Validated: Marion's 6 candidate pages map to their
schools (tools=`claude`); its 4 emergent records are the actual `5il.co`/`thrillshare` bell-schedule
PDFs found during capture. **38/150 records are emergent**, concentrated in Stroudsburg (23) — exactly
where near-dup clustering pays off. Stage-1 targeting lands in a `district_target` table
(batch_id, nces_year, nces_total, by_level, enrollment, claimed bands, schools_by_band). UI surfacing
is deliberately light (emergent ⚡ marker, panel "Provenance" line, by-level in the district header
tooltip) — the funnel/yield analysis itself is **later**.

# Future bridge (noted 2026-06-25, not acting yet): disk footprint at scale
At thousands of records the captured `page.png` / `page.pdf` / `raster_p*.png` will dominate disk. The
user plans to move the project to a large external drive by then. Options to revisit when we get there:
external/relocatable capture root, compressing or dropping regenerable rasters, or keeping only the
representations a record actually needs. **Cross that bridge when we come to it** — recorded so it isn't
forgotten.
