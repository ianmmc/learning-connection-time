"""#934 — pandas 2 vs pandas 3: does the LCT database come out IDENTICAL? (rerunnable, READ-ONLY)

Compares every public table of two LCT databases row-for-row (row multisets, every column cast to text),
excluding only volatile columns (serial ids, *_at timestamps, run ids). Intended inputs: two scratch
clones rebuilt by `rebuild_database.py` (+ `calculate_lct_variants.py`) under pandas 2 and pandas 3.
NEVER point this at a rebuild target you care about — it only reads, but the rebuild that feeds it truncates.

    python3 docs/technical-notes/production-quality-control-research/2026-10-28-issue934-pandas3-db-parity-measure.py DB_A DB_B

Check-map (#954 made every verdict a function of the state, not of the sweep's shape):
  C0  NOTHING MEASURED (exit 2) when A and B are the same database — a self-comparison is always "parity"
  C1  every table in the UNION of both schemas has the same row multiset in A and B; a table or column present
      on only one side is a DIFF, never skipped
  C2  per column, on BOTH sides and regardless of whether the column differs: counts of NULL vs the literal text
      'NaN'/'nan'/'None' — the axis that decides #934. The text 'NaN' present on both sides is reported as a
      WARN (equal, but wrong on both). A CSV round-trip CANNOT see this (read_csv parses 'NaN' back to NaN),
      which is how the first comparison on 2026-10-09 wrongly reported "identical"
  C3  NOTHING MEASURED (exit 2) on the DECIDING axis: `lct_calculations.instructional_minutes_year` must hold
      rows on both sides — since #941 aborts rebuild_database.py at Phase 6, an empty lct_calculations is the
      DEFAULT state of a half-run clone, and it used to print PARITY
  C4  NOTHING MEASURED (exit 2) if no table holds a row on either side

Findings (2026-10-09/10-28, scratch clones; re-verified 2026-10-29 after #954, feat/934 branch):
  - before the #934 fix: phases 1-5 identical; lct_calculations.instructional_minutes_year NULL 160,370 ->
    TEXT 'NaN' 160,370 under pandas 3 (to_dict hands pandas 3's string-dtype NaN to the driver).
  - after the fix (calculate_lct_variants -> infrastructure/utilities/frames.db_records(keep_numeric_nan=True)),
    pandas 2.3.3 vs pandas 3.1.0, full rebuild + LCT on identical inputs: C1 PARITY, 23 populated common tables
    (lct_calculations 160,916 rows). #940's 559 numeric-NaN lct_value rows are reported as a typed C2 WARN on
    both sides (numeric NaN, not the #934 text class).
  Proofs that every verdict is reachable (#954): A==B -> C0 exit 2; a clone with the text 'NaN' written back
  into 160,370 rows vs the clean clone -> C1 DIFF exit 1 with the C2 NULL->'NaN' line; a governance-schema
  clone vs an LCT clone -> every table 'only in A/B' then C3 (deciding axis absent) exit 2; a
  `postgresql+psycopg://` DATABASE_URL override -> runs (driver stripped). ~85 lct_value rows differing between
  a psycopg2-written table and a post-#931 rebuild are the DRIVER's float->numeric cast (#952), not pandas.
"""
import re
import sys
import psycopg
from sqlalchemy.engine import make_url

from infrastructure.database.connection import get_database_url

VOLATILE = re.compile(r"(^id$|_at$|^run_id$|timestamp|^output_files$)", re.I)   # created_by etc. are NOT volatile
TEXT_MISSING = ("NaN", "nan", "None")


def _url(db: str) -> str:
    """libpq form for psycopg.connect: the resolver passes a DATABASE_URL override through verbatim, so a
    `postgresql+psycopg://` override must have its +driver stripped here (#945/#954)."""
    return make_url(get_database_url()).set(drivername="postgresql", database=db).render_as_string(hide_password=False)


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
    if a == b:
        print(f"== C0 NOTHING MEASURED — {a!r} compared with itself")
        return 2
    ca, cb = psycopg.connect(_url(a)), psycopg.connect(_url(b))

    types = {}

    def schema(con):
        out = {}
        for t, c, dt in con.execute("select table_name, column_name, data_type from information_schema.columns "
                                    "where table_schema='public' order by table_name, ordinal_position"):
            out.setdefault(t, []).append(c)
            types[(t, c)] = dt
        return out
    sa, sb = schema(ca), schema(cb)
    populated = differing = 0
    warns = []
    for t in sorted(set(sa) | set(sb)):
        if t not in sa or t not in sb:
            differing += 1
            print(f"DIFF {t:32s} table only in {'A' if t in sa else 'B'}")
            continue
        cols_a, cols_b = set(sa[t]), set(sb[t])
        if cols_a != cols_b:
            differing += 1
            print(f"DIFF {t:32s} columns only in A: {sorted(cols_a - cols_b)} | only in B: {sorted(cols_b - cols_a)}")
            continue
        keep = [c for c in sa[t] if not VOLATILE.search(c)]
        if not keep:
            continue
        ra, rb = _rows(ca, t, keep), _rows(cb, t, keep)
        if not ra and not rb:
            continue
        populated += 1
        col_diffs = []
        for i, c in enumerate(keep):
            va, vb = _volatile_json(c, ra, i), _volatile_json(c, rb, i)
            texts = {m: (va.count(m), vb.count(m)) for m in TEXT_MISSING}
            if any(n for pair in texts.values() for n in pair):
                # a NUMERIC column reads 'NaN' through ::text too — that is #940's numeric NaN, not #934's text
                numeric = types.get((t, c), "") in ("numeric", "double precision", "real", "integer", "bigint")
                label = "numeric NaN stored (#940)" if numeric else "missing-as-TEXT present (#934 class)"
                warns.append(f"    C2 WARN {t}.{c}: {label} — " +
                             " ".join(f"'{m}' A={x} B={y}" for m, (x, y) in texts.items() if x or y))
            if va != vb:
                col_diffs.append(f"    C2 {c}: NULL {va.count(None)}->{vb.count(None)} | " +
                                 " ".join(f"'{m}' {x}->{y}" for m, (x, y) in texts.items()))
        same = len(ra) == len(rb) and not col_diffs
        differing += not same
        print(f"{'SAME' if same else 'DIFF'} {t:32s} rows {len(ra):>7}/{len(rb):<7}")
        print("\n".join(col_diffs)) if col_diffs else None
    for w in warns:
        print(w)
    if populated == 0 and differing == 0:
        print("== C4 NOTHING MEASURED — no populated table on either side (wrong database names?)")
        return 2
    axis = []
    for name, con in (("A", ca), ("B", cb)):
        try:
            axis.append(con.execute("select count(*) from lct_calculations where instructional_minutes_year is not null "
                                    "or instructional_minutes_year is null").fetchone()[0])
        except psycopg.Error:
            axis.append(None)
    if not all(axis):
        print(f"== C3 NOTHING MEASURED on the deciding axis — lct_calculations rows A={axis[0]} B={axis[1]} "
              f"(run calculate_lct_variants on both clones; #941 aborts the rebuild before it)")
        return 2
    verdict = "PARITY" if differing == 0 else f"{differing} TABLE(S) DIFFER"
    print(f"== C1 {populated} populated common tables: {verdict}  ({a} vs {b}; lct_calculations rows A={axis[0]} B={axis[1]})")
    return 0 if differing == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
