"""Cross-boundary architecture fitness functions (#124; governance §10).

The `arch-manifest.json` at the repo root DECLARES the couplings no import tool sees — external-process
invocations, cross-language dispatch, guarded entry points, and client<->server rule boundaries. These
tests assert the real code matches the manifest, so a NEW undeclared edge fails the suite. This is the
fitness-function layer that complements import-linter (intra-Python) + dependency-cruiser (intra-Node),
which see imports only (CLAUDE.md's recurring caveat: the graph tools miss environmental edges).

Pure filesystem + AST scan — no DB, no network, no subprocess. Seeded from the 2026-07-09 PR #198
review's three cross-boundary misses, then HARDENED by the PR #206 review: scan scope + variable/runner
breadth widened (and declared in the manifest's `scan` section), the caller check made bidirectional,
guard detection scoped to the real top-level function and blind to nested defs, the client-JS scans made
recursive + multi-line + indirection-aware, manifest schema/emptiness validated so a malformed or emptied
manifest fails loudly instead of silently collecting zero tests.

HONEST LIMITS (declared in the manifest too): dynamically-assembled argvs and unlisted runner names are
invisible (semantic coupling — the research doc's conclusion); guard detection is syntactic presence,
not runtime reachability (dead code still counts — vulture's domain); a behavioral duplicate of a helper
under a DIFFERENT name is beyond static reach.
"""
import ast
import functools
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((REPO / "arch-manifest.json").read_text())

# argv[0] of a subprocess argv-list is a bare command word (node / claude / pg_dump …), not a path/flag.
_PROGRAM_RE = re.compile(r"^[a-z][a-z0-9._+-]*$")
# Runner functions an argv-list is passed to — subprocess.* AND the injectable seams the pipeline uses so
# tests need no live subprocess (a naive `subprocess.*` scan would miss node/claude behind `_run`).
_RUNNERS = {"run", "Popen", "call", "check_output", "check_call", "create_subprocess_exec",
            "_run", "_tracked_run"}
# Variable names an argv-list literal is conventionally assigned to before being passed to a runner.
_CMD_VARS = {"cmd", "argv", "command"}


# ----------------------------- manifest serialization (#656) -----------------------------


def test_the_manifest_is_stored_in_its_canonical_serialization():
    """The file must be exactly `json.dumps(..., indent=2, ensure_ascii=False)` + a trailing newline.

    #656: a 2-entry content change in PR #641 re-serialized the WHOLE file, because the write path
    used the default `ensure_ascii=True` and converted every em-dash and section-sign in ~16
    `_comment` fields to a \\uXXXX escape. A 2-line change became a 264-line diff, and the escaped
    form then became the on-disk style, so the next hand-edit using literal punctuation would churn
    it right back. Cheap to pin, and it keeps this file's diffs reviewable — which matters more here
    than elsewhere, since CLAUDE.md makes an edit to this manifest THE review surface for a new
    cross-boundary edge."""
    raw = (REPO / "arch-manifest.json").read_text(encoding="utf-8")
    canonical = json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n"
    assert raw == canonical, (
        "arch-manifest.json is not in its canonical serialization. Rewrite it with\n"
        "  json.dumps(obj, indent=2, ensure_ascii=False) + '\\n'\n"
        f"(escapes present: {raw.count(chr(92) + 'u')}). Never serialize it with ensure_ascii=True — "
        "that rewrites every line carrying an em-dash or section-sign.")


