"""#152 — the gate@6->7 'Run extraction' background-job endpoint. Mirrors test_process_api's pattern:
the paid runner (R7.run_council_streaming) is monkeypatched so the job is a no-op; asserts the endpoint
guards (404 unknown handoff, 409 already-running) and that a job runs to 'done' streaming progress.
govdb — needs the governance Postgres (the handoff row + job board)."""
import json
import time

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb

pytestmark = [pytest.mark.integration, pytest.mark.govdb]

HH = "zzextrun01"


def _seed_handoff(con, status="dispatched"):
    con.execute(text("DELETE FROM handoff WHERE handoff_hash = :h"), {"h": HH})
    con.execute(text(
        "INSERT INTO handoff (handoff_hash, handoff_id, created_at, created_by, status, path, "
        "n_districts, n_reps, total_usd, cost_provenance, district_ids, council_ids) VALUES "
        "(:h, :hid, '2026-07-05T00:00:00Z', 'zz', :st, '/tmp/none.json', 1, 1, 0.0, 'test', "
        "CAST(:d AS json), CAST(:c AS json))"),
        {"h": HH, "hid": f"handoff_{HH}_t", "st": status,
         "d": json.dumps(["ZZED"]), "c": json.dumps(["low-cost-text"])})


@pytest.fixture
def client():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.process_governance import server

    gdb.init_precious_schema()
    with gdb.session_scope() as con:
        _seed_handoff(con)
    server._EXTRACT_JOBS.pop(HH, None)
    try:
        yield TestClient(server.app)
    finally:
        server._EXTRACT_JOBS.pop(HH, None)
        with gdb.session_scope() as con:
            con.execute(text("DELETE FROM handoff WHERE handoff_hash = :h"), {"h": HH})


def test_run_unknown_handoff_is_404(client):
    assert client.post("/api/extract/nope_999/run", json={}).status_code == 404


def test_status_of_unseen_handoff_is_idle(client):
    assert client.get("/api/extract/run/never_seen").json()["state"] == "idle"


def test_run_starts_background_job_and_streams_progress(client, monkeypatch):
    from infrastructure.acquisition.process_governance import server

    calls = {}

    def fake_stream(doc, *, persist=False, created_by="auto:stage7", on_district=None, **kw):
        calls["persist"], calls["actor"] = persist, created_by
        if on_district:
            on_district("ZZED", {"name": "Edville", "accepted": [{"band": "high"}], "unresolved": [],
                                 "bands": {"high": {"gross_minutes": 420}}, "telemetry": {"cost_usd": 0.01}})
        return {"handoff_hash": HH, "districts": {"ZZED": {}}}

    monkeypatch.setattr(server.R7, "load_handoff", lambda p: {"handoff_hash": HH})
    monkeypatch.setattr(server.R7, "run_council_streaming", fake_stream)

    r = client.post(f"/api/extract/{HH}/run", json={"actor": "ian"})
    assert r.status_code == 200 and r.json()["started"] is True
    for _ in range(50):
        job = server._EXTRACT_JOBS.get(HH)
        if job and job["state"] != "running":
            break
        time.sleep(0.05)
    job = server._EXTRACT_JOBS.get(HH)
    assert job and job["state"] == "done"
    assert calls["persist"] is True and calls["actor"] == "ian"           # persists; gate@6 was the go-ahead
    st = client.get(f"/api/extract/run/{HH}").json()
    assert st["summary"]["n_districts"] == 1
    assert st["events"][0]["district_id"] == "ZZED" and st["events"][0]["bands"]["high"] == 420


def test_run_twice_rejects_second_while_running(client, monkeypatch):
    import threading
    from infrastructure.acquisition.process_governance import server

    release = threading.Event()

    def blocking_stream(doc, **kw):
        release.wait(timeout=5)
        return {"handoff_hash": HH, "districts": {}}

    monkeypatch.setattr(server.R7, "load_handoff", lambda p: {"handoff_hash": HH})
    monkeypatch.setattr(server.R7, "run_council_streaming", blocking_stream)
    try:
        assert client.post(f"/api/extract/{HH}/run", json={}).status_code == 200
        for _ in range(50):
            if server._EXTRACT_JOBS.get(HH, {}).get("state") == "running":
                break
            time.sleep(0.05)
        assert client.post(f"/api/extract/{HH}/run", json={}).status_code == 409   # already running
    finally:
        release.set()
