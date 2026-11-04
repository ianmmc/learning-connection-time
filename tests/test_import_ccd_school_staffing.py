"""DB-free tests for the CCD school-file importer (#1039, #1022 T5; acceptance A2).

Every guard is driven through the production entry point (load_year / write_year) with an input shaped
like the failure it refuses, and the DataGuardError (a SystemExit) must escape (#981: wired, not merely
defined). The claim is measured, not asserted: the PR #1068 review (#1075) neutralised 11 live guards
one at a time with the first version of this file still green; each of those now has a test here that
goes red for that mutation (listed in the PR). Writes against a fake session are the chunking/lineage
contract only; the SQL that reaches Postgres is tested in test_import_ccd_school_staffing_db.py (#1076).
"""

from __future__ import annotations

import csv
import io
import warnings
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrastructure.database.migrations import import_ccd_school_staffing as m
from infrastructure.utilities import source_manifest
from infrastructure.utilities.data_guards import DataGuardError

YEAR = "2024-25"
SY = "2024-2025"                     # how the CCD files spell SCHOOL_YEAR
SUB4 = m.SUBTOTAL_BY_GRADE
EUT = m.EDUCATION_UNIT_TOTAL
EUT_MINUS = m.EDUCATION_UNIT_TOTAL_MINUS_ADULT
CAT_A = "Category Set A - By Race/Ethnicity; Sex; Grade"
LEA_IND = m.LEA_TEACHERS_INDICATOR
PRODUCTION_COMPARED_FLOOR = m.MIN_COMPARED_SHARE

DIR_COLS = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "ST", "SCH_NAME", "SY_STATUS_TEXT", "SCH_TYPE_TEXT",
            "LEVEL", "GSLO", "GSHI", "WEBSITE"]
STAFF_COLS = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "SCH_NAME", "TEACHERS", "TOTAL_INDICATOR", "DMS_FLAG"]
MEMB_COLS = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "GRADE", "RACE_ETHNICITY", "SEX", "STUDENT_COUNT",
             "TOTAL_INDICATOR", "DMS_FLAG"]
LEA_COLS = ["SCHOOL_YEAR", "LEAID", "STAFF", "STAFF_COUNT", "TOTAL_INDICATOR", "DMS_FLAG"]

ELEM, MID, HIGH = "010000500001", "010000500002", "010000500003"
LEA = "0100005"
# A fixture base that is NOT the real one, so locate() must take the folder from the manifest it is handed:
# a regression to a hard-coded base turns test_locate_reads_the_form_the_manifest_pins red (#1108).
BASE = "fixture/ccd-tree"


def ydir(root: Path, year: str = YEAR, base: str = BASE) -> Path:
    """Where build_year writes: the production folder rule over the fixture base (no second copy)."""
    return source_manifest.year_folder(base, year, root)


@pytest.fixture(autouse=True)
def three_school_floor(monkeypatch):
    """The three-specimen fixture compares 2 of 3 schools (ELEM carries unreported grades on purpose),
    below the production MIN_COMPARED_SHARE. That floor is exercised at its real value, on a 40-school
    fixture, by test_refuses_when_most_schools_cannot_be_compared."""
    monkeypatch.setattr(m, "MIN_COMPARED_SHARE", 0.5)


def _directory():
    return [
        [SY, ELEM, LEA, "AL", "Elm Elementary", "Open", "Regular School", "Elementary", "KG", "05", ""],
        [SY, MID, LEA, "AL", "Elm Middle", "Open", "Regular School", "Middle", "06", "08", ""],
        [SY, HIGH, LEA, "AL", "Elm High", "Reopened", "Special Education School", "High", "09", "12", ""],
    ]


def _staff():
    return [
        [SY, ELEM, LEA, "Elm Elementary", "20.50", EUT, "Reported"],
        [SY, MID, LEA, "Elm Middle", "", EUT, "Missing"],
        [SY, HIGH, LEA, "Elm High", "30.00", EUT, "Reported"],
    ]


def _sub4(ncessch, grade, count, flag="Reported"):
    return [SY, ncessch, LEA, grade, "No Category Codes", "No Category Codes", count, SUB4, flag]


def _total(ncessch, count, indicator):
    return [SY, ncessch, LEA, "Not Specified", "No Category Codes", "No Category Codes", count, indicator, "Derived"]


