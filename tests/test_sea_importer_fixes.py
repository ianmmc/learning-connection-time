"""
Tests importing the REAL state importer modules (issues #17, #22, #23).

The pre-existing integration suites exercised mocks defined inside the test files,
which is how the iloc off-by-one (#17), the `or 0` suppression coercion (#22), and
the leading-zero crosswalk misses (#23) all survived. These tests hit the shipped
modules directly.
"""

import pandas as pd
import pytest

from infrastructure.database.migrations import import_texas_tapr_data as tapr
from infrastructure.database.migrations.import_massachusetts_data import (
    ENROLLMENT_DATA_YEAR,
    TEACHER_DATA_YEAR,
    format_ma_district_code,
)
from infrastructure.database.migrations.import_michigan_data import (
    format_mi_district_code,
)
from infrastructure.database.migrations.import_illinois_data import (
    rcdts_to_state_id,
)


# =============================================================================
# Texas TAPR — name-based column access (issue #17)
# =============================================================================

def _tapr_frame(prefix: str, suffixes: dict) -> pd.DataFrame:
    """A one-row frame with real TAPR-style verbose headers."""
    cols = {f'{prefix}{suffix}': ['1.0'] for suffix in suffixes.values()}
    return pd.DataFrame(cols)


class TestTaprColumnResolution:

    def test_find_column_unique_suffix(self):
        cols = ['District 2025 Staff: Teacher Total Full Time Equiv Count',
                'District 2025 Staff: Teacher Total Full Time Equiv Percent']
        assert tapr.find_column(
            cols, 'Staff: Teacher Total Full Time Equiv Count'
        ) == cols[0]

    def test_find_column_rejects_ambiguity_and_absence(self):
        with pytest.raises(KeyError):
            tapr.find_column(['A Count', 'B Count'], 'Count')
        with pytest.raises(KeyError):
            tapr.find_column(['A Count'], 'Missing Count')

    def test_total_and_grade12_are_distinct_columns(self):
        """The original bug: iloc[27] fed BOTH total enrollment and grade 12."""
        df = _tapr_frame('District 2025 ', tapr.STUDENT_COLUMNS)
        cols = tapr.resolve_columns(df, tapr.STUDENT_COLUMNS)
        assert cols['total'] != cols['g12']
        assert cols['total'].endswith('All Students Count')
        assert cols['g12'].endswith('12 Count')
        # All 18 fields resolve to 18 DIFFERENT columns
        assert len(set(cols.values())) == len(tapr.STUDENT_COLUMNS)

    def test_staff_fields_resolve_distinctly(self):
        df = _tapr_frame('District 2025 ', tapr.STAFF_COLUMNS)
        cols = tapr.resolve_columns(df, tapr.STAFF_COLUMNS)
        assert len(set(cols.values())) == len(tapr.STAFF_COLUMNS)
        assert cols['teacher_special_ed'].endswith(
            'Teacher Special Education Full Time Equiv Count')

    def test_year_prefix_agnostic(self):
        """Suffix matching survives the annual header year bump."""
        df = _tapr_frame('District 2026 ', tapr.STAFF_COLUMNS)
        cols = tapr.resolve_columns(df, tapr.STAFF_COLUMNS)
        assert cols['teacher_total'].startswith('District 2026 ')

    @pytest.mark.integration
    def test_real_tapr_files_resolve(self):
        """Against the actual 2024-25 TAPR district CSVs when present."""
        if not (tapr.STAFF_FILE.exists() and tapr.STUDENT_FILE.exists()):
            pytest.skip('raw TAPR files not present')
        staff = pd.read_csv(tapr.STAFF_FILE, dtype=str)
        staff.columns = [c.strip('"') for c in staff.columns]
        stud = pd.read_csv(tapr.STUDENT_FILE, dtype=str)
        stud.columns = [c.strip('"') for c in stud.columns]
        sc = tapr.resolve_columns(staff, tapr.STAFF_COLUMNS)
        tc = tapr.resolve_columns(stud, tapr.STUDENT_COLUMNS)
        assert len(set(sc.values())) == len(tapr.STAFF_COLUMNS)
        assert len(set(tc.values())) == len(tapr.STUDENT_COLUMNS)
        # Houston ISD sanity: total enrollment far exceeds grade 12
        h = stud[stud[tapr.DISTRICT_NO_COL] == '101912'].iloc[0]
        assert int(h[tc['total']]) > 10 * int(h[tc['g12']])

    def test_no_positional_iloc_access_remains(self):
        """No executable .iloc access in the importer (docstrings excepted)."""
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(tapr))
        offenders = [
            node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == 'iloc'
        ]
        assert offenders == [], f'positional .iloc access at lines {offenders}'


# =============================================================================
# Massachusetts — converter + actual-year labels (issue #23)
# =============================================================================

class TestMassachusettsImporter:

    def test_converter_documented_example(self):
        assert format_ma_district_code('0035') == '0035'  # old code returned '0000'
        assert format_ma_district_code(350000) == '0035'
        assert format_ma_district_code('00350000') == '0035'

    def test_years_label_actual_data_years(self):
        # Teacher FTE comes from the 2024-25 DESE export; enrollment from SY 2026
        assert TEACHER_DATA_YEAR == '2024-25'
        assert ENROLLMENT_DATA_YEAR == '2025-26'


# =============================================================================
# Michigan — zero-padded codes, explicit None for bad input (issue #23)
# =============================================================================

class TestMichiganImporter:

    def test_small_codes_zero_padded(self):
        assert format_mi_district_code(4010) == '04010'
        assert format_mi_district_code(4010.0) == '04010'
        assert format_mi_district_code('04010') == '04010'
        assert format_mi_district_code(82015) == '82015'

    def test_missing_or_invalid_returns_none_not_none_string(self):
        assert format_mi_district_code(None) is None
        assert format_mi_district_code(float('nan')) is None
        assert format_mi_district_code('N/A') is None


# =============================================================================
# Illinois — leading zeros through the importer's own wrapper (issue #23)
# =============================================================================

class TestIllinoisImporter:

    def test_rcdts_leading_zero_regions(self):
        assert rcdts_to_state_id(10162990250000) == '01-016-2990-25'
        assert rcdts_to_state_id('150162990250000') == '15-016-2990-25'
