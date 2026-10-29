"""DataFrame -> database rows, through ONE function (#934).

A missing value must reach the driver as `None` (SQL NULL), never as a float NaN. Under pandas 3 a missing
string is NaN (the default `str` dtype), and `to_dict('records')` passes it straight through: measured, the LCT
calculation wrote the TEXT 'NaN' into 160,370 of 160,916 `lct_calculations` rows (rebuilt scratch clone,
2026-10-09/28) that pandas 2 left NULL. Every DataFrame
that is written to the database goes through `db_records`.
"""
import numpy as np
import pandas as pd


def _py(value):
    if value is None:
        return None
    if pd.api.types.is_scalar(value) and pd.isna(value):     # NaN, pd.NA, NaT — every missing form
        return None
    if isinstance(value, np.generic):                         # np.int64 / np.float64 / np.bool_ -> python
        return value.item()
    return value


def db_records(df: pd.DataFrame, *, keep_numeric_nan: bool = False) -> list[dict]:
    """`df.to_dict('records')`, except every missing value is `None` and numpy scalars are plain Python.

    `keep_numeric_nan=True` passes float NaN through in float-typed columns — pandas 2's existing DB-write
    behaviour, kept ONLY until #940 decides what a numeric NaN (e.g. an uncomputable lct_value, a NOT NULL
    column) should become. Remove the flag with #940; never add a new caller of it."""
    cols = list(df.columns)
    keep = {c for c in cols if keep_numeric_nan and pd.api.types.is_float_dtype(df[c].dtype)}
    return [{c: (v if c in keep and isinstance(v, float) and v != v else _py(v)) for c, v in zip(cols, row)}
            for row in df.astype(object).itertuples(index=False, name=None)]
