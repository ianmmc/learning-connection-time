# Stage 3 — Capture: present state & decision log

> **Authority:** Stage 3's purpose, I/O, per-candidate capture logic (Drive tiers, direct fetch, HTML
> render + de-chrome + fingerprint), the console + resilience layer, and manifest recovery — what the
> code does today.
> **Audience:** anyone building on or debugging Stage 3; anyone tracing why a page wasn't captured, was
> captured partially, or is missing a representation.
> **Companions:** `ACQUISITION_PIPELINE.md` §3 (the slim map + flow diagram), Stage 2's note (upstream
> `candidates.json` contract), Stage 4's + Stage 5's notes (downstream — de-chrome *measurement* lives in
> `STAGE5_FILTER_DESIGN.md`), `PIPELINE_GOVERNANCE_AND_STATE.md` (§3 state_event, §11 gates).
> **Update this when:** Stage 3's code behavior changes. Design turns and superseded approaches belong in
> §6 (Decision log), not here.

**Status: BUILT + run live**, including de-chrome, hosting/CMS fingerprinting, the console + resilience
layer (node-owns-shutdown, manifest recovery), iframe/embed capture (REQ-115), follow-up/redo delta-capture
(#174), the `batch_guard` abandoned-batch refusal (#168/#206), and an automated `node:test` harness for the
Node capture layer (REQ-079/#127, PR #239). Drive Tier 2 (OAuth) is deliberately deferred, not built (§5).

**Real redo traffic, 2026-07-27/28 (epic #617's #620 campaign, `batch_00030/31/32`, 25 districts):** the
first genuine follow-up/redo run at this scale since #647 fixed the console's TODO/DONE gate for redo
batches. Stage 3 outcome: 25/25 districts completed — 15 `captured_all`, 9 `captured_partial`, and 1
`failed`-by-subprocess-timeout that nonetheless captured all 119/119 planned records successfully before
the Node subprocess was killed (Orange County FL, `1201440` — see the #670 caveat in §3). This surfaced
three real console defects (#669/#670/#671, all open, epic #96) in the status/observability layer described
in §3 below — the capture WORK itself is correct; what's wrong is what the console displays about it. See
§6's 2026-07-27/28 entry for the full account.

**Code:** `stage3_capture/capture_stage3.py` (`reconcile`/`compute_outcome`/`finish_district`) imports
`common.district_status` (state events), `common.cache_ingest` (the Stage-3 cache hook — governance DB
only, never the LCT DB), and `common.batch_guard` (abandoned-batch refusal — see §3). `stage3_capture/
headless.py` is the batch runner the console drives. The browser work is Node:
`infrastructure/scraper/capture_discovery.mjs` — top-level flow (`segmentChrome`/`dismissModals`/
`stripFragment`/`buildHtmlFingerprint`/`runCapture`/`processTask`/`noteFileResult`/`noteFinalUrl`/
`seedFromPriorCaptures`) plus pure decision-core functions extracted for testability by #127
(`classifyFetchKind`, `driveFormatOutcome`, `categorizeEmbedHost`/`embedCategories`, `segmentBuckets`,
`findEmergentLinks`/`selectEmergentTargets`, `withTimeout`) — + `capture_drive.mjs` (Tier 1 Drive
export-URL logic). Three top-level CLI modes patch already-captured data with no browser/re-capture:
`backfill-fingerprints`, `backfill-segments`, `recompute-cms-hint` (§2c/§2d). Python orchestrates and owns
the registry; Node does the risky/external work — the same split as Stage 2.

---

## 0. Receipt from prior stage / Handoff to next stage

**Receipt from prior stage:** each district's `candidates.json` (Stage 2's deduped, capture-ready URL
list), read but never modified.

**Handoff to next stage:** `captures/<hash>/` directories + `captures.json` per district is Stage 4's
input, read via `find_districts()` (which requires both `discovery.json` and `captures.json`). Stage 3 is
**ungated** — Stage 4 can start as soon as capture completes.

---

## 1. Purpose & I/O

Fetch and persist every candidate page so later stages have local evidence to read — capture *everything
available*, decide which representation to trust downstream.

- **Input — read, never modify:** each district's `candidates.json` under
  `data/raw/lea-website-captures/<id>_<slug>/`.
- **Output, written once per district:**
  - `captures/<hash>/` — one subdirectory per captured URL, `hash = md5(url).slice(0,10)`, holding
    plain-named files (`page.txt`/`page.png`/`page.pdf` for HTML; `original.<ext>` for a direct binary;
    `<format>.<ext>` for a Drive export; plus the de-chrome segments — §2d).
  - `captures.json` — per-candidate record (`url`, `hash`, `tools`/`source`/`found_on`, `ok`, `kind`,
    `final_url`, `files`, `err`, `fingerprint`, `segmented`; `fidelity` (#518: `login_wall`/`soft_404`,
    present only when flagged) and `fetch_status` (#415: the non-2xx status when a binary-content-type
    fetch was refused a write)) — a separate file from `candidates.json`, never a mutation of it.
- **Gate:** **none** (Stages 2/3/4 ungated). Registry outcome: `captured_all` / `captured_partial` /
  `capture_failed_all` + a short `notes` rollup.

---

## 2. The design (settled)

### 2a. Reconciliation — filesystem-authoritative, redo-aware for follow-up batches
`captures.json` on disk IS "Stage 3 done"; the registry is a cache, reconciled *from* disk. Disk-ahead
reconciles up silently and skips; **registry-ahead-of-disk raises `SystemExit` CONTROL FAILURE** and halts
the whole run — the same severity as Stage 2's reconcile (a registry claiming completion the filesystem
can't back up signals lost data or a bad migration, not a per-district problem). This first-run behavior is
the default, but it is not the only mode: see CLAUDE.md's **three batch types** (`first-run`/`follow-up`/
`benchmark`) — Stage 3 now genuinely branches on `batch_type`.

**One bypass to that halt (#572):** before raising, `reconcile()` checks `DS.remediation_receipt(did)` — if
a decontamination restore point exists on disk for the district (within its trust window), the halt is
skipped and the district is queued to capture fresh instead. The full mechanism, including its time-bound
window and known cross-stage residual: `PIPELINE_GOVERNANCE_AND_STATE.md` §11l.

`reconcile(districts, registry, *, redo=False)` takes a `redo` flag; `headless.py`'s `run_batch()` passes
`redo=batch.get("batch_type") == "follow-up"`. When `redo=True`, an existing `captures.json` no longer means
skip — every district in a follow-up batch is `todo` regardless of on-disk state (issue #174, the
"deliberate redo"). The registry-ahead-of-disk control failure is unchanged in either mode. The delta
capture itself happens on the Node side: `runCapture()` calls `seedFromPriorCaptures()` (capture_discovery
.mjs) to seed each district's in-memory record set + `seen` set from its prior round's `captures.json`
before dispatching any new fetches, so a follow-up only re-hits the URL delta (new/changed candidates), not
every URL again. One rule governs replacement: **a prior record with `ok === false` whose URL is a
candidate again this round is dropped, not carried** — the retry's fresh record replaces it rather than
sitting behind it forever; every other prior record (successes, and failures not being retried) is kept
verbatim. The manifest `writeVersioned()` writes at the end of a follow-up run is therefore the **union** of
the prior round's records plus this round's new/replaced ones, never a slice — Stage 5 does a per-district
delete+rebuild ingest keyed off the *complete* manifest, so a partial file would silently drop prior
evidence from Stage 5 onward.

### 2b. Per-candidate branch logic
Every URL (and any emergent candidate) is `stripFragment()`-normalized before the `seen` dedup, then routed:
1. **Google Drive/Docs/Sheets/Slides** (checked first) — **Tier 1, unauthenticated export URL** for
   recognized single-file patterns: Docs → PDF + Markdown, Slides → PDF, Sheets → CSV + PDF. **Tier 2
   (OAuth Drive API)** — the only path for folder enumeration and Tier-1 failures — is designed, not
   built (§5). An OAuth/Drive failure is a **per-item flag** (`err: "needs_oauth_reauth"`), never a run
   halt — one stuck Drive item says nothing about the rest of the batch.
2. **Direct PDF/image fetch** (non-Google) — plain HTTP GET, byte-for-byte; never `page.pdf()` a URL that
   is already a PDF.
3. **Generic HTML render** — `goto(domcontentloaded)` + a wait (§2's #225 entry — `GOTO_WAIT`,
   shared by all three goto sites), then **modal dismissal**, then
   innerText→`.txt`, full-page screenshot→`.png`, and **`page.pdf()` unconditionally** (removes the need
   for a Tier-1→2 escalation trigger — capture both, decide downstream). **Emergent candidates:** scan
   anchors whose text/href match `SCHED_KW` → new candidate, exactly one hop, never recursive
   (`source: "emergent"`, `found_on`) — catches CDN-hosted PDFs too, not just Drive/Docs.

**File-write correctness (fable review issue #18):** the screenshot's manifest entry (`rec.files.png`) is
set only in the success `.then()`, mirroring the PDF path — a screenshot timeout leaves `rec.png_err`
instead of a phantom manifest claim. `page.txt` is written and its manifest entry set immediately after
the successful `writeFileSync` call.

### 2c. Hosting/CMS fingerprint + iframe/embed (per record, raw signals only)
`buildHtmlFingerprint`/`buildFetchFingerprint` record, at the **URL level**, facts gathered for free from
data the capture already held: `final_host`, `server`, `powered_by`, `cdn_hints[]`, `meta_generator`,
`resource_hosts[]` (off-domain script/link/img hosts, cap 20), `js_dependent`, and `cms_hint`. **Host
matching is dot-boundary, not a bare suffix check (#416):** the shared `hostMatches(host, suffix)` —
`host === suffix || host.endsWith('.' + suffix)` — replaced a buggy bare `host.endsWith(cms)` that let
`myfinalsite.net` false-match the CMS vendor `finalsite.net`. `hostMatches` (JS) and `_host_matches`
(Python, `common/discover.py`) are pinned to identical behavior by a shared cross-language golden-vector
fixture, `common/config/cms_host_match_cases.json` (11 cases: exact match, dotted/deep subdomain,
dotless-superstring negatives, edge cases), declared in `arch-manifest.json`'s `shared_config` and
consumed by both `capture_fingerprint.test.mjs` and `tests/test_cms_host_parity.py`. **Iframe/embed
detection (REQ-115):** `iframe_srcs[]`
(categorized social/feed · calendar · doc-viewer · other) + `embed_present`, a structural, vendor-agnostic
signal for the `embedded_feed`/embedded-calendar confounders Stage 5 screens for. Direct PDF/image/Drive
records get a reduced (no-DOM) fingerprint. Facts, not classification — real CMS ID is a later pure
function over these signals, refinable retroactively without re-capturing. `backfill-fingerprints` and
`recompute-cms-hint` apply a human-approved `cms_hosts`/signal change to already-captured data with no
browser, no re-capture.

**Capture-completeness note:** both the live capture (`captureInto`, capture_discovery.mjs:608-610) and the
fingerprint-backfill path (`htmlFingerprintFor`, lines 479-481) iterate `page.frames()` and concatenate
`document.body.innerText` across the main document **and every accessible child frame**, not just the top
document — so same-origin iframe content IS captured into `page.txt` today. Only a genuinely cross-origin
frame is skipped (browser-blocked; caught by a per-frame try/catch and silently dropped, logged nowhere).
For that residual cross-origin case, the visual path (screenshot → raster → tesseract OCR) still renders
the iframe's content, so it remains recoverable via the vision/OCR tier even when `page.txt` can't see it.
`embed_present`/`iframe_srcs[]` flag such pages so routing can prefer the visual rep when needed.

### 2d. DOM de-chrome segmentation (REQ-091, measured)
CMS chrome (a footer "Building Hours", a school-switcher nav, footer board/athletics links) injects false
signal. The fix lives at Stage 3, at render time — only `innerText` is persisted, so by Stage 4 the DOM
structure that identifies a footer is gone. **Segment, don't strip:** `segmentChrome()` captures
`innerText` of structural landmarks (`<header>`/`<footer>`/`<nav>` + ARIA equivalents — the landmark set
is **config-as-data**: `DE_CHROME_LANDMARKS` = `loadConfigValues('de_chrome_landmarks')`, threaded as the
`landmarks` param, so it widens by config edit not code) as separate **additive** representations
(`page.main/header/footer/nav.txt`) alongside the full `page.txt` — which is now written from the **same
read** (§2d-1), not from an earlier one.
Header/footer are kept because real *school hours* sometimes live there, not only confounding building
hours. `backfill-segments` applies it to already-captured data. Measured: category-guess 0.43→0.60,
topology 0.6→0.8 — a strong win (detail in `STAGE5_FILTER_DESIGN.md`). Stage 5's V2 scoring
computes time signals over the **max-evidence source** (main ∪ chrome ∪ best raw rep), never main
exclusively — de-chrome stays for keyword/category signal, never suppresses time evidence.
**Both call sites (`captureInto`, `runBackfillSegments`) route through `segmentWithTimeout(page)`
(#375)** — a shared `withTimeout(segmentChrome(page, DE_CHROME_LANDMARKS), OP_TIMEOUT_MS, 'segment')`
wrapper. Before this, both called `segmentChrome` directly and unwrapped: a `page.evaluate` with no
native Playwright deadline, so a wedged page could hang a capture worker indefinitely (in the backfill
path, this also risked losing the whole run's manifest writes, since those only happen after every
worker resolves).

### 2d-1. ONE read: `page.txt` and the segments are the same instant (#863, REQ-177)

Until 2026-08-21 `page.txt` was read at `domcontentloaded`+2.5s and the segments at **end of capture**,
after the full-page screenshot and `page.pdf()`. `page.main.txt` is `body.innerText` minus landmarks and
`page.txt` is `body.innerText`, so main is a subset **by construction — only if read at the same instant**,
and it was not. Measured over 3,095 records carrying both: **104** where main had MORE chars than
page.txt, **46** with more clock times, and **17** where page.txt held **zero** clock times and main held
some. Lazily-hydrating widgets (Finalsite tab/accordion panels) are the population.

`segmentChrome` now returns `full` — `body.innerText` read in the **same `page.evaluate`**, one statement
before the chrome removal that produces `main` — and `page.txt` is re-persisted from `full` plus the
non-main frames. The subset relation is constructive, not coincidental.

Four deliberate non-changes, each load-bearing:
- **`detectChallenge` stays on the early read** — a WAF interstitial must abort before a screenshot/PDF is
  spent on it (one-attempt, Critical Rule 3).
- **`js_dependent` stays on the early read** — it is a FINGERPRINT input, and the basis must stay
  backward-compatible or every record re-hashes and forces a mass re-review.
- **Non-main frames are read BEFORE segmentation** — an `<iframe>` nested in a `<footer>`/`<nav>` is
  detached by the removal and its frame dies; reading them after would silently drop text `page.txt` has
  always carried.
- **`fidelityFlags` moved ONTO the persisted text** — their contract is "derived only from persisted facts
  (url/final_url, page.txt, has_password)" and `recompute-fidelity` re-derives from disk, so leaving them
  on the early text would make live and recompute disagree on exactly the changed records. (#873 argued
  the reverse — that mixing an early `hasPassword` with late text can lose a `login_wall`. Real mechanism,
  measured population **zero**, and note the operative cause is the LENGTH clause, not the instant mixing:
  reading `hasPassword` late too yields the identical verdict. Watchdog: C5 of
  `2026-08-21-read-timing-split-measure.py`.)

`page.txt` is written from the early read FIRST and overwritten only on success, so no failure path loses
the file. **`text_phase`** (`final`|`early`) records which read is on disk — a Stage-3 receipt field, not a
DB column (ingest reads a fixed key list). `resolvePersistedText()` is the one pure place that decides,
and it distinguishes a late read that FAILED (`segmentChrome` returns `null`) from one that legitimately
came back EMPTY (`{full:'', …}`) — conflating those was #874, which discarded a good iframe read and
reproduced #863. `segmented:false` with `text_phase:'final'` is a valid pair, not a contradiction (#875):
the fields describe whether the segment FILES reached disk and which read is in `page.txt`.

**The corpus-wide property only clears on RE-CAPTURE** — legacy records keep their split reads, and the
measurement script reports `NOTHING MEASURED` for the post-fix population until re-captured records exist,
rather than a permanent false FAIL. First landed piece of **epic #864**; #643's render-facts sidecar is the
full form.

### 2e. Emergent dedup includes redirect targets (fable review issue #44)
`noteFinalUrl()` adds a captured page's `stripFragment(final_url)` to the `seen` set right after capture —
so an emergent anchor pointing at a URL that a *different* candidate redirects to is recognized as the
same content and not captured twice.

### 2f. Outcome rollup + single registry write
`compute_outcome()` rolls per-candidate `ok`/`err` into `captured_all`/`captured_partial`/
`capture_failed_all` + a `notes` counter of `err` reasons. The registry holds this rollup only — never a
live array of open issues; a human generates the triage list on demand by scanning `captures.json`. One
`record_stage()` write per district at completion. **Redo is versioned** (`writeVersioned` renames aside
with a UTC timestamp), never an overwrite.

### 2g. Abandoned-batch refusal (`batch_guard`, #168/#206)
`common/batch_guard.py` gives every Stage 3 write path a check against a batch that has been marked
terminal-`abandoned`, so no one can accidentally write more work into a batch that's been formally closed
out. `assert_runnable(sess, batch_id)` is **batch-grain**: `headless.py`'s `run_batch()` calls it before
doing anything else. `assert_district_runnable(sess, district_dir)` is **district-grain**:
`capture_stage3.py`'s `finish` and `reconstruct` CLI subcommands call it immediately before writing
`captures.json` state + a `state_event`, so even a district-scoped manual/recovery write is refused if that
district's artifacts belong to an abandoned batch. Either check failing raises `SystemExit` — the same
control-failure posture as reconciliation (§2a): an abandoned batch receiving a new write is a governance
bug, not a routine per-district condition, so it halts rather than silently proceeding.

---

## 3. Console + resilience layer

Stage 3 is **ungated**, so the console is **status/observability + a run trigger** (next human gate =
`gate@5`). `static/stage3.js` + `/api/capture/{batch_id}` (status) + `/api/capture/{batch_id}/run`
(background job, `stage3_capture/headless.py`). The batch is resolved from the **DB working store**
(`batch_store.to_view`, included-only), never the on-disk receipt.

**Reads the DB cross-stage cache**, not `captures.json` off disk — the Stage-3 finish hook
(`common.cache_ingest.cache_capture`) upserts each district's slice on completion (per-district
DELETE-then-UPSERT, so re-captured/removed URLs' rows never linger). Readout: per-district outcome +
capture/ok/failed/emergent counts, the **failure-reason breakdown** (`err`, incl. `needs_oauth_reauth`/WAF
blocks), and the batch-level **CMS/host distribution**. NOT a live PNG feed (low governance value). A
`done`-on-disk-but-not-in-cache district is self-healing (ingested on first console view).

**Caveat (#669, open, epic #96): the per-district counts are not scoped to a run.** `status_for_batch`'s
`rows_by_did` query (`SELECT ... FROM capture WHERE district_id = ANY(:ids)`) filters by district id only —
no `batch_id`/run column exists on the `capture` cache table — so `n_captures`/`n_ok`/`n_failed`/
`n_emergent` reflect whatever the cache currently holds for that district, not necessarily what the batch
being viewed just did. On an ordinary (non-redo) batch this is moot (one run per district, ever). On a redo
batch it means the numbers shown beside a district can be stale — from an earlier run — until this run's own
`finish_district` overwrites that district's cache slice. **Separately, and unconditionally wrong today:**
the Stage 3 confirm-run dialog's copy (`static/stage3.js`) reads *"Already-captured districts are skipped"*
— true for a first-run/ordinary batch, **false for a redo batch**, where `reconcile(redo=True)` does the
opposite (every district in the batch is `todo` regardless of on-disk state, §2a).

**No-link districts skip Playwright:** a district whose Stage-2 outcome is `manual_flag_all` (empty
`candidates.json`) is dropped before dispatch — no Node subprocess, no empty Stage-3 artifact; it stays
terminal at Stage 2.

**Per-district status (`status_for_batch`):** `awaiting_discovery` · `manual_flag_all` (terminal) · `todo`
· `done` · `failed`/`timed_out` (read from the latest `capture` state_event, not a captures.json artifact;
retriable). The rollup adds `resolved = done + flagged`; a batch's Stage 3 is complete when
`resolved == total`.

**Caveat (#670, open, epic #96): on an ORDINARY batch a late-timing-out district still renders as clean
`done` with its failure masked.** The `failed_caps` check (the latest `capture` state_event) is consulted
only inside the `if did not in captured:` branch. A district whose Node subprocess captured everything (a
fully-populated `captures.json` on disk) and *then* hit the Python-side subprocess-timeout backstop (§3's
`CAPTURE_TIMEOUT_S`) has both a `TimeoutExpired` state_event AND a complete manifest — and for an ordinary
batch `captured` is pure disk existence, so artifact-existence wins and no failure indicator appears.
Measured live on the #620 campaign: Orange County FL (`1201440`) recorded `TimeoutExpired` while holding
119/119 successfully-captured records; the console showed it as done. **#671 fixed this for REDO batches**
(see below — a stale artifact no longer confers doneness, and `failed` does not count as finishing, so
`1201440` now reads `timed_out`); the ordinary-batch residue and the separate *completeness* question —
whether those 119 records are the whole set or a truncated prefix, unanswerable without #623's
intended-vs-achieved receipt counts — remain #670's own scope.

**#671 (FIXED 2026-08-22): on a redo batch, every district holding a prior artifact used to read `done` —
with the PRIOR run's metrics — for most or all of the current run's duration.** `_dispatch_and_finish`
stamps the `dispatched` state_event for **every district in `todo`, up front, before the per-district
capture loop starts** (§3's dispatch loop above). The redo branch was `captured &=
DS.dispatched_by_batch(...)` (added by #647 to fix the TODO/DONE gate — that fix was correct, and this
defect was in the *rule it scoped with*, not in the scoping). It could only ask "did this batch dispatch
this district," not "has this run's own capture landed" — so from the moment dispatch was stamped until
that district's own `finish_district` overwrote its `captures.json`/cache slice, the console showed
`done` over stale, pre-redo data. Measured false-done windows on the campaign: 45s shortest, ~22min
median, 38m15s longest.

The conjunct is now **`DS.completed_by_batch`** — dispatched by this batch **and a stage OUTCOME
(`stage IS NOT NULL`) after that dispatch** — the one home for the rule, so the same correction reached
Stage 2 and Stage 4's identical `stale-disk ∧ …` views in the same edit. Keyed on event ORDER rather
than the completion event's `batch_id`, because completion events are only stamped from #647 onward
(stage-3: 28 of 147 rows) and keying on the stamp would declare 18 historical follow-up batches un-run.
Non-`done` districts take the zeroed row defaults, so the stale metrics stopped rendering as current
with no second change.

**This also retired #670's precedence half here.** `failed` deliberately does NOT count as finishing, so
Orange County FL (`1201440`) — `TimeoutExpired` while holding 119/119 records, whose only stage outcome
is `batch_00000`'s benchmark injection from three weeks before `batch_00031` dispatched it — now reaches
the failure branch and reads `timed_out` instead of a clean `done`. Still open in #670: ORDINARY batches
(where `captured` remains pure disk existence), and whether a truncated capture is *detectable* at all,
which needs #623's intended-vs-achieved receipt counts. Rerunnable evidence:
`docs/technical-notes/production-quality-control-research/2026-08-22-batch-done-predicate-measure.py`.

**Shared labels + left-pane progress:** `static/outcomes.js` (`outcomeBadge`, `progressBadge`) — the same
elements Stage 2/4 use. Honest counts: no-link districts report separately, never folded into the
captured count. The active batch's chip live-syncs to the header during a run.

**Capture hardening:** `page.pdf()`/`screenshot()` wrapped in a 45s timeout race; direct fetch is a 20s
`AbortSignal`; `goto` is 30s. Emergent candidates capped at 25/district.

**Node-owns-shutdown — a timeout writes a PARTIAL manifest, never orphans work.** `runCapture(ROOT, CONC,
only, deadlineMs)`: once the deadline passes, workers stop pulling new pages, in-flight pages finish
(bounded by the per-page timeouts above), un-started candidates are recorded `not_attempted`, and
`captures.json` is **always written**. A timeout is `captured_partial` with the work preserved, not lost.
Python's subprocess timeout is a backstop that only fires on a true Node hang.

**One task exception can no longer abort every district's manifest (fable review issue #35).** The entire
per-task body — hash, directory creation, capture logic, and the manifest-record push — is wrapped in one
try/catch, and workers run under `Promise.allSettled` rather than `Promise.all`; a district-level failure
(ENOSPC, EACCES) becomes a per-record error entry, and every other district's manifest still gets written
in a `finally`. This closes the last gap in the node-owns-shutdown guarantee.

**Manifest recovery** (`capture_stage3.py reconstruct <district_id> [--manual-file PATH --manual-url URL]`)
rebuilds `captures.json` from on-disk per-URL folders for already-orphaned districts. Recovery-only:
refuses to overwrite an existing manifest; emergent folders are unrecoverable (the URL was in-memory, the
hash is one-way) and are left on disk, out of the manifest. **URL-hash normalization matches Node's `new
URL().toString()`** (lowercase host, IDN punycode, default-port drop, WHATWG dot-segment removal,
percent-encoding without double-encoding — fable review issue #43) so a reconstruct run finds the right
folder for the same candidate URL Node would have hashed. **Reconstructed Drive exports map to the `bin`
key** (fable review issue #42) — Stage 4 reads `files.bin` for any non-text binary, so a recovered generic
Drive download (`file.pdf`, previously keyed `"file"` and silently skipped) is now readable.
`--manual-*` drops a human-sourced file in as a `source:"manual"` record.

---

## 4. Tool/code provenance
Active: `capture_discovery.mjs` (+ `capture_drive.mjs`). The modal-dismissal + `page.pdf()` logic was
ported from `capturer.ts` (confirmed pure-Playwright, zero coupling to the dead Crawlee/Express design).
**Superseded, do not revive:** `mapper.ts`'s `PlaywrightCrawler` (the abandoned Jan-2026 blind-site-mapping
design); `google_drive_handler.py`'s Playwright-preview + Gemini tiers (only its Tier-1 export logic
carried forward into `capture_drive.mjs`).

**Automated test suite (REQ-079, github #127, PR #239).** The Node capture layer has a `node:test` harness
under `infrastructure/scraper/`, wired into CI's `node-tests` job: `capture_browser.test.mjs` (a real
headless-Chromium harness using `page.route()` fixtures to exercise `dismissModals`/`readAnchors`/
`domFingerprint`/`segmentChrome` against actual DOM behavior, not mocks — self-skips if Chromium isn't
installed on the runner), `capture_dispatch.test.mjs` (`classifyFetchKind`/`driveFormatOutcome`/
`withTimeout`/`segmentBuckets`), `capture_drive.test.mjs`, `capture_emergent.test.mjs`
(`findEmergentLinks`/`selectEmergentTargets`), and `capture_records.test.mjs`. This closes the gap §6's
2026-07-02 entry left open (no automated harness existed for `capture_discovery.mjs`'s browser-driving
logic) — the #127 refactor pulled the decision cores listed in §0 out of the monolithic capture flow
specifically so they'd be unit-testable without a live browser, then added the browser-driven suite on top
for the DOM-touching functions that can't be faked that way.

## 5. Open decisions
- **Drive Tier 2 (OAuth Drive API) — deferred, not blocked** (REQ-078, `must`→`should`). Build it when a
  real Drive link actually needs it; zero real links have needed it so far. (tracked: #115)
- **Duplicate-PDF dedup — deliberately NOT built.** A cross-directory content-hash scan for a negligible
  current benefit; recorded watch-item.
- **Partial-retry — RESOLVED 2026-07-19 (#116, see the change log).** `headless retry <batch_id>` /
  `retry_partial()` re-attempts a captured district's retryable failures via the Node delta re-run in
  `retryable-only` mode; one-attempt errs carry verbatim.
- **Emergent recovery — RESOLVED 2026-07-19 (#117, see the change log).** The capture journals each
  completed record (`captures.journal.jsonl`); reconstruction consumes it, recovering emergent
  captures full-fidelity.
- **Politeness / rate-limiting.** A capture burst can trigger transient stalls on a target site; consider
  a small per-request delay or lower per-district concurrency if this recurs.
- **Per-district deadline can truncate large districts (#225, logged 2026-07-11, not yet fixed).** The
  math: (per-URL time limit × total URLs) can exceed `CAPTURE_DEADLINE_S` for a large enough district,
  independent of any per-URL slowness bug — observed on Jefferson County AL (85/112 captured before
  cutoff, 100% of what was captured usable). Node-owns-shutdown (§3) means this degrades to
  `captured_partial` rather than lost work, but the district is still incomplete. The fix belongs at the
  capacity-planning level (raise the deadline for large districts, shard the capture, or accept partial +
  a targeted top-up), not a one-off retry — see §6's newest entry for the full finding.

---

## 6. Decision log (chronological)

_Preserved verbatim from the retired flow diagram's decision log; `gate@5` was "CP-B" at the time of
writing (governance §11). Paths reflect the original `infrastructure/acquisition/discovery/` location
before the package promotion to `stage3_capture/`._

**2026-06-23 — Stage 3 (Capture) design conversation: grounded several open questions in what's actually in the codebase rather than the docs' claims about it.** Before any Stage 3 code is written:
- `capture_discovery.mjs` (the real, active capture script — 73 lines, bare Playwright + `fetch()`, no Crawlee) already implements the `captures/` subdirectory + MD5-hash-of-URL naming pattern independently converged on in conversation, and already writes a separate per-district `captures.json` (url → hash → files) rather than mutating `candidates.json` — which answers "should capture results get logged back to candidates.json" with "there's already a cleaner pattern, no write-once policy exception needed."
- **Confirmed Crawlee is genuinely dead code, not just superseded in spirit.** `mapper.ts`'s `PlaywrightCrawler` usage is literally the abandoned Jan-2026 blind-site-mapping design (its own docstring: "to enable intelligent URL ranking by Ollama") and isn't imported by anything in the active pipeline.
- **`google_drive_handler.py` already has a 3-tier Drive fallback (direct download → Playwright preview → Gemini API) anticipating exactly the Gemini question the user raised — but the Gemini tier is an unimplemented stub, and the Drive-folder case (vs. a direct file link) isn't handled at all (`DRIVE_PATTERNS` only matches file-level URLs).** It also depends on a separate Express microservice (`server.ts`, `localhost:3000`) nothing else in the active pipeline runs.
- **No modal-dismissal logic actually exists in the live capture path**, despite `ACQUISITION_PIPELINE.md` claiming it was "salvaged" from `capturer.ts` — confirmed by reading the real script. A real, previously-undocumented gap, agreed to fix now rather than defer.
- `page.pdf()` does not exist anywhere in the current capture script — confirmed it's a genuine addition, not a config flip. User decision: run it unconditionally on every HTML page captured (no multi-column-detection trigger), since it's free local compute and removes the need to ever define the "Tier 1→2 escalation trigger" that `ACQUISITION_PIPELINE.md`'s reader-routing spec had left deliberately open and unsolved.
- **Drive/Docs API research (Gemini MCP + Perplexity, cross-checked against each other):** `files.list` (folder enumeration) always requires OAuth/service account, even for fully public folders — no API-key-only path exists. The unauthenticated export-URL trick still works for "anyone with the link" content. An image-only Doc/Slide exports to an image-in-a-PDF with no text layer — not a dead end, it's the same shape as a scanned PDF and routes into the existing Tier 2.5 OCR path. **One real discrepancy caught between the two sources:** Gemini claimed refresh tokens expire after 6 months of inactivity as documented Google policy; a citation-backed Perplexity follow-up found no such rule in Google's actual OAuth docs — the only documented forced-short-lifetime case is leaving the OAuth consent screen in "Testing" publishing status (7-day tokens), unrelated to inactivity or personal/unverified-app status. Architectural implication: OAuth is only actually needed for folder *enumeration* — individual Docs/Sheets/Slides/Drive-file retrieval already works via the existing unauthenticated path.

**2026-06-23 — Stage 3 (Capture) design closed out and written into `ACQUISITION_PIPELINE.md` + this diagram.** Final three open points resolved before formalizing:
- **OAuth/Drive failure handling: a per-item flag, not a batch halt.** Unlike the Stage 2 billing CONTROL FAILURE (where one failure means every subsequent call fails identically), one stuck Drive item says nothing about the rest of the batch — so it's recorded (`err: "needs_oauth_reauth"` in that candidate's `captures.json` record) and capture moves on. Explicitly rejected: a live array of open issues inside the registry — the registry holds a status rollup only, and a human generates the actual triage array on demand.
- **Dropped the Gemini-API tier too, not just Playwright-preview.** Reasoning: Gemini would only end up calling the same Drive API that already failed. The original 3-tier design (direct download → Playwright preview → Gemini) collapses to 2 tiers (unauthenticated export URL → OAuth Drive API).
- **Export formats, finalized:** Docs → PDF + Markdown (a genuine cheap win — skips `pdftotext` entirely for born-digital Docs). Slides → PDF only. Sheets → CSV + PDF (PDF specifically catches an image pasted into a spreadsheet cell).

**2026-06-23 — clarified scope of the emergent-candidate path: explicitly for CDN-hosted materials too, not just Drive/Docs.** The real motivating case is broader — an on-domain page Discovery *did* find can easily link to a bell-schedule PDF hosted off-domain on a CMS/CDN host (Finalsite, BoardDocs, SchoolWires/Blackboard, an S3 bucket) that Discovery's domain-scoped search would never surface directly.

**2026-06-23 — Stage 3 implemented; one real bug caught by the user reviewing real output, not by anything written down beforehand.** Built `capture_stage3.py`, `capture_drive.mjs`, extended `capture_discovery.mjs` with modal dismissal, unconditional `page.pdf()`, one-hop emergent-candidate discovery, and the Drive Tier 1 branch.
- **The bug:** the original design said "capture directory per URL," but what got built collapsed this into flat hash-*prefixed* files sharing one district-wide `captures/` folder — only preserving the hashing half of the intent, not the per-URL grouping half. Caught by the user looking at real output mid-run.
- **Fix:** `capture_discovery.mjs` now creates `captures/<hash>/` per URL, with plain filenames inside. Both docs corrected; the first full-batch run was caught, stopped, and re-run after this fix.

**2026-06-23 — first real full-batch Stage 3 run, all 12 `batch_00001` districts, found a second real bug and confirmed the emergent-candidate path's value with hard numbers.** 112 original candidates grew to 173 total URLs on the first pass, all captured (0 failures) — but the count revealed a problem.
- **The bug:** Stroudsburg alone contributed 35 of 61 emergent candidates — mostly URL-fragment variants of pages already captured (`.../bell_schedules/#pageTitle`), re-rendered/re-screenshotted/re-PDF'd 2-3x because the `seen` dedup checked exact URL strings without stripping the fragment first.
- **Fix:** added `stripFragment()`, applied both when seeding the initial candidate set and when an emergent link is found. Total URLs dropped 173 → 150 (61 → 38 emergent) with genuine duplicates gone.
- **Net result:** the emergent-candidate path found 38 genuinely new pages Discovery never directly surfaced, zero capture failures. Final state: all 12 districts `captured_all`, 150/150 URLs, zero errors.

**2026-06-23 — Drive Tier 2 (OAuth) deliberately deferred, not just blocked on the GCP prerequisite.** `batch_00001` produced zero Drive/folder links needing it. User's explicit call: build Tier 2 when a real link is actually hit, not speculatively ahead of any evidence. REQ-078 downgraded `must`→`should`.

**2026-06-24 — Stage 3 hosting/CMS fingerprinting added, backfilled across all 12 districts, and immediately earned its keep.** Record what platform/CMS/host generates each captured page, at the URL level (school subdomains often differ from the district root). Grounded against the code first — found the capture was already *holding and discarding* most of the signal (Response headers, an existing DOM scan). Raw HTML is never saved (only innerText), so DOM signals must be read at render time.
- **Architecture: record raw facts, don't classify the CMS inline** (the one cheap exception: `cms_hint`, a host-suffix match against `CMS_HOSTS`) — real classification is a later pure function, refinable retroactively without re-capturing 20K districts.
- **Parity via backfill, not full re-capture** — re-running capture over already-Stage-4 districts would mix fresh Stage-3 artifacts with existing Stage-4 outputs and risk content drift. `backfill-fingerprints` patches only the fingerprint field. Ran live: 150/150 records, 0 errors.
- **The finding:** `cms_hint` came back `null` on all 150 — correctly, because the real platforms in this sample aren't in the discovery-era `CMS_HOSTS`. Raw `resource_hosts` revealed them: **SharpSchool** (51), **Apptegy/Thrillshare** (~24), **Educational Networks** (25).

**2026-06-24 — `CMS_HOSTS` grown by human approval, encoding a standing governance rule.** The fingerprint finding was acted on: `sharpschool.com`/`apptegy.net`/`thrillshare.com`/`educationalnetworks.net` added to `CMS_HOSTS` in both `discover.py` and `capture_discovery.mjs`. This also makes Stage 2's `gate()` keep slug-matched URLs on those hosts it previously rejected as off-district. **Standing governance rule: every `CMS_HOSTS` addition is human-in-the-loop, never automated, and must be a school-district-specific vendor, never a general host/CDN** — `amazonaws.com` deliberately NOT added despite appearing in the data. *(Later migrated to the `cms_hosts` config-as-data knob — single source of truth, no hand-syncing.)*

**2026-06-25 — Stage 3 DOM segmentation (header/footer/nav vs. main) designed, then built + measured (REQ-091).** Stage 5's batch_00001 review surfaced CMS *chrome* as the single biggest source of false signal: a global footer's "Building Hours" injects a fake start/end pair, a school-switcher nav inflates `roster_school_names_hit` into a false `hub` topology. Key realization: the fix has to live at Stage 3, at render time — the DOM structure that identifies a footer is gone by Stage 4.
- **Segment, don't strip.** Additive representations (`page.main/header/footer/nav.txt`) alongside the untouched full `page.txt` — never lossy. Header/footer are kept because real *school hours* sometimes live there too.
- **Built + measured:** the live backfill on batch_00001 (140/140 html, 123/150 de-chromed) measured **category-guess 0.43→0.60, topology 0.6→0.8**, tier A unchanged. Side-effect: footer-negative stripping floated 24 non-targets C→B — the tier-C `neg_dominant` retune became a Stage-5 follow-up.

**2026-06-28/29 — the console + resilience layer built and hardened over live runs (batch_00002–00005, REQ-110).** The core fix: `captures.json` used to be written once at end-of-run, so Python's subprocess timeout SIGKILLing Node mid-run discarded the manifest for ALL completed work (Brookwood, Fairfield, and a 534-file LAS CRUCES capture all read as total failures despite the files existing on disk). Fixed via node-owns-shutdown (§3) — a timeout now writes a partial manifest instead of losing everything. Manifest recovery (`reconstruct`) built as the interim path for already-orphaned districts (recovered Brookwood 5/15, Fairfield 8/9, LAS CRUCES 78/128 live) and doubled as the interim manual-follow-up mechanism (Brookwood's parent handbook, pp. 32-33, added via `--manual-file`).

**2026-07-01 — Stage 3 gained iframe/embed capture + `cms_hint` promotion (REQ-115).** Two Stage-5 V2 findings — `embedded_feed` pollution and embedded-calendar clusters — turned out to be structural (an `<iframe>`/`<embed>` pointing at a known third-party host), not a heuristic Stage 5 could reliably guess from URL/keyword patterns alone. See §2c.

**2026-07-02 — capture-manifest integrity gaps closed (fable review issues #18, #35, #42, #43, #44).** Adversarial review found the screenshot success path could leave a phantom `files.png` manifest entry on timeout (fixed — mirrors the pdf `.then()` pattern), a single task exception could abort every district's manifest in a run (fixed — whole-task try/catch + `Promise.allSettled`), emergent dedup didn't account for redirect targets (fixed — `noteFinalUrl`), and the Python-side reconstruct tool's URL normalization diverged from Node's `new URL()` and mis-keyed generic Drive downloads (both fixed — see §3). See §2b/§2e for the present-state description.

**2026-07-11 — capture throughput truncates large/slow districts under the per-district deadline
(#225, logged, not yet fixed).** Observed in the batch_00013 shakedown: Jefferson County (AL) captured
85/112 URLs (100% of those captured were usable) before `CAPTURE_DEADLINE_S` cut the district off — the
math Ian named live: (per-URL time limit × total URLs) can exceed the whole-district time limit for a
large enough district, independent of any per-URL slowness bug. Not an ad hoc re-trigger candidate (Ian
explicitly declined a bandage re-capture) — the fix belongs at the capacity-planning level (raise the
district deadline for large districts, shard the capture, or accept partial + a targeted top-up), not a
one-off retry. Whether Jefferson's partial 85 compromises the concurrent #122 shakedown was assessed and
confirmed NOT a conflict — logged for later, independent of the loop-validation work.

**2026-07-12 — doc audit: corrected this note against code that had moved on without it.** An independent
audit found the §2c iframe-capture note still described pre-REQ-115-fix behavior (page.txt now DOES
capture same-origin iframe innerText via a `page.frames()` loop, added alongside the REQ-115 iframe/embed
*detection* work but never reflected in this note's prose); and found four undocumented, already-shipped
mechanisms: the follow-up/redo delta-capture path (#174, `reconcile`'s `redo` param +
`seedFromPriorCaptures`), `batch_guard`'s abandoned-batch refusal (#168/#206), the #127/PR #239 `node:test`
harness, and the pure decision-core functions #127 extracted for testability. All four folded into §0/§2a/
§2c/§2g/§4 above; §5 gained a pointer to the #225 capacity-planning finding already in this log.

**2026-07-18/19 — epic #111 Phase 1 Node scraper sweep (PR #551, #375/#416): a hang risk closed, and a
false-match bug closed with a cross-language parity pin.** #375 closed the same "unwrapped page.evaluate
can hang a worker forever" class the 2026-07-02 entry already fixed for the PDF/screenshot paths, but had
missed the DOM de-chrome segmentation step: both `captureInto` and `runBackfillSegments` called
`segmentChrome` directly, with no native Playwright deadline. Fixed with a shared `segmentWithTimeout`
wrapper (§2d). #416 fixed a real false-match in `cmsHint`'s host suffix check (a bare `endsWith` let
`myfinalsite.net` match the CMS vendor `finalsite.net`) by extracting the dot-boundary `hostMatches`
predicate already used elsewhere in the gate, and pinned its behavior against the Python-side
`_host_matches` with a shared golden-vector fixture (§2c) — the review pattern this epic's sweep repeated
across every stage: a cross-language behavior claim gets a fixture, not just a code comment.

**2026-07-19 — #518 capture-fidelity flags + the #415 fold-in (epic #111 Phase 4).** Sized by a
read-only corpus survey (1,471 live records; numbers on #518): captures that succeed mechanically but
whose content is not what the URL promised now carry a `fidelity` flag list on the record — `login_wall`
(URL is a login endpoint, or a password field gates a near-empty page; Huntington's
`gateway/Login.aspx?returnUrl=…` is the motivating pair) and `soft_404` (a styled "Page Not Found"
served 200; 9 in-corpus, verified visually on morey/arlington.sburg.org's bell-schedule URLs). Flag,
never drop — the record still captures/processes; the flags project into the governance DB
(`capture.fidelity_json`, cache_ingest) so Stage 5 sees "capture suspect", never a silent
`target_absent`. Detection is the pure exported `fidelityFlags()` (capture_fidelity.test.mjs), fed
ONLY by persisted facts — url/final_url, the page-text head, and `fingerprint.has_password` (a raw
signal gathered inside `domFingerprint`'s single evaluate) — so the new `recompute-fidelity` CLI
mode re-derives flags after a regex tuning without re-capture, mirroring `recompute-cms-hint`. #415
folded in: the direct-fetch binary write is gated on `r.ok`; a 404/403 served with a PDF/image
content-type is a visible per-record failure (`err: binary_fetch_<status>` + `fetch_status`), never
written as `original.*` and never fallen through to render (the PR's own review round caught that a
render of a true binary URL yields a BLANK ok:true html record — worse than a visible failure).
Zero instances in-corpus; purely preventive, pinned by static-source tests. REQ-154.

**2026-07-19 — #225: goto wait strategy `networkidle/30s` → `domcontentloaded/15s` (shared
`GOTO_WAIT`, all three goto sites).** The Jefferson-AL truncation (85/112 at the 600s deadline) was
per-URL latency, not URL count: measured on 47 real URLs across 3 districts / multiple CMS vendors,
`networkidle` burned its FULL 30s timeout on 32/35 Apptegy pages (live feeds never go idle) and
averaged 7.8s even where it settled, vs 3.2–5.3s for `domcontentloaded` + the existing 2.5s settle —
with ZERO content loss (identical innerText clock-time counts row-for-row). Jefferson's projected
capture drops ~670s → ~130s, comfortably inside the deadline. The late-hydration risk is absorbed by
the settle window + the Tier 2.5/3 visual backstop. Full measurements: #225 (2026-07-19 spike).

**2026-07-19 — #116: partial retry (epic #111 Phase 4).** A `captured_partial` district's retryable
remnants are now re-attemptable without re-hitting anything that already answered: `python3 -m
infrastructure.acquisition.stage3_capture.headless retry <batch_id>`, or the console's
`POST /api/capture/{batch_id}/retry` (same background-job/lock machinery as `/run`; a UI button
rides with the gate@5 console work — the endpoint is curl-able meanwhile). Selection: a district dispatches only if its
on-disk manifest holds ≥1 failed record whose err is RETRYABLE (`not_attempted*` — deadline
truncation; `not_recovered*` — crash reconstruct) AND whose URL is still in the capture plan
(fragment-stripped parity with candidates.json). The Node run then executes in `retryable-only`
mode: `seedFromPriorCaptures(..., retryableOnly)` carries ok records verbatim (never re-hit),
drops-and-re-attempts retryable failures, and carries NON-retryable failures untouched —
`security_block` (the one-attempt WAF rule), `needs_oauth_reauth` (#115), `binary_fetch_*` (the
origin already answered). The predicate is mirrored (`isRetryableErr` in the mjs,
`RETRYABLE_ERR_PREFIXES` in headless.py). A failed EMERGENT record can't retry this way (its URL
isn't planned and its ok parent won't re-render) — that's #117's recovery territory. The union
manifest lands through the same `finish_district` path as a first run, so the outcome honestly
re-resolves (`captured_partial` → `captured_all` when the retry clears the remainder). REQ-155.

**2026-07-19 — #117: per-task journal — a hard kill no longer orphans emergent captures (epic #111
Phase 4).** The capture loop appends one JSONL line per COMPLETED record to the district's
`captures.journal.jsonl` (best-effort — a journal failure never fails the task; the manifest stays
the end-of-run authority). A crash leftover is renamed aside at the next run's start (never
clobbered); the live journal is deleted only once `captures.json` actually lands (it supersedes it).
`reconstruct_captures` now reads the journal(s) FIRST (live + renamed-aside, oldest first, latest
line per hash wins): a journaled record is used verbatim — full fidelity (fingerprint/final_url/
fidelity flags), where the folder scan could only rebuild a degraded record — and journal records
beyond the capture plan bring back the EMERGENT captures the pre-#117 reconstruction had to abandon
(md5 is one-way; their URL only ever existed in Node's memory). The folder scan remains the fallback
for pre-#117 orphans and lost journal lines; a torn final line (SIGKILL mid-append) is tolerated.
REQ-156.

**2026-07-20 — #578 (REQ-159): the one-attempt security-block rule is now ENFORCED, not just
classified.** Live finding (Millard NE, batch_00021): `security_block` existed only as a retry
classification — nothing assigned it, so a Cloudflare-challenged run recorded 81/83 interstitials
as `ok` while continuing to pressure the WAF. Now: `detectChallenge` (pure — `cf-mitigated:
challenge` header + bounded interstitial body markers; CDN presence never trips) runs on the fetch
branch AND the render branch (a challenge records `err='security_block'`, saves nothing as ok,
scans no anchors); `updateSecurityState` implements the district circuit breaker (3 consecutive
challenges → halt; remaining URLs record a NON-retryable security_block variant — deliberately not
`not_attempted`, which #116 would re-hammer); and a pre-capture probe GETs each district's dominant
planned host first (a challenged probe halts the district at one request of IP exposure; a clean
probe is necessary-not-sufficient — the breaker is the guarantee). Security-blocked districts are
ineligible for the 5→1 geo escalation (stage5_followup): the domain was fine, the WAF said no —
manual triage only. Tests: capture_security.test.mjs (the real Millard interstitial is the fixture).

**2026-07-27/28 — epic #617's #620 campaign drove the first real redo-batch traffic since #647, and it
found what #647 alone couldn't (governance §11's "the future case has to be constructed, not reasoned
about," now doubled).** `batch_00030/31/32` (25 `redo_attempted=true` districts) ran end-to-end: Stage 3
completed 25/25 (15 `captured_all`, 9 `captured_partial`, 1 `failed`-by-timeout that still captured its
full 119/119 planned records — Orange County FL). The capture WORK is correct throughout. Three console
*display* defects surfaced, all traceable to the same root — disk-artifact-existence as the stage-done
marker, with no per-run receipt: **#669** (per-district counts read from the district-id-keyed cache with
no batch/run scope, so a redo's displayed numbers can be a stale run's; the confirm-run dialog's
"Already-captured districts are skipped" copy is flatly false for a redo batch), **#670** (a district that
times out on the Python subprocess backstop *after* fully capturing can render as clean `done` — the
failure-event check is skipped once disk holds a manifest), **#671** (the whole-batch-up-front `dispatched`
stamp means every district holding a prior artifact reads `done`-with-stale-metrics for most of the run;
measured windows 45s–38m15s). None of these are #647's fault — #647 fixed the TODO/DONE *gate* (Run-control
button visibility) correctly; these three are the *rendering* layer #647 didn't touch. All three: open,
epic #96, not yet fixed. See §3 for the present-state caveats and `docs/technical-notes/learning-loop-
reports/2026-07-25-epic617-benchmark-model-findings.md` §13 for the full campaign account.

**2026-07-20 — doc correction: §2a's reconciliation halt has a bypass, now noted.** §2a described the
registry-ahead-of-disk `SystemExit` as unconditional; it isn't — `reconcile()`'s `remediation_receipt`
check (#572) has excused it since that PR landed. No code change; §2a now notes the bypass and
cross-references `PIPELINE_GOVERNANCE_AND_STATE.md` §11l, now the canonical explanation of the mechanism
(including its `REMEDIATION_RECEIPT_MAX_AGE_DAYS=30` time-bound and its documented not-stage-scoped
residual).
