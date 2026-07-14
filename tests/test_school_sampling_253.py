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
        assert r["middle"]["by_source"] == {"level_clean": 1, "grade_span": 2}
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
