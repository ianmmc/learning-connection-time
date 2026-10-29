"""DataFrame -> database rows for the LCT calculation's write path (#934, narrowed by #956).

A missing value must reach the driver as `None` (SQL NULL), never as a float NaN. Under pandas 3 a missing
string is NaN (the default `str` dtype), and `to_dict('records')` passes it straight through: measured, the LCT
calculation wrote the TEXT 'NaN' into 160,370 of 160,916 `lct_calculations` rows (rebuilt scratch clone,
2026-10-09/28) that pandas 2 left NULL.

Scope — what the guard in tests/test_frames.py actually enforces: `calculate_lct_variants` builds its DB rows
ONLY through `db_records`, and no production file calls `to_dict('records')` / `to_sql`. The SEA/NCES importers
under infrastructure/database/migrations/ write DataFrame cells through their own per-row converters
(`sea_import_utils.safe_*`, `row.get()` into ORM objects) and are OUTSIDE this function — they replay
identically on pandas 2.3.3 vs 3.1.0 on the real raw files, and their numeric-NaN behaviour is #940's.
"""
import pandas as pd


def _py(value):
    # `astype(object)` already yields Python builtins / pandas scalars for every dtype (measured over 28 dtypes,
    # #956); psycopg 3 adapts a numpy scalar that does reach it. A `.item()` branch here was dead under the
    # pinned driver and turned an object-cell np.datetime64[ns] into an epoch-nanoseconds int — deleted.
    if value is None or (pd.api.types.is_scalar(value) and pd.isna(value)):   # NaN, pd.NA, NaT — every missing form
        return None
    return value


def db_records(df: pd.DataFrame, *, keep_numeric_nan: bool = False) -> list[dict]:
    """`df.to_dict('records')`, except every missing value is `None` and numpy scalars are plain Python.

    `keep_numeric_nan=True` passes float NaN through in FLOAT-DTYPED columns — pandas 2's existing DB-write
    behaviour, kept ONLY until #940 decides what a numeric NaN (e.g. an uncomputable lct_value, a NOT NULL
    column) should become. It keys off the column dtype at call time: a float column that arrived as object
    (pandas 3 turns float64 into object on `concat` with an empty `DataFrame(columns=...)`) is NOT kept and its
    NaN becomes None — measured, not reachable from the sole caller. Remove the flag with #940; never add a
    new caller of it."""
    cols = list(df.columns)
    keep = {c for c in cols if keep_numeric_nan and pd.api.types.is_float_dtype(df[c].dtype)}
    return [{c: (v if c in keep and isinstance(v, float) and v != v else _py(v)) for c, v in zip(cols, row)}
            for row in df.astype(object).itertuples(index=False, name=None)]
