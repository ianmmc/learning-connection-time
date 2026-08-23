# Claude Code Project Briefing: Learning Connection Time

This is the first thing a fresh Claude Code session sees. It's a navigation hub + durable operating rules —
not a build log. For *why* this project exists, read `docs/PROJECT_CONTEXT.md`; for *what's built right
now*, read GitHub Issues (this repo uses them as the live tracker) — this file stays short on purpose so it
doesn't need constant rewriting.

## Project Mission

Transform student-to-teacher ratios into "Learning Connection Time" (LCT) metrics that tell the story of students getting shortchanged.

**Core Formula:**
```
LCT = (Daily Instructional Minutes × Instructional Staff) / Student Enrollment
```

**Example:** 5,000 students, 250 teachers, 360 min/day → LCT = 18 min/student/day

**Goal:** Analyze data from the largest U.S. school districts to identify educational equity disparities.
Full mission, reframe, and 6-phase roadmap: `docs/PROJECT_CONTEXT.md`. Currently in **Phase 1.5**: enriching
basic LCT with actual bell schedules acquired via the 9-stage acquisition pipeline
(`docs/ACQUISITION_PIPELINE.md`). Known methodological limitations (individualization fallacy,
time-as-quality assumption, averaging deception): `docs/METHODOLOGY.md`.

---

## Where to look for what

