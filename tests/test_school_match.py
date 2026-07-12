"""Tests for the shared school-name identity key (common/school_match.norm_school, REQ-117).

#236: district-type suffixes (ISD/USD/District/Schools/…) must be stripped so a school and its
district-suffixed name variant collapse to ONE key — else the same physical school is double-counted
in one band's modal aggregation. Deliberately CONSERVATIVE (PR #247 review hardening): qualifiers
strip only in a TRAILING run ending in a hard district marker — 'unified'/'consolidated'/
'independent' inside a proper name are preserved ("Meridian Consolidated School" is a different
school than "Meridian School"), and county/community/public are never stripped bare.
"""
from infrastructure.acquisition.common.school_match import norm_school, norm_school_strict


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

    def test_level_abbreviations_match_full_words(self):
        # PR #247 review: district sites use ES/MS/HS interchangeably with the full words — the same
        # school must not become two keys (a false-positive #237 contamination flag).
        assert norm_school("Lincoln HS") == norm_school("Lincoln High School")
        assert norm_school("Adams MS") == norm_school("Adams Middle School")
        assert norm_school("Kennedy ES") == norm_school("Kennedy Elementary School")

    def test_accented_names_transliterate(self):
        # PR #247 review: deleting non-ASCII chars mangled the word ('José' -> 'jos'); NFKD keeps it.
        assert norm_school("José Martí Elementary") == norm_school("Jose Marti Elementary")

    def test_hyphenated_suffix_matches_spaced(self):
        # PR #247 review: deleting the hyphen fused 'lincolnunified', hiding the suffix from the
        # word-boundary strip — hyphens must word-split.
        assert norm_school("Lincoln-Unified School District") == norm_school("Lincoln Unified School District")


class TestDistrictSuffixMerge:
    """#236: name variants that differ only by a marker-terminated district qualifier collapse."""

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
                        "Lincoln Unified School District", "Lincoln Consolidated District",
                        "Lincoln Independent School District"):
            assert norm_school(variant) == base, f"{variant!r} should strip to {base!r}"

    def test_qualifier_run_inside_marker_tail_strips(self):
        assert norm_school("Franklin Community School District") == norm_school("Franklin")
        # a generic word's removal can EXPOSE a marker tail — must still reach the fixed point
        assert norm_school("Lincoln ISD Academy") == norm_school("Lincoln")


class TestConservativeNonMerge:
    """Words that can distinguish two genuinely different schools must NOT be stripped bare —
    over-merge silently combines two schools' facts before council consensus (PR #247 review)."""

    def test_county_not_stripped(self):
        # Franklin County High vs Franklin High are DIFFERENT schools — keys must differ
        assert norm_school("Franklin County High") != norm_school("Franklin High")

    def test_community_not_stripped(self):
        assert norm_school("Northwood Community") != norm_school("Northwood")

    def test_public_not_stripped(self):
        assert norm_school("Riverside Public") != norm_school("Riverside")

    def test_bare_qualifiers_preserved_without_a_marker(self):
        # the PR #247 over-merge finding: 'consolidated'/'independent'/'unified' are ordinary words
        # in real proper names when no district marker follows them.
        assert norm_school("Meridian Consolidated School") != norm_school("Meridian School")
        assert norm_school("Franklin Independent School") != norm_school("Franklin School")
        assert norm_school("Lincoln Unified") != norm_school("Lincoln")


class TestIdempotence:
    """Stage 7 PERSISTS this key (school_fact.school); merge_fact_runs and the #237 detector
    re-normalize persisted keys through the current function at read time to self-heal stopword-list
    drift — that only works if norm_school(norm_school(x)) == norm_school(x)."""

    def test_fixed_point_on_representative_names(self):
        for name in ("Lincoln Unified School District", "Meridian Consolidated School",
                     "José Martí Elementary", "O'Brien Elementary", "The School District",
                     "Lincoln ISD Academy", "Union Hill ISD", "ISD"):
            key = norm_school(name)
            assert norm_school(key) == key, f"not idempotent: {name!r} -> {key!r} -> {norm_school(key)!r}"

    def test_pre_236_persisted_key_heals_to_current(self):
        # a key persisted before #236 ('lincoln unified district' — only level words stripped then)
        # must re-normalize to the CURRENT key for the same school, or cross-run merge fragments.
        assert norm_school("lincoln unified district") == norm_school("Lincoln Unified School District")


class TestEmptyKeyGuard:
    """#236: a name that is ALL type/qualifier words must not strip to '' (which would merge every
    all-type name into one bucket) — fall back to the punctuation-normalized form. The STRICT form
    returns the falsy '' instead, so junk roster entries can be FILTERED (PR #247 review: the
    fallback let a scraped 'School District' header through as a matchable roster key)."""

    def test_all_type_words_falls_back_not_empty(self):
        assert norm_school("The School District") != ""

    def test_distinct_all_type_names_stay_distinct(self):
        # both are pathological all-stopword names; the guard keeps them apart
        assert norm_school("ISD") != norm_school("USD")

    def test_strict_form_is_falsy_for_junk(self):
        assert norm_school_strict("School District") == ""
        assert norm_school_strict("The School District") == ""
        assert norm_school_strict("Union Hill ISD") == norm_school("Union Hill ISD")  # same when non-junk
