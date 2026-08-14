"""#572 — the #164 console control surface: GET/POST /api/discovery-policy wiring, the path-4
district-targeted draw, and the UI-visibility pins (per the standing rule: must-be-visible console
features get requirements + regression tests so they can't silently disappear)."""
from pathlib import Path

import pytest

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import discovery_policy as DPOL
from infrastructure.acquisition.stage1_queue import queue_batch as QB

REPO = Path(__file__).parent.parent
STATIC = REPO / "infrastructure/acquisition/process_governance/static"


# ---------------------------------------------------------------- pure: path-4 targeting
def _pool():
    return {
        "D1": {"website": "https://a.org", "name": "A", "state": "AK", "status": "Open",
               "claimed_bands": {"high"}, "enrollment_k12": 100},
        "D2": {"website": "", "name": "B", "state": "AL", "status": "Open",
               "claimed_bands": {"high"}, "enrollment_k12": 200, "city": "X", "zip": "1"},
        "D3": {"website": "https://c.org", "name": "C", "state": "AZ", "status": "Open",
               "claimed_bands": {"high"}, "enrollment_k12": 300},
    }


def test_build_batch_targeted_restricts_after_scope_filters(monkeypatch):
    monkeypatch.setattr(QB, "eligible_pool", lambda year, registry: (_pool(), {}, []))
    monkeypatch.setattr(QB.S, "school_level_counts", lambda year: {})
    # a targeted DOMAIN draw admits only pool members; the blank-domain D2 and the unknown ZZ
    # are reported missing (post-#229-filter restriction — never force-included)
    doc, _gap, _dx, _n = QB.build_batch("2024_25", 12, "batch_t", {"districts": {}},
                                        district_ids=["D1", "D2", "ZZ"])
    assert [d["district_id"] for d in doc["districts"]] == ["D1"]
    assert doc["targeted"] == {"requested": ["D1", "D2", "ZZ"], "missing": ["D2", "ZZ"]}
    # a targeted GEO draw admits only the blank pool — D1 (domained) is the miss now
    doc, _gap, _dx, _n = QB.build_batch("2024_25", 12, "batch_t", {"districts": {}},
                                        scope="geo", district_ids=["D1", "D2"])
    assert [d["district_id"] for d in doc["districts"]] == ["D2"]
    assert doc["targeted"]["missing"] == ["D1"]


def test_build_batch_untargeted_has_no_targeted_meta(monkeypatch):
    monkeypatch.setattr(QB, "eligible_pool", lambda year, registry: (_pool(), {}, []))
    monkeypatch.setattr(QB.S, "school_level_counts", lambda year: {})
    doc, *_ = QB.build_batch("2024_25", 12, "batch_t", {"districts": {}})
    assert "targeted" not in doc


# ---------------------------------------------------------------- endpoint wiring (govdb)
@pytest.fixture
def client():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.process_governance.server import app
    return TestClient(app)


@pytest.mark.govdb
def test_discovery_policy_get_shape(client, monkeypatch):
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "geo_for_blank")
    r = client.get("/api/discovery-policy")
    assert r.status_code == 200
    d = r.json()
    assert d["policy"] == "geo_for_blank"
    assert [p["policy"] for p in d["positions"]] == list(DPOL.POLICIES)
    assert "events" in d and d["pools"] is None      # pools only on request (?pools=true)


@pytest.mark.govdb
def test_discovery_policy_get_pools_degrades_honestly(client, monkeypatch):
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "domain_only")
    monkeypatch.setattr(QB, "scope_pool_counts",
                        lambda *a: (_ for _ in ()).throw(FileNotFoundError("no NCES CSVs")))
    r = client.get("/api/discovery-policy?pools=true")
    assert r.status_code == 200
    d = r.json()
    assert d["pools"] is None and "no NCES CSVs" in d["pools_error"]


@pytest.mark.govdb
def test_discovery_policy_get_pools_uses_the_real_registry(client, monkeypatch):
    """#575 review: pools=true used to call scope_pool_counts with a HARDCODED empty registry
    ({"districts": {}}), making the already-attempted filter a silent no-op and overcounting every
    eligible pool the Settings card displays. Must use DS.load() instead, same registry
    queue_create's draw uses."""
    from infrastructure.acquisition.process_governance import server as SV
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "geo_interleaved")
    sentinel_registry = {"districts": {"SENTINEL": {"furthest_stage": 9}}}
    monkeypatch.setattr(SV.DS, "load", lambda: sentinel_registry)
    seen = {}
    monkeypatch.setattr(QB, "scope_pool_counts",
                        lambda year, registry, discovered: seen.update(registry=registry)
                        or {"domain": 1, "geo": 2})
    r = client.get("/api/discovery-policy?pools=true")
    assert r.status_code == 200
    assert seen["registry"] is sentinel_registry     # NOT {"districts": {}}
    assert r.json()["pools"] == {"domain": 1, "geo": 2}


