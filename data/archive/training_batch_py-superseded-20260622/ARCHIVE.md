# Archive — training_batch.py, superseded by queue_batch.py (2026-06-22)

`infrastructure/acquisition/discovery/training_batch.py` was the discovery+capture **training**
loop's stratified batch picker (per-school-acquire-training skill, steps 1-5 only — no exclusion
filters, no extraction). Superseded by Stage 1's real implementation,
`infrastructure/acquisition/discovery/queue_batch.py`, which adds the pre-queue exclusion filters
(operating status, CTC/shared-service, grade-span integrity, already-attempted), enrollment-quartile
stratification (vs. training_batch.py's school-count tiers), per-band school selection with
cross-band overlap minimization, and the `district_status.json` registry. See
`docs/ACQUISITION_PIPELINE.md` (Stage 1 section) for the full design.

**Harvested into the new implementation before archiving** (nothing here is original/lost):
- Seeded-shuffle-then-top-up-if-short pattern → `queue_batch.py::stratified_pick`.
- Per-district per-band school counting via grade-span (`bands_for`) → already lived in, and stays
  in, `school_sampling.py` (extended with `school_index()` and `lea_info()`, not replaced).
- `--n`/positional-batch-number CLI shape and `batch_{NN:02d}` naming convention.

**Not carried forward** (deliberately superseded, not lost): the directory-presence
"touched" heuristic (`touched_ids()`) — replaced by the explicit `district_status.json` registry,
which records outcome/stage rather than inferring it from which directories happen to exist.

## Restore
Tracked in git; recover via `git log --follow -- infrastructure/acquisition/discovery/training_batch.py`
or simply copy `training_batch.py` (next to this file) back to its original path.
