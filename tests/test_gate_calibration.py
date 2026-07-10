"""REQ-121 / issue #210 — the gate@5/6/7 calibration WIRING (console → calibration records).

Pure builder tests (the console→calibration vocab translation, DB-free) + govdb integration tests that
drive each gate's REAL write path and assert a calibration_event row lands with the right proxy/decision/
agreed/slice. gate@8 (approving extracted TIMES) is deferred until Stage 8 is built (Ian, 2026-07-10)."""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import gate_calibration as GCAL
from infrastructure.acquisition.process_governance import stage6_dispatch as BR

pytestmark_govdb = pytest.mark.govdb


# ============================= pure builders (no DB) =============================
def test_gate5_maps_label_vocab_and_computes_the_survivorship_signal():
    # tier-D record (auto would REJECT) that the human labels a target (accept) -> agreed False: the
    # false-negative auto would have made — the exact signal the calibration corpus exists to surface.
    r = GCAL.gate5_label_record(rec_key="d:1", district_id="d", tier="D", sort_score=0.12,
                                primary_label="school_bell_table", status="labeled", state="WI",
                                created_at="t")
    assert r["gate"] == "gate@5" and r["proxy_name"] == "sort_score" and r["proxy_value"] == 0.12
    assert r["human_decision"] == "accept" and r["auto_recommendation"] == "reject" and r["agreed"] is False
    assert r["state"] == "WI"


def test_gate5_tierA_target_agrees_and_BC_escalates_to_none():
    assert GCAL.gate5_label_record(rec_key="d:2", district_id="d", tier="A", sort_score=0.9,
                                   primary_label="school_bell_table", status="labeled",
                                   created_at="t")["agreed"] is True
    # tier B/C: auto would HOLD (escalate) -> agreed None (the human-in-the-loop region, not a
    # unilateral-auto data point)
    assert GCAL.gate5_label_record(rec_key="d:3", district_id="d", tier="B", sort_score=0.5,
                                   primary_label="target_absent", status="labeled",
                                   created_at="t")["agreed"] is None


def test_gate5_returns_none_when_there_is_no_terminal_decision():
    # unlabeled status, missing label, and an off-axis label are all "no calibration data point".
    assert GCAL.gate5_label_record(rec_key="d:4", district_id="d", tier="B", sort_score=0.5,
                                   primary_label=None, status="unlabeled", created_at="t") is None
    assert GCAL.gate5_label_record(rec_key="d:5", district_id="d", tier="A", sort_score=0.5,
                                   primary_label=None, status="labeled", created_at="t") is None
    assert GCAL.gate5_label_record(rec_key="d:6", district_id="d", tier="A", sort_score=0.5,
                                   primary_label="some_new_shape", status="labeled", created_at="t") is None


def test_gate6_is_accept_only_with_the_n_send_proxy():
    r = GCAL.gate6_dispatch_record(handoff_hash="abc123", district_id="d1", n_send=3, state="CA",
                                   created_at="t")
    assert r["gate"] == "gate@6" and r["item_id"] == "abc123:d1"   # handoff-scoped -> re-dispatches distinct
    assert r["proxy_name"] == "n_send" and r["proxy_value"] == 3.0
    assert r["human_decision"] == "accept" and r["auto_recommendation"] == "accept" and r["agreed"] is True
    # n_send == 0 -> auto would NOT dispatch, but the human did -> disagreement captured
    assert GCAL.gate6_dispatch_record(handoff_hash="abc", district_id="d", n_send=0,
                                      created_at="t")["agreed"] is False


def test_gate7_uses_the_council_agreement_ratio_and_skips_pending():
    r = GCAL.gate7_request_record(request_id=5, district_id="d", status="approved",
                                  n_accepted=4, n_unresolved=1, band="high", state="WI",
                                  run_kind="production", created_at="t")
    assert r["gate"] == "gate@7" and r["item_id"] == "request:5"
    assert r["proxy_name"] == "council_agreement" and r["proxy_value"] == 0.8   # 4/(4+1)
    assert r["human_decision"] == "accept" and r["school_level"] == "high" and r["run_kind"] == "production"
    assert GCAL.gate7_request_record(request_id=6, district_id="d", status="rejected",
                                     n_accepted=1, n_unresolved=1, created_at="t")["human_decision"] == "reject"
    # 'pending' reopen is not a terminal decision; a zero-fact extraction -> None proxy (not a crash)
    assert GCAL.gate7_request_record(request_id=7, district_id="d", status="pending",
                                     n_accepted=0, n_unresolved=0, created_at="t") is None
    assert GCAL.gate7_request_record(request_id=8, district_id="d", status="approved",
                                     n_accepted=0, n_unresolved=0, created_at="t")["proxy_value"] is None


# ============================= govdb integration (real write paths) =============================
ZZ = "ZZCAL"


def _cleanup(con):
    con.execute(text("DELETE FROM calibration_event WHERE district_id LIKE :p"), {"p": f"{ZZ}%"})
    con.execute(text("DELETE FROM label WHERE rec_key LIKE :p"), {"p": f"{ZZ}%"})
    con.execute(text("DELETE FROM record WHERE district_id LIKE :p"), {"p": f"{ZZ}%"})
    con.execute(text("DELETE FROM district WHERE district_id LIKE :p"), {"p": f"{ZZ}%"})
    con.execute(text("DELETE FROM extraction_request WHERE district_id LIKE :p"), {"p": f"{ZZ}%"})
    con.execute(text("DELETE FROM extraction WHERE district_id LIKE :p"), {"p": f"{ZZ}%"})


