"""Stage 6 draft-dispatch console API — HTTP wiring for the new /api/dispatch* endpoints.

DB-free: monkeypatch session_scope() + the DSTORE6 store functions (the store itself is unit-tested
against the real governance DB in test_stage6_draft_store.py) — mirrors test_stage6_handoff_api.py's
pattern exactly.
"""
import contextlib

import pytest
from fastapi.testclient import TestClient

from infrastructure.acquisition.process_governance import server as SRV

client = TestClient(SRV.app)


@contextlib.contextmanager
def _fake_scope():
    yield "SESS"


def test_dispatch_list_returns_drafts_and_handoffs(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    rows = [{"kind": "draft", "draft_id": "draft_00001", "status": "draft"},
            {"kind": "handoff", "handoff_id": "handoff_x_20260713T000000Z", "origin": "stage7"}]
    monkeypatch.setattr(SRV.DSTORE6, "list_dispatch_rows", lambda con: rows)
    r = client.get("/api/dispatch")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["kind"] == "draft" and body[1]["origin"] == "stage7"


def test_dispatch_create_returns_the_new_draft_view(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.DSTORE6, "create_draft", lambda con, actor: "draft_00042")
    view = {"draft_id": "draft_00042", "status": "draft", "districts": [], "package": {}}
    monkeypatch.setattr(SRV.DSTORE6, "to_view", lambda con, did: view)
    r = client.post("/api/dispatch/create", json={"actor": "ian"})
    assert r.status_code == 200 and r.json()["draft_id"] == "draft_00042"


def test_dispatch_get_404_on_unknown_draft(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)

    def raise_keyerror(con, did):
        raise KeyError(did)

    monkeypatch.setattr(SRV.DSTORE6, "to_view", raise_keyerror)
    r = client.get("/api/dispatch/draft_nonexistent")
    assert r.status_code == 404


def test_dispatch_edit_unknown_op_is_400(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    r = client.post("/api/dispatch/draft_00001/edit", json={"op": "not_a_real_op", "district_id": "X"})
    assert r.status_code == 400


def test_dispatch_edit_locked_draft_is_409(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)

    def raise_locked(con, did, district_id):
        raise SRV.DSTORE6.DraftLocked(f"{did} is dispatched; only a draft can be edited")

    monkeypatch.setattr(SRV.DSTORE6, "add_district", raise_locked)
    r = client.post("/api/dispatch/draft_00001/edit", json={"op": "add_district", "district_id": "X"})
    assert r.status_code == 409


def test_dispatch_edit_unknown_district_is_404(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)

    def raise_keyerror(con, did, district_id):
        raise KeyError(district_id)

    monkeypatch.setattr(SRV.DSTORE6, "remove_district", raise_keyerror)
    r = client.post("/api/dispatch/draft_00001/edit", json={"op": "remove_district", "district_id": "ghost"})
    assert r.status_code == 404


@pytest.mark.govdb
@pytest.mark.integration
def test_dispatch_edit_add_district_round_trips_to_view():
    """District-scoped edits fire `_record_gate6_draft` -> `district_status.DS.load()`, which touches
    the real governance DB regardless of a mocked session_scope (the SAME shape gate@1's edit endpoint
    tests already accept — test_gate1_api.py's pytestmark = govdb) — so this hits Postgres for real via
    a genuine draft, rather than mocking DSTORE6. Hard-deletes the synthetic draft in teardown (matches
    test_gate1_api.py's convention: throwaway test fixtures are deleted, not soft-abandoned — abandon is
    for real domain data subject to the audit trail, not test pollution)."""
    from infrastructure.acquisition.common import db as gdb
    from sqlalchemy import text

    r = client.post("/api/dispatch/create", json={"actor": "ian"})
    assert r.status_code == 200
    draft_id = r.json()["draft_id"]
    try:
        r = client.post(f"/api/dispatch/{draft_id}/edit", json={"op": "add_district", "district_id": "0100810"})
        assert r.status_code == 200
        assert any(d["district_id"] == "0100810" and d["included"] for d in r.json()["districts"])
    finally:
        with gdb.session_scope() as con:
            con.execute(text("DELETE FROM dispatch_draft_district WHERE draft_id=:d"), {"d": draft_id})
            con.execute(text("DELETE FROM dispatch_draft WHERE draft_id=:d"), {"d": draft_id})


def test_dispatch_freeze_returns_summary(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    doc = {"handoff_hash": "abc123", "created_at": "2026-07-13T00:00:00Z",
           "verified_only": False, "districts": [{"district_id": "0100810"}],
           "cost": {"total_usd": 0.001, "n_reps": 1, "provenance": "bootstrap"}}
    monkeypatch.setattr(SRV.DSTORE6, "freeze_draft", lambda con, did, actor, expected_identity=None: doc)
    r = client.post("/api/dispatch/draft_00001/freeze", json={"actor": "ian"})
    assert r.status_code == 200
    body = r.json()
    assert body["handoff_hash"] == "abc123" and body["draft_id"] == "draft_00001"
    assert body["n_reps"] == 1 and body["n_districts"] == 1


def test_dispatch_freeze_stale_identity_is_409(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)

    def raise_stale(con, did, actor, expected_identity=None):
        raise ValueError("release changed since you last opened this draft — reload before freezing")

    monkeypatch.setattr(SRV.DSTORE6, "freeze_draft", raise_stale)
    r = client.post("/api/dispatch/draft_00001/freeze", json={"actor": "ian", "expected_identity": "stale"})
    assert r.status_code == 409
    assert "changed since" in r.json()["detail"]


def test_dispatch_freeze_empty_selection_is_400(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)

    def raise_empty(con, did, actor, expected_identity=None):
        raise ValueError("dispatch refused: the effective selection is empty — no districts were selected")

    monkeypatch.setattr(SRV.DSTORE6, "freeze_draft", raise_empty)
    r = client.post("/api/dispatch/draft_00001/freeze", json={"actor": "ian"})
    assert r.status_code == 400


def test_dispatch_freeze_locked_draft_is_409(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)

    def raise_locked(con, did, actor, expected_identity=None):
        raise SRV.DSTORE6.DraftLocked(f"{did} is abandoned; only a draft can be edited")

    monkeypatch.setattr(SRV.DSTORE6, "freeze_draft", raise_locked)
    r = client.post("/api/dispatch/draft_00001/freeze", json={"actor": "ian"})
    assert r.status_code == 409


def test_dispatch_abandon_returns_view(monkeypatch):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)
    monkeypatch.setattr(SRV.DSTORE6, "abandon_draft", lambda con, did, actor, reason: None)
    view = {"draft_id": "draft_00001", "status": "abandoned"}
    monkeypatch.setattr(SRV.DSTORE6, "to_view", lambda con, did: view)
    r = client.post("/api/dispatch/draft_00001/abandon", json={"actor": "ian", "reason": "superseded"})
    assert r.status_code == 200 and r.json()["status"] == "abandoned"


def test_handoff_detail_returns_full_package(monkeypatch, tmp_path):
    monkeypatch.setattr(SRV.gdb, "session_scope", _fake_scope)

    class _Row(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    row = _Row(handoff_id="handoff_x_20260713T000000Z", handoff_hash="x", created_at="t",
              created_by="ian", status="dispatched", path=str(tmp_path / "x.json"),
              n_districts=1, n_reps=1, total_usd=0.001, cost_provenance="bootstrap")

    class _Result:
        def __init__(self, val):
            self._val = val

        def mappings(self):
            return self

        def first(self):
            return self._val

        def scalar(self):
            return self._val

    calls = {"n": 0}

    def fake_execute(sql, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Result(row)          # the handoff row lookup
        if calls["n"] == 2:
            return _Result("stage7")     # classify_origin's derived-origin CASE query
        return _Result(1)                # n_extracted count

    class _Con:
        def execute(self, sql, params=None):
            return fake_execute(sql, params)

    @contextlib.contextmanager
    def scope():
        yield _Con()

    monkeypatch.setattr(SRV.gdb, "session_scope", scope)
    doc = {"districts": [{"district_id": "0100810"}], "cost": {"total_usd": 0.001, "n_reps": 1}}
    monkeypatch.setattr(SRV.R7, "load_handoff", lambda path: doc)
    r = client.get("/api/handoffs/handoff_x_20260713T000000Z")
    assert r.status_code == 200
    body = r.json()
    assert body["origin"] == "stage7" and body["package"]["districts"][0]["district_id"] == "0100810"


def test_handoff_detail_404_on_unknown(monkeypatch):
    class _Result:
        def mappings(self):
            return self

        def first(self):
            return None

    class _Con:
        def execute(self, sql, params=None):
            return _Result()

    @contextlib.contextmanager
    def scope():
        yield _Con()

    monkeypatch.setattr(SRV.gdb, "session_scope", scope)
    r = client.get("/api/handoffs/no_such_handoff")
    assert r.status_code == 404


# ----------------------------- existing routes untouched (regression) -----------------------------
@pytest.mark.govdb
@pytest.mark.integration
def test_old_handoff_routes_still_registered():
    """The plan explicitly keeps /api/handoff/preview and /api/handoff/dispatch as a legacy escape
    hatch (test_stage6_handoff_api.py exercises both directly) — confirm they're still on the app."""
    paths = {r.path for r in SRV.app.routes}
    assert "/api/handoff/preview" in paths
    assert "/api/handoff/dispatch" in paths
    assert "/api/dispatch" in paths
    assert "/api/dispatch/{draft_id}" in paths
    assert "/api/dispatch/{draft_id}/freeze" in paths
