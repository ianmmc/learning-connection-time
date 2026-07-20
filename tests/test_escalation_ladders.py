"""#164 PR 3b — the escalation ladders: the 7->1 second-loop scope split (compose emits up to TWO
scope-pure batches, each directive's executed_ref = ITS district's batch), the 5->1 zero-yield geo
composer (predicate + derived ladder + manual flag), the geo_interleaved scope draw, and the
pool-drained policy auto-advance wiring. Ladder position is always DERIVED from ever-approved
follow-up batch history (batch_store.followup_rounds), never a stored counter."""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import stage5_followup as S5F
from infrastructure.acquisition.process_governance import stage7_execute as EX
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import queue_batch as QB
from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict
from infrastructure.acquisition.stage7_extract import models as _M7  # noqa: F401  (registers tables)

govdb = pytest.mark.govdb


# ---------------------------------------------------------------- pure: the interleave draw
def test_draw_interleaved_scope_is_seeded_and_weighted():
    # all-blank pool -> geo with certainty; all-domained -> domain; empty -> conservative domain
    assert QB.draw_interleaved_scope({"domain": 0, "geo": 7}, "batch_00042") == "geo"
    assert QB.draw_interleaved_scope({"domain": 7, "geo": 0}, "batch_00042") == "domain"
    assert QB.draw_interleaved_scope({"domain": 0, "geo": 0}, "batch_00042") == "domain"
    # seeded: the same weights + the same batch id always draw the same scope
    w = {"domain": 3, "geo": 2}
    assert QB.draw_interleaved_scope(w, "batch_00042") == QB.draw_interleaved_scope(w, "batch_00042")


def test_scope_pool_counts_splits_on_the_dual_source_resolution(monkeypatch):
    pool = {
        "D1": {"website": "https://a.org", "name": "A", "state": "AK"},   # NCES domain -> domained
        "D2": {"website": "", "name": "B", "state": "AL"},                # blank, no confirmed -> geo
        "D3": {"website": "", "name": "C", "state": "AZ"},                # blank but CONFIRMED -> domained
    }
    monkeypatch.setattr(QB, "eligible_pool", lambda year, registry: (pool, {}, []))
    out = QB.scope_pool_counts("2024_25", {"districts": {}}, {"D3": "c-schools.org"})
    assert out == {"domain": 2, "geo": 1}


# ---------------------------------------------------------------- pure: force_widen_dids
def test_build_followup_force_widen_overrides_the_vocabulary_signal(monkeypatch):
    monkeypatch.setattr(QB.S, "lea_info", lambda year: {
        "3173740": {"name": "MILLARD", "state": "NE", "website": "", "status": "Open",
                    "lea_type": "x", "claimed_bands": {"high"}, "city": "OMAHA", "zip": "68137"}})
    monkeypatch.setattr(QB.S, "school_index", lambda year: {
        "3173740": {"high": [{"school_id": "s1", "name": "Millard North"}]}})
    monkeypatch.setattr(QB.S, "school_level_counts", lambda year: {})
    monkeypatch.setattr(QB, "load_enrollment", lambda: {})
    # without the override an untried school reads 'new_schools' (standard vocabulary)...
    doc, _ = QB.build_followup_batch("2024_25", "batch_x", {"3173740": ["high"]}, scope="geo")
    assert doc["districts"][0]["schools_by_band"]["high"]["query_strategy"] == "new_schools"
    # ...the ladder rung forces widen_queries regardless (geo+widened = loop 2)
    doc, _ = QB.build_followup_batch("2024_25", "batch_x", {"3173740": ["high"]}, scope="geo",
                                     force_widen_dids={"3173740"})
    assert doc["districts"][0]["schools_by_band"]["high"]["query_strategy"] == "widen_queries"


# ---------------------------------------------------------------- JS source pins (no JS harness)
def test_stage7_js_renders_the_scope_split():
    from pathlib import Path
    js = (Path(__file__).parent.parent /
          "infrastructure/acquisition/process_governance/static/stage7.js").read_text()
    for marker in ("prev.batches", "escalation_exhausted", "autoflow_batch_ids", "GEO-scoped"):
        assert marker in js, f"stage7.js lost the #164 scope-split marker {marker!r}"


# ---------------------------------------------------------------- govdb helpers
def _ensure_compose_tables(s):
    """Fresh-CI bootstrap: compose reads district_target (the SIGNAL schema, not precious) and the
    predicate reads capture (the cross-stage cache) — neither is created by init_precious_schema,
    and this file sorts before the suites that happen to create them locally/in CI order."""
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    from infrastructure.acquisition.stage5_filter import models as _S5M  # noqa: F401  (registers followup_flag on Base)
    gdb.init_precious_schema()
    BS.ensure_signal_schema(s)
    CI.ensure_cache_schema(s)


