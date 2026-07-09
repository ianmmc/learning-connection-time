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
                "district_id": "ZZTEST01", "name": "Testville", "state": "IA", "n_reps": 1, "n_judged": 1,
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
                        "created_by, run_kind FROM extraction WHERE extraction_id = :e"), {"e": eid}).one()
    assert ex.district_id == "ZZTEST01"
    assert ex.n_accepted == 1 and ex.n_unresolved == 1
    assert abs(ex.cost_usd - 0.0012) < 1e-9 and ex.created_by == "zz-test"
    assert ex.run_kind == "production"    # #148: a run with no run_kind persists as production

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

    ev = s.execute(text("SELECT stage, stage_name, event_type, note, state FROM state_event "
                        "WHERE district_id = 'ZZTEST01' AND event_type = 'extracted'")).one()
    assert ev.stage == 7 and ev.stage_name == "extract" and ev.note == "testhash7"
    assert ev.state == "IA"    # #165: the extract event must carry the district state


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


def test_persist_records_probe_run_kind(gov_session):
    """#148: a probe run (run_kind='probe' in the results dict, e.g. image_handoff_variant's output)
    persists that on the extraction row so the console can exclude it."""
    gdb.init_precious_schema()
    s = gov_session
    run = _synthetic_run()
    run["handoff_hash"] = "testhash7-image"
    run["run_kind"] = "probe"
    summ = R7.persist_run_session(s, run, created_by="zz-test")
    s.flush()
    eid = summ["districts"][0]["extraction_id"]
    rk = s.execute(text("SELECT run_kind FROM extraction WHERE extraction_id = :e"), {"e": eid}).scalar()
    assert rk == "probe"


def test_console_query_excludes_probe_runs_including_non_image_suffix(gov_session):
    """#148 core fix: the gate@7 left-pane query (latest production extraction per district) must
    exclude probe runs — INCLUDING a non-'-image' variant suffix (`-vision2`) that the old
    `handoff_hash NOT LIKE '%-image'` filter silently let through, shadowing the production run."""
    gdb.init_precious_schema()
    s = gov_session
    prod = _synthetic_run(); prod["district_id"] = "ZZSHADOW"
    prod["districts"]["ZZSHADOW"] = prod["districts"].pop("ZZTEST01")
    prod["districts"]["ZZSHADOW"]["district_id"] = "ZZSHADOW"
    R7.persist_run_session(s, prod, created_by="zz-prod")
    # a LATER probe with a brand-new council suffix — higher extraction_id, would win a naive MAX()
    probe = dict(prod); probe["handoff_hash"] = "testhash7-vision2"; probe["run_kind"] = "probe"
    R7.persist_run_session(s, probe, created_by="zz-probe")
    s.flush()
    # the exact left-pane selector: latest PRODUCTION extraction per district
    row = s.execute(text(
        "SELECT e.handoff_hash, e.created_by FROM extraction e "
        "JOIN (SELECT district_id, MAX(extraction_id) mx FROM extraction "
        "      WHERE run_kind = 'production' GROUP BY district_id) L ON L.mx = e.extraction_id "
        "WHERE e.district_id = 'ZZSHADOW'")).one()
    assert row.created_by == "zz-prod" and row.handoff_hash == "testhash7"   # NOT the probe


def _run_for(district_id: str, handoff_hash: str) -> dict:
    r = _synthetic_run()
    r["handoff_hash"] = handoff_hash
    pd = r["districts"].pop("ZZTEST01")
    pd["district_id"] = district_id
    r["districts"] = {district_id: pd}
    return r


def test_run_kind_backfill_flips_legacy_image_rows(gov_session):
    """#148 migration: the idempotent backfill flips a pre-migration `-image` extraction (which the
    ADD COLUMN default stamped 'production') to 'probe', and leaves a real production row alone."""
    gdb.init_precious_schema()
    s = gov_session
    # simulate two PRE-migration rows: written with no run_kind → both default to 'production'
    # (persist fills every NOT NULL column; the raw-INSERT shortcut would trip created_at NOT NULL).
    R7.persist_run_session(s, _run_for("ZZBF", "bf0011223344"), created_by="zz")
    R7.persist_run_session(s, _run_for("ZZBF", "bf0011223344-image"), created_by="zz")
    s.flush()
    # the backfill statement from db._PRECIOUS_ALTERS (guarded → idempotent)
    for _ in range(2):   # run twice — proves the guard makes it a no-op on re-run
        s.execute(text("UPDATE extraction SET run_kind = 'probe' "
                       "WHERE handoff_hash LIKE '%-image' AND run_kind = 'production'"))
    s.flush()
    kinds = dict(s.execute(text("SELECT handoff_hash, run_kind FROM extraction WHERE district_id='ZZBF'")).all())
    assert kinds["bf0011223344"] == "production"        # real production run untouched
    assert kinds["bf0011223344-image"] == "probe"       # legacy vision probe flipped


def test_detect_and_persist_requests_dedups(gov_session, monkeypatch):
    """The request-loop persist path: NEW requests inserted, re-detect is idempotent (natural-key
    dedup), human review status preserved. DB inputs mocked so no district_target/representation setup."""
    gdb.init_precious_schema()
    s = gov_session
    # claimed elementary+high; high has no facts -> one district 7->2 request. No alternates. Both
    # bands are real (real_bands={elementary,high}), so the #175 phantom gate doesn't suppress high.
    monkeypatch.setattr(R7, "_district_request_inputs",
                        lambda sess, res: (["elementary", "high"], {"high": ["A High"]}, {}, set(),
                                           {"elementary", "high"}))
    result = {"district_id": "ZZREQ1", "reps": [],
              "accepted": [{"band": "elementary", "school": "e"}], "unresolved": []}

    n1 = R7.detect_and_persist_requests(s, result, "hhreqtest")
    s.flush()
    assert n1 == 1
    row = s.execute(text("SELECT altitude, route, band, status FROM extraction_request "
                         "WHERE handoff_hash = 'hhreqtest'")).one()
    assert row.altitude == "district" and row.route == "7->2" and row.band == "high"
    assert row.status == "pending"

    # a human reviews it -> approved; a re-detect must NOT clobber that or duplicate
    s.execute(text("UPDATE extraction_request SET status='approved', reviewed_by='zz' "
                   "WHERE handoff_hash='hhreqtest'"))
    s.flush()
    n2 = R7.detect_and_persist_requests(s, result, "hhreqtest")
    s.flush()
    assert n2 == 0
    still = s.execute(text("SELECT status, COUNT(*) c FROM extraction_request "
                           "WHERE handoff_hash='hhreqtest' GROUP BY status")).all()
    assert len(still) == 1 and still[0].status == "approved" and still[0].c == 1
