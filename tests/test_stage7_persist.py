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


# --------------------------- #231: history-aware alternate exclusion ---------------------------
def test_request_inputs_exclude_reps_sent_in_prior_rounds(gov_session):
    """#231: the 7->6 alternate list must subtract every rep the record's request lineage names as
    sent in ANY prior round — not just this dispatch's reps. Live counterexample: Union Hill round 2
    re-offered round-1's failed tesseract_raster.txt as the TOP alternate (#3624)."""
    gdb.init_precious_schema()
    s = gov_session
    rk = "ZZTEST31:r1"
    # the record's captured, dispatchable inventory: 4 usable reps
    for fn, kind, nt in (("a.txt", "text", 30), ("b.txt", "text", 20),
                         ("c.png", "image", None), ("d.txt", "text", 10)):
        s.execute(text("INSERT INTO representation (rec_key, source, filename, file_kind, n_chars, "
                       "n_times, usable) VALUES (:k, 'test', :f, :kd, 100, :nt, 1)"),
                  {"k": rk, "f": fn, "kd": kind, "nt": nt})
    # round 1's lineage: a request naming a.txt as sent (single legacy sent_file — the fallback path)
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, params_json, reason, status, created_at) VALUES "
                   "('ZZTEST31', 'h1', 'representation', '7->6', :t, :p, 'r', 'executed', 't1')"),
              {"t": rk, "p": json.dumps({"sent_file": "a.txt"})})
    # round 2's lineage: a request naming BOTH files of a multi-rep send (the sent_files list path)
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, params_json, reason, status, created_at) VALUES "
                   "('ZZTEST31', 'h2', 'representation', '7->6', :t, :p, 'r', 'pending', 't2')"),
              {"t": rk, "p": json.dumps({"sent_file": "b.txt", "sent_files": ["b.txt", "d.txt"]})})
    # the current (round 3) result sent c.png, barren
    result = {"district_id": "ZZTEST31", "reps": [{"rec_key": rk, "file": "c.png", "accepted": []}]}
    _, _, alts, _, _ = R7._district_request_inputs(s, result)
    # a.txt (round 1), b.txt + d.txt (round 2), c.png (current) are ALL excluded -> nothing remains
    assert rk not in alts or [a["file"] for a in alts[rk]] == []


def test_request_inputs_status_does_not_matter_for_history_exclusion(gov_session):
    """#231: emission itself proves the send — a REJECTED request's sent rep was still dispatched
    and barren, so it must stay excluded (a human 'no' on the retry doesn't un-send the original)."""
    gdb.init_precious_schema()
    s = gov_session
    rk = "ZZTEST32:r1"
    for fn, kind, nt in (("a.txt", "text", 30), ("b.png", "image", None)):
        s.execute(text("INSERT INTO representation (rec_key, source, filename, file_kind, n_chars, "
                       "n_times, usable) VALUES (:k, 'test', :f, :kd, 100, :nt, 1)"),
                  {"k": rk, "f": fn, "kd": kind, "nt": nt})
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, params_json, reason, status, created_at) VALUES "
                   "('ZZTEST32', 'h1', 'representation', '7->6', :t, :p, 'r', 'rejected', 't1')"),
              {"t": rk, "p": json.dumps({"sent_file": "a.txt"})})
    result = {"district_id": "ZZTEST32", "reps": [{"rec_key": rk, "file": "zz.txt", "accepted": []}]}
    _, _, alts, _, _ = R7._district_request_inputs(s, result)
    assert [a["file"] for a in alts.get(rk, [])] == ["b.png"]   # only the untried image remains


