#!/usr/bin/env python3
"""
Regenerate the SEA data-collection campaign's readable artifacts from
docs/state-integrations/state_data_catalog.yaml, the source of truth.

state_data_catalog.yaml is written/appended to by probe and acquisition
agents (structured records: availability, urls, probe/acquisition
receipts). This script derives two human-facing summaries from it:

  - docs/state-integrations/STATE_DATA_AVAILABILITY_ASSESSMENT.md
    A tiered summary (integrated/ready/manual/blocked) of every state,
    DC, and territory.
  - docs/state-integrations/ACQUISITION_PLAN.md
    The concrete list of files a Phase D acquisition pass could pull
    today (2+ of enrollment/staffing/SPED confirmed via a direct-download
    or API URL) — the sign-off artifact before any bulk downloading.
  - docs/state-integrations/MANUAL_WORK_QUEUE.md + .csv
    Every (state, category) that still needs a human — a real browser
    session, a login, or fresh discovery — sorted easiest-first. The CSV
    is meant to be opened in Numbers/Excel/VisiData for filtering/sorting.

Do NOT hand-edit any output file — edit the catalog and re-run this.

Usage:
    python infrastructure/scripts/utilities/gen_state_assessment.py
"""
import csv
import datetime
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / 'docs' / 'state-integrations' / 'state_data_catalog.yaml'
ASSESSMENT_PATH = REPO_ROOT / 'docs' / 'state-integrations' / 'STATE_DATA_AVAILABILITY_ASSESSMENT.md'
PLAN_PATH = REPO_ROOT / 'docs' / 'state-integrations' / 'ACQUISITION_PLAN.md'
QUEUE_MD_PATH = REPO_ROOT / 'docs' / 'state-integrations' / 'MANUAL_WORK_QUEUE.md'
QUEUE_CSV_PATH = REPO_ROOT / 'docs' / 'state-integrations' / 'MANUAL_WORK_QUEUE.csv'

CORE_TYPES = ('enrollment', 'staffing', 'sped')
EASY_ACCESS = {'direct-download', 'api'}

TIER_LABELS = {
    'integrated-current': 'Integrated — current (no refresh needed)',
    'integrated-refresh': 'Integrated — refresh available (newer year confirmed)',
    'tier1-ready': 'Tier 1 — ready to acquire now (2+ core categories, direct-download/API)',
    'tier2-manual': 'Tier 2 — data exists, needs manual/dashboard work',
    'tier3-blocked': 'Tier 3 — blocked or largely unconfirmed',
}
TIER_ORDER = ['integrated-refresh', 'tier1-ready', 'tier2-manual', 'tier3-blocked', 'integrated-current']

AVAILABILITY_ICONS = {
    'confirmed': '✅', 'reported-partial': '⚠️', 'not-found': '❌',
    'blocked': '🚫', 'unknown': '❓',
}

# Literal (not catalog-derived) — the post-acquisition inspection pass's findings.
# This is hand-authored synthesis from a 13-agent file-by-file inspection of everything
# under data/raw/state/ (2026-07-21), not something the catalog's structured fields can
# regenerate on their own. It's embedded here as a literal constant (rather than hand-edited
# into the output .md) specifically so gen_assessment() stays the single source of truth and
# test_generated_docs_are_not_stale keeps passing — see MANIFEST.md in each state's directory
# for the underlying per-file detail this section summarizes.
CAMPAIGN_FINDINGS_MD = '''\
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
'''


def core_confirmed_count(s):
    return sum(1 for t in CORE_TYPES if s['data'][t]['availability'] == 'confirmed')


def is_easy_access(rec):
    return rec['availability'] == 'confirmed' and rec['access'] in EASY_ACCESS


def tier_for(s):
    if s['integration']['status'] == 'integrated':
        return 'integrated-refresh' if 'refresh-candidate' in s['flags'] else 'integrated-current'
    cc = core_confirmed_count(s)
    easy_core = sum(1 for t in CORE_TYPES if is_easy_access(s['data'][t]))
    blocked = 'blocked' in s['flags']
    if blocked and cc < 2:
        return 'tier3-blocked'
    if easy_core >= 2:
        return 'tier1-ready'
    if cc >= 1:
        return 'tier2-manual'
    return 'tier3-blocked'


