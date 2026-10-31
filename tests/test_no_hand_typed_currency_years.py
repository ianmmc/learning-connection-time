"""G3 (#972 generalization): no hand-typed school-year literal may act as behaviour in operational code
without being DECLARED. "Current" is spelled NCES_PRIMARY_YEAR (infrastructure/utilities/school_year.py).

A literal that names a FIXED source vintage (the 2017-18 SPED baseline, the year of a SEA workbook on
disk, a download catalog key) is legitimate — but it must be declared in arch-manifest.json
`data_year_literals.exemptions` with a reason AND its occurrence count, so that the review surface is
the manifest edit, not a silent default. Both ways: an undeclared (file, literal) fails; a declared one
whose count no longer matches fails — a NEW site under an already-declared literal (the #980 hole: a
(file, literal) key blessed every future site in the file) and a stale exemption alike.

The scan is AST-based (#980; repo precedent tests/test_frames.py): every `ast.Constant` whose value is
exactly a school year (`20YY-YY`) is behaviour — a default, a filter value, a dict value, a VALUES
literal, a sheet-name piece, an annotated-parameter default, a module constant. Docstrings and bare
string statements are not behaviour and are skipped; comments never reach the AST. Longer strings that
merely CONTAIN a year (help text, log lines, paths) are not exact matches and are not scanned — they
carry no behaviour either.

Scope follows the manifest's `scan` section (infrastructure/, scripts/); test modules are skipped
by name (they carry fixture years).
"""

from __future__ import annotations

import ast
import functools
import json
import re
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((REPO / "arch-manifest.json").read_text(encoding="utf-8"))
SECTION = MANIFEST["data_year_literals"]

YEAR = re.compile(r"^20\d\d-\d\d$")


def _scanned_files():
    excluded = set(MANIFEST["scan"]["excluded_dirs"])
    for root in MANIFEST["scan"]["python_roots"]:
        for p in sorted((REPO / root).rglob("*.py")):
            if not (set(p.parts) & excluded) and not p.name.startswith("test_"):
                yield p


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """ids of Constant nodes that are docstrings / bare string statements (not behaviour)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out.add(id(node.value))
    return out


@functools.lru_cache(maxsize=1)
def _hits() -> tuple[tuple[str, int, str], ...]:
    """(relpath, lineno, literal) for every behavioural school-year literal in scope. Cached — the
    parametrized exemption test alone calls it once per declaration."""
    out = []
    for p in _scanned_files():
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        skip = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and YEAR.match(node.value) and id(node) not in skip):
                out.append((str(p.relative_to(REPO)), node.lineno, node.value))
    return tuple(out)


def _counts() -> Counter:
    return Counter((f, lit) for f, _, lit in _hits())


def _declared() -> dict[tuple[str, str], int]:
    return {(e["file"], e["literal"]): e["count"] for e in SECTION["exemptions"]}


def test_section_schema():
    assert SECTION["exemptions"], "data_year_literals.exemptions emptied — the baseline/SEA-vintage declarations would vanish"
    seen = set()
    for e in SECTION["exemptions"]:
        assert {"file", "literal", "count", "why"} <= set(e), f"exemption incomplete: {e}"
        assert YEAR.match(e["literal"]), f"exemption literal is not a school year: {e}"
        assert (REPO / e["file"]).exists(), f"exemption names a file that does not exist: {e['file']}"
        assert isinstance(e["count"], int) and e["count"] >= 1, f"exemption count must be a positive int: {e}"
        assert len(e["why"]) > 20, f"exemption needs a real reason: {e}"
        key = (e["file"], e["literal"])
        assert key not in seen, f"duplicate exemption for {key} — merge them into one count"
        seen.add(key)


def test_scanner_sees_the_known_baseline_literal():
    """A measurement that cannot fail is not a verdict: the scanner must find the one 2017-18 baseline
    literal that is KNOWN to be in the tree (SPED_BASELINE_YEAR), or it is not scanning."""
    hits = _hits()
    assert any(f.endswith("utilities/school_year.py") and lit == "2017-18" for f, _, lit in hits), \
        f"scanner did not find SPED_BASELINE_YEAR = '2017-18' in school_year.py — NOTHING MEASURED (hits={len(hits)})"


def test_scanner_sees_the_forms_the_regex_version_missed():
    """#980: the forms the line-regex scanner was blind to must be hits for the AST scanner."""
    src = '''
def f(year: str = "2023-24"):           # annotated default
    q = text("""
        SELECT 1 WHERE y = '2023-24'
    """)                                  # multi-line SQL body (the triple-quote toggle skipped it)
    d = {"year": "2023-24"}               # dict value
    g = cfg.get("year", "2023-24")        # .get default
    """Docstring with '2023-24' is NOT behaviour."""
    return q, d, g
'''
    tree = ast.parse(src)
    skip = _docstring_nodes(tree)
    found = [n.value for n in ast.walk(tree)
             if isinstance(n, ast.Constant) and isinstance(n.value, str) and YEAR.match(n.value) and id(n) not in skip]
    # the SQL body is a longer string (not an exact year) — a year INSIDE text() must be a bound
    # parameter, which the raw-SQL scan in tests/test_stage6_dispatch_bridge.py covers; here: 3 exact literals
    assert found == ["2023-24", "2023-24", "2023-24"]


def test_no_undeclared_hand_typed_year():
    undeclared = sorted(set(_counts()) - set(_declared()))
    detail = [(f, n, lit) for f, n, lit in _hits() if (f, lit) in set(undeclared)]
    assert not undeclared, (
        "Hand-typed school-year literal(s) acting as behaviour in operational code. Use "
        "NCES_PRIMARY_YEAR for 'current', or declare a FIXED source vintage in arch-manifest.json "
        "data_year_literals.exemptions with its count and a reason:\n  " +
        "\n  ".join(f"{f}:{n}  {lit!r}" for f, n, lit in detail)
    )


@pytest.mark.parametrize("exemption", SECTION["exemptions"], ids=lambda e: f"{e['file']}:{e['literal']}")
def test_every_exemption_matches_its_declared_count(exemption):
    """Both directions (#980): a NEW site of a declared literal raises the count (declare it on purpose);
    a removed site lowers it (delete or trim the exemption, or it hides a future regression)."""
    key = (exemption["file"], exemption["literal"])
    actual = _counts().get(key, 0)
    assert actual == exemption["count"], (
        f"{exemption['file']} carries {exemption['literal']!r} as behaviour {actual}× but the manifest "
        f"declares {exemption['count']}× — "
        + ("stale exemption" if actual < exemption["count"] else "an UNDECLARED new site; review it, then bump the count")
        + ":\n  " + "\n  ".join(f"line {n}" for f, n, lit in _hits() if (f, lit) == key)
    )