def _run_for(did, hh, accepted=(), unresolved=(), run_kind=None):
    """A minimal persistable run dict: accepted/unresolved as (band, school) pairs."""
    tel = {"calls": 1, "judge_calls": 0, "errors": 0,
           "prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.0001}
    d = {"district_id": did, "name": "Testville", "state": "IA", "n_reps": 1, "n_judged": 1,
         "telemetry": tel,
         "accepted": [{"band": b, "school": sc, "start": "08:00", "end": "15:00", "gross": 420,
                       "models": ["m1"], "method": "council_agree", "rec_key": f"{did}:x",
                       "source_file": "f"} for b, sc in accepted],
         "unresolved": [{"band": b, "school": sc, "reason": "disagree", "starts": {}, "ends": {},
                         "rec_key": f"{did}:x", "source_file": "f"} for b, sc in unresolved]}
    run = {"handoff_hash": hh, "districts": {did: d}, "telemetry": tel}
    if run_kind:
        run["run_kind"] = run_kind
    return run


def test_covered_bands_ignore_probe_run_facts(gov_session):
    """PR #221 review: a probe's accepted fact is a measurement, never coverage — it must neither
    suppress remedy detection (_district_request_inputs) nor let compose auto-reject an approved
    directive (_covered_bands_now). Only a PRODUCTION run's accepted fact covers a band."""
    from infrastructure.acquisition.process_governance import stage7_execute as EX
    gdb.init_precious_schema()
    s = gov_session
    did = "ZZTEST33"
    R7.persist_run_session(s, _run_for(did, "h-probe", accepted=[("elementary", "brick mill")],
                                       run_kind="probe"), created_by="zz-test")
    s.flush()
    _, _, _, covered, _ = R7._district_request_inputs(s, {"district_id": did, "reps": []})
    assert covered == set()                        # the probe's accepted fact is not coverage
    assert EX._covered_bands_now(s, [did]) == {}   # the compose twin agrees
    R7.persist_run_session(s, _run_for(did, "h-prod", accepted=[("middle", "jones middle")]),
                           created_by="zz-test")
    s.flush()
    _, _, _, covered, _ = R7._district_request_inputs(s, {"district_id": did, "reps": []})
    assert covered == {"middle"}                   # production coverage counts; probe's still doesn't
    assert EX._covered_bands_now(s, [did]) == {did: {"middle"}}


def test_sent_files_by_rec_includes_recapture_route_history(gov_session):
    """PR #221 review: the EXECUTION-side exclusion (_sent_files_by_rec, feeding _bundle_alternate)
    must read 7->3 lineage too, matching the detection side (#231) — a file recorded only on a
    RECAPTURE request was still sent and barren (F4), so it must never be re-dispatched."""
    from infrastructure.acquisition.process_governance import stage7_execute as EX
    gdb.init_precious_schema()
    s = gov_session
    rk = "ZZTEST34:r1"
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, params_json, reason, status, created_at) VALUES "
                   "('ZZTEST34', 'h1', 'url', :r3, :t, :p, 'r', 'executed', 't1')"),
              {"r3": EX.RQ.ROUTE_RECAPTURE, "t": rk, "p": json.dumps({"sent_file": "a.txt"})})
    assert EX._sent_files_by_rec(s, "ZZTEST34") == {rk: {"a.txt"}}


def test_list_view_sql_matches_merge_fact_runs(gov_session):
    """PR #221 review: the gate@7 list view's cumulative-count SQL (CUMULATIVE_FACT_COUNTS_SQL) and
    AGG.merge_fact_runs are two expressions of ONE rule — 'a pair counts unresolved only if NO run
    ever accepted it', production runs only. This cross-check on shared rows is what keeps the badge
    counts and the detail view from silently drifting apart."""
    from infrastructure.acquisition.process_governance import server as SRV
    from infrastructure.acquisition.stage8_aggregate import aggregate as AGG
    gdb.init_precious_schema()
    s = gov_session
    did = "ZZTEST35"
    R7.persist_run_session(s, _run_for(did, "h1", accepted=[("elementary", "brick mill")],
                                       unresolved=[("high", "special program")]), created_by="zz")
    R7.persist_run_session(s, _run_for(did, "h2", accepted=[("middle", "jones middle")],
                                       unresolved=[("elementary", "brick mill")]), created_by="zz")
    R7.persist_run_session(s, _run_for(did, "h3", accepted=[("high", "special program")],
                                       run_kind="probe"), created_by="zz")
    s.flush()
    sql_rows = {r["district_id"]: r for r in
                s.execute(text(SRV.CUMULATIVE_FACT_COUNTS_SQL)).mappings().all()}
    facts = s.execute(text(
        "SELECT f.extraction_id, e.handoff_hash, f.band, f.school, f.status, f.start_time, "
        "f.end_time, f.gross_minutes, f.method, f.models_json, f.detail_json, f.rec_key, "
        "f.source_file FROM school_fact f JOIN extraction e ON e.extraction_id = f.extraction_id "
        "WHERE f.district_id = :d AND e.run_kind = 'production'"), {"d": did}).mappings().all()
    accepted, unresolved = AGG.merge_fact_runs([dict(f) for f in facts])
    # accepted: run1's elementary + run2's middle; unresolved: high (its only accept was the probe's)
    assert (len(accepted), len(unresolved)) == (2, 1)
    assert (sql_rows[did]["n_accepted"], sql_rows[did]["n_unresolved"]) \
        == (len(accepted), len(unresolved))


