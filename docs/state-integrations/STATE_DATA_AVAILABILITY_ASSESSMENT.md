# State Education Data Availability Assessment

**Regenerated:** 2026-07-21 (auto-generated from `docs/state-integrations/state_data_catalog.yaml` — DO NOT hand-edit this file, edit the catalog and re-run `infrastructure/scripts/utilities/gen_state_assessment.py`)
**Purpose:** Evaluate state education agency (SEA) data portals for Learning Connection Time (LCT) metric integration — enrollment, staffing, and SPED data at the district level, plus the state-ID<->NCES-LEAID crosswalk.
**Entities assessed:** 56 (50 states + DC + 5 territories)

---

## Precedence context (why this campaign matters, and where it doesn't)

Verified against the live DB 2026-07-20: staff_counts_effective is 100% nces_ccd across all states and years — SEA staff/enrollment data wins REQ-023 precedence NOWHERE today, because year-matched NCES (2024-25 CCD, ingested 2026-07) beats year-matched SEA by design (REQ-022/023). SEA data currently pays off through: (1) SPED-actual data via REQ-025 (state-actual beats the 2017-18 federal estimate — CA contributes 2,036 LCT rows today), (2) SPED-teacher splits feeding SPED scopes, and (3) years NEWER than the NCES primary (2025-26+), where SEA wins until the next CCD lands. Probe priority follows this ranking. NOT a target: daily instructional minutes — verified dead end (docs/INSTRUCTIONAL_TIME_HARVEST.md).

---

## Format preference policy

POLICY (Ian, 2026-07-20): when a state offers the SAME data in multiple formats, acquire only the single best format — never all of them. Preference order: (1) CSV — by far the most common here, and matches our existing importer/pandas tooling, so it beats JSON/XML on practicality even though those are more "structured"; (2) JSON; (3) XML; (4) XLSX; (5) XLS; (6) SAS (kept only because NCES itself sometimes uses it — no state in this campaign actually offers a real SAS file, confirmed by audit); (7) PDF — last resort, use pdftotext/pdfplumber/camelot depending on structure; (8) anything else. This does NOT apply when formats carry genuinely different data (e.g. LA's SPED Excel = rates, PDF = raw district counts; MP's live dashboard vs. an annual PDF snapshot) — those need both, not a pick-one. Never fabricate a "better format" URL that wasn't actually found/verified (see AR/NE/WV 2026-07-20 probe entries for the audit that applied this policy retroactively to Phase B's results).

---

## Summary

| Tier | Count | Meaning |
|---|---|---|
| Integrated — refresh available (newer year confirmed) | 3 | |
| Tier 1 — ready to acquire now (2+ core categories, direct-download/API) | 30 | |
| Tier 2 — data exists, needs manual/dashboard work | 11 | |
| Tier 3 — blocked or largely unconfirmed | 6 | |
| Integrated — current (no refresh needed) | 6 | |

**Crosswalk correction (2026-07-20):** most SEA portals don't publish their own state-ID->NCES-LEAID crosswalk file, and the per-state Crosswalk column below reports exactly that, honestly. But this was never the right place to look — `state_district_crosswalk` (REQ-027, 17,842 rows) is already populated from the `ST_LEAID` column in NCES CCD's own LEA directory file, which we'd already ingested and which is 100% populated across all 56 jurisdictions. **A state's Crosswalk cell showing ❌ is not a gap** — see "Consolidated sources" below and the catalog's `meta.crosswalk_correction` for the full story. OK, WI, and KY are still worth noting as states with an independent SEA-published crosswalk (useful for cross-validation per REQ-021), just not as an acquisition target.

---

## Campaign findings: post-acquisition inspection (2026-07-21)

