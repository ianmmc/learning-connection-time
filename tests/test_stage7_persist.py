"""Stage 7 governance persistence (REQ-117, slice 3): extraction + school_fact rows + the stage=7
state_event, written on a caller session so the rollback fixture isolates it. No paid calls — a
synthetic run dict stands in for `run_council`'s output. govdb-marked (needs the governance DB)."""
import json

import pytest

pytestmark = pytest.mark.govdb

from sqlalchemy import text  # noqa: E402
from infrastructure.acquisition.common import db as gdb  # noqa: E402
from infrastructure.acquisition.process_governance import stage7_run as R7  # noqa: E402


def _synthetic_run():
    return {
        "handoff_hash": "testhash7",
        "districts": {
            "ZZTEST01": {
                "district_id": "ZZTEST01", "name": "Testville", "n_reps": 1, "n_judged": 1,
                "telemetry": {"calls": 3, "judge_calls": 1, "errors": 0,
                              "prompt_tokens": 100, "completion_tokens": 40, "cost_usd": 0.0012},
                "accepted": [
                    {"band": "elementary", "school": "brick mill", "start": "09:10", "end": "15:50",
                     "gross": 400, "models": ["google/gemini-2.5-flash-lite",
                                              "mistralai/mistral-small-24b-instruct-2501"],
                     "method": "council_agree", "rec_key": "ZZTEST01:abc123", "source_file": "pdftotext.txt"},
                ],
                "unresolved": [
                    {"band": "high", "school": "special program", "reason": "disagree",
                     "starts": {"m1": "08:00", "m2": "08:20"}, "ends": {"m1": "15:00", "m2": "14:40"},
                     "rec_key": "ZZTEST01:abc123", "source_file": "pdftotext.txt"},
                ],
            }
        },
        "telemetry": {"calls": 3, "judge_calls": 1, "errors": 0,
                      "prompt_tokens": 100, "completion_tokens": 40, "cost_usd": 0.0012},
    }


def test_persist_writes_extraction_facts_and_event(gov_session):
    gdb.init_precious_schema()   # ensure extraction/school_fact exist (committed DDL, harmless)
    s = gov_session

    summ = R7.persist_run_session(s, _synthetic_run(), created_by="zz-test", receipt_path="/tmp/r.json")
    s.flush()

    assert summ["n_facts"] == 2
    eid = summ["districts"][0]["extraction_id"]

    ex = s.execute(text("SELECT district_id, n_accepted, n_unresolved, cost_usd, receipt_path, "
                        "created_by FROM extraction WHERE extraction_id = :e"), {"e": eid}).one()
    assert ex.district_id == "ZZTEST01"
    assert ex.n_accepted == 1 and ex.n_unresolved == 1
    assert abs(ex.cost_usd - 0.0012) < 1e-9 and ex.created_by == "zz-test"

    facts = s.execute(text("SELECT band, school, status, gross_minutes, method, models_json, "
                           "detail_json FROM school_fact WHERE extraction_id = :e ORDER BY status"),
                      {"e": eid}).all()
    assert len(facts) == 2
    accepted = [f for f in facts if f.status == "accepted"][0]
    assert accepted.band == "elementary" and accepted.gross_minutes == 400
    assert accepted.method == "council_agree"
    assert "gemini" in accepted.models_json
    unresolved = [f for f in facts if f.status == "unresolved"][0]
    assert unresolved.school == "special program" and unresolved.method == "disagree"
    assert json.loads(unresolved.detail_json)["starts"]["m2"] == "08:20"

    ev = s.execute(text("SELECT stage, stage_name, event_type, note FROM state_event "
                        "WHERE district_id = 'ZZTEST01' AND event_type = 'extracted'")).one()
    assert ev.stage == 7 and ev.stage_name == "extract" and ev.note == "testhash7"


def test_persist_appends_new_extraction_on_rerun(gov_session):
    gdb.init_precious_schema()
    s = gov_session
    a = R7.persist_run_session(s, _synthetic_run(), created_by="zz-test")
    s.flush()
    b = R7.persist_run_session(s, _synthetic_run(), created_by="zz-test")
    s.flush()
    # append-only: two distinct extraction rows for the same (handoff, district)
    assert a["districts"][0]["extraction_id"] != b["districts"][0]["extraction_id"]
    n = s.execute(text("SELECT COUNT(*) FROM extraction WHERE district_id='ZZTEST01' "
                       "AND handoff_hash='testhash7'")).scalar()
    assert n >= 2