def _seed_round(s, bid, did, scope, *, approved=True):
    """One ever-approved follow-up batch containing `did` — a ladder rung in the derived history."""
    now = _M7.utcnow()
    s.add(Batch(batch_id=bid, batch_type="follow-up", status="approved" if approved else "draft",
                discovery_scope=scope, nces_year="2024_25", created_at=now, created_by="zz",
                meta_json={}, first_approved_at=(now if approved else None)))
    s.add(BatchDistrict(batch_id=bid, district_id=did, ord=0, name=f"D {did}", state="ZZ",
                        domain="", lea_claimed_bands=["high"], nces_school_counts={},
                        band_processing_order=["high"], band_meta={}, included=True))
    s.flush()


def _seed_req(s, hh, did, route="7->2", band="high", status="approved"):
    s.execute(text(
        "INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, band, "
        "reason, status, created_at) VALUES (:d, :h, 'district', :r, :d, :b, 'test', :st, :ts)"),
        {"d": did, "h": hh, "r": route, "b": band, "st": status, "ts": _M7.utcnow()})


def _stub_builder(monkeypatch, calls):
    def fake_build(year, bid, targets, **kw):
        calls.append({"bid": bid, "targets": dict(targets), **kw})
        return {"batch_id": bid, "districts": [{"district_id": d} for d in targets]}, []
    monkeypatch.setattr(EX.Q1, "build_followup_batch", fake_build)
    monkeypatch.setattr(EX.BSTORE, "create_batch", lambda sess, doc, **k: None)


# ---------------------------------------------------------------- 7->1 second-loop scope split
@govdb
def test_compose_scope_split_emits_two_batches_with_per_district_refs(gov_session, monkeypatch):
    """A fresh district composes into the domain batch (loop 1); a district with an ever-approved
    follow-up round escalates to the GEO batch with forced-widened vocabulary (loop 2). Each
    directive's executed_ref is ITS district's batch — two reservations, one transaction."""
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz3bsplit"
    _seed_req(s, hh, "ZZ3B0")                       # 0 prior rounds -> domain batch
    _seed_req(s, hh, "ZZ3B1")                       # 1 prior domain round -> geo batch
    _seed_round(s, "batch_zz3b_r1", "ZZ3B1", "domain")
    calls = []
    _stub_builder(monkeypatch, calls)

    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    s.flush()

    assert [c["scope"] for c in out["batches"]] == ["domain", "geo"]
    assert out["n_districts"] == 2 and out["n_requests"] == 2
    by_scope = {c["scope"]: c for c in calls}
    assert set(by_scope["domain"]["targets"]) == {"ZZ3B0"}
    assert set(by_scope["geo"]["targets"]) == {"ZZ3B1"}
    assert by_scope["geo"]["force_widen_dids"] == {"ZZ3B1"}      # geo+widened, the second rung
    assert by_scope["domain"].get("force_widen_dids") is None
    refs = dict(s.execute(text(
        "SELECT district_id, executed_ref FROM extraction_request WHERE handoff_hash = :h "
        "AND status = 'executed'"), {"h": hh}).all())
    domain_bid = next(c["batch_id"] for c in out["batches"] if c["scope"] == "domain")
    geo_bid = next(c["batch_id"] for c in out["batches"] if c["scope"] == "geo")
    assert refs == {"ZZ3B0": domain_bid, "ZZ3B1": geo_bid}
    assert domain_bid != geo_bid


@govdb
def test_compose_draft_round_does_not_advance_the_ladder(gov_session, monkeypatch):
    """Only an EVER-APPROVED follow-up batch is a ladder rung — a draft/abandoned compose never
    escalates the next one (followup_rounds gates on first_approved_at)."""
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz3bdraft"
    _seed_req(s, hh, "ZZ3BD")
    _seed_round(s, "batch_zz3b_dr", "ZZ3BD", "domain", approved=False)
    calls = []
    _stub_builder(monkeypatch, calls)
    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    assert [c["scope"] for c in out["batches"]] == ["domain"]


