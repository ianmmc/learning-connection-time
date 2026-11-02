"""DB-free tests for the CCD school-file importer (#1039, #1022 T5; acceptance A2).

Every guard is driven through the production entry point (load_year / write_year) with an input shaped
like the failure it refuses, and the DataGuardError (a SystemExit) must escape (#981: wired, not merely
defined). Writes are exercised against a fake session.
"""

from __future__ import annotations

import csv
import io
import zipfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrastructure.database.migrations import import_ccd_school_staffing as m
from infrastructure.utilities import source_manifest
from infrastructure.utilities.data_guards import DataGuardError

YEAR = "2024-25"
SUB4 = m.SUBTOTAL_BY_GRADE
EUT = m.EDUCATION_UNIT_TOTAL
EUT_MINUS = m.EDUCATION_UNIT_TOTAL_MINUS_ADULT
CAT_A = "Category Set A - By Race/Ethnicity; Sex; Grade"

DIR_COLS = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "ST", "SCH_NAME", "SY_STATUS_TEXT", "SCH_TYPE_TEXT",
            "LEVEL", "GSLO", "GSHI", "WEBSITE"]
STAFF_COLS = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "SCH_NAME", "TEACHERS", "TOTAL_INDICATOR", "DMS_FLAG"]
MEMB_COLS = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "GRADE", "RACE_ETHNICITY", "SEX", "STUDENT_COUNT",
             "TOTAL_INDICATOR", "DMS_FLAG"]
LEA_COLS = ["SCHOOL_YEAR", "LEAID", "STAFF", "STAFF_COUNT", "TOTAL_INDICATOR", "DMS_FLAG"]

ELEM, MID, HIGH = "010000500001", "010000500002", "010000500003"
LEA = "0100005"


def _directory():
    return [
        [YEAR, ELEM, LEA, "AL", "Elm Elementary", "Open", "Regular School", "Elementary", "KG", "05", ""],
        [YEAR, MID, LEA, "AL", "Elm Middle", "Open", "Regular School", "Middle", "06", "08", ""],
        [YEAR, HIGH, LEA, "AL", "Elm High", "Open", "Regular School", "High", "09", "12", ""],
    ]


def _staff():
    return [
        [YEAR, ELEM, LEA, "Elm Elementary", "20.50", EUT, "Reported"],
        [YEAR, MID, LEA, "Elm Middle", "", EUT, "Missing"],
        [YEAR, HIGH, LEA, "Elm High", "30.00", EUT, "Reported"],
    ]


def _sub4(ncessch, grade, count, flag="Reported"):
    return [YEAR, ncessch, LEA, grade, "No Category Codes", "No Category Codes", count, SUB4, flag]


def _total(ncessch, count, indicator):
    return [YEAR, ncessch, LEA, "Not Specified", "No Category Codes", "No Category Codes", count, indicator, "Derived"]


# Every stored grade occurs (the importer requires that, as a dropped 'Grade 13' is the #976 shape).
# ELEM has a blank grade → not compared; MID: 100+110+120 (Adult Education excluded) == 330;
# HIGH: 50+51+52+53+2+4 + a 'Not Specified' residual of 1 == 213.
MEMB_MID_G7 = 12


def _membership():
    return [
        # a Category Set A detail row, the kind the importer must ignore
        [YEAR, ELEM, LEA, "Grade 1", "Asian", "Female", "3", CAT_A, "Reported"],
        _sub4(ELEM, "Pre-Kindergarten", "10"),
        _sub4(ELEM, "Kindergarten", "40"),
        _sub4(ELEM, "Grade 1", "41", "Manual adjustment"),
        _sub4(ELEM, "Grade 2", "", "Suppressed"),            # blank with a flag: stays NULL
        _sub4(ELEM, "Grade 3", "42"),
        _sub4(ELEM, "Grade 4", "43"),
        _sub4(ELEM, "Grade 5", "44"),
        _sub4(ELEM, "Not Specified", "0", "Derived"),
        _total(ELEM, "220", EUT_MINUS),
        _total(ELEM, "220", EUT),
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
        [YEAR, LEA, "Teachers", "52.00", "Derived - Major Staffing Category", "Reported"],
        [YEAR, LEA, "Elementary Teachers", "20.50", "Category Set A", "Reported"],
    ]


