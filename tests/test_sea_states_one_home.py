"""#990: the per-state SEA vintage registry (`SEA_STATES`) has ONE home, `sea_import_utils.py`.

merge_sea_precedence and compare_sea_vs_federal_lct each spelled their own copy and disagreed on MA (merge
2024-25, compare 2025-26). They now import the one registry; the importers' own vintage constants are pinned
to it member for member, so a re-stamp that moves an importer without the registry fails here."""
import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MIG = REPO / "infrastructure/database/migrations"

YEAR = re.compile(r"20\d\d-\d\d")


def _registry():
    from infrastructure.database.migrations.sea_import_utils import SEA_STATES
    return SEA_STATES


def test_registry_lives_in_sea_import_utils_and_covers_the_nine_states():
    assert sorted(_registry()) == ["CA", "FL", "IL", "MA", "MI", "NY", "PA", "TX", "VA"]


def test_merge_and_compare_use_the_one_registry_object():
    from infrastructure.database.migrations import merge_sea_precedence as merge
    from infrastructure.scripts.analyze import compare_sea_vs_federal_lct as compare
    assert merge.SEA_STATES is _registry()
    assert compare.SEA_STATES is _registry()


@pytest.mark.parametrize("path", [
    MIG / "merge_sea_precedence.py",
    REPO / "infrastructure/scripts/analyze/compare_sea_vs_federal_lct.py",
])
def test_no_second_spelling_of_the_registry(path):
    """The consumers IMPORT the registry; assigning `SEA_STATES = ...` (or any year-keyed dict) there is the drift."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assigned = [t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
                for t in n.targets if isinstance(t, ast.Name)]
    assert "SEA_STATES" not in assigned
    years = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
             and isinstance(n.value, str) and YEAR.fullmatch(n.value)]
    assert years == [], f"{path.name} spells vintages itself: {years}"


def test_ma_staff_and_enrollment_vintages_are_distinct_and_explicit():
    ma = _registry()["MA"]
    assert ma["year"] == "2024-25"          # DESE teacher export
    assert ma["enroll_year"] == "2025-26"   # E2C Hub enrollment export (a year ahead)


def test_ma_enrollment_is_queried_at_its_own_vintage():
    """compare applied ONE year to both MA tables; the enrollment export is a year ahead of the staff file."""
    from infrastructure.scripts.analyze import compare_sea_vs_federal_lct as compare
    seen = []

    class S:
        def execute(self, q, params=None):
            seen.append((str(q), dict(params or {})))
            return []

    compare.get_sea_data(S(), "MA", _registry()["MA"])
    by_table = {("ma_staff_data" if "ma_staff_data" in q else "ma_enrollment_data"): p["year"] for q, p in seen}
    assert by_table == {"ma_staff_data": "2024-25", "ma_enrollment_data": "2025-26"}


def _module_constants(path):
    """{NAME: value} for module-level `NAME = '20YY-YY'`."""
    out = {}
    for n in ast.parse(path.read_text(encoding="utf-8")).body:
        if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str) and YEAR.fullmatch(n.value.value)):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = n.value.value
    return out


# state -> (importer file, staff-vintage constant, enrollment-vintage constant or None when it is the same)
IMPORTER_CONSTANTS = [
    ("CA", "import_california_staff_data.py", "DATA_YEAR", None),
    ("MA", "import_massachusetts_data.py", "TEACHER_DATA_YEAR", "ENROLLMENT_DATA_YEAR"),
    ("MI", "import_michigan_data.py", "SOURCE_YEAR", None),
    ("NY", "import_new_york_data.py", "SOURCE_YEAR", None),
    ("PA", "import_pennsylvania_data.py", "SOURCE_YEAR", None),
    ("TX", "import_texas_tapr_data.py", "DATA_YEAR", None),
    ("VA", "import_virginia_data.py", "STAFF_SOURCE_YEAR", None),
]


@pytest.mark.parametrize("state,fname,staff_const,enroll_const", IMPORTER_CONSTANTS)
def test_importer_vintage_constants_equal_the_registry(state, fname, staff_const, enroll_const):
    reg = _registry()[state]
    consts = _module_constants(MIG / fname)
    assert consts[staff_const] == reg["year"], f"{fname}:{staff_const}"
    if enroll_const:
        assert consts[enroll_const] == reg["enroll_year"], f"{fname}:{enroll_const}"


@pytest.mark.parametrize("state,fname", [("FL", "import_florida_data.py"), ("IL", "import_illinois_data.py")])
def test_sql_literal_importers_stamp_the_registry_year(state, fname):
    """FL and IL stamp the year as an inline SQL literal ('2024-25' inside VALUES): the set of vintages the
    file writes must be exactly the registry's."""
    stamped = set(YEAR.findall("\n".join(
        n.value for n in ast.walk(ast.parse((MIG / fname).read_text(encoding="utf-8")))
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and "VALUES" in n.value)))
    assert stamped == {_registry()[state]["year"]}
