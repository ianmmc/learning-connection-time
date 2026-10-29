"""#934 — the LCT calculation's DataFrame becomes DB rows through ONE function, and a missing value lands as
SQL NULL (scope narrowed by #956: the SEA/NCES importers write through their own converters, outside this).

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
    # astype(object) already yields builtins; this pins that nothing re-wraps them
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


def test_956_object_cells_pass_through_unwrapped():
    """The deleted `.item()` branch: a numpy scalar already in an object cell reaches the driver as itself
    (psycopg 3 adapts it — measured on bigint/double/boolean/numeric/text), and an object-cell
    np.datetime64[ns] is no longer silently turned into an epoch-nanoseconds int (it now fails LOUDLY at the
    driver, 'cannot adapt type datetime64', instead of storing garbage into a bigint column)."""
    import numpy as np
    df = pd.DataFrame({"o": pd.Series([np.int64(5), np.datetime64("2026-01-02T00:00:00.000000006")], dtype=object)})
    rows = db_records(df)
    assert rows[0]["o"] == 5
    assert not isinstance(rows[1]["o"], int) and isinstance(rows[1]["o"], (np.datetime64, pd.Timestamp))


def test_956_the_lct_calculation_is_wired_through_db_records():
    """The narrowed claim, as a wiring pin: the ONE production caller builds its rows via db_records and never
    via to_dict / iterrows / itertuples — a bypass test on to_dict('records') alone passed with
    `to_dict(orient=VAR)` and `[dict(r) for _, r in df.iterrows()]`."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "infrastructure/scripts/analyze/calculate_lct_variants.py").read_text()
    tree = ast.parse(src)
    calls = [n.func for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert any(isinstance(f, ast.Name) and f.id == "db_records" for f in calls)
    attrs = {f.attr for f in calls if isinstance(f, ast.Attribute)}
    # the DB write builds from `results_list`; row-materialisers may exist for CSV/report paths, but the
    # write itself must not use them — pin the write call's argument by name
    write = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "write_calculations_to_db")
    assert isinstance(write.args[1], ast.Name) and write.args[1].id == "results_list"
    assign = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "results_list" for t in n.targets))
    assert isinstance(assign.value, ast.Call) and getattr(assign.value.func, "id", "") == "db_records"
    assert "to_sql" not in attrs


def test_no_production_code_bypasses_db_records():
    """No production file materialises DataFrame rows for a DB write behind db_records' back: any `.to_dict(`
    whose orient is 'records' or NOT a literal, and any `.to_sql(`, is an offender. Exempt by EXACT path
    (#956: `path.name == 'frames.py'` exempted any file with that basename)."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for top in ("infrastructure", "tools", "scripts"):
        for path in (root / top).rglob("*.py"):
            if "node_modules" in path.parts or path.relative_to(root) == Path("infrastructure/utilities/frames.py"):
                continue
            for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue
                if node.func.attr == "to_sql":
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} .to_sql(...)")
                    continue
                if node.func.attr != "to_dict":
                    continue
                orient = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "orient"), None)
                if orient is None:          # bare .to_dict(): orient defaults to 'dict' (a column map), not rows
                    continue
                literal = orient.value if isinstance(orient, ast.Constant) else None
                if literal == "records" or literal is None:     # 'records', or an orient we cannot read
                    offenders.append(f"{path.relative_to(root)}:{node.lineno} .to_dict({ast.unparse(orient)})")
    assert not offenders, "route through infrastructure.utilities.frames.db_records:\n  " + "\n  ".join(offenders)
