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
