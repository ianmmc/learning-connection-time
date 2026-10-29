"""#944 — can psycopg 3's server-side binding PREPARE every raw SQL statement in production code? (rerunnable)

psycopg2 interpolated parameters client-side; psycopg 3 sends them separately and Postgres must TYPE each one
at plan time. A string parameter is sent as `unknown`, so a parameter that only ever meets a VARIADIC "any"
function (CONCAT, FORMAT, ...) cannot be typed: `IndeterminateDatatype: could not determine data type of
parameter $N`. #931's regex scan looked for `:p IS NULL` and parameters in DDL/SET and missed exactly that
(`enhance_sped_with_sea_data.py` — green on --dry-run, which runs only the SELECT; the real run raised).

This sweep extracts every `text("...")` literal in `infrastructure/` by AST and asks Postgres itself to
PREPARE it — a plan, never an execution — with the types psycopg 3 would send: `unknown` for a scalar,
`text[]` for a parameter used with `ANY(...)`. A statement that cannot be planned against the governance DB
is retried against the LCT DB (two schemas, two databases). Both targets must be THROWAWAY clones: PREPARE
executes nothing, but this script must never be the thing that touches a live DB by habit.

    GOVERNANCE_DB_NAME=gov_scratch POSTGRES_DB=lct_scratch \\
    python3 docs/technical-notes/production-quality-control-research/2026-10-29-issue944-psycopg3-prepare-sweep-measure.py

Check-map:
  C1  FINDING — PREPARE fails with IndeterminateDatatype on both targets (the #944 class; fix: CAST(:p AS text))
  C2  NOT MEASURABLE — the literal is an f-string (SQL assembled at runtime) or an expanding `IN :p`;
      counted, listed, never silently skipped. A literal with NO bind parameter (DDL, a server_default
      fragment, a bare SELECT) is counted separately: psycopg 3 binds nothing there, so nothing can be untyped
  C3  NOT MEASURABLE — undefined relation/column on BOTH targets (a TEMP table or a test-only schema)
  C4  OTHER planner error on both targets — reported verbatim (a real bug or a sweep limitation; decide)
  C5  NOTHING MEASURED if zero statements reached a PREPARE on any target

Findings (2026-10-29, feat/930 branch, gov_scratch_944 (schema-only clone) + lct_rb_p2): 208 statements prepared
OK, 109 parameter-free, 74 not measurable (f-string / name / expanding IN), 0 findings AFTER the #944 CAST fix.
Proof the sweep can fail: with the CAST reverted it reports exactly that statement as C1 (lct target:
IndeterminateDatatype; governance target: UndefinedTable — one target finding it is the verdict).
"""
import ast
import os
import re
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[3]
PARAM = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")          # :name, not ::cast
ANY_PARAM = re.compile(r"ANY\s*\(\s*:([A-Za-z_]\w*)\s*\)", re.I)
IN_EXPANDING = re.compile(r"\bIN\s+:([A-Za-z_]\w*)", re.I)


def _literals():
    """(file:line, sql, is_fstring) for every text(<literal>) call under infrastructure/."""
    for path in sorted((ROOT / "infrastructure").rglob("*.py")):
        if "node_modules" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "text"
                    and node.args):
                continue
            arg = node.args[0]
            where = f"{path.relative_to(ROOT)}:{node.lineno}"
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                yield where, arg.value, False
            elif isinstance(arg, ast.JoinedStr):
                yield where, "".join(v.value for v in arg.values if isinstance(v, ast.Constant)), True
            # a name/attribute (text(QUERY)) is a literal defined elsewhere — out of this sweep's reach, counted as C2
            elif isinstance(arg, (ast.Name, ast.Attribute)):
                yield where, "", True


def _to_prepare(sql: str):
    """Rewrite :name -> $k and declare each parameter's type the way psycopg 3 would send it."""
    anys = set(ANY_PARAM.findall(sql))
    order, types = [], []
    def sub(m):
        name = m.group(1)
        if name not in order:
            order.append(name)
            types.append("text[]" if name in anys else "unknown")
        return f"${order.index(name) + 1}"
    body = PARAM.sub(sub, sql)
    return body, types


def _url(db_env: str, default_db: str) -> str:
    from infrastructure.database.connection import get_database_url
    from urllib.parse import urlsplit, urlunsplit
    u = urlsplit(get_database_url())
    return urlunsplit(u._replace(path="/" + os.environ.get(db_env, default_db)))


def main() -> int:
    targets = {"governance": _url("GOVERNANCE_DB_NAME", "governance"), "lct": _url("POSTGRES_DB", "learning_connection_time")}
    for name, url in targets.items():
        if url.rsplit("/", 1)[-1].split("?")[0] in ("governance", "learning_connection_time"):
            print(f"REFUSING: target '{name}' resolves to a LIVE database name; point it at a throwaway clone")
            return 2
    cons = {name: psycopg.connect(url, autocommit=False) for name, url in targets.items()}
    findings, unmeasurable, other, measured, no_params = [], [], [], 0, 0
    for i, (where, sql, is_f) in enumerate(_literals()):
        if is_f or IN_EXPANDING.search(sql):
            unmeasurable.append((where, "f-string / name / expanding IN"))
            continue
        if not PARAM.search(sql):
            no_params += 1          # DDL, fragments, bare SELECTs: psycopg 3 binds nothing, so nothing to type
            continue
        body, types = _to_prepare(sql)
        errs = {}
        for name, con in cons.items():
            try:
                with con.transaction():
                    con.execute(f"PREPARE sweep_{i}({', '.join(types)}) AS {body}" if types else f"PREPARE sweep_{i} AS {body}")
                    con.execute(f"DEALLOCATE sweep_{i}")
                errs = {}
                break
            except psycopg.Error as e:
                errs[name] = (type(e).__name__, str(e).splitlines()[0])
        kinds = {k for k, _ in errs.values()}
        if not errs:
            measured += 1
        elif "IndeterminateDatatype" in kinds:
            # ONE target reaching the typing error is the finding — the other target usually lacks the table
            # (two schemas), which is why "all targets agree" would hide it (it did, on the first proof run)
            findings.append((where, errs))
        elif kinds <= {"UndefinedTable", "UndefinedColumn", "UndefinedFunction", "UndefinedObject"}:
            unmeasurable.append((where, f"C3 {errs}"))
        else:
            other.append((where, errs))
    for c in cons.values():
        c.close()
    print(f"== statements: {measured} prepared OK | {len(findings)} C1 findings | {no_params} parameter-free (not at risk) "
          f"| {len(unmeasurable)} not measurable | {len(other)} other")
    for w, e in findings:
        print(f"C1 FINDING  {w}: {e}")
    for w, e in other:
        print(f"C4 OTHER    {w}: {e}")
    for w, why in unmeasurable:
        print(f"C2/C3 n/m   {w}: {why}")
    if measured == 0 and not findings:
        print("== C5 NOTHING MEASURED — no statement reached a PREPARE on any target")
        return 2
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
