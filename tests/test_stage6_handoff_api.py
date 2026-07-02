"""Stage 6 gate@6 console API (REQ-101) — HTTP wiring for the handoff view.

Endpoint wiring is tested DB-free (monkeypatch the session_scope + the H6 bridge — the bridge itself is
unit-tested in test_stage6_dispatch.py). Two read-only endpoints (candidates / handoffs) get a govdb
smoke test against the real governance DB.
"""
import contextlib

import pytest
from fastapi.testclient import TestClient

from infrastructure.acquisition.process_governance import server as SRV

client = TestClient(SRV.app)


@contextlib.contextmanager
def _fake_scope():
    yield "SESS"


# ----------------------------- endpoint wiring (DB-free) -----------------------------
def test_preview_returns_the_package(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    pkg = {"districts": [], "cost": {"total_usd": 0.0, "n_reps": 0, "provenance": "bootstrap"}}
    monkeypatch.setattr(SRV.H6, "build_handoff_package", lambda con, ids, *a, **k: pkg)
    r = client.post("/api/handoff/preview", json={"district_ids": ["X"]})
    assert r.status_code == 200
    assert r.json()["cost"]["provenance"] == "bootstrap"


def test_dispatch_returns_summary(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    doc = {"handoff_hash": "abc123", "created_at": "2026-06-30T00:00:00Z",
           "districts": [{"district_id": "0100810"}],
           "cost": {"total_usd": 0.00102, "n_reps": 1, "provenance": "bootstrap"}}
    monkeypatch.setattr(SRV.H6, "dispatch_handoff", lambda con, ids, **k: (doc, "/data/handoffs/x.json"))
    r = client.post("/api/handoff/dispatch", json={"district_ids": ["0100810"], "actor": "ian"})
    assert r.status_code == 200
    body = r.json()
    assert body["handoff_hash"] == "abc123"
    assert body["handoff_id"].startswith("handoff_abc123_")
    assert body["n_reps"] == 1 and body["n_districts"] == 1
    assert body["provenance"] == "bootstrap" and body["path"] == "/data/handoffs/x.json"


def test_dispatch_requires_districts():
    r = client.post("/api/handoff/dispatch", json={"district_ids": []})
    assert r.status_code == 400


# ----------------------------- read-only smoke (real DB) -----------------------------
@pytest.mark.govdb
@pytest.mark.integration
def test_candidates_and_handoffs_lists():
    c = client.get("/api/handoff/candidates")
    assert c.status_code == 200 and isinstance(c.json(), list)
    if c.json():
        row = c.json()[0]
        assert "district_id" in row and "n_send" in row and "n_hold" in row
    h = client.get("/api/handoffs")
    assert h.status_code == 200 and isinstance(h.json(), list)


# ----------------------------- preview→freeze staleness gate (issue #37) -----------------------------
from infrastructure.acquisition.stage6_handoff import handoff as HND


def _pkg():
    return {"districts": [{"district_id": "0100810", "records": [
                {"rec_key": "0100810:abc", "decision": "send",
                 "reps": [{"file": "page.txt", "kind": "text", "councils": ["low-cost-text"],
                           "est_usd": 0.001}]}]}],
            "cost": {"total_usd": 0.001, "n_reps": 1, "provenance": "bootstrap"},
            "verified_only": False}


def test_preview_returns_the_identity_token(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.H6, "build_handoff_package", lambda con, ids, *a, **k: _pkg())
    r = client.post("/api/handoff/preview", json={"district_ids": ["0100810"]})
    assert r.status_code == 200
    body = r.json()
    assert body["preview_identity"] == HND.package_identity(_pkg())


def test_dispatch_with_stale_identity_is_409(monkeypatch):
    """The release changed between preview and approve (a label edit / re-ingest): the dispatch
    rebuild no longer matches what the human reviewed -> 409, nothing frozen."""
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.H6, "build_handoff_package", lambda con, ids, *a, **k: _pkg())
    frozen = {"called": False}
    monkeypatch.setattr(SRV.H6, "dispatch_handoff",
                        lambda *a, **k: frozen.update(called=True) or ({}, ""))
    stale_pkg = _pkg()   # what an earlier preview hashed: the same district, a different record
    stale_pkg["districts"][0]["records"][0]["rec_key"] = "0100810:zzz"
    stale = HND.package_identity(stale_pkg)
    r = client.post("/api/handoff/dispatch",
                    json={"district_ids": ["0100810"], "expected_identity": stale})
    assert r.status_code == 409
    assert "re-preview" in r.json()["detail"]
    assert frozen["called"] is False               # nothing was frozen/recorded


def test_dispatch_with_matching_identity_freezes(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.H6, "build_handoff_package", lambda con, ids, *a, **k: _pkg())
    doc = {"handoff_hash": "abc123", "created_at": "2026-07-02T00:00:00Z",
           "districts": [{"district_id": "0100810"}],
           "cost": {"total_usd": 0.001, "n_reps": 1, "provenance": "bootstrap"}}
    monkeypatch.setattr(SRV.H6, "dispatch_handoff", lambda con, ids, **k: (doc, "/x.json"))
    r = client.post("/api/handoff/dispatch",
                    json={"district_ids": ["0100810"],
                          "expected_identity": HND.package_identity(_pkg())})
    assert r.status_code == 200 and r.json()["handoff_hash"] == "abc123"
