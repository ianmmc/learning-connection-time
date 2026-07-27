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

REPO = Path(__file__).resolve().parent.parent
ACQ = REPO / "infrastructure" / "acquisition"
govdb = pytest.mark.govdb


# --------------------------- the fitness function (DB-free) ---------------------------


# The predicate's SQL is written as ADJACENT STRING LITERALS across several source lines, so a naive
# line-by-line scan misses it — verified against the real pre-consolidation sources: it caught the
# backfill's one-line form but MISSED both stage7_execute's and incorporate's. Normalize first.
_JOINED_LITERALS = re.compile(r"[\"']\s*[\"']")          # "…" "…" (incl. across newlines) -> one string
# The quotes around 'benchmark' are OPTIONAL on purpose: joining adjacent literals can consume the
# value's own closing quote when it abuts the string's (`… = 'benchmark'"))` -> `… = 'benchmark))`).
# `batch_district` within 300 chars keeps it specific — prose mentioning batch_type alone won't trip.
_INLINE_PREDICATE = re.compile(r"batch_district\b.{0,300}?batch_type\s*=\s*'?benchmark", re.S)


def _normalize_source(src: str) -> str:
    """Collapse adjacent string literals + whitespace so a multi-line SQL string reads as one line."""
    return re.sub(r"\s+", " ", _JOINED_LITERALS.sub("", src))


def test_the_predicate_has_exactly_one_home():
    """No module outside common/benchmark.py may inline the benchmark JOIN. This is the guard against
    the exact regression epic #617 cleaned up: five copies that could drift apart, each carrying its
    own comment explaining why it shouldn't exist. A new call site imports the module; it never
    re-spells the SQL.

    `test_the_detector_catches_the_real_removed_copies` below proves this actually fires."""
    offenders = []
    for py in ACQ.rglob("*.py"):
        if py.name == "benchmark.py" and py.parent.name == "common":
            continue
        if _INLINE_PREDICATE.search(_normalize_source(py.read_text())):
            offenders.append(str(py.relative_to(REPO)))
    assert not offenders, (
        "the benchmark predicate was re-inlined instead of imported from common/benchmark.py:\n  "
        + "\n  ".join(offenders))


# The three copies epic #617 removed, verbatim, as the detector's falsification corpus. Embedded as
# literals rather than read from git on purpose: a `git show <ref>:<path>` lookup silently stops
# testing anything once the ref moves past the consolidation (and breaks in a shallow CI clone).
_REMOVED_COPIES = {
    "stage7_execute._benchmark_district_ids": '''
    rows = session.execute(text(
        "SELECT DISTINCT bd.district_id FROM batch_district bd "
        "JOIN batch b ON b.batch_id = bd.batch_id "
        "WHERE b.batch_type = 'benchmark' AND bd.district_id = ANY(:d)"),
        {"d": list(district_ids)})''',
    "incorporate._is_benchmark_district": '''
        return bool(gs.execute(text(
            "SELECT 1 FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id "
            "WHERE b.batch_type = 'benchmark' AND bd.district_id = :d LIMIT 1"),
            {"d": district_id}).first())''',
    "backfill_receipts.load_benchmark_ids": '''
    rows = session.execute(text(
        "SELECT DISTINCT bd.district_id FROM batch_district bd "
        "JOIN batch b ON b.batch_id = bd.batch_id WHERE b.batch_type = 'benchmark'"))''',
    "server.IS_BENCHMARK_SQL": '''
IS_BENCHMARK_SQL = """EXISTS (SELECT 1 FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id
                              WHERE bd.district_id = {alias}.district_id
                                AND b.batch_type = 'benchmark')"""''',
}


@pytest.mark.parametrize("name", sorted(_REMOVED_COPIES))
def test_the_detector_catches_the_real_removed_copies(name):
    """A fitness function nobody has falsified is decoration. Each of these is a copy that actually
    existed in this repo; the detector must trip on every one, or it would not catch a new one.

    This caught two real defects in the detector while it was being written: a line-by-line scan
    missed the two copies whose SQL spans adjacent string literals, and the literal-joining normalizer
    then ate the closing quote of `'benchmark'` where it abutted the enclosing string's quote."""
    assert _INLINE_PREDICATE.search(_normalize_source(_REMOVED_COPIES[name])), (
        f"detector failed to catch the known inline copy from {name}")


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


# The #619 provenance predicate gets the SAME one-home guard as the membership one, for the same
# reason: it is about to acquire call sites at three altitudes (the Stage-9 write wall, the gate@8
# queue, the request-execution guards), and five hand-copies is exactly how the membership rule got
# into the state epic #617 had to clean up.
# Both anchor on FROM/JOIN <table>, which is what makes them SQL-specific. A bare table name is not
# enough — `batch_district` happens to appear only in SQL, but `handoff` and `capture` are ordinary
# vocabulary in this codebase's prose, and the first draft of these two fired on stage6_dispatch's
# docstring (`capture.source='benchmark_gt'`) and its operator error string ("set
# dispatch_type='benchmark' to run this as a Council Lab…"). A display string mentioning the rule is
# not a second copy of it, and a detector that cries wolf gets ignored.
_SQL_FROM = r"(?:FROM|JOIN)\s+"
_INLINE_DISPATCH_ARM = re.compile(_SQL_FROM + r"handoff\b.{0,200}?dispatch_type\s*=\s*'benchmark", re.S)
_INLINE_CAPTURE_ARM = re.compile(_SQL_FROM + r"capture\b.{0,200}?source\s*=\s*'benchmark_gt", re.S)


