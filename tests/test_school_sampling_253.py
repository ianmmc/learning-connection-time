"""#253: the combined-scope name detector (A1) + the live band-SERVING denominator roster (B).

Detector tests are pure. Roster tests run against a synthetic ccd_sch fixture (the same
monkeypatched _NCES_DIR pattern as test_school_sampling_files.py) so they need no real data files;
one guard asserts the FileNotFoundError -> None fallback the closing-argument loader relies on.
"""
import csv

import pytest

from infrastructure.acquisition.common import school_sampling as SS

ROSTER = ["MILAGRO MIDDLE", "EDWARD ORTIZ MIDDLE", "GONZALES ELEMENTARY", "SANTA FE HIGH"]


class TestCombinedScopeName:
    def test_grade_band_group_descriptors_flag(self):
        for name, bands in (("k8 schools", ["elementary", "middle"]),
                            ("K-8 Schools", ["elementary", "middle"]),
                            ("middle schools", ["middle"]),
                            ("All Elementary Schools", ["elementary"])):
            m = SS.combined_scope_name(name, ROSTER)
            assert m and m["kind"] == "group_descriptor", name
            assert m["implied_bands"] == bands, name

    def test_conjunction_with_collective_plural_flags_unresolved(self):
        # the Santa Fe row: segments don't strict-match the roster ('ortiz' != 'edward ortiz'),
        # but the collective plural marks it a group all the same
        m = SS.combined_scope_name("milagro and ortiz schools", ROSTER)
        assert m and m["kind"] == "conjunction" and m["campuses"] == []

    def test_conjunction_resolving_two_roster_campuses_flags_with_list(self):
        m = SS.combined_scope_name("Milagro Middle and Edward Ortiz Middle", ROSTER)
        assert m and m["kind"] == "conjunction"
        assert set(m["campuses"]) == {"MILAGRO MIDDLE", "EDWARD ORTIZ MIDDLE"}

    def test_single_campus_names_do_not_flag(self):
        # 'and' inside one school's proper name; a plural typo on a real campus; plain names
        for name in ("Lewis and Clark Elementary", "Kearny Elementary Schools",
                     "MILAGRO MIDDLE", "Gonzales Elementary", ""):
            assert SS.combined_scope_name(name, ROSTER) is None, name


@pytest.fixture
def nces(tmp_path, monkeypatch):
    monkeypatch.setattr(SS, "_NCES_DIR", tmp_path)
    SS._district_schools.cache_clear()
    yield tmp_path
    SS._district_schools.cache_clear()


_SCH_COLS = ["LEAID", "NCESSCH", "SCH_NAME", "SY_STATUS", "SCH_TYPE_TEXT", "CHARTER_TEXT",
             "LEVEL", "GSLO", "GSHI"]