# --------------------------- #234: cross-handoff open-request dedup ---------------------------
def test_detect_dedups_against_an_open_request_from_another_handoff(gov_session, monkeypatch):
    """#234: actioning ONE request spins a new handoff for the district; the re-detection under that
    handoff must not duplicate a sibling directive still OPEN from an earlier round (the live
    batch_00013 symptom: 0602559's high-band 7->2 pending twice, 4220130's across FOUR handoffs)."""
    gdb.init_precious_schema()
    s = gov_session
    monkeypatch.setattr(R7, "_district_request_inputs",
                        lambda sess, res: (["elementary", "high"], {"high": ["A High"]}, {}, set(),
                                           {"elementary", "high"}))
    result = {"district_id": "ZZREQ2", "reps": [],
              "accepted": [{"band": "elementary", "school": "e"}], "unresolved": []}
    assert R7.detect_and_persist_requests(s, result, "hh-round1") == 1   # round 1 emits the 7->2 high
    s.flush()
    assert R7.detect_and_persist_requests(s, result, "hh-round2") == 0   # round 2: still open -> no dup
    s.flush()
    n = s.execute(text("SELECT COUNT(*) FROM extraction_request WHERE district_id='ZZREQ2'")).scalar()
    assert n == 1


def test_detect_reemits_after_a_prior_round_was_actioned(gov_session, monkeypatch):
    """#234's counterweight: an EXECUTED (or otherwise closed) prior round does NOT block a new
    round's identical ask -- bounding repeat rounds is the depth guard's job, never dedup's."""
    gdb.init_precious_schema()
    s = gov_session
    monkeypatch.setattr(R7, "_district_request_inputs",
                        lambda sess, res: (["elementary", "high"], {"high": ["A High"]}, {}, set(),
                                           {"elementary", "high"}))
    result = {"district_id": "ZZREQ3", "reps": [],
              "accepted": [{"band": "elementary", "school": "e"}], "unresolved": []}
    assert R7.detect_and_persist_requests(s, result, "hh-r1") == 1
    s.flush()   # the ORM add must hit the DB before the raw UPDATE can see it
    s.execute(text("UPDATE extraction_request SET status='executed', executed_ref='batch_x' "
                   "WHERE district_id='ZZREQ3'"))
    s.flush()
    assert R7.detect_and_persist_requests(s, result, "hh-r2") == 1       # the gap persists -> new ask
    s.flush()
    n = s.execute(text("SELECT COUNT(*) FROM extraction_request WHERE district_id='ZZREQ3'")).scalar()
    assert n == 2


# --------------------------- #233: auto-withdraw satisfied directives ---------------------------
def _seed_requests(s, did, claimed):
    # every claimed band is backed by a real school — under #240's detect-consistent semantics an
    # unbacked claimed band is PHANTOM (unfillable), which is its own test case below, not this one
    sbb = {b: {"schools": [{"name": f"{b} school", "low": "KG", "high": "12"}]} for b in claimed}
    s.execute(text("INSERT INTO district_target (district_id, lea_claimed_bands_json, "
                   "schools_by_band_json) VALUES (:d, :c, :s)"),
              {"d": did, "c": json.dumps(claimed), "s": json.dumps(sbb)})
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, "
                   "band, params_json, reason, status, created_at) VALUES "
                   "(:d, 'h1', 'district', '7->2', :d, 'high', '{}', 'r', 'pending', 't1'), "
                   "(:d, 'h1', 'representation', '7->6', :t, NULL, '{}', 'r', 'approved', 't1')"),
              {"d": did, "t": f"{did}:rec1"})


