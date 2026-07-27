"""#618 (epic #617) — `dispatch_type` as a first-class dispatch attribute, at REPRESENTATION grain.

A benchmark DISPATCH is the Stages-6/7 A/B harness and terminates at gate@7, so it is structurally
never a Stage-9 candidate. The type is:
  * FORCED-by-refusal, never silently: a production dispatch that selected a benchmark-provenance rep
    is REFUSED at freeze. Auto-forcing the whole dispatch to benchmark would let one stale `gt://` rep
    wall every OTHER district in the same dispatch off from the Stage-9 write.
  * opt-in-able: a human may run a production-rep draft as a benchmark A/B (the Council Lab path).
  * keyed on the REP, never the district. A district that merely *was* in a benchmark batch composes a
    production dispatch freely — that is mobility property 3, and the whole point of epic #617.

`capture.source='benchmark_gt'` is the provenance signal; see common/benchmark.py for why it is the
only durable representation-grain one.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import benchmark as BM
from infrastructure.acquisition.common import db as gdb
from tests import benchmark_seed as BSEED
from infrastructure.acquisition.process_governance import stage6_dispatch as BR
from infrastructure.acquisition.stage6_handoff import handoff as HND

govdb = pytest.mark.govdb


def _pkg(dispatch_type=BM.DISPATCH_PRODUCTION, rec_keys=("r1",), district_id="ZZD1"):
    return {"districts": [{"district_id": district_id,
                           "records": [{"rec_key": k, "decision": "send",
                                        "reps": [{"file": "e.txt", "kind": "text", "pages": None,
                                                  "councils": ["low-cost-text"],
                                                  "fidelity_suspect": False}]}
                                       for k in rec_keys]}],
            "cost": {"total_usd": 0.0, "n_reps": len(rec_keys), "provenance": "bootstrap"},
            "verified_only": False, "dispatch_type": dispatch_type}


# --------------------------- identity + the type constants (DB-free) ---------------------------

def test_the_same_reps_hash_differently_as_benchmark_vs_production():
    """The `verified_only` precedent: a benchmark dispatch of identical reps is a DISTINCT artifact —
    it terminates at gate@7 and never reaches the LCT write, so it must not collide with a production
    dispatch of the same content."""
    prod = HND.package_identity(_pkg(BM.DISPATCH_PRODUCTION))
    bench = HND.package_identity(_pkg(BM.DISPATCH_BENCHMARK))
    assert prod != bench


def test_an_absent_dispatch_type_reads_as_production():
    """Every pre-#618 frozen artifact and open draft has no type; it must read production, matching
    the column default — never None, and never accidentally benchmark."""
    pkg = _pkg()
    del pkg["dispatch_type"]
    assert HND.package_identity(pkg) == HND.package_identity(_pkg(BM.DISPATCH_PRODUCTION))


def test_the_frozen_doc_records_its_own_type():
    """The artifact on disk must be self-describing: 'was this dispatch benchmark?' has to be
    answerable from the receipt alone, not only from a DB row that could be lost or disagree."""
    doc = HND.freeze(_pkg(BM.DISPATCH_BENCHMARK), {}, {}, created_by="ian")
    assert doc["dispatch_type"] == BM.DISPATCH_BENCHMARK
    assert HND.freeze(_pkg(), {}, {}, created_by="ian")["dispatch_type"] == BM.DISPATCH_PRODUCTION


def test_an_invalid_dispatch_type_raises_rather_than_minting_a_third_type():
    """`batch_type` shipped unvalidated and its literals became load-bearing; this axis validates from
    day one so a typo can never satisfy neither terminus."""
    with pytest.raises(ValueError, match="dispatch_type must be one of"):
        BM.validate_dispatch_type("benchmarks")
    with pytest.raises(ValueError):
        BM.validate_dispatch_type(None)
    assert BM.validate_dispatch_type(BM.DISPATCH_BENCHMARK) == BM.DISPATCH_BENCHMARK


# --------------------------- the provenance guard (govdb) ---------------------------

_seed_rec = BSEED.seed_rep     # #661: the record+capture pair lives in one place now


@pytest.fixture
def signals(gov_session):
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    from infrastructure.acquisition.common import cache_ingest as CI
    gdb.init_precious_schema()
    BS.ensure_signal_schema(gov_session)
    CI.ensure_cache_schema(gov_session)
    return gov_session


@govdb
def test_a_production_dispatch_with_a_benchmark_rep_is_refused(signals):
    s = signals
    _seed_rec(s, "ZZP1", "ZZP1:aaa", "aaa", BM.BENCHMARK_CAPTURE_SOURCE)
    pkg = _pkg(BM.DISPATCH_PRODUCTION, rec_keys=("ZZP1:aaa",), district_id="ZZP1")
    assert BR.benchmark_reps_in_package(s, pkg) == [{"district_id": "ZZP1", "rec_key": "ZZP1:aaa"}]
    with pytest.raises(ValueError, match="carry benchmark provenance"):
        BR.assert_dispatch_type_allowed(s, pkg)


@govdb
def test_an_explicit_benchmark_dispatch_may_contain_benchmark_reps(signals):
    """The Council Lab opt-in — and a benchmark dispatch is *allowed* production reps too; mixing is
    the point of an A/B."""
    s = signals
    _seed_rec(s, "ZZP2", "ZZP2:bbb", "bbb", BM.BENCHMARK_CAPTURE_SOURCE)
    _seed_rec(s, "ZZP2", "ZZP2:ccc", "ccc", "discovered")
    pkg = _pkg(BM.DISPATCH_BENCHMARK, rec_keys=("ZZP2:bbb", "ZZP2:ccc"), district_id="ZZP2")
    BR.assert_dispatch_type_allowed(s, pkg)      # must not raise


@govdb
def test_mobility_3_a_benchmark_batch_district_composes_a_production_dispatch_on_fresh_reps(signals):
    """MOBILITY PROPERTY 3, the one the first draft of this design got wrong.

    ZZP3 is a member of a benchmark BATCH — permanently, since batch_district rows are never deleted.
    Under a district-grain rule it could never compose a production dispatch again. Under rep-grain it
    composes freely, because the reps it actually selected are fresh."""
    from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict
    s = signals
    s.add(Batch(batch_id="batch_zzdt_bm", batch_type="benchmark", status="approved",
                nces_year="2024_25", created_at="t", created_by="zz", meta_json={}))
    s.add(BatchDistrict(batch_id="batch_zzdt_bm", district_id="ZZP3", ord=0, name="ZZ", state="AK",
                        domain="", enrollment_k12=None, lea_claimed_bands=[], nces_school_counts={},
                        band_processing_order=[], band_meta={}, included=True))
    s.flush()
    assert BM.is_benchmark_district(s, "ZZP3") is True        # the district IS benchmark-associated
    _seed_rec(s, "ZZP3", "ZZP3:fresh", "fresh", "discovered")  # ...but this rep is honestly fresh

    pkg = _pkg(BM.DISPATCH_PRODUCTION, rec_keys=("ZZP3:fresh",), district_id="ZZP3")
    assert BR.benchmark_reps_in_package(s, pkg) == []
    BR.assert_dispatch_type_allowed(s, pkg)                    # must not raise


@govdb
def test_the_same_district_is_still_refused_on_its_stale_injected_rep(signals):
    """The converse of property 3, and why rep-grain is not a loophole: the SAME district's leftover
    `benchmark_gt` rep still refuses. After a #620 re-run a district holds both kinds at once (Node's
    #174 seeding carries prior records verbatim into the new manifest), so both halves are live."""
    s = signals
    _seed_rec(s, "ZZP4", "ZZP4:fresh", "f4", "discovered")
    _seed_rec(s, "ZZP4", "ZZP4:stale", "s4", BM.BENCHMARK_CAPTURE_SOURCE)
    ok = _pkg(BM.DISPATCH_PRODUCTION, rec_keys=("ZZP4:fresh",), district_id="ZZP4")
    BR.assert_dispatch_type_allowed(s, ok)                     # fresh-only selection: fine
    mixed = _pkg(BM.DISPATCH_PRODUCTION, rec_keys=("ZZP4:fresh", "ZZP4:stale"), district_id="ZZP4")
    with pytest.raises(ValueError, match="ZZP4:stale"):         # the message NAMES the offender
        BR.assert_dispatch_type_allowed(s, mixed)


