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
- `stage8_aggregate/aggregate.py` (whole module, vs `test_aggregate.py` + the property suite):
  96/167 killed (57.5%). The PR #221 review's targeted read: **`merge_fact_runs` (the REQ-122 core)
  had exactly 2 real survivors** — the strict `<`/`>` equal-run tie-breaks at L194/L196 — killed by
  `test_equal_run_ties_keep_the_first_row_seen`. The remaining survivors sit in the OLDER council/
  consensus functions (L21–L169: `_cluster`, `council_school`, `mode_stable`, `consensus_school_facts`),
  whose deeper coverage lives in the stage-7 integration suites this per-module sweep deliberately
  doesn't run; treat those as the module's known pre-#221 debt, not a regression.
- `stage7_extract/requests.py` (whole module, vs `test_stage7_requests.py` + the property suite):
  40/54 killed (74.1%). **The #231 sent-files core (`_sent_inventory`/`_sent_file`/`_sent_files`) had
  ZERO survivors.** The 14 survivors are rank-key tier constants (`rank_alternates`) that are
  equivalent mutants — flipping a tier number preserves the ladder's relative order — plus
  `_accepted_counts` arithmetic only observable through detect_requests' DB-marked paths.