# Every stored grade occurs (the importer requires that, as a dropped 'Grade 13' is the #976 shape).
# ELEM has unreported grades → not compared; MID: 100+110+120 (Adult Education excluded) == 330;
# HIGH: 50+51+52+53+2+4 + a 'Not Specified' residual of 1 == 213.
MEMB_MID_G7 = 12


def _membership():
    return [
        # a Category Set A detail row, the kind the importer must ignore
        [SY, ELEM, LEA, "Grade 1", "Asian", "Female", "3", CAT_A, "Reported"],
        _sub4(ELEM, "Pre-Kindergarten", "10"),
        _sub4(ELEM, "Kindergarten", "40"),
        _sub4(ELEM, "Grade 1", "0", "Manual adjustment"),   # NCES's zero-fill: NULL + flag (#1070)
        _sub4(ELEM, "Grade 2", "", "Suppressed"),            # blank with a flag: stays NULL
        _sub4(ELEM, "Grade 3", "42"),
        _sub4(ELEM, "Grade 4", "43"),
        _sub4(ELEM, "Grade 5", "44"),
        _sub4(ELEM, "Not Specified", "0", "Derived"),
        _total(ELEM, "179", EUT_MINUS),
        _total(ELEM, "179", EUT),
        _sub4(MID, "Grade 6", "100"),
        _sub4(MID, "Grade 7", "110"),
        _sub4(MID, "Grade 8", "120"),
        _sub4(MID, "Adult Education", "5"),
        _sub4(MID, "Not Specified", "0", "Derived"),
        _total(MID, "330", EUT_MINUS),
        _total(MID, "335", EUT),
        _sub4(HIGH, "Grade 9", "50"),
        _sub4(HIGH, "Grade 10", "51"),
        _sub4(HIGH, "Grade 11", "52"),
        _sub4(HIGH, "Grade 12", "53"),
        _sub4(HIGH, "Grade 13", "2"),
        _sub4(HIGH, "Ungraded", "4"),
        _sub4(HIGH, "Not Specified", "1", "Derived"),
        _total(HIGH, "213", EUT_MINUS),
        _total(HIGH, "213", EUT),
    ]


def _lea():
    return [
        [SY, LEA, "Teachers", "52.00", LEA_IND, "Reported"],
        [SY, LEA, "Elementary Teachers", "20.50", "Category Set A", "Reported"],
    ]


