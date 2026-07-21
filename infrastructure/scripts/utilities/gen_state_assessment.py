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
