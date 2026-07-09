"""Cross-boundary architecture fitness functions (#124; governance §10).

The `arch-manifest.json` at the repo root DECLARES the couplings no import tool sees — external-process
invocations, cross-language dispatch, guarded entry points, and client<->server rule boundaries. These
tests assert the real code matches the manifest, so a NEW undeclared edge fails the suite. This is the
fitness-function layer that complements import-linter (intra-Python) + dependency-cruiser (intra-Node),
which see imports only (CLAUDE.md's recurring caveat: the graph tools miss environmental edges).

Pure filesystem + AST scan — no DB, no network, no subprocess. Seeded from the 2026-07-09 PR #198
code-review's three cross-boundary misses (entry-point parity, client<->server literal, forked helper).
"""
import ast
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ACQ = REPO / "infrastructure" / "acquisition"
MANIFEST = json.loads((REPO / "arch-manifest.json").read_text())

# argv[0] of a subprocess argv-list is a bare command word (node / claude / pdftotext …), not a path/flag.
_PROGRAM_RE = re.compile(r"^[a-z][a-z0-9._-]*$")
# The runner functions an argv-list is passed to — subprocess.* AND the injectable `_run` seams the
# pipeline uses so tests need no live subprocess (a naive `subprocess.*` scan would miss node/claude).
_RUNNERS = {"run", "Popen", "call", "check_output", "_run", "_tracked_run"}


def _acq_py_files():
    return [p for p in ACQ.rglob("*.py") if "__pycache__" not in str(p)]


def _argv_head(node):
    """If `node` is a `[ "prog", ... ]` list literal, return "prog" when it's a bare command word."""
    if isinstance(node, ast.List) and node.elts and isinstance(node.elts[0], ast.Constant) \
            and isinstance(node.elts[0].value, str) and _PROGRAM_RE.match(node.elts[0].value):
        return node.elts[0].value
    return None


def _external_program_calls():
    """{program -> [ 'relpath:line', … ]} over the acquisition tree. An external program is the head of
    an argv-list assigned to `cmd` or passed as the first arg to a runner call (survives the `_run` seam)."""
    found = {}
    for p in _acq_py_files():
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        rel = p.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            lst = None
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "cmd" for t in node.targets):
                lst = node.value
            elif isinstance(node, ast.Call) and node.args:
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                if name in _RUNNERS:
                    lst = node.args[0]
            prog = _argv_head(lst) if lst is not None else None
            if prog:
                found.setdefault(prog, []).append(f"{rel}:{node.lineno}")
    return found


# ----------------------------- external programs -----------------------------
def test_no_undeclared_external_program():
    """Every external program the pipeline shells out to must be declared in the manifest — a NEW
    subprocess / CLI / Node edge that isn't declared fails here (the canonical §10 fitness function)."""
    declared = set(MANIFEST["external_programs"]) - {"_comment"}
    actual = _external_program_calls()
    undeclared = {prog: sites for prog, sites in actual.items() if prog not in declared}
    assert not undeclared, (
        "Undeclared external-process edge(s) — add them to arch-manifest.json `external_programs` "
        f"(with why + callers): {undeclared}")


def test_no_stale_external_program_declarations():
    """The reverse — a declared program that no longer appears keeps the manifest honest (prevents rot)."""
    declared = set(MANIFEST["external_programs"]) - {"_comment"}
    actual = set(_external_program_calls())
    stale = declared - actual
    assert not stale, f"arch-manifest.json declares external programs no longer invoked (remove them): {stale}"


def test_declared_program_callers_actually_invoke_it():
    """Each declared program's `callers` list is accurate — the module actually builds an argv for it."""
    actual = _external_program_calls()
    for prog, spec in MANIFEST["external_programs"].items():
        if prog == "_comment":
            continue
        caller_files = {site.rsplit(":", 1)[0] for site in actual.get(prog, [])}
        for declared_caller in spec["callers"]:
            assert declared_caller in caller_files, (
                f"arch-manifest.json says {prog!r} is invoked by {declared_caller}, but no argv for "
                f"{prog!r} was found there (found in: {sorted(caller_files)})")


# ----------------------------- entry-point guards -----------------------------
def _calls_in_function(path: Path, func_name: str):
    """The set of called names (bare + attribute) inside the top-level function `func_name` in `path`."""
    tree = ast.parse(path.read_text())
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name), None)
    if fn is None:
        return None
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                names.add(f.attr)
            elif isinstance(f, ast.Name):
                names.add(f.id)
    return names


