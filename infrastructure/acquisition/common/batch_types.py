"""THE `batch_type` axis, and the redo lever it used to imply (epic #617, Phase 2c).

`batch_type` shipped as an unconstrained string whose legal values lived only in a comment
(`stage1_queue/models.py`), and five separate sites derived BEHAVIOR from string equality against it:

  * ``stage2_discover/discover_stage2.py::reconcile``  — `followup` (the todo decision itself)
  * ``stage2_discover/discover_stage2.py`` legacy CLI  — `merge=`
  * ``stage2_discover/headless.py``                    — `merge=`
  * ``stage3_capture/headless.py``                     — `redo=`
  * ``stage4_process/headless.py``                     — `redo=`

Every one of them asked ``batch_type == "follow-up"``, so a third batch type silently got first-run
behavior: a benchmark batch skipped every already-attempted district, which is exactly why mobility
property 2 (a first-run/follow-up district later entering a benchmark batch) could not work.

**Redo-eligibility is now a DECLARED batch attribute, not a type derivation.** That distinction is
load-bearing, not stylistic. Deriving it — "benchmark batches redo" — would have made Stage 2 on
`batch_00000` re-run discovery over the 27 curated-GT districts and, via `merge=True`, fold fresh SERP
candidates into their FROZEN `gt://` candidate sets. That corpus is FIXED (CLAUDE.md), and the
injector's own write-once guard (`benchmark_batch.inject_district`) only protects the initial
injection, not a later re-run. So:

  * a batch that DECLARES `redo_attempted` is believed, whatever its type;
  * a batch that declares nothing (every row and receipt predating this column, `batch_00000`
    included) falls back to the historical ``batch_type == 'follow-up'`` rule — byte-identical
    behavior, no backfill, and the frozen benchmark artifacts stay untouchable by default;
  * new composers declare it explicitly (`default_redo_attempted`), so a NEWLY composed benchmark
    batch — a real Stages-2/3/4 A/B harness — does redo, which is what property 2 needs.

Lives in `common` because the stages are independent siblings under the import-linter layering
contract and may not import each other or `stage1_queue` — the same reason `batch_guard` lives here.
"""
from __future__ import annotations

FIRST_RUN = "first-run"
FOLLOW_UP = "follow-up"
BENCHMARK = "benchmark"
BATCH_TYPES = (FIRST_RUN, FOLLOW_UP, BENCHMARK)

# The types whose composers declare redo_attempted=True. A benchmark batch re-runs districts that
# have already been through the pipeline (that IS the A/B), so it redoes — but only when a composer
# says so on the batch itself; see the module docstring for why the type alone must not imply it.
_REDO_BY_DEFAULT = (FOLLOW_UP, BENCHMARK)


def validate_batch_type(value: str) -> str:
    """Return `value` if it is a legal batch type, else raise. The `dispatch_type` axis (#618)
    validated from day one for exactly this reason; `batch_type` never did, which is how the
    `batch_00000` literal and the `== "follow-up"` branches became load-bearing."""
    if value not in BATCH_TYPES:
        raise ValueError(f"batch_type must be one of {BATCH_TYPES} (got {value!r})")
    return value


def default_redo_attempted(batch_type: str) -> bool:
    """What a COMPOSER declares for a freshly built batch of this type. Composition-time only —
    never a read-path fallback (that is `redoes_attempted`'s legacy branch, which deliberately
    disagrees with this for `benchmark`)."""
    return batch_type in _REDO_BY_DEFAULT


def redoes_attempted(batch: dict) -> bool:
    """Does this batch deliberately RE-RUN districts that already reached a later stage?

    True → Stage 2/3/4 reconcile treats every included district as todo regardless of on-disk state,
    and Stage 2 merges the new round into the prior one rather than replacing it.

    Reads the DECLARED `redo_attempted` when present; falls back to the historical
    ``batch_type == 'follow-up'`` rule when it is absent or NULL, so every pre-#617 batch row and
    on-disk receipt keeps its exact prior behavior."""
    declared = batch.get("redo_attempted")
    if declared is not None:
        return bool(declared)
    return batch.get("batch_type") == FOLLOW_UP
