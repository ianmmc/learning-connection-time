"""#1035 (#1022 T1): the grade -> band map and the school -> band classifier have ONE home,
`infrastructure/utilities/grade_bands.py`. The values are pinned here, and every former spelling is
pinned by IDENTITY with the home, not by agreement between copies. The input construction is
pinned too (#846): the call sites derive their lists from the home's functions. The one-home
fitness row (tests/test_one_home_fitness.py) keeps literal re-spellings from coming back.
"""
import pytest

from infrastructure.utilities import grade_bands as GB


class TestMap:

    def test_bands_by_token(self):
        assert GB.band_grade_tokens("elementary") == ["KG", "01", "02", "03", "04", "05"]
        assert GB.band_grade_tokens("middle") == ["06", "07", "08"]
        assert GB.band_grade_tokens("high") == ["09", "10", "11", "12"]
        assert GB.band_grade_tokens("nope") == []

    def test_pk_is_elementary_and_13_is_high_but_neither_is_an_lct_grade(self):
        assert GB.canon_band("PK") == "elementary"
        assert GB.canon_band("13") == "high"
        assert "PK" not in GB.K12_GRADE_TOKENS and "13" not in GB.K12_GRADE_TOKENS
        assert GB.canon_band("UG") is None

    def test_every_lct_grade_has_exactly_one_owner(self):
        for g in GB.K12_GRADE_TOKENS:
            assert [b for b, rng in GB.BANDS.items() if GB.GRADE_ORD[g] in rng] == [GB.canon_band(g)]

    def test_grade_int_and_enrollment_column(self):
        assert [GB.grade_int(g) for g in ("PK", "KG", "01", "12", "13")] == [-1, 0, 1, 12, 13]
        assert GB.grade_int("UG") is None
        assert GB.enrollment_column("KG") == "enrollment_kindergarten"
        assert GB.enrollment_column("07") == "enrollment_grade_7"

    def test_norm(self):
        assert GB.norm(" kindergarten ") == "KG" and GB.norm("PreKindergarten") == "PK"
        assert GB.norm(None) == ""


class TestSchoolClassifier:
    """The rule the school-file band scopes band schools by (#1022 D1/D2)."""

    @pytest.mark.parametrize("level,gslo,gshi,expected", [
        ("Elementary", "KG", "08", {"elementary"}),           # a K-8 elementary is elementary only
        ("Elementary", "PK", "06", {"elementary"}),
        ("Middle", "04", "06", {"elementary"}),               # #498 carve-out (Liberati)
        ("Middle", "05", "06", {"middle"}),                   # NOT overridden (ruled 2026-07-15)
        ("Middle", "06", "08", {"middle"}),
        ("High", "09", "13", {"high"}),
        ("Other", "KG", "12", {"elementary", "middle", "high"}),   # combined: span overlap
        ("Secondary", "07", "12", {"middle", "high"}),
        ("Not reported", "M", "M", set()),                    # ungraded / unknown
    ])
    def test_primary_bands_for(self, level, gslo, gshi, expected):
        assert GB.primary_bands_for(level, gslo, gshi) == expected

    def test_bands_for_is_the_fixed_overlap(self):
        assert GB.bands_for("KG", "06") == {"elementary", "middle"}
        assert GB.bands_for("09", "13") == {"high"}
        assert GB.bands_for("08", "06") == set()


class TestCallSitesUseTheHome:

    def test_school_sampling_re_exports_the_same_objects(self):
        from infrastructure.acquisition.common import school_sampling as SS
        for name in ("BANDS", "GRADE_ORD", "LEVEL_BAND", "norm", "bands_for", "effective_level_band",
                     "is_intermediate_span", "primary_bands_for", "INTERMEDIATE_MAX_START",
                     "INTERMEDIATE_MAX_TOP"):
            assert getattr(SS, name) is getattr(GB, name), name
        assert SS._IM_START_ORD == GB.INTERMEDIATE_START_ORD
        assert SS._IM_TOP_ORD == GB.INTERMEDIATE_TOP_ORD

    def test_stage9_per_grade(self):
        from infrastructure.acquisition.stage9_incorporate import per_grade as PG
        assert PG.GRADE_TOKENS is GB.K12_GRADE_TOKENS
        assert PG._canon_band is GB.canon_band
        for band in ("elementary", "middle", "high"):
            assert PG._canonical_grades(band) == set(GB.band_grade_tokens(band))

    def test_lct_per_grade_minutes(self):
        from infrastructure.scripts.analyze import per_grade_lct as PGL
        assert PGL.GRADES is GB.K12_GRADE_TOKENS
        assert PGL._CANON_BAND == {g: GB.canon_band(g) for g in GB.K12_GRADE_TOKENS}

    def test_grade_level_enrollment_extract(self):
        from infrastructure.scripts.extract import extract_grade_level_enrollment as E
        assert E.ELEMENTARY_GRADES == [0, 1, 2, 3, 4, 5]
        assert E.MIDDLE_GRADES == [6, 7, 8]
        assert E.HIGH_GRADES == [9, 10, 11, 12]

    def test_lea_enrollment_importer_derives_its_lists_from_the_home(self):
        """The importer's lists are locals inside load_enrollment_data, so pin by source that it
        calls the home rather than spelling the columns (the fitness row catches a re-spelling)."""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1]
               / "infrastructure/database/migrations/import_staff_and_enrollment.py").read_text()
        assert 'elem_grades = [enrollment_column(g) for g in band_grade_tokens("elementary")]' in src
        assert ('sec_grades = [enrollment_column(g) for g in band_grade_tokens("middle") + '
                'band_grade_tokens("high")]') in src
