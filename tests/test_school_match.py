"""Tests for the shared school-name identity key (common/school_match.norm_school, REQ-117).

#236: district-type suffixes (ISD/USD/District/Schools/…) must be stripped so a school and its
district-suffixed name variant collapse to ONE key — else the same physical school is double-counted
in one band's modal aggregation. Deliberately CONSERVATIVE: county/community/public are NOT stripped
(they can be part of a school's distinguishing name, not just its type — would over-merge).
"""
from infrastructure.acquisition.common.school_match import norm_school


class TestNormSchoolBasics:
    def test_empty_and_none(self):
        assert norm_school("") == ""
        assert norm_school(None) == ""

    def test_lowercase_and_punctuation_stripped(self):
        # the REQ-117 canonical example: 'Brick Mill ES/ECC' -> 'brick mill esecc'
        assert norm_school("Brick Mill ES/ECC") == norm_school("brick mill esecc")

    def test_level_words_stripped(self):
        assert norm_school("Marion High School") == "marion"
        assert norm_school("Marion Elementary") == "marion"


class TestDistrictSuffixMerge:
    """#236: name variants that differ only by a district-type qualifier collapse to one key."""

    def test_union_hill_isd_variant(self):
        # the exact #236 case (Union Hill ISD, high band): 'union hill' == 'union hill isd'
        assert norm_school("union hill") == norm_school("union hill isd")

    def test_elmbrook_district_vs_schools(self):
        # the SECOND real instance found in Stage 7 data (Elmbrook, middle band)
        assert norm_school("Elmbrook District") == norm_school("Elmbrook Schools")

    def test_common_district_type_abbreviations_stripped(self):
        base = norm_school("Lincoln")
        for variant in ("Lincoln USD", "Lincoln CISD", "Lincoln CUSD", "Lincoln CCSD",
                        "Lincoln UFSD", "Lincoln CSD", "Lincoln PSD", "Lincoln SD",
                        "Lincoln Unified", "Lincoln Consolidated", "Lincoln Independent"):
            assert norm_school(variant) == base, f"{variant!r} should strip to {base!r}"


class TestConservativeNonMerge:
    """Gemini-vetted: county/community/public can distinguish two genuinely different schools —
    they must NOT be stripped (over-merge risk)."""

    def test_county_not_stripped(self):
        # Franklin County High vs Franklin High are DIFFERENT schools — keys must differ
        assert norm_school("Franklin County High") != norm_school("Franklin High")

    def test_community_not_stripped(self):
        assert norm_school("Northwood Community") != norm_school("Northwood")

    def test_public_not_stripped(self):
        assert norm_school("Riverside Public") != norm_school("Riverside")


class TestEmptyKeyGuard:
    """#236: a name that is ALL type/qualifier words must not strip to '' (which would merge every
    all-type name into one bucket) — fall back to the punctuation-normalized form."""

    def test_all_type_words_falls_back_not_empty(self):
        assert norm_school("The School District") != ""

    def test_distinct_all_type_names_stay_distinct(self):
        # both are pathological all-stopword names; the guard keeps them apart
        assert norm_school("ISD") != norm_school("USD")
