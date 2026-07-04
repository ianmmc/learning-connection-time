"""Stage 7 request-more-evidence EXECUTION planning (REQ-118) — the PURE collect/guard/cap logic that
turns approved NEW-work directives into a targeted follow-up-batch plan. No DB/network; the DB glue
(compose_followup_batch) is orchestration over this. Mirrors test_stage7_requests.py's pure style."""
from infrastructure.acquisition.process_governance import stage7_execute as EX


def _req(request_id, district_id, route="7->2", band="high"):
    return {"request_id": request_id, "district_id": district_id, "route": route, "band": band}


def test_only_newwork_routes_are_swept():
    # 7->6 (existing reps, direct re-dispatch) is NOT a follow-up-batch route — it is filtered out here
    reqs = [_req(1, "D1", "7->2", "high"), _req(2, "D1", "7->6", None), _req(3, "D1", "7->3", None)]
    plan = EX.plan_followup(reqs, claimed_bands={"D1": ["elementary", "high"]})
    assert 2 not in plan["swept_ids"]                 # the 7->6 request is not swept into a batch
    assert set(plan["swept_ids"]) == {1, 3}


def test_explicit_band_targets_that_band():
    plan = EX.plan_followup([_req(1, "D1", "7->2", "high")], claimed_bands={})
    assert plan["targets"] == {"D1": ["high"]}
    assert plan["swept_ids"] == [1]


def test_bandless_request_expands_to_claimed_bands():
    # a 7->3 (URL recapture, band=None) re-targets the district's claimed bands (re-discover it)
    plan = EX.plan_followup([_req(1, "D1", "7->3", None)],
                            claimed_bands={"D1": ["elementary", "middle", "high"]})
    assert plan["targets"] == {"D1": ["elementary", "middle", "high"]}


def test_multiple_requests_one_district_union_of_bands_dedup():
    reqs = [_req(1, "D1", "7->2", "high"), _req(2, "D1", "7->2", "middle"), _req(3, "D1", "7->2", "high")]
    plan = EX.plan_followup(reqs, claimed_bands={})
    assert plan["targets"] == {"D1": ["high", "middle"]}     # order-preserved, deduped
    assert plan["swept_ids"] == [1, 2, 3]


def test_twelve_district_cap_spills_the_rest():
    reqs = [_req(i, f"D{i}", "7->2", "high") for i in range(1, 16)]   # 15 districts
    plan = EX.plan_followup(reqs, claimed_bands={}, cap=12)
    assert len(plan["targets"]) == 12
    assert [s["district_id"] for s in plan["spilled"]] == ["D13", "D14", "D15"]
    # spilled districts' requests are NOT swept — they stay 'approved' for the next compose
    assert 13 not in plan["swept_ids"] and 15 not in plan["swept_ids"]
    assert len(plan["swept_ids"]) == 12


def test_depth_guard_blocks_exhausted_district_band():
    # D1/high already fired its max rounds -> blocked; D1/middle is fresh -> kept
    reqs = [_req(1, "D1", "7->2", "high"), _req(2, "D1", "7->2", "middle")]
    plan = EX.plan_followup(reqs, claimed_bands={}, executed_rounds={("D1", "high"): 2}, max_rounds=2)
    assert plan["targets"] == {"D1": ["middle"]}
    assert plan["swept_ids"] == [2]
    assert [b["request_id"] for b in plan["blocked"]] == [1]


def test_depth_guard_none_max_never_blocks():
    reqs = [_req(1, "D1", "7->2", "high")]
    plan = EX.plan_followup(reqs, claimed_bands={}, executed_rounds={("D1", "high"): 99}, max_rounds=None)
    assert plan["swept_ids"] == [1] and plan["blocked"] == []


def test_empty_requests_is_empty_plan():
    plan = EX.plan_followup([], claimed_bands={})
    assert plan["targets"] == {} and plan["swept_ids"] == [] and plan["spilled"] == []


def test_district_order_is_first_seen_preserving_attention_sort():
    reqs = [_req(1, "DB", "7->2", "high"), _req(2, "DA", "7->2", "high"), _req(3, "DB", "7->2", "middle")]
    plan = EX.plan_followup(reqs, claimed_bands={})
    assert list(plan["targets"]) == ["DB", "DA"]   # DB first (seen first), not alphabetized


# --- DB glue (govdb): the real SQL — approved read, depth-guard rounds, and the atomic flip. The
# NCES/LCT-heavy build (build_followup_batch) + persist (persist_batch) are stubbed; this asserts the
# orchestration + that swept directives flip to 'executed' with the batch_id as executed_ref. ---
import json  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from infrastructure.acquisition.common import db as gdb  # noqa: E402
from infrastructure.acquisition.stage7_extract import models as _M7  # noqa: E402,F401 (registers table)