@pytest.mark.govdb
def test_discovery_policy_set_wires_store_and_twin(client, monkeypatch):
    calls = {}
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "domain_only")
    monkeypatch.setattr(DPOL, "set_policy",
                        lambda con, policy, *, actor, trigger: calls.update(
                            policy=policy, actor=actor, trigger=trigger) or policy)
    from infrastructure.acquisition.process_governance import server as SV
    monkeypatch.setattr(SV, "_backup_discovery_policy",
                        lambda con: calls.update(twin=True) or 0)
    r = client.post("/api/discovery-policy", json={"policy": "geo_for_blank", "actor": "ian"})
    assert r.status_code == 200
    assert r.json() == {"policy": "geo_for_blank", "previous": "domain_only", "changed": True}
    assert calls["policy"] == "geo_for_blank" and calls["trigger"] == "human (console)"
    assert calls.get("twin") is True                 # the git twin refreshed post-commit


@pytest.mark.govdb
def test_discovery_policy_set_rejects_unknown_position(client):
    r = client.post("/api/discovery-policy", json={"policy": "geo_sometimes"})
    assert r.status_code == 400


@pytest.mark.govdb
def test_queue_create_threads_district_ids(client, monkeypatch):
    from infrastructure.acquisition.common import discovered_domain as DDOM
    from infrastructure.acquisition.common import district_status as DS
    from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
    seen = {}
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "geo_for_blank")
    monkeypatch.setattr(DDOM, "all_confirmed", lambda con: {})
    monkeypatch.setattr(DS, "load", lambda: {"districts": {}})
    monkeypatch.setattr(BSTORE, "reserve_next_batch", lambda con, actor: "batch_zzt572")
    monkeypatch.setattr(BSTORE, "release_reservation", lambda con, bid: None)
    monkeypatch.setattr(BSTORE, "to_view", lambda con, bid: {"batch_id": bid, "status": "draft"})

    def fake_build(year, n, bid, registry, **kw):
        seen.update(kw, n=n)
        return ({"batch_id": bid, "discovery_scope": kw.get("scope"),
                 "districts": [{"district_id": "3173740", "name": "M", "state": "NE"}],
                 "targeted": {"requested": ["3173740"], "missing": []}}, [], [], 1)
    monkeypatch.setattr(QB, "build_batch", fake_build)
    monkeypatch.setattr(QB, "persist_batch", lambda doc, registry, **k: seen.update(persisted=doc))

    r = client.post("/api/queue/create", json={"discovery_scope": "geo", "n": 1,
                                               "district_ids": ["3173740"], "actor": "ian"})
    assert r.status_code == 200, r.text
    assert seen["district_ids"] == ["3173740"] and seen["scope"] == "geo" and seen["n"] == 1
    assert seen["persisted"]["targeted"]["requested"] == ["3173740"]


@pytest.mark.govdb
def test_queue_create_targeted_miss_409s_without_pool_advance(client, monkeypatch):
    from infrastructure.acquisition.common import discovered_domain as DDOM
    from infrastructure.acquisition.common import district_status as DS
    from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "domain_only")
    monkeypatch.setattr(DPOL, "advance_one_step",
                        lambda con, **k: (_ for _ in ()).throw(AssertionError("must not advance")))
    monkeypatch.setattr(DDOM, "all_confirmed", lambda con: {})
    monkeypatch.setattr(DS, "load", lambda: {"districts": {}})
    monkeypatch.setattr(BSTORE, "reserve_next_batch", lambda con, actor: "batch_zzt572b")
    monkeypatch.setattr(BSTORE, "release_reservation", lambda con, bid: None)
    monkeypatch.setattr(QB, "build_batch", lambda *a, **kw: (
        {"batch_id": "batch_zzt572b", "districts": [],
         "targeted": {"requested": ["ZZMISS"], "missing": ["ZZMISS"]}},
        [], [{"district_id": "ZZB1"}], 0))
    r = client.post("/api/queue/create", json={"district_ids": ["ZZMISS"], "actor": "ian"})
    assert r.status_code == 409
    assert "ZZMISS" in r.json()["detail"]            # the miss is named, the policy untouched


