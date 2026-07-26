"""REQ-131 (epic #481; 2026-07-15 audit sweep) — a standing guard against self-testing theater: a test
file whose only imports are stdlib/pytest/mocks, never touching real production code, so a 100% pass
rate evidences nothing. PR #486 fixed the two KNOWN instances by hand (test_bell_schedule_enrichment.py,
infrastructure/quality-assurance/tests/test_utilities.py), driven by a one-time external crossfam
review (#477) — not by a standing check. Without this test, a materially identical file could be added
tomorrow and pass CI indefinitely.

Pure filesystem + AST scan (mirrors test_arch_manifest.py's style) — no DB, no network.

GRANDFATHER LIST: this sweep found 21 pre-existing test files with zero infrastructure./tools. imports.
Fixing them is its own #486-shaped cleanup pass (some are legitimately infra-light fitness functions
like this one and test_arch_manifest.py; at least one — test_nces_import.py — genuinely matches the
theater pattern #486 was meant to catch and missed, since it also carries no unittest.mock.patch()
string-target reference to production code either). Rather than block this REQ's build on that separate
cleanup, the 21 are grandfathered explicitly below — visible, dated, and a punch-list — while this guard
bites immediately on any NEW zero-production-coupling test file."""
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO / "tests"

# A module reference counts as "touches production code" if it starts with one of these roots.
_PRODUCTION_ROOTS = ("infrastructure", "tools")

# Grandfathered as of the 2026-07-15 sweep (REQ-131) — zero infrastructure./tools. import AND zero
# unittest.mock.patch() string-target reference to production code, as of this commit. Not all of these
# are theater (test_arch_manifest.py, test_config_schemas.py, and test_constraints.py are legitimate
# pure-filesystem/pure-SQL fitness functions with nothing production-Python to import) — this list is a
# snapshot, not an endorsement. Remove an entry once its file gains real production coupling (or is
# fixed/deleted the way #486 fixed its two instances); never ADD to this list for a new file — a new
# zero-coupling test should fail this guard, not be silently grandfathered in.
_GRANDFATHERED = {
    "test_acquisition_paths.py", "test_arch_manifest.py", "test_california_integration.py",
    "test_config_schemas.py", "test_constraints.py", "test_data_safeguards.py", "test_export.py",
    "test_florida_integration.py", "test_illinois_integration.py", "test_infrastructure.py",
    "test_massachusetts_integration.py", "test_michigan_integration.py", "test_nces_import.py",
    "test_new_york_integration.py", "test_pennsylvania_integration.py", "test_sea_integration_base.py",
    "test_sped_segmentation.py", "test_state_integration.py", "test_texas_integration.py",
    "test_validation.py", "test_virginia_integration.py",
    # legitimate pure-filesystem fitness functions — same shape as test_arch_manifest.py, nothing
    # production-Python to import (test_ci_workflows.py scans .github/workflows/*.yml, not infra code)
    "test_suite_hygiene.py", "test_ci_workflows.py",
    # test_one_home_fitness.py (#650) scans acquisition + tests SOURCE for re-spelled rules — it must
    # NOT import the modules it polices (importing would prove nothing about their text, and the
    # policed set includes test files). Same shape as test_arch_manifest.py.
    "test_one_home_fitness.py",
    # test_state_catalog.py validates docs/state-integrations/state_data_catalog.yaml
    # (the SEA-campaign source-of-truth written by probe/acquire agents) — pure-YAML
    # fitness function, no production Python involved
    "test_state_catalog.py",
}


def _imported_modules(tree):
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def _patch_targets(tree):
    """String targets of unittest.mock.patch(...)/patch.object(...) calls — a test that mocks
    infrastructure.x.y by STRING never imports it, so the import scan alone would miss it."""
    targets = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in ("patch", "object") and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                targets.add(node.args[0].value)
    return targets


def _touches_production_code(path):
    tree = ast.parse(path.read_text())
    mods = _imported_modules(tree)
    if any(m == root or m.startswith(root + ".") for m in mods for root in _PRODUCTION_ROOTS):
        return True
    patches = _patch_targets(tree)
    return any(t == root or t.startswith(root + ".") for t in patches for root in _PRODUCTION_ROOTS)


def _test_files():
    return sorted(TESTS_DIR.glob("test_*.py"))


def test_every_non_grandfathered_test_file_touches_production_code():
    offenders = [f.name for f in _test_files()
                if f.name not in _GRANDFATHERED and not _touches_production_code(f)]
    assert not offenders, (
        f"{len(offenders)} test file(s) import zero infrastructure./tools. code and patch() zero "
        f"production-code string targets — the #486 self-testing-theater pattern: {offenders}. Either "
        f"import/patch real production code, or if this file is a genuine pure-filesystem/pure-SQL "
        f"fitness function (like test_arch_manifest.py), add it to _GRANDFATHERED above with a reason.")


def test_grandfather_list_has_no_stale_or_missing_entries():
    # keeps the list itself honest: an entry for a deleted file, or a real file missing from a fresh
    # scan, both mean the list has drifted from the filesystem it's supposed to describe
    real_names = {f.name for f in _test_files()}
    stale = _GRANDFATHERED - real_names
    assert not stale, f"_GRANDFATHERED references file(s) that no longer exist: {stale}"
