"""#154 — gate@7 request-loop lineage: _request_lineage makes the loop legible (where an executed
directive went + the target's live state; why an approved/pending one can't fire). govdb — seeds
extraction_request + handoff/batch rows and asserts the resolved lineage."""
import json

import pytest
from sqlalchemy import text

from tests import benchmark_seed as BSEED

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import models  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.govdb]

DID = "ZZLIN"


def _req(con, route, status, *, ref=None, params=None):
    rid = con.execute(text(
        "INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, band, "
        "params_json, reason, status, executed_ref, created_at) VALUES "
        "(:d, 'h', 'representation', :r, 't', NULL, :p, 'x', :s, :ref, '2026-07-05T00:00:00Z') "
        "RETURNING request_id"),
        {"d": DID, "r": route, "s": status, "ref": ref,
         "p": json.dumps(params) if params else None}).scalar()
    return con.execute(text("SELECT request_id, route, status, executed_ref, params_json, district_id "
                            "FROM extraction_request WHERE request_id = :i"), {"i": rid}).mappings().first()


@pytest.fixture
def env():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    gdb.init_precious_schema()
    from infrastructure.acquisition.process_governance import server
    # Proper `with` (crossfam #445): the old direct __enter__ + rollback never ran __exit__, so the
    # session was never closed/returned — a per-test connection leak. The rollback in the finally
    # still discards the test's writes (incl. the DELETE); __exit__ then commits an empty txn and
    # closes the session.
    with gdb.session_scope() as con:
        con.execute(text("DELETE FROM extraction_request WHERE district_id = :d"), {"d": DID})
        try:
            yield server, con
        finally:
            con.rollback()


def _lin(server, con, req):
    ctx = server._district_loop_ctx(con, DID)
    return server._request_lineage(con, DID, dict(req), ctx)


def test_executed_7to6_points_to_its_handoff(env):
    server, con = env
    BSEED.seed_handoff(con, "lin76", handoff_id="h_lin76")
    r = _req(con, "7->6", "executed", ref="lin76")
    lin = _lin(server, con, r)
    assert lin["kind"] == "handoff" and lin["ref"] == "lin76"
    assert lin["state"] == "dispatched — run extraction at Stage 6"     # no extraction rows yet


def test_executed_7to2_points_to_its_followup_batch(env):
    server, con = env
    BSTORE.create_batch(con, {"batch_id": "batch_zzlin", "created": "t", "nces_year": "2024_25",
                              "districts": []}, batch_type="follow-up", actor="zz")
    r = _req(con, "7->2", "executed", ref="batch_zzlin")
    lin = _lin(server, con, r)
    assert lin["kind"] == "batch" and lin["ref"] == "batch_zzlin" and lin["batch_status"] == "draft"


def test_approved_7to6_is_blocked_when_rounds_exhausted(env):
    server, con = env
    # two executed rounds (distinct refs) -> at the default cap (2) -> the 3rd is a depth-blocked zombie
    _req(con, "7->6", "executed", ref="round_a")
    _req(con, "7->6", "executed", ref="round_b")
    r = _req(con, "7->6", "approved")
    lin = _lin(server, con, r)
    assert lin and lin.get("blocked") and "depth guard" in lin["reason"]


def test_7to2_defer_is_LIVE_not_detect_time_params(env):
    """R8 (review of 9e3b085): the deferred note must track the LIVE compose check
    (_defer_76_districts), never the request's detect-time params — once the district's 7->6s are
    resolved, the stale params must not show a forever-deferred card."""
    server, con = env
    # detect-time params SAY deferred, but there is NO live un-executed 7->6 -> no defer note
    r = _req(con, "7->2", "pending", params={"pending_alt_reps": 2})
    assert _lin(server, con, r) is None
    # now a LIVE pending 7->6 exists -> the same 7->2 shows deferred (count from live state)
    _req(con, "7->6", "pending")
    lin = _lin(server, con, r)
    assert lin and lin.get("deferred") and "1 un-executed 7->6" in lin["reason"]


def test_7to2_not_deferred_when_the_76s_are_zombies(env):
    """R2 interplay: rounds exhausted -> the district's un-executed 7->6s can never fire, compose
    does NOT hold the 7->2 — so neither does the card."""
    server, con = env
    _req(con, "7->6", "executed", ref="ra")
    _req(con, "7->6", "executed", ref="rb")        # 2/2 rounds spent
    _req(con, "7->6", "pending")                   # a zombie
    r = _req(con, "7->2", "pending", params={"pending_alt_reps": 1})
    assert _lin(server, con, r) is None            # compose would sweep it; card must agree


def test_ordinary_pending_request_has_no_lineage(env):
    server, con = env
    assert _lin(server, con, _req(con, "7->2", "pending")) is None