@govdb
def test_the_refusal_names_the_reps_so_the_human_can_act(signals):
    """A refusal a human can't act on is a dead end — the message must identify what to deselect and
    state the alternative (run it as benchmark on purpose)."""
    s = signals
    for i in range(7):
        _seed_rec(s, "ZZP5", f"ZZP5:r{i}", f"h{i}", BM.BENCHMARK_CAPTURE_SOURCE)
    pkg = _pkg(BM.DISPATCH_PRODUCTION, rec_keys=tuple(f"ZZP5:r{i}" for i in range(7)),
               district_id="ZZP5")
    with pytest.raises(ValueError) as ei:
        BR.assert_dispatch_type_allowed(s, pkg)
    msg = str(ei.value)
    assert "7 selected representation(s)" in msg
    assert "(+2 more)" in msg                    # truncated at 5, but the count is honest
    assert "dispatch_type='benchmark'" in msg    # the alternative is stated


# --------------------------- console visibility (the UI-visibility rule) ---------------------------
# Static-source pins: this repo has no JS harness for the console (a documented deferral), so the
# regression guard is that the markers exist. Without these, a console rework can silently drop the
# ONLY surface that tells a human why a freeze is refused — leaving an unexplainable 400.

def test_gate6_console_surfaces_the_dispatch_type_and_the_blocking_reps():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/stage6.js").read_text()
    # the human's opt-in control + its two read-only badges (draft header, frozen handoff)
    assert 'data-feat="s6-dispatch-type-toggle"' in js
    assert 'id="s6-dispatch-type"' in js
    assert 'data-feat="s6-dispatch-type"' in js
    assert '"set_dispatch_type"' in js
    # the actionable warning: names the reps AND states the alternative
    assert 'data-feat="s6-benchmark-reps"' in js
    assert "benchmark_reps" in js
    assert "Deselect those records" in js
    # the terminus is stated where the human decides, not just in a design note
    assert "gate@7" in js


