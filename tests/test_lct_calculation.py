"""
Tests for LCT (Learning Connection Time) calculation.
Covers: REQ-001 (core LCT formula)

These tests exercise the REAL production function
(infrastructure/scripts/analyze/calculate_lct_variants.py::calculate_lct),
not a placeholder. The production function:
  - returns the raw, UNROUNDED float (rounding happens at export time)
  - returns None when staff_count <= 0 OR enrollment <= 0

Run: pytest tests/test_lct_calculation.py -v
"""

import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from infrastructure.scripts.analyze import calculate_lct_variants
from infrastructure.scripts.analyze.calculate_lct_variants import (
    calculate_lct,
    clear_lct_calculations,
)


class TestLCTCalculation:
    """REQ-001: LCT = (Daily Instructional Minutes × Staff) / Enrollment"""

    # --- Happy Path ---

    def test_lct_basic_calculation(self):
        # From CLAUDE.md example: 360 min × 250 staff / 5000 students = 18
        assert calculate_lct(360, 250, 5000) == pytest.approx(18.0)

    def test_lct_returns_float(self):
        result = calculate_lct(360, 250, 5000)
        assert isinstance(result, float)

    def test_lct_unrounded_precise_value(self):
        # The production function does NOT round (export does). 360×100/7777
        assert calculate_lct(360, 100, 7777) == pytest.approx(4.629034332, abs=1e-6)

    def test_lct_small_district(self):
        # 300 min × 20 staff / 200 students = 30
        assert calculate_lct(300, 20, 200) == pytest.approx(30.0)

    def test_lct_large_district(self):
        # 400 min × 5000 staff / 100000 students = 20
        assert calculate_lct(400, 5000, 100000) == pytest.approx(20.0)

    def test_lct_minimum_values(self):
        # 1 min × 1 staff / 1 student = 1
        assert calculate_lct(1, 1, 1) == pytest.approx(1.0)

    # --- Edge Cases (production guard behavior) ---

    def test_lct_zero_enrollment_returns_none(self):
        """Zero enrollment returns None (not a division error)."""
        assert calculate_lct(360, 250, 0) is None

    def test_lct_zero_staff_returns_none(self):
        """Zero staff returns None — LCT is undefined with no instructional staff."""
        assert calculate_lct(360, 0, 5000) is None

    def test_lct_negative_inputs_return_none(self):
        """Negative staff/enrollment are guarded and return None."""
        assert calculate_lct(360, -5, 5000) is None
        assert calculate_lct(360, 250, -100) is None

    def test_lct_zero_minutes_returns_zero(self):
        """Zero instructional minutes is a valid 0.0 LCT (staff/enrollment valid)."""
        assert calculate_lct(0, 250, 5000) == pytest.approx(0.0)

    def test_lct_handles_float_staff(self):
        """Staff counts are FTE floats from the DB (Decimal-safe)."""
        assert calculate_lct(360, 12.5, 250) == pytest.approx(18.0)

    # --- Validation ---

    def test_lct_result_in_reasonable_range(self):
        result = calculate_lct(360, 250, 5000)
        assert 0 <= result <= 1440  # max minutes in a day

    def test_lct_typical_values_produce_typical_results(self):
        # 360 × 200 / 4000 = 18 — typical districts land ~10-60 min
        result = calculate_lct(360, 200, 4000)
        assert 10 <= result <= 60


# --- Data-driven edge cases ---

@pytest.fixture
def edge_case_districts():
    """(minutes, staff, enrollment, expected) — None where LCT is undefined."""
    return [
        {'minutes': 360, 'staff': 250, 'enrollment': 0, 'expected': None},
        {'minutes': 0, 'staff': 250, 'enrollment': 5000, 'expected': 0.0},
        {'minutes': 360, 'staff': 0, 'enrollment': 5000, 'expected': None},
    ]


class TestLCTEdgeCases:
    def test_edge_cases(self, edge_case_districts):
        for case in edge_case_districts:
            result = calculate_lct(case['minutes'], case['staff'], case['enrollment'])
            if case['expected'] is None:
                assert result is None, f"Expected None for {case}"
            else:
                assert result == pytest.approx(case['expected']), f"Failed for {case}"


