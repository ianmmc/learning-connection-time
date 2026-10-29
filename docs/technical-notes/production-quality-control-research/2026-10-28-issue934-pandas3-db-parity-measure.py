"""#934 — pandas 2 vs pandas 3: does the LCT database come out IDENTICAL? (rerunnable, READ-ONLY)

Compares every public table of two LCT databases row-for-row (row multisets, every column cast to text),
excluding only volatile columns (serial ids, *_at timestamps, run ids). Intended inputs: two scratch
clones rebuilt by `rebuild_database.py` (+ `calculate_lct_variants.py`) under pandas 2 and pandas 3.
NEVER point this at a rebuild target you care about — it only reads, but the rebuild that feeds it truncates.

    python3 docs/technical-notes/production-quality-control-research/2026-10-28-issue934-pandas3-db-parity-measure.py DB_A DB_B

Check-map:
  C1  every populated table has the same row multiset in A and B (the parity verdict)
  C2  per differing column: NULL vs literal 'NaN'/'nan'/'None' counts — the axis that decides #934.
      A CSV round-trip CANNOT see this (read_csv parses the text 'NaN' back to NaN), which is how the
      first comparison on 2026-10-09 wrongly reported "identical".
  C3  NOTHING MEASURED if no table holds a row in either DB (a wrong-DB / empty-sweep bug, not a pass)

Findings (2026-10-09/10-28, scratch clones of learning_connection_time, 54 tables):
  - before the fix: phases 1-5 identical; lct_calculations.instructional_minutes_year NULL 160,370 ->
    TEXT 'NaN' 160,370 under pandas 3 (to_dict hands pandas 3's string-dtype NaN to the driver).
  - after the fix (calculate_lct_variants -> infrastructure/utilities/frames.db_records(keep_numeric_nan=True)),
    pandas 2.3.3 vs pandas 3.1.0, full rebuild + LCT on identical inputs: C1 PARITY, 19 populated tables
    (lct_calculations 160,916 rows). pandas 2 before-fix vs after-fix: lct_calculations identical (only
    calculation_runs gains the new run's row). #940's 559 numeric-NaN lct_value rows unchanged in all three.
"""
import hashlib
import re
import sys
from urllib.parse import urlsplit, urlunsplit

import psycopg

from infrastructure.database.connection import get_database_url

VOLATILE = re.compile(r"(^id$|_at$|^run_id$|timestamp|^created|^updated|^imported|^loaded|^output_files$)", re.I)
TEXT_MISSING = ("NaN", "nan", "None")


def _url(db: str) -> str:
    u = urlsplit(get_database_url())
    return urlunsplit(u._replace(path="/" + db))


def _rows(con, table, cols):
    sel = ", ".join(f'"{c}"::text' for c in cols)
    rows = con.execute(f'select {sel} from "{table}"').fetchall()
    return sorted(rows, key=lambda r: tuple("" if v is None else v for v in r))


def _volatile_json(col: str, rows, i):
    # calculation_runs.qa_summary embeds per-run timestamps; strip them before comparing
    if col != "qa_summary":
        return [r[i] for r in rows]
    stamp = re.compile(r"\d{8}T\d{6}Z|\d{4}-\d{2}-\d{2}[T ][\d:.]+[^\"]*")
    return [stamp.sub("", r[i] or "") for r in rows]


def main(a: str, b: str) -> int:
    ca, cb = psycopg.connect(_url(a)), psycopg.connect(_url(b))
    tables = [r[0] for r in ca.execute(
        "select table_name from information_schema.tables where table_schema='public' "
        "and table_type='BASE TABLE' order by 1")]
    populated = differing = 0
    for t in tables:
        cols = [r[0] for r in ca.execute(
            "select column_name from information_schema.columns where table_schema='public' "
            "and table_name=%s order by ordinal_position", (t,))]
        keep = [c for c in cols if not VOLATILE.search(c)]
        if not keep:
            continue
        ra, rb = _rows(ca, t, keep), _rows(cb, t, keep)
        if not ra and not rb:
            continue
        populated += 1
        col_diffs = []
        for i, c in enumerate(keep):
            va, vb = _volatile_json(c, ra, i), _volatile_json(c, rb, i)
            if va != vb:
                nulls = f"NULL {va.count(None)}->{vb.count(None)}"
                text = " ".join(f"'{m}' {va.count(m)}->{vb.count(m)}" for m in TEXT_MISSING)
                col_diffs.append(f"    C2 {c}: {nulls} | {text}")
        same = len(ra) == len(rb) and not col_diffs
        differing += not same
        print(f"{'SAME' if same else 'DIFF'} {t:32s} rows {len(ra):>7}/{len(rb):<7}")
        print("\n".join(col_diffs)) if col_diffs else None
    if populated == 0:
        print("== C3 NOTHING MEASURED — no populated table in either DB (wrong database names?)")
        return 2
    verdict = "PARITY" if differing == 0 else f"{differing} TABLE(S) DIFFER"
    print(f"== C1 {populated} populated tables of {len(tables)}: {verdict}  ({a} vs {b})")
    return 0 if differing == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
