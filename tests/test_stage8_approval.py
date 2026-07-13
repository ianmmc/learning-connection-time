"""gate@8 approval record — govdb tests (STAGE8 §2b/§2e). Real governance Postgres via gov_session."""
import json

import pytest

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage8_aggregate import approval as APV
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA

pytestmark = pytest.mark.govdb


def _ca(district_id="9999001", gross=420):
    """A minimal real closing argument (one accepted elementary school)."""
    acc = [{"band": "elementary", "school": "oak", "status": "accepted", "extraction_id": 1,
            "start_time": "08:00", "end_time": f"{8 + gross//60:02d}:{gross%60:02d}",
            "gross_minutes": gross, "method": "council_agree", "models_json": json.dumps(["m1", "m2"]),
            "rec_key": f"{district_id}:oak"}]
    return CA.build_closing_argument(district_id, merged_accepted=acc, merged_unresolved=[],
                                     nces_total=3, nces_by_level={"Elementary": 3}, schools_by_band={})


def test_record_approval_writes_row_and_state_event(gov_session):
    gdb.init_precious_schema()
    s = gov_session
    ca = _ca()
    aid = APV.record_decision(s, ca, disposition="approved", actor="ian", name="Test District", state="AL")
    s.flush()
    assert isinstance(aid, int)
    latest = APV.latest_decision(s, "9999001")
    assert latest["disposition"] == "approved" and latest["actor"] == "ian"
    # a gate@8 state_event was recorded alongside
    from sqlalchemy import text
    ev = s.execute(text("SELECT checkpoint, event_type, stage FROM state_event "
                        "WHERE district_id='9999001' AND checkpoint='gate@8' ORDER BY event_id DESC LIMIT 1")).mappings().first()
    assert ev["event_type"] == "approved" and ev["stage"] == 8


def test_decision_status_fresh_vs_stale(gov_session):
    gdb.init_precious_schema()
    s = gov_session
    ca = _ca(district_id="9999002", gross=420)
    APV.record_decision(s, ca, disposition="approved")
    s.flush()
    fp = CA.fingerprint(ca)
    fresh = APV.decision_status(s, "9999002", current_fingerprint=fp)
    assert fresh["is_approved"] is True and fresh["is_stale"] is False
    # a re-extraction that changed the picture -> a different fingerprint -> stale, not authorized
    ca2 = _ca(district_id="9999002", gross=430)
    stale = APV.decision_status(s, "9999002", current_fingerprint=CA.fingerprint(ca2))
    assert stale["is_stale"] is True and stale["is_approved"] is False


def test_sent_back_requires_reason(gov_session):
    gdb.init_precious_schema()
    s = gov_session
    ca = _ca(district_id="9999003")
    with pytest.raises(ValueError):
        APV.record_decision(s, ca, disposition="sent_back")            # no reason
    aid = APV.record_decision(s, ca, disposition="sent_back", reason="high band unsatisfied (1/7) — 8->1")
    s.flush()
    assert APV.latest_decision(s, "9999003")["disposition"] == "sent_back"


def test_latest_decision_is_newest(gov_session):
    gdb.init_precious_schema()
    s = gov_session
    ca = _ca(district_id="9999004")
    APV.record_decision(s, ca, disposition="sent_back", reason="thin coverage")
    APV.record_decision(s, ca, disposition="approved")
    s.flush()
    assert APV.latest_decision(s, "9999004")["disposition"] == "approved"   # append-only, newest wins
