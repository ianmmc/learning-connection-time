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


class TestNcesAbbreviationTails:
    """#499 PR-A (REQ-144): CCD SCH_NAME abbreviations strip as TRAILING runs only, so a roster
    slot and its extracted fact share a key — while the Spanish article survives mid-name."""

    def test_nces_abbreviated_roster_names_match_extracted_names(self):
        from infrastructure.acquisition.common.school_match import norm_school
        assert norm_school("Liberty Bell El Sch") == norm_school("liberty bell")
        assert norm_school("Hopewell El Sch") == norm_school("hopewell elementary school")
        assert norm_school("Southern Lehigh SHS") == norm_school("southern lehigh high school")
        assert norm_school("Roosevelt El") == norm_school("roosevelt")

    def test_el_survives_mid_name(self):
        from infrastructure.acquisition.common.school_match import norm_school
        assert "el camino" in norm_school("El Camino High School")
        assert norm_school("El Dorado El Sch") == norm_school("el dorado")

    def test_idempotent(self):
        from infrastructure.acquisition.common.school_match import norm_school
        for n in ("Liberty Bell El Sch", "Southern Lehigh SHS", "El Camino High School"):
            assert norm_school(norm_school(n)) == norm_school(n)


class TestRosterMatchKeys826:
    """#826 — the roster-hit signal's key construction and document basis.

    The issue framed the defect as "roster names don't go through norm_school". Measurement showed
    the roster side ALWAYS did (build_signals.py:1545); the DOCUMENT side did not, so a normalized
    key was searched inside raw lowercased text. The asymmetry was the bug."""

    def test_p2_a_variant_spelling_matches_once_the_document_is_normalized(self):
        """MUST FAIL against raw-lowercase matching: punctuation in the document blocked the key."""
        from infrastructure.acquisition.common.school_match import norm_document, roster_match_keys
        keys = roster_match_keys(["St. Mary's Elementary School", "Mount Vernon High School"],
                                 "Somewhere School District")
        doc = "Bell schedules for St. Mary's Elementary and Mt Vernon High follow."
        assert all(k not in doc.lower() for k in keys)          # today's behaviour: no match
        basis = norm_document(doc)
        assert "st marys" in basis                              # apostrophe + period folded
        assert any(k in basis for k in keys)

    def test_p3_the_district_name_collision_is_guarded(self):
        """A roster entry normalizing to the district's own name cannot produce a hit: level
        stripping collapses "Springfield Elementary School" and "Springfield School District" onto
        the same key, so every mention of the DISTRICT would score as a school."""
        from infrastructure.acquisition.common.school_match import norm_document, roster_match_keys
        keys = roster_match_keys(["Springfield Elementary School", "Lincoln Middle School"],
                                 "Springfield School District")
        assert "springfield" not in keys
        assert keys == ["lincoln"]
        # ...and the guard is what stops a bare district mention scoring
        basis = norm_document("Welcome to Springfield School District.")
        assert sum(1 for k in keys if k in basis) == 0

    def test_p3_the_guard_only_drops_the_COLLIDING_entry(self):
        """It must not drop schools that merely share a word with the district."""
        from infrastructure.acquisition.common.school_match import roster_match_keys
        keys = roster_match_keys(
            ["Springfield Elementary School", "Springfield Heights Academy", "Lincoln Middle"],
            "Springfield School District")
        assert "springfield heights" in keys       # distinct key, kept
        assert "lincoln" in keys
        assert "springfield" not in keys           # the exact collision, dropped

    def test_no_district_name_means_no_guard(self):
        from infrastructure.acquisition.common.school_match import roster_match_keys
        assert "springfield" in roster_match_keys(["Springfield Elementary School"], None)

    def test_short_stems_still_filtered(self):
        from infrastructure.acquisition.common.school_match import roster_match_keys
        assert roster_match_keys(["Ada High School"], "Somewhere ISD") == []      # 'ada' < 4
        assert roster_match_keys(["Adams High School"], "Somewhere ISD") == ["adams"]

    def test_norm_document_keeps_type_words(self):
        """The document must NOT be generic-stripped: a stripped key ('memphis central') has to
        remain findable inside the full name. Stripping both sides deletes the bridge."""
        from infrastructure.acquisition.common.school_match import norm_document, roster_match_keys
        basis = norm_document("Memphis Central High School")
        assert basis == "memphis central high school"
        assert roster_match_keys(["Memphis Central High School"], "Shelby County")[0] in basis

    def test_p4_pure_function_of_roster_plus_district_name(self):
        """No DB, no filesystem, no ordering dependence — recomputable from a re-ingest."""
        from infrastructure.acquisition.common.school_match import roster_match_keys
        a = roster_match_keys(["B School", "A Academy", "B School"], "D District")
        b = roster_match_keys(["A Academy", "B School"], "D District")
        assert a == b == sorted(set(a))
