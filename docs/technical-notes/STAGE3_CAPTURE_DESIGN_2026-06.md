# Stage 3 — Capture: design & decision log

> **Status: BUILT + run live (2026-06-23)** against all 12 `batch_00001` districts (150/150 URLs
> captured, 0 failures, all `captured_all`). Per-record hosting/CMS **fingerprinting** added + backfilled
> 2026-06-24 (150/150); DOM **de-chrome** segmentation built + backfilled 2026-06-25 (REQ-091). Drive
> Tier 2 (OAuth) deliberately deferred, not built. Produces, per district,
> `captures/<hash>/` directories + `captures.json` — the input Stage 4 (Local processing) consumes.
>
> **What this note is:** for the already-built Stages 1–4 the **code is authoritative**; this note is a
> **narrative of what the code currently does — to inform the console**, not a redesign. §1–§5 describe
> current behavior (verified against the scripts 2026-06-27); §6 is the historical decision log.
>
> **Code (grimp-confirmed, 2026-06-27):** the Python orchestration `stage3_capture/capture_stage3.py`
> imports exactly `common.district_status` (no LCT DB — ungated middle stage). The actual browser work is
> Node: `infrastructure/scraper/capture_discovery.mjs` (active; `segmentChrome`/`dismissModals`/
> `stripFragment`/`buildHtmlFingerprint`/`runCapture`/`runBackfill*`) + `capture_drive.mjs` (Tier 1 Drive
> export-URL logic, `node:test`-tested). The Python↔Node split mirrors Stage 2: **Python orchestrates and
> owns the registry; a separate process does the risky/external work.** *(Note: the Python code was
> promoted from `infrastructure/acquisition/discovery/` to `stage3_capture/`; the decision log below
> reflects the original paths.)*

**Companions:** `ACQUISITION_PIPELINE.md` §3 (the slim map), `acquisition_pipeline_flow.md` (the visual),
Stage 2's note (upstream `candidates.json` contract), Stage 4's + Stage 5's notes (downstream — de-chrome
*measurement* lives in `STAGE5_FILTER_DESIGN_2026-06.md`). `PIPELINE_GOVERNANCE_AND_STATE_2026-06.md`
(§3 state_event, §11 gates).

---

## 1. Purpose & I/O

Fetch and persist every candidate page so later stages have local evidence to read — capture *everything
available*, decide which representation to trust downstream.

- **Input — read, never modify:** each district's `candidates.json` (Stage 2's deduped, capture-ready URL
  list) under `data/raw/lea-website-captures/<id>_<slug>/`. `find_districts()` requires both
  `discovery.json` (for the name/state/domain header fields) and `candidates.json` to be present.
- **Output, written once per district:**
  - `captures/<hash>/` — **one subdirectory per captured URL**, `hash = md5(url).slice(0,10)`, holding
    plain-named files (`page.txt`/`page.png`/`page.pdf` for HTML; `original.<ext>` for a direct binary;
    `<format>.<ext>` for a Drive export; plus the de-chrome segments — §2d). One folder = everything for
    one page (not flat hash-*prefixed* files; that was the first-pass bug, §6).
  - `captures.json` — per-candidate record (`url`, `hash`, `tools`/`source`/`found_on`, `ok`, `kind`,
    `final_url`, `files`, `err`, `fingerprint`, `segmented`) — a **separate file from `candidates.json`**,
    never a mutation of it.
- **Gate:** **none** (Stages 2/3/4 ungated). Registry outcome: `captured_all` / `captured_partial` /
  `capture_failed_all` + a short `notes` rollup.

---

## 2. The design (settled)

### 2a. Reconciliation — filesystem-authoritative (identical pattern to Stage 2)
`captures.json` on disk IS "Stage 3 done"; the registry is a cache, reconciled *from* disk. Disk-ahead
reconciles up silently (`reconciled_from_disk`, skip); **registry-ahead-of-disk** (registry says
`furthest_stage >= 3`, no `captures.json`) raises `SystemExit` CONTROL FAILURE and halts the whole run.

