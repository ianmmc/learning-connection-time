"""epic #617 — `common/benchmark.py` is THE definition of "is this benchmark?".

The rule previously lived in three hand-maintained copies (Stage 9's write wall, Stage 7's execution
wall, server.py's console fragment) plus two more inline (stage7_run's early-exit, the receipts
backfill). Each carried a comment saying it ought to have one definition; none could, because
`stage9_incorporate` may not import `process_governance`. `common` is the base layer, so it can.

These tests cover the predicate itself (govdb, real SQL) AND pin the consolidation with a fitness
function — the copies must not silently grow back.
"""
import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import db as gdb
from tests import benchmark_seed as BSEED

REPO = Path(__file__).resolve().parent.parent
ACQ = REPO / "infrastructure" / "acquisition"
govdb = pytest.mark.govdb


# --------------------------- the one-home guards: MOVED (#650) ---------------------------
# `test_the_predicate_has_exactly_one_home`, the provenance-arm twin, and both falsification corpora
# now live in `tests/test_one_home_fitness.py` as rows of a declared table covering the whole
# one-home CLASS. The epic wrote a bespoke guard for this rule, then introduced three more rules and
# hand-copied every one of them; the guard could not see them because it protected a rule rather
# than a class. What stays here is what is specific to THIS predicate: its shape, its arms, and its
# behaviour against real SQL.


def test_the_sql_fragment_keys_on_type_never_the_batch_00000_literal():
    """#621's lesson, pinned: the id literal silently denies a second benchmark batch whatever the
    guard was protecting. Every form here keys on batch_type."""
    forms = [BM.IS_BENCHMARK_SQL, str(BM._IDS_SQL), str(BM._ONE_SQL), str(BM._ALL_SQL)]
    for sql in forms:
        assert "batch_type = 'benchmark'" in sql
        assert "batch_00000" not in sql


def test_the_fragment_is_alias_parameterized_and_formats():
    """server.py embeds this inside a larger query under two different table aliases."""
    for frag in (BM.IS_BENCHMARK_SQL, BM.IS_BENCHMARK_PROVENANCE_SQL):
        assert "{alias}" in frag
        rendered = frag.format(alias="p")
        assert "p.district_id" in rendered and "{alias}" not in rendered


def test_the_provenance_fragment_scopes_to_production_extractions():
    """A probe (#148) is an experiment, not a release path. Folding probes into the wall would hide a
    district from gate@8 for a council A/B it never released — the coarse-unit harm again."""
    assert BM.IS_BENCHMARK_PROVENANCE_SQL.count("e.run_kind = 'production'") == 2   # once per arm


def test_the_provenance_predicate_has_both_arms_and_needs_both():
    """The two arms answer different questions and neither subsumes the other (#619 / findings §11.4):
    arm 1 cannot see a production dispatch that pulled in an injected rep (the real mixed handoff);
    arm 2 cannot see a benchmark dispatch composed entirely of production reps."""
    assert "dispatch_type = 'benchmark'" in BM.IS_BENCHMARK_PROVENANCE_SQL
    assert "c.source = 'benchmark_gt'" in BM.IS_BENCHMARK_PROVENANCE_SQL
    assert BM.IS_BENCHMARK_PROVENANCE_SQL.count("EXISTS") == 2


def test_provenance_empty_input_short_circuits_without_a_session():
    """Both arms skip the round trip on empty input, so a caller holding neither identifier (a receipt
    of purely human-added facts) never touches the DB — and is not walled."""
    assert BM.benchmark_dispatch_fact_ids(None, []) == set()
    assert BM.is_benchmark_provenance(None, rec_keys=(), fact_ids=()) is False


def test_empty_input_short_circuits_without_a_session():
    """`ANY(:d)` on an empty list is a needless round trip — and this lets callers skip the guard
    entirely on an empty batch. Passing None as the session proves no query is issued."""
    assert BM.benchmark_district_ids(None, []) == set()


# --------------------------- the real SQL (govdb) ---------------------------

def _seed(s, batch_id, batch_type, *district_ids):
    from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict
    s.add(Batch(batch_id=batch_id, batch_type=batch_type, status="approved", nces_year="2024_25",
                created_at="t", created_by="zz", meta_json={}))
    for i, did in enumerate(district_ids):
        s.add(BatchDistrict(batch_id=batch_id, district_id=did, ord=i, name="ZZ", state="AK",
                            domain="", enrollment_k12=None, lea_claimed_bands=[],
                            nces_school_counts={}, band_processing_order=[], band_meta={},
                            included=True))
    s.flush()


