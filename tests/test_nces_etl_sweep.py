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

    def test_nces_ccd_missing_leaid_raises_clear_error(self):
        """Max-effort review: the state path got a missing-district_id guard
        but the NCES path didn't — added for consistency (fast, diagnosable
        failure instead of a later opaque validate_normalized_data error)."""
        from infrastructure.scripts.transform.normalize_districts import normalize_nces_ccd
        df = pd.DataFrame({'LEA_NAME': ['A'], 'MEMBER': [10]})
        with pytest.raises(ValueError, match='district_id'):
            normalize_nces_ccd(df, '2024-25')

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

    def test_csv_concat_aligns_shuffled_column_order(self, tmp_path):
        """Max-effort review: appending by raw file position (no header,
        mode='a') silently transposed values when a later part's columns
        were the same NAMES but a different ORDER — a realistic risk for
        split government CSV exports. Must align by name, not position."""
        from infrastructure.scripts.extract.split_large_files import concatenate_csv_files
        f1 = tmp_path / 'a_1.csv'
        f2 = tmp_path / 'a_2.csv'
        pd.DataFrame({'x': [1, 2], 'y': ['a', 'b']}).to_csv(f1, index=False)
        pd.DataFrame({'y': ['c'], 'x': [3]}).to_csv(f2, index=False)  # order swapped
        out = tmp_path / 'combined.csv'
        concatenate_csv_files([f1, f2], out)
        result = pd.read_csv(out)
        row3 = result.iloc[2]
        assert row3['x'] == 3
        assert row3['y'] == 'c'

    def test_csv_concat_rejects_mismatched_schema(self, tmp_path):
        from infrastructure.scripts.extract.split_large_files import concatenate_csv_files
        f1 = tmp_path / 'a_1.csv'
        f2 = tmp_path / 'a_2.csv'
        pd.DataFrame({'x': [1], 'y': [2]}).to_csv(f1, index=False)
        pd.DataFrame({'x': [1], 'z': [2]}).to_csv(f2, index=False)  # different column
        out = tmp_path / 'combined.csv'
        with pytest.raises(ValueError, match='columns'):
            concatenate_csv_files([f1, f2], out)


class TestExtractGradeLevelStaffingYearRegex:
    def test_year_extracted_from_real_ccd_filename(self):
        """Max-effort review: the '#389 fix' regex r'(\\d{4}[-_]\\d{2})' does
        NOT match this project's own documented canonical filename
        (ccd_lea_059_2324_l_1a_073124.csv — year is one 4-digit token, not
        NNNN-NN), so every real run fell through to 'unknown', silently
        clobbering prior years' output on repeat runs. Must match the same
        pattern the sibling enrollment extractor already uses correctly."""
        import re
        # exact pattern currently in extract_grade_level_staffing.py's main()
        pattern = r'_(\d{4})_'
        m = re.search(pattern, 'ccd_lea_059_2324_l_1a_073124.csv')
        assert m is not None
        assert m.group(1) == '2324'


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

    def test_non_network_write_failure_still_cleans_up_part_file(self, tmp_path, monkeypatch):
        """Max-effort review: the old except clause only caught
        requests.exceptions.RequestException, so an OSError from f.write()
        (disk full, permission denied) skipped cleanup and left the .part
        file behind. Cleanup must run on every exit path (finally)."""
        from infrastructure.scripts.download import fetch_nces_ccd as mod

        class FakeResponse:
            headers = {'content-length': '100'}
            def raise_for_status(self): pass
            def iter_content(self, chunk_size):
                raise OSError("No space left on device")

        monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: FakeResponse())
        out = tmp_path / 'file.zip'
        with pytest.raises(OSError):
            mod.download_file('http://x', out)
        assert not out.with_suffix('.zip.part').exists()

    def test_successful_download_does_not_delete_final_file(self, tmp_path, monkeypatch):
        """The finally-block cleanup must be a no-op once tmp_path has
        already been renamed to output_path on success."""
        from infrastructure.scripts.download import fetch_nces_ccd as mod

        class FakeResponse:
            headers = {'content-length': '3'}
            def raise_for_status(self): pass
            def iter_content(self, chunk_size):
                yield b'abc'

        monkeypatch.setattr(mod.requests, 'get', lambda *a, **k: FakeResponse())
        out = tmp_path / 'file.zip'
        assert mod.download_file('http://x', out) is True
        assert out.read_bytes() == b'abc'
