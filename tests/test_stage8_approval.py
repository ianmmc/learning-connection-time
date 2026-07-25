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


def test_staleness_derives_from_receipt_not_the_stored_stamp(gov_session):
    """REQ-147 (the 2026-07-14 incident): a fingerprint-basis evolution between decision time and
    now must NOT fake staleness on an unchanged picture. Simulate a legacy-era approval by
    corrupting the stored stamp — the receipt still hashes equal to the live picture, so the
    decision stays fresh; a real content change still goes stale."""
    from sqlalchemy import text
    gdb.init_precious_schema()
    s = gov_session
    ca = _ca(district_id="9999004", gross=420)
    aid = APV.record_decision(s, ca, disposition="approved")
    s.flush()
    # a hash-function change at decision time == a stamp today's code can't reproduce
    s.execute(text("UPDATE stage8_approval SET facts_fingerprint='legacy-era-hash' "
                   "WHERE approval_id=:a"), {"a": aid})
    fresh = APV.decision_status(s, "9999004", current_fingerprint=CA.fingerprint(ca))
    assert fresh["is_stale"] is False and fresh["is_approved"] is True
    # ...while a REAL content change is still caught
    ca2 = _ca(district_id="9999004", gross=430)
    stale = APV.decision_status(s, "9999004", current_fingerprint=CA.fingerprint(ca2))
    assert stale["is_stale"] is True


def test_staleness_falls_back_to_stamp_when_receipt_unparseable(gov_session):
    from sqlalchemy import text
    gdb.init_precious_schema()
    s = gov_session
    ca = _ca(district_id="9999005", gross=420)
    aid = APV.record_decision(s, ca, disposition="approved")
    s.flush()
    s.execute(text("UPDATE stage8_approval SET receipt_json='not json' WHERE approval_id=:a"),
              {"a": aid})
    fp = CA.fingerprint(ca)
    st = APV.decision_status(s, "9999005", current_fingerprint=fp)
    assert st["is_stale"] is False            # the stamp (made with current code here) still matches
    st2 = APV.decision_status(s, "9999005", current_fingerprint="moved" + fp)
    assert st2["is_stale"] is True


def test_decision_status_never_ships_the_receipt(gov_session):
    gdb.init_precious_schema()
    s = gov_session
    ca = _ca(district_id="9999006")
    APV.record_decision(s, ca, disposition="approved")
    s.flush()
    st = APV.decision_status(s, "9999006", current_fingerprint=CA.fingerprint(ca))
    assert "receipt_json" not in st["latest"]


# ----------------------------- gate@8 capture-dir audit receipt (REQ-164) -----------------------------
def test_gate8_receipt_payload_projection():
    """The per-district gate@8 receipt is a faithful projection (bands -> gross_minutes+method) that
    points at the authoritative frozen record, not a copy of the full closing argument."""
    ca = {"district_id": "9999010",
          "bands": {"elementary": {"gross_minutes": 400, "method": "modal", "schools": [1, 2]},
                    "high": {"gross_minutes": 450, "method": "modal"}}}
    p = APV.gate8_receipt_payload(ca, disposition="approved", reason=None, approval_id=42,
                                  actor="ian", fingerprint="fp-abc")
    assert p["stage"] == 8 and p["checkpoint"] == "gate@8"
    assert p["district_id"] == "9999010" and p["disposition"] == "approved"
    assert p["approval_id"] == 42 and p["facts_fingerprint"] == "fp-abc" and p["actor"] == "ian"
    assert p["authoritative"].startswith("gov_db:stage8_approval")
    assert p["bands"] == {"elementary": {"gross_minutes": 400, "method": "modal"},
                          "high": {"gross_minutes": 450, "method": "modal"}}


def test_gate8_receipt_payload_sent_back_carries_reason():
    """A send-back is an auditable state transition too -- it gets a receipt carrying its reason."""
    p = APV.gate8_receipt_payload({"district_id": "9999011", "bands": {}}, disposition="sent_back",
                                  reason="middle band unresolved", approval_id=7, actor="ian",
                                  fingerprint="fp-x")
    assert p["disposition"] == "sent_back" and p["reason"] == "middle band unresolved"
    assert p["bands"] == {}
