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
        assert GB.band_grade_tokens("elementary") == ("KG", "01", "02", "03", "04", "05")
        assert GB.band_grade_tokens("middle") == ("06", "07", "08")
        assert GB.band_grade_tokens("high") == ("09", "10", "11", "12")
        assert GB.band_grade_tokens("nope") == ()

    def test_the_shared_grade_list_is_immutable(self):
        """#1059: one object backs Stage 9, the LCT minutes and the importers; a tuple cannot be
        appended to, sorted in place or have a grade removed by any of them."""
        assert isinstance(GB.K12_GRADE_TOKENS, tuple)
        assert isinstance(GB.band_grade_tokens("middle"), tuple)

    def test_pk_is_elementary_and_13_is_high_but_neither_is_an_lct_grade(self):
        assert GB.canon_band("PK") == "elementary"
        assert GB.canon_band("13") == "high"
        assert "PK" not in GB.K12_GRADE_TOKENS and "13" not in GB.K12_GRADE_TOKENS
        assert GB.canon_band("UG") is None
        assert GB.canon_band("K") is None          # a lookup, not a validator: norm() first

    def test_every_lct_grade_has_exactly_one_owner(self):
        for g in GB.K12_GRADE_TOKENS:
            assert [b for b, rng in GB.BANDS.items() if GB.GRADE_ORD[g] in rng] == [GB.canon_band(g)]

    def test_grade_int_is_the_pipelines_one_convention(self):
        """#1059: PK and KG are both 0 (pre-grade-1), as school_sampling._grade_num has always said."""
        from infrastructure.acquisition.common import school_sampling as SS
        assert [GB.grade_int(g) for g in ("PK", "KG", "01", "12", "13")] == [0, 0, 1, 12, 13]
        assert GB.grade_int("UG") is None
        for g, idx in GB.GRADE_ORD.items():
            assert SS._grade_num(idx) == GB.grade_int(g), g

    def test_enrollment_column_refuses_anything_outside_k12(self):
        """#1059: a fabricated column name read through getattr(..., 0) is a silent zero (REQ-165)."""
        assert GB.enrollment_column("KG") == "enrollment_kindergarten"
        assert GB.enrollment_column("07") == "enrollment_grade_7"
        for bad in ("PK", "13", "UG", "K", "7", ""):
            with pytest.raises(ValueError):
                GB.enrollment_column(bad)

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

    def test_the_model_method_derives_the_level_sums_from_the_home(self):
        """#1060: EnrollmentByGrade.calculate_level_enrollments is the ONE writer of
        enrollment_elementary/_secondary (REQ-010), and it sums the home's bands."""
        from infrastructure.database.models import EnrollmentByGrade
        e = EnrollmentByGrade(district_id="d", source_year="2024-25")
        for g in GB.K12_GRADE_TOKENS:
            setattr(e, GB.enrollment_column(g), 1000 + GB.grade_int(g))   # distinct per grade
        e.enrollment_prek, e.enrollment_grade_13, e.enrollment_ungraded = 7, 9, 11   # must not count
        e.calculate_level_enrollments()
        assert e.enrollment_elementary == sum(1000 + GB.grade_int(g) for g in GB.band_grade_tokens("elementary"))
        assert e.enrollment_secondary == sum(1000 + GB.grade_int(g)
                                             for g in GB.band_grade_tokens("middle") + GB.band_grade_tokens("high"))

    def test_the_lea_enrollment_importer_calls_the_model_method(self):
        """#1060: the importer used to carry its own K-5 / 6-12 column lists (REQ-010 said the method
        'is called after import'; it was not). Pin that it now is, by source: the call is inside
        load_enrollment_data's row loop."""
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1]
               / "infrastructure/database/migrations/import_staff_and_enrollment.py").read_text()
        assert "enrollment.calculate_level_enrollments()" in src
        assert "elem_grades" not in src and "sec_grades" not in src
