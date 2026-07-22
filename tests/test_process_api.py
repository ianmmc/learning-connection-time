"""Stage 4 (Process) console API (REQ-111) — HTTP wiring for the status view + the process trigger.

Hits the REAL governance DB (seeds + deletes a synthetic batch; skips if Docker is down), and NEVER runs
the real harvesters — the run test monkeypatches server._run_stage4_subprocess (the #608 isolated-
subprocess seam) so the background job is a no-op and never actually spawns a process. The runner itself
is unit-tested in test_stage4_headless.py; the subprocess plumbing itself in test_stage4_subprocess.py.
"""
import time

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import batch_store as BS
from infrastructure.acquisition.stage1_queue import models  # noqa: F401  (registers tables)

pytestmark = [pytest.mark.integration, pytest.mark.govdb]

BID = "batch_test_process_api"


def _doc():
    return {
        "batch_id": BID, "created": "2026-06-27T00:00:00Z", "nces_year": "2024_25",
        "stratification": {"priority": ["enrollment"]}, "school_cap_per_band": 12,
        "districts": [
            {"district_id": "ZZPRCA", "name": "Alpha", "state": "AK", "domain": "a.org",
             "enrollment_k12": 500, "lea_claimed_bands": ["elementary"],
             "nces_school_counts": {"total": 1, "by_level": {"Elementary": 1}},
             "band_processing_order": ["elementary"],
             "schools_by_band": {"elementary": {"n_candidates": 1, "n_unclaimed_at_selection": 1, "n_selected": 1,
                "schools": [{"school_id": "A1", "name": "A Elem", "is_charter": "No", "level": "Elementary", "gslo": "KG", "gshi": "05"}]}}},
        ],
    }


def _cleanup(con):
    for tbl in ("batch_school", "batch_district", "batch"):
        con.execute(text(f"DELETE FROM {tbl} WHERE batch_id=:b"), {"b": BID})


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
        _cleanup(con)
        BS.create_batch(con, _doc(), actor="setup")
    server._PROCESS_JOBS.pop(BID, None)
    # per-batch run lock (issue #47): a prior test's job thread may release a beat after its job
    # reads "done" — wait for the lock so the next run request can't 409 spuriously
    _lk = server._BATCH_RUN_LOCKS.get(BID)
    for _ in range(100):
        if _lk is None or not _lk.locked():
            break
        time.sleep(0.05)
    try:
        yield TestClient(server.app)
    finally:
        with gdb.session_scope() as con:
            _cleanup(con)
        server._PROCESS_JOBS.pop(BID, None)


def test_status_unknown_batch_is_404(client):
    assert client.get("/api/process/batch_nope_999").status_code == 404


def test_status_returns_awaiting_discovery(client):
    """A queued-but-undiscovered batch: the lone district has no discovery.json, so it reads
    awaiting_discovery and is not processable (todo == 0)."""
    r = client.get(f"/api/process/{BID}")
    assert r.status_code == 200
    body = r.json()
    assert body["rollup"]["awaiting_discovery"] == 1 and body["rollup"]["todo"] == 0
    assert body["districts"][0]["status"] == "awaiting_discovery"


def test_run_on_unknown_batch_is_404(client):
    assert client.post("/api/process/batch_nope_999/run", json={}).status_code == 404


def test_run_starts_background_job(client, monkeypatch):
    from infrastructure.acquisition.process_governance import server

    calls = {}

    def fake_run_batch(batch, *, actor="auto:stage4", on_event=None):
        calls["bid"], calls["actor"] = batch["batch_id"], actor
        if on_event:
            on_event("completed", {"batch_id": batch["batch_id"], "district_id": "ZZPRCA", "outcome": "processed_all"})
        return {"batch_id": batch["batch_id"], "todo": 1, "skipped": 0,
                "results": [{"district_id": "ZZPRCA", "outcome": "processed_all"}]}

    monkeypatch.setattr(server, "_run_stage4_subprocess", fake_run_batch)
    r = client.post(f"/api/process/{BID}/run", json={"actor": "ian"})
    assert r.status_code == 200 and r.json()["started"] is True

    for _ in range(50):
        job = server._PROCESS_JOBS.get(BID)
        if job and job["state"] != "running":
            break
        time.sleep(0.05)
    job = server._PROCESS_JOBS.get(BID)
    assert job and job["state"] == "done"
    assert calls["bid"] == BID and calls["actor"] == "ian"