def test_withdraw_band_scoped_when_covered_record_scoped_only_when_no_gap_left(gov_session):
    """#233: a 7->2 for band B withdraws once B has a cumulative accepted fact; a band-NULL 7->6
    withdraws only when NO claimed band remains uncovered (it might fill any remaining gap)."""
    gdb.init_precious_schema()
    s = gov_session
    did = "ZZWDR1"
    _seed_requests(s, did, ["elementary", "high"])
    R7.persist_run_session(s, _run_for(did, "hw1", accepted=[("high", "hs")]), created_by="zz")
    s.flush()
    wd = R7.withdraw_satisfied_requests(s, did)
    assert len(wd) == 1                                            # only the band-scoped 7->2
    rows = {r.route: r for r in s.execute(text(
        "SELECT route, status, reviewed_by, review_note FROM extraction_request "
        "WHERE district_id=:d"), {"d": did}).all()}
    assert rows["7->2"].status == "withdrawn"
    assert rows["7->2"].reviewed_by == "auto:premise-satisfied"
    assert "band 'high'" in rows["7->2"].review_note
    assert rows["7->6"].status == "approved"                       # elementary still uncovered
    R7.persist_run_session(s, _run_for(did, "hw2", accepted=[("elementary", "es")]), created_by="zz")
    s.flush()
    wd2 = R7.withdraw_satisfied_requests(s, did)
    assert len(wd2) == 1                                           # now the record-scoped 7->6 too
    r76 = s.execute(text("SELECT status, review_note FROM extraction_request "
                         "WHERE district_id=:d AND route='7->6'"), {"d": did}).one()
    assert r76.status == "withdrawn" and "no fillable gap remains" in r76.review_note


def test_withdraw_ignores_probe_facts_and_actioned_rows(gov_session):
    """#233: a probe's accepted fact is a measurement, never a premise-satisfier; and rows a human
    (or compose) already actioned are untouched -- only OPEN rows are eligible."""
    gdb.init_precious_schema()
    s = gov_session
    did = "ZZWDR2"
    _seed_requests(s, did, ["elementary", "high"])
    s.execute(text("UPDATE extraction_request SET status='rejected' "
                   "WHERE district_id=:d AND route='7->6'"), {"d": did})
    R7.persist_run_session(s, _run_for(did, "hwp", accepted=[("high", "hs")], run_kind="probe"),
                           created_by="zz")
    s.flush()
    assert R7.withdraw_satisfied_requests(s, did) == []            # probe coverage counts for nothing
    R7.persist_run_session(s, _run_for(did, "hwq", accepted=[("high", "hs")]), created_by="zz")
    s.flush()
    wd = R7.withdraw_satisfied_requests(s, did)
    assert len(wd) == 1 and "band 'high'" in wd[0][1]              # only the pending 7->2 withdraws
    rej = s.execute(text("SELECT status FROM extraction_request WHERE district_id=:d AND route='7->6'"),
                    {"d": did}).scalar()
    assert rej == "rejected"                                       # the actioned row stays actioned


def test_withdrawn_does_not_block_reemission(gov_session, monkeypatch):
    """#233 x #234: 'withdrawn' is not an OPEN status -- if the gap ever re-opens, a fresh
    re-detection re-emits a new pending directive instead of being deduped into silence."""
    gdb.init_precious_schema()
    s = gov_session
    monkeypatch.setattr(R7, "_district_request_inputs",
                        lambda sess, res: (["elementary", "high"], {"high": ["A High"]}, {}, set(),
                                           {"elementary", "high"}))
    result = {"district_id": "ZZWDR3", "reps": [],
              "accepted": [{"band": "elementary", "school": "e"}], "unresolved": []}
    assert R7.detect_and_persist_requests(s, result, "hh-w1") == 1
    s.flush()   # the ORM add must hit the DB before the raw UPDATE can see it
    s.execute(text("UPDATE extraction_request SET status='withdrawn' WHERE district_id='ZZWDR3'"))
    s.flush()
    assert R7.detect_and_persist_requests(s, result, "hh-w2") == 1   # re-emitted, not deduped