@pytest.mark.parametrize("guard_spec", [g for g in MANIFEST["entry_point_guards"]],
                         ids=[g["guard"] for g in MANIFEST["entry_point_guards"]])
def test_entry_point_guards_are_called(guard_spec):
    """A declared invariant guard must be reached by EVERY listed entry point — the fix for the class of
    bug where a rule is enforced at one entry point (the console) but a sibling (the CLI) skips it
    (#198 review finding #2: the headless run_batch ran a terminal abandoned batch)."""
    guard = guard_spec["guard"]
    for target in guard_spec["must_be_called_in"]:
        rel, func = target.split("::")
        calls = _calls_in_function(REPO / rel, func)
        assert calls is not None, f"arch-manifest.json entry-point guard target not found: {target}"
        assert guard in calls, (
            f"entry-point guard `{guard}` is NOT called in {target} — every entry point that runs a "
            f"stage must pass through it ({guard_spec['why']})")


# ----------------------------- client <-> server boundaries -----------------------------
def _static_js_files(scope: str):
    return [p for p in (REPO / scope).glob("*.js")]


@pytest.mark.parametrize("rule", [r for r in MANIFEST["client_server_boundaries"]["forbidden_client_comparisons"]],
                         ids=[r["literal"] for r in MANIFEST["client_server_boundaries"]["forbidden_client_comparisons"]])
def test_forbidden_client_comparison_literals(rule):
    """A server-authoritative rule literal must not be re-decided in client JS by COMPARISON (it duplicates
    a server truth and drifts). #198 review finding #3: the benchmark badge keyed on
    `c.batch_id === 'batch_00000'` instead of the server-computed is_benchmark. Comparison context only —
    an incidental display string (`benchmark-walled (batch_00000)`) is allowed."""
    lit = re.escape(rule["literal"])
    # the literal on either side of an (in)equality comparison: === / !== / == / !=
    cmp_re = re.compile(rf"""(?:[=!]==?\s*['"`]{lit}['"`])|(?:['"`]{lit}['"`]\s*[=!]==?)""")
    hits = []
    for p in _static_js_files(rule["scope"]):
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if cmp_re.search(line):
                hits.append(f"{p.relative_to(REPO).as_posix()}:{i}: {line.strip()}")
    assert not hits, (
        f"client JS compares against the server-authoritative literal {rule['literal']!r} — use "
        f"{rule['use_instead']} instead:\n  " + "\n  ".join(hits))


@pytest.mark.parametrize("helper", [h for h in MANIFEST["client_server_boundaries"]["single_definition_helpers"]],
                         ids=[h["name"] for h in MANIFEST["client_server_boundaries"]["single_definition_helpers"]])
def test_single_definition_helpers(helper):
    """A shared client helper must be DEFINED in exactly one file (its home) so it can't fork across the
    stage views (#198 review finding #5: the abandoned badge tone was added to gate1.js only)."""
    name = re.escape(helper["name"])
    def_re = re.compile(rf"""(?:function\s+{name}\b|(?:const|let|var)\s+{name}\s*=)""")
    definers = [p.relative_to(REPO).as_posix() for p in _static_js_files(helper["scope"])
                if def_re.search(p.read_text())]
    home = helper["home"]
    assert definers == [home], (
        f"client helper `{helper['name']}` must be defined only in {home}, found in: {definers} "
        "(define it once in common.js and alias it off window.LCT elsewhere)")


# ----------------------------- file dispatches (receipts) -----------------------------
@pytest.mark.parametrize("receipt", [r for r in MANIFEST["file_dispatches"]["receipts"]],
                         ids=[r["artifact"] for r in MANIFEST["file_dispatches"]["receipts"]])
def test_file_dispatch_producer_references_artifact(receipt):
    """Each declared receipt's producer module actually references its artifact filename — a light contract
    that the manifest's declared producer is the real one (the DB is the working store; these are receipts)."""
    producer = REPO / receipt["producer"]
    artifact = receipt["artifact"]
    referenced = any(
        f'"{artifact}"' in p.read_text() or f"'{artifact}'" in p.read_text()
        for p in producer.rglob("*.py") if "__pycache__" not in str(p))
    assert referenced, (
        f"arch-manifest.json says {receipt['producer']} produces {artifact}, but no .py there references "
        f"the filename {artifact!r}")
