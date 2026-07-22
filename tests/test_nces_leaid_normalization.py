"""NCES CCD importer LEAID normalization + coverage guardrail (issue #611 regression).

The 2024-25 staff/enrollment ingest silently dropped ~3,125 districts (~17.5% of the corpus, every
FIPS<10 state) because `import_staff_and_enrollment` normalized LEAIDs with `str(int(leaid))`, which
strips the leading zero ('0100810' -> '100810'). After migration 015 canonicalized the `districts`
table to 7-digit leading-zero ids, the stripped ids failed the `.isin(existing_districts)` match and
were filtered out with no error.

These tests pin the REAL importer functions (not a test-local reimplementation) so the regression
can't return: the canonical form must PAD to 7 digits, never strip, and a low post-filter match rate
must abort the import loudly.
"""
import pytest

from infrastructure.database.migrations.import_staff_and_enrollment import (
    _assert_match_coverage,
    _canonical_leaid,
)


class TestCanonicalLeaid:
    def test_leading_zero_is_preserved_not_stripped(self):
        # THE #611 regression: str(int('0100810')) == '100810' silently unmatched every FIPS<10 state.
        assert _canonical_leaid("0100810") == "0100810"
        assert _canonical_leaid("0100810") != "100810"

    def test_pads_short_id_to_seven_digits(self):
        assert _canonical_leaid("100005") == "0100005"

    def test_already_seven_is_unchanged(self):
        assert _canonical_leaid("3901234") == "3901234"

    def test_all_leading_zero_fips_states_survive(self):
        # AL/AK/AZ/AR/CA/CO/CT — the populations #611 dropped. Each must round-trip to its 7-char id.
        for lid in ("0100810", "0200180", "0400123", "0500012", "0602095", "0800030", "0900001"):
            assert _canonical_leaid(lid) == lid

    def test_none_and_nan_pass_through(self):
        import pandas as pd
        assert _canonical_leaid(None) is None
        assert pd.isna(_canonical_leaid(float("nan")))   # NaN in -> NaN out, not the string "nan"

    def test_whitespace_is_stripped_then_padded(self):
        assert _canonical_leaid("  100005 ") == "0100005"

    def test_integer_input_is_padded_not_reformatted(self):
        # A LEAID that arrives as an int (100810) must still pad to the 7-char canonical form.
        assert _canonical_leaid(100810) == "0100810"


class TestMatchCoverageGuardrail:
    def test_passes_at_full_coverage(self):
        # 17,751 of 17,842 matched (99.5%) — the corrected 2024-25 ingest. No raise.
        _assert_match_coverage(n_file_districts=18548, n_matched=17751, n_existing=17842,
                               label="enrollment import")

    def test_raises_on_the_611_partial_import(self):
        # 14,717 of 17,842 (82.5%) — the buggy 2024-25 ingest. Must abort, not silently commit.
        with pytest.raises(SystemExit, match="issue #611"):
            _assert_match_coverage(n_file_districts=18548, n_matched=14717, n_existing=17842,
                                   label="enrollment import")

    def test_denominator_is_the_smaller_of_file_or_table(self):
        # Small partial file (say a single-state test extract) must not trip the floor: denom follows
        # the file, so matching all 500 of 500 file districts passes even against a 17k table.
        _assert_match_coverage(n_file_districts=500, n_matched=500, n_existing=17842, label="staff import")

    def test_empty_denominator_never_raises(self):
        _assert_match_coverage(n_file_districts=0, n_matched=0, n_existing=17842, label="staff import")