def fmt_cell(rec):
    icon = AVAILABILITY_ICONS.get(rec['availability'], '❓')
    year = rec.get('year') or '—'
    return f'{icon} {year}'


QUEUE_PRIORITY = {
    'confirmed-manual': (1, 'Confirmed — just needs a browser/login',
                          'A real file/export is known to exist; access is dashboard-export or '
                          'request-only. Lowest-uncertainty manual work — the destination is known, '
                          'just needs a human to click through or request access.'),
    'partial-manual': (2, 'Reported-partial — probably exists, needs verification',
                        'The probe found the portal/category but couldn\'t pin a specific file or '
                        'confirm the format. Worth a look before assuming it\'s not there.'),
    'blocked': (3, 'Blocked — needs a real browser past a WAF/Cloudflare wall',
                'An automated probe hit a real block (not a tool artifact). A human browser session '
                'will likely get through where the probe couldn\'t.'),
    'not-found': (4, 'Not found — needs fresh discovery',
                  'The probe looked and came up empty. Might genuinely not exist, or might need a '
                  'different search angle than the probe tried.'),
    'unknown': (5, 'Unprobed', 'No probe data recorded for this category at all.'),
}


def queue_bucket_for(rec):
    if rec['availability'] == 'confirmed':
        if rec['access'] in ('dashboard-export', 'request-only'):
            return 'confirmed-manual'
        return None  # direct-download/api and already acquirable — not manual work
    if rec['availability'] == 'reported-partial':
        return 'partial-manual'
    if rec['availability'] == 'blocked':
        return 'blocked'
    if rec['availability'] == 'not-found':
        return 'not-found'
    if rec['availability'] == 'unknown':
        return 'unknown'
    return None


def build_manual_queue(states):
    acquired = {
        (s['code'], a['category'])
        for s in states for a in (s.get('acquisitions') or [])
    }
    rows = []
    for s in states:
        for dtype in ('enrollment', 'staffing', 'sped', 'crosswalk_ids', 'frpm_ell'):
            if (s['code'], dtype) in acquired:
                continue
            rec = s['data'][dtype]
            bucket = queue_bucket_for(rec)
            if bucket is None:
                continue
            rank, _, _ = QUEUE_PRIORITY[bucket]
            rows.append({
                'priority_rank': rank,
                'priority': bucket,
                'state_code': s['code'],
                'state_name': s['name'],
                'category': dtype,
                'availability': rec['availability'],
                'access': rec.get('access') or '',
                'year': rec.get('year') or '',
                'format': rec.get('format') or '',
                'urls': '; '.join(rec.get('urls') or s.get('portals') or []),
                'state_flags': '; '.join(s.get('flags') or []),
                'notes': (s.get('notes') or '').replace('\n', ' ').strip(),
            })
    rows.sort(key=lambda r: (r['priority_rank'], r['state_code'], r['category']))
    return rows