# ----------------------------- manifest self-checks (schema + emptiness) -----------------------------
# #206 review: (a) unguarded dict-key access crashed with a raw KeyError on an incomplete entry, and
# (b) pytest.parametrize over an emptied manifest list silently collects ZERO tests instead of failing.
# These two tests make a malformed/emptied manifest a loud, readable failure.
def test_manifest_schema():
    for prog, spec in MANIFEST["external_programs"].items():
        if prog == "_comment":
            continue
        assert _PROGRAM_RE.match(prog), f"external_programs key {prog!r} is not a bare command word"
        assert {"why", "callers"} <= set(spec), f"external_programs[{prog!r}] needs why + callers"
        assert spec["callers"], f"external_programs[{prog!r}].callers must not be empty"
    for g in MANIFEST["entry_point_guards"]:
        assert {"guard", "why", "must_be_called_in"} <= set(g), f"entry_point_guards entry incomplete: {g}"
        assert all("::" in t for t in g["must_be_called_in"]), f"targets must be path::function: {g}"
    for r in MANIFEST["client_server_boundaries"]["forbidden_client_comparisons"]:
        assert {"literal", "use_instead", "scope"} <= set(r), f"forbidden_client_comparisons entry incomplete: {r}"
    for h in MANIFEST["client_server_boundaries"]["single_definition_helpers"]:
        assert {"name", "home", "scope"} <= set(h), f"single_definition_helpers entry incomplete: {h}"
    for rec in MANIFEST["file_dispatches"]["receipts"]:
        assert {"artifact", "producer", "role"} <= set(rec), f"receipts entry incomplete: {rec}"
    for ldr in MANIFEST["file_dispatches"]["cli_only_loaders"]:
        assert {"loader", "why", "forbidden_scope"} <= set(ldr), f"cli_only_loaders entry incomplete: {ldr}"
    for ar in MANIFEST["file_dispatches"]["audit_receipts"]:
        assert {"basename", "stage", "producer", "role"} <= set(ar), f"audit_receipts entry incomplete: {ar}"
    for root in MANIFEST["scan"]["python_roots"]:
        assert (REPO / root).is_dir(), f"scan.python_roots entry does not exist: {root}"


def test_manifest_enforced_sections_are_nonempty():
    """An emptied section would make its parametrized test silently collect zero cases — a green run
    with the fitness check gone. Emptying a section must be a DELIBERATE act that edits this test too."""
    assert len(set(MANIFEST["external_programs"]) - {"_comment"}) > 0
    assert MANIFEST["entry_point_guards"], "entry_point_guards emptied — the #168 guard check would vanish"
    assert MANIFEST["client_server_boundaries"]["forbidden_client_comparisons"]
    assert MANIFEST["client_server_boundaries"]["single_definition_helpers"]
    assert MANIFEST["file_dispatches"]["receipts"]
    assert MANIFEST["file_dispatches"]["cli_only_loaders"], \
        "cli_only_loaders emptied — the #526 receipt-as-transport check would vanish"
    assert MANIFEST["file_dispatches"]["audit_receipts"], \
        "audit_receipts emptied — the REQ-164 both-ways receipt-coverage check would vanish"


# ----------------------------- external programs -----------------------------
def _scanned_py_files():
    excluded = set(MANIFEST["scan"]["excluded_dirs"])
    for root in MANIFEST["scan"]["python_roots"]:
        for p in (REPO / root).rglob("*.py"):
            if not excluded & set(p.parts):
                yield p


def _argv_head(node):
    """If `node` is a `[ "prog", ... ]` list literal, return "prog" when it's a bare command word."""
    if isinstance(node, ast.List) and node.elts and isinstance(node.elts[0], ast.Constant) \
            and isinstance(node.elts[0].value, str) and _PROGRAM_RE.match(node.elts[0].value):
        return node.elts[0].value
    return None


@functools.lru_cache(maxsize=1)
def _external_program_calls():
    """{program -> tuple of 'relpath:line'} over the declared scan scope. An external program is the
    head of an argv-list assigned to a conventional cmd variable or passed as the first arg to a runner
    call (survives the injectable `_run` seam). Cached — three tests consume it (#206 review)."""
    found = {}
    for p in _scanned_py_files():
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        rel = p.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            lst = None
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id in _CMD_VARS for t in node.targets):
                lst = node.value
            elif isinstance(node, ast.Call) and node.args:
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
                if name in _RUNNERS:
                    lst = node.args[0]
            prog = _argv_head(lst) if lst is not None else None
            if prog:
                found.setdefault(prog, []).append(f"{rel}:{node.lineno}")
    return {prog: tuple(sites) for prog, sites in found.items()}


def test_no_undeclared_external_program():
    """Every external program the scanned trees shell out to must be declared in the manifest — a NEW
    subprocess / CLI / Node edge that isn't declared fails here (the canonical §10 fitness function)."""
    declared = set(MANIFEST["external_programs"]) - {"_comment"}
    undeclared = {prog: sites for prog, sites in _external_program_calls().items()
                  if prog not in declared}
    assert not undeclared, (
        "Undeclared external-process edge(s) — add them to arch-manifest.json `external_programs` "
        f"(with why + callers): {undeclared}")


