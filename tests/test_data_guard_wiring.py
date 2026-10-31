"""#981: the guards must be WIRED, not merely defined. A verifier replaced reconcile_total and
require_labels_seen with no-ops and the fast gate still passed 2586 green — the guard functions were
tested in isolation (tests/test_data_guards.py) and never through the code that calls them. Every test
here drives a PRODUCTION entry point with an input shaped like the failure it guards against, and asserts
the DataGuardError (a SystemExit) escapes. DB-free: fake sessions where a session is needed.

Covers: import_sped_baseline (#970 shape, #975 header/preamble, #982 missing Total + unknown label, G2
personnel), import_staff_and_enrollment (#976 per-LEA cap), apply_sped_estimates (G4 + COVID refusal),
merge_sea_precedence (#984 per-state SEA year), enhance_sped_with_sea_data (#983 fl.year), MA (#977),
NY (#978), rebuild_database phase 5 (#985), and the import-after-shim rule (#987).
"""

from __future__ import annotations

import ast
import csv
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy.sql.elements import TextClause

from infrastructure.utilities.data_guards import DataGuardError

REPO = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------------------- fakes
class FakeResult(list):
    def fetchall(self):
        return list(self)


class FakeSession:
    """Answers every execute() with the rows given, in order; records the SQL it was asked."""

    def __init__(self, *results):
        self._results = list(results)
        self.sql: list[str] = []
        self.params: list[dict] = []

    def execute(self, clause, params=None):
        self.sql.append(str(clause.text if isinstance(clause, TextClause) else clause))
        self.params.append(params or {})
        return FakeResult(self._results.pop(0) if self._results else [])


# ----------------------------------------------------------------------------- import_sped_baseline
HEADERS = ["Year", "State Name", "SEA Education Environment", "SEA Disability Category", "Age 3 to 5", "Ages 6-21"]


def _row(env, a35, a621, state="Alabama", year="2017", dis="All Disabilities"):
    return [year, state, env, dis, a35, a621]


def _good_rows(state="Alabama"):
    return [
        _row("Inside regular class 80% or more of the day", "-", "600", state),
        _row("Inside regular class 40% through 79% of the day", "-", "200", state),
        _row("Inside regular class less than 40% of the day", "-", "100", state),
        _row("Separate School, Age 6-21", "-", "50", state),
        _row("Residential Facility, Age 6-21", "-", "10", state),
        _row("Homebound/Hospital", "-", "20", state),
        _row("Correctional Facilities", "-", "5", state),
        _row("Parentally Placed in Private Schools", "-", "15", state),
        _row("Total, Age 6-21", "-", "1000", state),
        _row("Separate Class", "30", "-", state),
        _row("Services in Regular Early Childhood Program (attend at least 10 hours)", "70", "-", state),
        _row("Total, Age 3-5", "100", "-", state),
    ]


