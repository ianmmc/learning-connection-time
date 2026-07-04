"""gate@7 console API (REQ-117) — HTTP wiring, DB-free (fake session_scope + fake connection).
The heavy logic (detection/persistence/dedup) is unit-tested in test_stage7_requests / _persist."""
import contextlib

from fastapi.testclient import TestClient

from infrastructure.acquisition.process_governance import server as SRV

client = TestClient(SRV.app)


class _Result:
    def __init__(self, rows=None, rowcount=1, scalar=None):
        self._rows = [dict(r) for r in (rows or [])]
        self.rowcount = rowcount
        self._scalar = scalar

    def scalar(self):
        return self._scalar

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Con:
    """Returns queued results in call order (one per execute)."""
    def __init__(self, results):
        self._results, self._i = results, 0

    def execute(self, *a, **k):
        r = self._results[self._i] if self._i < len(self._results) else _Result()
        self._i += 1
        return r


def _use(monkeypatch, con):
    @contextlib.contextmanager
    def _scope():
        yield con
    monkeypatch.setattr(SRV.gdb, "session_scope", _scope)


# ------------------------------- districts list -------------------------------
def test_districts_returns_rows(monkeypatch):
    _use(monkeypatch, _Con([_Result(rows=[
        {"district_id": "D1", "name": "One", "state": "AL", "handoff_hash": "h",
         "n_accepted": 5, "n_unresolved": 2, "cost_usd": 0.003, "n_reps": 4,
         "created_at": "t", "n_pending": 1, "n_requests": 2}])]))
    r = client.get("/api/extract/districts")
    assert r.status_code == 200
    assert r.json()[0]["district_id"] == "D1" and r.json()[0]["n_pending"] == 1


# ------------------------------- district detail -------------------------------
def test_district_detail_shape(monkeypatch):
    ext = _Result(rows=[{"extraction_id": 1, "handoff_hash": "h", "created_at": "t",
                         "created_by": "x", "cost_usd": 0.003, "n_accepted": 1,
                         "n_unresolved": 1, "n_reps": 1}])
    facts = _Result(rows=[
        {"band": "elementary", "school": "a", "status": "accepted", "start_time": "08:00",
         "end_time": "14:00", "gross_minutes": 360, "method": "council_agree",
         "models_json": '["m1"]', "detail_json": None, "rec_key": "D1:aa", "source_file": "f"},
        {"band": "high", "school": "b", "status": "unresolved", "start_time": None, "end_time": None,
         "gross_minutes": None, "method": "disagree", "models_json": None,
         "detail_json": '{"starts": {}}', "rec_key": "D1:bb", "source_file": "f"}])
    reqs = _Result(rows=[{"request_id": 9, "altitude": "district", "route": "7->2", "target": "D1",
                          "band": "high", "params_json": "{}", "reason": "gap", "status": "pending",
                          "reviewed_by": None, "reviewed_at": None, "review_note": None, "created_at": "t"}])
    _use(monkeypatch, _Con([ext, facts, reqs]))
    body = client.get("/api/extract/district/D1").json()
    assert body["bands"]["elementary"]["gross_minutes"] == 360
    assert len(body["accepted"]) == 1 and len(body["unresolved"]) == 1
    assert body["requests"][0]["route"] == "7->2"


def test_district_detail_404_when_no_extraction(monkeypatch):
    _use(monkeypatch, _Con([_Result(rows=[])]))   # ext query returns nothing
    assert client.get("/api/extract/district/ZZ").status_code == 404


# ------------------------------- request review (the mutation) -------------------------------
def test_review_approve_updates(monkeypatch):
    _use(monkeypatch, _Con([_Result(rowcount=1)]))
    r = client.post("/api/extract/request/9", json={"status": "approved", "actor": "ian", "note": "go"})
    assert r.status_code == 200 and r.json() == {"request_id": 9, "status": "approved"}


def test_review_rejects_bad_status(monkeypatch):
    _use(monkeypatch, _Con([]))
    assert client.post("/api/extract/request/9", json={"status": "banana"}).status_code == 400


def test_review_404_when_no_such_request(monkeypatch):
    # rowcount=0 -> the endpoint disambiguates via a status SELECT; no row -> 404
    _use(monkeypatch, _Con([_Result(rowcount=0), _Result(scalar=None)]))
    assert client.post("/api/extract/request/999", json={"status": "rejected"}).status_code == 404


def test_review_executed_is_terminal_409(monkeypatch):
    """#135: an 'executed' directive must never be reopened/re-approved — the depth guard counts
    rows whose CURRENT status is executed, so a reopen would decrement the safety counter and allow
    unlimited paid re-fires. rowcount=0 + current status 'executed' -> 409, not a silent flip."""
    _use(monkeypatch, _Con([_Result(rowcount=0), _Result(scalar="executed")]))
    r = client.post("/api/extract/request/7", json={"status": "pending"})
    assert r.status_code == 409 and "terminal" in r.json()["detail"]


# ------------------------------- execution endpoints (REQ-118) -------------------------------
def test_compose_followup_endpoint(monkeypatch):
    captured = {}
    def _fake(**kw):
        captured.update(kw)
        return {"batch_id": "batch_00042", "n_requests": 3, "n_districts": 2,
                "targets": {"D1": ["high"], "D2": ["middle"]}, "spilled": [], "blocked": [], "skipped": []}
    monkeypatch.setattr(SRV.EX, "compose_followup_batch", _fake)
    r = client.post("/api/extract/compose-followup", json={"handoff_hash": "h", "actor": "zz", "cap": 5})
    assert r.status_code == 200
    assert r.json()["batch_id"] == "batch_00042" and r.json()["n_requests"] == 3
    assert captured["handoff_hash"] == "h" and captured["actor"] == "zz" and captured["cap"] == 5


def test_execute_endpoint_success(monkeypatch):
    monkeypatch.setattr(SRV.EX, "execute_alternate_dispatch",
                        lambda rid, **kw: {"ok": True, "handoff_hash": "NEW", "path": "/x",
                                           "alt_file": "raster_p-1.png", "council": {"k": "image"}})
    r = client.post("/api/extract/execute/7", json={"actor": "zz"})
    assert r.status_code == 200 and r.json()["handoff_hash"] == "NEW"


def test_execute_endpoint_refused_is_409(monkeypatch):
    monkeypatch.setattr(SRV.EX, "execute_alternate_dispatch",
                        lambda rid, **kw: {"ok": False, "blocked": True, "reason": "depth guard: max rounds"})
    r = client.post("/api/extract/execute/7", json={})
    assert r.status_code == 409 and "depth guard" in r.json()["detail"]