@govdb
def test_compose_exhausted_ladder_flags_and_rejects(gov_session, monkeypatch):
    """A district whose GEO round already ran is past the ladder's end: its directive is
    auto-rejected (human-reversible, note carries the story) and the district gets ONE unresolved
    followup_flag — deduped across re-composes."""
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz3bexh"
    _seed_req(s, hh, "ZZ3BX")
    _seed_round(s, "batch_zz3b_x1", "ZZ3BX", "domain")
    _seed_round(s, "batch_zz3b_x2", "ZZ3BX", "geo")
    calls = []
    _stub_builder(monkeypatch, calls)

    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    s.flush()
    assert out["batches"] == [] and out["batch_id"] is None
    assert [e["district_id"] for e in out["escalation_exhausted"]] == ["ZZ3BX"]
    status, note = s.execute(text(
        "SELECT status, review_note FROM extraction_request WHERE handoff_hash = :h"),
        {"h": hh}).one()
    assert status == "rejected" and "escalation exhausted" in note
    n_flags = s.execute(text(
        "SELECT COUNT(*) FROM followup_flag WHERE district_id = 'ZZ3BX' "
        "AND actor = 'auto:escalation-ladder' AND resolved_at IS NULL")).scalar()
    assert n_flags == 1
    # dedupe: a re-compose (fresh approved directive) must not stack a second flag
    _seed_req(s, hh, "ZZ3BX")
    EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    n_flags = s.execute(text(
        "SELECT COUNT(*) FROM followup_flag WHERE district_id = 'ZZ3BX' "
        "AND actor = 'auto:escalation-ladder' AND resolved_at IS NULL")).scalar()
    assert n_flags == 1


@govdb
def test_compose_dry_run_split_neither_flags_nor_rejects(gov_session, monkeypatch):
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz3bdry"
    _seed_req(s, hh, "ZZ3BY")
    _seed_round(s, "batch_zz3b_y1", "ZZ3BY", "domain")
    _seed_round(s, "batch_zz3b_y2", "ZZ3BY", "geo")
    calls = []
    _stub_builder(monkeypatch, calls)
    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s, dry_run=True)
    assert [e["district_id"] for e in out["escalation_exhausted"]] == ["ZZ3BY"]
    status = s.execute(text("SELECT status FROM extraction_request WHERE handoff_hash = :h"),
                       {"h": hh}).scalar()
    assert status == "approved"                     # untouched — preview promised no writes
    n_flags = s.execute(text(
        "SELECT COUNT(*) FROM followup_flag WHERE district_id = 'ZZ3BY'")).scalar()
    assert n_flags == 0


# ---------------------------------------------------------------- 5->1 zero-yield predicate
@govdb
def test_zero_yield_reason_clean_district_is_eligible(gov_session, monkeypatch):
    from infrastructure.acquisition.common import cache_ingest as CI
    CI.ensure_cache_schema(gov_session)
    monkeypatch.setattr(S5F.REL, "load_district_records", lambda s, d: [])
    assert S5F.zero_yield_reason(gov_session, "ZZ5Y0") is None


@govdb
def test_zero_yield_reason_held_record_blocks(gov_session, monkeypatch):
    # a tier-B unlabeled record decides 'hold' — a maybe-target awaiting a label blocks escalation
    held = {"label": None, "tier": "B", "signals": {}, "facets": {}, "reps": []}
    monkeypatch.setattr(S5F.REL, "load_district_records", lambda s, d: [held])
    reason = S5F.zero_yield_reason(gov_session, "ZZ5Y1")
    assert reason and "dispatchable/held" in reason


@govdb
def test_zero_yield_reason_retryable_err_routes_to_116(gov_session, monkeypatch):
    from infrastructure.acquisition.common import cache_ingest as CI
    CI.ensure_cache_schema(gov_session)
    monkeypatch.setattr(S5F.REL, "load_district_records", lambda s, d: [])
    gov_session.execute(text(
        "INSERT INTO capture (district_id, hash, url, err) "
        "VALUES ('ZZ5Y2', 'h1', 'https://x', 'not_attempted (deadline)')"))
    reason = S5F.zero_yield_reason(gov_session, "ZZ5Y2")
    assert reason and "#116" in reason


@govdb
def test_zero_yield_reason_fidelity_flag_routes_to_triage(gov_session, monkeypatch):
    from infrastructure.acquisition.common import cache_ingest as CI
    CI.ensure_cache_schema(gov_session)
    monkeypatch.setattr(S5F.REL, "load_district_records", lambda s, d: [])
    gov_session.execute(text(
        "INSERT INTO capture (district_id, hash, url, err, fidelity_json) "
        "VALUES ('ZZ5Y3', 'h1', 'https://x', NULL, '[\"login_wall\"]')"))
    reason = S5F.zero_yield_reason(gov_session, "ZZ5Y3")
    assert reason and "fidelity" in reason