class TestChildCountGuardsAreWired:
    def test_happy_path_parses(self):
        from infrastructure.database.migrations.import_sped_baseline import parse_child_count_rows
        assert parse_child_count_rows(HEADERS, _good_rows(), "2017")["AL"]["ages_6_21"] == 1000

    def test_970_shape_total_row_summed_in_fails_as_the_signature(self):
        """Revert #970 in data: a Total row that is the env sum ×2 → G1 reports 2.000× (the signature)."""
        from infrastructure.database.migrations.import_sped_baseline import parse_child_count_rows
        rows = [r for r in _good_rows() if r[2] != "Total, Age 6-21"] + [_row("Total, Age 6-21", "-", "500")]
        with pytest.raises(DataGuardError, match="2.000×.*#970"):
            parse_child_count_rows(HEADERS, rows, "2017")

    def test_970_label_drift_fails_g2(self):
        """The file spells 'Separate School' bare (as #970's parser expected) → the parser's label is never seen."""
        from infrastructure.database.migrations.import_sped_baseline import parse_child_count_rows
        rows = [(_row("Separate School", "-", "50") if r[2] == "Separate School, Age 6-21" else r) for r in _good_rows()]
        with pytest.raises(DataGuardError, match=r"\['Separate School, Age 6-21'\]"):
            parse_child_count_rows(HEADERS, rows, "2017")

    def test_975_missing_header_fails_instead_of_falling_back_to_an_index(self):
        from infrastructure.database.migrations.import_sped_baseline import parse_child_count_rows
        headers = HEADERS[:-1] + ["School Age"]   # the 2024-25 relabel
        with pytest.raises(DataGuardError, match=r"header row.*\['Ages 6-21'\]"):
            parse_child_count_rows(headers, _good_rows(), "2017")

    def test_975_header_row_is_found_by_content_not_preamble_length(self, tmp_path):
        """A 5-row preamble (the 2024-25 layout) and a 4-row one both parse to the same totals."""
        from infrastructure.database.migrations.import_sped_baseline import read_child_count_file
        for n_preamble in (4, 5, 7):
            p = tmp_path / f"cc_{n_preamble}.csv"
            with p.open("w", newline="") as f:
                w = csv.writer(f)
                for i in range(n_preamble):
                    w.writerow([f"meta {i}", ""] + [""] * 4)
                w.writerow(HEADERS)
                w.writerows(_good_rows())
            assert read_child_count_file(p, "2017")["AL"]["self_contained"] == 150

    def test_975_no_header_row_fails_loud(self, tmp_path):
        from infrastructure.database.migrations.import_sped_baseline import read_child_count_file
        p = tmp_path / "cc.csv"
        p.write_text("\n".join(["a,b"] * 30))
        with pytest.raises(DataGuardError, match="no header row"):
            read_child_count_file(p, "2017")

    def test_982_state_with_suppressed_total_fails_instead_of_parsing_to_zero(self):
        from infrastructure.database.migrations.import_sped_baseline import parse_child_count_rows
        rows = _good_rows() + [(_row("Total, Age 6-21", "-", "*", "California") if r[2] == "Total, Age 6-21" else
                                _row(r[2], r[4], r[5], "California")) for r in _good_rows()]
        with pytest.raises(DataGuardError, match="CA.*nothing to reconcile"):
            parse_child_count_rows(HEADERS, rows, "2017")

    def test_982_unclassified_environment_label_is_a_parse_error(self):
        from infrastructure.database.migrations.import_sped_baseline import parse_child_count_rows
        # an EXTRA school-age setting the parser has never heard of (all known labels still present)
        rows = _good_rows() + [_row("Inside regular class 80% or more of the day (School Age)", "-", "600")]
        with pytest.raises(DataGuardError, match="does not classify.*School Age"):
            parse_child_count_rows(HEADERS, rows, "2017")


PERSONNEL_HEADERS = ["Year", "State", "Personnel Type", "Teachers Fully Certified/Paraprofessionals Qualified",
                     "Teachers Not Fully Certified/\nParaprofessionals Not Qualified", "Teachers/Paraprofessionals Total"]


class TestPersonnelGuardsAreWired:
    def test_happy_path(self):
        from infrastructure.database.migrations.import_sped_baseline import parse_personnel_rows
        rows = [["2017", "Alabama", "Special Education Teachers for Ages 6-21", "100", "10", "110"],
                ["2017", "Alabama", "Special Education Paraprofessionals for Ages 6-21", "50", "5", "55"]]
        out = parse_personnel_rows(PERSONNEL_HEADERS, rows, "2017")
        assert out["AL"]["teachers_total"] == 110 and out["AL"]["paras_total"] == 55

    def test_relabelled_type_fails_g2(self):
        """The 2023-24 personnel file says 'School Age' — must be a parse error, not zero teachers."""
        from infrastructure.database.migrations.import_sped_baseline import parse_personnel_rows
        rows = [["2023", "Alabama", "Special Education Teachers for School Age", "100", "10", "110"]]
        with pytest.raises(DataGuardError, match="personnel 2023 types"):
            parse_personnel_rows(PERSONNEL_HEADERS, rows, "2023")

    def test_missing_header_fails(self):
        from infrastructure.database.migrations.import_sped_baseline import parse_personnel_rows
        with pytest.raises(DataGuardError, match="header row"):
            parse_personnel_rows(["Year", "State", "Personnel Type", "a", "b", "c"], [], "2017")


