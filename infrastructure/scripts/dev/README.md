# Dev utilities

## `mutation_sweep.py` (#204, epic #200)

Mutation testing for the highest-stakes **pure** modules (control-law / stats / state-machine cores).

**Why not mutmut:** mutmut 3.x copies the whole repo into `mutants/` and its baseline runs the *entire*
`tests/` suite there — which trips on this repo's file-reading fitness tests (`test_arch_manifest` reads
`arch-manifest.json` at import) and its govdb/integration tests. This sweeper mutates one module in place
and runs only that module's own DB-free tests against the real tree — no copy, no baseline-collects-all.

```bash
python3 infrastructure/scripts/dev/mutation_sweep.py \
  infrastructure/acquisition/stage5_filter/exploration_audit.py \
  tests/test_exploration_audit.py tests/test_property_guardrail_cores.py
```

A mutant **survives** (a coverage gap) when the tests still pass; it's **killed** when they fail. Restores
the module unconditionally (even on Ctrl-C). Triage survivors → add a killing test, or confirm the mutant
is *equivalent* (no test can distinguish it) and leave it.

**Baseline results (2026-07-11):**
- `exploration_audit.py`: 44/46 killed (95.7%); the 2 survivors are equivalent — `round(1-fnr, 6)` 6→7
  (the complement is already 6-decimal) and `< p` → `<= p` in the sampler (an exact-equality draw is
  measure-zero).
- `config_artifact.py`: 26/27 killed (96.3%); the 1 survivor is `ensure_ascii=False`→`True` (ASCII-only
  fingerprints, internally consistent either way).