def test_withdraw_no_gap_left_uses_fillable_not_raw_claimed_bands(gov_session):
    """#233 review: a PHANTOM claimed band (no real school serves it) can never be covered, so the
    no-gap-left check must run on claimed ∩ real (detect's #175 predicate) — raw `claimed` would
    leave record-scoped directives un-withdrawable forever for exactly those districts."""
    gdb.init_precious_schema()
    s = gov_session
    did = "ZZWDR4"
    # claimed: elementary + middle, but the schools data serves ONLY elementary (middle = phantom)
    sbb = {"elementary": {"schools": [{"name": "Real ES", "low": "KG", "high": "05"}]}}
    s.execute(text("INSERT INTO district_target (district_id, lea_claimed_bands_json, "
                   "schools_by_band_json, nces_by_level_json) VALUES (:d, :c, :s, :n)"),
              {"d": did, "c": json.dumps(["elementary", "middle"]), "s": json.dumps(sbb),
               "n": json.dumps({})})
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, band, params_json, reason, status, created_at) VALUES "
                   "(:d, 'h1', 'representation', '7->6', :t, NULL, '{}', 'r', 'pending', 't1')"),
              {"d": did, "t": f"{did}:rec1"})
    R7.persist_run_session(s, _run_for(did, "hw4", accepted=[("elementary", "real es")]),
                           created_by="zz")
    s.flush()
    wd = R7.withdraw_satisfied_requests(s, did)
    assert len(wd) == 1 and "no fillable gap remains" in wd[0][1]


def test_withdraw_all_phantom_district_is_vacuously_satisfied(gov_session):
    """#240 review: when NOTHING claimed is fillable (all claimed bands phantom — detect has
    permanently suppressed the district), a record retry can never fill anything, so the
    record-scoped directive withdraws VACUOUSLY — mirroring detect's own `target_bands <= have`."""
    gdb.init_precious_schema()
    s = gov_session
    did = "ZZWDR6"
    # row PRESENT, claimed populated, but no real-school data at all -> every claimed band phantom
    s.execute(text("INSERT INTO district_target (district_id, lea_claimed_bands_json) VALUES (:d, :c)"),
              {"d": did, "c": json.dumps(["elementary", "middle"])})
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, band, params_json, reason, status, created_at) VALUES "
                   "(:d, 'h1', 'representation', '7->6', :t, NULL, '{}', 'r', 'pending', 't1')"),
              {"d": did, "t": f"{did}:rec1"})
    wd = R7.withdraw_satisfied_requests(s, did)
    assert len(wd) == 1 and "no fillable band exists" in wd[0][1]


def test_withdraw_never_fires_when_district_target_row_is_missing(gov_session):
    """#240 review: a MISSING district_target row means the target data is UNKNOWN — unknown is
    never 'satisfied', so record-scoped directives stay open (the one asymmetry vs detect)."""
    gdb.init_precious_schema()
    s = gov_session
    did = "ZZWDR7"
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                   "target, band, params_json, reason, status, created_at) VALUES "
                   "(:d, 'h1', 'representation', '7->6', :t, NULL, '{}', 'r', 'pending', 't1')"),
              {"d": did, "t": f"{did}:rec1"})
    R7.persist_run_session(s, _run_for(did, "hw7", accepted=[("high", "hs")]), created_by="zz")
    assert R7.withdraw_satisfied_requests(s, did) == []
    st = s.execute(text("SELECT status FROM extraction_request WHERE district_id=:d"), {"d": did}).scalar()
    assert st == "pending"


def test_withdraw_sees_this_rounds_facts_under_production_session_semantics():
    """#240 review (the HIGH finding): production sessions run autoflush=False (db.py), and the old
    code left this round's SchoolFact adds unflushed when detect/withdraw ran — so #233's primary
    case ('this round's facts satisfied an earlier directive') silently never fired in production
    while every test passed on an autoflush=True fixture. This test runs the REAL session config
    with NO test-side flush: persist_run_session's own flush must make the facts visible."""
    from sqlalchemy.orm import Session
    gdb.init_precious_schema()
    try:
        conn = gdb.get_engine().connect()
        conn.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    s = Session(bind=conn, autoflush=False)   # PRODUCTION parity — do not add flushes here
    try:
        did = "ZZWDR8"
        _seed_requests(s, did, ["high"])
        R7.persist_run_session(s, _run_for(did, "hw8", accepted=[("high", "hs")]), created_by="zz")
        wd = R7.withdraw_satisfied_requests(s, did)   # same txn, no flush between — the real call shape
        assert any("band 'high'" in note for _, note in wd), \
            "withdraw must see the facts persist_run_session just added in this same transaction"
    finally:
        s.rollback()
        s.close()
        conn.close()