class TestLCTWriteIdempotency:
    """REQ-041: a full LCT recalculation clears prior results before writing.

    Regression guard for the 2026-06-06 bug where write_calculations_to_db
    appended without clearing, so re-runs failed on the unique constraint /
    id-sequence collision. The clear-before-write must stay in place.
    """

    def test_main_clears_before_writing(self):
        """main() must call clear_lct_calculations BEFORE write_calculations_to_db.

        Walks the AST for actual Call nodes (crossfam #472: the old raw-source .find() could be
        fooled by the call name appearing first in a comment/string, or miss a second real call)."""
        import ast
        import textwrap

        src = textwrap.dedent(inspect.getsource(calculate_lct_variants.main))
        calls = []  # (lineno, func_name) of every call in source order

        def _name(node):
            f = node.func
            return f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)

        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Call):
                calls.append((node.lineno, _name(node)))

        clear_lines = [ln for ln, n in calls if n == "clear_lct_calculations"]
        write_lines = [ln for ln, n in calls if n == "write_calculations_to_db"]
        assert clear_lines, "main() no longer calls clear_lct_calculations"
        assert write_lines, "main() no longer calls write_calculations_to_db"
        assert max(clear_lines) < min(write_lines), (
            "EVERY clear must precede EVERY write (idempotent re-run)"
        )

    def test_clear_all_deletes_every_calculation(self):
        """clear_lct_calculations(session) with no run_id deletes ALL rows."""
        session = MagicMock()
        session.query.return_value.delete.return_value = 123
        deleted = clear_lct_calculations(session)
        session.query.assert_called_once()
        session.query.return_value.delete.assert_called_once()
        assert deleted == 123

    def test_clear_by_run_id_filters(self):
        """clear_lct_calculations(session, run_id) deletes only that run's rows."""
        session = MagicMock()
        session.query.return_value.filter.return_value.delete.return_value = 7
        deleted = clear_lct_calculations(session, run_id="20260606T000000Z")
        session.query.return_value.filter.assert_called_once()
        assert deleted == 7

    def test_clear_by_year_filters(self):
        """clear_lct_calculations(session, year=...) deletes only that year's rows (issue #297)."""
        session = MagicMock()
        session.query.return_value.filter.return_value.delete.return_value = 11
        deleted = clear_lct_calculations(session, year="2024-25")
        session.query.return_value.filter.assert_called_once()
        assert deleted == 11

    def test_main_scopes_clear_to_target_year(self):
        """A --target-year run must NOT clear other years' rows (issue #297).

        main() must pass the year filter into clear_lct_calculations so a
        target-year recalculation preserves rows from other years; only
        blended mode may full-clear."""
        import ast
        import textwrap

        src = textwrap.dedent(inspect.getsource(calculate_lct_variants.main))
        clear_calls = [
            node for node in ast.walk(ast.parse(src))
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
            == "clear_lct_calculations"
        ]
        assert clear_calls, "main() no longer calls clear_lct_calculations"
        for call in clear_calls:
            assert any(kw.arg == "year" for kw in call.keywords), (
                "clear_lct_calculations in main() must pass year= so a "
                "target-year run doesn't destroy other years' calculations"
            )


class TestBasisAwareReader:
    """Issue #582: get_instructional_minutes must never label a stored
    statutory-fallback bell row as measured bell data."""

    def _session_with_rows(self, rows_by_call):
        session = MagicMock()
        q = session.query.return_value.filter.return_value.order_by.return_value
        q.all.side_effect = rows_by_call
        return session

    def _row(self, minutes, method='council_extraction', basis='gross_bell_to_bell',
             year='2024-25'):
        return SimpleNamespace(instructional_minutes=minutes, method=method,
                               minutes_basis=basis, year=year)

    def test_measured_row_wins(self):
        from infrastructure.scripts.analyze.calculate_lct_variants import get_instructional_minutes
        session = self._session_with_rows([[self._row(400)], [], []])
        minutes, source, year = get_instructional_minutes(session, '0612345', 'CA', 'high')
        assert (minutes, source, year) == (400, 'bell_schedule', '2024-25')

    def test_statutory_fallback_row_not_labeled_bell(self):
        from infrastructure.scripts.analyze.calculate_lct_variants import get_instructional_minutes
        stat = self._row(360, method='statutory_fallback', basis='statutory')
        session = self._session_with_rows([[stat], [], []])
        minutes, source, year = get_instructional_minutes(session, '0612345', 'CA', 'high')
        assert minutes == 360
        assert source == 'statutory_fallback'
        assert year is None  # statutory minutes carry no school-year identity (#24)

    def test_measured_preferred_over_stored_statutory(self):
        from infrastructure.scripts.analyze.calculate_lct_variants import get_instructional_minutes
        stat = self._row(360, method='statutory_fallback', basis='statutory')
        measured = self._row(410, year='2023-24')
        session = self._session_with_rows([[stat, measured], [], []])
        minutes, source, year = get_instructional_minutes(session, '0612345', 'CA', 'high')
        assert (minutes, source, year) == (410, 'bell_schedule', '2023-24')

    def test_fallback_level_measured_beats_requested_level_statutory(self):
        from infrastructure.scripts.analyze.calculate_lct_variants import get_instructional_minutes
        stat = self._row(360, method='statutory_fallback', basis='statutory')
        measured_middle = self._row(395, year='2024-25')
        session = self._session_with_rows([[stat], [measured_middle], []])
        minutes, source, year = get_instructional_minutes(session, '0612345', 'CA', 'high')
        assert (minutes, source, year) == (395, 'bell_schedule_middle', '2024-25')

    def test_statutory_basis_alone_also_excluded(self):
        """A row with minutes_basis='statutory' is statutory even if method
        says otherwise."""
        from infrastructure.scripts.analyze.calculate_lct_variants import get_instructional_minutes
        odd = self._row(360, method='human_provided', basis='statutory')
        session = self._session_with_rows([[odd], [], []])
        _, source, year = get_instructional_minutes(session, '0612345', 'CA', 'high')
        assert source == 'statutory_fallback'
        assert year is None


class TestComparisonGuardrails:
    """Issue #595: the SEA-vs-federal comparison must exclude entities outside
    the 0-360 validity band before aggregating (intermediate units with tiny
    enrollments dominated the unweighted state means)."""

    def test_out_of_band_entity_excluded(self):
        import pandas as pd
        from infrastructure.scripts.analyze.compare_sea_vs_federal_lct import compare_sources

        federal = pd.DataFrame([
            {'district_id': '1', 'teachers': 100.0, 'enrollment_k12': 1800, 'enrollment_k5': 900},
            # 50 teachers / 10 students -> implied LCT 1800: an intermediate-unit shape
            {'district_id': '2', 'teachers': 50.0, 'enrollment_k12': 10, 'enrollment_k5': 5},
        ])
        sea = pd.DataFrame([
            {'district_id': '1', 'teachers': 105.0, 'enrollment_k12': 1800},
            {'district_id': '2', 'teachers': 50.0, 'enrollment_k12': 10},
        ])
        result = compare_sources(federal, sea, 'PA')
        assert result['districts_compared'] == 1
        assert result['teachers_only_fed_mean'] == pytest.approx(360 * 100 / 1800)