# ---------------------------------------------------------------- 5->1 composer + ladder
def _seed_source_batch(s, bid, dids, *, batch_type="first-run", approved=True):
    now = _M7.utcnow()
    s.add(Batch(batch_id=bid, batch_type=batch_type, status="approved" if approved else "draft",
                discovery_scope="domain", nces_year="2024_25", created_at=now, created_by="zz",
                meta_json={}, first_approved_at=(now if approved else None)))
    for i, did in enumerate(dids):
        s.add(BatchDistrict(batch_id=bid, district_id=did, ord=i, name=f"D {did}", state="ZZ",
                            domain="", lea_claimed_bands=["high"], nces_school_counts={},
                            band_processing_order=["high"], band_meta={}, included=True))
    s.flush()


@govdb
def test_compose_zero_yield_ladder_rungs(gov_session, monkeypatch):
    """0 geo rounds -> geo+standard; 1 -> geo+widened; >=2 -> manual flag, no compose. One
    geo-scoped draft; ladder positions derived from history."""
    s = gov_session
    _ensure_compose_tables(s)
    _seed_source_batch(s, "batch_zz5y_src", ["ZZ5L0", "ZZ5L1", "ZZ5L2"])
    _seed_round(s, "batch_zz5y_g1", "ZZ5L1", "geo")
    _seed_round(s, "batch_zz5y_g2a", "ZZ5L2", "geo")
    _seed_round(s, "batch_zz5y_g2b", "ZZ5L2", "geo")
    monkeypatch.setattr(S5F, "zero_yield_reason", lambda sess, did: None)
    calls = []

    def fake_build(year, bid, targets, **kw):
        calls.append({"bid": bid, "targets": dict(targets), **kw})
        return {"batch_id": bid, "discovery_scope": kw.get("scope"),
                "districts": [{"district_id": d} for d in targets]}, []
    monkeypatch.setattr(S5F.Q1, "build_followup_batch", fake_build)
    created = []
    monkeypatch.setattr(S5F.BSTORE, "create_batch",
                        lambda sess, doc, **k: created.append((doc["batch_id"], k)))

    out = S5F.compose_zero_yield("batch_zz5y_src", actor="zz", session=s)
    assert out["ok"] and out["batch_id"] and out["scope"] == "geo"
    assert out["ladder"] == {"ZZ5L0": "geo+standard", "ZZ5L1": "geo+widened",
                             "ZZ5L2": "manual_flag"}
    assert set(calls[0]["targets"]) == {"ZZ5L0", "ZZ5L1"}
    assert calls[0]["scope"] == "geo" and calls[0]["force_widen_dids"] == {"ZZ5L1"}
    assert created and created[0][1]["batch_type"] == "follow-up"
    n_flags = s.execute(text(
        "SELECT COUNT(*) FROM followup_flag WHERE district_id = 'ZZ5L2' "
        "AND actor = 'auto:escalation-ladder' AND resolved_at IS NULL")).scalar()
    assert n_flags == 1


@govdb
def test_compose_zero_yield_skips_ineligible_districts(gov_session, monkeypatch):
    s = gov_session
    _ensure_compose_tables(s)
    _seed_source_batch(s, "batch_zz5y_mix", ["ZZ5M0", "ZZ5M1"])
    monkeypatch.setattr(S5F, "zero_yield_reason",
                        lambda sess, did: None if did == "ZZ5M0" else "2 dispatchable record(s)")
    calls = []
    monkeypatch.setattr(S5F.Q1, "build_followup_batch",
                        lambda year, bid, targets, **kw: (calls.append(dict(targets)) or
                            ({"batch_id": bid, "districts": [{"district_id": d} for d in targets]}, [])))
    monkeypatch.setattr(S5F.BSTORE, "create_batch", lambda sess, doc, **k: None)
    out = S5F.compose_zero_yield("batch_zz5y_mix", actor="zz", session=s)
    assert out["ok"] and set(calls[0]) == {"ZZ5M0"}
    assert [x["district_id"] for x in out["ineligible"]] == ["ZZ5M1"]


@govdb
def test_compose_zero_yield_refuses_benchmark_and_never_approved(gov_session):
    s = gov_session
    _ensure_compose_tables(s)
    _seed_source_batch(s, "batch_zz5y_bm", ["ZZ5B0"], batch_type="benchmark")
    _seed_source_batch(s, "batch_zz5y_nv", ["ZZ5B1"], approved=False)
    out = S5F.compose_zero_yield("batch_zz5y_bm", session=s)
    assert not out["ok"] and "benchmark" in out["reason"]
    out = S5F.compose_zero_yield("batch_zz5y_nv", session=s)
    assert not out["ok"] and "never approved" in out["reason"]
    out = S5F.compose_zero_yield("batch_zz5y_missing", session=s)
    assert not out["ok"] and "no such batch" in out["reason"]