def test_no_stale_external_program_declarations():
    """The reverse — a declared program that no longer appears keeps the manifest honest (prevents rot)."""
    declared = set(MANIFEST["external_programs"]) - {"_comment"}
    stale = declared - set(_external_program_calls())
    assert not stale, f"arch-manifest.json declares external programs no longer invoked (remove them): {stale}"


def test_program_callers_match_bidirectionally():
    """BOTH directions (#206 review — the old check only verified declared->found, so a NEW file calling
    an already-declared program from an undeclared location shipped green): every declared caller is
    real, and every ACTUAL caller is declared — the callers lists are load-bearing, not documentation."""
    actual = _external_program_calls()
    for prog, spec in MANIFEST["external_programs"].items():
        if prog == "_comment":
            continue
        declared_callers = set(spec["callers"])
        actual_callers = {site.rsplit(":", 1)[0] for site in actual.get(prog, ())}
        missing = declared_callers - actual_callers
        assert not missing, (
            f"arch-manifest.json says {prog!r} is invoked by {sorted(missing)}, but no argv for "
            f"{prog!r} was found there (found in: {sorted(actual_callers)})")
        undeclared = actual_callers - declared_callers
        assert not undeclared, (
            f"NEW undeclared caller(s) of {prog!r}: {sorted(undeclared)} — add them to "
            f"external_programs[{prog!r}].callers in arch-manifest.json (that edit is the review surface)")


# ----------------------------- entry-point guards -----------------------------
def _module_level_function(tree, func_name):
    """The MODULE-TOP-LEVEL function named `func_name` — not a same-named method/nested def elsewhere in
    the file (#206 review: a bare ast.walk name match could validate a decoy)."""
    return next((n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name), None)


def _direct_calls(fn):
    """Called names reachable from `fn`'s OWN body — deliberately blind to nested function/lambda bodies
    (#206 review: a guard tucked into a defined-but-never-invoked inner helper must NOT count as called).
    Syntactic presence only: dead code after a return still counts (reachability is vulture's domain)."""
    names = set()

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue                       # a nested def's body does not run when fn runs
            if isinstance(child, ast.Call):
                f = child.func
                names.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None))
            visit(child)

    visit(fn)
    return names


@pytest.mark.parametrize("guard_spec", MANIFEST["entry_point_guards"],
                         ids=[g["guard"] for g in MANIFEST["entry_point_guards"]])
def test_entry_point_guards_are_called(guard_spec):
    """A declared invariant guard must be reached by EVERY listed entry point — the fix for the class of
    bug where a rule is enforced at one entry point but a sibling skips it (#198 review finding #2:
    the headless run_batch; #206 review: the older per-district CLIs)."""
    guard = guard_spec["guard"]
    for target in guard_spec["must_be_called_in"]:
        rel, func = target.split("::")
        fn = _module_level_function(ast.parse((REPO / rel).read_text()), func)
        assert fn is not None, f"arch-manifest.json entry-point guard target not found at module level: {target}"
        assert guard in _direct_calls(fn), (
            f"entry-point guard `{guard}` is NOT called in {target}'s own body — every entry point that "
            f"runs a stage must pass through it ({guard_spec['why']})")


# ----------------------------- client <-> server boundaries -----------------------------
def _static_js_files(scope: str):
    return sorted((REPO / scope).rglob("*.js"))      # recursive (#206 review: glob missed subdirs)


def _hits(pattern: re.Pattern, path: Path):
    text = path.read_text()
    return [f"{path.relative_to(REPO).as_posix()}:{text.count(chr(10), 0, m.start()) + 1}: "
            f"{text[m.start():m.end()][:80]}"
            for m in pattern.finditer(text)]


@pytest.mark.parametrize("rule", MANIFEST["client_server_boundaries"]["forbidden_client_comparisons"],
                         ids=[r["literal"] for r in MANIFEST["client_server_boundaries"]["forbidden_client_comparisons"]])
