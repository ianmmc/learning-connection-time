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

# The DISPATCH axis (#618). Batches organize Stages 1-4; dispatches organize Stages 6-7 — there is no
# first-run/follow-up notion for a dispatch, so this is the ONLY dispatch type axis. A benchmark
# dispatch is the Stages-6/7 A/B harness (which representations to which councils, and the yield) and
# TERMINATES AT gate@7, which is what makes benchmark output structurally incapable of reaching Stage 9.
DISPATCH_PRODUCTION = "production"
DISPATCH_BENCHMARK = "benchmark"
DISPATCH_TYPES = (DISPATCH_PRODUCTION, DISPATCH_BENCHMARK)


def validate_dispatch_type(value: str) -> str:
    """Return `value` if it is a legal dispatch type, else raise. `batch_type` shipped as an
    unconstrained string with its legal values living only in a comment, which is how the
    `batch_00000` literal and the `== "follow-up"` branches became load-bearing — this axis validates
    from day one so a typo can never mint a third type that silently bypasses the termini."""
    if value not in DISPATCH_TYPES:
        raise ValueError(f"dispatch_type must be one of {DISPATCH_TYPES} (got {value!r})")
    return value

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


# ---------------------------------------------------------------------------
# REPRESENTATION grain (#618) — the provenance of a *thing*, not of a district
# ---------------------------------------------------------------------------
# `capture.source` is the ONLY durable representation-grain provenance signal in the schema:
# `record` and `representation` carry no batch_id, and `district`/`district_target` each hold a single
# batch_id that is OVERWRITTEN on re-ingest — so after a follow-up re-run they name the follow-up batch
# and the benchmark association is gone. `benchmark_batch.capture_record` stamps injected records
# `source='benchmark_gt'` (URL scheme `gt://…`), and `attribution.py` already consumes it, so it is an
# exercised field rather than a vestige.
#
# It also SURVIVES a re-run: Node's #174 follow-up seeding (`seedFromPriorCaptures`) pushes prior
# records verbatim into the new manifest, and `cache_ingest` upserts the union — so a re-run district
# legitimately holds benchmark_gt reps alongside fresh ones. That mixing is exactly why this grain is
# load-bearing: without it a reviewer could pull a stale `gt://` rep into a production dispatch and,
# post-#619, write injected older-school-year data into the LCT DB.
#
# Measured 2026-07-25 against the live governance DB: 95 benchmark_gt captures across all 27
# benchmark-batch districts, 0 benchmark_gt captures outside them, 0 benchmark districts without
# captures, and record->capture joins 1489/1489. So TODAY this grain and district-membership return
# identical answers; they diverge only once #620's re-run creates the mixed case.
BENCHMARK_CAPTURE_SOURCE = "benchmark_gt"

_REC_PROV_SQL = text(
    "SELECT DISTINCT r.rec_key FROM record r "
    "JOIN capture c ON c.district_id = r.district_id AND c.hash = r.hash "
    "WHERE c.source = :src AND r.rec_key = ANY(:k)")


def benchmark_provenance_rec_keys(session, rec_keys) -> set:
    """The subset of `rec_keys` whose underlying capture came from benchmark injection.

    Errors PROPAGATE — deliberately, and unlike `is_benchmark_district`'s fresh-DB tolerance. This
    feeds the gate@6 freeze decision, which bakes `dispatch_type` into an IMMUTABLE artifact: a loud
    failure is recoverable (the human retries the freeze), a silently-wrong type is not. There is also
    no fresh-DB case to tolerate — a dispatch cannot be composed at all without `record` rows."""
    keys = list(rec_keys)
    if not keys:
        return set()
    return {r[0] for r in session.execute(
        _REC_PROV_SQL, {"src": BENCHMARK_CAPTURE_SOURCE, "k": keys})}
