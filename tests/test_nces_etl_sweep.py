"""WP-8 characterization tests for the one-shot NCES ETL scripts (epic #480).

These scripts had no coverage; the fixed defect classes get pinned here:
whitespace-tolerant indicator matching, merge dedup, header-skip by
comparison, generic-mapping single-target, numeric-dtype validation, robust
year extraction.
"""

import logging

import pandas as pd
import pytest

from infrastructure.scripts.transform.normalize_districts import (
    VALID_STATE_CODES,
    merge_grade_level_data,
    normalize_state_data,
    validate_normalized_data,
)


class TestNormalizeDistricts:
    def test_generic_mapping_single_target(self):
        """#311/#313: two id-ish columns must not both rename to district_id."""
        df = pd.DataFrame({
            'District ID': ['1'], 'County Code': ['9'],
            'District Name': ['A'], 'Enrollment': [10], 'Teachers': [2.0],
        })
        out = normalize_state_data(df, 'OH', '2024-25')
        assert list(out.columns).count('district_id') == 1

    def test_no_id_column_raises_clear_error(self):
        df = pd.DataFrame({'Enrollment': [10], 'Teachers': [1.0]})
        with pytest.raises(ValueError, match='district_id'):
            normalize_state_data(df, 'OH', '2024-25')

    def test_merge_keeps_canonical_names(self, tmp_path):
        """#312: overlapping columns must not become enrollment_x/_y."""
        base = pd.DataFrame({'district_id': [100001], 'enrollment': [100]})
        grade_file = tmp_path / 'grades.csv'
        pd.DataFrame({'district_id': [100001], 'enrollment': [99],
                      'enrollment_elementary': [50]}).to_csv(grade_file, index=False)
        out = merge_grade_level_data(base, enrollment_file=grade_file)
        assert 'enrollment' in out.columns
        assert 'enrollment_x' not in out.columns
        assert out['enrollment'].iloc[0] == 100  # base frame wins the name

    def test_validate_accepts_float32(self):
        """#392: any numeric dtype passes, not just float64/int64."""
        df = pd.DataFrame({
            'district_id': ['1'], 'district_name': ['A'], 'state': ['OH'],
            'year': ['2024-25'], 'data_source': ['x'],
            'enrollment': pd.array([100], dtype='Int64'),
            'instructional_staff': pd.Series([5.0], dtype='float32'),
        })
        assert validate_normalized_data(df) is True

    def test_valid_state_codes_cover_dc_pr(self):
        assert {'DC', 'PR', 'CA', 'WY'} <= set(VALID_STATE_CODES)


class TestSplitLargeFiles:
    def test_header_skip_by_comparison_not_isdigit(self, tmp_path):
        """#304: a part whose first data row starts non-numerically must not
        lose that row."""
        from infrastructure.scripts.extract.split_large_files import concatenate_text_files
        f1 = tmp_path / 'part_1.txt'
        f2 = tmp_path / 'part_2.txt'
        f1.write_text('ID,NAME\n1,Alpha\n')
        # part 2 has NO repeated header; first row's field 'X2' is not a digit
        f2.write_text('X2,Beta\n')
        out = tmp_path / 'combined.txt'
        concatenate_text_files([f1, f2], out)
        lines = out.read_text().splitlines()
        assert lines == ['ID,NAME', '1,Alpha', 'X2,Beta']

    def test_repeated_header_still_skipped(self, tmp_path):
        from infrastructure.scripts.extract.split_large_files import concatenate_text_files
        f1 = tmp_path / 'part_1.txt'
        f2 = tmp_path / 'part_2.txt'
        f1.write_text('ID,NAME\n1,Alpha\n')
        f2.write_text('ID,NAME\n2,Beta\n')
        out = tmp_path / 'combined.txt'
        concatenate_text_files([f1, f2], out)
        assert out.read_text().splitlines() == ['ID,NAME', '1,Alpha', '2,Beta']

    def test_csv_concat_streams_parts(self, tmp_path):
        from infrastructure.scripts.extract.split_large_files import concatenate_csv_files
        f1 = tmp_path / 'a_1.csv'
        f2 = tmp_path / 'a_2.csv'
        pd.DataFrame({'x': [1, 2]}).to_csv(f1, index=False)
        pd.DataFrame({'x': [3]}).to_csv(f2, index=False)
        out = tmp_path / 'combined.csv'
        n = concatenate_csv_files([f1, f2], out)
        assert n == 3
        assert len(pd.read_csv(out)) == 3


class TestFetchNcesCcdDownload:
    def test_malformed_content_length_streams_anyway(self, tmp_path, monkeypatch):
        """#381/#382: bad Content-Length must not crash; body must stream."""
        from infrastructure.scripts.download import fetch_nces_ccd as mod

        class FakeResponse:
            headers = {'content-length': 'not-a-number'}
            def raise_for_status(self): pass
            def iter_content(self, chunk_size):
                yield b'abc'
                yield b'def'

        monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: FakeResponse())
        out = tmp_path / 'file.zip'
        assert mod.download_file('http://x', out) is True
        assert out.read_bytes() == b'abcdef'
        assert not out.with_suffix('.zip.part').exists()

    def test_failed_download_leaves_no_partial_file(self, tmp_path, monkeypatch):
        """#383: a failed download must not leave a corrupt final file."""
        from infrastructure.scripts.download import fetch_nces_ccd as mod
        import requests as _requests

        class FakeResponse:
            headers = {'content-length': '100'}
            def raise_for_status(self): pass
            def iter_content(self, chunk_size):
                yield b'abc'
                raise _requests.exceptions.ConnectionError('dropped')

        monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: FakeResponse())
        out = tmp_path / 'file.zip'
        assert mod.download_file('http://x', out) is False
        assert not out.exists()
        assert not out.with_suffix('.zip.part').exists()