@govdb
def test_membership_is_by_type_across_any_benchmark_batch(gov_session):
    gdb.init_precious_schema()
    s = gov_session
    _seed(s, "batch_zzbm_a", "benchmark", "ZZBMA")
    _seed(s, "batch_zzbm_b", "benchmark", "ZZBMB")       # a SECOND benchmark batch (not batch_00000)
    _seed(s, "batch_zzfr", "first-run", "ZZFR")

    got = BM.benchmark_district_ids(s, ["ZZBMA", "ZZBMB", "ZZFR", "ZZNOBODY"])
    assert got == {"ZZBMA", "ZZBMB"}
    assert BM.is_benchmark_district(s, "ZZBMA") is True
    assert BM.is_benchmark_district(s, "ZZFR") is False
    assert BM.is_benchmark_district(s, "ZZNOBODY") is False


@govdb
def test_union_semantics_benchmark_membership_dominates(gov_session):
    """A district in BOTH a benchmark and a production batch reads as benchmark. This is the shape
    #617's re-run campaign creates for all 27 batch_00000 districts, and it is exactly why the
    district-MEMBERSHIP grain is wrong for a write decision (#619 moves those callers to provenance):
    the association is permanent, so honest fresh facts stay refused forever."""
    gdb.init_precious_schema()
    s = gov_session
    _seed(s, "batch_zzbm_c", "benchmark", "ZZBOTH")
    _seed(s, "batch_zzfu_c", "follow-up", "ZZBOTH")
    assert BM.benchmark_district_ids(s, ["ZZBOTH"]) == {"ZZBOTH"}
    assert BM.is_benchmark_district(s, "ZZBOTH") is True


@govdb
def test_sql_fragment_agrees_with_the_python_helpers(gov_session):
    """The embeddable fragment and the helpers must never disagree about what's benchmark — they are
    the same rule in two shapes, and the console (fragment) vs the walls (helpers) must not diverge."""
    gdb.init_precious_schema()
    s = gov_session
    _seed(s, "batch_zzbm_d", "benchmark", "ZZAGREE1")
    _seed(s, "batch_zzfr_d", "first-run", "ZZAGREE2")
    s.execute(text("CREATE TEMP TABLE zz_dists (district_id text) ON COMMIT DROP"))
    s.execute(text("INSERT INTO zz_dists VALUES ('ZZAGREE1'), ('ZZAGREE2')"))

    via_sql = {r[0] for r in s.execute(text(
        f"SELECT district_id FROM zz_dists p WHERE {BM.IS_BENCHMARK_SQL.format(alias='p')}"))}
    via_py = BM.benchmark_district_ids(s, ["ZZAGREE1", "ZZAGREE2"])
    assert via_sql == via_py == {"ZZAGREE1"}


@govdb
def test_all_benchmark_district_ids_is_a_superset_of_a_filtered_lookup(gov_session):
    """The corpus-wide sweep form (the receipts backfill's `_benchmark` tagging) must agree with the
    filtered form on any district it is asked about."""
    gdb.init_precious_schema()
    s = gov_session
    _seed(s, "batch_zzbm_e", "benchmark", "ZZSWEEP")
    everyone = BM.all_benchmark_district_ids(s)
    assert "ZZSWEEP" in everyone
    assert BM.benchmark_district_ids(s, ["ZZSWEEP"]) <= everyone


# --------------------------- the PROVENANCE predicate (govdb, #619) ---------------------------

def _seed_prov(s, did, rec_key, hash_, source, *, dispatch_type=None):
    """A district's rep (the arm-2 path) and optionally a whole run stamped with `dispatch_type`
    (the arm-1 path). Returns the fact_id when a run was made. Thin wrapper over the shared seeders
    in `tests/benchmark_seed.py` (#661) — the SQL lives there, once."""
    BSEED.ensure_schema(s)
    if dispatch_type is None:
        BSEED.seed_rep(s, did, rec_key, hash_, source)
        return None
    _eid, fid = BSEED.seed_run(s, did, rec_key=rec_key, hash_=hash_, source=source,
                               dispatch_type=dispatch_type)
    return fid


