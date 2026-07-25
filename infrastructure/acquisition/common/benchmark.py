"""THE definition of "is this benchmark?" for the whole pipeline (epic #617).

Before this module the rule lived in **three hand-maintained copies**, each carrying a comment
explaining why it should have one definition:

  * ``stage9_incorporate/incorporate.py::_is_benchmark_district`` — *"mirrors
    stage7_execute._benchmark_district_ids, which Stage 9 cannot import: process_governance sits
    ABOVE this layer"*
  * ``process_governance/stage7_execute.py::_benchmark_district_ids`` (#134)
  * ``process_governance/server.py::IS_BENCHMARK_SQL`` — *"a rule this load-bearing gets ONE
    definition so a future change can't silently leave the gates disagreeing about what's benchmark"*

The layering constraint that forced the duplication is real (``stage9_incorporate`` may not import
``process_governance``), but ``common`` is the base layer every stage may import — so the rule belongs
here. A fourth copy lived inline in ``stage7_run._early_exit_targets`` and a fifth in
``maintenance/backfill_receipts.load_benchmark_ids``; both now read this module too.

**Grain matters, and it is about to change.** Everything here is *district-membership* grain — "has this
district EVER been in a ``batch_type='benchmark'`` batch". That is the pre-#619 semantics, preserved
byte-for-byte so the consolidation is a pure refactor. Epic #617's whole thesis is that this grain is
wrong for a *write* decision: ``batch_district`` rows are never deleted, so a district honestly re-run
through a production batch still matches forever, and its correct facts are refused at Stage 9 (#619).

When #619 lands, the write-eligibility guards move to **provenance** grain — "did the fact under
consideration come from a benchmark DISPATCH" — which will live here alongside these, NOT replace them:
membership stays the right question for genuinely batch-grain callers (e.g. Stage 5's zero-yield
escalation, which asks about the source batch). Read the grain in the function name, never assume.

**Fail-closed asymmetry is deliberate, not an oversight.** ``is_benchmark_district`` tolerates ONLY a
missing table (a fresh governance DB) and lets every other error propagate — a wall that can never
fail-open, so a transient DB fault cannot let a benchmark district through (PR #607 R2). The set-valued
readers do NOT carry that tolerance, matching their pre-consolidation behavior; a caller that wants to
degrade wraps the call itself (``stage7_run._early_exit_targets`` does exactly that, advisory-style).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

BENCHMARK_BATCH_TYPE = "benchmark"

# Embeddable correlated-EXISTS fragment for callers that need this inside a larger query's WHERE/SELECT
# (the console's district lists). `{alias}` = the outer query's district-bearing table alias.
# Keys on batch_type membership, NEVER the `batch_00000` id literal — the GT corpus grows into new
# benchmark batches, and a literal silently denies a second one whatever the guard was protecting
# (that exact bug was #621, in stage7_run._early_exit_targets).
IS_BENCHMARK_SQL = """EXISTS (SELECT 1 FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id
                              WHERE bd.district_id = {alias}.district_id
                                AND b.batch_type = 'benchmark')"""

_IDS_SQL = text(
    "SELECT DISTINCT bd.district_id FROM batch_district bd "
    "JOIN batch b ON b.batch_id = bd.batch_id "
    "WHERE b.batch_type = 'benchmark' AND bd.district_id = ANY(:d)")

_ONE_SQL = text(
    "SELECT 1 FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id "
    "WHERE b.batch_type = 'benchmark' AND bd.district_id = :d LIMIT 1")

_ALL_SQL = text(
    "SELECT DISTINCT bd.district_id FROM batch_district bd "
    "JOIN batch b ON b.batch_id = bd.batch_id WHERE b.batch_type = 'benchmark'")


def benchmark_district_ids(session, district_ids) -> set:
    """The subset of `district_ids` belonging to ANY benchmark batch. Empty input short-circuits
    without a query (`ANY(:d)` on an empty list is a needless round trip). Errors PROPAGATE — a caller
    that wants to degrade wraps this itself."""
    ids = list(district_ids)
    if not ids:
        return set()
    return {r[0] for r in session.execute(_IDS_SQL, {"d": ids})}


def is_benchmark_district(session, district_id: str) -> bool:
    """True when the district belongs to ANY benchmark batch — the FAIL-CLOSED single-district form
    Stage 9's write wall uses. Only a MISSING batch/batch_district table (a fresh governance DB) is
    treated as not-benchmark; every other error propagates, so a transient DB fault can never let a
    benchmark district through (PR #607 R2)."""
    try:
        return bool(session.execute(_ONE_SQL, {"d": district_id}).first())
    except ProgrammingError:
        session.rollback()   # relation "batch"/"batch_district" does not exist — fresh DB, no members
        return False


def all_benchmark_district_ids(session) -> set:
    """Every district in any benchmark batch (no id filter) — the corpus-wide sweep form, for tools
    that tag or partition by benchmark provenance (the receipts backfill's `_benchmark` basename)."""
    return {r[0] for r in session.execute(_ALL_SQL)}
