# Archive — GT-benchmark-era tooling, superseded by the live Stage 1-4 pipeline (2026-06-24)

CLAUDE.md already claimed "the GT/benchmark exploration concluded and was archived" (git tag
`gt-exercise-complete`), but these six files never actually moved — they sat live in
`infrastructure/acquisition/` and `infrastructure/acquisition/discovery/` alongside the real
Stage 1-4 pipeline, with no current code importing any of them. This archives them for real,
as part of reorganizing `infrastructure/acquisition/` into per-stage subdirectories (the
"discovery" directory name was Stage 2's name specifically, but held code for every stage).

| File | What it was | Why it's here, not in a stage folder |
|---|---|---|
| `per_school_run.py` | Per-school discovery in WAVES, pre-Stage-1 design | Rebuilds its own roster from raw NCES CSV via plain `bands_for()`, bypassing Stage 1's `batch_NNNNN.json` entirely — discards every Stage 1 CP-A fix (virtual-school exclusion, CTC exclusion, `recursive_band_groups()`, the 12-per-band cap, cross-band dedup). Already explicitly marked "do not use as-is" before this move. |
| `council_extract.py` | Per-page Path-1 council extraction → score vs GT | A GT-scoring harness (compares extraction output against curated ground truth), not the real Stage 7 council — which hasn't been built yet and will read `filtered.json`/`processed.json`, not this script's input shape. |
| `extractors.py` | Provider-agnostic bell-schedule extractors, "for the benchmark" | GT-benchmark harness tooling. |
| `gt_propose.py` | Proposes GROSS per-band minutes for hand-curated GT districts, for human verification | GT-curation tooling — its job (curating ground truth) is done; the 940-school verified set it produced is real and durable, this script that helped build it is not needed going forward. |
| `reading.py` | Document → text/image reading for the extraction benchmark | Superseded as a *dependency* by Stage 4's `process_stage4.py`, which independently reimplements the same `_ocr_pdf`/rasterize-then-OCR pattern (not by importing this file — confirmed no live code ever imported it) for the new `captures/<hash>/` directory layout. Kept here as the original precedent, not deleted. |
| `score_minutes.py` | Re-scores saved benchmark extractions against GT-relevant modal minutes | GT-benchmark scoring tooling. |

**Not archived, despite living in the same era:** `aggregate.py` (Stage 8's real mode-then-mean
aggregation logic, "pure logic, no I/O" — moved to `infrastructure/acquisition/stage8_aggregate/`,
not archived, since it's still the actual rule the real pipeline will use) and `relevance.py`
(Stage 5's only existing draft — stale, predates the new `captures.json` schema, but Stage 5 has
no other implementation yet, so it moved to `infrastructure/acquisition/stage5_filter/` as a
starting point to update, not dead code to retire).

## Restore
Tracked in git; recover any file via `git log --follow -- <original path>` or copy it back from
this directory to wherever it's needed.
