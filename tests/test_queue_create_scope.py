"""#164 PR 3b — queue-create scope wiring: the geo_interleaved weighted draw (recorded on the
batch meta) and the pool-drained one-step policy auto-advance, tested through the real endpoint
(the 2026-07-19 review lesson: the wiring, not the units, is where fields silently drop). The
NCES-heavy builder + persistence + the policy store are stubbed at their module seams; the
governance DB only backs session_scope plumbing."""
import pytest

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import discovered_domain as DDOM
from infrastructure.acquisition.common import discovery_policy as DPOL
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import queue_batch as QB

pytestmark = pytest.mark.govdb


@pytest.fixture
def client():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.process_governance.server import app
    return TestClient(app)


@pytest.fixture
def stubbed_create(monkeypatch):
    """Stub every heavy/persisting seam of queue_create; return the capture dict."""
    seen = {"build": None, "persisted": None, "advanced": [], "backed_up": 0}
    monkeypatch.setattr(DDOM, "all_confirmed", lambda con: {})
    monkeypatch.setattr(DS, "load", lambda: {"districts": {}})
    monkeypatch.setattr(BSTORE, "reserve_next_batch", lambda con, actor: "batch_zzqcs")
    monkeypatch.setattr(BSTORE, "release_reservation", lambda con, bid: None)
    monkeypatch.setattr(BSTORE, "to_view", lambda con, bid: {"batch_id": bid, "status": "draft"})

    def fake_build(year, n, bid, registry, *, scope="domain", geo_pool="blank", **kw):
        doc = {"batch_id": bid, "discovery_scope": scope, "nces_year": year,
               "districts": [{"district_id": "ZZQ1", "name": "Q", "state": "ZZ"}]}
        seen["build"] = {"scope": scope, "geo_pool": geo_pool}
        return doc, [], [], 1

    monkeypatch.setattr(QB, "build_batch", fake_build)
    monkeypatch.setattr(QB, "persist_batch",
                        lambda doc, registry, **k: seen.update(persisted=doc))
    return seen


def test_interleave_draw_sets_scope_and_records_the_draw(client, stubbed_create, monkeypatch):
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "geo_interleaved")
    # an all-blank pool draws geo with certainty — deterministic assertion
    monkeypatch.setattr(QB, "scope_pool_counts", lambda year, reg, dd: {"domain": 0, "geo": 5})
    r = client.post("/api/queue/create", json={"actor": "zz"})    # no discovery_scope: drawn
    assert r.status_code == 200, r.text
    assert stubbed_create["build"]["scope"] == "geo"
    draw = stubbed_create["persisted"]["scope_draw"]
    assert draw == {"policy": "geo_interleaved", "weights": {"domain": 0, "geo": 5}, "drawn": "geo"}


def test_interleave_explicit_scope_skips_the_draw(client, stubbed_create, monkeypatch):
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "geo_interleaved")
    monkeypatch.setattr(QB, "scope_pool_counts",
                        lambda *a: (_ for _ in ()).throw(AssertionError("draw must not run")))
    r = client.post("/api/queue/create", json={"actor": "zz", "discovery_scope": "domain"})
    assert r.status_code == 200, r.text
    assert stubbed_create["build"]["scope"] == "domain"
    assert "scope_draw" not in stubbed_create["persisted"]


def test_pool_drained_auto_advances_one_step_and_409s(client, stubbed_create, monkeypatch):
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "domain_only")

    def fake_build(year, n, bid, registry, **kw):
        return ({"batch_id": bid, "districts": []}, [],
                [{"district_id": "ZZB1", "name": "Blank", "state": "ZZ", "website": ""}], 0)
    monkeypatch.setattr(QB, "build_batch", fake_build)

    def fake_advance(con, *, actor, trigger):
        stubbed_create["advanced"].append({"actor": actor, "trigger": trigger})
        return "geo_for_blank"
    monkeypatch.setattr(DPOL, "advance_one_step", fake_advance)
    from infrastructure.acquisition.process_governance import server as SV
    monkeypatch.setattr(SV, "_backup_discovery_policy",
                        lambda con: stubbed_create.update(backed_up=stubbed_create["backed_up"] + 1))

    r = client.post("/api/queue/create", json={"actor": "zz"})
    assert r.status_code == 409
    assert "AUTO-ADVANCED" in r.json()["detail"]
    assert len(stubbed_create["advanced"]) == 1
    assert "pool exhausted" in stubbed_create["advanced"][0]["trigger"]
    assert stubbed_create["backed_up"] == 1          # the precious twin refreshed post-commit
    assert stubbed_create["persisted"] is None       # nothing composed


def test_pool_drained_when_policy_already_geo_does_not_advance(client, stubbed_create, monkeypatch):
    monkeypatch.setattr(DPOL, "get_policy", lambda con: "geo_for_blank")

    def fake_build(year, n, bid, registry, **kw):
        return ({"batch_id": bid, "districts": []}, [],
                [{"district_id": "ZZB1", "name": "Blank", "state": "ZZ", "website": ""}], 0)
    monkeypatch.setattr(QB, "build_batch", fake_build)
    monkeypatch.setattr(DPOL, "advance_one_step", lambda con, **k: None)

    r = client.post("/api/queue/create", json={"actor": "zz"})
    assert r.status_code == 409
    assert "policy already allows" in r.json()["detail"]
    assert stubbed_create["persisted"] is None