### 2b. Per-candidate branch logic (`runCapture`)
Every URL (and any emergent candidate) is `stripFragment()`-normalized before the `seen` dedup, then routed:
1. **Google Drive/Docs/Sheets/Slides** (checked first) — **Tier 1, unauthenticated export URL** for
   recognized single-file patterns: Docs → PDF **+ Markdown** (the cheap win — born-digital Markdown skips
   `pdftotext`), Slides → PDF, Sheets → CSV **+ PDF** (PDF catches an image pasted into a cell), generic
   Drive file → direct download. All applicable formats captured unconditionally. **Tier 2 (OAuth Drive
   API)** — the only path for folder enumeration and Tier-1 failures — is **designed, not built** (§5).
   An OAuth/Drive failure is a **per-item flag** (`err: "needs_oauth_reauth"`), NOT a run halt — one stuck
   Drive item says nothing about the rest of the batch (contrast the Stage 2 billing CONTROL FAILURE).
2. **Direct PDF/image fetch** (non-Google) — plain HTTP GET, byte-for-byte; **never** `page.pdf()` a URL
   that is already a PDF (a lossy round-trip).
3. **Generic HTML render** — `goto(networkidle)` + a 2.5s wait, then **modal dismissal** (`dismissModals`:
   CSS-hide overlays → click known dismiss selectors → DOM removal), then innerText→`.txt`, full-page
   screenshot→`.png`, and **`page.pdf()` unconditionally** (resolves the reader-routing "Tier 1→2
   escalation trigger" by removing the need for a trigger — capture both, decide downstream).
   **Emergent candidates:** scan anchors whose text/href match `SCHED_KW` → new candidate, **exactly one
   hop, never recursive** (`source: "emergent"`, `found_on`). Explicitly for CDN-hosted PDFs too, not just
   Drive/Docs.

### 2c. Hosting/CMS fingerprint (per record, raw signals only — 2026-06-24)
`buildHtmlFingerprint`/`buildFetchFingerprint` record, at the **URL level** (school subdomains often run a
different platform than the district root), facts gathered for free from data the capture already held:
`final_host`, `server`, `powered_by`, `cdn_hints[]`, `meta_generator`, `resource_hosts[]` (off-domain
script/link/img hosts, own-host dropped, cap 20), `js_dependent` (served-vs-rendered-text proxy; null for
non-HTML), and `cms_hint` (the one cheap inline classification — a suffix match against the shared
`cms_hosts` config knob; null on no match). Direct PDF/image/Drive records get a reduced (no-DOM)
fingerprint. **Facts, not classification** — real CMS ID is a later pure function over these signals,
refinable retroactively. Backfilled via `backfill-fingerprints` (re-visits each `ok` record, patches only
the fingerprint, touches nothing Stage 4 produced); `recompute-cms-hint` re-derives `cms_hint` over stored
`resource_hosts` with no browser at all — the standing mechanism for applying a human-approved `cms_hosts`
change to already-captured data cheaply.

### 2d. DOM de-chrome segmentation (REQ-091, built + measured 2026-06-25)
CMS chrome (a footer "Building Hours 7:15–3:15", a school-switcher nav, footer board/athletics links)
injects false signal. The fix **must live at Stage 3, at render time** — we persist `innerText` only, never
raw HTML, so by Stage 4 the structure that identifies a footer is gone. **Segment, don't strip:**
`segmentChrome()` captures `innerText` of structural landmarks (`<header>`/`<footer>`/`<nav>` + ARIA
banner/contentinfo/navigation, per `config/de_chrome_landmarks.json`) as **separate additive
representations** — `page.main.txt` (clean signal), `page.header/footer/nav.txt` — alongside the
**untouched full `page.txt`** (always kept; segmentation is best-effort, never lossy). Header/footer are
kept because real *school hours* sometimes live there, not only confounding building hours. Stage 5 tiers
on `main` only and screens chrome separately. Backfilled via `backfill-segments`. **The measurement
belongs to Stage 5** (`STAGE5_FILTER_DESIGN_2026-06.md`): the live backfill measured category-guess
0.43→0.60 and topology 0.6→0.8 — a strong win.

### 2e. Outcome rollup + single registry write
`compute_outcome()` rolls per-candidate `ok`/`err` into `captured_all`/`captured_partial`/
`capture_failed_all` + a `notes` `Counter` of `err` reasons. The registry holds this **rollup only** —
never a live array of open issues (a sync-bug recipe); a human generates the triage list on demand by
scanning `captures.json` for an `err` string. One `record_stage()` write per district at completion.
**Redo is versioned** (`writeVersioned` renames aside with a UTC timestamp), never an overwrite.

---

## 3. Console surface
Stage 3 is **ungated** — surface as status/observability: per-district outcome, per-candidate `ok`/`err`
(esp. `needs_oauth_reauth`), emergent-candidate counts, and the fingerprint/`cms_hint` landscape (useful
context for the `cms_hosts` human-in-the-loop refinement loop). The next human gate is `gate@5`.

## 4. Tool/code provenance
Active: `capture_discovery.mjs` (+ `capture_drive.mjs`). The modal-dismissal + `page.pdf()` logic was
ported from `capturer.ts` (confirmed pure-Playwright, zero coupling to the dead Crawlee/Express design).
**Superseded, do not revive:** `mapper.ts`'s `PlaywrightCrawler` (the abandoned Jan-2026 blind-site-mapping
design); `google_drive_handler.py`'s Playwright-preview + Gemini tiers (only its Tier-1 export logic
carried forward into `capture_drive.mjs`).