@govdb
def test_arm2_sees_an_injected_rep_in_an_ordinary_production_dispatch(gov_session):
    """The MIXED case, which is the whole reason arm 1 alone is not enough: a genuine production
    dispatch that pulled in a curated-GT PDF. Real instance: `f33790e63820`, 3 reps in 3 of its 9
    districts, 227 accepted facts held back by nothing but the wall #619 retires."""
    gdb.init_precious_schema()
    s = gov_session
    fid = _seed_prov(s, "ZZPV1", "ZZPV1:gt", "gt1", BM.BENCHMARK_CAPTURE_SOURCE,
                     dispatch_type=BM.DISPATCH_PRODUCTION)
    assert BM.benchmark_dispatch_fact_ids(s, [fid]) == set()          # arm 1 sees nothing…
    assert BM.benchmark_provenance_rec_keys(s, ["ZZPV1:gt"]) == {"ZZPV1:gt"}   # …arm 2 does
    assert BM.is_benchmark_provenance(s, rec_keys=["ZZPV1:gt"], fact_ids=[fid]) is True


@govdb
def test_arm1_sees_a_benchmark_dispatch_built_only_from_production_reps(gov_session):
    """The converse, which is why arm 2 alone is not enough either: a Council Lab A/B composed
    entirely of ordinary discovered reps carries no rep-level signal at all."""
    gdb.init_precious_schema()
    s = gov_session
    fid = _seed_prov(s, "ZZPV2", "ZZPV2:ok", "ok2", "discovered",
                     dispatch_type=BM.DISPATCH_BENCHMARK)
    assert BM.benchmark_provenance_rec_keys(s, ["ZZPV2:ok"]) == set()          # arm 2 sees nothing…
    assert BM.benchmark_dispatch_fact_ids(s, [fid]) == {fid}                   # …arm 1 does
    assert BM.is_benchmark_provenance(s, rec_keys=["ZZPV2:ok"], fact_ids=[fid]) is True


@govdb
def test_an_ordinary_production_district_is_not_benchmark_provenance(gov_session):
    """Neither arm fires on honest production work — the case #619 exists to UNBLOCK. Note the
    district is also seeded into a benchmark BATCH: membership says benchmark, provenance says no,
    and provenance is what a write decision must ask."""
    gdb.init_precious_schema()
    s = gov_session
    fid = _seed_prov(s, "ZZPV3", "ZZPV3:ok", "ok3", "discovered",
                     dispatch_type=BM.DISPATCH_PRODUCTION)
    _seed(s, "batch_zzpv3_bm", "benchmark", "ZZPV3")
    assert BM.is_benchmark_district(s, "ZZPV3") is True                        # membership: walled
    assert BM.is_benchmark_provenance(s, rec_keys=["ZZPV3:ok"], fact_ids=[fid]) is False


@govdb
def test_the_provenance_fragment_and_the_helper_agree(gov_session):
    """The embeddable fragment (gate@8's queue) and the helper (Stage 9's wall) are the same rule in
    two shapes — asked of the live facts and of the frozen receipt. They must not diverge, for the
    same reason the membership pair must not: the gate that authorizes the write and the write itself
    disagreeing about what is walled is how a benchmark fact reaches production."""
    gdb.init_precious_schema()
    s = gov_session
    f1 = _seed_prov(s, "ZZPVA", "ZZPVA:gt", "gta", BM.BENCHMARK_CAPTURE_SOURCE,
                    dispatch_type=BM.DISPATCH_PRODUCTION)
    f2 = _seed_prov(s, "ZZPVB", "ZZPVB:ok", "okb", "discovered",
                    dispatch_type=BM.DISPATCH_PRODUCTION)
    s.execute(text("CREATE TEMP TABLE zz_pv (district_id text) ON COMMIT DROP"))
    s.execute(text("INSERT INTO zz_pv VALUES ('ZZPVA'), ('ZZPVB')"))

    via_sql = {r[0] for r in s.execute(text(
        f"SELECT district_id FROM zz_pv p WHERE {BM.IS_BENCHMARK_PROVENANCE_SQL.format(alias='p')}"))}
    via_py = {d for d, k, f in (("ZZPVA", "ZZPVA:gt", f1), ("ZZPVB", "ZZPVB:ok", f2))
              if BM.is_benchmark_provenance(s, rec_keys=[k], fact_ids=[f])}
    assert via_sql == via_py == {"ZZPVA"}


