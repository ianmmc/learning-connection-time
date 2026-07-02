"""Stage 5 faceted console API (the district-driven rework) — HTTP wiring for the left pane.

Hits the REAL governance DB: seeds two synthetic districts (a high-attention `untouched` one + a
`complete` one) + a follow-up flag + a saved view, all ZZ-prefixed, and cleans up. Skips if Docker is
down. Asserts the behaviors the left pane relies on: attention-first sort, grouping, record-level
filtering (district stays visible), the flag→attention jump, and saved-view CRUD.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage5_filter import models  # noqa: F401  (registers precious tables)
from infrastructure.acquisition.stage5_filter import build_signals as BS  # ensure_signal_schema

pytestmark = [pytest.mark.integration, pytest.mark.govdb]

DH, DL = "ZZFACETH", "ZZFACETL"   # high-attention (untouched) + low (complete) synthetic districts


def _seed(con):
    _cleanup(con)
    # high-attention untouched district: one image_only unlabeled record
    con.execute(text("""INSERT INTO district (district_id, name, state, pipeline_state, attention_score,
        attention_reasons_json, n_unlabeled, n_records, guessed_topology)
        VALUES (:d,'ZZ High','ZZ','untouched',90,'[\"image_only\"]',1,1,'unknown')"""), {"d": DH})
    con.execute(text("""INSERT INTO record (rec_key, district_id, url, tier, attention_score,
        attention_reasons_json, is_cluster_rep) VALUES (:rk,:d,'http://z/h','C',70,'[\"image_only\"]',1)"""),
        {"rk": f"{DH}:r", "d": DH})
    con.execute(text("INSERT INTO label (rec_key, status) VALUES (:rk,'unlabeled')"), {"rk": f"{DH}:r"})
    # complete (resolved) district: one labeled record, attention 0
    con.execute(text("""INSERT INTO district (district_id, name, state, pipeline_state, attention_score,
        attention_reasons_json, n_unlabeled, n_records) VALUES (:d,'ZZ Low','ZZ','complete',0,'[\"resolved\"]',0,1)"""),
        {"d": DL})
    con.execute(text("""INSERT INTO record (rec_key, district_id, url, tier, attention_score,
        attention_reasons_json, is_cluster_rep) VALUES (:rk,:d,'http://z/l','A',0,'[\"resolved\"]',1)"""),
        {"rk": f"{DL}:r", "d": DL})
    con.execute(text("INSERT INTO label (rec_key, status, primary_label) VALUES (:rk,'labeled','target')"),
                {"rk": f"{DL}:r"})


def _cleanup(con):
    for did in (DH, DL):
        con.execute(text("DELETE FROM label WHERE rec_key LIKE :p"), {"p": f"{did}:%"})
        con.execute(text("DELETE FROM record WHERE district_id=:d"), {"d": did})
        con.execute(text("DELETE FROM district WHERE district_id=:d"), {"d": did})
        con.execute(text("DELETE FROM followup_flag WHERE district_id=:d"), {"d": did})
    con.execute(text("DELETE FROM saved_view WHERE actor='zz-test'"))


@pytest.fixture
def client():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.process_governance import server
    gdb.init_precious_schema()                 # precious model tables (label/followup_flag/saved_view/…)
    with gdb.session_scope() as con:
        BS.ensure_signal_schema(con)           # district/record/… signal tables (not models) — fresh-DB safe
        _seed(con)
    try:
        yield TestClient(server.app)
    finally:
        with gdb.session_scope() as con:
            _cleanup(con)


def _find(groups, did):
    for g in groups:
        for d in g["districts"]:
            if d["district_id"] == did:
                return d, g
    return None, None


def test_attention_first_and_grouping(client):
    body = client.get("/api/stage5/districts", params={"group_by": "pipeline_state", "sort": "attention", "dir": "desc"}).json()
    dh, gh = _find(body["groups"], DH)
    dl, gl = _find(body["groups"], DL)
    assert dh and dl
    assert dh["attention_score"] == 90 and dh["attention_reasons"][0] == "image_only"
    assert dl["attention_score"] == 0
    assert gh["key"] == "untouched" and gl["key"] == "complete"     # grouped by pipeline_state
    # the high district outranks the low one in the flat order
    flat = [d["district_id"] for g in body["groups"] for d in g["districts"]]
    assert flat.index(DH) < flat.index(DL)


def test_hide_resolved_drops_complete_districts(client):
    body = client.get("/api/stage5/districts", params={"hide_resolved": "true"}).json()
    assert _find(body["groups"], DH)[0] is not None      # untouched stays
    assert _find(body["groups"], DL)[0] is None          # complete dropped


def test_record_filter_keeps_district_hides_records(client):
    """Filtering to labeled records hides the untouched district's (unlabeled) record but KEEPS the
    district visible — the user's rule: filter URLs, not districts."""
    body = client.get("/api/stage5/districts", params={"label": "labeled"}).json()
    dh, _ = _find(body["groups"], DH)
    assert dh is not None and dh["records"] == []        # district visible, its unlabeled record hidden


