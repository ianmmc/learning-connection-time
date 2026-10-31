"""#996: ONE reader for the CCD membership 'Education Unit Total' rows, carrying BOTH hard-won guards -
strip the indicator (#308) and dedupe on LEAID (#427: a duplicate LEAID Cartesian-multiplies a join).

merge_nces_files spelled the dedupe inline and import_staff_and_enrollment's G1 reconciliation re-read the row
with only the strip, so a duplicate total row would have multiplied its join and inflated n_compared."""
import csv

import pandas as pd

from infrastructure.utilities.common import ccd_education_unit_totals


def _membership(rows):
    return pd.DataFrame(rows, columns=["LEAID", "TOTAL_INDICATOR", "STUDENT_COUNT"])


def test_helper_strips_the_indicator_and_keeps_only_total_rows():
    df = _membership([
        ("0100001", " Education Unit Total ", 10),
        ("0100001", "Category Set A - By Race/Ethnicity; Sex; Grade", 4),
        ("0100002", "Education Unit Total", 20),
    ])
    out = ccd_education_unit_totals(df)
    assert out.set_index("LEAID")["STUDENT_COUNT"].to_dict() == {"0100001": 10, "0100002": 20}


def test_helper_dedupes_on_leaid_keeping_first():
    df = _membership([
        ("0100001", "Education Unit Total", 10),
        ("0100001", "Education Unit Total", 99),
        ("0100002", "Education Unit Total", 20),
    ])
    out = ccd_education_unit_totals(df)
    assert out["LEAID"].is_unique
    assert out.set_index("LEAID")["STUDENT_COUNT"].to_dict() == {"0100001": 10, "0100002": 20}


def _write_ccd(path, duplicate_total_for=None):
    leas = {"0100001": {"Kindergarten": 50, "Grade 1": 60}, "0100002": {"Grade 9": 100, "Grade 10": 90}}
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["LEAID", "TOTAL_INDICATOR", "GRADE", "RACE_ETHNICITY", "SEX", "STUDENT_COUNT"])
        for leaid, grades in leas.items():
            for grade, n in grades.items():
                w.writerow([leaid, "Category Set A - By Race/Ethnicity; Sex; Grade", grade, "White", "Male", n])
            w.writerow([leaid, "Education Unit Total", "Not Specified", "No Category Codes", "Not Specified",
                        sum(grades.values())])
            if leaid == duplicate_total_for:
                w.writerow([leaid, "Education Unit Total", "Not Specified", "No Category Codes", "Not Specified",
                            sum(grades.values())])


def test_g1_reconciliation_does_not_multiply_on_a_duplicate_total_row(tmp_path, capsys):
    """The G1 join must compare each LEA once: 2 LEAs, not 3, when one LEA's total row is duplicated."""
    from infrastructure.database.migrations.import_staff_and_enrollment import load_enrollment_data
    p = tmp_path / "m.csv"
    _write_ccd(p, duplicate_total_for="0100001")
    df = load_enrollment_data(p, "2024-25")
    assert len(df) == 2
    assert "2 LEAs compared" in capsys.readouterr().out


def test_indicator_selects_a_different_row_not_a_respelling():
    """#1001: the SPED baseline's K-12 denominator is the 'minus Adult Education' row; it goes through
    the same strip + dedupe, and never matches the plain Education Unit Total."""
    from infrastructure.utilities.common import EDUCATION_UNIT_TOTAL_MINUS_ADULT
    df = pd.DataFrame({
        "LEAID": ["0100001", "0100001", "0100001", "0100002"],
        "TOTAL_INDICATOR": ["Education Unit Total", f" {EDUCATION_UNIT_TOTAL_MINUS_ADULT} ",
                            EDUCATION_UNIT_TOTAL_MINUS_ADULT, EDUCATION_UNIT_TOTAL_MINUS_ADULT],
        "STUDENT_COUNT": [110, 100, 999, 50],
        "ST": ["AL", "AL", "AL", "AL"],
    })
    out = ccd_education_unit_totals(df, indicator=EDUCATION_UNIT_TOTAL_MINUS_ADULT,
                                    columns=("LEAID", "STUDENT_COUNT", "ST"))
    assert out.set_index("LEAID")["STUDENT_COUNT"].to_dict() == {"0100001": 100, "0100002": 50}
    assert list(out.columns) == ["LEAID", "STUDENT_COUNT", "ST"]