@pytest.fixture
def client():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.process_governance import server
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    gdb.init_precious_schema()                 # creates calibration_event too (PR #217)
    with gdb.session_scope() as con:
        BS.ensure_signal_schema(con)
        _cleanup(con)
    try:
        yield TestClient(server.app)
    finally:
        with gdb.session_scope() as con:
            _cleanup(con)


@pytest.mark.integration
@pytest.mark.govdb
def test_gate5_label_writes_a_calibration_row(client):
    did, rk = ZZ + "D", ZZ + "D:r"
    with gdb.session_scope() as con:
        con.execute(text("INSERT INTO district (district_id, name, state) VALUES (:d,'ZZ',:s)"),
                    {"d": did, "s": "WI"})
        con.execute(text("""INSERT INTO record (rec_key, district_id, url, tier, sort_score, is_cluster_rep)
            VALUES (:rk,:d,'http://z','D',0.11,1)"""), {"rk": rk, "d": did})
        con.execute(text("INSERT INTO label (rec_key, status) VALUES (:rk,'unlabeled')"), {"rk": rk})
    # human labels the tier-D record a TARGET (accept) — a false negative auto would have made
    r = client.post(f"/api/label/{rk}", json={"primary_label": "school_bell_table", "status": "labeled"})
    assert r.status_code == 200
    with gdb.session_scope() as con:
        row = con.execute(text(
            """SELECT gate, proxy_name, proxy_value, human_decision, auto_recommendation, agreed, state
               FROM calibration_event WHERE item_id = :rk"""), {"rk": rk}).mappings().one()
    assert row["gate"] == "gate@5" and row["proxy_name"] == "sort_score" and row["proxy_value"] == 0.11
    assert row["human_decision"] == "accept" and row["auto_recommendation"] == "reject"
    assert row["agreed"] is False and row["state"] == "WI"


@pytest.mark.integration
@pytest.mark.govdb
def test_gate5_unlabeled_writes_no_calibration_row(client):
    did, rk = ZZ + "U", ZZ + "U:r"
    with gdb.session_scope() as con:
        con.execute(text("INSERT INTO district (district_id, name, state) VALUES (:d,'ZZ','CA')"), {"d": did})
        con.execute(text("""INSERT INTO record (rec_key, district_id, url, tier, sort_score, is_cluster_rep)
            VALUES (:rk,:d,'http://z','B',0.5,1)"""), {"rk": rk, "d": did})
        con.execute(text("INSERT INTO label (rec_key, status) VALUES (:rk,'unlabeled')"), {"rk": rk})
    r = client.post(f"/api/label/{rk}", json={"status": "unlabeled"})   # a no-decision save
    assert r.status_code == 200
    with gdb.session_scope() as con:
        n = con.execute(text("SELECT COUNT(*) FROM calibration_event WHERE item_id=:rk"), {"rk": rk}).scalar()
    assert n == 0


@pytest.mark.govdb
def test_gate6_dispatch_writes_a_calibration_row_per_district(gov_session):
    gdb.init_precious_schema()   # ensure state_event + calibration_event exist
    doc = {"handoff_hash": "zzhash", "districts": [
        {"district_id": ZZ + "6", "records": [{"rec_key": "a", "decision": "send"},
                                              {"rec_key": "b", "decision": "hold"}]}],
        "fingerprints": {}}
    metas = {ZZ + "6": {"name": "ZZ Six", "state": "TX", "labeled_topology": "per_school"}}
    BR._record_dispatched_events(gov_session, doc, actor="zz-test", metas=metas)
    row = gov_session.execute(text(
        """SELECT gate, proxy_name, proxy_value, human_decision, state FROM calibration_event
           WHERE item_id = :it"""), {"it": f"zzhash:{ZZ}6"}).mappings().one()
    assert row["gate"] == "gate@6" and row["proxy_name"] == "n_send" and row["proxy_value"] == 1.0
    assert row["human_decision"] == "accept" and row["state"] == "TX"
    # the existing dispatched state_event is still written alongside (same transaction, not displaced)
    ev = gov_session.execute(text(
        "SELECT COUNT(*) FROM state_event WHERE district_id=:d AND checkpoint='gate@6'"),
        {"d": ZZ + "6"}).scalar()
    assert ev == 1


@pytest.mark.integration
@pytest.mark.govdb
def test_gate7_request_review_writes_a_calibration_row(client):
    from infrastructure.acquisition.stage7_extract.models import Extraction, ExtractionRequest
    did = ZZ + "7"
    with gdb.session_scope() as con:
        con.execute(text("INSERT INTO district (district_id, name, state) VALUES (:d,'ZZ','NY')"), {"d": did})
        con.add(Extraction(handoff_hash="zz7hash", district_id=did, run_kind="production",
                           n_accepted=3, n_unresolved=1))                      # ORM defaults fill the NOT NULLs
        req = ExtractionRequest(district_id=did, handoff_hash="zz7hash", altitude="representation",
                                route="7->6", target="a", band="high", reason="need alt rep", status="pending")
        con.add(req)
        con.flush()
        rid = req.request_id
    r = client.post(f"/api/extract/request/{rid}", json={"status": "approved", "actor": "zz-test"})
    assert r.status_code == 200
    with gdb.session_scope() as con:
        row = con.execute(text(
            """SELECT gate, proxy_name, proxy_value, human_decision, school_level, run_kind, state
               FROM calibration_event WHERE item_id = :it"""), {"it": f"request:{rid}"}).mappings().one()
    assert row["gate"] == "gate@7" and row["proxy_name"] == "council_agreement"
    assert row["proxy_value"] == 0.75 and row["human_decision"] == "accept"   # 3/(3+1)
    assert row["school_level"] == "high" and row["run_kind"] == "production" and row["state"] == "NY"