def test_the_provenance_predicate_also_has_exactly_one_home():
    """Both ARMS live in common/benchmark.py. A call site imports the module or embeds
    IS_BENCHMARK_PROVENANCE_SQL; it never re-spells either arm's SQL.

    Note what is deliberately NOT flagged: referencing the CONSTANTS (`BM.DISPATCH_BENCHMARK`,
    `BM.BENCHMARK_CAPTURE_SOURCE`) is the sanctioned way to ask the question in Python — the guard is
    against re-inlining the SQL, which is what can silently drift."""
    offenders = []
    for py in ACQ.rglob("*.py"):
        if py.name == "benchmark.py" and py.parent.name == "common":
            continue
        src = _normalize_source(py.read_text())
        if _INLINE_DISPATCH_ARM.search(src) or _INLINE_CAPTURE_ARM.search(src):
            offenders.append(str(py.relative_to(REPO)))
    assert not offenders, (
        "a benchmark-provenance arm was re-inlined instead of imported from common/benchmark.py:\n  "
        + "\n  ".join(offenders))


@pytest.mark.parametrize("arm,src,caught", [
    # the two arms as a call site would plausibly hand-inline them — both must trip
    ("dispatch", '''
    rows = s.execute(text(
        "SELECT 1 FROM extraction e JOIN handoff h ON h.handoff_hash = e.handoff_hash "
        "WHERE h.dispatch_type = 'benchmark' AND e.district_id = :d"), {"d": did})''', True),
    ("capture", '''
    rows = s.execute(text(
        "SELECT r.rec_key FROM record r JOIN capture c ON c.district_id = r.district_id "
        "AND c.hash = r.hash WHERE c.source = 'benchmark_gt'"))''', True),
    # …and the three REAL non-copies that must NOT trip, or the detector gets ignored. All three are
    # verbatim from stage6_dispatch.py, and all three tripped an earlier draft of these patterns.
    ("prose", "An explicit `dispatch_type='benchmark'` always passes: the Council Lab opt-in.", False),
    ("error string", '''f"Deselect those records, or set dispatch_type='benchmark' to run this "''',
     False),
    ("dotted attr in prose", "(`capture.source='benchmark_gt'`), which is real and mixed after a "
     "#620 re-run", False),
])
def test_the_provenance_detector_catches_a_hand_inlined_arm(arm, src, caught):
    """Falsification, same standard as the membership detector: a fitness function nobody has
    falsified is decoration. Both polarities, because the first draft of this detector DID fire on
    stage6_dispatch's prose and operator error string."""
    hit = bool(_INLINE_DISPATCH_ARM.search(_normalize_source(src))
               or _INLINE_CAPTURE_ARM.search(_normalize_source(src)))
    assert hit is caught, f"{arm}: expected caught={caught}"


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
    """A district's rep (record + capture, the arm-2 path) and optionally a dispatch/extraction/fact
    chain stamped with `dispatch_type` (the arm-1 path). Returns the fact_id when one was made."""
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    BS.ensure_signal_schema(s)
    CI.ensure_cache_schema(s)
    s.execute(text("INSERT INTO record (rec_key, district_id, url, hash, tier) "
                   "VALUES (:k, :d, :u, :h, 'A') ON CONFLICT (rec_key) DO NOTHING"),
              {"k": rec_key, "d": did, "u": f"http://x/{hash_}", "h": hash_})
    s.execute(text("INSERT INTO capture (district_id, hash, url, ok, kind, source) "
                   "VALUES (:d, :h, :u, 1, 'html', :s) "
                   "ON CONFLICT (district_id, hash) DO UPDATE SET source = EXCLUDED.source"),
              {"d": did, "h": hash_, "u": f"http://x/{hash_}", "s": source})
    if dispatch_type is None:
        s.flush()
        return None
    hh = f"zzh{hash_}"
    s.execute(text(
        "INSERT INTO handoff (handoff_id, handoff_hash, created_at, created_by, status, path, "
        "dispatch_type, n_districts, n_reps, total_usd, cost_provenance, district_ids, council_ids) "
        "VALUES (:hid, :hh, 'now', 'zz', 'dispatched', '/zz/x.json', :dt, 1, 1, 0.0, 'zz', "
        "'[]', '[]')"), {"hid": f"handoff_{hh}_t", "hh": hh, "dt": dispatch_type})
    eid = s.execute(text(
        "INSERT INTO extraction (handoff_hash, district_id, run_kind, created_at, created_by, "
        "n_reps, n_calls, n_judge_calls, n_errors, prompt_tokens, completion_tokens, cost_usd, "
        "n_accepted, n_unresolved) VALUES (:hh, :d, 'production', 'now', 'zz', 1, 1, 0, 0, 0, 0, "
        "0.0, 1, 0) RETURNING extraction_id"), {"hh": hh, "d": did}).scalar()
    fid = s.execute(text(
        "INSERT INTO school_fact (extraction_id, district_id, band, school, status, rec_key, "
        "created_at, human_determination) VALUES (:e, :d, 'elementary', 'oak', 'accepted', :k, "
        "'now', '') RETURNING fact_id"), {"e": eid, "d": did, "k": rec_key}).scalar()
    s.flush()
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
    s.execute(text(
        "INSERT INTO handoff (handoff_id, handoff_hash, created_at, created_by, status, path, "
        "dispatch_type, n_districts, n_reps, total_usd, cost_provenance, district_ids, council_ids) "
        "VALUES (:hid, :hh, 'now', 'zz', 'dispatched', '/zz/x.json', 'production', 1, 1, 0.0, 'zz', "
        "'[]', '[]')"), {"hid": f"handoff_{hh}_t", "hh": hh})
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