def _csv_bytes(header, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


FILE_STEMS = {
    "029": "ccd_sch_029_2425_w_1a_073025",
    "059": "ccd_sch_059_2425_l_1a_073025",
    "052": "ccd_sch_052_2425_l_1a_073025",
    "lea_059": "ccd_lea_059_2425_l_1a_073025",
}


def build_year(root: Path, *, directory=None, staff=None, membership=None, lea=None,
               membership_as_zip=True, staff_as_zip=False, year=YEAR, base=BASE) -> dict:
    """Write a year directory under `root` and return a manifest that pins every file (all four)."""
    d = ydir(root, year, base)
    d.mkdir(parents=True, exist_ok=True)
    files = {}

    def put(stem, data, as_zip):
        if as_zip:
            p = d / (stem + ".zip")
            with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(stem + ".csv", data)
        else:
            p = d / (stem + ".csv")
            p.write_bytes(data)
        files[p.name] = p

    put(FILE_STEMS["029"], _csv_bytes(DIR_COLS, _directory() if directory is None else directory), False)
    put(FILE_STEMS["059"], _csv_bytes(STAFF_COLS, _staff() if staff is None else staff), staff_as_zip)
    put(FILE_STEMS["052"], _csv_bytes(MEMB_COLS, _membership() if membership is None else membership),
        membership_as_zip)
    put(FILE_STEMS["lea_059"], _csv_bytes(LEA_COLS, _lea() if lea is None else lea), False)
    return {"source": "nces-ccd", "base": base, "years": {year: [
        {"file": n, "bytes": p.stat().st_size, "sha256": source_manifest.sha256_file(p), "url": "u"}
        for n, p in files.items()]}}


def _restamp(rows, sy):
    return [[sy] + r[1:] for r in rows]


# ------------------------------------------------------------------------------------------------- happy path
def test_loads_every_directory_school_verbatim(tmp_path):
    manifest = build_year(tmp_path)
    rows, details = m.load_year(YEAR, tmp_path, manifest)
    by = {r["ncessch"]: r for r in rows}
    assert set(by) == {ELEM, MID, HIGH}
    e = by[ELEM]
    assert (e["leaid"], e["state"], e["level"], e["gslo"], e["gshi"]) == (LEA, "AL", "Elementary", "KG", "05")
    assert (e["school_name"], e["sy_status"], e["sch_type"]) == ("Elm Elementary", "Open", "Regular School")
    assert e["teachers_fte"] == 20.5 and e["teachers_dms_flag"] == "Reported"
    assert (e["memb_pk"], e["memb_kg"], e["memb_03"], e["memb_05"]) == (10, 40, 42, 44)
    assert e["memb_01"] is None                      # 'Manual adjustment' 0 is not a count (#1070)
    assert e["memb_02"] is None                      # blank stays NULL, never 0
    assert e["memb_06"] is None                      # a grade the school has no row for
    assert e["membership_flags"] == {"Grade 1": "Manual adjustment", "Grade 2": "Suppressed"}
    mid = by[MID]
    assert mid["teachers_fte"] is None and mid["teachers_dms_flag"] == "Missing"
    assert (mid["memb_06"], mid["memb_07"], mid["memb_08"]) == (100, 110, 120)
    assert mid["membership_flags"] is None
    h = by[HIGH]
    assert (h["school_name"], h["sy_status"], h["sch_type"]) == ("Elm High", "Reopened", "Special Education School")
    assert h["teachers_fte"] == 30.0 and h["membership_flags"] is None
    assert (h["memb_09"], h["memb_13"], h["memb_ug"], h["memb_kg"]) == (50, 2, 4, None)
    assert all(r["source_year"] == YEAR for r in rows)
    assert set(details["sources"]) == {"029", "052", "059", "lea_059"}
    for fid in ("029", "052", "059"):
        assert {r[f"src_{fid}_sha256"] for r in rows} == {details["sources"][fid][1]}
    assert all(len(v[1]) == 64 for v in details["sources"].values())
    rec = details["membership_reconciliation"]
    assert (rec["n_compared"], rec["n_disagree"]) == (2, 0)              # MID + HIGH; ELEM has unreported grades
    assert details["membership_compared_share"] == round(2 / 3, 5)
    assert details["grade_not_specified_students"] == 1                 # HIGH's residual, counted not stored
    assert details["membership_unreported_cells"] == {"Manual adjustment": 1, "Suppressed": 1}
    assert details["membership_unreported_cells_by_fips"] == {"01": 2}
    assert details["teachers_unreported_values"] == 0
    assert "memb_ns" not in h and "Not Specified" not in (h["membership_flags"] or {})
    cov = details["lea_coverage"]
    assert cov["school_teachers_fte"] == 50.5 and cov["lea_teachers_fte"] == 52.0
    assert cov["leas_compared"] == 1 and cov["leas_within_5pct"] == 1


def test_an_unreported_teacher_value_is_null_with_its_flag(tmp_path):
    staff = _staff()
    staff[2][4:7] = ["0.00", EUT, "Manual adjustment"]
    lea = _lea()
    lea[0][3] = "20.50"                                   # keep the LEA coverage guard out of the picture
    rows, details = m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff, lea=lea))
    h = next(r for r in rows if r["ncessch"] == HIGH)
    assert h["teachers_fte"] is None and h["teachers_dms_flag"] == "Manual adjustment"
    assert details["teachers_unreported_values"] == 1


def test_blank_text_cells_are_null_and_a_school_named_none_survives(tmp_path):
    directory = _directory()
    directory[0][3:5] = ["", ""]                 # blank ST and SCH_NAME
    directory[1][4] = "None"                     # pandas' default NA token; a real name here (#1071)
    rows, _ = m.load_year(YEAR, tmp_path, build_year(tmp_path, directory=directory))
    by = {r["ncessch"]: r for r in rows}
    assert by[ELEM]["state"] is None and by[ELEM]["school_name"] is None
    assert by[MID]["school_name"] == "None"
    assert not any(isinstance(v, float) and v != v for r in rows for v in r.values())


