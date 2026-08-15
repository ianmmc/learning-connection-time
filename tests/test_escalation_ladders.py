"""#164 PR 3b — the escalation ladders: the 7->1 scope split (compose emits up to TWO scope-pure
batches, each directive's executed_ref = ITS district's batch), the 5->1 zero-yield composer
(predicate + derived ladder + manual flag), the geo_interleaved scope draw, and the pool-drained
policy auto-advance wiring. Ladder position is always DERIVED from ever-approved follow-up batch
history (batch_store.followup_rounds), never a stored counter.

#719: scope is a DIAGNOSIS, not a rung — a district WITH a usable scoping domain always composes
domain-scoped (escalation = widened vocabulary; geo would blank its domain and #229-refuse every
result); geo is only for domain-less districts. Tests stub Q1.usable_scoping_domains (the NCES
LEA CSV is absent on CI) via _stub_domains."""
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


def _stub_domains(monkeypatch, domains):
    """#719 diagnosis stub: {district_id: domain} — '' / absent = domain-less (the geo pool).
    Patches queue_batch.usable_scoping_domains (shared by EX.Q1 and S5F.Q1), which otherwise
    reads the on-disk NCES LEA CSV (absent on CI)."""
    monkeypatch.setattr(EX.Q1, "usable_scoping_domains",
                        lambda year, dids, dd: {d: ((domains.get(d, ""), "nces")
                                                    if domains.get(d) else ("", ""))
                                                for d in dids})


# ---------------------------------------------------------------- 7->1 scope split (#719: by diagnosis)
@govdb
def test_compose_scope_split_emits_two_batches_with_per_district_refs(gov_session, monkeypatch):
    """#719: scope is the DIAGNOSIS — a domain-having district composes into the domain batch
    (round 0 -> standard vocabulary); a DOMAIN-LESS district with an ever-approved round composes
    into the GEO batch with forced-widened vocabulary. Each directive's executed_ref is ITS
    district's batch — two reservations, one transaction."""
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz3bsplit"
    _seed_req(s, hh, "ZZ3B0")                       # domain-having, 0 rounds -> domain batch
    _seed_req(s, hh, "ZZ3B1")                       # domain-less, 1 prior GEO round -> geo+widened
    _seed_round(s, "batch_zz3b_r1", "ZZ3B1", "geo")
    calls = []
    _stub_builder(monkeypatch, calls)
    _stub_domains(monkeypatch, {"ZZ3B0": "zz3b0.org"})

    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    s.flush()

    assert [c["scope"] for c in out["batches"]] == ["domain", "geo"]
    assert out["n_districts"] == 2 and out["n_requests"] == 2
    by_scope = {c["scope"]: c for c in calls}
    assert set(by_scope["domain"]["targets"]) == {"ZZ3B0"}
    assert set(by_scope["geo"]["targets"]) == {"ZZ3B1"}
    # #737: widening counts SCOPE-PURE rounds (the same counting ladder_exhausted uses)
    assert by_scope["geo"]["force_widen_dids"] == {"ZZ3B1"}      # >=1 prior GEO round -> widened
    assert by_scope["domain"].get("force_widen_dids") is None    # round 0 -> standard
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
    _stub_domains(monkeypatch, {"ZZ3BD": "zz3bd.org"})
    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    assert [c["scope"] for c in out["batches"]] == ["domain"]
    assert calls[0].get("force_widen_dids") is None   # draft round never advanced the ladder


@govdb
def test_compose_exhausted_ladder_flags_and_rejects(gov_session, monkeypatch):
    """A DOMAIN-LESS district past the geo ladder's end (>=GEO_LADDER_EXHAUSTED_AT ever-approved
    geo rounds — #575 review: shared with the 5->1 composer, so ONE geo round alone is NOT
    exhausted, it's "geo+widened") gets its directive auto-rejected (human-reversible, note
    carries the story) and ONE unresolved followup_flag — deduped across re-composes."""
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz3bexh"
    _seed_req(s, hh, "ZZ3BX")
    _seed_round(s, "batch_zz3b_x1", "ZZ3BX", "domain")
    _seed_round(s, "batch_zz3b_x2", "ZZ3BX", "geo")
    _seed_round(s, "batch_zz3b_x3", "ZZ3BX", "geo")   # 2nd geo round -> genuinely exhausted
    calls = []
    _stub_builder(monkeypatch, calls)
    _stub_domains(monkeypatch, {})                    # domain-less -> the geo ladder governs

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
    _seed_round(s, "batch_zz3b_y3", "ZZ3BY", "geo")   # 2nd geo round -> genuinely exhausted
    calls = []
    _stub_builder(monkeypatch, calls)
    _stub_domains(monkeypatch, {})                    # domain-less -> the geo ladder governs
    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s, dry_run=True)
    assert [e["district_id"] for e in out["escalation_exhausted"]] == ["ZZ3BY"]
    status = s.execute(text("SELECT status FROM extraction_request WHERE handoff_hash = :h"),
                       {"h": hh}).scalar()
    assert status == "approved"                     # untouched — preview promised no writes
    n_flags = s.execute(text(
        "SELECT COUNT(*) FROM followup_flag WHERE district_id = 'ZZ3BY'")).scalar()
    assert n_flags == 0


