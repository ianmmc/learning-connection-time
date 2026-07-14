"""Cross-family external code review harness (2026-07-13).

A one-shot review campaign that delegates a full read of the codebase to a diverse set of
**non-Claude** OpenRouter models (11 finder families) and adjudicates their findings through a
rotating cross-family judge cascade (3 reasoning models), then auto-files the survivors on the
GitHub tracker under a campaign label. Rationale + budget: the design discussion of 2026-07-13; the
mechanism mirrors the pipeline's own council invariant (REQ-056) — diversity, not count, is where
correctness comes from, and the third-family judge is load-bearing.

This is deliberately OUTSIDE `infrastructure/acquisition/` — it reviews the pipeline, it is not part
of it (no import-linter contract applies). It reuses the pipeline's paid client
(`stage7_extract.openrouter`) and family map (`common.model_families`) rather than reinventing them.

Entry point: `python -m tools.crossfam_review.run` (see `run.py` for flags;
`--dry-run` is the default — a live paid run requires `--live`).
"""
