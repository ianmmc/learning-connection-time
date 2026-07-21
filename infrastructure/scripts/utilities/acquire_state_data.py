#!/usr/bin/env python3
"""
Phase D of the SEA data-collection campaign: download every file listed in
docs/state-integrations/ACQUISITION_PLAN.md (the Ian-approved Tier-1-ready +
integrated-refresh set from state_data_catalog.yaml) and record a receipt.

Scope is intentionally narrow: only (availability=confirmed AND access in
{direct-download, api}) entries for states the tiering logic (imported from
gen_state_assessment.py) classifies as tier1-ready or integrated-refresh —
exactly what a human reviewing ACQUISITION_PLAN.md signed off on. Never
downloads a dashboard-export/request-only URL as if it were a data file.

One-attempt rule: a failed fetch is logged and flagged, never retried in
this run. Existing files under data/raw/state/ are never overwritten.

Usage:
    python infrastructure/scripts/utilities/acquire_state_data.py [--dry-run]
"""
import argparse
import hashlib
import importlib.util
import io
import re
import sys
import urllib.parse
from pathlib import Path

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = REPO_ROOT / 'docs' / 'state-integrations' / 'state_data_catalog.yaml'
RAW_STATE_DIR = REPO_ROOT / 'data' / 'raw' / 'state'
GEN_SCRIPT_PATH = REPO_ROOT / 'infrastructure' / 'scripts' / 'utilities' / 'gen_state_assessment.py'

BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
    'Accept': '*/*',
}
TIMEOUT_S = 90
DATA_TYPES = ('enrollment', 'staffing', 'sped', 'crosswalk_ids', 'frpm_ell')
DOWNLOADABLE_ACCESS = {'direct-download', 'api'}

# Socrata resource endpoints support swapping the extension for a different
# export format. Our format-preference policy (meta.format_preference) says
# CSV beats a bare JSON response for our pandas-based tooling.
SOCRATA_RESOURCE_RE = re.compile(r'^(https?://[^/]+/resource/[A-Za-z0-9-]+)\.json(\?.*)?$')


