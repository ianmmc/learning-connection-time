"""epic #617 — `common/benchmark.py` is THE definition of "is this benchmark?".

The rule previously lived in three hand-maintained copies (Stage 9's write wall, Stage 7's execution
wall, server.py's console fragment) plus two more inline (stage7_run's early-exit, the receipts
backfill). Each carried a comment saying it ought to have one definition; none could, because
`stage9_incorporate` may not import `process_governance`. `common` is the base layer, so it can.

These tests cover the predicate itself (govdb, real SQL) AND pin the consolidation with a fitness
function — the copies must not silently grow back.
"""
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
    assert "{alias}" in BM.IS_BENCHMARK_SQL
    rendered = BM.IS_BENCHMARK_SQL.format(alias="p")
    assert "p.district_id" in rendered and "{alias}" not in rendered


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