@govdb
def test_compose_one_geo_round_is_not_exhausted_the_shared_threshold(gov_session, monkeypatch):
    """#575 review regression: a DOMAIN-LESS district with exactly ONE ever-approved geo round
    must NOT be ladder-exhausted under 7->1 — it escalates to a geo+widened batch instead (the
    5->1 composer's own rung 2, BSTORE.ladder_exhausted is the ONE shared predicate). The bug
    this guards: 7->1 used to exhaust at geo>=1 while 5->1 offered a widened rung at geo==1,
    disagreeing for any district sitting at exactly one approved geo round."""
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz3bwid"
    _seed_req(s, hh, "ZZ3BW")
    _seed_round(s, "batch_zz3b_w1", "ZZ3BW", "domain")
    _seed_round(s, "batch_zz3b_w2", "ZZ3BW", "geo")     # exactly ONE geo round
    calls = []
    _stub_builder(monkeypatch, calls)
    _stub_domains(monkeypatch, {})                      # domain-less -> geo is legitimate

    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    s.flush()
    assert out["escalation_exhausted"] == []
    assert [c["scope"] for c in out["batches"]] == ["geo"]
    assert calls[0]["force_widen_dids"] == {"ZZ3BW"}   # loop 2's forced-widened vocabulary


# ---------------------------------------------------------------- #719: diagnosis-based scope
def test_ladder_exhausted_is_diagnosis_keyed():
    """#719: domain-having districts ladder on DOMAIN rounds (exhausted at 3; misdiagnosed geo
    rounds never charge them); domain-less districts ladder on GEO rounds (exhausted at 2)."""
    # the six #719 districts' live shape: {domain:1, geo:1} with a good domain — NOT exhausted
    assert not BSTORE.ladder_exhausted({"domain": 1, "geo": 1}, has_domain=True)
    assert not BSTORE.ladder_exhausted({"domain": 2, "geo": 2}, has_domain=True)
    assert BSTORE.ladder_exhausted({"domain": 3, "geo": 0}, has_domain=True)
    # domain-less: the geo ladder, unchanged from #575
    assert not BSTORE.ladder_exhausted({"domain": 1, "geo": 1}, has_domain=False)
    assert BSTORE.ladder_exhausted({"domain": 0, "geo": 2}, has_domain=False)


@govdb
def test_compose_domain_district_never_escalates_to_geo(gov_session, monkeypatch):
    """#719's must-fail-today acceptance case (the Washoe shape): a district WITH a usable scoping
    domain sitting at {domain:1, geo:1} — the pre-#719 rule ((domain+geo)>=1 -> geo) composed it
    GEO with a blanked domain, a guaranteed 100% #229 refusal. Now: another DOMAIN-scoped round
    with widened vocabulary, and it is NOT ladder-exhausted."""
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz719w"
    _seed_req(s, hh, "ZZ719W")
    _seed_round(s, "batch_zz719_w1", "ZZ719W", "domain")
    _seed_round(s, "batch_zz719_w2", "ZZ719W", "geo")   # the misdiagnosed no-op round
    calls = []
    _stub_builder(monkeypatch, calls)
    _stub_domains(monkeypatch, {"ZZ719W": "washoeschools-shape.net"})

    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    s.flush()
    assert out["escalation_exhausted"] == []
    assert [c["scope"] for c in out["batches"]] == ["domain"]
    assert calls[0]["force_widen_dids"] == {"ZZ719W"}   # escalation = widened vocabulary, same domain


@govdb
def test_compose_misrouted_geo_round_does_not_burn_the_standard_pass(gov_session, monkeypatch):
    """#737: a domain-having district whose ONLY follow-up history is a pre-#719 misrouted geo
    round ({domain:0, geo:1}) composes its FIRST real domain-scoped round with STANDARD
    vocabulary — the geo round never touched its domain, so widening on it would skip the one
    standard pass. Widen counts scope-pure rounds, exactly like ladder_exhausted."""
    s = gov_session
    _ensure_compose_tables(s)
    hh = "zz737"
    _seed_req(s, hh, "ZZ737M")
    _seed_round(s, "batch_zz737_g1", "ZZ737M", "geo")   # the misrouted no-op round
    calls = []
    _stub_builder(monkeypatch, calls)
    _stub_domains(monkeypatch, {"ZZ737M": "zz737.org"})
    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    s.flush()
    assert [c["scope"] for c in out["batches"]] == ["domain"]
    assert calls[0].get("force_widen_dids") is None     # standard vocabulary: round 0 of ITS ladder


