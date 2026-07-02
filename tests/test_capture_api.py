"""Stage 3 (Capture) console API (REQ-110) — HTTP wiring for the status view + the capture trigger.

Hits the REAL governance DB (seeds + deletes a synthetic batch; skips if Docker is down), and NEVER runs
a live Node capture — the run test monkeypatches H3.run_batch so the background job is a no-op. The runner
itself is unit-tested in test_stage3_headless.py.
"""
import time

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import batch_store as BS
from infrastructure.acquisition.stage1_queue import models  # noqa: F401  (registers tables)

pytestmark = [pytest.mark.integration, pytest.mark.govdb]

BID = "batch_test_capture_api"


def _doc():
    return {
        "batch_id": BID, "created": "2026-06-27T00:00:00Z", "nces_year": "2024_25",
        "stratification": {"priority": ["enrollment"]}, "school_cap_per_band": 12,
        "districts": [
            {"district_id": "ZZCAPA", "name": "Alpha", "state": "AK", "domain": "a.org",
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
    server._CAPTURE_JOBS.pop(BID, None)
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
        server._CAPTURE_JOBS.pop(BID, None)


def test_status_unknown_batch_is_404(client):
    assert client.get("/api/capture/batch_nope_999").status_code == 404


def test_status_returns_awaiting_discovery(client):
    """A queued-but-undiscovered batch: the lone district has no discovery.json, so it reads
    awaiting_discovery and is not capturable (todo == 0)."""
    r = client.get(f"/api/capture/{BID}")
    assert r.status_code == 200
    body = r.json()
    assert body["rollup"]["awaiting_discovery"] == 1 and body["rollup"]["todo"] == 0
    assert body["districts"][0]["status"] == "awaiting_discovery"


def test_run_on_unknown_batch_is_404(client):
    assert client.post("/api/capture/batch_nope_999/run", json={}).status_code == 404


def test_run_starts_background_job(client, monkeypatch):
    from infrastructure.acquisition.process_governance import server

    calls = {}

    def fake_run_batch(batch, *, actor="auto:stage3", on_event=None, **kw):
        calls["bid"], calls["actor"] = batch["batch_id"], actor
        if on_event:
            on_event("completed", {"batch_id": batch["batch_id"], "district_id": "ZZCAPA", "outcome": "captured_all"})
        return {"batch_id": batch["batch_id"], "todo": 1, "skipped": 0,
                "results": [{"district_id": "ZZCAPA", "outcome": "captured_all"}]}

    monkeypatch.setattr(server.H3, "run_batch", fake_run_batch)
    r = client.post(f"/api/capture/{BID}/run", json={"actor": "ian"})
    assert r.status_code == 200 and r.json()["started"] is True

    for _ in range(50):
        job = server._CAPTURE_JOBS.get(BID)
        if job and job["state"] != "running":
            break
        time.sleep(0.05)
    job = server._CAPTURE_JOBS.get(BID)
    assert job and job["state"] == "done"
    assert calls["bid"] == BID and calls["actor"] == "ian"


def test_run_twice_rejects_second_while_running(client, monkeypatch):
    from infrastructure.acquisition.process_governance import server
    import threading
    release = threading.Event()

    def blocking_run_batch(batch_ref, **kw):
        release.wait(timeout=5)
        return {"batch_id": batch_ref, "todo": 0, "skipped": 0, "results": []}

    monkeypatch.setattr(server.H3, "run_batch", blocking_run_batch)
    try:
        assert client.post(f"/api/capture/{BID}/run", json={}).status_code == 200
        for _ in range(20):
            if server._CAPTURE_JOBS.get(BID, {}).get("state") == "running":
                break
            time.sleep(0.05)
        assert client.post(f"/api/capture/{BID}/run", json={}).status_code == 409
    finally:
        release.set()
        # wait for the job thread to release the per-batch run lock (issue #47) before the next test
        for _ in range(50):
            if server._CAPTURE_JOBS.get(BID, {}).get("state") != "running":
                break
            time.sleep(0.05)


def test_cross_stage_runs_on_same_batch_are_mutually_exclusive(client, monkeypatch):
    """Issue #47: while a capture run is in flight for a batch, starting a PROCESS run on the SAME
    batch is refused with 409 (per-batch run lock; in-process only — single localhost server)."""
    from infrastructure.acquisition.process_governance import server
    import threading
    release = threading.Event()

    def blocking_run_batch(batch, **kw):
        release.wait(timeout=5)
        return {"batch_id": batch["batch_id"], "todo": 0, "skipped": 0, "no_links": 0, "results": []}

    monkeypatch.setattr(server.H3, "run_batch", blocking_run_batch)
    try:
        assert client.post(f"/api/capture/{BID}/run", json={}).status_code == 200
        for _ in range(20):
            if server._CAPTURE_JOBS.get(BID, {}).get("state") == "running":
                break
            time.sleep(0.05)
        r = client.post(f"/api/process/{BID}/run", json={})
        assert r.status_code == 409
        assert "already in progress" in r.json()["detail"]
    finally:
        release.set()
        # wait for the job thread to finish and release the per-batch lock (no cross-test leakage)
        for _ in range(50):
            if server._CAPTURE_JOBS.get(BID, {}).get("state") != "running":
                break
            time.sleep(0.05)
