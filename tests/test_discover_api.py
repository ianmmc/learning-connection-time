"""Stage 2 (Discover) console API (REQ-104) — HTTP wiring for the status view + the headless
discovery trigger. Hits the REAL governance DB (seeds + deletes a synthetic batch; skips if Docker is
down), and NEVER makes a live `claude -p` call — the approved-run test monkeypatches H2.run_batch so
the background job runs a no-op. The runner itself is unit-tested in test_stage2_headless.py.
"""
import time

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import batch_store as BS
from infrastructure.acquisition.stage1_queue import models  # noqa: F401  (registers tables)

BID = "batch_test_discover_api"
DISTRICTS = ("ZZDISCA", "ZZDISCB")


def _doc():
    return {
        "batch_id": BID, "created": "2026-06-27T00:00:00Z", "nces_year": "2024_25",
        "stratification": {"priority": ["enrollment"]}, "school_cap_per_band": 12,
        "districts": [
            {"district_id": "ZZDISCA", "name": "Alpha", "state": "AK", "domain": "a.org",
             "enrollment_k12": 500, "lea_claimed_bands": ["elementary"],
             "nces_school_counts": {"total": 1, "by_level": {"Elementary": 1}},
             "band_processing_order": ["elementary"],
             "schools_by_band": {"elementary": {"n_candidates": 1, "n_unclaimed_at_selection": 1, "n_selected": 1,
                "schools": [{"school_id": "A1", "name": "A Elem", "is_charter": "No", "level": "Elementary", "gslo": "KG", "gshi": "05"}]}}},
            {"district_id": "ZZDISCB", "name": "Beta", "state": "AL", "domain": "",
             "enrollment_k12": 100, "lea_claimed_bands": ["high"],
             "nces_school_counts": {"total": 1, "by_level": {"High": 1}},
             "band_processing_order": ["high"],
             "schools_by_band": {"high": {"n_candidates": 1, "n_unclaimed_at_selection": 1, "n_selected": 1,
                "schools": [{"school_id": "B1", "name": "B High", "is_charter": "No", "level": "High", "gslo": "09", "gshi": "12"}]}}},
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
    server._DISCOVER_JOBS.pop(BID, None)
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
        server._DISCOVER_JOBS.pop(BID, None)


def _approve(con):
    BS.approve_batch(con, BID, "setup")


def test_run_on_draft_is_409(client):
    """Discovery requires gate@1 approval — a draft batch must be refused before any job starts."""
    r = client.post(f"/api/discover/{BID}/run", json={"actor": "ian"})
    assert r.status_code == 409
    assert "approval" in r.json()["detail"].lower()


def test_run_on_unknown_batch_is_404(client):
    assert client.post("/api/discover/batch_nope_999/run", json={}).status_code == 404


def test_run_on_approved_starts_background_job(client, monkeypatch):
    from infrastructure.acquisition.process_governance import server
    with gdb.session_scope() as con:
        _approve(con)

    calls = {}

    def fake_run_batch(batch_ref, *, actor="auto:stage2", workers=2, provider=None, on_event=None, **kw):
        calls["ref"], calls["actor"] = batch_ref, actor
        if on_event:
            on_event("completed", {"batch_id": batch_ref, "district_id": "ZZDISCA", "outcome": "found_all"})
        return {"batch_id": batch_ref, "todo": 1, "skipped": 0,
                "results": [{"district_id": "ZZDISCA", "outcome": "found_all"}]}

    monkeypatch.setattr(server.H2, "run_batch", fake_run_batch)

    r = client.post(f"/api/discover/{BID}/run", json={"actor": "ian"})
    assert r.status_code == 200 and r.json()["started"] is True

    # the background thread runs the (fake) job — wait briefly for it to finish
    for _ in range(50):
        job = server._DISCOVER_JOBS.get(BID)
        if job and job["state"] != "running":
            break
        time.sleep(0.05)
    job = server._DISCOVER_JOBS.get(BID)
    assert job and job["state"] == "done"
    assert calls["ref"] == BID and calls["actor"] == "ian"
    assert job["summary"]["results"][0]["outcome"] == "found_all"


def test_run_twice_rejects_second_while_running(client, monkeypatch):
    """A second run while one is in flight is a 409 (one writer); uses a blocking fake to hold the job."""
    from infrastructure.acquisition.process_governance import server
    with gdb.session_scope() as con:
        _approve(con)

    import threading
    release = threading.Event()

    def blocking_run_batch(batch_ref, **kw):
        release.wait(timeout=5)
        return {"batch_id": batch_ref, "todo": 0, "skipped": 0, "results": []}

    monkeypatch.setattr(server.H2, "run_batch", blocking_run_batch)
    try:
        assert client.post(f"/api/discover/{BID}/run", json={}).status_code == 200
        # give the thread a beat to mark the job running
        for _ in range(20):
            if server._DISCOVER_JOBS.get(BID, {}).get("state") == "running":
                break
            time.sleep(0.05)
        assert client.post(f"/api/discover/{BID}/run", json={}).status_code == 409
    finally:
        release.set()
        # wait for the job thread to release the per-batch run lock (issue #47) before the next test
        for _ in range(50):
            if server._DISCOVER_JOBS.get(BID, {}).get("state") != "running":
                break
            time.sleep(0.05)