def test_facets_vocabulary(client):
    f = client.get("/api/stage5/facets").json()
    assert "pipeline_state" in f["group_by"] and "attention" in f["sort"]
    ps = {x["value"] for x in f["pipeline_state"]}
    assert "untouched" in ps and "complete" in ps


def test_followup_flag_jumps_attention_then_resolves(client):
    r = client.post("/api/followup", json={"scope": "district", "target_id": DL, "directive": "do X", "actor": "zz-test"})
    assert r.status_code == 200
    with gdb.session_scope() as con:
        after = con.execute(text("SELECT attention_score, n_flagged FROM district WHERE district_id=:d"), {"d": DL}).first()
    assert after[0] == 100 and after[1] == 1             # resolved district floored at manual_flag
    fid = client.get("/api/followup", params={"district_id": DL}).json()[0]["id"]
    client.post(f"/api/followup/{fid}/resolve", json={})
    with gdb.session_scope() as con:
        back = con.execute(text("SELECT attention_score FROM district WHERE district_id=:d"), {"d": DL}).scalar()
    assert back == 0                                     # back to baseline


def test_saved_view_crud(client):
    client.post("/api/views", json={"name": "zztest", "config": {"sort": "attention", "tier": ["A"]}, "actor": "zz-test"})
    views = client.get("/api/views", params={"actor": "zz-test"}).json()
    assert len(views) == 1 and views[0]["config"]["tier"] == ["A"]
    # overwrite by name
    client.post("/api/views", json={"name": "zztest", "config": {"sort": "name"}, "actor": "zz-test"})
    views = client.get("/api/views", params={"actor": "zz-test"}).json()
    assert len(views) == 1 and views[0]["config"]["sort"] == "name"
    client.delete(f"/api/views/{views[0]['id']}")
    assert client.get("/api/views", params={"actor": "zz-test"}).json() == []


def test_facets_json_column_and_roundtrip(client):
    """REQ-114: init_precious_schema adds the facets_json column (additive migration) and a label
    round-trips the V2 facet questionnaire (detector-mirroring answers + structured where/page)."""
    with gdb.session_scope() as con:
        cols = [r[0] for r in con.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='label'"))]
        assert "facets_json" in cols            # the additive migration applied
        import json
        facets = {"schedule_table": "yes", "news_feed": "no", "_where": "footer", "_pages": "4"}
        con.execute(text("UPDATE label SET facets_json=:f WHERE rec_key=:rk"),
                    {"f": json.dumps(facets), "rk": f"{DL}:r"})
        back = con.execute(text("SELECT facets_json FROM label WHERE rec_key=:rk"),
                           {"rk": f"{DL}:r"}).scalar()
        assert json.loads(back) == facets


def test_label_save_never_touches_legacy_flags_json(client):
    """Regression (fable review 2026-07-01, finding 2.1): the v2.1 UI posts no `flags`, and the old
    UPSERT wrote payload.get('flags', []) — wiping historical v2.0 flags_json on every save. The
    upsert must not reference flags_json at all: a save leaves the inert archive column untouched.
    (Exercises the real UPSERT_LABEL statement directly — the endpoint itself also exports the
    tracked labels.json backup, a side effect tests must not trigger.)"""
    import json
    from infrastructure.acquisition.process_governance.server import UPSERT_LABEL
    legacy = json.dumps(["duplicate", "building_hours_visible"])
    with gdb.session_scope() as con:
        con.execute(text("UPDATE label SET flags_json=:fj WHERE rec_key=:rk"),
                    {"fj": legacy, "rk": f"{DL}:r"})
        con.execute(UPSERT_LABEL, {
            "rec_key": f"{DL}:r", "primary_label": "school_bell_table",
            "facets_json": json.dumps({"needs_vision": "yes"}),
            "note": "", "status": "labeled", "updated_at": "2026-07-01T00:00:00Z"})
        row = con.execute(text("SELECT flags_json, primary_label, facets_json FROM label WHERE rec_key=:rk"),
                          {"rk": f"{DL}:r"}).fetchone()
        assert row[0] == legacy                       # the archive column survived the save
        assert row[1] == "school_bell_table"          # ...while the v2.1 fields were written
        assert json.loads(row[2]) == {"needs_vision": "yes"}
