"""#934 — a DataFrame becomes DB rows through ONE function, and a missing value always lands as SQL NULL.

Measured under pandas 3: `calculate_lct_variants` wrote the TEXT 'NaN' into 160,370 of 160,916 `lct_calculations`
rows (instructional_minutes_year; rebuilt scratch clone, 2026-10-09/28) where pandas 2 wrote NULL. pandas 3's
default `str` dtype represents a missing
string as float NaN; `to_dict('records')` hands that NaN to the driver, which stores it in a text column as
'NaN'. No error, no warning — and `read_csv` parses the text back to NaN, so a CSV round-trip hides it."""
import math

import numpy as np
import pandas as pd

from infrastructure.utilities.frames import db_records


def _frame():
    return pd.DataFrame({
        "year": pd.Series(["2024-25", None], dtype="str"),       # pandas 3's default for strings
        "obj": pd.Series(["a", None], dtype=object),
        "f": [1.5, np.nan],
        "i": pd.array([7, pd.NA], dtype="Int64"),
        "t": [pd.Timestamp("2026-01-02"), pd.NaT],
        "b": pd.array([True, pd.NA], dtype="boolean"),
    })


def test_every_missing_form_becomes_none():
    rows = db_records(_frame())
    assert rows[1] == {"year": None, "obj": None, "f": None, "i": None, "t": None, "b": None}


def test_present_values_are_plain_python_and_unchanged():
    row = db_records(_frame())[0]
    assert row["year"] == "2024-25" and row["obj"] == "a" and row["f"] == 1.5
    assert row["i"] == 7 and row["b"] is True and row["t"] == pd.Timestamp("2026-01-02")
    # the driver must never see numpy scalars (np.int64 does not adapt cleanly)
    assert type(row["i"]) is int and type(row["f"]) is float and type(row["b"]) is bool


def test_no_nan_survives_anywhere():
    for row in db_records(_frame()):
        for v in row.values():
            assert not (isinstance(v, float) and math.isnan(v)), row


def test_empty_frame():
    assert db_records(pd.DataFrame({"a": []})) == []


def test_keep_numeric_nan_reproduces_pandas2_db_writes_exactly():
    """#934's narrow fix (#940 pending): missing NON-numeric values -> None (what pandas 2's object dtype
    gave), numeric NaN passes through untouched (pandas 2's existing behaviour, tracked in #940)."""
    rows = db_records(_frame(), keep_numeric_nan=True)
    missing = rows[1]
    assert missing["year"] is None and missing["obj"] is None and missing["t"] is None
    assert isinstance(missing["f"], float) and math.isnan(missing["f"])
    assert rows[0] == db_records(_frame())[0]                  # present values identical either way


def test_no_production_code_bypasses_db_records():
    """The ONE-function rule, enforced: a DataFrame reaches the database only via `db_records`. A bare
    `to_dict('records')` / `to_sql(` in production code is the path that wrote 'NaN' text under pandas 3."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for top in ("infrastructure", "tools", "scripts"):
        for path in (root / top).rglob("*.py"):
            if "node_modules" in path.parts or path.name == "frames.py":
                continue
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                args = [a.value for a in node.args if isinstance(a, ast.Constant)] + \
                       [k.value.value for k in node.keywords if k.arg == "orient" and isinstance(k.value, ast.Constant)]
                if (node.func.attr == "to_dict" and "records" in args) or node.func.attr == "to_sql":
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} .{node.func.attr}(...)")
    assert not offenders, "route through infrastructure.utilities.frames.db_records:\n  " + "\n  ".join(offenders)