def test_loads_without_a_deprecation_warning(tmp_path):
    manifest = build_year(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("error")           # pytest.ini ignores DeprecationWarning; #1081 hid behind it
        m.load_year(YEAR, tmp_path, manifest)


# ------------------------------------------------------------------------------------------------- the manifest decides
def test_locate_reads_the_form_the_manifest_pins(tmp_path):
    manifest = build_year(tmp_path, staff_as_zip=True)
    d = ydir(tmp_path)
    (d / (FILE_STEMS["059"] + ".csv")).write_bytes(b"stray extracted copy")    # both forms on disk
    sources = m.locate(YEAR, manifest, tmp_path)
    assert sources["059"][0].suffix == ".zip" and sources["029"][0].suffix == ".csv"
    rows, _ = m.load_year(YEAR, tmp_path, manifest)
    assert len(rows) == 3
    manifest = build_year(tmp_path, staff_as_zip=False)
    (d / (FILE_STEMS["059"] + ".zip")).write_bytes(b"stray zip")
    assert m.locate(YEAR, manifest, tmp_path)["059"][0].suffix == ".csv"


def test_locate_refuses_an_undeclared_year_id_or_absent_pin(tmp_path):
    manifest = build_year(tmp_path)
    with pytest.raises(DataGuardError, match="2023-24 is not declared in the nces-ccd manifest"):
        m.load_year("2023-24", tmp_path, manifest)
    entries = manifest["years"][YEAR]
    manifest["years"][YEAR] = [e for e in entries if "052" not in e["file"]]
    with pytest.raises(DataGuardError, match=r"declares 0 ccd_sch_052_\* file"):
        m.load_year(YEAR, tmp_path, manifest)
    manifest["years"][YEAR] = entries + [dict(entries[1], file="ccd_sch_059_2425_l_2a_073025.csv")]
    with pytest.raises(DataGuardError, match=r"declares 2 ccd_sch_059_\* file"):
        m.load_year(YEAR, tmp_path, manifest)
    manifest["years"][YEAR] = entries
    (ydir(tmp_path) / (FILE_STEMS["lea_059"] + ".csv")).unlink()
    with pytest.raises(DataGuardError, match="ccd_lea_059_.* is pinned for 2024-25 but is not on disk"):
        m.load_year(YEAR, tmp_path, manifest)


@pytest.mark.parametrize("fid", ["059", "lea_059"])
def test_refuses_a_file_whose_bytes_drifted_from_the_pin(tmp_path, fid):
    manifest = build_year(tmp_path)
    p = ydir(tmp_path) / (FILE_STEMS[fid] + ".csv")
    p.write_bytes(p.read_bytes().replace(b"52.00", b"52.01").replace(b"20.50", b"20.51"))
    with pytest.raises(DataGuardError, match=f"{FILE_STEMS[fid]}.* is not the pinned 2024-25 file"):
        m.load_year(YEAR, tmp_path, manifest)              # the LEA file too (#1072)


def test_the_lea_file_sha_is_recorded(tmp_path):
    manifest = build_year(tmp_path)
    _, details = m.load_year(YEAR, tmp_path, manifest)
    p = ydir(tmp_path) / (FILE_STEMS["lea_059"] + ".csv")
    assert details["sources"]["lea_059"] == [p.name, source_manifest.sha256_file(p)]


# ------------------------------------------------------------------------------------------------- the year
def test_refuses_a_covid_or_malformed_year_before_reading_anything(tmp_path):
    with pytest.raises(DataGuardError, match="2021-22: a COVID-excluded year"):
        m.load_year("2021-22", tmp_path, {"years": {}})
    with pytest.raises(DataGuardError, match="not a school year"):
        m.load_year("2024-2025", tmp_path, {"years": {}})


@pytest.mark.parametrize("which, label", [("directory", "029"), ("staff", "059"), ("membership", "052"), ("lea", "LEA 059")])
def test_refuses_a_file_whose_own_school_year_is_another_vintage(tmp_path, which, label):
    rows = {"directory": _directory, "staff": _staff, "membership": _membership, "lea": _lea}[which]()
    manifest = build_year(tmp_path, **{which: _restamp(rows, "2023-2024")})
    with pytest.raises(DataGuardError, match=rf"{label}: SCHOOL_YEAR is \['2023-2024'\], not '2024-2025'"):
        m.load_year(YEAR, tmp_path, manifest)


# ------------------------------------------------------------------------------------------------- A2: vocabulary
@pytest.mark.parametrize("field, bad", [
    ("GRADE", "Grade 14"),
    ("DMS_FLAG", "Estimated"),
    ("TOTAL_INDICATOR", "Subtotal 5 - By Grade"),
])
def test_refuses_an_unknown_052_label(tmp_path, field, bad):
    rows = _membership()
    rows[MEMB_MID_G7][MEMB_COLS.index(field)] = bad          # MID's Grade 7 Subtotal 4 row
    manifest = build_year(tmp_path, membership=rows)
    with pytest.raises(DataGuardError, match=f"052 .*{field}.*outside the known vocabulary"):
        m.load_year(YEAR, tmp_path, manifest)


@pytest.mark.parametrize("col, bad, label", [
    (6, "Reported (est.)", "059 DMS_FLAG"),
    (5, "Education Unit Totals", "059 TOTAL_INDICATOR"),
    (6, "", "059 DMS_FLAG"),                                 # a blank is outside every vocabulary (#1071)
])
def test_refuses_an_unknown_059_label(tmp_path, col, bad, label):
    staff = _staff()
    staff[0][col] = bad
    with pytest.raises(DataGuardError, match=f"{label}.*outside the known vocabulary"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))