def test_forbidden_client_comparison_literals(rule):
    """A server-authoritative rule literal must not be re-decided in client JS (it duplicates a server
    truth and drifts — #198 review finding #3). Whole-file scan (multi-line safe) over four decision
    forms (#206 review widened from same-line equality only): (in)equality comparisons, string-method
    predicates, switch-case labels, and BINDING the literal to a variable (the indirection vector —
    `const BENCH_ID = "..."; x === BENCH_ID` would otherwise evade any literal-adjacent pattern).
    A purely-display occurrence (inside a template string, no decision) is allowed."""
    lit = re.escape(rule["literal"])
    q = r"['\"`]"
    pattern = re.compile(
        rf"(?:[=!]==?\s*{q}{lit}{q})"                                        # x === "lit" (multi-line via \s)
        rf"|(?:{q}{lit}{q}\s*[=!]==?)"                                       # "lit" === x
        rf"|(?:\.(?:includes|startsWith|endsWith|indexOf)\(\s*{q}{lit}{q})"  # x.includes("lit")
        rf"|(?:\bcase\s+{q}{lit}{q})"                                        # case "lit":
        rf"|(?:(?<![=!<>+])=(?!=)\s*{q}{lit}{q})")                           # const X = "lit" (indirection)
    hits = [h for p in _static_js_files(rule["scope"]) for h in _hits(pattern, p)]
    assert not hits, (
        f"client JS decides against the server-authoritative literal {rule['literal']!r} — use "
        f"{rule['use_instead']} instead:\n  " + "\n  ".join(hits))


@pytest.mark.parametrize("helper", MANIFEST["client_server_boundaries"]["single_definition_helpers"],
                         ids=[h["name"] for h in MANIFEST["client_server_boundaries"]["single_definition_helpers"]])
def test_single_definition_helpers(helper):
    """A shared client helper must be DEFINED in exactly one file (its home) so it can't fork across the
    stage views (#198 review finding #5). Detected forms (#206 review widened): function/const/let/var
    definitions AND property assignments (`window.LCT.name = ...`). Aliasing via destructuring
    (`const { statusBadge } = window.LCT`) is a USE, not a definition, and stays allowed."""
    name = re.escape(helper["name"])
    def_re = re.compile(
        rf"(?:function\s+{name}\b)"
        rf"|(?:(?:const|let|var)\s+{name}\s*=)"
        rf"|(?:\.\s*{name}\s*=(?!=))")                # window.LCT.statusBadge = ... (property assignment)
    definers = sorted({p.relative_to(REPO).as_posix()
                       for p in _static_js_files(helper["scope"]) if def_re.search(p.read_text())})
    assert definers == [helper["home"]], (
        f"client helper `{helper['name']}` must be defined only in {helper['home']}, found in: {definers} "
        "(define it once in common.js and alias it off window.LCT elsewhere)")


# ----------------------------- file dispatches (receipts) -----------------------------
def _py_files_under(scope: Path) -> list:
    """Every .py under `scope`, pycache excluded — the one shared directory-scoped scan loop
    for the file_dispatches tests (#555 review: this idiom had started duplicating per test).
    Distinct from _scanned_py_files(), which walks the manifest's global python_roots."""
    return [p for p in scope.rglob("*.py") if "__pycache__" not in str(p)]


@pytest.mark.parametrize("receipt", MANIFEST["file_dispatches"]["receipts"],
                         ids=[r["artifact"] for r in MANIFEST["file_dispatches"]["receipts"]])
def test_file_dispatch_producer_references_artifact(receipt):
    """Each declared receipt's producer module actually references its artifact filename — a light contract
    that the manifest's declared producer is the real one (the DB is the working store; these are receipts)."""
    artifact = receipt["artifact"]
    referenced = any(
        f'"{artifact}"' in p.read_text() or f"'{artifact}'" in p.read_text()
        for p in _py_files_under(REPO / receipt["producer"]))
    assert referenced, (
        f"arch-manifest.json says {receipt['producer']} produces {artifact}, but no .py there references "
        f"the filename {artifact!r}")


@pytest.mark.parametrize("ldr", MANIFEST["file_dispatches"]["cli_only_loaders"],
                         ids=[l["loader"] for l in MANIFEST["file_dispatches"]["cli_only_loaders"]])