# --------------------------- #644: every freeze path is guarded ---------------------------
# The #618 provenance guard shipped with ONE call site against THREE freeze paths. That class of
# defect — a rule that is correct where it is applied and simply ABSENT elsewhere — is invisible to
# every test of the guard itself, so the durable fix is to count the guarded OPERATION rather than
# to test the guard again. Grep the operation, not the guard (findings report §12.7).
_FREEZE_CALL = re.compile(r"\bHND\.freeze\s*\(")
# The guard counts either directly or through a SANCTIONED wrapper. `_refuse_benchmark_reps` is the
# back-edge adapter: same guard, but returning this-module's `{"ok": False, "reason": ...}` refusal
# rather than raising, because those two callers are console actions whose contract is a refusal dict.
# Naming wrappers explicitly (rather than accepting any call whose name contains "benchmark") keeps
# the detector honest — a new indirection has to be added here deliberately, which is the review point.
_GUARD_CALL = re.compile(r"(?:assert_dispatch_type_allowed|_refuse_benchmark_reps)\s*\(")


def test_every_freeze_call_site_is_preceded_by_the_provenance_guard():
    """A frozen handoff is IMMUTABLE, so a wrong `dispatch_type` is unrecoverable — the guard has to
    run before every freeze, not before the one the author remembered.

    Scoped per-function: the guard must appear in the same function body as the freeze, above it.
    A module-level count would pass on a file that guards one path twice and another not at all,
    which is exactly the shape of the defect being pinned."""
    offenders = []
    for py in ACQ.rglob("*.py"):
        src = py.read_text()
        if not _FREEZE_CALL.search(src):
            continue
        tree = ast.parse(src)
        for fn in (n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
            body = ast.get_source_segment(src, fn) or ""
            fm = _FREEZE_CALL.search(body)
            if not fm:
                continue
            gm = _GUARD_CALL.search(body)
            if gm is None or gm.start() > fm.start():
                offenders.append(f"{py.relative_to(REPO)}::{fn.name}")
    assert not offenders, (
        "these functions freeze a handoff without first calling assert_dispatch_type_allowed — a "
        "production dispatch could carry benchmark-provenance representations into an IMMUTABLE "
        "artifact (#644):\n  " + "\n  ".join(offenders))


def test_the_freeze_detector_would_have_caught_the_644_defect():
    """Falsification: the pre-#644 body of `_bundle_alternate`, verbatim in shape. A fitness function
    that cannot be shown to fail on the real defect it was written for is decoration."""
    pre_644 = '''
def _bundle_alternate(s, district_id, actor, root):
    package = PKG6.assemble_package(districts_input, councils, cost_model, overrides)
    package["verified_only"] = False
    fps = {district_id: REL.district_fingerprints(s, district_id)}
    doc = HND.freeze(package, councils, fps, created_by=actor)
'''
    fm = _FREEZE_CALL.search(pre_644)
    gm = _GUARD_CALL.search(pre_644)
    assert fm is not None and gm is None, "the detector would not have caught the #644 defect"


# --------------------------- #651: where run_kind scoping belongs ---------------------------
# Not a style rule. A query that ENUMERATES a district's history must scope to production (a probe
# is not a release path); a query asked about identifiers THE CALLER ALREADY SELECTED must not —
# narrowing there only removes rows the caller asked about, which on a fail-closed wall is the
# fail-OPEN direction. Pinned in both directions so neither can be "made consistent" by accident.

def test_the_enumerating_queries_scope_to_production_and_the_caller_selected_ones_do_not():
    assert BM.IS_BENCHMARK_PROVENANCE_SQL.count("e.run_kind = 'production'") == 2   # both arms
    prov_reqs = str(BM._BENCH_PROV_REQUESTS_SQL)
    assert prov_reqs.count("e.run_kind = 'production'") == 1     # arm 2 enumerates; arm 1 needn't
    # the caller-selected pair: adding a run_kind filter here would fail OPEN
    assert "run_kind" not in str(BM._REC_PROV_SQL)
    assert "run_kind" not in str(BM._BENCH_DISPATCH_FACTS_SQL)


@govdb
def test_a_probe_touching_an_injected_rep_does_not_wall_a_production_directive(gov_session):
    """`extraction` is append-only, so (handoff_hash, district_id) can match several runs and the
    directive names none of them. Before #651 a probe that read one gt:// rep walled every
    production directive raised against the same handoff — for an experiment never released."""
    gdb.init_precious_schema()
    s = gov_session
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    BS.ensure_signal_schema(s)
    CI.ensure_cache_schema(s)
    hh = "zzh651probe"
    BSEED.seed_handoff(s, hh, dispatch_type=BM.DISPATCH_PRODUCTION)
    s.execute(text("INSERT INTO record (rec_key, district_id, url, hash, tier) "
                   "VALUES ('ZZ651:gt', 'ZZ651', 'http://x/g', 'zz651g', 'A')"))
    s.execute(text("INSERT INTO capture (district_id, hash, url, ok, kind, source) "
                   "VALUES ('ZZ651', 'zz651g', 'http://x/g', 1, 'html', :s)"),
              {"s": BM.BENCHMARK_CAPTURE_SOURCE})
    # the PROBE run is the only one that read the injected rep
    for kind, rec in (("probe", "ZZ651:gt"), ("production", None)):
        eid = s.execute(text(
            "INSERT INTO extraction (handoff_hash, district_id, run_kind, created_at, created_by, "
            "n_reps, n_calls, n_judge_calls, n_errors, prompt_tokens, completion_tokens, cost_usd, "
            "n_accepted, n_unresolved) VALUES (:hh, 'ZZ651', :rk, 'now', 'zz', 1, 1, 0, 0, 0, 0, "
            "0.0, 1, 0) RETURNING extraction_id"), {"hh": hh, "rk": kind}).scalar()
        if rec:
            s.execute(text(
                "INSERT INTO school_fact (extraction_id, district_id, band, school, status, rec_key, "
                "created_at, human_determination) VALUES (:e, 'ZZ651', 'high', 'oak', 'accepted', "
                ":k, 'now', '')"), {"e": eid, "k": rec})
    rid = s.execute(text(
        "INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, reason, "
        "status, created_at) VALUES ('ZZ651', :hh, 'district', '7->2', 'ZZ651', 'zz', 'approved', "
        "'now') RETURNING request_id"), {"hh": hh}).scalar()
    s.flush()

    assert BM.benchmark_provenance_request_ids(s, [rid]) == set()


# --------------------------- #654: the fail-closed catch is narrow ---------------------------

def test_only_a_missing_table_is_tolerated_not_any_programming_error():
    """The docstrings have always said "ONLY a missing table"; before #654 the `except` clause said
    ProgrammingError, which is also what a renamed column or a SQL typo raises. Swallowing THOSE
    answers "not benchmark" because the guard could not ask — fail-OPEN on a fail-closed wall."""
    from sqlalchemy.exc import ProgrammingError

    class _Orig(Exception):
        def __init__(self, pgcode):
            self.pgcode = pgcode

    missing = ProgrammingError("stmt", {}, _Orig("42P01"))
    renamed = ProgrammingError("stmt", {}, _Orig("42703"))       # undefined_column
    assert BM._is_undefined_table(missing) is True
    assert BM._is_undefined_table(renamed) is False
    # no pgcode at all (a driver or a mock): fall back to the message, never crash a real fresh DB
    assert BM._is_undefined_table(ProgrammingError('relation "handoff" does not exist', {}, None)) \
        is True
    assert BM._is_undefined_table(ProgrammingError("syntax error at or near", {}, None)) is False


def test_a_non_missing_table_fault_propagates_out_of_both_fail_closed_predicates(monkeypatch):
    """Asserted on the real functions, not on the helper — the helper being right is worthless if a
    call site still catches the whole class."""
    from sqlalchemy.exc import ProgrammingError

    class _Orig(Exception):
        pgcode = "42703"

    class _Sess:
        def execute(self, *a, **k):
            raise ProgrammingError("stmt", {}, _Orig())

        def rollback(self):
            raise AssertionError("must not swallow a real SQL fault")

    with pytest.raises(ProgrammingError):
        BM.is_benchmark_district(_Sess(), "ZZ654")
    with pytest.raises(ProgrammingError):
        BM.is_benchmark_provenance(_Sess(), rec_keys=["ZZ654:x"])


def test_a_missing_table_still_reads_as_not_benchmark():
    """The tolerance #654 narrowed must survive narrowing — a fresh governance DB with no dispatch
    history has no provenance, and that is not an error."""
    from sqlalchemy.exc import ProgrammingError

    class _Orig(Exception):
        pgcode = "42P01"

    class _Sess:
        rolled = False

        def execute(self, *a, **k):
            raise ProgrammingError("stmt", {}, _Orig())

        def rollback(self):
            self.rolled = True

    s = _Sess()
    assert BM.is_benchmark_district(s, "ZZ654") is False
    assert BM.is_benchmark_provenance(s, rec_keys=["ZZ654:x"]) is False
    assert s.rolled is True