## 5. Open decisions
- **Drive Tier 2 (OAuth Drive API) — deferred, not blocked** (REQ-078, `must`→`should`). Build it when a
  real Drive link actually needs it; `batch_00001` produced zero. Needs a one-time GCP OAuth setup with the
  consent screen out of "Testing" status (the documented trigger for forced-short refresh tokens).
- **Duplicate-PDF dedup — deliberately NOT built.** A cross-directory content-hash scan for a negligible
  current benefit; recorded watch-item.
- **Tier-C `neg_dominant` retune** (de-chrome side-effect) — a Stage 5 follow-up (its note), surfaced here
  because de-chrome is the Stage 3 mechanism that exposed it.

---

## 6. Decision log (chronological — moved here from the flow diagram, 2026-06-27)

_Preserved verbatim from `acquisition_pipeline_flow.md`'s decision log; `gate@5` was "CP-B" at the time of
writing (governance §11). Paths reflect the original `infrastructure/acquisition/discovery/` location
before the package promotion._

**2026-06-23 — Stage 3 (Capture) design conversation: grounded several open questions in what's actually in the codebase rather than the docs' claims about it.** Before any Stage 3 code is written:
- `capture_discovery.mjs` (the real, active capture script — 73 lines, bare Playwright + `fetch()`, no Crawlee) already implements the `captures/` subdirectory + MD5-hash-of-URL naming pattern independently converged on in conversation, and already writes a separate per-district `captures.json` (url → hash → files) rather than mutating `candidates.json` — which answers "should capture results get logged back to candidates.json" with "there's already a cleaner pattern, no write-once policy exception needed."
- **Confirmed Crawlee is genuinely dead code, not just superseded in spirit.** `mapper.ts`'s `PlaywrightCrawler` usage is literally the abandoned Jan-2026 blind-site-mapping design (its own docstring: "to enable intelligent URL ranking by Ollama") and isn't imported by anything in the active pipeline.
- **`google_drive_handler.py` already has a 3-tier Drive fallback (direct download → Playwright preview → Gemini API) anticipating exactly the Gemini question the user raised — but the Gemini tier is an unimplemented stub, and the Drive-folder case (vs. a direct file link) isn't handled at all (`DRIVE_PATTERNS` only matches file-level URLs).** It also depends on a separate Express microservice (`server.ts`, `localhost:3000`) nothing else in the active pipeline runs.
- **No modal-dismissal logic actually exists in the live capture path**, despite `ACQUISITION_PIPELINE.md` claiming it was "salvaged" from `capturer.ts` — confirmed by reading the real script. A real, previously-undocumented gap, agreed to fix now rather than defer.
- `page.pdf()` does not exist anywhere in the current capture script — confirmed it's a genuine addition, not a config flip. User decision: run it unconditionally on every HTML page captured (no multi-column-detection trigger), since it's free local compute and removes the need to ever define the "Tier 1→2 escalation trigger" that `ACQUISITION_PIPELINE.md`'s reader-routing spec had left deliberately open and unsolved.
- **Drive/Docs API research (Gemini MCP + Perplexity, cross-checked against each other):** `files.list` (folder enumeration) always requires OAuth/service account, even for fully public folders — no API-key-only path exists. The unauthenticated export-URL trick still works for "anyone with the link" content. An image-only Doc/Slide exports to an image-in-a-PDF with no text layer — not a dead end, it's the same shape as a scanned PDF and routes into the existing Tier 2.5 OCR path. **One real discrepancy caught between the two sources:** Gemini claimed refresh tokens expire after 6 months of inactivity as documented Google policy; a citation-backed Perplexity follow-up found no such rule in Google's actual OAuth docs — the only documented forced-short-lifetime case is leaving the OAuth consent screen in "Testing" publishing status (7-day tokens), unrelated to inactivity or personal/unverified-app status. Architectural implication: OAuth is only actually needed for folder *enumeration* — individual Docs/Sheets/Slides/Drive-file retrieval already works via the existing unauthenticated path. Not yet written into `ACQUISITION_PIPELINE.md` — still mid-discussion.

