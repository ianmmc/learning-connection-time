"""#518 — the capture-fidelity flag CONSUMER: the triage endpoint over capture fidelity flags,
security_block errs (#578), and Stage-4 time_blind flags, grouped per district with the
open-followup-flag context. Until this surface existed the fidelity columns were write-only."""
from pathlib import Path

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb

pytestmark = pytest.mark.govdb
STATIC = Path(__file__).parent.parent / "infrastructure/acquisition/process_governance/static"


@pytest.fixture
def client():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.process_governance.server import app
    return TestClient(app)


def test_triage_groups_classes_and_flags(client):
    from contextlib import closing
    from infrastructure.acquisition.common import cache_ingest as CI
    eng = gdb.get_engine()
    with closing(eng.connect()) as con:
        with con.begin():
            from sqlalchemy.orm import Session
            s = Session(bind=con)
            gdb.init_precious_schema()
            CI.ensure_cache_schema(s)
            # cleanup any prior test rows, then seed
            for t, c in (("capture", "district_id"), ("processed_doc", "district_id"),
                         ("followup_flag", "district_id")):
                s.execute(text(f"DELETE FROM {t} WHERE {c} LIKE 'ZZFT%'"))
            s.execute(text("INSERT INTO capture (district_id, hash, url, fidelity_json, err) VALUES "
                           "('ZZFT1', 'h1', 'https://a/login', '[\"login_wall\"]', NULL), "
                           "('ZZFT1', 'h2', 'https://a/404', '[\"soft_404\"]', NULL), "
                           "('ZZFT2', 'h3', 'https://b/x', NULL, 'security_block (probe)')"))
            s.execute(text("INSERT INTO processed_doc (district_id, hash, url, fidelity_json) "
                           "VALUES ('ZZFT1', 'h9', 'https://a/blind', '[\"time_blind\"]')"))
            s.execute(text("INSERT INTO followup_flag (scope, target_id, district_id, directive, "
                           "actor, created_at) VALUES ('district', 'ZZFT2', 'ZZFT2', 'x', 'zz', 't')"))
            s.flush()
    try:
        r = client.get("/api/fidelity-triage")
        assert r.status_code == 200
        d = r.json()
        mine = {b["district_id"]: b for b in d["districts"] if b["district_id"].startswith("ZZFT")}
        assert mine["ZZFT1"]["classes"] == {"login_wall": 1, "soft_404": 1, "time_blind": 1}
        assert mine["ZZFT1"]["open_followup_flag"] is False
        assert mine["ZZFT2"]["classes"] == {"security_block": 1}
        assert mine["ZZFT2"]["open_followup_flag"] is True       # recovery context
        assert {"login_wall", "soft_404", "time_blind", "security_block"} <= set(d["summary"])
    finally:
        with closing(eng.connect()) as con:
            with con.begin():
                for t in ("capture", "processed_doc", "followup_flag"):
                    con.execute(text(f"DELETE FROM {t} WHERE district_id LIKE 'ZZFT%'"))


def test_triage_row_listing_is_bounded(client):
    from contextlib import closing
    from infrastructure.acquisition.common import cache_ingest as CI
    eng = gdb.get_engine()
    with closing(eng.connect()) as con:
        with con.begin():
            from sqlalchemy.orm import Session
            s = Session(bind=con)
            CI.ensure_cache_schema(s)
            s.execute(text("DELETE FROM capture WHERE district_id = 'ZZFT9'"))
            for i in range(20):
                s.execute(text("INSERT INTO capture (district_id, hash, url, err) VALUES "
                               "('ZZFT9', :h, :u, 'security_block (x)')"),
                          {"h": f"h{i:02}", "u": f"https://z/{i}"})
            s.flush()
    try:
        d = client.get("/api/fidelity-triage").json()
        b = next(x for x in d["districts"] if x["district_id"] == "ZZFT9")
        assert b["n_total"] == 20 and len(b["rows"]) == 12    # bounded (the Millard-81 case)
    finally:
        with closing(eng.connect()) as con:
            with con.begin():
                con.execute(text("DELETE FROM capture WHERE district_id = 'ZZFT9'"))


def test_console_panels_are_pinned():
    js = (STATIC / "outcomes.js").read_text()
    for marker in ("fidelityTriagePanel", "fidelity-triage-panel", "/api/fidelity-triage",
                   "triage-flag", "/api/followup"):
        assert marker in js, f"outcomes.js lost the #518 triage marker {marker!r}"
    assert "fidelityTriagePanel" in (STATIC / "stage3.js").read_text()
    assert "fidelityTriagePanel" in (STATIC / "app.js").read_text()   # the gate@5 consumer mount


def test_triage_panel_flag_badges_use_the_shared_badge_system():
    """#575 review: fidelityTriagePanel used to hand-write its own <span class="badge ..."> for the
    'already flagged'/'flagged' states instead of calling the shared window.outcomeBadge() — the
    ONE place outcomes.js's own header comment says a label/tone change should propagate from."""
    js = (STATIC / "outcomes.js").read_text()
    assert 'window.outcomeBadge("already_flagged")' in js
    assert 'window.outcomeBadge("flagged")' in js
    assert '<span class="badge badge-lavender">already flagged</span>' not in js
    assert '<span class="badge badge-lavender">flagged</span>' not in js
