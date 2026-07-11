#!/usr/bin/env python3
"""Lightweight AST mutation sweeper for the highest-stakes PURE modules (#204, epic #200).

Why home-grown instead of mutmut: mutmut 3.x copies the whole repo into a `mutants/` tree and its baseline
runs the ENTIRE `tests/` suite there — which trips on this repo's file-reading fitness tests
(`test_arch_manifest` reads `arch-manifest.json` at import) and its govdb/integration tests. This sweeper
mutates ONE module in place and runs only that module's own DB-free tests against the REAL tree — no copy,
no baseline-collects-everything problem. Same idea (introduce a defect, confirm a test catches it), scoped
to where it pays: the pure control-law / stats / state-machine cores the PR #220 review found bugs in.

Operators (the classic high-signal set): comparison boundary/negation flips (< <-> <=, > <-> >=, == <-> !=,
and cross-flips), boolean And<->Or, boolean-constant True<->False, numeric n -> n±1. One mutant per
(site, variant); a mutant SURVIVES when the tests still pass (a coverage gap) and is KILLED when they fail.

Usage:  python3 infrastructure/scripts/dev/mutation_sweep.py <module.py> <testfile> [testfile ...]
Restores the module unconditionally (try/finally), even on Ctrl-C.
"""
import ast
import subprocess
import sys
from pathlib import Path

_CMP_ALT = {
    ast.Lt: [ast.LtE, ast.GtE], ast.LtE: [ast.Lt, ast.Gt],
    ast.Gt: [ast.GtE, ast.LtE], ast.GtE: [ast.Gt, ast.Lt],
    ast.Eq: [ast.NotEq], ast.NotEq: [ast.Eq],
}
_BOOL_ALT = {ast.And: ast.Or, ast.Or: ast.And}


def _mutable_nodes(tree):
    """Deterministic (kind, node) list over mutable sites — same source ⇒ same ast.walk order, so an
    opportunity index maps to the same node on every re-parse."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP_ALT:
            out.append(("compare", node))
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL_ALT:
            out.append(("bool", node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            out.append(("boolconst", node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            out.append(("num", node))
    return out


def _variants(kind, node):
    if kind == "compare":
        op = type(node.ops[0])
        return [(alt, f"{op.__name__}->{alt.__name__}") for alt in _CMP_ALT[op]]
    if kind == "bool":
        alt = _BOOL_ALT[type(node.op)]
        return [(alt, f"{type(node.op).__name__}->{alt.__name__}")]
    if kind == "boolconst":
        return [(not node.value, f"{node.value}->{not node.value}")]
    if kind == "num":
        vs = [(node.value + 1, f"{node.value}->{node.value + 1}"),
              (node.value - 1, f"{node.value}->{node.value - 1}")]
        return vs
    return []


def _apply(src, index, kind, variant):
    """Re-parse, mutate the index-th mutable node per (kind, variant), return the new source."""
    tree = ast.parse(src)
    node = _mutable_nodes(tree)[index][1]
    if kind == "compare":
        node.ops[0] = variant()
    elif kind == "bool":
        node.op = variant()
    elif kind in ("boolconst", "num"):
        node.value = variant
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def sweep(module_path, test_files):
    module_path = Path(module_path)
    original = module_path.read_text()
    tree = ast.parse(original)
    sites = _mutable_nodes(tree)
    mutants = []
    for i, (kind, node) in enumerate(sites):
        for variant, label in _variants(kind, node):
            mutants.append((i, kind, variant, f"L{node.lineno} {kind} {label}"))

    killed, survived = 0, []
    print(f"{module_path.name}: {len(mutants)} mutants over {len(sites)} sites; "
          f"tests = {' '.join(test_files)}\n")
    try:
        for i, kind, variant, label in mutants:
            mutated = _apply(original, i, kind, variant)
            if mutated == original:
                continue
            module_path.write_text(mutated)
            try:
                # timeout: a mutant that flips a loop/recursion bound can hang its pytest run forever;
                # a hang IS a detected defect, so TimeoutExpired counts as killed (mutmut's convention).
                rc = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-p",
                                     "no:cacheprovider", *test_files],
                                    capture_output=True, timeout=300).returncode
            except subprocess.TimeoutExpired:
                rc = 1
            if rc == 0:
                survived.append(label)
                print(f"  SURVIVED  {label}")
            else:
                killed += 1
    finally:
        module_path.write_text(original)

    total = killed + len(survived)
    score = (killed / total * 100) if total else 100.0
    print(f"\nscore: {killed}/{total} killed ({score:.1f}%)")
    if survived:
        print("SURVIVORS (add a killing test for each):")
        for s in survived:
            print(f"  - {s}")
    return survived


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: mutation_sweep.py <module.py> <testfile> [testfile ...]")
    survivors = sweep(sys.argv[1], sys.argv[2:])
    sys.exit(1 if survivors else 0)
