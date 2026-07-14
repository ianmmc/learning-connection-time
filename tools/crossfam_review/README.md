# Cross-family external code review harness

A one-shot review campaign that delegates a full read of the codebase to a diverse set of
**non-Claude** OpenRouter models and adjudicates their findings through a rotating cross-family judge
cascade, then files the survivors on the GitHub tracker under a campaign label.

**Why.** This codebase has been reviewed repeatedly by Claude variants. Claude tends to *make* (and
therefore *miss*) mistakes in the directions its training biases it — same-family reviewers share the
blind spot. The pipeline's own council data (REQ-056; `models-and-council-composition/`) proved that
cross-family diversity is where correctness comes from and that a third-family judge is load-bearing.
This applies that same mechanism to code review. Rationale + budget: PROJECT_HISTORY 2026-07-13.

## How it works

```
36 shards ── 10 finders (one pass each) ──▶ raw findings
                                              │  dedup (file + ~line + category)
                                              ▼
                                          unique candidates
                                              │  rotating 3-family judge cascade
                                              │  (2 voters; a split escalates to the 3rd)
                                              ▼
                                          confirmed ──▶ GitHub issues (campaign label)
```

- **Finders** (10 families: DeepSeek, Moonshot, Qwen, Xiaomi, MiniMax, Google, OpenAI, xAI, Mistral,
  Meta): each reviews every shard. Diversity, not count, is the point. (Z-AI's glm-4.7-flash was
  dropped after the smoke test — it streams reasoning the shared client can't capture and returned
  empty content; see `roster.py`.)
- **Judge cascade** (`gemini-2.5-pro`, `gpt-5.6-luna`, `deepseek-v4-pro`): two cross-family voters
  adjudicate each candidate; a split escalates to the third. Roles **rotate per candidate** (by the
  candidate's own identity, stable across resumes) so no model is permanently the tie-breaker.
- **Spend guard**: a hard USD cap (`--cap`, default $10) enforced by reserve-then-settle; real cost
  comes from OpenRouter's `usage.cost`. Realistic full run ≈ $6.

## Usage

```bash
# Free: validate model ids against the live catalog, print the shard map + budget estimate
python -m tools.crossfam_review.run

# Full paid review; PRINT the issues it would file (no tracker writes)
python -m tools.crossfam_review.run --run

# Full review + actually file issues under 'crossfam-review-<date>'
python -m tools.crossfam_review.run --run --live

# Cheap smoke test: first shard, one finder (use a current roster model — a name not in the roster
# runs 0 finders and silently "succeeds", masking a bad key/setup)
python -m tools.crossfam_review.run --run --max-shards 1 --only gemini-2.5-flash-lite --cap 0.50
```

Receipts (every stage's raw output — finder findings, candidates, verdicts, issues, spend) land under
`data/review/crossfam-<stamp>/`. Re-runs are idempotent: each issue body carries a stable
`crossfam-fp:` fingerprint, and `--live` skips fingerprints already on the tracker.

## Placement

Deliberately **outside `infrastructure/`** — this tool reviews the pipeline, it is not part of it, so
the import-linter root (`infrastructure`) doesn't graph it (it reuses the acquisition paid client,
which the "scripts must not import acquisition" contract would otherwise forbid). It is registered as
a package via `pyproject.toml`'s `tools*` include so `pip install -e .` makes it importable.
