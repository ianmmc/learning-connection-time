"""#157 — follow-up auto-flow: gate@1 auto-pass -> Stages 2->3->4 -> STOP at gate@5. The stage runners
(H2/H3/H4.run_batch) are monkeypatched so the chain is a fast no-op; asserts the ORDER, that the batch
is auto-approved, that it lands at gate@5, and that gate@6 (dispatch) is never auto-crossed on failure.
govdb — needs the governance DB (a real draft batch to approve + the run lock)."""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import models  # noqa: F401  (registers batch tables)

pytestmark = [pytest.mark.integration, pytest.mark.govdb]

BID = "batch_zzautoflow"


def _seed_draft(con):
    con.execute(text("DELETE FROM batch_school WHERE batch_id = :b"), {"b": BID})
    con.execute(text("DELETE FROM batch_district WHERE batch_id = :b"), {"b": BID})
    con.execute(text("DELETE FROM batch WHERE batch_id = :b"), {"b": BID})
    BSTORE.create_batch(con, {
        "batch_id": BID, "created": "2026-07-05T00:00:00Z", "nces_year": "2024_25",
        "districts": [{"district_id": "ZZAF", "name": "Autoville", "state": "IA", "domain": "af.org",
                       "band_processing_order": ["high"],
                       "schools_by_band": {"high": {"n_candidates": 1, "n_unclaimed_at_selection": 1,
                                                    "n_selected": 1, "schools": [{"school_id": "ZZAF01",
                                                    "name": "Auto High", "is_charter": "No",
                                                    "level": "High", "gslo": "09", "gshi": "12"}]}}}],
    }, batch_type="follow-up", actor="zz")


@pytest.fixture
def env():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    gdb.init_precious_schema()
    from infrastructure.acquisition.process_governance import server
    with gdb.session_scope() as con:
        _seed_draft(con)
    server._AUTOFLOW_JOBS.pop(BID, None)
    server._BATCH_RUN_LOCKS.pop(BID, None)
    try:
        yield server
    finally:
        server._AUTOFLOW_JOBS.pop(BID, None)
        with gdb.session_scope() as con:
            con.execute(text("DELETE FROM batch_school WHERE batch_id = :b"), {"b": BID})
            con.execute(text("DELETE FROM batch_district WHERE batch_id = :b"), {"b": BID})
            con.execute(text("DELETE FROM batch WHERE batch_id = :b"), {"b": BID})
            # #178: gate@1 auto-approve records real state_event rows for the fixture district — clean
            # them, or the live registry accumulates ZZAF events monotonically per test run.
            con.execute(text("DELETE FROM state_event WHERE district_id = 'ZZAF'"))


def test_autoflow_approves_then_runs_2_3_4_and_stops_at_gate5(env, monkeypatch):
    order = []
    monkeypatch.setattr(env.H2, "run_batch", lambda bid, **kw: order.append("discover") or {"summary": {"d": 1}})
    monkeypatch.setattr(env.H3, "run_batch", lambda batch, **kw: order.append("capture") or {"summary": {"c": 1}})
    monkeypatch.setattr(env.H4, "run_batch", lambda batch, **kw: order.append("process") or {"summary": {"p": 1}})

    env._autoflow_followup(BID, "ian")

    assert order == ["discover", "capture", "process"]           # 2 -> 3 -> 4, in order
    job = env._AUTOFLOW_JOBS[BID]
    assert job["state"] == "done" and job["stage"] == "gate@5"   # landed at the review gate, no gate@6
    assert job["stages"]["gate1"] == "approved"
    with gdb.session_scope() as con:
        assert con.execute(text("SELECT status FROM batch WHERE batch_id = :b"), {"b": BID}).scalar() == "approved"


def test_autoflow_halts_on_stage_failure_and_does_not_advance(env, monkeypatch):
    order = []
    monkeypatch.setattr(env.H2, "run_batch", lambda bid, **kw: order.append("discover") or {"summary": {}})

    def boom(batch, **kw):
        order.append("capture")
        raise RuntimeError("scraper down")
    monkeypatch.setattr(env.H3, "run_batch", boom)
    monkeypatch.setattr(env.H4, "run_batch", lambda batch, **kw: order.append("process"))

    env._autoflow_followup(BID, "ian")

    assert order == ["discover", "capture"]                      # process never reached
    job = env._AUTOFLOW_JOBS[BID]
    assert job["state"] == "error" and job["stage"] == "capture"
    assert "scraper down" in job["error"]


def test_autoflow_releases_the_run_lock(env, monkeypatch):
    monkeypatch.setattr(env.H2, "run_batch", lambda bid, **kw: {"summary": {}})
    monkeypatch.setattr(env.H3, "run_batch", lambda batch, **kw: {"summary": {}})
    monkeypatch.setattr(env.H4, "run_batch", lambda batch, **kw: {"summary": {}})
    env._autoflow_followup(BID, "ian")
    lock = env._BATCH_RUN_LOCKS.get(BID)
    assert lock is None or not lock.locked()                     # lock freed for the next (manual gate@6) run