# ---------------------------------------------------------------- reconcile × remediation (#572)
class TestReconcileRemediationReceipt:
    """The registry-ahead-of-disk CONTROL FAILURE must stand down when the missing artifacts are
    EXPLAINED by an on-disk decontamination restore point (remediate_contamination preserves state
    history while removing artifacts — Millard NE's post-#227 redo hit exactly this halt)."""

    def _setup(self, tmp_path, monkeypatch, stage):
        from infrastructure.acquisition.common import district_status as DS
        from infrastructure.acquisition.stage2_discover import discover_stage2 as D2
        monkeypatch.setattr(D2, "RAW_DIR", tmp_path / "captures")
        # Patch the paths module object DS (the helper's home) actually holds — NOT a fresh
        # import: test_acquisition_paths pops `paths` from sys.modules, so a re-import here can
        # be a DIFFERENT object (the test_remediate_contamination pattern).
        monkeypatch.setattr(DS.paths, "ACQUISITION", tmp_path / "acq")
        d = {"district_id": "9999999", "name": "Test District", "state": "ZZ",
             "dir": tmp_path / "captures" / "9999999_test_district"}
        registry = {"schema_version": 1, "last_updated": None, "districts": {}}
        DS.record_stage(registry, d["district_id"], d["name"], d["state"],
                        stage=stage, stage_name="x", outcome="found_all")
        return D2, d, registry

    def _receipt(self, tmp_path, did="9999999"):
        # Time-relative, NOT hardcoded: the receipt trust window is REMEDIATION_RECEIPT_MAX_AGE_DAYS
        # (#575), so a fixed date here is a calendar time bomb — the original 20260712T000000Z stamp
        # expired 2026-08-11 and failed these tests on every machine. Same pattern as
        # test_remediate_contamination's expiry test, which mints its timestamp from now().
        from datetime import datetime, timedelta, timezone
        ts = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%dT%H%M%SZ")
        (tmp_path / "acq" / "remediation" / f"{did}_{ts}").mkdir(parents=True)

    def test_stage2_without_receipt_still_halts(self, tmp_path, monkeypatch):
        D2, d, registry = self._setup(tmp_path, monkeypatch, stage=2)
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            D2.reconcile({"batch_id": "b", "batch_type": "follow-up", "districts": [d]}, registry)

    def test_stage2_receipt_sanctions_a_fresh_rediscover(self, tmp_path, monkeypatch):
        D2, d, registry = self._setup(tmp_path, monkeypatch, stage=2)
        self._receipt(tmp_path)
        todo, skipped = D2.reconcile(
            {"batch_id": "b", "batch_type": "follow-up", "districts": [d]}, registry)
        assert [x["district_id"] for x in todo] == ["9999999"] and skipped == []

    def test_stage2_other_districts_receipt_does_not_sanction(self, tmp_path, monkeypatch):
        D2, d, registry = self._setup(tmp_path, monkeypatch, stage=2)
        self._receipt(tmp_path, did="1111111")
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            D2.reconcile({"batch_id": "b", "batch_type": "follow-up", "districts": [d]}, registry)

    def test_stage3_receipt_sanctions_a_fresh_capture(self, tmp_path, monkeypatch):
        from infrastructure.acquisition.stage3_capture import capture_stage3 as C3
        _D2, d, registry = self._setup(tmp_path, monkeypatch, stage=3)
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            C3.reconcile([d], registry)
        self._receipt(tmp_path)
        todo, skipped = C3.reconcile([d], registry)
        assert [x["district_id"] for x in todo] == ["9999999"] and skipped == []

    def test_stage4_receipt_sanctions_a_fresh_process(self, tmp_path, monkeypatch):
        from infrastructure.acquisition.stage4_process import process_stage4 as P4
        _D2, d, registry = self._setup(tmp_path, monkeypatch, stage=4)
        with pytest.raises(SystemExit, match="CONTROL FAILURE"):
            P4.reconcile([d], registry)
        self._receipt(tmp_path)
        # the sanctioned district falls through to the NORMAL path (consistency check → todo);
        # the check itself reads the loaded captures manifest, out of scope here
        monkeypatch.setattr(P4, "check_file_consistency", lambda d_: [])
        todo, skipped, quarantined = P4.reconcile([d], registry)
        assert [x["district_id"] for x in todo] == ["9999999"]
        assert skipped == [] and quarantined == []