def _csv_bytes(header, rows) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def build_year(root: Path, *, directory=None, staff=None, membership=None, lea=None,
               membership_as_zip=True, staff_as_zip=False) -> dict:
    """Write a year directory under `root` and return a manifest that pins every file."""
    d = root / YEAR.replace("-", "_")
    d.mkdir(parents=True, exist_ok=True)
    files = {}

    def put(name, data, as_zip):
        if as_zip:
            p = d / (name + ".zip")
            with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(name + ".csv", data)
        else:
            p = d / (name + ".csv")
            p.write_bytes(data)
        files[p.name] = p

    put("ccd_sch_029_2425_w_1a_073025", _csv_bytes(DIR_COLS, _directory() if directory is None else directory), False)
    put("ccd_sch_059_2425_l_1a_073025", _csv_bytes(STAFF_COLS, _staff() if staff is None else staff), staff_as_zip)
    put("ccd_sch_052_2425_l_1a_073025", _csv_bytes(MEMB_COLS, _membership() if membership is None else membership),
        membership_as_zip)
    put("ccd_lea_059_2425_l_1a_073025", _csv_bytes(LEA_COLS, _lea() if lea is None else lea), False)
    return {"source": "nces-ccd", "base": "x", "years": {YEAR: [
        {"file": n, "bytes": p.stat().st_size, "sha256": source_manifest.sha256_file(p), "url": "u"}
        for n, p in files.items()]}}


# ------------------------------------------------------------------------------------------------- happy path
def test_loads_every_directory_school_verbatim(tmp_path):
    manifest = build_year(tmp_path)
    rows, details = m.load_year(YEAR, tmp_path, manifest)
    by = {r["ncessch"]: r for r in rows}
    assert set(by) == {ELEM, MID, HIGH}
    e = by[ELEM]
    assert (e["leaid"], e["state"], e["level"], e["gslo"], e["gshi"]) == (LEA, "AL", "Elementary", "KG", "05")
    assert e["teachers_fte"] == 20.5 and e["teachers_dms_flag"] == "Reported"
    assert (e["memb_pk"], e["memb_kg"], e["memb_01"], e["memb_05"]) == (10, 40, 41, 44)
    assert e["memb_02"] is None                      # blank stays NULL, never 0
    assert e["memb_06"] is None                      # a grade the school has no row for
    assert e["membership_flags"] == {"Grade 1": "Manual adjustment", "Grade 2": "Suppressed"}
    mid = by[MID]
    assert mid["teachers_fte"] is None and mid["teachers_dms_flag"] == "Missing"
    assert (mid["memb_06"], mid["memb_07"], mid["memb_08"]) == (100, 110, 120)
    assert mid["membership_flags"] is None
    h = by[HIGH]
    assert h["teachers_fte"] == 30.0 and h["membership_flags"] is None
    assert (h["memb_09"], h["memb_13"], h["memb_ug"], h["memb_kg"]) == (50, 2, 4, None)
    assert all(r["source_year"] == YEAR for r in rows)
    for fid in ("029", "052", "059"):
        assert {r[f"src_{fid}_sha256"] for r in rows} == {details["sources"][fid][1]}
        assert len(details["sources"][fid][1]) == 64
    assert details["membership_reconciliation"]["n_compared"] == 2      # MID + HIGH; ELEM has a blank grade
    assert details["membership_reconciliation"]["n_disagree"] == 0
    assert details["grade_not_specified_students"] == 1                 # HIGH's residual, counted not stored
    assert "memb_ns" not in h and "Not Specified" not in (h["membership_flags"] or {})
    cov = details["lea_coverage"]
    assert cov["school_teachers_fte"] == 50.5 and cov["lea_teachers_fte"] == 52.0
    assert cov["leas_compared"] == 1 and cov["leas_within_5pct"] == 1


def test_reads_the_csv_when_present_else_the_zip_member(tmp_path):
    manifest = build_year(tmp_path, staff_as_zip=True)
    paths = m.locate(YEAR, tmp_path)
    assert paths["059"].suffix == ".zip" and paths["029"].suffix == ".csv" and paths["052"].suffix == ".zip"
    rows, _ = m.load_year(YEAR, tmp_path, manifest)
    assert len(rows) == 3


def test_locate_refuses_an_ambiguous_or_absent_file(tmp_path):
    build_year(tmp_path)
    d = tmp_path / "2024_25"
    (d / "ccd_sch_059_2425_l_2a_073025.csv").write_bytes(b"x")
    with pytest.raises(DataGuardError, match="exactly one ccd_sch_059"):
        m.locate(YEAR, tmp_path)
    (d / "ccd_sch_059_2425_l_2a_073025.csv").unlink()
    (d / "ccd_sch_059_2425_l_1a_073025.csv").unlink()
    with pytest.raises(DataGuardError, match="exactly one ccd_sch_059"):
        m.locate(YEAR, tmp_path)


# ------------------------------------------------------------------------------------------------- manifest pins
def test_refuses_a_file_the_manifest_does_not_declare(tmp_path):
    manifest = build_year(tmp_path)
    manifest["years"][YEAR] = [e for e in manifest["years"][YEAR] if "052" not in e["file"]]
    with pytest.raises(DataGuardError, match="not declared .* pin it"):
        m.load_year(YEAR, tmp_path, manifest)


