"""
Tests for the REAL SEA merge precedence logic (issue #14).

Unlike tests/test_data_precedence.py (which pins REQ wording against mocks defined
inside the test file), these tests import infrastructure.database.migrations.
merge_sea_precedence itself, so regressions in the shipped decision logic fail here.

Decided semantics (project owner, 2026-07-01):
- Precedence (REQ-023): year-matched NCES > year-matched SEA > older NCES > older SEA.
  SEA never unconditionally overwrites NCES; it supplements when NCES lacks the field
  or SEA is strictly newer.
- COVID years (2019-20..2022-23) are never admitted.
- Blend window = 3 consecutive school years (max start-year span 2).
- Suppressed/masked values are None and are never merged.
"""

import pytest

from infrastructure.database.migrations.merge_sea_precedence import (
    SEA_STATES,
    apply_sea_supplement,
    decide_precedence,
    get_temporal_flags,
)
from infrastructure.database.models import StaffCountsEffective
from infrastructure.database.school_year import MAX_BLEND_SPAN


# =============================================================================
# decide_precedence — the pure REQ-023 decision
# =============================================================================

class TestDecidePrecedence:

    def test_year_matched_nces_wins(self):
        decision, reason = decide_precedence('2023-24', '2023-24', 100.0, 90.0)
        assert decision == 'nces'
        assert 'REQ-023' in reason

    def test_newer_nces_wins_over_older_sea(self):
        decision, _ = decide_precedence('2024-25', '2023-24', 100.0, 90.0)
        assert decision == 'nces'

    def test_strictly_newer_sea_wins(self):
        decision, _ = decide_precedence('2023-24', '2024-25', 100.0, 90.0)
        assert decision == 'sea'

    def test_sea_fills_gap_when_nces_lacks_value(self):
        # Even an older SEA year supplements when NCES has no value (within window)
        for sea_year in ('2023-24', '2024-25', '2025-26'):
            decision, _ = decide_precedence('2025-26', sea_year, None, 90.0)
            assert decision == 'sea', sea_year

    def test_covid_sea_year_rejected(self):
        for covid_year in ('2019-20', '2020-21', '2021-22', '2022-23'):
            decision, reason = decide_precedence('2023-24', covid_year, None, 90.0)
            assert decision == 'skip', covid_year
            assert 'COVID' in reason

    def test_covid_sea_rejected_even_when_nces_lacks_value(self):
        decision, _ = decide_precedence('2023-24', '2022-23', None, 90.0)
        assert decision == 'skip'

    def test_suppressed_sea_value_skipped(self):
        decision, reason = decide_precedence('2023-24', '2024-25', 100.0, None)
        assert decision == 'skip'
        assert 'suppressed' in reason.lower()
        # ...and also when NCES lacks the value: None never merges
        decision, _ = decide_precedence('2023-24', '2024-25', None, None)
        assert decision == 'skip'

    def test_span_two_is_within_window(self):
        decision, _ = decide_precedence('2023-24', '2025-26', 100.0, 90.0)
        assert decision == 'sea'  # strictly newer, span 2 == MAX_BLEND_SPAN

    def test_span_three_rejected(self):
        # Old code admitted span <= 3; decided window is span <= 2
        decision, reason = decide_precedence('2023-24', '2026-27', None, 90.0)
        assert decision == 'skip'
        assert 'blend window' in reason

    def test_malformed_year_skipped(self):
        decision, _ = decide_precedence('2023-24', 'FY2024', 100.0, 90.0)
        assert decision == 'skip'
        decision, _ = decide_precedence('', '2024-25', 100.0, 90.0)
        assert decision == 'skip'


# =============================================================================
# get_temporal_flags — window edges
# =============================================================================

class TestTemporalFlags:

    def test_same_and_adjacent_years_unflagged(self):
        assert get_temporal_flags(0) == []
        assert get_temporal_flags(1) == []

    def test_window_edge_warns(self):
        assert get_temporal_flags(MAX_BLEND_SPAN) == ['WARN_YEAR_GAP']

    def test_beyond_window_errors(self):
        assert get_temporal_flags(MAX_BLEND_SPAN + 1) == ['ERR_SPAN_EXCEEDED']
        assert get_temporal_flags(10) == ['ERR_SPAN_EXCEEDED']


# =============================================================================
# apply_sea_supplement — merged rows stay internally coherent
# =============================================================================

def _nces_row() -> StaffCountsEffective:
    row = StaffCountsEffective(
        district_id='9999999',
        effective_year='2023-24',
        primary_source='nces_ccd',
        teachers_total=100.0,
        teachers_elementary=50.0,
        teachers_secondary=40.0,
        teachers_kindergarten=8.0,
    )
    row.calculate_scopes()
    return row


class TestApplySeaSupplement:

    def test_teachers_total_updated_from_sea(self):
        row = _nces_row()
        apply_sea_supplement(row, 'TX', '2023-24', '2024-25', 105.5, 'SEA strictly newer')
        assert float(row.teachers_total) == 105.5

    def test_teachers_k12_stays_consistent_with_per_level_fields(self):
        """The issue #14 incoherence: teachers_k12 must always equal the sum of its
        NCES per-level inputs, before and after the SEA supplement — and stay that
        way even if calculate_scopes() runs again later."""
        row = _nces_row()
        expected_k12 = 50.0 + 40.0 + 8.0
        assert float(row.teachers_k12) == expected_k12

        apply_sea_supplement(row, 'TX', '2023-24', '2024-25', 105.5, 'SEA strictly newer')
        assert float(row.teachers_k12) == expected_k12
        assert float(row.scope_teachers_only) == expected_k12

        row.calculate_scopes()  # idempotent: nothing reverts, nothing drifts
        assert float(row.teachers_k12) == expected_k12
        assert float(row.teachers_total) == 105.5

    def test_primary_source_stays_nces_baseline(self):
        """Per-level fields and every scope remain NCES-derived, so primary_source
        keeps its NCES value; SEA provenance is field-level in sources_used."""
        row = _nces_row()
        apply_sea_supplement(row, 'TX', '2023-24', '2024-25', 105.5, 'SEA strictly newer')
        assert row.primary_source == 'nces_ccd'

    def test_sources_used_records_field_level_provenance(self):
        row = _nces_row()
        apply_sea_supplement(row, 'TX', '2023-24', '2024-25', 105.5, 'SEA strictly newer')
        by_source = {s['source']: s for s in row.sources_used}
        assert by_source['tx_sea']['year'] == '2024-25'
        assert by_source['tx_sea']['fields'] == ['teachers_total']
        assert by_source['nces_ccd']['year'] == '2023-24'
        assert 'teachers_k12' in by_source['nces_ccd']['fields']

    def test_resolution_notes_are_honest(self):
        row = _nces_row()
        apply_sea_supplement(row, 'MA', '2023-24', '2024-25', 88.0, 'SEA strictly newer')
        notes = row.resolution_notes
        assert 'teachers_total from MA SEA (2024-25)' in notes
        assert 'remain NCES' in notes


# =============================================================================
# Configuration sanity
# =============================================================================

class TestSeaStatesConfig:

    def test_ma_year_matches_teacher_file(self):
        # The MA teacher-FTE file is the 2024-25 export (issue #23 year mislabel)
        assert SEA_STATES['MA']['year'] == '2024-25'

    def test_no_covid_years_configured(self):
        from infrastructure.database.school_year import is_covid_year
        for state, cfg in SEA_STATES.items():
            assert not is_covid_year(cfg['year']), state