def test_the_no_client_side_provenance_rule_is_declared_in_the_manifest():
    """The "client must not re-decide provenance" rule belongs in arch-manifest.json, not in an ad-hoc
    assertion here: that file is the declared home for cross-boundary rules and its parametrized
    fitness test already understands the difference between a DECISION on a literal and a comment or
    display string mentioning it. This test only pins that the rule stays declared."""
    import json
    from pathlib import Path
    manifest = json.loads((Path(__file__).resolve().parent.parent / "arch-manifest.json").read_text())
    literals = {r["literal"] for r in
                manifest["client_server_boundaries"]["forbidden_client_comparisons"]}
    assert BM.BENCHMARK_CAPTURE_SOURCE in literals


# --------------------------- #644: the back-edge freeze paths --------------------------------

@govdb
def test_644_the_back_edge_adapter_refuses_a_benchmark_rep(signals):
    """#644: the gate@7 back-edges (`_bundle_alternate`, `_dispatch_recover_band`) froze dispatches
    by calling HND.freeze DIRECTLY, so #618's provenance guard — which had ONE call site against
    THREE freeze paths — never ran on them. They also never set `dispatch_type`, so it defaulted to
    `production`.

    A 7->6 directive names its alternate reps by rec_key from the district's LIVE reps, and a
    batch_00000 district holds `benchmark_gt` captures (95 across the 27), so these paths could mint
    a production dispatch carrying injected `gt://` reps into an IMMUTABLE artifact.

    The adapter returns this-module's refusal dict rather than raising, because both callers are
    console actions whose contract is `{"ok": False, "reason": ...}`."""
    from infrastructure.acquisition.process_governance import stage7_execute as EX
    s = signals
    _seed_rec(s, "ZZ644", "ZZ644:gt", "gt644", BM.BENCHMARK_CAPTURE_SOURCE)
    pkg = _pkg(BM.DISPATCH_PRODUCTION, rec_keys=("ZZ644:gt",), district_id="ZZ644")

    refusal = EX._refuse_benchmark_reps(s, pkg)
    assert refusal is not None and refusal["ok"] is False
    assert "ZZ644:gt" in refusal["reason"]          # names the rep, so the human can deselect it
    assert "benchmark provenance" in refusal["reason"]


@govdb
def test_644_the_adapter_lets_clean_reps_through(signals):
    """The refusal must be narrow: an ordinary discovered rep freezes normally. A guard that blocked
    the honest path would simply be turned off."""
    from infrastructure.acquisition.process_governance import stage7_execute as EX
    s = signals
    _seed_rec(s, "ZZ644B", "ZZ644B:ok", "ok644", "discovered")
    pkg = _pkg(BM.DISPATCH_PRODUCTION, rec_keys=("ZZ644B:ok",), district_id="ZZ644B")

    assert EX._refuse_benchmark_reps(s, pkg) is None


@govdb
def test_644_a_deliberate_benchmark_back_edge_is_allowed(signals):
    """The Council Lab opt-in survives the adapter: an explicit benchmark dispatch may carry
    benchmark reps, on the back-edge exactly as at gate@6. The guard refuses a MIS-TYPED dispatch,
    never a benchmark one."""
    from infrastructure.acquisition.process_governance import stage7_execute as EX
    s = signals
    _seed_rec(s, "ZZ644C", "ZZ644C:gt", "gt644c", BM.BENCHMARK_CAPTURE_SOURCE)
    pkg = _pkg(BM.DISPATCH_BENCHMARK, rec_keys=("ZZ644C:gt",), district_id="ZZ644C")

    assert EX._refuse_benchmark_reps(s, pkg) is None