# ----------------------------------------------------------------------------- import_staff_and_enrollment
def _mini_ccd(path: Path, leas: dict[str, dict[str, int]], *, total_override: dict[str, int] | None = None):
    """A membership CSV with per-grade detail rows + the file's own 'Education Unit Total' per LEA."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["LEAID", "TOTAL_INDICATOR", "GRADE", "RACE_ETHNICITY", "SEX", "STUDENT_COUNT"])
        for leaid, grades in leas.items():
            for grade, n in grades.items():
                w.writerow([leaid, "Category Set A - By Race/Ethnicity; Sex; Grade", grade, "White", "Male", n])
            w.writerow([leaid, "Education Unit Total", "Not Specified", "No Category Codes", "Not Specified",
                        (total_override or {}).get(leaid, sum(grades.values()))])


class TestCcdG1IsWiredAndEnforcesRows:
    LEAS = {"0100001": {"Kindergarten": 50, "Grade 1": 60, "Grade 13": 3},
            "0100002": {"Grade 9": 100, "Grade 10": 90}}

    def test_reconciled_file_loads(self, tmp_path):
        from infrastructure.database.migrations.import_staff_and_enrollment import load_enrollment_data
        p = tmp_path / "m.csv"
        _mini_ccd(p, self.LEAS)
        df = load_enrollment_data(p, "2024-25")
        assert df.set_index("district_id")["enrollment_total"].to_dict() == {"0100001": 113, "0100002": 190}

    def test_976_a_dropped_grade_category_fails_on_the_row_count_not_the_aggregate(self, tmp_path, monkeypatch):
        """Dropping 'Grade 13' from the mapping moves ONE LEA by 3 students (ratio 0.99 — inside the 0.5%
        aggregate tolerance? no: 300/303; make it inside) — the row cap must catch what the ratio cannot."""
        import infrastructure.database.migrations.import_staff_and_enrollment as m
        leas = {"0100001": {"Kindergarten": 5000, "Grade 1": 6000, "Grade 13": 3},
                "0100002": {"Grade 9": 10000, "Grade 10": 9000}}
        p = tmp_path / "m.csv"
        _mini_ccd(p, leas)
        monkeypatch.setitem(m.GRADE_MAPPING, "Grade 13", None)
        monkeypatch.delitem(m.GRADE_MAPPING, "Grade 13")
        with pytest.raises(DataGuardError, match="1 of 2 rows disagree.*#976"):
            m.load_enrollment_data(p, "2024-25")

    def test_970_signature_on_ccd(self, tmp_path):
        from infrastructure.database.migrations.import_staff_and_enrollment import load_enrollment_data
        p = tmp_path / "m.csv"
        _mini_ccd(p, self.LEAS, total_override={"0100001": 226, "0100002": 380})   # file total = 2× ours? no: ours = half
        with pytest.raises(DataGuardError):
            load_enrollment_data(p, "2024-25")


# ----------------------------------------------------------------------------- apply_sped_estimates
class TestApplySpedEstimatesGuardsAreWired:
    def test_covid_year_is_refused_without_a_db(self):
        from infrastructure.database.migrations.apply_sped_estimates import select_year_totals
        with pytest.raises(DataGuardError, match="COVID-excluded"):
            select_year_totals(None, "2021-22")

    def test_empty_year_selection_fails_before_any_write(self, monkeypatch):
        import infrastructure.database.migrations.apply_sped_estimates as m
        monkeypatch.setattr(m, "select_year_totals", lambda session, year: [])
        monkeypatch.setattr(m, "available_years", lambda session: {"enrollment_by_grade": ["2024-25"]})
        with pytest.raises(DataGuardError, match="matched 0 rows.*2024-25"):
            m.apply_estimates(None, "2019-20x", {}, {}, {}, {}, {}, {})


# ----------------------------------------------------------------------------- merge_sea_precedence
class TestMergeSeaYearGuardIsWired:
    def test_984_declared_year_the_table_does_not_carry_fails_loud(self):
        from infrastructure.database.migrations.merge_sea_precedence import load_sea_staff_data
        s = FakeSession([], [("2025-26",)])        # SELECT ... WHERE year = :year → nothing; DISTINCT year → 2025-26
        with pytest.raises(DataGuardError, match=r"ma_staff_data rows for year=2024-25.*2025-26"):
            load_sea_staff_data(s, "MA", "ma_staff_data", "2024-25")
        assert "year = :year" in s.sql[0] and s.params[0] == {"year": "2024-25"}

    def test_984_rows_for_the_declared_year_load(self):
        from infrastructure.database.migrations.merge_sea_precedence import load_sea_staff_data
        s = FakeSession([("0100001", 12.5, "2024-25")])
        out = load_sea_staff_data(s, "MA", "ma_staff_data", "2024-25")
        assert out == {"0100001": {"teachers_fte": 12.5, "year": "2024-25"}}

    def test_984_every_state_query_is_year_keyed(self):
        import infrastructure.database.migrations.merge_sea_precedence as m
        src = ast.parse(Path(m.__file__).read_text())
        bodies = [n.value for n in ast.walk(src) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                  and "SELECT nces_id" in n.value]
        assert len(bodies) == len(m.SEA_STATES) and all("year = :year" in b for b in bodies)


# ----------------------------------------------------------------------------- enhance_sped_with_sea_data
class TestEnhanceFlYearGuardIsWired:
    def test_983_join_is_keyed_on_fl_year_and_empty_fails(self):
        from infrastructure.database.migrations.enhance_sped_with_sea_data import update_fl_sped_estimates
        s = FakeSession([], [("2024-25",)], [("2024-25",)])
        with pytest.raises(DataGuardError, match="fl_staff_data.*2024-25"):
            update_fl_sped_estimates(s, year="2023-24", dry_run=True)
        assert "fl.year = :year" in s.sql[0]


# ----------------------------------------------------------------------------- Massachusetts (#977)
class TestMassachusettsEnrollmentYearIsSelectedNotRelabelled:
    def test_sy_is_derived_from_the_vintage(self):
        from infrastructure.database.migrations.import_massachusetts_data import dese_sy_for
        assert dese_sy_for("2025-26") == 2026 and dese_sy_for("2026-27") == 2027

    def test_977_rows_follow_the_requested_vintage(self, monkeypatch, tmp_path):
        import infrastructure.database.migrations.import_massachusetts_data as m
        export = pd.DataFrame({"SY": [2026, 2027, 2027], "ORG_TYPE": ["District"] * 3,
                               "DIST_CODE": [35, 35, 0], "TOTAL_CNT": [100, 110, 999]})
        f = tmp_path / "e.xlsx"
        f.write_bytes(b"")
        monkeypatch.setattr(m, "ENROLLMENT_FILE", f)
        monkeypatch.setattr(m.pd, "read_excel", lambda *a, **k: export)
        monkeypatch.setattr(m, "ENROLLMENT_DATA_YEAR", "2026-27")
        df = m.load_enrollment_data()
        assert df["SY"].tolist() == [2027] and df["TOTAL_CNT"].tolist() == [110]

    def test_977_vintage_absent_from_the_export_fails_loud(self, monkeypatch, tmp_path):
        import infrastructure.database.migrations.import_massachusetts_data as m
        export = pd.DataFrame({"SY": [2026], "ORG_TYPE": ["District"], "DIST_CODE": [35], "TOTAL_CNT": [100]})
        f = tmp_path / "e.xlsx"
        f.write_bytes(b"")
        monkeypatch.setattr(m, "ENROLLMENT_FILE", f)
        monkeypatch.setattr(m.pd, "read_excel", lambda *a, **k: export)
        monkeypatch.setattr(m, "ENROLLMENT_DATA_YEAR", "2024-25")
        with pytest.raises(DataGuardError, match=r"SY 2025 \(2024-25\).*\[2026\]"):
            m.load_enrollment_data()


# ----------------------------------------------------------------------------- New York (#978)
class TestNewYorkYearDrivesFilesSheetsAndStamp:
    def test_paths_are_derived_from_the_year(self):
        from infrastructure.database.migrations.import_new_york_data import workbook_paths
        staff, enr, sped = workbook_paths("2024-25")
        assert (staff.name, enr.name, sped.name) == (
            "ny_staffing_2024_25.xlsx", "ny_enrollment_district_2024_25.xlsx", "ny_enrollment_sped_2024_25.xlsx")

    @pytest.mark.parametrize("bad", ["garbage", "2021-22", "2023-25", "", None])
    def test_malformed_or_covid_year_is_refused(self, bad):
        from infrastructure.database.migrations.import_new_york_data import validate_source_year
        with pytest.raises(DataGuardError):
            validate_source_year(bad)

    def test_missing_sheet_for_the_year_fails_instead_of_loading_nothing(self, monkeypatch, tmp_path):
        import infrastructure.database.migrations.import_new_york_data as m
        wb = tmp_path / "ny_enrollment_district_2024_25.xlsx"
        pd.DataFrame({"a": [1]}).to_excel(wb, sheet_name="public-district-2023-24", index=False)
        monkeypatch.setattr(m, "SOURCE_YEAR", "2024-25")
        with pytest.raises(DataGuardError, match="no sheet 'public-district-2024-25'.*public-district-2023-24"):
            m.read_district_sheet(wb, label="NYSED enrollment workbook")

    def test_staff_sheet_reporting_another_year_fails(self, monkeypatch, tmp_path):
        import infrastructure.database.migrations.import_new_york_data as m
        wb = tmp_path / "ny_staffing_2024_25.xlsx"
        pd.DataFrame({"REPORT_SCHOOL_YEAR": ["2023-24"], "FTE": [1.0]}).to_excel(wb, sheet_name="STAFF_RATIOS", index=False)
        monkeypatch.setattr(m, "SOURCE_YEAR", "2024-25")
        monkeypatch.setattr(m, "STAFF_FILE", wb)
        with pytest.raises(DataGuardError, match=r"reports school year\(s\) \['2023-24'\], not.*2024-25"):
            m.load_staff_data()

    def test_missing_workbook_fails(self, monkeypatch, tmp_path):
        import infrastructure.database.migrations.import_new_york_data as m
        monkeypatch.setattr(m, "STAFF_FILE", tmp_path / "absent.xlsx")
        with pytest.raises(DataGuardError, match="not found"):
            m.load_staff_data()


# ----------------------------------------------------------------------------- rebuild_database (#985)
def test_985_phase_5_forwards_the_rebuild_year(monkeypatch):
    import infrastructure.scripts.rebuild_database as rb
    seen = {}

    def fake_run(script, args=None, dry_run=False):
        seen["args"] = args
        return True
    monkeypatch.setattr(rb, "run_script", fake_run)
    assert rb.phase_5_sped_estimates(False, "2023-24") is True
    assert seen["args"] == ["--year", "2023-24"]


# ----------------------------------------------------------------------------- import-after-shim (#987)
@pytest.mark.parametrize("rel", [
    "infrastructure/scripts/analyze/compare_sea_vs_federal_lct.py",
    "infrastructure/scripts/utilities/generate_sea_integration.py",
])
def test_987_project_imports_come_after_the_sys_path_shim(rel):
    tree = ast.parse((REPO / rel).read_text())
    shim = next(n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
                and ast.unparse(n.func) == "sys.path.insert")
    first_project_import = min(n.lineno for n in tree.body if isinstance(n, ast.ImportFrom)
                               and (n.module or "").startswith("infrastructure"))
    assert shim < first_project_import, f"{rel}: project import at line {first_project_import} precedes the shim at {shim}"
