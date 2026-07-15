"""gate@1 (Stage 1 Queue) console API (REQ-102) — HTTP wiring over the batch working store.

These hit the REAL governance DB (the endpoints commit), so each test seeds a SYNTHETIC batch via
batch_store and deletes it (+ its gate@1 events) in teardown. Skips if Docker is down. The heavy
`create` endpoint (full-NCES draw) is verified at the batch_00002 milestone, not here — its pieces
(build_batch / persist_batch / create_batch) are unit-tested elsewhere.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage1_queue import batch_store as BS
from infrastructure.acquisition.stage1_queue import models  # noqa: F401  (registers tables)

# #201: every test here hits the governance DB (self-bootstraps via init_precious_schema) — mark govdb so
# it runs in CI's governance-db job and is cleanly excluded from the DB-free job (was leaking as a skip).
pytestmark = pytest.mark.govdb

BID = "batch_test_api"
DISTRICTS = ("ZZTESTA", "ZZTESTB")


def _doc():
    return {
        "batch_id": BID, "created": "2026-06-27T00:00:00Z", "nces_year": "2024_25",
        "stratification": {"priority": ["enrollment"]}, "school_cap_per_band": 12,
        "districts": [
            {"district_id": "ZZTESTA", "name": "Alpha", "state": "AK", "domain": "a.org",
             "enrollment_k12": 500, "lea_claimed_bands": ["elementary"],
             "nces_school_counts": {"total": 2, "by_level": {"Elementary": 2}},
             "band_processing_order": ["elementary"],
             "schools_by_band": {"elementary": {"n_candidates": 2, "n_unclaimed_at_selection": 2, "n_selected": 2,
                "schools": [{"school_id": "A1", "name": "A Elem 1", "is_charter": "No", "level": "Elementary", "gslo": "KG", "gshi": "05"},
                            {"school_id": "A2", "name": "A Elem 2", "is_charter": "No", "level": "Elementary", "gslo": "KG", "gshi": "05"}]}}},
            {"district_id": "ZZTESTB", "name": "Beta", "state": "AL", "domain": "",
             "enrollment_k12": 100, "lea_claimed_bands": ["high"],
             "nces_school_counts": {"total": 1, "by_level": {"High": 1}},
             "band_processing_order": ["high"],
             "schools_by_band": {"high": {"n_candidates": 1, "n_unclaimed_at_selection": 1, "n_selected": 1,
                "schools": [{"school_id": "B1", "name": "B High", "is_charter": "No", "level": "High", "gslo": "09", "gshi": "12"}]}}},
        ],
    }


@pytest.fixture
def client():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.common import district_status as DS
    from infrastructure.acquisition.process_governance.server import app

    # The approve/edit endpoints call DS.save(), which regenerates the tracked district_status.json
    # backup from the DB (with our synthetic gate@1 events present at that moment). Snapshot + restore
    # it so a test run never leaves phantom test districts in a version-controlled file.
    status_file = DS.STATUS_FILE
    status_backup = status_file.read_bytes() if status_file.exists() else None

    gdb.init_precious_schema()
    with gdb.session_scope() as con:
        con.execute(text("DELETE FROM batch_school WHERE batch_id=:b"), {"b": BID})
        con.execute(text("DELETE FROM batch_district WHERE batch_id=:b"), {"b": BID})
        con.execute(text("DELETE FROM batch WHERE batch_id=:b"), {"b": BID})
        BS.create_batch(con, _doc(), actor="setup")
    try:
        yield TestClient(app)
    finally:
        with gdb.session_scope() as con:
            con.execute(text("DELETE FROM batch_school WHERE batch_id=:b"), {"b": BID})
            con.execute(text("DELETE FROM batch_district WHERE batch_id=:b"), {"b": BID})
            con.execute(text("DELETE FROM batch WHERE batch_id=:b"), {"b": BID})
            con.execute(text("DELETE FROM state_event WHERE district_id = ANY(:d)"), {"d": list(DISTRICTS)})
        if status_backup is not None:
            status_file.write_bytes(status_backup)


def test_get_returns_view(client):
    r = client.get(f"/api/queue/{BID}")
    assert r.status_code == 200
    j = r.json()
    assert j["batch_id"] == BID and j["status"] == "draft"
    assert {d["district_id"] for d in j["districts"]} == set(DISTRICTS)


def test_get_unknown_is_404(client):
    assert client.get("/api/queue/batch_does_not_exist").status_code == 404


def test_list_includes_batch(client):
    rows = client.get("/api/queue").json()
    row = next((b for b in rows if b["batch_id"] == BID), None)
    assert row and row["n_districts"] == 2 and row["status"] == "draft"


def test_edit_reject_school(client):
    r = client.post(f"/api/queue/{BID}/edit",
                    json={"op": "reject_school", "district_id": "ZZTESTA", "school_id": "A1"})
    assert r.status_code == 200
    a = next(d for d in r.json()["districts"] if d["district_id"] == "ZZTESTA")
    a1 = next(s for s in a["schools_by_band"]["elementary"]["schools"] if s["school_id"] == "A1")
    assert a1["included"] is False
    assert a["schools_by_band"]["elementary"]["n_selected"] == 1


def test_edit_add_school(client):
    r = client.post(f"/api/queue/{BID}/edit", json={
        "op": "add_school", "district_id": "ZZTESTB", "bands": ["high"],
        "school": {"school_id": "B2", "name": "B High 2", "level": "High", "gslo": "09", "gshi": "12"}})
    assert r.status_code == 200
    b = next(d for d in r.json()["districts"] if d["district_id"] == "ZZTESTB")
    b2 = next(s for s in b["schools_by_band"]["high"]["schools"] if s["school_id"] == "B2")
    assert b2["source"] == "manual_add"


def test_approve_then_edit_is_locked(client):
    assert client.post(f"/api/queue/{BID}/approve", json={"actor": "ian"}).json()["status"] == "approved"
    r = client.post(f"/api/queue/{BID}/edit",
                    json={"op": "reject_school", "district_id": "ZZTESTA", "school_id": "A1"})
    assert r.status_code == 409
    # reopen unlocks
    assert client.post(f"/api/queue/{BID}/reopen", json={"actor": "ian"}).json()["status"] == "draft"
    assert client.post(f"/api/queue/{BID}/edit",
                       json={"op": "reject_school", "district_id": "ZZTESTA", "school_id": "A1"}).status_code == 200


def test_abandon_endpoint_is_terminal(client):
    # #168: abandon a draft -> terminal; approve/reopen/edit all 409 afterward.
    j = client.post(f"/api/queue/{BID}/abandon", json={"actor": "ian", "reason": "superseded"}).json()
    assert j["status"] == "abandoned" and j["abandon_reason"] == "superseded"
    assert client.get("/api/queue").json() and next(
        b for b in client.get("/api/queue").json() if b["batch_id"] == BID)["status"] == "abandoned"
    assert client.post(f"/api/queue/{BID}/approve", json={"actor": "ian"}).status_code == 409
    assert client.post(f"/api/queue/{BID}/reopen", json={"actor": "ian"}).status_code == 409
    assert client.post(f"/api/queue/{BID}/edit",
                       json={"op": "reject_school", "district_id": "ZZTESTA", "school_id": "A1"}).status_code == 409


def test_abandon_refuses_ever_approved_via_api(client):
    # #168 review: once approved, abandon is refused even after reopen (durable first_approved_at) —
    # the reopen->abandon poison bypass is closed at the endpoint too.
    assert client.post(f"/api/queue/{BID}/approve", json={"actor": "ian"}).json()["status"] == "approved"
    assert client.post(f"/api/queue/{BID}/abandon", json={"actor": "ian"}).status_code == 409
    assert client.post(f"/api/queue/{BID}/reopen", json={"actor": "ian"}).json()["status"] == "draft"
    assert client.post(f"/api/queue/{BID}/abandon", json={"actor": "ian"}).status_code == 409   # bypass closed


def test_roster_spine_endpoint_shape(client, monkeypatch):
    """#499 REQ-150: the gate@1 roster-spine endpoint — the CLOSING ARGUMENT's slot projection
    reshaped (epic-#499 review round: never a parallel raw-facts projection), and 404 (honest
    null) when the CCD roster is unavailable. The roster is patched at closing_argument's own
    SS seam so the REAL load path (exclusions, dispositions, band facts) runs end to end."""
    from infrastructure.acquisition.process_governance import server as SRV
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    # the real load path reads the REGENERABLE district/district_target signal tables — on a
    # fresh CI database they only exist once some later test creates them (alphabetical order
    # bit us live: this file runs before the stage7 ones); idempotent CREATE IF NOT EXISTS.
    with gdb.session_scope() as con:
        BS.ensure_signal_schema(con)
        con.commit()
    rosters = {"high": {"total": 2, "by_source": {}, "schools": ["North SHS", "South SHS"],
                        "slot_recs": [
                            {"school_id": "X1", "name": "North SHS", "is_charter": "No",
                             "gslo": "09", "gshi": "12", "level": "High",
                             "effective_band": "high", "source": "level_clean"},
                            {"school_id": "X2", "name": "South SHS", "is_charter": "Yes",
                             "gslo": "09", "gshi": "12", "level": "High",
                             "effective_band": "high", "source": "level_clean"}]},
               "_year": "2024_25"}
    monkeypatch.setattr(SRV.CA8.SS, "band_rosters_for_district", lambda d: rosters)
    r = client.get(f"/api/queue/{BID}/roster/ZZTESTA")
    assert r.status_code == 200
    body = r.json()
    assert body["nces_year"] == "2024_25" and "criteria" in body
    slots = {s["school_id"]: s for s in body["bands"]["high"]["slots"]}
    assert slots["X2"]["is_charter"] == "Yes"
    assert all(s["slot_state"] in ("filled", "unfilled", "projected") for s in slots.values())

    monkeypatch.setattr(SRV.CA8.SS, "band_rosters_for_district", lambda d: None)
    assert client.get(f"/api/queue/{BID}/roster/ZZTESTA").status_code == 404


def test_roster_spine_is_the_gate8_projection_not_a_parallel_one(client, monkeypatch):
    """Epic-#499 review round (the root-cause finding): the spine endpoint must reshape
    load_closing_argument's slot_projection — the one place #257 exclusions, #474 human adds,
    REQ-145 dispositions and REQ-146 band-fact projection are applied — so gate@1 and gate@8
    can never disagree about the same district's slot states."""
    from infrastructure.acquisition.process_governance import server as SRV
    ca = {"slot_projection": {"high": {
              "slots": [{"school_id": "X1", "roster_school": "North SHS", "norm_key": "north",
                         "gslo": "09", "gshi": "12", "is_charter": "No",
                         "roster_source": "level_clean", "slot_state": "projected",
                         "match": None}],
              "extras": [],
              "stats": {"n_slots": 1, "n_filled": 0, "n_projected": 1, "n_unfilled": 0,
                        "n_extras": 0, "n_ambiguous": 0, "slot_coverage": 0.0}}},
          "provenance": {"denominator": {"nces_year": "2024_25"}}}
    seen_kw = {}

    def fake_load(con, d, **kw):
        seen_kw.update(kw)
        return ca
    monkeypatch.setattr(SRV.CA8, "load_closing_argument", fake_load)
    body = client.get(f"/api/queue/{BID}/roster/ZZTESTA").json()
    # the gate@8-only "projected" state passes straight through — proof the endpoint reads the
    # assembled projection, not a raw accepted-facts rebuild (which can't produce "projected")
    assert body["bands"]["high"]["slots"][0]["slot_state"] == "projected"
    assert body["nces_year"] == "2024_25"
    # review round 2: a GET that promises "nothing persisted" must load the PURE-read variant —
    # never committing a roster_drift state_event as a side effect of being viewed
    assert seen_kw.get("record_drift_event") is False


def test_gate1_console_carries_the_roster_spine_markers():
    """UI-visibility regression (the console-features rule) for the #499 gate@1 spine panel."""
    from pathlib import Path
    from infrastructure.acquisition.process_governance import server as SRV
    js = (Path(SRV.__file__).parent / "static" / "gate1.js").read_text()
    for marker in ("data-feat='s1-roster-spine'", 'data-feat="s1-roster-spine"'):
        if marker in js:
            break
    else:
        raise AssertionError("gate1.js lost the s1-roster-spine marker")
    for marker in ('s1-slot-unfilled', 's1-slot-selected', 's1-slot-filled',
                   "/roster/", "q-spine-criteria"):
        assert marker in js, f"gate1.js lost the marker {marker!r}"
    css = (Path(SRV.__file__).parent / "static" / "app.css").read_text()
    assert ".q-spine-unfilled" in css and ".q-spine-selected" in css
