# Stage 5 (Local Filtering) — Design Note

> **Present-state design of record.** Code is ground truth; this note narrates it. Rewritten clean
> 2026-07-01 (V2 scoring/labeling architecture) — prior accreted history (the June 24–29 build layers)
> lives in git. Authority for Stage-5 *signals / tiers / topology / clustering / funnel / tuning*.
> Cross-stage architecture (state model, gates, the console) is `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`.
> Tuning methods + citations: `STAGE5_TUNING_NOTES_2026-06.md`. Research that grounds V2:
> `docs/technical-notes/filtering-research/` (weak-supervision / labeling functions; K-12 hours markup).

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
| `lf_office_hours` | a time-range whose nearest heading is `office`/`staff`/`workday` | **−negative (soft)** | the office-vs-school-hours confusable (research §5.2); the LCPS staff-hours page |
| `lf_no_times` | zero in-window times anywhere (incl. raw reps) | **−suppress** | §2a-3, the corrected suppress floor |

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

---

## 4. Labeling — a facet questionnaire (V2, REQ-114)

**V1 asked for one primary label (radio) + a few orthogonal flags.** That forced multi-purpose pages (a
homepage with a news feed *and* footer hours *and* a calendar widget) into a single bucket, and buried the
real findings in 202 free-text notes. **V2 turns labeling into a checklist that mirrors the detectors** —
so the human confirms/corrects each detector, which is exactly the per-detector ground truth the harness
needs (§5), and multi-module pages are represented honestly.

- **Keep one "dominant content type"** field (topology/funnel bookkeeping) — but it stops being the only
  signal scoring reasons about.
- **Add detector-mirroring facets**, each **tri-state** (yes / no / unsure), pre-filled with the detector's
  own vote so labeling is *confirm-or-correct*, not blank-slate: *footer/header hours block present?
  student start/end declared anywhere? dominated by a news/social feed? calendar widget (not a schedule)?
  times are staff/office not students? non-standard-day variant? buried in a multi-topic handbook?* The V1
  flags (`buried_in_long_doc`, `target_image_only`, `building_hours_visible`) fold in here.
- **Structured "where"** (main / footer / header / table / image / feed-post) replacing prose "in the footer".
- **Structured handbook page number** — reusing the guessed-vs-labeled pattern already built for topology:
  keep `harvest_pages` (guessed) + `harvest_pages_labeled` (a numeric field), so harvest precision/recall
  becomes measurable instead of anecdotal (§2a evidence showed the 15-page cap + density heuristic miss real pages).
- **Free-text note stays** as color commentary — valuable, but no longer the only record of a finding.

The **primary-label taxonomy is retained** (targets: `school_bell_schedule`, `school_start_end_prose`,
`district_hub_schedule`, `explicit_instructional_time`, `nonstandard_format`; non-targets: `board_schedule`,
`sports_schedule`, `academic_calendar`, `community_calendar`, `transportation_schedule`, `embedded_feed`,
`other_schedule`, `none`, `unusable`) — the facets are **additive**, not a reset (the 440 existing labels +
202 notes stay valid evidence; user decision 2026-07-01). Facets backfill deterministically from existing
signals where a detector already answers them.

---

## 5. The learning loop (REQ-113 harness extension; scale endgame deferred)

The machinery already exists and V2 **extends** it — it does not replace it: `harness.py` (fingerprinted
scorecards), `frontier.py` (recall-constrained grid/coordinate search + LOGO-by-district CV guard),
`tuning_ledger.py` (append-only before→after episodes), config-as-data with `provenance`.

1. **NOW (this REQ): per-detector precision/recall.** The harness scores **each detector against its
   matching facet** (not just one aggregate tier-A number) — Snorkel's LF diagnostics: **coverage** (how
   often it fires), **accuracy** (precision when it fires), **polarity**, **overlap/conflict** (where two
   detectors disagree). This is the prerequisite for tuning anything, and it's what makes "you and me
   having chats to adjust weights" a data-grounded conversation instead of guesswork.
2. **WHEN STAGE 7/8 LANDS: outcome feedback.** The real target metric is *did the representation we sent
   actually extract correctly* — a stronger signal than "did the human confirm the detector." It flows
   into the **same** ledger/harness (not a separate system): the deterministic decision becomes a *proxy*
   whose calibration against the paid outcome is measured (the SUPG recall-floor discipline).
3. **LATER (documented, deferred — the scale endgame, `STAGE5_TUNING_NOTES`):** a learned combiner
   (Snorkel `LabelModel`, inferring per-detector accuracy from agreement without gold labels for every
   point) replaces the hand-weighted vote **once diagnostics justify it**; hierarchical partial-pooling
   **by CMS vendor** (the natural structure, since detector accuracy plausibly varies more by template than
   geography); ADDIS online-FDR drift across per-vendor/per-state streams; VPC/ICC to decide which knobs
   live at which level. **None of this runs at n≈440** — built only when label coverage warrants.

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
| V1 tiering (`tier_and_category`), de-chrome, clustering, topology, funnel, attention, harness/frontier/ledger | **BUILT** (pre-V2) |
| V2 detectors + combiner (`detectors.py`/`combiner.py`); the 3 fixes; new signals (footer/heading/table-density/cms_hint) | **BUILT (REQ-113)** |
| Per-detector harness diagnostics (coverage/accuracy/overlap/conflict) | **BUILT (REQ-113)** |
| Facet questionnaire labeling UI (server + JS + detector pre-fill) | **REQ-114** |
| Stage-3 iframe/embed capture + `cms_hint` promotion + iframe-innerText check | **REQ-115** |
| Learned `LabelModel` combiner · hierarchical/vendor pooling · online-FDR drift · Stage-7/8 outcome feedback | **DEFERRED (scale endgame)** |

---

## Change log

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