def test_refuses_a_file_whose_bytes_drifted_from_the_pin(tmp_path):
    manifest = build_year(tmp_path)
    p = tmp_path / "2024_25" / "ccd_sch_059_2425_l_1a_073025.csv"
    p.write_bytes(p.read_bytes().replace(b"20.50", b"20.51"))
    with pytest.raises(DataGuardError, match="is not the pinned 2024-25 file"):
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


def test_refuses_an_unknown_059_flag_and_029_level(tmp_path):
    staff = _staff()
    staff[0][6] = "Reported (est.)"
    with pytest.raises(DataGuardError, match="059 DMS_FLAG.*outside the known vocabulary"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))
    directory = _directory()
    directory[0][7] = "Primary"
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


# ------------------------------------------------------------------------------------------------- A2: CRC
def test_refuses_a_member_whose_crc_fails(tmp_path):
    manifest = build_year(tmp_path, membership_as_zip=False)
    d = tmp_path / "2024_25"
    csv_path = d / "ccd_sch_052_2425_l_1a_073025.csv"
    data = csv_path.read_bytes()
    csv_path.unlink()
    zip_path = d / "ccd_sch_052_2425_l_1a_073025.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        z.writestr(csv_path.name, data)
    raw = zip_path.read_bytes()
    assert raw.count(b"No Category Codes") >= 1
    zip_path.write_bytes(raw.replace(b"No Category Codes", b"No Category Codex", 1))   # payload edited, CRC not
    entry = next(e for e in manifest["years"][YEAR] if "052" in e["file"])
    entry.update(file=zip_path.name, bytes=zip_path.stat().st_size, sha256=source_manifest.sha256_file(zip_path))
    with pytest.raises(zipfile.BadZipFile, match="CRC"):
        m.load_year(YEAR, tmp_path, manifest)


# ------------------------------------------------------------------------------------------------- A2: 0 rows
def test_write_year_refuses_zero_rows_before_deleting(tmp_path):
    session = MagicMock()
    with pytest.raises(DataGuardError, match="matched 0 rows"):
        m.write_year(session, YEAR, [], {"sources": {}})
    session.execute.assert_not_called()


def test_an_empty_directory_is_refused(tmp_path):
    manifest = build_year(tmp_path, directory=[])
    with pytest.raises(DataGuardError):
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


def test_refuses_a_school_outside_the_directory_or_with_another_leaid(tmp_path):
    staff = _staff() + [[YEAR, "019999900001", LEA, "Ghost", "1.0", EUT, "Reported"]]
    with pytest.raises(DataGuardError, match="059 staff: 1 school.* not in the 029 directory"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))
    staff = _staff()
    staff[2][2] = "0100006"
    with pytest.raises(DataGuardError, match="059 staff: 1 school.* different LEAID"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, staff=staff))


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


def test_lea_coverage_refuses_the_wrong_lea_vocabulary(tmp_path):
    lea = [[YEAR, LEA, "Teachers", "52.00", "Education Unit Total", "Reported"]]
    with pytest.raises(DataGuardError, match="LEA 059 TOTAL_INDICATOR.*never seen"):
        m.load_year(YEAR, tmp_path, build_year(tmp_path, lea=lea))


# ------------------------------------------------------------------------------------------------- write
def test_write_year_replaces_the_year_in_chunks_and_logs_lineage(monkeypatch):
    monkeypatch.setattr(m, "INSERT_CHUNK", 2)
    session = MagicMock()
    rows = [{"ncessch": str(i), "source_year": YEAR} for i in range(5)]
    details = {"sources": {"029": ["a.csv", "x"], "052": ["b.zip", "y"], "059": ["c.csv", "z"]}}
    assert m.write_year(session, YEAR, rows, details) == 5
    calls = session.execute.call_args_list
    assert "DELETE FROM ccd_school_staffing" in str(calls[0].args[0].compile())
    assert [len(c.args[1]) for c in calls[1:]] == [2, 2, 1]
    lineage = session.add.call_args.args[0]
    assert (lineage.entity_type, lineage.entity_id, lineage.operation) == ("ccd_school_staffing", YEAR, "import")
    assert lineage.source_file == "a.csv, b.zip, c.csv" and lineage.details is details


def test_dry_run_never_opens_a_session(monkeypatch, tmp_path):
    manifest = build_year(tmp_path)
    monkeypatch.setattr(m, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(m.source_manifest, "load", lambda source: manifest)
    opened = MagicMock()

    @contextmanager
    def scope():
        opened()
        yield MagicMock()
    monkeypatch.setattr(m, "session_scope", scope)
    m.main(["--year", YEAR, "--dry-run"])
    opened.assert_not_called()
    m.main(["--year", YEAR])
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