def test_build_followup_geo_scope_refuses_a_domain_having_district(monkeypatch):
    """#719 acceptance: a geo batch for a district that HAS a usable scoping domain is
    unrepresentable — build_followup_batch refuses it loudly instead of blanking the domain and
    letting Stage 2's #229 gate silently no-op the whole round."""
    monkeypatch.setattr(QB.S, "lea_info", lambda year: {
        "ZZ719G": {"name": "DOMAINED", "state": "NV", "website": "https://www.zz719.net/",
                   "status": "Open", "lea_type": "x", "claimed_bands": {"high"},
                   "city": "RENO", "zip": "89501"}})
    monkeypatch.setattr(QB.S, "school_index", lambda year: {
        "ZZ719G": {"high": [{"school_id": "s1", "name": "ZZ High"}]}})
    monkeypatch.setattr(QB.S, "school_level_counts", lambda year: {})
    monkeypatch.setattr(QB, "load_enrollment", lambda: {})
    doc, skipped = QB.build_followup_batch("2024_25", "batch_x", {"ZZ719G": ["high"]}, scope="geo")
    assert doc["districts"] == []
    assert len(skipped) == 1 and "#719" in skipped[0]["reason"] and "zz719.net" in skipped[0]["reason"]
    # ...and the SAME district composes fine domain-scoped
    doc, skipped = QB.build_followup_batch("2024_25", "batch_x", {"ZZ719G": ["high"]}, scope="domain")
    assert [d["district_id"] for d in doc["districts"]] == ["ZZ719G"] and skipped == []


def test_usable_scoping_domains_resolves_dual_source(monkeypatch):
    """#719 diagnosis input: NCES website first, confirmed discovered domain second, else ('','');
    a district absent from the LEA file resolves like a blank website."""
    monkeypatch.setattr(QB.S, "lea_info", lambda year: {
        "D1": {"website": "https://a.org"}, "D2": {"website": ""}, "D3": {"website": ""}})
    out = QB.usable_scoping_domains("2024_25", ["D1", "D2", "D3", "D4"], {"D3": "c-schools.org"})
    assert out == {"D1": ("a.org", "nces"), "D2": ("", ""),
                   "D3": ("c-schools.org", "discovered"), "D4": ("", "")}


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


@govdb
def test_zero_yield_reason_security_block_never_escalates(gov_session, monkeypatch):
    """#578: a security-blocked district must not geo-escalate — the WAF said no (Rule 3);
    geo rediscovery would re-derive and re-pressure the same blocked hosts."""
    from infrastructure.acquisition.common import cache_ingest as CI
    CI.ensure_cache_schema(gov_session)
    monkeypatch.setattr(S5F.REL, "load_district_records", lambda s, d: [])
    gov_session.execute(text(
        "INSERT INTO capture (district_id, hash, url, err) VALUES "
        "('ZZ5Y4', 'h1', 'https://x', 'security_block (body marker \"just a moment...\")')"))
    reason = S5F.zero_yield_reason(gov_session, "ZZ5Y4")
    assert reason and "security-blocked" in reason and "manual triage" in reason


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
    """Domain-less districts: 0 geo rounds -> geo+standard; 1 -> geo+widened; >=2 -> manual flag,
    no compose. One geo-scoped draft; ladder positions derived from history."""
    s = gov_session
    _ensure_compose_tables(s)
    _seed_source_batch(s, "batch_zz5y_src", ["ZZ5L0", "ZZ5L1", "ZZ5L2"])
    _seed_round(s, "batch_zz5y_g1", "ZZ5L1", "geo")
    _seed_round(s, "batch_zz5y_g2a", "ZZ5L2", "geo")
    _seed_round(s, "batch_zz5y_g2b", "ZZ5L2", "geo")
    monkeypatch.setattr(S5F, "zero_yield_reason", lambda sess, did: None)
    _stub_domains(monkeypatch, {})                  # all domain-less -> the geo composer
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
    assert out["ok"] and out["batch_id"]
    assert [c["scope"] for c in out["batches"]] == ["geo"]
    assert out["ladder"] == {"ZZ5L0": "geo+standard", "ZZ5L1": "geo+widened",
                             "ZZ5L2": "manual_flag"}
    assert out["names"]["ZZ5L0"] == "D ZZ5L0"       # #572: human-readable modal labels
    assert set(calls[0]["targets"]) == {"ZZ5L0", "ZZ5L1"}
    assert calls[0]["scope"] == "geo" and calls[0]["force_widen_dids"] == {"ZZ5L1"}
    assert created and created[0][1]["batch_type"] == "follow-up"
    n_flags = s.execute(text(
        "SELECT COUNT(*) FROM followup_flag WHERE district_id = 'ZZ5L2' "
        "AND actor = 'auto:escalation-ladder' AND resolved_at IS NULL")).scalar()
    assert n_flags == 1