@pytest.mark.parametrize("bad", ["Primary", ""])
def test_refuses_an_unknown_or_blank_029_level(tmp_path, bad):
    directory = _directory()
    directory[0][7] = bad
    with pytest.raises(DataGuardError, match="029 LEVEL.*outside the known vocabulary"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, directory=directory))


def test_refuses_when_the_subtotal_rows_it_filters_on_never_occur(tmp_path):
    rows = [r for r in _membership() if r[7] != SUB4]          # a relabel that empties the selection
    manifest = build_year(tmp_path, membership=rows)
    with pytest.raises(DataGuardError, match="052 TOTAL_INDICATOR.*never seen"):
        m.load_year(YEAR, tmp_path, manifest)


def test_refuses_when_a_stored_grade_never_occurs(tmp_path):
    rows = [r for r in _membership() if r[3] != "Grade 7"]
    manifest = build_year(tmp_path, membership=rows)
    with pytest.raises(DataGuardError, match="052 GRADE.*never seen.*Grade 7"):
        m.load_year(YEAR, tmp_path, manifest)


def test_refuses_when_a_required_level_never_occurs(tmp_path):
    directory = _directory()
    directory[1][7] = "Other"                                 # no 'Middle' anywhere: a relabel (#1075)
    with pytest.raises(DataGuardError, match="029 LEVEL.*never seen.*Middle"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, directory=directory))


def test_refuses_when_no_cell_is_reported(tmp_path):
    staff = [r[:6] + ["Missing"] for r in _staff()]
    with pytest.raises(DataGuardError, match="059 DMS_FLAG.*never seen.*Reported"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))
    membership = [r[:8] + ["Derived"] for r in _membership()]
    with pytest.raises(DataGuardError, match="052 DMS_FLAG.*never seen.*Reported"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, membership=membership))


def test_an_empty_directory_is_refused(tmp_path):
    manifest = build_year(tmp_path, directory=[])
    with pytest.raises(DataGuardError, match=r"029: SCHOOL_YEAR is \[\], not '2024-2025'"):   # header-only: no vintage
        m.load_year(YEAR, tmp_path, manifest)


# ------------------------------------------------------------------------------------------------- A2: ids and numbers
@pytest.mark.parametrize("col, bad, label", [(2, "100005", "029 LEAID"), (1, "10000500001", "029 NCESSCH")])
def test_refuses_an_id_of_the_wrong_shape(tmp_path, col, bad, label):
    directory = _directory()
    directory[0][col] = bad                                   # the stripped leading zero, #611 (#1085)
    with pytest.raises(DataGuardError, match=rf"{label}: 1 id\(s\) are not .*{bad}"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, directory=directory))


@pytest.mark.parametrize("token", ["-5", "42.9", "*", "1,234", "nan"])
def test_refuses_a_student_count_that_is_not_a_non_negative_integer(tmp_path, token):
    rows = _membership()
    rows[MEMB_MID_G7][6] = token
    with pytest.raises(DataGuardError, match=rf"052 STUDENT_COUNT \(Subtotal 4\): 1 cell.*'{MID}', '{token}'"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, membership=rows))        # names the school (#1084)


@pytest.mark.parametrize("token", ["-1", "*", "inf"])
def test_refuses_a_teacher_count_that_is_not_a_non_negative_number(tmp_path, token):
    staff = _staff()
    staff[0][4] = token
    with pytest.raises(DataGuardError, match=rf"059 TEACHERS: 1 cell.*'{ELEM}', '{token}'"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))