# ---------------------------------------------------------------- proposal decisions (#572)
@pytest.mark.govdb
class TestProposalDecisions:
    def test_record_decision_validates_and_appends(self, gov_session):
        from infrastructure.acquisition.common import discovered_domain as DDOM
        gdb.init_precious_schema()
        s = gov_session
        with pytest.raises(ValueError):
            DDOM.record_decision(s, "ZZPD1", "x.org", "maybe", actor="zz")
        with pytest.raises(ValueError):          # a rejection NEEDS a reason (the training signal)
            DDOM.record_decision(s, "ZZPD1", "x.org", "reject", actor="zz")
        DDOM.record_decision(s, "ZZPD1", "x.org", "reject", reason="aggregator site", actor="zz")
        DDOM.record_decision(s, "ZZPD1", "y.org", "confirm", actor="zz",
                             tally={"y.org": {"n": 9}})
        latest = DDOM.latest_decisions(s, ["ZZPD1"])
        assert latest["ZZPD1"]["decision"] == "confirm" and latest["ZZPD1"]["domain"] == "y.org"

    def test_endpoint_reject_records_corpus_only(self, client, monkeypatch):
        from infrastructure.acquisition.common import discovered_domain as DDOM
        calls = {"decision": None, "confirmed": False, "twin": 0}
        monkeypatch.setattr(DDOM, "record_decision",
                            lambda con, did, dom, dec, **kw: calls.update(decision=(did, dom, dec, kw.get("reason"))) or
                            type("R", (), {"decision": dec, "reason": kw.get("reason", ""),
                                           "actor": kw.get("actor"), "created_at": "t"})())
        monkeypatch.setattr(DDOM, "confirm",
                            lambda *a, **k: calls.update(confirmed=True))
        from infrastructure.acquisition.process_governance import server as SV
        monkeypatch.setattr(SV, "_backup_discovered_domain_decisions",
                            lambda con: calls.update(twin=calls["twin"] + 1) or 0)
        r = client.post("/api/discovered-domain", json={
            "district_id": "ZZPD2", "domain": "x.org", "decision": "reject",
            "reason": "wrong district's site", "actor": "zz"})
        assert r.status_code == 200, r.text
        assert calls["decision"] == ("ZZPD2", "x.org", "reject", "wrong district's site")
        assert calls["confirmed"] is False       # reject NEVER touches the operative store
        assert calls["twin"] == 1

    def test_endpoint_confirm_records_both(self, client, monkeypatch):
        from infrastructure.acquisition.common import discovered_domain as DDOM
        calls = {"confirmed": False}
        monkeypatch.setattr(DDOM, "record_decision",
                            lambda con, did, dom, dec, **kw:
                            type("R", (), {"decision": dec, "reason": "", "actor": "zz",
                                           "created_at": "t"})())
        monkeypatch.setattr(DDOM, "confirm",
                            lambda con, did, dom, **kw: calls.update(confirmed=True) or
                            type("C", (), {"confirmed_by": "zz", "confirmed_at": "t"})())
        from infrastructure.acquisition.process_governance import server as SV
        monkeypatch.setattr(SV, "_backup_discovered_domain_decisions", lambda con: 0)
        monkeypatch.setattr(SV, "_backup_discovered_domains", lambda con: 0)
        r = client.post("/api/discovered-domain", json={
            "district_id": "ZZPD3", "domain": "x.org", "actor": "zz"})   # decision defaults confirm
        assert r.status_code == 200 and calls["confirmed"] is True


# ---------------------------------------------------------------- UI-visibility source pins
def test_settings_js_carries_the_policy_card():
    js = (STATIC / "settings.js").read_text()
    for marker in ("discovery-policy-card", "discovery-policy-set", "discovery-policy-history",
                   "/api/discovery-policy", "loadDiscoveryPolicy"):
        assert marker in js, f"settings.js lost the #572 policy-card marker {marker!r}"


def test_stage2_js_carries_the_proposal_card():
    js = (STATIC / "stage2.js").read_text()
    for marker in ("s2-geo-proposal", "s2-confirm-domain", "s2-reject-domain", "s2-domain-decided",
                   "geo_proposal", "/api/discovered-domain"):
        assert marker in js, f"stage2.js lost the #572 proposal-card marker {marker!r}"


def test_gate1_js_carries_scope_create_and_badges():
    js = (STATIC / "gate1.js").read_text()
    for marker in ("q-create-scope-geo", "q-create-targets", "q-scope-badge", "q-scope-draw",
                   "q-targeted", "q-geo-tokens", "discovery-policy?pools=true",
                   "q-zero-yield", "compose-zero-yield", "prev.names"):
        assert marker in js, f"gate1.js lost the #572 scope-surface marker {marker!r}"
    # #575 review: prev.batch_id was interpolated into the zero-yield modal without esc(), the one
    # inconsistency in an otherwise esc()-everywhere function — pinned so it can't silently regress.
    assert "esc(prev.batch_id)" in js, "gate1.js lost the esc() around the zero-yield modal's batch_id"