def test_run_twice_rejects_second_while_running(client, monkeypatch):
    from infrastructure.acquisition.process_governance import server
    import threading
    release = threading.Event()

    def blocking_run_batch(batch, **kw):
        release.wait(timeout=5)
        return {"batch_id": batch["batch_id"], "todo": 0, "skipped": 0, "results": []}

    monkeypatch.setattr(server, "_run_stage4_subprocess", blocking_run_batch)
    try:
        assert client.post(f"/api/process/{BID}/run", json={}).status_code == 200
        for _ in range(20):
            if server._PROCESS_JOBS.get(BID, {}).get("state") == "running":
                break
            time.sleep(0.05)
        assert client.post(f"/api/process/{BID}/run", json={}).status_code == 409
    finally:
        release.set()
        # wait for the job thread to release the per-batch run lock (issue #47) before the next test
        for _ in range(50):
            if server._PROCESS_JOBS.get(BID, {}).get("state") != "running":
                break
            time.sleep(0.05)


def _stub_stage5(monkeypatch, *, resolved, total):
    """Stub out the heavy Stage-4 run + the Stage-5 ingest so the handoff trigger can be tested in
    isolation: run_batch reports it processed something; status_for_batch reports the given rollup;
    BS.ingest_batch records its call; DS is in-memory (no real state_event writes)."""
    from infrastructure.acquisition.process_governance import server
    calls = {}
    monkeypatch.setattr(server, "_run_stage4_subprocess",
                        lambda batch, **kw: {"batch_id": batch["batch_id"], "todo": 1, "skipped": 0,
                                             "results": [{"district_id": "ZZPRCA", "outcome": "processed_all"}]})
    monkeypatch.setattr(server.H4, "status_for_batch",
                        lambda batch: {"rollup": {"resolved": resolved, "total": total}})

    def fake_ingest_batch(ids, *a, **k):
        calls["ids"] = list(ids)
        return {"districts": ["ZZPRCA"], "n_districts": 1, "n_records": 3,
                "n_filtered_written": 1, "n_send": 2}

    monkeypatch.setattr(server.BS, "ingest_batch", fake_ingest_batch)
    monkeypatch.setattr(server.DS, "load", lambda: {"schema_version": 2, "districts": {}, "_events": []})
    monkeypatch.setattr(server.DS, "save", lambda r: None)
    return calls


def _wait_done(server, bid):
    for _ in range(50):
        job = server._PROCESS_JOBS.get(bid)
        if job and job["state"] != "running":
            return job
        time.sleep(0.05)
    return server._PROCESS_JOBS.get(bid)


def test_completion_triggers_stage5_ingest(client, monkeypatch):
    """When a run resolves the whole batch, the Stage-4 job incrementally ingests it into Stage 5
    (BS.ingest_batch) and emits a stage5_ingested event — the lag-avoidance handoff."""
    from infrastructure.acquisition.process_governance import server
    calls = _stub_stage5(monkeypatch, resolved=1, total=1)
    assert client.post(f"/api/process/{BID}/run", json={"actor": "ian"}).status_code == 200
    job = _wait_done(server, BID)
    assert job and job["state"] == "done"
    assert calls.get("ids") == ["ZZPRCA"]                                   # ingest_batch called for this batch
    assert any(e["kind"] == "stage5_ingested" for e in job["events"])       # event surfaced to the feed


def test_incomplete_batch_skips_stage5_ingest(client, monkeypatch):
    """A run that leaves the batch partially resolved (a district still failed/pending) must NOT ingest
    to Stage 5 yet — the handoff waits until every district is resolved."""
    from infrastructure.acquisition.process_governance import server
    calls = _stub_stage5(monkeypatch, resolved=0, total=1)
    assert client.post(f"/api/process/{BID}/run", json={}).status_code == 200
    job = _wait_done(server, BID)
    assert job and job["state"] == "done"
    assert "ids" not in calls                                               # ingest_batch NOT called
    assert not any(e["kind"] == "stage5_ingested" for e in job["events"])