def load_gen_module():
    spec = importlib.util.spec_from_file_location('gen_state_assessment', GEN_SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def year_slug(year_value):
    if not year_value:
        return 'undated'
    m = re.search(r'(\d{4})-(\d{2})', str(year_value))
    if m:
        return f'{m.group(1)}_{m.group(2)}'
    m2 = re.search(r'(\d{4})', str(year_value))
    if m2:
        return m2.group(1)
    return 'undated'


def prefer_csv_over_json(url):
    m = SOCRATA_RESOURCE_RE.match(url)
    if m:
        return m.group(1) + '.csv' + (m.group(2) or '')
    return url


KNOWN_EXTS = {'.csv', '.xlsx', '.xls', '.pdf', '.json', '.zip', '.xml'}
CONTENT_TYPE_EXT = {
    'text/csv': '.csv',
    'application/csv': '.csv',
    'application/pdf': '.pdf',
    'application/json': '.json',
    'application/zip': '.zip',
    'application/xml': '.xml',
    'text/xml': '.xml',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'application/vnd.ms-excel': '.xls',
}
FORMAT_HINT_EXT = [
    ('CSV', '.csv'), ('JSON', '.json'), ('XML', '.xml'),
    ('XLSX', '.xlsx'), ('XLS', '.xls'), ('Excel', '.xlsx'),
    ('PDF', '.pdf'), ('ZIP', '.zip'), ('API', '.json'),
]


def guess_extension(url, format_hint, content_type):
    parsed = urllib.parse.urlparse(url)
    url_ext = Path(parsed.path).suffix.lower()
    if url_ext in KNOWN_EXTS:
        return url_ext
    if content_type:
        base_ct = content_type.split(';')[0].strip().lower()
        if base_ct in CONTENT_TYPE_EXT:
            return CONTENT_TYPE_EXT[base_ct]
    if format_hint:
        for needle, ext in FORMAT_HINT_EXT:
            if needle.lower() in format_hint.lower():
                return ext
    return '.dat'


def filename_for(url, dtype, index, ext):
    parsed = urllib.parse.urlparse(url)
    stem = urllib.parse.unquote(Path(parsed.path).stem)
    # strip a trailing known extension the stem may already carry (e.g. a URL
    # path of "...report.xlsx.aspx" leaves stem "...report.xlsx" after Path
    # only strips the outer ".aspx" — don't double it up with the guessed ext)
    for known in KNOWN_EXTS:
        if stem.lower().endswith(known):
            stem = stem[:-len(known)]
            break
    if not stem or stem in ('query', 'download', 'FileDownloadWebHandler'):
        stem = f'{dtype}_{index}'
    return f'{stem}{ext}'


def sniff_verify(content, suffix):
    suffix = suffix.lower()
    try:
        if suffix in ('.csv',):
            import pandas as pd
            df = pd.read_csv(io.BytesIO(content), nrows=5)
            return len(df.columns) > 0
        if suffix in ('.xlsx', '.xls'):
            import pandas as pd
            df = pd.read_excel(io.BytesIO(content), nrows=5)
            return len(df.columns) > 0
        if suffix == '.pdf':
            return content[:5] == b'%PDF-'
        if suffix == '.json':
            import json
            json.loads(content)
            return True
        if suffix == '.zip':
            return content[:2] == b'PK'
    except Exception:
        return False
    return len(content) > 0


def fetch(session, url):
    try:
        resp = session.get(url, headers=BROWSER_HEADERS, timeout=TIMEOUT_S, allow_redirects=True)
    except requests.RequestException as e:
        return None, None, str(e)
    if resp.status_code != 200:
        return None, None, f'HTTP {resp.status_code}'
    return resp.content, resp.headers.get('Content-Type'), None


def acquire(catalog, dry_run):
    mod = load_gen_module()
    states = sorted(catalog['states'], key=lambda s: s['code'])
    for s in states:
        s['_tier'] = mod.tier_for(s)
    ready = [s for s in states if s['_tier'] in ('tier1-ready', 'integrated-refresh')]

    session = requests.Session()
    total_ok, total_fail, total_skip = 0, 0, 0
    failures = []
    # url -> (out_path, sha256, size, verified) — one fetch per distinct URL,
    # even when the same file legitimately covers multiple categories (e.g.
    # a per-district PDF that answers enrollment+staffing+sped+frpm_ell at once).
    url_cache = {}

    for s in ready:
        code = s['code']
        state_dir_name = s['name'].lower().replace(' ', '-').replace(',', '')
        for dtype in DATA_TYPES:
            rec = s['data'][dtype]
            if rec['availability'] != 'confirmed' or rec['access'] not in DOWNLOADABLE_ACCESS:
                continue
            urls = rec.get('urls') or []
            if not urls:
                continue
            yslug = year_slug(rec.get('year'))
            target_dir = RAW_STATE_DIR / state_dir_name / yslug
            for i, raw_url in enumerate(urls):
                url = prefer_csv_over_json(raw_url)

                if url in url_cache:
                    cached = url_cache[url]
                    if cached is None:
                        continue  # this URL already failed once this run
                    out_path, sha256, size, verified = cached
                    s.setdefault('acquisitions', []).append({
                        'source_url': raw_url, 'retrieved': '2026-07-20',
                        'path': str(out_path.relative_to(REPO_ROOT)), 'sha256': sha256,
                        'size_bytes': size, 'category': dtype, 'verified': verified,
                    })
                    total_ok += 1
                    print(f"{'OK   ' if verified else 'UNVER'} {code} {dtype:14} (shared file) -> "
                          f"{out_path.relative_to(REPO_ROOT)}")
                    continue

                if dry_run:
                    ext = guess_extension(url, rec.get('format'), None)
                    fname = filename_for(url, dtype, i, ext)
                    print(f'WOULD {code} {dtype:14} {url} -> {target_dir.relative_to(REPO_ROOT)}/{fname}')
                    continue

                content, content_type, err = fetch(session, url)
                if content is None:
                    total_fail += 1
                    url_cache[url] = None
                    failures.append({'code': code, 'dtype': dtype, 'url': url, 'error': err})
                    print(f'FAIL  {code} {dtype:14} {url}  ({err})')
                    continue

                ext = guess_extension(url, rec.get('format'), content_type)
                fname = filename_for(url, dtype, i, ext)
                out_path = target_dir / fname
                if out_path.exists():
                    total_skip += 1
                    url_cache[url] = (out_path, None, None, None)
                    print(f'SKIP  {code} {dtype:14} already exists: {out_path.relative_to(REPO_ROOT)}')
                    continue

                verified = sniff_verify(content, ext)
                target_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(content)
                sha256 = hashlib.sha256(content).hexdigest()
                url_cache[url] = (out_path, sha256, len(content), verified)

                s.setdefault('acquisitions', []).append({
                    'source_url': raw_url,
                    'retrieved': '2026-07-20',
                    'path': str(out_path.relative_to(REPO_ROOT)),
                    'sha256': sha256,
                    'size_bytes': len(content),
                    'category': dtype,
                    'verified': verified,
                })
                total_ok += 1
                flag = 'OK   ' if verified else 'UNVER'
                print(f'{flag} {code} {dtype:14} {len(content):>10,}B -> {out_path.relative_to(REPO_ROOT)}')

    print()
    print(f'Acquired: {total_ok}  Skipped (already present): {total_skip}  Failed: {total_fail}')
    if failures:
        print('\nFailures (flagged follow-up-manual, not retried):')
        for f in failures:
            print(f"  {f['code']} {f['dtype']}: {f['error']} — {f['url']}")
        codes_failed = {f['code'] for f in failures}
        for s in states:
            if s['code'] in codes_failed and 'follow-up-manual' not in s.get('flags', []):
                s['flags'].append('follow-up-manual')
    return states, failures


def write_catalog(catalog):
    class Dumper(yaml.SafeDumper):
        pass

    def str_presenter(dumper, data):
        if len(data) > 90:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='>')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)

    Dumper.add_representer(str, str_presenter)

    with open(CATALOG_PATH, 'w') as f:
        f.write('# State SEA data catalog — source of truth for the state-data campaign.\n')
        f.write('# STATE_DATA_AVAILABILITY_ASSESSMENT.md is regenerated from this file.\n')
        f.write('# Probe/acquisition agents append receipt records here; humans review diffs.\n')
        clean = {'meta': catalog['meta'], 'consolidated_sources': catalog['consolidated_sources'],
                  'states': [{k: v for k, v in s.items() if not k.startswith('_')}
                             for s in catalog['states']]}
        yaml.dump(clean, f, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    with open(CATALOG_PATH) as f:
        catalog = yaml.safe_load(f)

    states, failures = acquire(catalog, args.dry_run)

    if not args.dry_run:
        write_catalog(catalog)
        print(f'\nWrote {CATALOG_PATH}')

    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