**2026-06-23 — Stage 3 (Capture) design closed out and written into `ACQUISITION_PIPELINE.md` + this diagram.** Final three open points resolved before formalizing:
- **OAuth/Drive failure handling: a per-item flag, not a batch halt.** Unlike the Stage 2 billing CONTROL FAILURE (where one failure means every subsequent call fails identically), one stuck Drive item says nothing about the rest of the batch — so it's recorded (`err: "needs_oauth_reauth"` in that candidate's `captures.json` record) and capture moves on to the next candidate. Explicitly rejected: maintaining a live array of open issues inside the registry itself ("that's a recipe for sync issues" — the user's words) — the registry holds a status rollup only (`captured_partial`, etc.), and a human generates the actual triage array on demand by scanning `captures.json` files when ready to act, not by reading an accumulating structure that has to stay in sync with reality.
- **Dropped the Gemini-API tier too, not just Playwright-preview.** Reasoning: Gemini would only end up calling the same Drive API that already failed — it buys nothing over what OAuth+Drive-API already attempted. `google_drive_handler.py`'s original 3-tier design (direct download → Playwright preview → Gemini) collapses to 2 tiers (unauthenticated export URL → OAuth Drive API), with the OAuth tier also being the *only* path for folder enumeration — one mechanism doing double duty instead of three separate ones.
- **Export formats, finalized:** Docs → PDF + Markdown (the Markdown export is a genuine cheap win — already-clean plain text, skips `pdftotext` entirely for born-digital Docs). Slides → PDF only (no markdown equivalent makes sense for slides). Sheets → CSV + PDF (PDF specifically to catch the edge case of an image pasted into a spreadsheet cell, which CSV alone would silently lose — same shape as the image-only-Doc problem already solved via the existing OCR path).
- The full per-candidate branch logic (Google detection → Tier 1/Tier 2 Drive handling → direct PDF/image fetch → generic HTML render with modal dismissal + unconditional `page.pdf()` + one-hop emergent-candidate link-following) is now in both docs. Nothing built yet — `capture_discovery.mjs` still needs all of this added; `capturer.ts`'s modal-dismissal and PDF-options logic still needs porting in, not run as-is.

**2026-06-23 — clarified scope of the emergent-candidate path: explicitly for CDN-hosted materials too, not just Drive/Docs.** Caught before implementation: the emergent-candidate writeup had been framed almost entirely around the Drive/Docs research that preceded it, risking a narrow mental model (and narrow test coverage) for whoever builds it. The real motivating case is broader — an on-domain page Discovery *did* find can easily link to a bell-schedule PDF hosted off-domain on a CMS/CDN host (Finalsite, BoardDocs, SchoolWires/Blackboard, an S3 bucket — `discover.py`'s existing `CMS_HOSTS` set, not a new list) that Discovery's domain-scoped search would never surface directly. The branch logic already handles this correctly once an emergent candidate is found (it lands on the ordinary direct-PDF/image-fetch branch) — the thing that needed fixing was documentation/intent, so that **when Stage 3's tests get written, a CDN-hosted-PDF emergent candidate is a first-class test case, not an incidental side effect of the Drive/Docs test cases.** `ACQUISITION_PIPELINE.md` and the `C_EMERGENT` node both updated to say this explicitly.

**2026-06-23 — Stage 3 implemented; one real bug caught by the user reviewing real output, not by anything written down beforehand.** Built `capture_stage3.py` (Python orchestration: reconcile/outcome-rollup/registry write-back, mirroring `discover_stage2.py` exactly), `capture_drive.mjs` (Tier 1 Drive/Docs/Sheets/Slides export-URL logic, unit-tested via `node:test` — no new dependency), and extended `capture_discovery.mjs` with modal dismissal, unconditional `page.pdf()`, one-hop emergent-candidate discovery, and the Drive Tier 1 branch.
- **The bug:** the original design conversation said "capture directory per URL" — meaning one subdirectory per captured page. What got documented (`ACQUISITION_PIPELINE.md`: "files named by `md5(url).slice(0,10)` plus extension") and built both quietly collapsed this into flat hash-*prefixed* files sharing one district-wide `captures/` folder — which only preserves the hashing half of the original intent, not the per-URL grouping half. This happened because the existing 73-line `capture_discovery.mjs` was read early in the Stage 3 design conversation, its hash-naming was (correctly) noted as matching what we'd just converged on, and that got reported back as "already exactly how `capture_discovery.mjs` works today, independently arrived at twice" — true for the hashing, not true for the directory-per-URL structure, and the distinction wasn't caught at design time.
- **Caught how:** the user looked at real output (`data/raw/lea-website-captures/1739960_urbana_sd_116/captures/`) mid-run and asked directly whether it should be grouped by hash into subdirectories. It should have been.
- **Fix:** `capture_discovery.mjs` now creates `captures/<hash>/` per URL, with plain filenames inside (`page.txt`/`page.png`/`page.pdf` for HTML; `original.<ext>` for a direct binary fetch; `<format>.<ext>` for a Drive export) — `captures.json`'s `files` field now holds bare filenames within that per-hash folder, not hash-prefixed names. Both docs corrected. The first real full-batch run was caught, stopped, and re-run after this fix — no district was left with the wrong structure.
- Confirmed via two re-runs after the fix: a local HTML fixture (modal dismissal, `page.pdf()`, and emergent-candidate discovery via a "Bell Schedule" link, with an unrelated "About Us" link correctly excluded) and a real district (Blue Water Middle College, 4 real URLs, all captured cleanly) — both before discovering the structure bug, repeated after fixing it.

**2026-06-23 — first real full-batch Stage 3 run, all 12 `batch_00001` districts, found a second real bug and confirmed the emergent-candidate path's value with hard numbers.** 112 original candidates grew to 173 total URLs on the first pass — every single one captured successfully (0 failures), but the count itself revealed a problem worth checking before trusting it.
- **The bug:** Stroudsburg alone contributed 35 of the 61 emergent candidates found. Inspecting them showed many were pure URL-fragment variants of pages already captured (`.../bell_schedules/#pageTitle`, `.../bell_schedules/#nav_items_0`) — a fragment never represents different server-side content, so these were the *same page* being re-rendered, re-screenshotted, and re-PDF'd 2-3 times under fragment-different URLs, because the dedup `seen` set was checking exact URL strings without stripping the fragment first.
- **Fix:** added `stripFragment()`, applied both when seeding the initial candidate set and when an emergent link is found, before the `seen` dedup check. Re-running after the fix: total URLs dropped from 173 to 150 (61 → 38 emergent), with the genuine duplicates gone and all real distinct content preserved — confirmed by re-inspecting Stroudsburg's remaining 23 emergent candidates by hand: a shared `cross.jsp` cross-reference link repeated once per school subdomain (real but low-marginal-value), several `printerfriendly.jsp` variants (potentially a cleaner extraction target than the regular page), and multiple genuinely distinct `index.jsp?id=N` entries per school within what's clearly a shared "Bell Schedules" CMS app (id 7100-7105 alone under one high school) — likely real alternate-day-type schedule variants (early release, 2-hour delay, etc.) that Stage 7's existing "standard full day only" filtering is already designed to sort out downstream, not something Capture needed to pre-filter.
- **Net result, user's read confirmed with numbers:** the emergent-candidate path "earned its keep" — across the batch it found 38 genuinely new candidate pages Discovery's domain-scoped search never directly surfaced, with zero capture failures and the duplicate-inflation bug caught and fixed before it could quietly waste effort at scale.
- Final state: all 12 districts `captured_all` in the registry (`capture_stage3.py finish` run for each), 150/150 URLs captured with zero errors, 900 Python tests + 8 Node tests passing.

**2026-06-23 — Drive Tier 2 (OAuth) deliberately deferred, not just blocked on the GCP prerequisite.** The real `batch_00001` run produced zero Drive/folder links needing it — `needs_oauth_reauth` never actually fired on real data. User's explicit call: build Tier 2 when a real Drive link is actually hit, not speculatively ahead of any evidence it's needed ("it's also very possible that it's never needed... getting ahead of ourselves is counterproductive"). REQ-078 downgraded from `must` to `should` and reworded to record this as a deliberate choice, not an open blocker — a future session should not read it as forgotten work.

**2026-06-24 — Stage 3 hosting/CMS fingerprinting added, backfilled across all 12 districts, and immediately earned its keep.** User's idea: record what platform/CMS/host generates each captured page, at the URL level (school subdomains often differ from the district root), as early screening signal for later refinement. Grounded against the code first — found the capture was already *holding and discarding* most of the signal: the `goto`/`fetch` Response headers (only `content-type` was kept), and there was already a `page.evaluate` DOM scan (for emergent anchors) that fingerprint extraction could ride alongside. Raw HTML is never saved (only innerText), so DOM signals (`<meta generator>`, resource hosts) are ephemeral and must be read at render time — a sharp constraint that settled the design.
- **Architecture: record raw facts, don't classify the CMS inline** (the one cheap exception: a `cms_hint` host-suffix match against the existing `CMS_HOSTS`). Same invariant as the rest of the pipeline — real classification is a later pure function over the raw signals, refinable retroactively without re-capturing 20K districts. User approved this framing explicitly ("just capture fingerprints").
- **Fields** (per record `fingerprint` block): `final_host`, `server`, `powered_by`, `cdn_hints[]`, `meta_generator`, `resource_hosts[]` (off-domain script/link/img hosts, own-host dropped, cap 20), `js_dependent` (served-text-near-empty-but-rendered-substantial proxy; null for non-HTML), `cms_hint`. Direct PDF/image/Drive records get a reduced (no-DOM) fingerprint.
- **Parity via backfill, NOT full re-capture** — the user's call after I flagged that re-running capture over the already-Stage-4 districts would mix fresh Stage-3 artifacts with existing Stage-4 outputs in the same `captures/<hash>/` dirs, leave `processed.json` stale, and risk content drift. `backfill-fingerprints` mode re-visits each existing `ok` record, computes only the fingerprint, patches `captures.json` (versioned-redo) — touches nothing Stage 4 produced. Ran live: 150/150 records, 0 errors.
- **The finding:** `cms_hint` came back `null` on all 150 — correctly, because the real platforms in this sample aren't in the discovery-era `CMS_HOSTS`. Raw `resource_hosts` revealed them: **SharpSchool** (51), **Apptegy/Thrillshare** (~24), **Educational Networks** (25); server strings corroborated (`Pepyaka`=Wix, `Pagely`=managed WordPress, `AmazonS3`). Whether to grow `CMS_HOSTS` (cross-cutting — it changes `discover.py`'s `gate()`) or give fingerprinting its own broader platform list is recorded as Open decision #8, deliberately not acted on unilaterally.
- Tests: 6 new pure-helper unit tests (`capture_fingerprint.test.mjs`, `node:test`), helpers exported + a main-module guard added so importing for tests doesn't trigger a capture run. 14 Node tests pass (8 drive + 6 fingerprint).

**2026-06-24 — CMS_HOSTS grown by human approval (Open decision #8 resolved), encoding a standing governance rule.** The fingerprint finding (SharpSchool/Apptegy/Educational Networks dominate the sample, none in CMS_HOSTS) was acted on: the user approved adding `sharpschool.com`/`apptegy.net`/`thrillshare.com`/`educationalnetworks.net` to `CMS_HOSTS` in both `discover.py` and `capture_discovery.mjs`. This is the load-bearing change — it also makes Stage 2's `gate()` keep slug-matched URLs on those hosts that it previously rejected as off-district (closing a possible recall gap), so a `TestDiscoveryGate` regression class was added. **Standing governance rule the user set:** every `CMS_HOSTS` addition is a human-in-the-loop decision, never automated, and must be a *school-district-specific vendor*, never a general host/CDN — `amazonaws.com` was deliberately NOT added despite `core-docs.s3.amazonaws.com` appearing in the data, exactly to avoid the pollution that whitelisting general hosting would invite. The user framed this as the first instance of the fingerprint-driven refinement loop they want to run continuously, and an explicit topic to carry into Stage 5 design. _(Later migrated to the `cms_hosts` config-as-data knob — single source of truth across `discover.py` and `capture_discovery.mjs`, no more hand-syncing; see Stage 5's note.)_

**2026-06-25 — Stage 3 DOM segmentation (header/footer/nav vs. main) designed, then BUILT + MEASURED (REQ-091).** Stage 5's batch_00001 review surfaced CMS *chrome* as the single biggest source of false signal: a global footer's "Building Hours 7:15–3:15" injects a fake start/end proximity-pair (false-positive tier), a school-switcher `nav` inflates `roster_school_names_hit` into a false `hub` topology (Marion's `guess hub` vs labeled `per_school`), and footer board/athletics/calendar links drag real schedule pages toward tier C. Key realization, traced to a hard constraint: **the fix has to live at Stage 3, at render time** — we persist `innerText` only, never raw HTML (the fingerprint-design constraint), so by Stage 4 the DOM structure that identifies "this is a footer" is gone. Decisions, mirroring the fingerprint pattern:
- **Segment, don't strip.** Capture `innerText` of the structural landmarks (`<header>`/`<footer>`/`<nav>` + ARIA `banner`/`contentinfo`/`navigation`) as **separate representations** (`page.main/header/footer/nav.txt`) alongside the **untouched full `page.txt`** — additive, best-effort, never lossy. We keep header/footer because the real *school hours* sometimes live there, not only the confounding building hours.
- **Raw segments, not classification** (same invariant as fingerprinting): Stage 5 computes signals per representation, **tiers on `main` only** (chrome can't contaminate the verdict), and **screens chrome separately** — a footer start/end pair + `office hours`/`building hours` ⇒ the existing `building_hours_visible` flag; + `school hours`/`dismissal` and not in a board/sports nav ⇒ a candidate school-hours signal.
- **Graceful degradation + `backfill-segments`** (a no-Stage-4-touch re-visit, exactly like `backfill-fingerprints`) for the already-captured batch_00001; free on future captures. When no landmarks exist (`<div class="footer">` CMSs), `main` = full page, chrome reps empty — never worse than today.
- **Built + measured** (`config/de_chrome_landmarks.json`, `segmentChrome()` + `backfill-segments`, `build_signals.compute_signals(main_text=…)`): the live backfill on batch_00001 (140/140 html, 123/150 de-chromed) measured **category-guess 0.43→0.60 (+17pts), topology 0.6→0.8** (Marion `hub→per_school`), **tier A unchanged**. Side-effect: footer-negative stripping floated 24 non-targets C→B (A+B precision 0.75→0.53) — the tier-C `neg_dominant` retune is the next Tier-0 follow-up. Two bugs caught by validating on Marion first: `textContent`-on-detached-clone (98KB hidden cruft → live-DOM `innerText`); `goto` missing the capture path's `.catch(()=>null)`. The measurement detail lives in `STAGE5_FILTER_DESIGN_2026-06.md`.