# ------------------------------------------------------------------------------------------------- A2: CRC + members
def test_refuses_a_member_whose_crc_fails(tmp_path):
    manifest = build_year(tmp_path, membership_as_zip=False)
    d = ydir(tmp_path)
    csv_path = d / (FILE_STEMS["052"] + ".csv")
    data = csv_path.read_bytes()
    csv_path.unlink()
    zip_path = d / (FILE_STEMS["052"] + ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        z.writestr(csv_path.name, data)
    raw = zip_path.read_bytes()
    assert raw.count(b"No Category Codes") >= 1
    zip_path.write_bytes(raw.replace(b"No Category Codes", b"No Category Codex", 1))   # payload edited, CRC not
    entry = next(e for e in manifest["years"][YEAR] if "052" in e["file"])
    entry.update(file=zip_path.name, bytes=zip_path.stat().st_size, sha256=source_manifest.sha256_file(zip_path))
    with pytest.raises(zipfile.BadZipFile, match="CRC"):
        m.load_year(YEAR, tmp_path, manifest)


def test_refuses_a_zip_with_two_csv_members(tmp_path):
    manifest = build_year(tmp_path)
    zip_path = ydir(tmp_path) / (FILE_STEMS["052"] + ".zip")
    with zipfile.ZipFile(zip_path, "a") as z:
        z.writestr("readme_extra.csv", "x")
    entry = next(e for e in manifest["years"][YEAR] if "052" in e["file"])
    entry.update(bytes=zip_path.stat().st_size, sha256=source_manifest.sha256_file(zip_path))
    with pytest.raises(DataGuardError, match="expected exactly one .csv member"):
        m.load_year(YEAR, tmp_path, manifest)


# ------------------------------------------------------------------------------------------------- reconciliation
def test_refuses_a_per_school_total_that_does_not_reconcile(tmp_path):
    rows = _membership()
    rows[MEMB_MID_G7][6] = "111"                         # MID Grade 7: 100 + 111 + 120 != 330
    manifest = build_year(tmp_path, membership=rows)
    with pytest.raises(DataGuardError, match="1 of 2 rows disagree"):
        m.load_year(YEAR, tmp_path, manifest)


def test_the_grade_unknown_residual_is_part_of_the_reconciled_sum(tmp_path):
    rows = _membership()
    hi = next(i for i, r in enumerate(rows) if r[1] == HIGH and r[3] == "Not Specified")
    rows[hi][6] = "2"                                     # 212 + 2 != 213
    with pytest.raises(DataGuardError, match="1 of 2 rows disagree"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, membership=rows))


def test_adult_education_is_excluded_from_the_reconciled_sum_and_not_stored(tmp_path):
    manifest = build_year(tmp_path)
    rows, _ = m.load_year(YEAR, tmp_path, manifest)
    mid = next(r for r in rows if r["ncessch"] == MID)
    assert "memb_ae" not in mid and sum(v for k, v in mid.items() if k.startswith("memb_") and v) == 330


def test_refuses_duplicate_grade_or_total_rows(tmp_path):
    rows = _membership() + [_sub4(MID, "Grade 7", "110")]
    with pytest.raises(DataGuardError, match=r"052 Subtotal 4: 1 duplicate \(NCESSCH, GRADE\)"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, membership=rows))
    rows = _membership() + [_total(MID, "330", EUT_MINUS)]
    with pytest.raises(DataGuardError, match="052 'Derived - Education Unit Total minus Adult Education Count': 1 NCESSCH"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, membership=rows))


def _many_schools(n: int, uncompared: int):
    """n Elementary/Middle/High schools in one LEA; the first `uncompared` carry a suppressed grade."""
    directory, staff, membership = [], [], []
    for i in range(n):
        sch = f"{LEA}{i:05d}"
        level = ("Elementary", "Middle", "High")[i % 3]
        directory.append([SY, sch, LEA, "AL", f"School {i}", "Open", "Regular School", level, "KG", "12", ""])
        staff.append([SY, sch, LEA, f"School {i}", "1.00" if i == 0 else "", EUT, "Reported" if i == 0 else "Missing"])
        if i < uncompared:
            membership.append(_sub4(sch, "Kindergarten", "", "Suppressed"))
        else:
            membership.append(_sub4(sch, "Kindergarten", "10"))
        if i == 0:                                        # every stored grade must be seen once
            membership += [_sub4(sch, g, "0") for g in m.GRADE_COLUMN if g != "Kindergarten"]
        membership += [_sub4(sch, "Not Specified", "0", "Derived"), _total(sch, "10", EUT_MINUS), _total(sch, "10", EUT)]
    lea = [[SY, LEA, "Teachers", "1.00", LEA_IND, "Reported"]]
    return dict(directory=directory, staff=staff, membership=membership, lea=lea)


