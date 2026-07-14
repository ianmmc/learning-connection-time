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