def _write_year(root, year, rows):
    d = root / year
    d.mkdir()
    with open(d / f"ccd_sch_029_{year[2:4]}{year[5:7]}_w_1a_073025.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_SCH_COLS)
        w.writeheader()
        w.writerows(rows)
    with open(d / f"ccd_sch_129_{year[2:4]}{year[5:7]}_w_1a_073025.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["NCESSCH", "VIRTUAL_TEXT"])
        w.writeheader()


def _sch(name, level, gslo, gshi, lea="1234567", sid="S1"):
    return {"LEAID": lea, "NCESSCH": sid, "SCH_NAME": name, "SY_STATUS": "1",
            "SCH_TYPE_TEXT": "Regular School", "CHARTER_TEXT": "No",
            "LEVEL": level, "GSLO": gslo, "GSHI": gshi}


class TestBandRostersForDistrict:
    def test_serving_rule_level_clean_union_grade_span(self, nces):
        # the Santa Fe shape in miniature: a clean Middle, an 'Elementary'-tagged K-8 (serves
        # middle via its span), a clean-Elementary K-6 (does NOT — the grade-7 discrimination),
        # and a 'High' 07-12 (gap-fill class — serves middle too)
        _write_year(nces, "2024_25", [
            _sch("Ortiz Middle", "Middle", "06", "08", sid="S1"),
            _sch("Gonzales K8", "Elementary", "KG", "08", sid="S2"),
            _sch("Atalaya Elementary", "Elementary", "PK", "06", sid="S3"),
            _sch("Tech Classics", "High", "07", "12", sid="S4"),
        ])
        r = SS.band_rosters_for_district("1234567")
        assert r["_year"] == "2024_25"
        assert r["middle"]["total"] == 3
        assert r["middle"]["by_source"] == {"level_clean": 1, "grade_span": 2, "level_override": 0}
        assert set(r["middle"]["schools"]) == {"Ortiz Middle", "Gonzales K8", "Tech Classics"}
        assert r["elementary"]["total"] == 2          # K-8 + K-6; 07-12 High serves no elementary
        assert r["high"]["total"] == 1

    def test_unattributed_and_latest_year_pick(self, nces):
        _write_year(nces, "2023_24", [_sch("Old Middle", "Middle", "06", "08")])
        _write_year(nces, "2024_25", [_sch("Ungraded Center", "Other", "M", "M")])
        assert SS.latest_nces_year() == "2024_25"
        r = SS.band_rosters_for_district("1234567")   # picks 2024_25, not the older year
        assert r["middle"]["total"] == 0
        assert r["_unattributed"] == ["Ungraded Center"]

    def test_missing_files_return_none(self, nces):
        assert SS.latest_nces_year() is None
        assert SS.band_rosters_for_district("1234567") is None


class TestIntermediateCarveOut:
    """#498 (DECIDED 2026-07-15): LEVEL stays primary with ONE override — LEVEL=Middle on an
    intermediate span (starts ≤4, tops ≤6) is upper ELEMENTARY. Every application is surfaced."""

    def test_liberati_class_reclassifies(self):
        assert SS.effective_level_band("Middle", "04", "06") == "elementary"
        assert SS.effective_level_band("Middle", "02", "06") == "elementary"

    def test_five_six_and_orphans_stay_untouched(self):
        # 5-6 is middle per the standard (NCES agrees); orphans RULED middle (Ian 2026-07-15)
        assert SS.effective_level_band("Middle", "05", "06") == "middle"
        assert SS.effective_level_band("Middle", "06", "06") == "middle"
        assert SS.effective_level_band("Middle", "05", "05") == "middle"
        assert SS.effective_level_band("Middle", "06", "08") == "middle"

    def test_other_levels_and_ambiguous_unaffected(self):
        assert SS.effective_level_band("Elementary", "KG", "06") == "elementary"
        assert SS.effective_level_band("High", "07", "12") == "high"
        assert SS.effective_level_band("Other", "04", "06") is None   # ambiguous stays ambiguous

    def test_intermediate_name_token_never_mismatches_either_side(self):
        # 'Intermediate' implies elementary OR middle (corpus: real ones sit on both sides)
        assert SS.name_level_mismatch("Pike Road Intermediate School", None, ["elementary"]) is None
        assert SS.name_level_mismatch("Albertville Intermediate School", None, ["middle"]) is None

    def test_roster_applies_and_surfaces_the_override(self, nces):
        _write_year(nces, "2024_25", [
            _sch("Liberati Intermediate", "Middle", "04", "06", sid="S1"),
            _sch("Real Middle", "Middle", "07", "08", sid="S2"),
        ])
        r = SS.band_rosters_for_district("1234567")
        assert r["middle"]["total"] == 1                    # only the real middle school
        assert r["elementary"]["total"] == 1
        assert r["elementary"]["by_source"]["level_override"] == 1
        (ov,) = r["_level_overrides"]
        assert ov["school"] == "Liberati Intermediate" and ov["band"] == "elementary" \
            and ov["instead_of"] == "middle"

    def test_school_index_places_intermediate_in_elementary(self, nces):
        _write_year(nces, "2024_25", [
            _sch("Liberati Intermediate", "Middle", "04", "06", sid="S1"),
            _sch("Real Middle", "Middle", "07", "08", sid="S2"),
            _sch("Some Elem", "Elementary", "KG", "03", sid="S3"),
        ])
        idx = SS.school_index("2024_25")["1234567"]
        assert [s["name"] for s in idx["middle"]] == ["Real Middle"]
        assert "Liberati Intermediate" in [s["name"] for s in idx["elementary"]]


class TestOrphanRulingMiddleFamily:
    """#498 orphan ruling (Ian, 2026-07-15): 5-5, 5-6, and 6-6 are all MIDDLE — a span starting
    at grade 5+ is middle-family and never counts elementary."""

    def test_rescue_bands_middle_family_spans(self):
        assert SS.bands_for_rescue("05", "06") == {"middle"}
        assert SS.bands_for_rescue("05", "05") == {"middle"}
        assert SS.bands_for_rescue("06", "06") == {"middle"}
        assert SS.bands_for_rescue("05", "08") == {"middle"}          # no elementary leak
        assert SS.bands_for_rescue("05", "12") == {"middle", "high"}  # ditto

    def test_rescue_low_starts_unchanged(self):
        # the West Bonner discipline is intact: PK-06 stays pure elementary; PK-07 reaches middle
        assert SS.bands_for_rescue("PK", "06") == {"elementary"}
        assert SS.bands_for_rescue("PK", "07") == {"elementary", "middle"}
        assert SS.bands_for_rescue("04", "06") == {"elementary"}      # intermediate span
        assert SS.bands_for_rescue("KG", "08") == {"elementary", "middle"}

    def test_partition_prefix_stops_before_a_grade5_segment(self):
        # K-4 / 5-6 / 7-8 / 9-12: only K-4 folds into elementary; 5-6 AND 7-8 are middle
        GO = SS.GRADE_ORD
        spans = {(GO["KG"], GO["04"]), (GO["05"], GO["06"]), (GO["07"], GO["08"]), (GO["09"], GO["12"])}
        g = SS.recursive_band_groups(spans)
        assert g == {"elementary": [0], "middle": [1, 2], "high": [3]}

    def test_partition_prefix_still_folds_intermediate_tiers(self):
        # K-3 / 4-6 / 7-8 / 9-12: both leading tiers are elementary (the Southern Lehigh shape)
        GO = SS.GRADE_ORD
        spans = {(GO["KG"], GO["03"]), (GO["04"], GO["06"]), (GO["07"], GO["08"]), (GO["09"], GO["12"])}
        g = SS.recursive_band_groups(spans)
        assert g == {"elementary": [0, 1], "middle": [2], "high": [3]}


class TestReviewRoundFixes:
    """PR #500 review round: the signal-1 phantom band, the span-aware #258 predicate, and the
    loader's effective-band stamp."""

    def test_roster_replaces_carveout_blind_signal1(self):
        # the 0604650 class: by_level says Middle:1 but that school is a 04-06 intermediate —
        # with the live roster supplied, middle is NOT claimed (no phantom for the spend gate)
        rosters = {"elementary": {"total": 1, "by_source": {}, "schools": ["Strawberry"]},
                   "middle": {"total": 0, "by_source": {}, "schools": []},
                   "high": {"total": 0, "by_source": {}, "schools": []},
                   "_unattributed": [], "_level_overrides": [], "_year": "2024_25"}
        got = SS.real_bands_for_district({"Elementary": 3, "Middle": 1}, {}, band_rosters=rosters)
        assert got == {"elementary"}
        # fallback (no roster — CCD off disk): the old aggregate signal stands
        got = SS.real_bands_for_district({"Elementary": 3, "Middle": 1}, {})
        assert got == {"elementary", "middle"}

    def test_stale_stage1_placement_still_claims_via_signal2(self):
        # a pre-#498 batch placed the intermediate under middle — signal 2 keeps the claim
        # (surfaced as a stale-roster note at gate@8, not silently dropped)
        rosters = {"elementary": {"total": 1, "by_source": {}, "schools": []},
                   "middle": {"total": 0, "by_source": {}, "schools": []},
                   "high": {"total": 0, "by_source": {}, "schools": []},
                   "_unattributed": [], "_level_overrides": [], "_year": "2024_25"}
        sbb = {"middle": {"schools": [{"school": "Liberati", "level": "Middle",
                                       "gslo": "04", "gshi": "06"}]}}
        got = SS.real_bands_for_district({"Middle": 1}, sbb, band_rosters=rosters)
        assert "middle" in got

    def test_mismatch_predicate_is_span_aware_both_directions(self):
        # the two review-round repro cases: a carved-out school named 'Middle' OR 'Elementary'
        # no longer false-positives against its own correct elementary placement
        assert SS.name_level_mismatch("Liberati Middle School", "Middle", ["elementary"],
                                      gslo="04", gshi="06") is None
        assert SS.name_level_mismatch("Liberati Elementary School", "Middle", ["elementary"],
                                      gslo="04", gshi="06") is None
        # the flag's real prey is untouched: Coffee County (high-named, ambiguous LEVEL, in
        # elementary) and Hammarskjold (elementary-named, genuine 5-6 middle) still flag
        assert SS.name_level_mismatch("Zion Chapel High School", "Other", ["elementary"],
                                      gslo="PK", gshi="12") is not None
        assert SS.name_level_mismatch("Hammarskjold Upper Elementary School", "Middle",
                                      ["middle"], gslo="05", gshi="06") is not None
        # span-less callers (the extracted-fact surface) behave exactly as before
        assert SS.name_level_mismatch("Northside High", None, ["elementary"]) is not None

    def test_loader_stamps_effective_band(self, nces):
        _write_year(nces, "2024_25", [
            _sch("Liberati Intermediate", "Middle", "04", "06", sid="S1"),
            _sch("Real Middle", "Middle", "07", "08", sid="S2"),
        ])
        by_did = SS._district_schools("2024_25")
        stamped = {s["name"]: (s["effective_band"], s["level_overridden"])
                   for s in by_did["1234567"]}
        assert stamped["Liberati Intermediate"] == ("elementary", True)
        assert stamped["Real Middle"] == ("middle", False)


class TestCorpusGoldenCounts:
    """REQ-142 (2026-07-15 audit sweep): the #498 carve-out's blast radius was measured ONCE against
    the real 2024-25 CCD (330 intermediate-carve-out overrides nationally) and recorded only in commit
    messages/PR bodies — nothing pinned it. Runs against the REAL on-disk corpus (2024-25 CCD is
    git-tracked, negated out of the data/raw/ .gitignore specifically so this is always available) so a
    future NCES refresh or an edit to effective_level_band that silently shifts this count fails CI
    instead of going unnoticed until the next hand audit. A tolerance band, not an exact pin, since NCES
    vintages do occasionally get corrected file-in-place without a version bump.

    (The PR's OTHER measured figure — 129 schools/123 districts losing a spurious elementary membership
    from the grade-5+ rescue-rule tightening — is a diff against the PRE-#498 rule, not an invariant of
    current-state code alone; some candidate schools resolve via recursive_band_groups's clean-partition
    path rather than the conservative bands_for_rescue fallback, so a simple current-side predicate
    overcounts. Not pinned here for that reason — a live re-diff against the pre-#498 commit, as done to
    verify this test file's own numbers, is the honest way to re-check it if #498's rules change again.)"""

    def test_intermediate_override_count_matches_pinned_measurement(self):
        year = SS.latest_nces_year()
        if year is None:
            pytest.skip("NCES CCD files not present on disk")
        n = sum(1 for schools in SS._district_schools(year).values()
               for sc in schools if sc.get("level_overridden"))
        assert 300 <= n <= 360, (
            f"intermediate carve-out override count drifted to {n} (pinned measurement: 330, "
            f"2024-25 CCD) — a real NCES change or a code change to effective_level_band; verify "
            f"which before updating this tolerance band")