def test_cli_only_loaders_not_referenced_in_scope(ldr):
    """#526: a receipt loader declared cli_only must not be referenced anywhere in its forbidden
    scope — the console/autoflow resolves batches from the DB working store (_batch_from_db), and a
    single `H2.load_batch_any(...)` call would silently reintroduce the receipt-as-transport edge.
    Name-presence scan (comments included) on purpose: even a commented example invites the call back."""
    offenders = [str(p.relative_to(REPO)) for p in _py_files_under(REPO / ldr["forbidden_scope"])
                 if ldr["loader"] in p.read_text()]
    assert not offenders, (
        f"{ldr['loader']} is CLI-only ({ldr['why']}) but is referenced in {offenders} — "
        f"resolve the batch via _batch_from_db instead")


# ----------------------------- audit receipts (REQ-164, common/receipts.py) -----------------------------
def _receipts_alias(tree):
    """The local alias bound to `infrastructure.acquisition.common.receipts` in this module, or None."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "infrastructure.acquisition.common":
            for alias in node.names:
                if alias.name == "receipts":
                    return alias.asname or alias.name
    return None


@functools.lru_cache(maxsize=1)
def _audit_receipt_calls():
    """{basename -> tuple of 'relpath:line'} over the declared scan scope — every call of the shared
    per-district receipt writer (`RCPT.write_receipt(district_id, name, basename, payload)`), keyed by
    its basename (the 3rd positional arg, a string literal). Mirrors _external_program_calls()'s shape
    so the same both-ways coverage pattern (#206's external_programs review) applies to audit receipts."""
    found = {}
    for p in _scanned_py_files():
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError:
            continue
        alias = _receipts_alias(tree)
        if alias is None:
            continue
        rel = p.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "write_receipt"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == alias):
                continue
            if len(node.args) < 3 or not (isinstance(node.args[2], ast.Constant)
                                           and isinstance(node.args[2].value, str)):
                continue
            found.setdefault(node.args[2].value, []).append(f"{rel}:{node.lineno}")
    return {basename: tuple(sites) for basename, sites in found.items()}


def test_no_undeclared_audit_receipt():
    """Every basename passed to the shared per-district receipt writer must be declared in the manifest
    — a NEW stage (or a renamed basename) that isn't declared fails here."""
    declared = {ar["basename"] for ar in MANIFEST["file_dispatches"]["audit_receipts"]}
    undeclared = {b: sites for b, sites in _audit_receipt_calls().items() if b not in declared}
    assert not undeclared, (
        "Undeclared audit-receipt basename(s) — add them to arch-manifest.json "
        f"`file_dispatches.audit_receipts` (with stage + producer + role): {undeclared}")


def test_no_stale_audit_receipt_declaration():
    """The reverse — a declared basename no longer written anywhere keeps the manifest honest."""
    declared = {ar["basename"] for ar in MANIFEST["file_dispatches"]["audit_receipts"]}
    stale = declared - set(_audit_receipt_calls())
    assert not stale, f"arch-manifest.json declares audit receipt basename(s) no longer written: {stale}"


def test_audit_receipt_producer_matches_bidirectionally():
    """BOTH directions (mirrors test_program_callers_match_bidirectionally): the declared producer must
    be a real call site for its basename, and every ACTUAL call site of a declared basename must be the
    declared producer — a second module quietly writing the same basename is a review-worthy new edge."""
    actual = _audit_receipt_calls()
    for ar in MANIFEST["file_dispatches"]["audit_receipts"]:
        basename, declared_producer = ar["basename"], ar["producer"]
        actual_files = {site.rsplit(":", 1)[0] for site in actual.get(basename, ())}
        assert declared_producer in actual_files, (
            f"arch-manifest.json says {declared_producer} produces audit receipt {basename!r}, but no "
            f"write_receipt(..., {basename!r}, ...) call was found there (found in: {sorted(actual_files)})")
        undeclared = actual_files - {declared_producer}
        assert not undeclared, (
            f"NEW undeclared producer(s) of audit receipt {basename!r}: {sorted(undeclared)} — add them "
            f"to file_dispatches.audit_receipts in arch-manifest.json (that edit is the review surface)")
