"""G3 (#972 generalization): no hand-typed school-year literal may act as a CURRENCY default in
operational code. "Current" is spelled NCES_PRIMARY_YEAR (infrastructure/utilities/school_year.py).

A literal that names a FIXED source vintage (the 2017-18 SPED baseline, the year of a SEA workbook on
disk) is legitimate — but it must be DECLARED in arch-manifest.json `data_year_literals.exemptions`
with a reason, so that the review surface is the manifest edit, not a silent default. Both ways:
an undeclared literal fails; a declared one that no longer matches fails (stale exemption).

Scope follows the manifest's `scan` section (infrastructure/, scripts/). Matched forms:
  - argparse defaults:          default="2023-24" / default='2023-24'
  - ORM / SQL comparisons:      == '2023-24'   ·   = '2023-24' inside text(...)
  - keyword vintages:           year="2023-24", source_year=..., fiscal_year=..., estimate_year=...,
                                effective_year=..., baseline_year=...
  - sheet / path selectors:     sheet_name="...2023-24..."
  - module constants:           SOURCE_YEAR = "2023-24" (the indirection vector)
Help strings, comments and docstrings are not matched (they carry no behaviour).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((REPO / "arch-manifest.json").read_text(encoding="utf-8"))
SECTION = MANIFEST["data_year_literals"]

YEAR = r"20\d\d-\d\d"
PATTERNS = [
    re.compile(rf"""default\s*=\s*["']({YEAR})["']"""),
    re.compile(rf"""==\s*["']({YEAR})["']"""),
    re.compile(rf"""(?<![:\w])=\s*'({YEAR})'"""),                      # raw-SQL  col = '2023-24'
    re.compile(rf"""\b(?:year|source_year|fiscal_year|estimate_year|effective_year|baseline_year)\s*=\s*["']({YEAR})["']"""),
    re.compile(rf"""sheet_name\s*=\s*["'][^"']*({YEAR})[^"']*["']"""),
    re.compile(rf"""^\s*[A-Z_]*YEAR[A-Z_]*\s*=\s*["']({YEAR})["']"""),   # module constant (the indirection vector)
]
COMMENT_OR_DOC = re.compile(r"^\s*#")


def _scanned_files():
    excluded = set(MANIFEST["scan"]["excluded_dirs"])
    for root in MANIFEST["scan"]["python_roots"]:
        for p in sorted((REPO / root).rglob("*.py")):
            if (set(p.parts) & excluded) or p.name.startswith("test_"):   # test modules carry fixture years
                yield from ()
            else:
                yield p


def _hits():
    """(relpath, lineno, literal, line) for every behavioural year literal in scope."""
    out = []
    for p in _scanned_files():
        in_doc = False
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if line.count('"""') % 2 == 1:
                in_doc = not in_doc
                continue
            if in_doc or COMMENT_OR_DOC.match(line):
                continue
            code = line.split("  #", 1)[0]
            for pat in PATTERNS:
                m = pat.search(code)
                if m:
                    out.append((str(p.relative_to(REPO)), i, m.group(1), line.strip()))
                    break   # one hit per line, whichever pattern matched first
    return out


def _exempt(rel: str, literal: str) -> bool:
    return any(e["file"] == rel and e["literal"] == literal for e in SECTION["exemptions"])


def test_section_schema():
    assert SECTION["exemptions"], "data_year_literals.exemptions emptied — the baseline/SEA-vintage declarations would vanish"
    for e in SECTION["exemptions"]:
        assert {"file", "literal", "why"} <= set(e), f"exemption incomplete: {e}"
        assert re.fullmatch(YEAR, e["literal"]), f"exemption literal is not a school year: {e}"
        assert (REPO / e["file"]).exists(), f"exemption names a file that does not exist: {e['file']}"
        assert len(e["why"]) > 20, f"exemption needs a real reason: {e}"


def test_scanner_sees_the_known_baseline_literals():
    """A measurement that cannot fail is not a verdict: the scanner must find the one 2017-18 baseline
    literal that is KNOWN to be in the tree (SPED_BASELINE_YEAR), or it is not scanning."""
    hits = _hits()
    assert any(f.endswith("utilities/school_year.py") and lit == "2017-18" for f, _, lit, _ in hits), \
        f"scanner did not find SPED_BASELINE_YEAR = '2017-18' in school_year.py — NOTHING MEASURED (hits={len(hits)})"


def test_no_undeclared_hand_typed_year():
    undeclared = [(f, n, lit, line) for f, n, lit, line in _hits() if not _exempt(f, lit)]
    assert not undeclared, (
        "Hand-typed school-year literal(s) acting as behaviour in operational code. Use "
        "NCES_PRIMARY_YEAR for 'current', or declare a FIXED source vintage in arch-manifest.json "
        "data_year_literals.exemptions with a reason:\n  " +
        "\n  ".join(f"{f}:{n}  {lit!r}  {line}" for f, n, lit, line in undeclared)
    )


@pytest.mark.parametrize("exemption", SECTION["exemptions"], ids=lambda e: f"{e['file']}:{e['literal']}")
def test_every_exemption_still_matches_a_literal(exemption):
    """A declared exemption whose literal is gone is stale: delete it (or it hides a future regression)."""
    hits = {(f, lit) for f, _, lit, _ in _hits()}
    assert (exemption["file"], exemption["literal"]) in hits, \
        f"stale exemption: {exemption['file']} no longer carries {exemption['literal']!r} as behaviour"