def test_refuses_when_most_schools_cannot_be_compared(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "MIN_COMPARED_SHARE", PRODUCTION_COMPARED_FLOOR)      # 0.95: the real floor (#1078)
    rows, details = m.load_year(YEAR, tmp_path, build_year(tmp_path, **_many_schools(40, 2)))
    assert details["membership_compared_share"] == 0.95 and len(rows) == 40
    with pytest.raises(DataGuardError, match=r"compared only 37 of 40 schools \(92.5%, floor 95%\)"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, **_many_schools(40, 3)))


def test_refuses_a_school_outside_the_directory_or_with_another_leaid(tmp_path):
    staff = _staff() + [[SY, "019999900001", LEA, "Ghost", "1.0", EUT, "Reported"]]
    with pytest.raises(DataGuardError, match="059 staff: 1 school.* not in the 029 directory"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))
    staff = _staff()
    staff[2][2] = "0100006"
    with pytest.raises(DataGuardError, match="059 staff: 1 school.* different LEAID"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))
    membership = _membership() + [_sub4("019999900001", "Grade 1", "1"), _total("019999900001", "1", EUT_MINUS)]
    with pytest.raises(DataGuardError, match="052 membership: 1 school.* not in the 029 directory"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, membership=membership))


def test_refuses_a_duplicate_school_row(tmp_path):
    staff = _staff() + [_staff()[0]]
    with pytest.raises(DataGuardError, match="059 staff: 1 NCESSCH value.* more than once"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))


# ------------------------------------------------------------------------------------------------- LEA coverage
def test_lea_coverage_is_reported_and_only_the_aggregate_is_guarded(tmp_path):
    lea = _lea()
    lea[0][3] = "60.00"                                 # 50.5 / 60 = 0.84: outside ±5%
    manifest = build_year(tmp_path, lea=lea)
    with pytest.raises(DataGuardError, match="059 Σ school teachers vs LEA-file 'Teachers'"):
        m.load_year(YEAR, tmp_path, manifest)


def test_lea_coverage_refuses_the_wrong_lea_vocabulary_or_a_duplicate_lea(tmp_path):
    lea = [[SY, LEA, "Teachers", "52.00", "Education Unit Total", "Reported"]]
    with pytest.raises(DataGuardError, match="LEA 059 TOTAL_INDICATOR.*never seen"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, lea=lea))
    lea = _lea() + [_lea()[0]]
    with pytest.raises(DataGuardError, match="LEA 059 'Teachers': 1 duplicate LEAID"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, lea=lea))


# ------------------------------------------------------------------------------------------------- one home (#1086)
def test_the_grade_vocabulary_and_required_levels_have_one_home():
    from infrastructure.database.migrations.import_staff_and_enrollment import GRADE_MAPPING
    from infrastructure.utilities.grade_bands import LEVEL_BAND
    assert set(m.GRADE_COLUMN) == set(GRADE_MAPPING) - {"Adult Education"}
    assert m.LEVELS_REQUIRED == set(LEVEL_BAND)


# ------------------------------------------------------------------------------------------------- write
def _session(n_districts: int, n_matched: int) -> MagicMock:
    session = MagicMock()
    session.execute.return_value.scalar.side_effect = [n_districts, n_matched]
    return session


def test_write_year_refuses_zero_rows_before_deleting(tmp_path):
    session = _session(1, 1)
    with pytest.raises(DataGuardError, match="matched 0 rows"):
        m.write_year(session, YEAR, [], {"sources": {}})
    session.execute.assert_not_called()


def test_write_year_refuses_a_file_that_matches_too_few_districts_before_deleting():
    rows = [{"ncessch": f"{i:012d}", "leaid": f"{i:07d}", "source_year": YEAR} for i in range(100)]
    session = _session(100, 50)
    with pytest.raises(DataGuardError, match="only 50 of 100 districts matched"):
        m.write_year(session, YEAR, rows, {"sources": {}})
    assert session.execute.call_count == 2 and "DELETE" not in str(session.execute.call_args_list)