@govdb
def test_compose_zero_yield_domain_district_composes_domain_widened(gov_session, monkeypatch):
    """#719: a zero-yield district WITH a usable scoping domain composes DOMAIN-scoped with
    widened vocabulary (its standard pass already yielded nothing) — never geo (which would blank
    the domain and #229-refuse everything). Mixed eligibility emits TWO scope-pure drafts."""
    s = gov_session
    _ensure_compose_tables(s)
    _seed_source_batch(s, "batch_zz5y_719", ["ZZ5D0", "ZZ5D1"])
    monkeypatch.setattr(S5F, "zero_yield_reason", lambda sess, did: None)
    _stub_domains(monkeypatch, {"ZZ5D0": "zz5d0.org"})   # ZZ5D1 stays domain-less
    calls = []

    def fake_build(year, bid, targets, **kw):
        calls.append({"bid": bid, "targets": dict(targets), **kw})
        return {"batch_id": bid, "districts": [{"district_id": d} for d in targets]}, []
    monkeypatch.setattr(S5F.Q1, "build_followup_batch", fake_build)
    created = []
    monkeypatch.setattr(S5F.BSTORE, "create_batch",
                        lambda sess, doc, **k: created.append(doc["batch_id"]))

    out = S5F.compose_zero_yield("batch_zz5y_719", actor="zz", session=s)
    assert out["ok"]
    assert [c["scope"] for c in out["batches"]] == ["domain", "geo"]
    assert out["ladder"] == {"ZZ5D0": "domain+widened", "ZZ5D1": "geo+standard"}
    by_scope = {c["scope"]: c for c in calls}
    assert set(by_scope["domain"]["targets"]) == {"ZZ5D0"}
    assert by_scope["domain"]["force_widen_dids"] == {"ZZ5D0"}   # widened: standard already failed
    assert set(by_scope["geo"]["targets"]) == {"ZZ5D1"}
    assert len(created) == 2 and out["n_districts"] == 2


@govdb
def test_compose_zero_yield_dry_run_targets_reflect_survivors_not_candidates(gov_session, monkeypatch):
    """#575 review: the dry-run preview's `targets` used to be built from the PRE-build candidate
    set, not from what build_followup_batch actually returned — a claimed band with zero NCES
    school-level coverage gets silently dropped into `skipped`, but the gate@1 preview would still
    show that district as composable. Confirms `targets` now excludes a district the builder drops."""
    s = gov_session
    _ensure_compose_tables(s)
    _seed_source_batch(s, "batch_zz5y_sk", ["ZZ5S0", "ZZ5S1"])
    monkeypatch.setattr(S5F, "zero_yield_reason", lambda sess, did: None)
    _stub_domains(monkeypatch, {})   # the diagnosis reads the CCD CSV, absent on CI

    def fake_build(year, bid, targets, **kw):
        # simulate build_followup_batch dropping ZZ5S1 (e.g. no school-level coverage for its
        # claimed band) even though it was in the pre-build candidate set
        districts = [{"district_id": d} for d in targets if d != "ZZ5S1"]
        skipped = [{"district_id": "ZZ5S1", "reason": "no NCES school-level coverage"}]
        return {"batch_id": bid, "districts": districts}, skipped
    monkeypatch.setattr(S5F.Q1, "build_followup_batch", fake_build)

    out = S5F.compose_zero_yield("batch_zz5y_sk", actor="zz", session=s, dry_run=True)
    assert out["ok"] and out["dry_run"] is True
    assert set(out["targets"]) == {"ZZ5S0"}          # ZZ5S1 must NOT appear as composable
    assert out["n_districts"] == 1
    assert [sk["district_id"] for sk in out["skipped"]] == ["ZZ5S1"]


@govdb
def test_compose_zero_yield_skips_ineligible_districts(gov_session, monkeypatch):
    s = gov_session
    _ensure_compose_tables(s)
    _seed_source_batch(s, "batch_zz5y_mix", ["ZZ5M0", "ZZ5M1"])
    monkeypatch.setattr(S5F, "zero_yield_reason",
                        lambda sess, did: None if did == "ZZ5M0" else "2 dispatchable record(s)")
    _stub_domains(monkeypatch, {})   # the diagnosis reads the CCD CSV, absent on CI
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
