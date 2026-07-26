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

**Grain matters, and THREE grains live here.** Read the grain in the function name, never assume:

  * *district-membership* — "has this district EVER been in a ``batch_type='benchmark'`` batch"
    (``is_benchmark_district`` / ``benchmark_district_ids`` / the ``IS_BENCHMARK_SQL`` fragment).
    Permanent by construction: ``batch_district`` rows are never deleted, which is the WRONG question
    for any decision about releasing work — that was #619's bug — and it is why nothing that gates a
    write, a spend, or a dispatch reads these any more. Live production callers after #620:
    ``all_benchmark_district_ids`` (the receipts backfill's ``_benchmark`` basename) and
    ``IS_BENCHMARK_SQL`` (the gate@6 console BADGE, where "this district is part of the yardstick
    corpus" is true and useful to an operator). ``is_benchmark_district`` and
    ``benchmark_district_ids`` currently have no production caller and are kept on purpose: tests
    need membership as the CONTRAST to provenance, and this module is the only place permitted to
    spell that SQL, so removing them would force a re-inlined JOIN the fitness function rejects.
    (Stage 5's zero-yield escalation is batch-grain and never used these — it compares
    ``Batch.batch_type`` on the ORM row.)
  * *representation* — "did this rep's capture come from benchmark injection"
    (``benchmark_provenance_rec_keys``, keyed on ``capture.source='benchmark_gt'``).
  * *provenance* — "did the FACT under consideration come from benchmark work" (``is_benchmark_provenance``
    and its two arms). This is what every write-eligibility guard asks post-#619.

**The provenance predicate has TWO ARMS, and neither is redundant** (#619, from the 39-handoff census
in the epic's findings report §11.4). Arm 1 is the STAMPED signal — ``handoff.dispatch_type='benchmark'``
(#618) — which is the only thing that can see a future Council Lab A/B composed entirely of *production*
reps. Arm 2 is the DERIVED signal — the fact's own rep carries benchmark provenance — which is the only
thing that can see the one real MIXED artifact (``f33790e63820``: a genuine production dispatch that
pulled three ``gt://`` curated PDFs into 3 of its 9 districts). Dispatch grain alone answers that one
wrong in *both* directions, which is why the guard is not simply "was this a benchmark dispatch".

Deriving arm 2 rather than back-stamping the handoffs is deliberate: the two pure-benchmark artifacts
are immutable frozen files that PREDATE ``dispatch_type``, so stamping their DB rows would leave each
row disagreeing with its own receipt — and the receipt is the auditable record. (This retired the
epic's planned Phase 2e.)

**Fail-closed asymmetry is deliberate, not an oversight.** ``is_benchmark_district`` tolerates ONLY a
missing table (a fresh governance DB) and lets every other error propagate — a wall that can never
fail-open, so a transient DB fault cannot let a benchmark district through (PR #607 R2). The set-valued
readers do NOT carry that tolerance, matching their pre-consolidation behavior; a caller that wants to
degrade wraps the call itself (``stage7_run._early_exit_targets`` does exactly that, advisory-style).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from infrastructure.acquisition.common.batch_types import BENCHMARK as BENCHMARK_BATCH_TYPE  # noqa: F401 (re-export)

# The DISPATCH axis (#618). Batches organize Stages 1-4; dispatches organize Stages 6-7 — there is no
# first-run/follow-up notion for a dispatch, so this is the ONLY dispatch type axis. A benchmark
# dispatch is the Stages-6/7 A/B harness (which representations to which councils, and the yield) and
# TERMINATES AT gate@7, which is what makes benchmark output structurally incapable of reaching Stage 9.
DISPATCH_PRODUCTION = "production"
DISPATCH_BENCHMARK = "benchmark"
DISPATCH_TYPES = (DISPATCH_PRODUCTION, DISPATCH_BENCHMARK)


def effective_dispatch_type(doc: dict) -> str:
    """The dispatch type of a package / frozen handoff doc / API payload, defaulting an absent or
    empty value to production (#650).

    Every artifact predating #618 is unstamped, and back-stamping was rejected (arm 2 derives the
    answer for historical work — see the module docstring), so the fallback is permanent rather than
    a migration window. It shipped as `X.get("dispatch_type") or DISPATCH_PRODUCTION` hand-copied at
    8 sites across 4 files — including the freeze refusal and the mode-stability gate, which must
    never disagree about the same doc's effective type. The consolidation the epic performed on the
    benchmark predicate, applied to the rule the epic itself introduced.

    Deliberately NOT validating: this is a read-path default over data already on disk, and a stored
    junk value must surface as a mismatch at the gate that cares (`validate_dispatch_type` at the
    write path), not be swallowed here."""
    return doc.get("dispatch_type") or DISPATCH_PRODUCTION


def is_benchmark_dispatch(doc: dict) -> bool:
    """Does this doc describe a BENCHMARK dispatch? The predicate form of `effective_dispatch_type`,
    for the call sites that only ever compare (the freeze refusal, the early-exit gate)."""
    return effective_dispatch_type(doc) == DISPATCH_BENCHMARK


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


# ---------------------------------------------------------------------------
# PROVENANCE grain (#619) — "did the fact under consideration come from benchmark work"
# ---------------------------------------------------------------------------
# The write-eligibility question, and the one the district-membership guards were WRONGLY answering.
# Two arms (see the module docstring); a caller supplies whichever identifiers it holds and the arms
# it can't feed simply don't fire.
#
# Measured against the live governance DB 2026-07-26, across all 83 districts holding production facts:
# membership and arm 2 agree on ALL 83 (27 benchmark either way, zero disagreements), and every
# benchmark district's production facts are ENTIRELY benchmark-provenance (`any` == `all`). So the
# re-key is behaviour-preserving TODAY — including for the mixed handoff's three districts, whose 227
# accepted facts stay walled. The two grains diverge only once #620's re-run mints fresh production
# reps for a district that also holds injected ones, which is exactly the case #617 exists to unblock.
# Arm 1 fires on nothing today (all 39 handoff rows are `dispatch_type='production'`, the two
# pure-benchmark artifacts included — see the no-back-stamping note in the module docstring); it is
# the forward-looking arm, stamped by #618 on every dispatch frozen from now on.

# Embeddable correlated-EXISTS fragment, the provenance twin of IS_BENCHMARK_SQL, for callers that
# need this inside a larger query (the gate@8 review queue). `{alias}` = the outer query's
# district-bearing table alias. Both arms, scoped to PRODUCTION extractions — a probe is not a
# release path, and folding probes in would wall a district for an experiment it never released.
# It reads the LIVE facts rather than a frozen receipt because a queue exists before any approval
# does; Stage 9's wall re-asks the same question of the receipt it actually writes from.
IS_BENCHMARK_PROVENANCE_SQL = """(
  EXISTS (SELECT 1 FROM extraction e JOIN handoff h ON h.handoff_hash = e.handoff_hash
          WHERE e.district_id = {alias}.district_id AND e.run_kind = 'production'
            AND h.dispatch_type = 'benchmark')
  OR EXISTS (SELECT 1 FROM extraction e
             JOIN school_fact f ON f.extraction_id = e.extraction_id
             JOIN record r ON r.rec_key = f.rec_key
             JOIN capture c ON c.district_id = r.district_id AND c.hash = r.hash
             WHERE e.district_id = {alias}.district_id AND e.run_kind = 'production'
               AND c.source = 'benchmark_gt'))"""

_BENCH_DISPATCH_FACTS_SQL = text(
    "SELECT DISTINCT f.fact_id FROM school_fact f "
    "JOIN extraction e ON e.extraction_id = f.extraction_id "
    "JOIN handoff h ON h.handoff_hash = e.handoff_hash "
    "WHERE h.dispatch_type = :dt AND f.fact_id = ANY(:f)")


def benchmark_dispatch_fact_ids(session, fact_ids) -> set:
    """ARM 1: the subset of `fact_ids` produced by a run against a BENCHMARK dispatch.

    Keyed by FACT rather than by handoff hash because that is what the callers hold — the frozen
    receipt names its facts, not its dispatches. A handoff-keyed form is the obvious sibling and is
    deliberately absent until something needs it (the deferred #134 re-key would, §12.6).

    The join is fact -> extraction -> handoff, because `school_fact` carries no dispatch link of its
    own. A fact whose row has since been deleted contributes nothing — which is safe here only because
    arm 2 keys on the same facts' `rec_key`, and `school_fact` is precious/append-only anyway."""
    ids = list(fact_ids)
    if not ids:
        return set()
    return {r[0] for r in session.execute(
        _BENCH_DISPATCH_FACTS_SQL, {"dt": DISPATCH_BENCHMARK, "f": ids})}


_BENCH_PROV_REQUESTS_SQL = text("""
SELECT DISTINCT er.request_id FROM extraction_request er
JOIN handoff h ON h.handoff_hash = er.handoff_hash
WHERE h.dispatch_type = :dt AND er.request_id = ANY(:r)
UNION
SELECT DISTINCT er.request_id FROM extraction_request er
JOIN extraction e ON e.handoff_hash = er.handoff_hash AND e.district_id = er.district_id
JOIN school_fact f ON f.extraction_id = e.extraction_id
JOIN record rec ON rec.rec_key = f.rec_key
JOIN capture c ON c.district_id = rec.district_id AND c.hash = rec.hash
WHERE c.source = :src AND er.request_id = ANY(:r)""")


def benchmark_provenance_request_ids(session, request_ids) -> set:
    """The subset of gate@7 directives (`extraction_request`) that ORIGINATE in benchmark work — the
    #134 request-execution guard, re-keyed from district membership to provenance (#619/#620).

    A directive is a finding OF an extraction, so its provenance is that extraction's: the same two
    arms, at `(handoff × district)` grain — arm 1 the stamped `handoff.dispatch_type`, arm 2 the reps
    behind the facts that extraction produced. `extraction_request` carries `handoff_hash` +
    `district_id`, which is exactly the key both arms need.

    WHAT THIS DOES AND DOES NOT STOP. It stops an EXPERIMENT from silently seeding production work: a
    benchmark dispatch terminates at gate@7, so its findings must not compose themselves into a
    production follow-up batch. It does NOT stop a district that has benchmark history from acting on
    directives its PRODUCTION runs produced — that is mobility property 1, and forbidding it was the
    #134 defect. Rep-grain contamination on the dispatch-building back-edges is a separate concern,
    covered at freeze by `assert_dispatch_type_allowed` (#618/#644).

    Errors PROPAGATE. Unlike `is_benchmark_provenance`'s fresh-DB tolerance there is no fresh-DB case
    here — a directive cannot exist without the extraction that raised it."""
    ids = list(request_ids)
    if not ids:
        return set()
    return {r[0] for r in session.execute(
        _BENCH_PROV_REQUESTS_SQL,
        {"dt": DISPATCH_BENCHMARK, "src": BENCHMARK_CAPTURE_SOURCE, "r": ids})}


def is_benchmark_provenance(session, *, rec_keys=(), fact_ids=()) -> bool:
    """True when ANY of the supplied facts/reps carries benchmark provenance by EITHER arm — the
    write-eligibility wall Stage 9 asks (#619), replacing the district-membership question.

    ANY, not ALL, and deliberately: one injected `gt://` rep among a district's evidence is enough to
    taint the band value it feeds, so this REFUSES rather than silently dropping the tainted fact —
    the same "never let a guard whose unit is coarser than its trigger coerce an answer" posture that
    made #618's freeze refuse. The auditable way to satisfy it is for a human to strike the stale
    evidence at gate@8 (`band_exclusion`, #257), which removes those schools from the receipt's
    write-bearing set before this ever sees them.

    Fail-closed like `is_benchmark_district`, and for the same PR #607 R2 reason: ONLY a missing table
    (a fresh governance DB with no dispatch history at all) reads as not-benchmark; every other error
    propagates, so a transient DB fault can never let benchmark data through. Note this is the opposite
    tolerance from bare `benchmark_provenance_rec_keys`, which feeds the gate@6 freeze — there a loud
    failure is recoverable (retry the freeze) and there is no fresh-DB case to tolerate."""
    try:
        if benchmark_dispatch_fact_ids(session, fact_ids):
            return True
        return bool(benchmark_provenance_rec_keys(session, rec_keys))
    except ProgrammingError:
        session.rollback()   # relation "handoff"/"record"/"capture" absent — fresh DB, no provenance
        return False
