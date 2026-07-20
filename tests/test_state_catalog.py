"""Fitness tests for docs/state-integrations/state_data_catalog.yaml — the
source of truth for the SEA data-collection campaign.

The catalog is written by probe/acquisition agents in structured records;
these tests keep the record shape honest so fleet edits can't silently drift
(same pattern as tests/test_arch_manifest.py for arch-manifest.json).
"""

import re
from pathlib import Path

import pytest
import yaml

CATALOG_PATH = Path(__file__).parent.parent / 'docs' / 'state-integrations' / 'state_data_catalog.yaml'

US_STATE_CODES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID',
    'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS',
    'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK',
    'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
    'WI', 'WY',
}
TERRITORY_CODES = {'DC', 'PR', 'VI', 'GU', 'AS', 'MP'}

DATA_TYPES = {'enrollment', 'staffing', 'sped', 'crosswalk_ids', 'frpm_ell'}
INTEGRATION_STATUSES = {'none', 'crosswalk-only', 'partial', 'integrated'}


@pytest.fixture(scope='module')
def catalog():
    with open(CATALOG_PATH) as f:
        return yaml.safe_load(f)


def test_catalog_loads_and_has_top_level_shape(catalog):
    assert set(catalog) >= {'meta', 'consolidated_sources', 'states'}
    assert catalog['meta']['version']


def test_full_entity_coverage(catalog):
    codes = [s['code'] for s in catalog['states']]
    assert len(codes) == len(set(codes)), 'duplicate state records'
    assert set(codes) == US_STATE_CODES | TERRITORY_CODES


def test_every_state_record_has_required_fields(catalog):
    required = {'code', 'name', 'portals', 'integration', 'data',
                'probes', 'acquisitions', 'flags'}
    for s in catalog['states']:
        missing = required - set(s)
        assert not missing, f"{s.get('code', '?')}: missing {missing}"
        assert set(s['data']) == DATA_TYPES, f"{s['code']}: data types {set(s['data'])}"
        assert s['integration']['status'] in INTEGRATION_STATUSES, s['code']


def test_availability_and_flag_values_from_vocab(catalog):
    avail_vocab = set(catalog['meta']['availability_vocab'])
    flags_vocab = set(catalog['meta']['flags_vocab'])
    for s in catalog['states']:
        for dtype, rec in s['data'].items():
            assert rec['availability'] in avail_vocab, \
                f"{s['code']}.{dtype}: {rec['availability']!r}"
            assert isinstance(rec['urls'], list), f"{s['code']}.{dtype}: urls not a list"
        for flag in s['flags']:
            assert flag in flags_vocab, f"{s['code']}: unknown flag {flag!r}"


def test_years_are_quoted_strings_not_yaml_scalars(catalog):
    """YAML's loose typing can silently turn 2024 into an int or NO into a
    bool (the Norway problem). Years must survive as strings."""
    for s in catalog['states']:
        assert isinstance(s['code'], str) and re.fullmatch(r'[A-Z]{2}', s['code'])
        for dtype, rec in s['data'].items():
            year = rec.get('year')
            assert year is None or isinstance(year, str), \
                f"{s['code']}.{dtype}: year {year!r} is {type(year).__name__}, want str"


def test_probe_receipts_are_structured(catalog):
    """Probe agents must leave auditable receipts, not prose."""
    for s in catalog['states']:
        for probe in s['probes']:
            missing = {'date', 'urls_tried', 'outcome'} - set(probe)
            assert not missing, f"{s['code']} probe: missing {missing}"


def test_acquisition_receipts_are_structured_and_files_exist(catalog):
    """Every acquisition receipt must name an existing file with a sha256."""
    repo_root = CATALOG_PATH.parent.parent.parent
    for s in catalog['states']:
        for acq in s['acquisitions']:
            missing = {'source_url', 'retrieved', 'path', 'sha256'} - set(acq)
            assert not missing, f"{s['code']} acquisition: missing {missing}"
            assert re.fullmatch(r'[0-9a-f]{64}', acq['sha256']), \
                f"{s['code']}: bad sha256 {acq['sha256']!r}"
            assert (repo_root / acq['path']).exists(), \
                f"{s['code']}: receipt names missing file {acq['path']}"