govdb = pytest.mark.govdb


def _seed_req(s, hh, did, route, band, status="approved"):
    s.execute(text(
        "INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, band, "
        "reason, status, created_at) VALUES (:d, :h, 'district', :r, :d, :b, 'test', :st, :ts)"),
        {"d": did, "h": hh, "r": route, "b": band, "st": status, "ts": _M7.utcnow()})


@govdb
def test_compose_flips_approved_to_executed(gov_session, monkeypatch):
    gdb.init_precious_schema()
    s = gov_session
    hh = "zzcompose"
    _seed_req(s, hh, "ZZC1", "7->2", "high")
    _seed_req(s, hh, "ZZC2", "7->2", "middle")
    _seed_req(s, hh, "ZZC3", "7->6", None)          # existing-rep route — must NOT be swept
    s.flush()

    # stub the NCES/LCT-heavy build + persist (their own tests cover them); return both target districts
    monkeypatch.setattr(EX.Q1, "build_followup_batch",
                        lambda year, bid, targets: ({"batch_id": bid, "districts":
                            [{"district_id": d} for d in targets]}, []))
    monkeypatch.setattr(EX.Q1, "persist_batch", lambda doc, reg, **k: None)
    monkeypatch.setattr(EX.DS, "load", lambda: {})

    out = EX.compose_followup_batch(handoff_hash=hh, actor="zz", session=s)
    s.flush()

    assert out["batch_id"] and out["n_districts"] == 2 and out["n_requests"] == 2
    assert set(out["targets"]) == {"ZZC1", "ZZC2"}
    statuses = dict(s.execute(text(
        "SELECT route, status FROM extraction_request WHERE handoff_hash = :h ORDER BY route"),
        {"h": hh}).all())
    assert statuses["7->2"] == "executed"           # swept
    assert statuses["7->6"] == "approved"           # left for the direct-dispatch path
    ref = s.execute(text("SELECT DISTINCT executed_ref FROM extraction_request "
                         "WHERE handoff_hash=:h AND status='executed'"), {"h": hh}).scalar()
    assert ref == out["batch_id"]


@govdb
def test_compose_nothing_approved_is_noop(gov_session, monkeypatch):
    gdb.init_precious_schema()
    s = gov_session
    _seed_req(s, "zznoop", "ZZN1", "7->2", "high", status="pending")   # not approved
    s.flush()
    monkeypatch.setattr(EX.Q1, "persist_batch", lambda *a, **k: pytest.fail("must not persist"))
    out = EX.compose_followup_batch(handoff_hash="zznoop", session=s)
    assert out["batch_id"] is None and out["n_requests"] == 0


# --- 7->6 direct alternate-rep re-dispatch ---
def test_pick_alternate_prefers_image():
    alts = [{"file": "pdftotext.txt", "kind": "text"}, {"file": "raster_p-1.png", "kind": "image"}]
    assert EX.pick_alternate(alts)["file"] == "raster_p-1.png"
    assert EX.pick_alternate([{"file": "a.txt", "kind": "text"}])["file"] == "a.txt"   # no image -> first
    assert EX.pick_alternate([]) is None


def test_build_alternate_input_synthesizes_send_and_image_override():
    meta = {"district_id": "D1", "district_dir": "dd", "name": "D", "state": "AK"}
    rec = {"rec_key": "D1:abc", "url": "http://x", "signals": {"s": 1},
           "intended_schools": ["a", "b"],
           "reps": [{"filename": "raster_p-1.png", "file_kind": "image", "n_chars": None, "n_times": None}]}
    alt = {"file": "raster_p-1.png", "kind": "image"}
    districts_input, overrides = EX.build_alternate_input(meta, rec, alt)
    (m, records), = districts_input
    assert m["district_id"] == "D1"
    assert records[0]["decision"] == "send" and records[0]["send"][0]["file"] == "raster_p-1.png"
    assert records[0]["send"][0]["n_schools"] == 2
    assert overrides == {"D1:abc::raster_p-1.png": "image"}   # image alt -> image council by default


def test_build_alternate_input_text_alt_auto_routes():
    meta = {"district_id": "D1", "district_dir": "dd"}
    rec = {"rec_key": "D1:abc", "url": "http://x", "reps": [], "intended_schools": []}
    _, overrides = EX.build_alternate_input(meta, rec, {"file": "alt.txt", "kind": "text"})
    assert overrides == {}    # a text alt with no explicit council is left to auto-routing