| You need... | Go to... |
|---|---|
| **What's currently built / in flight / next** | `gh issue list` (this repo's live tracker) — not this file |
| The mission, the story, the evolution roadmap | `docs/PROJECT_CONTEXT.md` |
| Dev setup, fresh-checkout orientation, conventions | `docs/GETTING_STARTED.md` |
| LCT calculation mechanics, SPED segmentation, QA | `docs/METHODOLOGY.md` |
| The 9-stage acquisition pipeline, end to end | `docs/ACQUISITION_PIPELINE.md` (the map) → `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` (per-stage present state) |
| Cross-stage architecture: DB/state/gate model | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md` |
| Why a decision was made, project history | `docs/PROJECT_HISTORY.md` |
| Vocabulary | `docs/TERMINOLOGY.md` (read first) |

---

## Durable pipeline facts (settled architecture — rarely changes; NOT current-status)

**Metric = GROSS bell-to-bell minutes (end − start), NOT net.** No lunch/passing/recess deduction, no
*assumed* deductions. Ground truth is already gross; gross needs only two reliably-published numbers
(↑accuracy). Net is a deferred enhancement. Labeled `gross_bell_to_bell`. Plausibility gate 240–510 min.
(REQ-055; supersedes net in REQ-042/046.)

**INVARIANT — extractors read TIMES; deterministic code computes MINUTES + the MODE.** Council models
return only per-school `{start_time,end_time,grade_level,school_name}` facts; Python does `gross=end−start`
and the per-band exact-mode. Never ask a model to compute minutes or pick a "typical" schedule. (REQ-054.)

**Extraction = COUNCIL (correctness); Discovery = WAVES (recall).** Council: consensus is on the per-school
(start,end) pair, cross-family, ±15 min — same-family agreement is NOT consensus (REQ-056). Council
template: 2 cross-family voters → a 3rd-family judge on disagreement, enforced in `councils.validate()`.
Model composition is deferred to the council lab (`cost_benchmark`), never guessed. Discovery = a
deterministic SERP cascade, NOT agent waves: Wave 1 = Bright Data SERP + Serper failover (real Google
index) → Wave 2 = Claude WebSearch on the residual (a different index, speculative). The index predicts
recall — raw Google wins; own-index providers crater on long-tail K-12.

**The DB is the working store; disk holds binaries + receipts.** The governance Postgres DB is what every
stage actually reads/writes; per-stage JSON files (`discovery.json`, `stage5_filter.<ts>...`,
`handoff_*.json`, etc.) are regenerable, auditable receipts — never the transport between stages. Stages
5-9 write theirs via the ONE shared `common/receipts.py::write_receipt`, ALWAYS datetime-stamped
(`stage<N>_<stage_name>.<fs_stamp>.<writer>-<h8>.json`, unified naming 2026-07-23); stages 2-4 stay
fixed-filename handoffs whose EXISTENCE is a stage-done marker (REQ-164; conversion tracked #617/#622/#623).

**Human-in-the-loop gates are stage-numbered:** `gate@1` (Queue) · `gate@5` (Filter — the critical
per-URL review gate) · `gate@6` (Dispatch) · `gate@7` (Extract) · `gate@8` (Aggregate — Stage 9 then
auto-writes). Stages 2/3/4 + the Stage-9 write are ungated. Each gate is manual/auto (confidence-escalating).

**Ramp-up model (standing operating posture):** the pipeline is built **high-supervision-first** — every
gate manual now, easing toward auto (confidence-escalating) only as each gate's reliability is proven;
the destination is a self-governing app. **So present gate output as a recommendation for human sign-off,
not a done deal, until that gate is explicitly set to auto** — the human inspects real output at each gate
and catches real-data bugs code review misses. (governance §11b.)

**When working on bell schedule acquisition infrastructure, a robust pipeline — not harvesting the instructional time data — is the immediate goal.** The way that we get instructional time data extracted and integrated is by way of the pipeline.
Bell-schedule acquisition work targets the highly-automated, as-deterministic-as-possible pipeline in `ACQUISITION_PIPELINE.md`. A correct outcome
reached by hand-orchestration — reading captures by eye, watching district-by-district for whether a rule
triggers, re-adjudicating an already-approved gate@8 decision — is a **process failure even when the
number is right**: it violates commandments #2 + #4 (manual inspection of ~20k districts doesn't scale)
AND commandment #1 (a probabilistic model judgment isn't reproducible or auditable the way a deterministic
guard is — run at a different time/model and the "verdict" could differ). Trust the deterministic inputs
(the approved gate@8 receipt is authoritative; a note here is not) and the script's own guards (benchmark
wall, TOCTOU, REQ-147 same-vintage staleness, REQ-026 temporal window, foreign-collision fail-loud) as the
ONLY legitimate gates. When an outcome is wrong or fragile, fix the **pipeline** (a guard, a metadata gap)
— never hand-fix the district. (2026-07-23, Ian.)

**Three batch types (Stage 1):** `first-run`, `follow-up`, and `benchmark` (the 27 curated-GT districts
injected as `batch_00000` — permanently walled off from Stage-9 writes and funnel/enrichment stats; see
`STAGE1_QUEUE_DESIGN.md` §2h).

**Ground truth, hand-verified (gross, per-school):** `data/benchmark/gt_curation_*/gt_proposals.json` —
940/943 schools human-verified across `batch_00000`'s 27 districts. Process: council *proposes*, human
*verifies* (REQ-059). **This set is FIXED — gate@8 approvals do NOT append to it** (no such code path;
Stage 9, the writer, is unbuilt — #93). What grows is the **confirmed-fact base**: every district approved
at gate@8 accrues a `stage8_approval` row + a frozen closing-argument receipt, and the more confirmed facts
we hold, the more we have to *learn from and improve with* — realized as pipeline-improvement work (epics
#478/#119, continuing in #106), not as a write into the GT corpus (Ian, 2026-07-16).

**Reader-routing (format-route the reader, outcome-based):** Tier 1 plain text → Tier 2 `page.pdf()` +
`pdftotext -layout` (multi-column) → Tier 2.5 OCR a clean image → Tier 3 vision (reads JS/image/scan pages
all text paths miss). Trigger is "did the cheap reader recover usable content," not format.

**SEA central-data harvest is a dead end for daily minutes** (verified) — states publish only statutory
minimums / day-counts, not actual daily minutes. Web discovery + extraction is the primary acquisition
path. See `INSTRUCTIONAL_TIME_HARVEST.md`.

**Notes:** Local Ollama deleted; paid-cloud extraction is cheap (~$0.05–0.30/1M). Keys in gitignored
`config/secrets.local.json` + `.env`. Requirements are tracked as REQ-001…184 in `docs/REQUIREMENTS.yaml`
(some superseded/retired — read that file's own status column, never a list here). **The ledger is
ENFORCED** by `tests/test_requirements_yaml_hygiene.py` (18 checks): five statuses only, `type:` is the
altitude axis (`principle` exempt from the evidence rule), delegation is `enforced_by:`, `tested` must
cite a resolvable test, no phantom REQ ids in the ledger OR in `infrastructure/`, and `last_updated`
must not lag the newest entry. Adding a REQ: spec/invariant only — a review finding AMENDS the REQ it
belongs to rather than getting its own.

---

## Fresh-session essentials

`/catchup` → `pip install -e .` → **Docker up** (`docker-compose up -d`) → `lint-imports` (expect "kept/0
broken") + `pytest -q -m "not integration"`. `build_signals` full re-ingest (**~8.5 min** since 2026-08-18 —
whole documents are scanned, the 60-page cap is gone; idempotent, preserves labels/facets) is only needed
after a scoring/config change or new captures — not just to reboot the app. Run it `--assert-floor`.

Console: `python3 -m infrastructure.acquisition.process_governance.server` (→ :8005; Stage 5 default).
**Reload the browser for `static/*.js`, restart the server for Python changes.** Self-verify UI changes with
Playwright before shipping visuals (Python playwright isn't installed — drive the Node one in
`infrastructure/scraper`). CI runs two jobs: the DB-free suite + `governance-db` (`pytest -m govdb` on a
Postgres service container).

**Precious state + backups:** `label` (incl. `facets_json`) / `cluster_split` / `followup_flag` /
`handoff` + the gate@8 human-judgment tables (`stage8_approval` incl. frozen receipts, `band_exclusion`,
`human_added_fact`, `slot_assignment`, `gate_mode`) live in the governance DB;
`handoff_<hash>_<ts>.json` under `data/acquisition/handoffs/` is immutable; `saved_view` holds UI prefs.
The tracked `.githooks/pre-commit` sweeps the git-backed JSON twins (`labels.json`,
`district_status.json`, `stage8_approvals.json`, `band_exclusions.json`, `human_added_facts.json`,
`slot_assignments.json`, …) into every commit — on a fresh clone run `git config core.hooksPath
.githooks` (`GETTING_STARTED.md` §1b). Stage 4 needs poppler/tesseract/ghostscript
(`GETTING_STARTED.md` §1a).

**Current status (2026-08-22): PRs #872/#881/#882/#883 all MERGED (`9c9bde3`) — #863, #672, #861
closed. #671 is IN FLIGHT on `fix/671-batch-done-predicate`.** #872 carried the Stage-3
single-instant DOM read (#863), Stage-2 rung-regression recording (#672), and a `REQUIREMENTS.yaml`
audit that gave the ledger its own fitness function; review round #873-#880 was absorbed into the
same PR — six fixed, #873/#875 closed as not-bugs with pins. Then #881 (`deepseek-v3.2` catalog
refresh, caught by #809's network canary), #882 (checkpoint), #883 (#861 — one name, one formula).
The live governance DB is UNCHANGED since the 2026-08-19 re-ingest (116 districts / 3,561 records /
2,614 labels); nothing has altered scoring, so no re-ingest is owed, and the baseline is GREEN.

**#671 was filed as a design question and is a WRONG PREDICATE — the SIXTEENTH instance of
measure-first, and a new shape of it.** Batch-scoped done-ness was `stale disk artifact ∧ this
batch DISPATCHED it`, and dispatch is stamped for the whole todo list up front, so a redo district
holding a prior artifact read `done` from t=0. The issue measured that as a ≤38-minute transient
window and asked what the badge should *say*. Both premises were incomplete: **the window is not
transient** (7 districts dispatched to Stage 4 on 2026-07-22 had read `done` off a prior run for
**32 days**), and **no design decision was needed** — non-`done` districts already take the zeroed
row defaults, so one predicate change also stops the stale metrics rendering as current. The new
shape: because `stage4.js` hides the Run control at `todo + failed == 0`, **the false `done`
suppressed its own fix** — the console asserted completion and simultaneously removed the means of
correcting it. Fix is `DS.completed_by_batch` (dispatched by this batch AND a stage OUTCOME after
that dispatch), keyed on event ORDER so the pre-#647 unstamped era still reads correctly. Measured
strictly withdrawing: over 43 batches × 3 stages the corrected set is never a superset. Retires
#670's *precedence* half for redo batches as a side effect (`1201440` now reads `timed_out`).

**Review round #885/#886 absorbed into PR #884 — and #885 is the measure-first lesson AGAIN, on a
review finding.** #885's MECHANISM was real and sev:critical: the first predicate asked only for an
outcome AFTER this batch's dispatch, and `event_id` is a global serial, so a LATER batch's outcome
finished an EARLIER batch — #671 one level up, whose TRIGGER is the remediation of #671's own 7 stuck
districts. But its PROPOSED FIX (`AND e.batch_id = :b`) was wrong and measurably so: only 22.4% of
`process` outcomes carry a batch_id, so that filter withdraws **36 genuine completions**. Shipped
instead: the outcome must land in the WINDOW the dispatch owns (after it, before the next dispatch of
the same district+stage) — agrees with the pre-#885 rule on all 159 live done-districts AND closes
the hole. **Latent is not absent:** the corpus shows 0 cross-batch rows because remediation has not
run, so coverage is CONSTRUCTED in the suite and C5 names the 8 pending triggers. #886 (merge Stage
4's two predicate calls) measured and DECLINED — 1.5-2.0ms of a ~43ms render, and it would give the
one-home predicate a polymorphic return; pinned at the call site.

**#863's corpus property clears only on RE-CAPTURE.** `page.txt` and the segments are now one
read, so `page.main.txt <= page.txt` holds by construction — but only for records captured after
the fix. `text_phase` (`final`|`early`) marks them; it lives in the Stage-3 receipt, not the DB.
The measurement reports `NOTHING MEASURED` for the post-fix population until re-captures exist,
which is the honest state, not a failure.

**The spec ledger is now enforced, and its vocabulary changed.** Five statuses
(`proposed`/`accepted`/`tested`/`superseded`/`retired` — `implemented`, `approved` and
`in_progress` are gone), `type:` is the documented altitude axis (`principle` is exempt from the
evidence rule), and delegation uses `enforced_by:` — never invent `satisfied_by`. The evidence
rule is **one-directional**: `tested` implies evidence, evidence does NOT imply `tested` (REQ-169
is mid-build on open epic #617 and legitimately carries tests). `tests/test_requirements_yaml_hygiene.py`
is 18 tests and will fail the build on a phantom REQ id, a stale `last_updated`, an orphaned test
citation, or an invented status. REQ-177–185 added; #674 amends REQ-044 rather than duplicating it.

**Next (RESUME HERE — 2026-08-22):**
1. **The Stage 2-4 console triple → #723. #671's PREDICATE is done (PR open); what remains is
   #669 + #670's residue, and one cosmetic call.**
   - **#669 is now the largest unblocked piece.** Arm 1a (the confirm dialog asserting the
     OPPOSITE of what redo does) is trivial and lands alone — NB it is in BOTH `stage3.js:160`
     and `stage4.js:159`; the issue only names stage3. Arm 1b (cumulative counts in the
     run-summary position) and Arm 2 (no fresh-vs-carried signal EXISTS to scope) ride #623/#640.
   - **#670's residue:** ORDINARY batches still let artifact-existence outrank a failure event
     (#671 only scoped redo batches), and the *completeness* question — was a timed-out capture
     truncated? — is unanswerable without #623's intended-vs-achieved receipt counts.
   - **The one cosmetic call left from #671, Ian's:** a dispatched-but-unfinished district now
     reads `todo`, which is honest and keeps the Run control correctly suppressed mid-run
     (`canRun` already gates on `!running`). Whether it deserves a visually distinct `in-flight`
     badge is a look-at-the-console decision, deliberately NOT guessed. Cheap either way.
2. **#708 — OCR name-mangling. BLOCKED ON DATA, not design.** The issue's proposed Stage-5
   roster-match rate is confounded (Lewiston's mangled rep scores 1/6, not 0, and a single-school
   page legitimately names one school). The unconfounded signal is the Stage-7 rate over EXTRACTED
   names, but only **29 of 84** OCR rep-extractions carry `identity_json`. Widen that coverage
   first or re-scope P3. NB Lewiston was already solved by the VISION rep (ext 77, 7 accepted).
3. **#685 — Stage 3 captures only the ACTIVE tab panel** (Cedar Rapids loses 54 of 110 times).
   **BLOCKED on Ian's design calls**, which the issue reserves: (a) what is stored — raw
   `page.content()` vs a `tabpanel:hidden` text rep vs the hidden panels' `outerHTML`; (b) whether
   `usable`/`n_times` are computed for it; (c) whether v1 covers `<details>`/accordions or defers.
   Trigger is settled and cheap. NB the naive reveal recovered NOTHING — the vendor open-state
   class and `max-height` are load-bearing.
4. **#871 — geo's unbuilt second job. BLOCKED on Ian's design calls** (filed this round, REQ-184
   `proposed`). Geo carries two jobs and only one is built: disambiguate a common school name
   (built) and REACH off-domain PDFs/Docs on a CDN or Drive (intended, never built). The gate
   refuses off-domain documents in BOTH branches, and `drive.google.com` is in `CMS_HOSTS` yet
   unreachable because `cms-slug` needs the district slug in the URL and a Drive URL is an opaque
   file ID. **Not a revert of #719** — sequencing: the gate must be able to KEEP such a document
   before routing anyone into that round is worth anything.
5. **Ian's call, not a session task:** re-running Cedar Rapids / New Haven CT / Washoe / New Haven
   Unified / Little Rock on the `domain+widened` rung they now route to, to recover the **160**
   on-domain URLs the #719-era geo rungs left in no capture plan (incl. literal bell-schedule and
   handbook pages); routing Broward/Cleveland/Essex's send-backs; resuming the 5→1 composer on
   West Ada/Lincoln/Baldwin. All live spend, console-driven. Epic #80's experiments (#823-#825) too.
Ian drives the console; prepare and verify, don't execute stage runs (Stage 9 CLI, the #716 replay,
and the **read-only measurement scripts** are the verification exceptions). *Falsifier unchanged: if
any district needs a hand-edit or a re-adjudicated gate@8 call, the mechanism is wrong — fix the
pipeline, not the district.*


**Standing method note (now on its SIXTEENTH instance): measure the thing before fixing it.** An
issue's proposed fix has been overturned by measurement fifteen times (#691, #684, #719, #755,
#706's severity ranking, #721, #794, #796, #795, #822's image-council premise, #826, #841, #852,
#868, #672, **#671**). **#671 is the newest SHAPE: an issue can be filed as a DESIGN question when
its substance is a wrong predicate** — #671 asked "what should a stage's status badge mean during a
re-run?" and offered a four-option menu, but the badge only ever said `done` because the rule behind
it was false; correcting the rule answered three of the four acceptance criteria and left one
cosmetic choice. It also broke the issue's own severity framing twice: the "up to 38 min" transient
is really 32 DAYS on 7 live districts, and the false `done` HID ITS OWN FIX by driving the Run
control's `retriable == 0` branch. #672 was an earlier new shape: the fix that overturned it (#719) had landed
BETWEEN the issue being filed and the work starting**, so nothing in the issue text was wrong when
written — only replaying the LIVE predicates could show that its headline mechanism, its severity
("109 URLs thrown away" is 3 once you notice candidates.json unions across rungs) and its terminal-
state claim had all expired. Re-read an issue's premises against today's code before implementing it. The last two are review findings whose mechanism was real in the source and unreachable in
practice — #852's ladder-stop (no ladder starts when `roster_unique` resolves) and #868's degenerate
send (`visual_text_gap` is true BY CONSTRUCTION when every real text rep is sub-usable, so the image
branch fires a step earlier). Both are closed as not-bugs WITH pins, because "we checked" is not
durable and the next reader will re-derive the same plausible worry. The last
three are the sharpest yet because two of them were *unfalsifiable as posed*: #822's "0 records
exceed the image council" was true by construction (the clamp tops out below that council's
ceiling), and #841's "how often does `segment:main` carry more times" could not be answered from the
DB at all (`n_times` is NULL for all 11,349 segment reps, and `nt or 0` reads every one as zero).
#841 then REVERSED the issue's leaning: main is the uniquely best alternate on 27 records and
dominated on 4. Corollaries: **a fix can remove a failure's VISIBILITY instead of the failure**
(#792); **a marker without a consequence is decoration** (#793); **re-run the measurement after the
fix it motivated**; and, new this session, **before calling a divergence a bug, check whether it is
INTENTIONAL** — the #841 audit's first pass reported 3,532 collector "disagreements" that were all
one deliberate difference (`release.alternates` admits `pdf` for a HUMAN at gate@6;
`live_alternates` excludes it because an automated retry would send raw bytes to a text council).
Compare the dimension the rule is about, not whole outputs.

**The implemented-twice-drifts class (ELEVEN instances across five sessions; the newest two are
#876 — `htmlFingerprintFor` still hand-spelling the frame loop that the SAME PR had just extracted
into `readFrameText`, i.e. a copy left behind by the extraction itself — and #880, a measurement
script re-implementing the `kept_in()` it was committed to validate. Both were caught by review, not
by me, in the very PR that added REQ-182 ("ONE EXPORTED PREDICATE PER RULE") to the ledger. Earlier:
#866 — `best_send` spelling `NON_SWAPPABLE_SOURCES` a FOURTH way, `not in SLICE and not in CHROME`
being provably that same union — and #869, three more sites computing their own chrome-inclusive
"densest": the gate@6 sibling tie-break, a measurement script's hand-copied pool, and the gate@5
"densest" badge that named a rep `best_send` refuses to send. The fix is the usual one, ONE exported
predicate, `release.sendable_text_reps`; the new wrinkle is that a CLIENT mirror counts as a call
site, so app.js's chrome set is pinned member-for-member against the Python one.) Earlier:** #798/#810/#799/#816;
then #834's two slice predicates disagreeing on 43 live records; then this session's two —
#843/#845/#847/#848 were ONE root (the "how is this rep degraded" fold hand-written at FOUR sites,
two of which disagreed: an overflow-only rep counted degraded in telemetry and barren in `explain`),
and #841's three alternate collectors spelling three segment rules. The countermeasure is always the
same and always structural: ONE function in the base layer (`MF.rep_degraded_kinds`,
`MF.rep_prompt_size`, `SM.roster_match_keys`, `release.NON_SWAPPABLE_SOURCES`), not a test that locks
two copies into agreement. **#846 sharpened it further: an identity assertion locks the FUNCTION, not
its INPUTS** — two call sites can drift by feeding the same function different things (dispatch was
omitting the system prompt, ~1,000 tokens), so the input construction must be one function too, and
P4 is asserted at the CALL SITES.

**NEW (2026-08-19) — a correct fix can ship with a WRONG RATIONALE, and the rationale is what the
next reader inherits.** PR #865's one line was right and stayed; its justification was wrong twice
and a review caught both. It sized the change at **4** records when a full `best_send` replay
measures **244** (the 4 counted only what #841's scoring newly flipped, missing ~240 that had won on
the `n_chars` tie-break since REQ-091 — invisible because all 244 are REJECT-decided and a reject
never serializes its send). And it offered the reassurance "the footer's evidence is not lost —
page.txt, chrome included, stays in the pool", **false on 5 live records** (`0103390:fb71b7cc63`:
footer 12 clock times, its own page.txt 0). Corollaries now standing: **a fix's measured blast
radius is part of the fix** — commit the rerunnable script, never the recollection (that is what
#870 asked for and why `2026-08-19-chrome-first-send-measure.py` exists); and **a reassuring
sentence in a comment is a claim — measure it or delete it**, because the tidy version is the one
that survives into the next design.

**A measurement script is EVIDENCE and is held to the standard of what it measures (#879, new).**
The geo script's on-domain test was a bare `endswith`, so `nlrsd.org` — NORTH Little Rock, a
different district — counted as on-domain for Little Rock's `lrsd.org`. The published corpus figure
was **164; it is 160**, corrected in the PR body, `STAGE2_DISCOVER_DESIGN.md` §2f and REQ-180. Import
the production predicate; never approximate it for convenience. Corollary from the same round: when
choosing a PROXY for something you cannot measure directly, check the proxy has the property you are
testing for — #873's first pass used `segment:main` as the late-read proxy, but main EXCLUDES chrome
and chrome growth was the entire scenario.

**The standing lesson (now on its EIGHTH shape): a measurement that cannot fail.** The newest is
a TEST, not a sweep: #866's `assert CHROME_SOURCES <= NON_SWAPPABLE_SOURCES` — true by construction
(the definition IS that union), and it never touched the function it claimed to guard. Replaced by a
loop over the real set through the real `best_send`, verified to fail on 3 arms against the pre-fix
pool. **An identity assertion about CONSTANTS proves nothing about BEHAVIOUR.** Earlier shapes: §10.11 · the fix
round's own findings · a merged fix un-run against the live DB (§13.1) · Pass B comparing the
post-state with itself · #822's clamped estimate that could never exceed the image ceiling · #841's
NULL-coerced segment times. Countermeasure now standard in every measurement script: an explicit
`NOTHING MEASURED` verdict instead of a green zero on an empty sweep — it earned its keep twice this
session (the #826 sweep caught a wrong district-dir path assumption that had scanned 0 records).
**A verdict that cannot fail is not a verdict; make the script say so.**

**Schema invariant (bit us on PR #641):** a `_PRECIOUS_ALTERS` column's DDL must be declared TWICE,
identically — a SQLAlchemy `default=` never reaches the DDL, so a fresh `create_all()` DB diverges
from a migrated one and fails raw `text()` INSERTs **on CI only**. Always pair with `server_default=`.
Enforced DB-free by `tests/test_precious_alters_parity.py`. **Verify a new precious column against a
THROWAWAY governance DB — the local migrated one tests the path that isn't broken.**

**Cloning the governance DB does NOT isolate the git-tracked JSON twins (REQ-176).** They are files
on disk and every exporter rebuilds them WHOLESALE from the connected DB's log, so a scratch console
on a clone writes its throwaway drafts into `district_status.json` (this happened during #822's
verification) and a scratch server on an EMPTY governance DB would blank all twelve — measured, the
tracked status file holds 175 districts and an empty-DB export produces 0. `guard_tracked_backup`
now quarantines under EITHER cause (pytest, or a non-canonical DB) with a one-time note.
**Seeing that quarantine line while running against a clone is the guard working.**
**Outstanding:** Playwright-verify the gate@6 + gate@1 console changes (incl. #853's third `benchmark-only held` badge arm — seed a clone with an `out_of_window` gt:// label), **#869's gate@5 "densest" badge** (it now excludes chrome, so a footer with unique times must read `adder`, not `densest` — `0103390:fb71b7cc63` is the record, footer 12 times vs page.txt 0; source-pinned only so far), #647's Stage 2/3/4 status/Run
control, AND **#840's new gate@5 page-scoping card** (★ harvest / ◆ floor markers, `data-scoping=`
DOM hook — static-source-pinned only so far); #667's gate@8/#662's gate@5 badges, #684's staff-day
surfacing and the three gate@8 arrows ARE verified — rerunnable verifiers
`infrastructure/scraper/verify_684_console.mjs`, `verify_682_console.mjs`, and
`verify_822_console.mjs` (#822's gate@6 overflow badge + gate@7 degraded banner, 15/15 — it also
documents the clone-and-seed runbook, since the gate@7 banner reads a STORED column and every live
row is `{}` until a post-#822 Stage-7 run happens). The pattern to extend.
**Deferred by design (epic #128):** #642 (content-derived document vintage) and #643 (the Stage-3
render-facts probe; rides #623's Node seam — now ALSO the spine of epic #864). **Retired, do not do:** Phase 2e's retroactive
`dispatch_type='benchmark'` tagging — arm 2 derives it. Banked routing: #112 → epic #128. Parked:
#475/#476, #103 (+#110); the SEA integration follow-up (~9 states) is an opt-in backlog item — ask
Ian before filing. Documented-in-code deferrals: `_satisfied_bands_now` batching; the #522 guardrail's
per-rep keyword/table attribution (needs a server payload change); JS behavioral tests (no JS
harness); the remediation-receipt exception is not STAGE-scoped (30-day expiry since 2026-07-20);
attribution v1 reads each district's LATEST candidate plan; the `stage6_handoff/requests.py:17-18`
docstring falsely claims Stage 7 "reads ONLY the flagged pages" — the `pages` hint never scoped
content (the slice FILE is the scoping), a live source of wrong inferences worth a one-line issue.
Resume-essentials (ALL re-verified 2026-08-22 on `main` post-#881/#882 — the baseline is fully
GREEN; no known-red command): `pip
install -e .` → Docker up (`docker-compose up -d`) → `git config core.hooksPath .githooks` (fresh
clone only) → `lint-imports` (expect **4 kept/0 broken**) + `pytest -q -m "not integration"` (expect
**2457** pass, 1 skipped [pyarrow]) + `pytest -q -m govdb` (expect **400** pass, Postgres up) +
`pytest tests/test_*_integration.py` (expect **257** pass, 149 skipped) + `cd infrastructure/scraper
&& npm test` (expect **100**) + `flake8 . --count --select=E9,F63,F7,F82` (expect **0** — this is CI's
blocking lint; the vulture whitelist is `per-file-ignores`'d for F821, main had been red on it since
ebcc1a1). NB `pytest -m integration` also carries a NETWORK test (`test_model_windows_integration.py`,
#809) that re-fetches OpenRouter and fails with "refresh the catalog" if `MODEL_WINDOWS` has drifted
— skips cleanly offline, excluded from the default suite. **Full re-ingest is now ~8.5 min**
(`python3 -m infrastructure.acquisition.stage5_filter.build_signals --assert-floor`; whole documents
scanned, largest is 1,017 pages) — needed only after a scoring/config change or new captures; run it
with `--assert-floor` so a recall regression rolls back inside the transaction; take a `pg_dump` of
the precious tables first (governance DB is `postgresql://…@localhost:5432/governance`, separate
from the LCT DB).
**pytest is 9.1.1**: `pytest.ini` declares `pythonpath = .` — without it, pytest 9's bare `pytest`
script fails COLLECTION on `tests/test_benchmark_*`. `requirements.txt` floor is `pytest>=9.0`.
Scheduled CI runs nightly (#722).
Console: reload the browser for `static/*.js`; Playwright-verify UI work against REAL records (Huntington
`4824000:af06722adb` 333k-char handbook; `0602095:6e8db3e114` 258 rasters + a floor-slice PDF at
311 pages; Bentonville `0503060:a5f32ff869` staff-day tier B, `0503060` again for gate@8's write
badge; Broward `1200180` for gate@8 send-back routing; **`0904830:71acfa3404` the 1,017-page
handbook whose floor slice was #834's dead-slice case — the record to Playwright #840 against**).
Drive the Node Playwright from `infrastructure/scraper`; scratch console servers on `:8015`, never
Ian's `:8005`.
Stage 9 incorporate CLI: `python3 -m infrastructure.acquisition.stage9_incorporate <did> [--dry-run]`
(fires automatically on gate@8 approval, #682 — the CLI is the recovery/backfill path); gate@8
send-back routing: `python3 -m infrastructure.acquisition.process_governance.stage8_sendback {route
<did> --route 8->1|8->6|unrouted} [--dry-run]` (#689); re-review audit: `python3 -m
infrastructure.acquisition.stage8_aggregate.rereview [<did> …]` (#713); sign-off preview: `python3
-m infrastructure.scripts.analyze.per_grade_lct_sample`. **Measurement scripts (rerunnable,
read-only, import the LIVE functions)** — all under
`docs/technical-notes/production-quality-control-research/`:
`2026-08-17-{per-page-uncap,timebearing-floor}-measure.py` ·
`2026-08-18-output-overflow-measure.py` (#822 P5) ·
`2026-08-18-roster-hit-measure.py` (#826 — reports today / +normalization / +guard as THREE columns,
because the two halves move the number in opposite directions and a combined figure hides both) ·
`2026-08-19-chrome-first-send-measure.py` (#862/#870 — C1 the invariant, C2 the 244-record
population replayed BOTH ways, C3 the 5 records whose clock times live ONLY in chrome (must never be
send-decided — that arm is #863's watchdog), C4 #868's guarded fallback) ·
`2026-08-21-read-timing-split-measure.py` (#863 — C1 the before-table 104/46/329/2720/17, C2 the
acceptance property split old/new by `text_phase`, C3 the 17 zero-early records, C5 **#873's
login_wall watchdog**, currently CLEAR at population 0) ·
`2026-08-21-geo-ladder-regression-measure.py` (#672 — C1 the live re-route, C2 the 10 regressed rung
pairs CLASSIFIED by mechanism, C5 the plan-aware cost: quote the NOT-in-any-capture-plan column,
never the raw count) ·
`2026-08-22-batch-done-predicate-measure.py` (#671 — C1 the strictly-withdrawing invariant over
43 batches x 3 stages, C2 the 8 false-`done` rows with the AGE of each stale outcome, C3 the #670
boundary (`failed` does not count as finishing), C4 the drain watchdog) ·
`2026-08-18-segment-main-alternate-measure.py` (#841 — scans segment text FROM DISK, since the DB
cannot answer while segment `n_times` is NULL; re-run it after the post-merge re-ingest and its S1
section should report 0 NULL).
Full detail: `docs/PROJECT_HISTORY.md` (2026-08-17/18 entry), `STAGE1-9_*_DESIGN.md`,
`PIPELINE_GOVERNANCE_AND_STATE.md`, `docs/REQUIREMENTS.yaml`.

---

## Current Data Years

**Current School Year:** derived automatically (July-1 rollover) by
`infrastructure/utilities/school_year.py:current_school_year()` — the single source of truth,
never hand-bumped (2026-27 as of this writing). `NCES_PRIMARY_YEAR` in the same module IS
hand-bumped, on ingest of a new CCD (a data event), verified against `lct_calculations` rows.

### Data Year Strategy

| Data Type | Year | Notes |
|-----------|------|-------|
| Primary dataset | 2024-25 | NCES CCD enrollment/staffing (ingested + LCT-calculated 2026-07) |
| Bell schedules | current → 2023-24 | Post-COVID acceptable, search current first; the REQ-026 blend window (span ≤ 2 start-years) arbitrates per calculation |
| COVID exclusion | 2019-20 through 2022-23 | Never use - abnormal schedules |

**Search Order:** current school year first, then back to 2023-24 (all post-COVID)

---

## Database Quick Reference

```bash
# Bell schedule count (source of truth)
python3 -c "
from infrastructure.database.connection import session_scope
from sqlalchemy import text
with session_scope() as s:
    print(s.execute(text('SELECT COUNT(DISTINCT district_id) FROM bell_schedules')).scalar())
"

# Query enrichment status
python -c "
from infrastructure.database.connection import session_scope
from infrastructure.database.queries import print_enrichment_report
with session_scope() as session:
    print_enrichment_report(session)
"
```

**Key Tables:** `districts`, `bell_schedules`, `state_requirements`, `lct_calculations`, `state_district_crosswalk`

---

## Essential Commands

```bash
# Calculate LCT (recommended)
python3 infrastructure/scripts/analyze/calculate_lct_variants.py

# Run SEA integration tests
pytest tests/test_*_integration.py -v

# VERIFICATION - Run after enrichment!
python3 infrastructure/scripts/verify_enrichment.py --quick
```

### Architecture & code-exploration tools (use these to read/verify the codebase — REQ-098)
These are installed (dev-deps) and are the project's standard way to map dependencies and enforce
layering — reach for them before writing or verifying any "what depends on what" narrative:
```bash
lint-imports                 # enforce the acquisition layering contracts (config: pyproject.toml); expect "4 kept, 0 broken"
python3 -c "import grimp; g=grimp.build_graph('infrastructure'); \
  print(sorted(g.find_modules_directly_imported_by('infrastructure.acquisition.stage1_queue.queue_batch')))"
                             # grimp: query the real import graph (what a module imports / is imported by)
vulture infrastructure/acquisition .vulture_whitelist.py    # dead-code sweep vs the audited baseline
                             # (a finding = NEW since 2026-08-17: prove it reachable + whitelist, or delete it)
cd infrastructure/scraper && npm run lint:deps   # Node (.mjs) side — depcruise over the flat *.mjs (no lib/ dir)
pytest tests/test_arch_manifest.py    # cross-boundary FITNESS functions vs arch-manifest.json (#124)
```
> **Caveat (the recurring lesson):** the import tools see **Python/Node imports only**. They do NOT see the
> *environmental* dependencies that often matter most — NCES CSV files read by path/year, **LCT DB
> tables** accessed via the ORM, `subprocess`/`claude -p` calls, OpenRouter API hosts. After the import
> graph, **read the code** for those edges. (Toolchain rationale: `PIPELINE_GOVERNANCE_AND_STATE.md` §10.)
> **`arch-manifest.json` + `tests/test_arch_manifest.py` (#124) now close part of this gap:** the declared
> ground truth for the cross-boundary edges (external processes, guarded entry points, client↔server rule
> literals, stage receipts), enforced as fitness functions. **When you add such an edge, update the manifest**
> — that edit is the review surface, and the suite fails on an undeclared one.

#### Design System for frontend/UI via DesignSync
To access current design resources, use the claude_design MCP (https://api.anthropic.com/v1/design/mcp, auth via /design-login) to import this project: https://claude.ai/design/p/07ef80cc-f2fe-4393-945e-99f1a40b0809

---

## Key Files

| Task | File |
|------|------|
| **Acquisition pipeline (canonical map)** | `docs/ACQUISITION_PIPELINE.md` |
| **Per-stage present-state design notes** | `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` |
| **Live pipeline code** | `infrastructure/acquisition/` (stage1_queue/ … stage9, process_governance/ console) |
| Extraction leaderboard + costs | `docs/technical-notes/learning-loop-reports/EXTRACTION_BENCHMARK_FINDINGS.md` |
| Council design research | `docs/technical-notes/models-and-council-composition/LLM_COUNCIL_RESEARCH_2026-06.md` |
| Decisions, lessons, project history | `docs/PROJECT_HISTORY.md` |
| Data methodology (incl. SPED, QA dashboard) | `docs/METHODOLOGY.md` |
| Database setup | `docs/DATABASE_SETUP.md` |
| SEA integration guide | `SEA_INTEGRATION_GUIDE.md` |
| LCT calculation | `infrastructure/scripts/analyze/calculate_lct_variants.py` |
| Database migrations + ledger | `infrastructure/database/migrations/` (`migrate.py status`) |
| Database queries | `infrastructure/database/queries.py` |

---

## Load Additional Context When Needed

This is the core briefing. Load the right doc for the task:

| Context Needed | Load File |
|----------------|-----------|
| Decisions, lessons, history | `docs/PROJECT_HISTORY.md` |
| Dev setup, workflow, testing, commands, conventions | `docs/GETTING_STARTED.md` |
| Database setup + schema | `docs/DATABASE_SETUP.md` (schema authority = `infrastructure/database/models.py`) |
| Data sources, SEA integrations, ID crosswalks, complex districts | `docs/DATA_SOURCES.md` · `SEA_INTEGRATION_GUIDE.md` |
| Data methodology (LCT, sampling, exclusions, temporal) | `docs/METHODOLOGY.md` |
| The acquisition pipeline + per-stage design notes | `docs/ACQUISITION_PIPELINE.md` (map) → `docs/technical-notes/acquisition-pipeline-stage-design-notes/STAGE*_DESIGN.md` |
| Governance / state model / gate model / console | `docs/technical-notes/PIPELINE_GOVERNANCE_AND_STATE.md` |

**Token Efficiency:** load only what the task needs.

---

## Critical Rules

1. **Docker Required**: Always use `docker-compose up -d` before database operations. Never use `brew services start postgresql` - the `.env` is configured for Docker's PostgreSQL container.
2. **COVID Data Exclusion**: Never use 2019-20 through 2022-23 data
3. **Security Blocks**: ONE-attempt rule for Cloudflare/WAF-protected districts
4. **Temporal Validation**: Data from multiple sources must span ≤3 years
5. **Raw Data**: Never modify files in `data/raw/`
6. **Data Verification**: ALWAYS verify data exists in database before claiming enrichment counts. Never trust dispatch documentation without database verification.
7. **Research before implementing**: When a task involves a non-trivial design decision, an unfamiliar
   failure mode, or a pattern this codebase hasn't established a convention for (state-machine/invariant
   design, a new library, a class of bug just hit), do a web search *before* writing code — not only
   after a bug or a code-review finding surfaces it. Goal: prevention over correction — spend a small,
   cheap search now to avoid a larger token/time cost fixing it later (a wrong implementation, a review
   round-trip, a CI failure). Cite what you found and how it shaped the approach, the same as any other
   research. This does not replace reading this codebase's own conventions first (CLAUDE.md, the
   `docs/technical-notes/` design notes, existing code in the area) — check those before an external
   search, since a local precedent usually beats a generic pattern.

---

## Technical Reference

- **Crosswalk table**: `state_district_crosswalk` - single source of truth for all state mappings
- **SPED baseline**: 2017-18 IDEA 618/CRDC exempt from temporal rule
- **Acquisition pipeline**: the stage-based per-school pipeline in `infrastructure/acquisition/` — see `docs/ACQUISITION_PIPELINE.md` (the retired Crawlee+Ollama API/scraper was archived 2026-06-25 to `data/archive/crawlee-ollama-era-superseded-20260625/`)

For detailed reference, load the appropriate appendix above.