def test_write_year_replaces_the_year_in_chunks_and_logs_lineage(monkeypatch):
    monkeypatch.setattr(m, "INSERT_CHUNK", 2)
    session = _session(1, 1)
    rows = [{"ncessch": str(i), "leaid": LEA, "source_year": YEAR} for i in range(5)]
    details = {"sources": {"029": ["a.csv", "x"], "052": ["b.zip", "y"], "059": ["c.csv", "z"], "lea_059": ["d.csv", "w"]}}
    assert m.write_year(session, YEAR, rows, details) == 5
    calls = session.execute.call_args_list
    assert "DELETE FROM ccd_school_staffing" in str(calls[2].args[0].compile())
    assert [len(c.args[1]) for c in calls[3:]] == [2, 2, 1]
    lineage = session.add.call_args.args[0]
    assert (lineage.entity_type, lineage.entity_id, lineage.operation) == ("ccd_school_staffing", YEAR, "import")
    assert lineage.source_file == "a.csv, b.zip, c.csv, d.csv" and lineage.details is details
    assert details["district_match"] == {"file_leas": 1, "districts": 1, "matched": 1}


def test_dry_run_never_opens_a_session(monkeypatch, tmp_path):
    manifest = build_year(tmp_path)
    monkeypatch.setattr(m.source_manifest, "load", lambda source: manifest)
    opened = MagicMock()

    @contextmanager
    def scope():
        opened()
        yield _session(1, 1)
    monkeypatch.setattr(m, "session_scope", scope)
    m.main(["--year", YEAR, "--dry-run"], root=tmp_path)
    opened.assert_not_called()
    m.main(["--year", YEAR], root=tmp_path)
    opened.assert_called_once()


# ------------------------------------------------------------------------------------------------- rebuild wiring
def test_phase_3_runs_the_school_import_after_the_lea_import_for_the_same_year(monkeypatch):
    import infrastructure.scripts.rebuild_database as rb
    seen = []

    def fake_run(script, args=None, dry_run=False):
        seen.append((script, args, dry_run))
        return True
    monkeypatch.setattr(rb, "run_script", fake_run)
    assert rb.phase_3_staff_enrollment(True, "2023-24") is True
    assert seen == [
        (rb.SCRIPTS["import_staff_enrollment"], ["--year", "2023-24"], True),
        (rb.SCRIPTS["import_ccd_school_staffing"], ["--year", "2023-24"], True),
    ]
    assert rb.SCRIPTS["import_ccd_school_staffing"].endswith("import_ccd_school_staffing.py")


def test_phase_3_stops_when_the_lea_import_fails(monkeypatch):
    import infrastructure.scripts.rebuild_database as rb
    seen = []

    def fake_run(script, args=None, dry_run=False):
        seen.append(script)
        return False
    monkeypatch.setattr(rb, "run_script", fake_run)
    assert rb.phase_3_staff_enrollment(False, "2024-25") is False
    assert seen == [rb.SCRIPTS["import_staff_enrollment"]]


def test_phase_3_fails_when_only_the_school_import_fails(monkeypatch):
    import infrastructure.scripts.rebuild_database as rb
    seen = []

    def fake_run(script, args=None, dry_run=False):
        seen.append(script)
        return script != rb.SCRIPTS["import_ccd_school_staffing"]      # LEA ok, school import fails (#1080)
    monkeypatch.setattr(rb, "run_script", fake_run)
    assert rb.phase_3_staff_enrollment(False, "2024-25") is False
    assert seen == [rb.SCRIPTS["import_staff_enrollment"], rb.SCRIPTS["import_ccd_school_staffing"]]


def test_the_folder_comes_from_the_manifest_base_and_follows_lct_data_root(tmp_path, monkeypatch):
    """#1089/#1099: no importer-local folder rule. With no root given, a manifest whose base is the real
    CCD base resolves under LCT_DATA_ROOT (the `data/` prefix relocates), exactly as
    source_manifest.ccd_year_folder (every CCD reader) and source_manifest.verify see it."""
    repo_shaped = tmp_path / "relocated"
    manifest = build_year(repo_shaped, base=source_manifest.CCD_BASE)
    moved = repo_shaped / "data"
    monkeypatch.setenv("LCT_DATA_ROOT", str(moved))
    sources = m.locate(YEAR, manifest)
    assert sources["029"][0].parent == moved / "raw/federal/nces-ccd/2024_25" == source_manifest.ccd_year_folder(YEAR)
    rows, _ = m.load_year(YEAR, None, manifest)
    assert len(rows) == 3