Ian did the bulk of the acquisition personally (Tier 2/3 manual downloads, dropped directly
into `data/raw/state/{state}/`, no recorded provenance) alongside Phase D's automated 32-state
pull. This section reports what a systematic file-by-file inspection (13 parallel agents,
one per state/territory, every file opened and read — not just filename-classified) found
across all 300 files in 52 of the 56 jurisdictions, and what integrating any of it would
actually cost and buy. Full per-file detail lives in each state's `data/raw/state/{state}/
MANIFEST.md`; this is the aggregate view.

**Coverage.** 52 of 56 jurisdictions have at least one acquired file — Maine, Montana, North
Carolina, and Vermont remain fully unacquired (dashboard-only/request-only/blocked, still in
the manual work queue). Of the 52:

| Input | Clean & district-grain-usable as acquired | Present but needs real rework | Not usable / not collected |
|---|---|---|---|
| Enrollment | 42 | 10 (name-only join, truncated fetch, stale, needs subgroup filter) | 0 |
| Staffing | 26 | 18 (PDF-locked, opaque job codes, mislabeled statewide-only, encoding) | 8 (no file collected at all) |
| SPED | 20 | 15 (percentages not counts, single-district sample, outcomes not counts) | 17 (state-aggregate-only despite a `sped` tag, or nothing found) |

Six jurisdictions (Guam, American Samoa, U.S. Virgin Islands, Northern Mariana Islands, Puerto
Rico, and — structurally, though not a territory — Hawaii, whose Complex Areas aren't
independent LEAs) are single-LEA or near-single-LEA: no sub-jurisdiction variation is possible
there regardless of file quality, so "integrating" them buys essentially nothing beyond the one
aggregate row NCES/the crosswalk already implies.

Seven of the 52 (IL, MI, VA, PA, NY, MA, FL) are **already** Tier-1 integrated — for these the
question isn't new coverage but whether the newly-acquired files are a genuine refresh. Most
are (PA/VA/MA's files are 1-2 years newer than what's in the DB); NY's refresh is blocked on
Access-DB (`.mdb`/`.accdb`) extraction tooling that doesn't exist yet; one of Michigan's files
is corrupted (truncated download, unreadable).

**11 states have a genuinely clean enrollment+staffing+SPED trio, ready to use close to
as-acquired:** CA, OH, TX, NJ, VA, IL, NE, MO, KY, SD, KS (2 of these — VA, IL — are the
already-integrated refresh case above; the other 9 would be net-new). **24 states have at
least clean enrollment+staffing** — the two inputs LCT actually computes with directly (SPED
is a REQ-025 precedence bonus, not a core input). **8 non-territory states collected no
staffing file at all** (AZ, NM, RI, WA, IN, WI, LA, OK) — SEA integration wouldn't even
complete an LCT input pair for these without further acquisition work.

**Recurring integration-friction patterns — why this isn't "51 identical importers."** The
same handful of problems recur across unrelated states, meaning integration cost scales with
the number of *distinct problem types* encountered per state, not a single templated import
job:
1. District ID is a name string, not a numeric/NCES-joinable code (UT, WV staffing, CT, part
   of WA and NV's staffing).
2. A file tagged `sped` turns out to be state-aggregate-only, not district-level (NM, ID, TN,
   part of AL, WA's compliance-indicator file) — the tag describes intent, not what the file
   actually delivers.
3. Multi-sheet workbooks bury real data behind a cover/warning sheet (a documented NE pattern,
   generalized as a standing caution — check every sheet, never trust the first one).
4. Non-standard encodings or mislabeled delimiters (IA's UTF-16LE tab-delimited ".csv" files,
   CT's fixed-width text mislabeled as CSV, WI's latin-1 file).
5. Silent API pagination truncation — DE's and WA's Socrata endpoints both truncate at exactly
   1,000 rows (Socrata's default page size), a bug in this campaign's *own* Phase-D fetch
   script, not the source; both states' real data exists but only via Ian's manual full
   downloads or a pagination fix.
6. PDF-locked data needing table extraction (ID/WA/SC staffing, LA/AL SPED profiles, GA's
   subgroup-metrics file).
7. FERPA small-cell-suppression conventions differ by state (KS's `<10*`, others use different
   markers) and need per-state handling, not a shared rule.
8. Two catalog data-quality bugs this pass caught in our *own* prior work: CT's single-district
   PDF was recorded as answering all 4 statewide categories (it covers 1 of ~200 districts);
   Maryland's directory holds an unrelated, stale 2014 federal accountability PDF that isn't
   MSDE SEA data at all. Conversely, two Phase-B/C **false negatives got corrected**: IL's and
   CO's staffing files were previously classified as unusable HTML dashboard landing pages and
   are confirmed-real binary data with genuine per-district numbers.
9. The large majority of the 300 files (Ian's manual downloads, as opposed to the Phase-D
   automated 32-state batch) have **no recorded source URL** — an auditability gap against this
   project's own "auditability is the north star" principle if any of this data were written to
   the DB without first backfilling provenance.

**The one genuine surprise: Minnesota publishes real instructional-minutes data.** Every other
state's files are enrollment/staffing/SPED/FRPM — consistent with `INSTRUCTIONAL_TIME_HARVEST.md`'s
prior finding that SEA central-data harvest is a dead end for daily minutes. Minnesota's
`Average Length of Instructional Days by Sch and Grade K-12 FY25.xlsx`, found via Ian's manual
browsing (not the automated discovery cascade), is the one exception: genuine gross bell-to-bell
minutes per school×grade, independently verified twice (arithmetic cross-check against the
file's own hour totals). Filed as its own exploratory issue — [#604](https://github.com/ianmmc/learning-connection-time/issues/604)
— rather than folded into this SEA-enrollment/staffing/SPED assessment, since it's a different
kind of input (the *minutes* side, not numerator/denominator) with its own precedence questions.

**What integrating any of this would actually require.** Not one importer — closer to ~45
bespoke small ETL jobs, each with its own header-skip count, encoding, join key, and
suppression convention (pattern list above). It would mean roughly a 5x expansion of the
existing `SEA_ID_FORMATS` registry and per-state test-mixin pattern (currently 9 states), a
source-URL backfill pass across the ~270 unprovenanced manual files before any of it could be
written to the DB, an explicit decision to skip the 6 single-LEA/near-single-LEA jurisdictions
(no sub-jurisdiction gain possible), and a decision to exclude rather than force-fit the SPED
files that are percentages/outcomes/single-district-samples rather than raw district counts.

**What it would actually buy.** Recency: most acquired files are 2024-25 or 2025-26 — 0 to 1
year newer than NCES CCD's already-current 2024-25 primary dataset. Real, but the project's own
REQ-026 blend window (≤3 years) already absorbs that gap, so for enrollment/staffing this is a
precision nudge, not a categorical improvement. SPED-actual recency is the one place SEA data
has a structural advantage NCES can't match on its own — the federal SPED baseline is IDEA
618/CRDC 2017-18, eight years stale — but this campaign found only 20 of 52 states have a
clean, district-level, raw-count SPED file *as acquired*; the rest would need real rework or
aren't available at usable grain at all. Crosswalk convenience (KY, IL's RCDTS file, TX's new
TEA-NCES crosswalk, LA's school directory, MI's EEM file all carry a usable NCES-ID column) is
a nice-to-have that lowers future join friction — not a new capability, since REQ-027's
crosswalk is already solved via NCES CCD's own `ST_LEAID` column (see the crosswalk correction
above).

**Risk.** States define "staffing" differently in ways that don't map cleanly onto
"instructional staff" — Alabama's file reports Foundation Program funding *units earned*, not
confirmed-equivalent to actual employed FTE; Kansas splits licensed/non-licensed; New Hampshire
mixes SAU (multi-district administrative unit) and district-level rows in adjacent files.
Blending ~45 independently-defined state schemas into the one federal-shaped LCT schema risks
silently mixing incompatible measures under a single column name. Long-term maintenance is also
a real cost: 45 independently-changing state portals vs. NCES's single, well-understood annual
CCD drop — each state's format/URL/schema can silently shift year to year with no equivalent of
NCES's single upstream change to track.

**The big question, answered.** Given all of the above, a **blanket push to integrate all
~45 remaining states is hard to justify** against this project's own commandments
(auditability, minimize-bad-data-at-scale, tight cash spend, one human's time): the work is
manual-inspection-heavy by construction (PDF tables, name-joins, encoding sniffing — exactly
what "as automated as tolerable" argues against at this scale), most of the files lack recorded
provenance, and the dominant benefit (recency) is a marginal gain the project's own blend-window
rule already absorbs. Ian's skepticism holds up under an honest look at what's actually in these
files.

That said, it isn't zero-value across the board. A **narrow, opt-in follow-up** scoped to the
~9 net-new states with a genuinely clean enrollment+staffing+SPED trio (CA, OH, TX, NJ, NE, MO,
KY, SD, KS) would be comparatively low-friction and would deliver the one benefit SEA data
structurally offers that NCES cannot: current-year SPED-actual data superseding the 8-year-stale
federal baseline, for those specific states. That's a bounded backlog item, not a 45-state
initiative — and it doesn't compete with the higher-priority work already queued (closing the
Stage 9 loop, #92, and #582's minutes-basis-aware reader), since SEA enrollment/staffing/SPED
data doesn't touch the actual bottleneck on LCT's minutes input, which the bell-schedule
acquisition pipeline — not SEA data — is what solves (Minnesota's file, issue #604, being the
one narrow exception worth a look).

---

## Integrated — refresh available (newer year confirmed) (3)

| State | Enrollment | Staffing | SPED | Crosswalk | FRPM/ELL | Flags | Notes |
|---|---|---|---|---|---|---|---|
| **IL** Illinois | ✅ 2024-25 | ⚠️ 2024-25 | ⚠️ 2024-25 | ✅ 2025-26 | ⚠️ 2024-25 | refresh-candidate, follow-up-manual | Manual open of the 2024-25 Report Card Public Data Set needed to confirm SPED-teacher-split field before re-import — every recorded URL i... |
| **MI** Michigan | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ✅ current-rolling | ⚠️ 2024-25 | refresh-candidate | Best-confirmed refresh of the three (IL/MI/NY): direct-download links in hand for enrollment/staffing/SPED at 2024-25, crosswalk confirme... |
| **NY** New York | ✅ 2024-25 | ✅ 2024-25 | ⚠️ 2024-25 | 🚫 unchanged | ⚠️ 2024-25 (FRPM); 2023-24 (ELL, not advanced) | refresh-candidate, blocked, follow-up-manual | Enrollment/staffing refresh is clean; SPED bulk-file and crosswalk re-verification need manual follow-up (SEDREF login wall). |

## Tier 1 — ready to acquire now (2+ core categories, direct-download/API) (30)

| State | Enrollment | Staffing | SPED | Crosswalk | FRPM/ELL | Flags | Notes |
|---|---|---|---|---|---|---|---|
| **AK** Alaska | ✅ 2025-26 | ✅ 2025-26 | ⚠️ 2024-25 | ❌ — | ✅ 2025-26 | api-available | Previously-undocumented ArcGIS REST API — strong new lead, not in the Jan-2026 assessment. |
| **AL** Alabama | ✅ 2025-26 | ✅ 2026-27 (FY2027 enacted) | ✅ 2025-26 (Oct-1-2025 count) | ⚠️ unknown | ✅ 2025-26 | follow-up-manual | Enrollment/staffing/FRPM ready to acquire; SPED needs ~140 per-district PDF pulls. |
| **AS** American Samoa | ✅ 2020-21 | ✅ 2020-21 | ✅ 2024-25 | ✅ 2022-23 | ✅ 2020-21 | dashboard-only, follow-up-manual | Correction to Jan-2026 "NCES-only" — real SPED/LRE data exists and is current (FFY24); enrollment/staffing/FRPM stuck at 2020-21. |
| **CT** Connecticut | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ❌ — | ✅ 2024-25 | dashboard-only | Rich per-district PDFs (all 5 categories in one doc) but need per-district URL construction, not a bulk file. |
| **DC** District of Columbia | ✅ 2024-25 | ✅ 2022-23 | ⚠️ 2024-25 | ❌ — | ✅ 2024-25 | dashboard-only, request-only | One file covers enrollment+SWD+EL+econ-disadvantaged together; staffing is headcount not FTE, no crosswalk found. |
| **DE** Delaware | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ❌ — | ✅ 2024-25 | api-available | Best-in-batch: real Socrata API with a clean SPED-teacher-FTE split, ready to acquire programmatically. |
| **GA** Georgia | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ❌ — | ✅ 2024-25 | dashboard-only, follow-up-manual, request-only | Portal moved (georgiainsights -> GOEWS) — update the seed URL in any future re-probe. |
| **GU** Guam | ✅ 2023-24 | ✅ 2023-24 | ⚠️ 2024-25 | ✅ 2024-25 | ⚠️ 2023-24 | dashboard-only, follow-up-manual | Correction to Jan-2026 "limited public access" — SPED data reports page is genuinely current (Dec 2024 child count), but needs the specif... |
| **IA** Iowa | ✅ 2025-26 | ⚠️ 2025-26 | ✅ 2025-26 | ❌ — | ✅ 2025-26 | dashboard-only, follow-up-manual | Strong enrollment/SPED/FRPM source once past the Tableau dashboard; staffing FTE unresolved. |
| **ID** Idaho | ✅ 2025-26 | ✅ 2023-24 | ✅ 2024-25 | ❌ — | ❌ — | follow-up-manual | Strong enrollment/SPED source; staffing lacks a SPED split, no crosswalk or FRPM/ELL found. |
| **IN** Indiana | ✅ 2025-26 | ⚠️ 2021-22 | ✅ 2025-26 | ❌ — | ✅ 2025-26 | follow-up-manual | Strong enrollment/SPED/FRPM source; staffing needs a different/newer source. |
| **KY** Kentucky | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | — | Best-in-class source: NCES ID column at district+school level makes this the reference model for a future importer. |
| **LA** Louisiana | ✅ 2025-26 | ⚠️ 2024-25 | ✅ 2024-25 | ⚠️ 2025-26 | ✅ 2025-26 | — | Strong enrollment/SPED/FRPM source; staffing FTE-by-district is the gap. |
| **MD** Maryland | ✅ 2023-24 | ✅ 2023-24 | ✅ 2025-26 (Oct 2025 count, published Apr 2026) | ⚠️ 2024-25 | ❌ — | dashboard-only, follow-up-manual | SPED census is newer than our NCES baseline (SY2025-26) — a real precedence win once acquired. |
| **MO** Missouri | ✅ 2025-26 (no explicit label; refreshed weekly) | ✅ 2025-26 (no explicit label; refreshed weekly) | 🚫 unknown | ❌ — | ❌ — | blocked, follow-up-manual, login-required, request-only | Basic enrollment/staff totals confirmed via a real PDF directory; finer detail needs the MCDS login or a formal data request. |
| **MS** Mississippi | ✅ 2024-25 | ✅ 2024-25 | ✅ 2022-23 | ❌ — | ❌ — | dashboard-only, follow-up-manual | Portal moved (newreports -> Superintendent Annual Report packet); no crosswalk or FRPM/ELL found. |
| **ND** North Dakota | ✅ 2025-26 | ✅ 2024-25 | ⚠️ 2025 | ❌ — | ❌ — | follow-up-manual | Enrollment + aggregate staffing ready to acquire; SPED is state-level only, no crosswalk found. |
| **NE** Nebraska | ✅ 2025-26 | ✅ 2024-25 | ⚠️ 2024-25 | ❌ — | ✅ 2025-26 | dashboard-only, follow-up-manual | Enrollment/staffing/FRPM ready to acquire now via real files; SPED needs the NEP dashboard. |
| **NJ** New Jersey | ✅ 2025-26 | ✅ 2025-26 | ✅ 2024-25 (Oct 15 2024 count) | ❌ — | ✅ 2025-26 | follow-up-manual | Strong open portal; correction to seed note — staffing file does NOT split SPED vs general-ed teachers. |
| **NM** New Mexico | ✅ 2024-25 | ❌ — | ✅ 2024-25 | ❌ — | ❌ — | blocked, follow-up-manual, login-required | Portal moved off the Jan-2026 seed URL; richer data confirmed behind a login wall. |
| **NV** Nevada | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ❌ — | ✅ 2024-25 | blocked | Best small-state find: genuine SPED-teacher split in staffing, all 4 core categories confirmed. |
| **OH** Ohio | ✅ 2025-26 | ⚠️ 2024-25 | ✅ 2024-25 | ✅ current | ❌ — | dashboard-only, follow-up-manual, request-only | Enrollment + SPED ready to acquire now; staffing needs a login, data.ohio.gov open-data catalog appears dead. |
| **OR** Oregon | ✅ 2024-25 | ⚠️ — | ✅ 2024-25 | ❌ — | ⚠️ — | dashboard-only | Enrollment + SPED-by-environment confirmed strong; staffing needs a dropdown click-through. |
| **SC** South Carolina | ✅ 2024-25 | ✅ 2024-25 | ✅ 2022-23 | ❌ — | ❌ — | follow-up-manual | SPED-teacher split derivable from position codes even without a pre-built column — worth building that aggregation in the importer. |
| **SD** South Dakota | ✅ 2025-26 | ✅ 2024-25 | ✅ 2025 | ❌ — | ✅ 2025 | follow-up-manual | Genuinely strong flat-file source once the /ofm sub-pages are known — enrollment/staffing/SPED/FRPM all ready to acquire. |
| **TN** Tennessee | ✅ 2024-25 | ✅ 2024-25 | ⚠️ 2023-24 | ✅ current (undated static reference) | ✅ 2024-25 | dashboard-only | Confirmed crosswalk file with explicit NCES.District.Number column; portal moved off the SAS seed URL. |
| **UT** Utah | ✅ 2025-26 | ✅ 2024-25 | ❌ — | ❌ — | ⚠️ — | — | Genuine SPED-teacher-FTE column confirmed in staffing — a clean source once the real file location (schools.utah.gov, not the dashboard) ... |
| **WA** Washington | ✅ 2025-26 | ✅ 2024-25 | ✅ FFY2024 (submitted 2026) | ❌ — | ✅ 2025-26 | api-available | One Socrata API call covers enrollment+FRPM+ELL+SPED-count together — an excellent acquisition target. |
| **WI** Wisconsin | ✅ 2025-26 | ⚠️ 2025-26 | ✅ 2025-26 | ✅ 2025-26 | ✅ 2025-26 | dashboard-only, follow-up-manual | Best crosswalk found in this batch (real NCES-code column + dedicated crosswalk file); enrollment/SPED/FRPM/ELL all one bulk source, only... |
| **WV** West Virginia | ✅ 2025-26 | ✅ 2025-26 | ✅ 2023-24 | ❌ — | ⚠️ 2024-25 | dashboard-only, follow-up-manual, request-only | Confirmed SPED-teacher split by county in the FTE file — a clean source for the SPED-teacher-split rubric goal. Enrollment's Excel-via-Zo... |

## Tier 2 — data exists, needs manual/dashboard work (11)

| State | Enrollment | Staffing | SPED | Crosswalk | FRPM/ELL | Flags | Notes |
|---|---|---|---|---|---|---|---|
| **AR** Arkansas | ✅ 2025-26 | ✅ 2025-26 | ✅ 2024-25 | ✅ 2025-26 | ⚠️ 2020-21 | follow-up-manual, dashboard-only | Strong flat-file source with a confirmed crosswalk; enrollment/staffing CSV needs a browser (ASP.NET postback export, not a plain URL) — ... |
| **CO** Colorado | ✅ 2024-25 | ⚠️ 2025-26 | ⚠️ 2024-25 | ❌ — | ✅ 2024-25 | dashboard-only, follow-up-manual | Strong enrollment/FRPM source; staffing is a dashboard landing page not a real file link; crosswalk file exists but has no NCES field. |
| **KS** Kansas | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ⚠️ 2025-26 | ⚠️ 2024-25 | follow-up-manual | Real report-generator tool once past a tool-side TLS quirk; export each report to build the dataset. |
| **ME** Maine | ⚠️ 2024-25 | ⚠️ unknown | ✅ 2024-25 | ❌ — | ⚠️ unknown | dashboard-only, follow-up-manual | SPED confirmed; enrollment/staffing/FRPM/ELL need a human browser session on the dashboards. |
| **MP** Northern Mariana Islands | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ❌ — | ⚠️ unknown | dashboard-only, follow-up-manual | Correction to Jan-2026 "limited" — a real dashboard portal (EnVision PSS) with CSV-exportable sheets now exists. |
| **MT** Montana | ✅ 2024-25 | ⚠️ unknown | ⚠️ 2024-25 | ❌ — | ⚠️ unknown | dashboard-only, request-only | OPI data services, limited online portal access |
| **NC** North Carolina | ⚠️ current (multi-year selectable) | ⚠️ current | ✅ 2023-24 (FFY2023, submitted 2025) | ⚠️ current | ⚠️ post-2021-22 (Econ Disadvantaged, not raw FRPM) | dashboard-only, follow-up-manual | Real data exists behind an Oracle APEX app that blocks automated fetch — needs a human browser session to confirm CSV export. |
| **OK** Oklahoma | ✅ 2024-25 | ❌ — | ⚠️ — | ✅ 2024-25 | ⚠️ 2024-25 | dashboard-only, follow-up-manual | One of the strongest crosswalk finds in the whole campaign — a real NCES-ID column in the enrollment CSV itself. |
| **PR** Puerto Rico | ✅ 2024-25 | ⚠️ 2024-25 | ❌ — | ❌ — | ❌ — | dashboard-only, follow-up-manual | Correction to Jan-2026 "no portal found" — a real, current enrollment directory exists at perfilescolar.dde.pr. |
| **RI** Rhode Island | ✅ 2024-25 | ✅ 2024-25 | ⚠️ 2024-25 | ❌ — | ❌ — | dashboard-only, request-only | RIDE Data Center, 618 data collections (format unclear) |
| **VI** US Virgin Islands | ✅ 2024-25 | ⚠️ 2024-25 | ❌ — | ❌ — | ❌ — | follow-up-manual | Correction to Jan-2026 "no portal found" — real enrollment PDFs exist; SPED/FRPM/ELL/crosswalk still not found. |

## Tier 3 — blocked or largely unconfirmed (6)

| State | Enrollment | Staffing | SPED | Crosswalk | FRPM/ELL | Flags | Notes |
|---|---|---|---|---|---|---|---|
| **AZ** Arizona | ⚠️ 2024-25 | ⚠️ 2018-19 | ⚠️ 2018-19 | ❌ — | ⚠️ 2024-25 | blocked, follow-up-manual | Genuine Cloudflare block on a state marked "high priority" in the seed — worth a real browser session, likely rich data behind it. |
| **HI** Hawaii | ⚠️ 2022-23 | ⚠️ 2022-23 | ⚠️ 2022-23 | ❌ — | ⚠️ 2022-23 | dashboard-only, follow-up-manual | SPA needs Playwright; only a 2022-23 ERIC-mirrored PDF confirmed so far. |
| **MN** Minnesota | 🚫 — | 🚫 — | 🚫 — | ⚠️ 2025-26 | 🚫 — | blocked, dashboard-only, follow-up-manual | Genuine WAF block on the real data engine — needs a human browser visit, not a repeat automated attempt. |
| **NH** New Hampshire | ⚠️ 2025-26 | ⚠️ 2021-22 | ⚠️ 2024-25 | ⚠️ 2024-25 | ⚠️ 2022-23 | blocked, dashboard-only, follow-up-manual | Entire domain WAF-blocked to automated tools — needs a human browser pass before any conclusion is trusted; findings here are unverified ... |
| **VT** Vermont | ✅ 2025-26 | ⚠️ 2020-21 | ❌ — | ❌ — | ❌ — | blocked, follow-up-manual | Enrollment newer than NCES baseline (2025-26); staffing/SPED/FRPM need a human pass past the WAF. |
| **WY** Wyoming | ⚠️ 2025-26 (unconfirmed) | ⚠️ 2025-26 (unconfirmed) | ⚠️ 2025-26 (unconfirmed) | ❌ — | ⚠️ 2025-26 (unconfirmed) | dashboard-only, follow-up-manual | Publicly viewable (no login needed) but needs Playwright/a browser to actually extract — good candidate for the acquisition phase. |

## Integrated — current (no refresh needed) (6)

| State | Enrollment | Staffing | SPED | Crosswalk | FRPM/ELL | Flags | Notes |
|---|---|---|---|---|---|---|---|
| **CA** California | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ✅ — | — |  |
| **FL** Florida | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ❓ — | — |  |
| **MA** Massachusetts | ✅ 2025-26 | ✅ 2025-26 | ⚠️ 2025-26 | ✅ 2025-26 | ❓ — | — |  |
| **PA** Pennsylvania | ✅ 2024-25 | ✅ 2024-25 | ⚠️ 2024-25 | ✅ 2024-25 | ❓ — | — |  |
| **TX** Texas | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ✅ 2024-25 | ❓ — | — |  |
| **VA** Virginia | ✅ 2025-26 | ✅ 2025-26 | ✅ 2025-26 | ✅ 2025-26 | ❓ — | — |  |

---

## Legend

- ✅ `confirmed` — an actual downloadable file or API endpoint was fetched/verified
- ⚠️ `reported-partial` — portal/category exists but format/download unclear, or only headcounts/percentages where raw FTE/counts were sought
- ❌ `not-found` — looked, could not find
- 🚫 `blocked` — Cloudflare/WAF/login wall encountered (one-attempt rule applied, not retried)
- ❓ `unknown` — not yet probed

## Consolidated (multi-state) sources

### NCES CCD ST_LEAID (already in our own ingested data — the real crosswalk source)
- **Outcome:** confirmed (probed 2026-07-20)
- The state-ID<->NCES-LEAID crosswalk this campaign was probing SEA portals for already exists, for free, in data we ingested months ago: ccd_lea_052_*.csv (the NCES CCD LEA directory file) carries an ST_LEAID column (e.g. "NE-120056000", "WI-3862") 100% populated across all 3.8M rows / 56 jurisdictions in the 2024-25 file, paired 1:1 with the federal LEAID. `state_district_crosswalk` (REQ-027, 17,842 rows) is already sourced from exactly this field (source='nces_ccd', id_system='st_leaid'). See meta.crosswalk_correction for the full story — this superseded the per-state crosswalk_ids probing before it started; kept for the record so it isn't re-derived.

### IDEA Section 618 LEA Part B Child Count (data.ed.gov)
- **Outcome:** confirmed (probed 2026-07-20)
- **URL:** https://data.ed.gov/dataset/16968dd3-87bd-4e4a-92ed-50f03e6c4941
- District(LEA)-level SPED child counts by disability category, ALL states in one federal CSV per year, direct download URLs, current through 2024-25 (bchildcountdisabilitycategorylea2024-25.csv). State-reported actuals — a candidate to supersede the 2017-18 SPED baseline nationally under REQ-025, likely higher-yield than most per-state SEA probes. Note: 2021-22-and-earlier files bundled educational environment; 2022-23+ split it out — the LEA-level ed-environment companion dataset still needs locating.

### CRDC (Civil Rights Data Collection), 2021-22 public-use files
- **Outcome:** confirmed (probed 2026-07-20)
- **URL:** https://civilrightsdata.ed.gov/data
- 2021-22 CRDC public-use data files released January 2025 — the newest usable collection (2020-21 exists but is a COVID-excluded year). Refresh candidate for the 2017-18 CRDC-based SPED baseline (REQ-018), 4 years newer; VERIFY first that the 2021-22 elements include the staffing fields the baseline derivation used (SPED teachers / paraprofessionals). 2023-24 CRDC: submission closed 2025-04, release slipped from 'end of Dec 2025' to 'by 2026' (still N/A as of 2026-03 page review) — watch, do not wait.

### Urban Institute Education Data Portal API
- **Outcome:** confirmed (probed 2026-07-20)
- **URL:** https://educationdata.urban.org/api/v1/
- Clean REST API over CCD/CRDC/EDFacts. school-districts/ccd/directory returns state_leaid per district (verified 2023, e.g. NE-120056000) — useful to backfill/verify state_district_crosswalk (REQ-027) for every state without touching SEA portals, and as an independent validation source (REQ-021). Supplements, never substitutes for, SEA-actual data.

### CCSSO / AASA / NSBA / NAESP
- **Outcome:** not-found (probed 2026-07-20)
- Membership/policy organizations — publish aggregates and reports, not district-level FTE/enrollment/SPED files. Not acquisition sources.

---

## Full detail

Per-state portal URLs, probe receipts (URLs tried, outcomes), and raw notes live in `state_data_catalog.yaml` — this document is a summary view. Acquisition candidates and sign-off status: `ACQUISITION_PLAN.md`.