@govdb
def test_execute_alternate_dispatch_flips_and_records(gov_session, monkeypatch):
    gdb.init_precious_schema()
    s = gov_session
    hh = "zz76"
    # seed an approved 7->6 request naming a PNG alternate
    s.execute(text(
        "INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, band, "
        "params_json, reason, status, created_at) VALUES ('ZZ76D', :h, 'representation', '7->6', "
        "'ZZ76D:abc', NULL, :p, 'test', 'approved', :ts)"),
        {"h": hh, "p": json.dumps({"sent_file": "pdftotext.txt",
                                   "alternate_reps": [{"file": "raster_p-1.png", "kind": "image"}]}),
         "ts": _M7.utcnow()})
    s.flush()
    rid = s.execute(text("SELECT request_id FROM extraction_request WHERE handoff_hash=:h"),
                    {"h": hh}).scalar()

    # stub the release reads + the freeze/record/write internals (their own tests cover them)
    monkeypatch.setattr(EX.REL, "load_district", lambda sess, d: {"district_id": d, "district_dir": "dd",
                                                                  "name": "Z", "state": "AK"})
    monkeypatch.setattr(EX.REL, "load_district_records", lambda sess, d: [
        {"rec_key": "ZZ76D:abc", "url": "http://x", "signals": {}, "intended_schools": [],
         "reps": [{"filename": "raster_p-1.png", "file_kind": "image", "n_chars": None, "n_times": None}]}])
    monkeypatch.setattr(EX.REL, "district_fingerprints", lambda sess, d: {"config": "c", "labels": "l", "data": "x"})
    monkeypatch.setattr(EX.C6, "load_configs", lambda: {"image": {"voters": ["v1", "v2"], "judge": "j",
                                                                  "prompts": {"default": "p"}}})
    monkeypatch.setattr(EX.COST6, "load_cost_model", lambda: {"provenance": "test",
                        "assumptions": {"escalation_rate": 0.5}, "models": {}})
    monkeypatch.setattr(EX.PKG6, "assemble_package", lambda di, c, cm, ov: {
        "districts": [{"district_id": "ZZ76D"}], "cost": {"total_usd": 0.01, "n_reps": 1, "provenance": "test"},
        "generated_at": "t"})
    monkeypatch.setattr(EX.HND, "freeze", lambda pkg, c, fp, created_by: {"handoff_hash": "NEW76",
                        "created_at": "t", "created_by": created_by, "districts": pkg["districts"],
                        "cost": pkg["cost"], "councils": c})
    monkeypatch.setattr(EX.HND, "handoff_filename", lambda doc: "handoff_NEW76_t.json")
    monkeypatch.setattr(EX.HND, "write", lambda doc, root=None: None)
    monkeypatch.setattr(EX.H6, "record_dispatch", lambda sess, doc, path, actor, metas: "hid")

    out = EX.execute_alternate_dispatch(rid, actor="zz", session=s)
    s.flush()
    assert out["ok"] and out["handoff_hash"] == "NEW76"
    row = s.execute(text("SELECT status, executed_ref FROM extraction_request WHERE request_id=:r"),
                    {"r": rid}).one()
    assert row.status == "executed" and row.executed_ref == "NEW76"


@govdb
def test_execute_alternate_dispatch_depth_guard_blocks(gov_session, monkeypatch):
    gdb.init_precious_schema()
    s = gov_session
    # two prior EXECUTED 7->6 rounds for ZZ76G/None -> at the default max_request_rounds (2) -> blocked
    for _ in range(2):
        s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, "
                       "target, band, reason, status, created_at) VALUES ('ZZ76G', 'h', 'representation', "
                       "'7->6', 'ZZ76G:x', NULL, 'r', 'executed', :ts)"), {"ts": _M7.utcnow()})
    s.execute(text("INSERT INTO extraction_request (district_id, handoff_hash, altitude, route, target, "
                   "band, params_json, reason, status, created_at) VALUES ('ZZ76G', 'h2', 'representation', "
                   "'7->6', 'ZZ76G:x', NULL, :p, 'r', 'approved', :ts)"),
              {"p": json.dumps({"alternate_reps": [{"file": "a.png", "kind": "image"}]}), "ts": _M7.utcnow()})
    s.flush()
    rid = s.execute(text("SELECT request_id FROM extraction_request WHERE status='approved' "
                         "AND district_id='ZZ76G'")).scalar()
    out = EX.execute_alternate_dispatch(rid, session=s)
    assert out["ok"] is False and out.get("blocked") is True