def gen_manual_work_queue(states, today):
    rows = build_manual_queue(states)

    # --- CSV: flat, sortable/filterable in Numbers/Excel/VisiData ---
    fieldnames = ['priority_rank', 'priority', 'state_code', 'state_name', 'category',
                  'availability', 'access', 'year', 'format', 'urls', 'state_flags', 'notes']
    with open(QUEUE_CSV_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # --- Markdown: grouped by priority bucket, easiest first ---
    lines = []
    lines.append('# Manual SEA Data Work Queue')
    lines.append('')
    lines.append(f'**Regenerated:** {today} (auto-generated from `state_data_catalog.yaml` — DO '
                  'NOT hand-edit, edit the catalog and re-run '
                  '`infrastructure/scripts/utilities/gen_state_assessment.py`)')
    lines.append(f'**{len(rows)} (state, category) pairs** still need a human — not already '
                  'auto-acquired (Phase D) and not scriptable without one. A flat, filterable '
                  'version of this same data: `MANUAL_WORK_QUEUE.csv` (open in Numbers/Excel/'
                  'VisiData, sort/filter by any column).')
    lines.append('')
    lines.append('Sorted easiest-first: confirmed-but-manual, then reported-partial, then blocked, '
                  'then not-found, then unprobed.')
    lines.append('')
    lines.append('---')
    lines.append('')

    by_bucket = {}
    for r in rows:
        by_bucket.setdefault(r['priority'], []).append(r)

    for bucket, (rank, label, desc) in sorted(QUEUE_PRIORITY.items(), key=lambda kv: kv[1][0]):
        bucket_rows = by_bucket.get(bucket, [])
        if not bucket_rows:
            continue
        lines.append(f'## {rank}. {label} ({len(bucket_rows)})')
        lines.append('')
        lines.append(desc)
        lines.append('')
        lines.append('| State | Category | Year | Format | Access | URL(s) | Flags | Notes |')
        lines.append('|---|---|---|---|---|---|---|---|')
        for r in bucket_rows:
            notes = r['notes']
            if len(notes) > 130:
                notes = notes[:127] + '...'
            lines.append(
                f"| **{r['state_code']}** {r['state_name']} | {r['category']} | "
                f"{r['year'] or '—'} | {r['format'] or '—'} | {r['access'] or '—'} | "
                f"{r['urls'] or '—'} | {r['state_flags'] or '—'} | {notes} |"
            )
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## Notes')
    lines.append('')
    lines.append('- A row disappears from this queue once its category gets an `acquisitions[]` '
                  'receipt in the catalog — re-run this generator after adding one manually.')
    lines.append('- "Confirmed" rows already have a real, verified file/endpoint recorded — the '
                  'URL(s) column is where to start, not a guess.')
    lines.append('- Full probe history (what was tried, what the raw findings were) lives in each '
                  "state's `probes[]` block in `state_data_catalog.yaml`.")
    lines.append('')

    QUEUE_MD_PATH.write_text('\n'.join(lines) + '\n')


def gen_assessment(catalog, today):
    states = sorted(catalog['states'], key=lambda s: s['code'])
    for s in states:
        s['_tier'] = tier_for(s)

    counts = Counter(s['_tier'] for s in states)

    lines = []
    lines.append('# State Education Data Availability Assessment')
    lines.append('')
    lines.append(f'**Regenerated:** {today} (auto-generated from '
                  '`docs/state-integrations/state_data_catalog.yaml` — DO NOT hand-edit this '
                  'file, edit the catalog and re-run '
                  '`infrastructure/scripts/utilities/gen_state_assessment.py`)')
    lines.append('**Purpose:** Evaluate state education agency (SEA) data portals for Learning '
                  'Connection Time (LCT) metric integration — enrollment, staffing, and SPED data '
                  'at the district level, plus the state-ID<->NCES-LEAID crosswalk.')
    lines.append(f'**Entities assessed:** {len(states)} (50 states + DC + 5 territories)')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## Precedence context (why this campaign matters, and where it doesn\'t)')
    lines.append('')
    lines.append(catalog['meta']['precedence_context'])
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## Format preference policy')
    lines.append('')
    lines.append(catalog['meta']['format_preference'])
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## Summary')
    lines.append('')
    lines.append('| Tier | Count | Meaning |')
    lines.append('|---|---|---|')
    for tier in TIER_ORDER:
        lines.append(f'| {TIER_LABELS[tier]} | {counts.get(tier, 0)} | |')
    lines.append('')
    lines.append('**Crosswalk correction (2026-07-20):** most SEA portals don\'t publish their own '
                  'state-ID->NCES-LEAID crosswalk file, and the per-state Crosswalk column below '
                  'reports exactly that, honestly. But this was never the right place to look — '
                  '`state_district_crosswalk` (REQ-027, 17,842 rows) is already populated from the '
                  '`ST_LEAID` column in NCES CCD\'s own LEA directory file, which we\'d already '
                  'ingested and which is 100% populated across all 56 jurisdictions. **A state\'s '
                  'Crosswalk cell showing ❌ is not a gap** — see "Consolidated sources" below and '
                  'the catalog\'s `meta.crosswalk_correction` for the full story. OK, WI, and KY are '
                  'still worth noting as states with an independent SEA-published crosswalk (useful '
                  'for cross-validation per REQ-021), just not as an acquisition target.')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append(CAMPAIGN_FINDINGS_MD)

    for tier in TIER_ORDER:
        tier_states = [s for s in states if s['_tier'] == tier]
        if not tier_states:
            continue
        lines.append(f'## {TIER_LABELS[tier]} ({len(tier_states)})')
        lines.append('')
        lines.append('| State | Enrollment | Staffing | SPED | Crosswalk | FRPM/ELL | Flags | Notes |')
        lines.append('|---|---|---|---|---|---|---|---|')
        for s in tier_states:
            d = s['data']
            flags = ', '.join(s['flags']) if s['flags'] else '—'
            notes = (s.get('notes') or '').replace('\n', ' ').strip()
            if len(notes) > 140:
                notes = notes[:137] + '...'
            lines.append(
                f"| **{s['code']}** {s['name']} | {fmt_cell(d['enrollment'])} | "
                f"{fmt_cell(d['staffing'])} | {fmt_cell(d['sped'])} | "
                f"{fmt_cell(d['crosswalk_ids'])} | {fmt_cell(d['frpm_ell'])} | {flags} | {notes} |"
            )
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## Legend')
    lines.append('')
    lines.append('- ✅ `confirmed` — an actual downloadable file or API endpoint was fetched/verified')
    lines.append('- ⚠️ `reported-partial` — portal/category exists but format/download unclear, or '
                  'only headcounts/percentages where raw FTE/counts were sought')
    lines.append('- ❌ `not-found` — looked, could not find')
    lines.append('- 🚫 `blocked` — Cloudflare/WAF/login wall encountered (one-attempt rule applied, '
                  'not retried)')
    lines.append('- ❓ `unknown` — not yet probed')
    lines.append('')
    lines.append('## Consolidated (multi-state) sources')
    lines.append('')
    for src in catalog.get('consolidated_sources', []):
        lines.append(f"### {src['name']}")
        lines.append(f"- **Outcome:** {src['outcome']} (probed {src['probed']})")
        if src.get('url'):
            lines.append(f"- **URL:** {src['url']}")
        lines.append(f"- {src['detail']}")
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## Full detail')
    lines.append('')
    lines.append('Per-state portal URLs, probe receipts (URLs tried, outcomes), and raw notes live '
                  'in `state_data_catalog.yaml` — this document is a summary view. Acquisition '
                  'candidates and sign-off status: `ACQUISITION_PLAN.md`.')
    lines.append('')

    ASSESSMENT_PATH.write_text('\n'.join(lines) + '\n')
    return states


def gen_acquisition_plan(states, today):
    ready = sorted((s for s in states if s['_tier'] in ('tier1-ready', 'integrated-refresh')),
                    key=lambda s: s['code'])

    lines = []
    lines.append('# SEA Data Acquisition Plan — Phase C')
    lines.append('')
    lines.append(f'**Generated:** {today} from `state_data_catalog.yaml` (Phase B probe results, '
                  'PR #601/#602).')
    lines.append("**Status: AWAITING IAN'S SIGN-OFF.** Nothing in this list has been downloaded. "
                  'Per the campaign plan, this is the hard human gate before any bulk acquisition '
                  '(Phase D) begins.')
    lines.append('')
    lines.append("## What's in scope")
    lines.append('')
    lines.append(f'{len(ready)} entities have at least 2 of 3 core categories (enrollment/staffing/'
                  'SPED) confirmed via a direct-download file or API endpoint — genuinely ready to '
                  'acquire without further manual portal work. This list is everything a Phase D '
                  'acquisition agent could pull today.')
    lines.append('')
    lines.append('Explicitly OUT of scope for this list (Tier 2/3, need manual/dashboard work '
                  'first, or blocked): see the assessment doc\'s Tier 2/3 tables. Nothing there '
                  'should be bulk-downloaded yet.')
    lines.append('')
    lines.append('**Note on crosswalk_ids rows below:** these are a bonus if a state happens to '
                  'publish its own state-ID<->NCES-LEAID file — NOT something to wait on. The real '
                  'crosswalk (REQ-027, 17,842 rows) already exists from NCES CCD\'s ST_LEAID column, '
                  'ingested months before this campaign. See the assessment doc\'s crosswalk '
                  'correction note.')
    lines.append('')
    lines.append('**Caveat — "confirmed direct-download" is not always one bulk statewide file.** '
                  'A handful of entries below resolve to a *per-district* file pattern rather than '
                  'a single statewide download — e.g. **CT**\'s URL is one example district\'s PDF '
                  '(the state publishes ~200 of these, one per LEA code) and **AL**\'s SPED source '
                  'is ~140 separate per-district PDFs. The blockquoted note under each state below '
                  'carries this caveat when it applies — a Phase D acquisition agent must read it '
                  'before assuming a single fetch suffices, since enumerating district codes to '
                  'build the full URL list is itself work that hasn\'t been scoped here.')
    lines.append('')
    lines.append('---')
    lines.append('')

    for s in ready:
        lines.append(f"## {s['code']} — {s['name']}")
        if s['integration']['status'] == 'integrated':
            lines.append(f"*Refresh of existing integration: {s['integration']['detail']}*")
        if s.get('notes'):
            lines.append(f"> {s['notes']}")
        lines.append('')
        lines.append('| Category | Year | Format | Access | URL(s) |')
        lines.append('|---|---|---|---|---|')
        for dtype in ('enrollment', 'staffing', 'sped', 'crosswalk_ids', 'frpm_ell'):
            rec = s['data'][dtype]
            if rec['availability'] != 'confirmed' or not rec['urls']:
                continue
            urls = '<br>'.join(rec['urls'])
            lines.append(f"| {dtype} | {rec.get('year') or '—'} | {rec.get('format') or '—'} | "
                          f"{rec.get('access') or '—'} | {urls} |")
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## Acquisition mechanics (Phase D, once approved)')
    lines.append('')
    lines.append('- Download to `data/raw/state/{state}/{year}/`, never modify existing raw files.')
    lines.append('- Every file gets an acquisition receipt in the catalog: source URL, retrieval '
                  'date, sha256, size — plus a `MANIFEST.md` per new state directory.')
    lines.append('- Spot-verify each file opens/parses (pandas read of first rows) before marking '
                  'it acquired.')
    lines.append('- Failures/blocks on retry -> flag `follow-up-manual`, one-attempt rule applies, '
                  'do not retry-loop.')
    lines.append('')
    lines.append('## Not in this list — flagged for manual follow-up')
    lines.append('')
    manual = sorted((s for s in states if s['_tier'] in ('tier2-manual', 'tier3-blocked')),
                     key=lambda s: s['code'])
    lines.append(f'{len(manual)} entities need a human browser session (WAF blocks, JS-only '
                 'dashboards, login walls) or more manual investigation before any file can be '
                 'reliably acquired. Full detail in the assessment doc\'s Tier 2/Tier 3 tables — '
                 'notably: **AZ, MN, NH, VT** are genuine WAF blocks (not tool artifacts); **HI, '
                 'WY, KS** are JS-rendered dashboards a probe without Playwright could not read; '
                 '**MO, NM, GA** (crosswalk/deeper data) need a login or formal data request.')
    lines.append('')

    PLAN_PATH.write_text('\n'.join(lines) + '\n')


def main():
    with open(CATALOG_PATH) as f:
        catalog = yaml.safe_load(f)
    today = datetime.date.today().isoformat()
    states = gen_assessment(catalog, today)
    gen_acquisition_plan(states, today)
    gen_manual_work_queue(states, today)
    print(f'Wrote {ASSESSMENT_PATH}')
    print(f'Wrote {PLAN_PATH}')
    print(f'Wrote {QUEUE_MD_PATH}')
    print(f'Wrote {QUEUE_CSV_PATH}')


if __name__ == '__main__':
    main()
