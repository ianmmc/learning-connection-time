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


def test_detector_weights_endpoint_mirrors_the_ssot(client):
    """#521: /api/detector-weights serves detectors.EVENT_WEIGHTS verbatim so the frontend holds no
    weights of its own. Shape = {event: {polarity: ±1, weight: >0}}, exactly the SSOT."""
    from infrastructure.acquisition.stage5_filter import detectors as DET
    w = client.get("/api/detector-weights").json()
    assert set(w) == set(DET.EVENT_WEIGHTS)
    for ev, (pol, weight) in DET.EVENT_WEIGHTS.items():
        assert w[ev] == {"polarity": pol, "weight": weight}
    assert w["proximity_pair"]["polarity"] == 1 and w["board"]["polarity"] == -1   # both directions present


def test_relevance_density_nav_present_in_console():
    """UI-visibility regression (#521): a long rep must get relevance-density navigation — a heat-strip +
    ranked bookmarks + text anchors, driven by the SERVER weight SSOT (no hardcoded weights in JS) with
    click-to-scroll. Guards the feature (and its no-second-weight-set discipline) from silently vanishing."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    css = (repo / "infrastructure/acquisition/process_governance/static/app.css").read_text()
    assert "function renderDensityNav" in js and "if (t.length > DENSITY_MIN_CHARS) renderDensityNav" in js, \
        "a long rep must route to the density nav"
    assert "/api/detector-weights" in js and "w.polarity * w.weight" in js, \
        "weights must come from the server SSOT applied as polarity*weight — no hardcoded JS weights"
    assert 'class="dn-strip"' in js and 'class="dn-chip"' in js and 'class="bm-anchor"' in js, \
        "heat-strip, bookmark chips, and in-text anchors must render"
    assert "data-bm" in js and "strip.onclick" in js, "bookmarks + heat-strip must be click-to-scroll"
    assert ".dn-strip" in css and ".bm-anchor" in css, "the density-nav styles must exist"


def test_relevance_density_nav_is_keyboard_accessible():
    """#521 follow-up: the heat-strip is the primary click-to-jump surface; a keyboard-only reviewer must
    be able to reach and operate it too (the bookmark chips already do, via real <button> elements)."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    assert 'tabindex="0"' in js and 'role="slider"' in js, "the heat-strip must be focusable and announce its role"
    assert "strip.onkeydown" in js, "the heat-strip must respond to keyboard input, not just clicks"


def test_dn_esc_escapes_quotes():
    """Security regression: dnEsc's output fills an HTML attribute (title="...") via innerHTML — it must
    escape " (and ') or a quote in scraped document text breaks out of the attribute."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    import re
    m = re.search(r"const dnEsc = \(s\) => s\.replace\((/\[[^\]]*\]/g)", js)
    assert m, "dnEsc's escape regex must be present and easy to locate"
    charclass = m.group(1)
    assert '"' in charclass or "&quot;" in js.split("dnEsc")[0], "dnEsc must escape the double-quote character"


def test_content_adaptive_defaults_present_in_console():
    """UI-visibility regression (#522): the center pane's DEFAULT view must be the evidence the machine
    used — classification-driven open states, rasters demoted to one collapsed gallery, the source PDF as
    the default visual, and the full raw set one click away (show-all). Guards each from silently vanishing."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    css = (repo / "infrastructure/acquisition/process_governance/static/app.css").read_text()
    assert "function applyEvidenceDefaults" in js and "applyEvidenceDefaults(c, annotateUniqueTimes(" in js, \
        "the classification must DRIVE the defaults, not just decorate them"
    assert "raster-gallery" in js and "what the OCR/vision model saw" in js, \
        "per-page rasters must be demoted to one collapsed, labeled gallery (machine input, not human)"
    assert 'gal.addEventListener("toggle"' in js, "the raster gallery must fill lazily on first open"
    assert 'data-pdf-view' in js, "the source PDF (embedded viewer) must be the default visual"
    assert "show-all-reps" in js and "collapse to defaults" in js, \
        "the full raw set must stay one click away — nothing removed"
    assert 'const shotsOpen = s.visual_text_gap || d.kind === "image"' in js and "visual-rep" in js, \
        "screenshots must auto-open exactly when the record may be image-only (visual_text_gap / image kind)"
    assert "const provisional = fulls[0] || ordered[0]" in js, \
        "a provisional densest must open at render time — the pane is never all-collapsed while bodies fetch"
    assert 'c.dataset.showAll = "1"' in js and 'c.dataset.showAll === "1"' in js, \
        "a mid-load 'show all reps' click must not be silently reverted by the async classification"
    assert ".evidence-pointer" in css and ".raster-gallery" in css, "the #522 styles must exist"


def test_evidence_guardrail_pointer_present_in_console():
    """#522 guardrail regression: whenever a rep carrying evidence ends up collapsed by default, the console
    MUST surface a pointer that names it and click-opens it. Scope = the client-checkable detector surface:
    in-window clock times PLUS instructional-minutes/period phrasing (`other`) — a rep the scorer's strongest
    detector fired on must not vanish just because it has no colon-times. The check must be independent of
    the open rules (including a closed densest) so a rules change can't silently regress it."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    assert "evidence-pointer" in js and "ev-jump" in js, "the pointer strip + jump chips must exist"
    assert "evidence in collapsed rep(s)" in js, "the pointer must say what it is"
    assert "const hidden = classes.filter(" in js, \
        "the guardrail must re-derive hidden evidence from the classification, independent of the open rules"
    assert "function dnOtherEvidence" in js and "other: dnOtherEvidence(" in js, \
        "non-clock-time scorer evidence (instructional-minutes/period) must feed the classification"
    assert "k.nTimes > 0 && !densestOpen" in js, \
        "a subsumed rep's times must count as hidden evidence when the densest rep is not open (no tautology)"
    assert "CSS.escape(k.filename)" in js, \
        "filename-interpolated selectors must be CSS-escaped (an odd filename must not throw and kill the guardrail)"


def test_density_bookmarks_carry_pdf_page_and_steer_viewer():
    """#522 composition with #521: pdftotext output keeps \\f page separators, so a char-offset bookmark
    maps deterministically to a source-PDF page — chips must carry p.N and steer the embedded viewer.
    Pins the FULL steering expression: the fragment-strip (src.split("#")[0]) keeps repeated clicks
    idempotent, and steering must abstain unless exactly one PDF iframe exists (never steer the wrong doc)."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    assert 'text.indexOf("\\f")' in js and "const pageOf = (off)" in js, "the \\f page map must exist"
    assert "data-page" in js, "bookmark chips must carry the page"
    assert 'views[0].src = views[0].src.split("#")[0] + "#page=" + c.dataset.page' in js, \
        "steering must strip the old fragment (idempotent across clicks), not append to it"
    assert "views.length === 1" in js, \
        "steering must abstain when the single-PDF-per-record invariant doesn't hold"


def test_density_nav_js_constants_match_build_signals_python():
    """No-drift guard (#521): DN_PROXIMITY/DN_WIN_LO/DN_WIN_HI in app.js are hand-mirrored copies of
    build_signals.py's PROXIMITY_CHARS/WINDOW_LO/WINDOW_HI — nothing else ties them together, so pin the
    literal values here. If build_signals.py's constants change, this fails instead of the heat-strip
    silently drifting from the real proximity/window definition."""
    from pathlib import Path
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    import re
    m = re.search(r"const DN_PROXIMITY = (\d+), DN_WIN_LO = (\d+), DN_WIN_HI = (\d+)", js)
    assert m, "DN_PROXIMITY/DN_WIN_LO/DN_WIN_HI declaration must be present and in this exact shape"
    assert int(m.group(1)) == BS.PROXIMITY_CHARS
    assert (int(m.group(2)), int(m.group(3))) == (BS.WINDOW_LO, BS.WINDOW_HI)


def test_density_nav_js_regexes_match_build_signals_python():
    """No-drift guard (#521): DN_INSTRUCTIONAL/DN_PERIOD in app.js are verbatim ports of build_signals.py's
    INSTRUCTIONAL_RE/PERIOD_RE (JS can't import a Python module). Pin the pattern strings so a future edit
    to either Python regex — this one has already been revised once, per build_signals.py's own comment —
    fails loudly here instead of leaving the heat-strip silently visualizing a stale pattern."""
    from pathlib import Path
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    import re
    m_instr = re.search(r"const DN_INSTRUCTIONAL = /(.+)/gi;", js)
    m_period = re.search(r"const DN_PERIOD = /(.+)/gi;", js)
    assert m_instr and m_period, "DN_INSTRUCTIONAL/DN_PERIOD declarations must be present and in this exact shape"
    assert m_instr.group(1) == BS.INSTRUCTIONAL_RE.pattern
    assert m_period.group(1) == BS.PERIOD_RE.pattern


def test_non_regular_day_confounder_checkbox_present_in_console():
    """UI-visibility regression (#537): the ONE coarse "Non-Regular-Day Schedule" Axis-2 checkbox must
    exist, keyed `other_schedule` (continuity with the v2.0→v2.1 migration rows + harness.DETECTOR_FACET's
    lf_nonstandard_day mapping — reusing the key is what un-freezes that detector's facet denominator),
    hinted by lf_nonstandard_day, with a tooltip enumerating the class (the helper text does the scoping
    work the deliberately-coarse label can't). Guards the #537 vocabulary decision from silently vanishing
    or fragmenting back into per-cause checkboxes."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    assert '["other_schedule", "Non-Regular-Day Schedule", "lf_nonstandard_day"]' in js, \
        "the coarse other_schedule confounder checkbox must be in CONFOUNDERS, hinted by lf_nonstandard_day"
    assert "other_schedule: \"Times/schedule for something other than the regular full school day" in js, \
        "the tooltip must define the class"
    for term in ("early dismissal", "late start", "remote", "summer school", "open house"):
        assert term in js, f"the tooltip must enumerate the class members (missing: {term})"
    from infrastructure.acquisition.stage5_filter.harness import DETECTOR_FACET
    assert DETECTOR_FACET["lf_nonstandard_day"] == {"other_schedule"}, \
        "the checkbox key must stay aligned with the harness facet mapping"


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


# ----------------------------- cluster cascade facet strip (issue #64) -----------------------------
def test_cascade_facets_strips_member_page_keys():
    from infrastructure.acquisition.process_governance import server
    facets = {"schedule_table": "yes", "_where": "footer", "_pages": "4-6", "_pages_list": [4, 5, 6]}
    assert server.cascade_facets(facets) == {"schedule_table": "yes", "_where": "footer"}
    assert server.cascade_facets(None) is None
    assert server.cascade_facets({}) == {}


def test_label_cascade_strips_pages_from_members(client, monkeypatch):
    """Labeling a cluster REPRESENTATIVE cascades the label to members, but the rep-specific Axis-3
    page-range keys (_pages/_pages_list) must NOT be stamped onto every member (issue #64)."""
    import json
    from infrastructure.acquisition.process_governance import server
    # keep the endpoint's export/refresh side effects away from the real tracked backups
    monkeypatch.setattr(server.BS, "export_labels", lambda *a, **k: 0)
    monkeypatch.setattr(server, "_refresh_filtered", lambda *a, **k: None)
    rep, mem = f"{DH}:crep", f"{DH}:cmem"
    with gdb.session_scope() as con:
        con.execute(text("""INSERT INTO record (rec_key, district_id, url, tier, is_cluster_rep,
            cluster_id, cluster_size) VALUES (:rk,:d,'http://z/rep','A',1,'ZZCL',2)"""),
            {"rk": rep, "d": DH})
        con.execute(text("""INSERT INTO record (rec_key, district_id, url, tier, is_cluster_rep,
            cluster_id, cluster_size) VALUES (:rk,:d,'http://z/mem','A',0,'ZZCL',2)"""),
            {"rk": mem, "d": DH})
    facets = {"schedule_table": "yes", "_where": "handbook", "_pages": "12-14", "_pages_list": [12, 13, 14]}
    r = client.post(f"/api/label/{rep}", json={"primary_label": "school_bell_table",
                                               "facets": facets, "status": "labeled"})
    assert r.status_code == 200 and r.json()["cascaded"] == 1
    with gdb.session_scope() as con:
        rep_f = json.loads(con.execute(text("SELECT facets_json FROM label WHERE rec_key=:rk"),
                                       {"rk": rep}).scalar())
        mem_f = json.loads(con.execute(text("SELECT facets_json FROM label WHERE rec_key=:rk"),
                                       {"rk": mem}).scalar())
    assert rep_f == facets                                        # the representative keeps its pages
    assert mem_f == {"schedule_table": "yes", "_where": "handbook"}   # members get the shared answers only


# ----------------------------- #228 reset labels -----------------------------
def _no_backup_side_effects(monkeypatch):
    """Keep the endpoint's export_labels/_refresh_filtered away from the real tracked backups."""
    from infrastructure.acquisition.process_governance import server
    monkeypatch.setattr(server.BS, "export_labels", lambda *a, **k: 0)
    monkeypatch.setattr(server, "_refresh_filtered", lambda *a, **k: None)


def test_reset_record_returns_to_unlabeled(client, monkeypatch):
    """A record-scope reset nulls primary + facets + note and sets status='unlabeled'."""
    _no_backup_side_effects(monkeypatch)
    with gdb.session_scope() as con:   # give DL:r some facets+note to prove they're all cleared
        con.execute(text("UPDATE label SET facets_json='{\"schedule_table\":\"yes\"}', note='seen' WHERE rec_key=:rk"),
                    {"rk": f"{DL}:r"})
    r = client.post("/api/reset-labels", json={"scope": "record", "target_id": f"{DL}:r"})
    assert r.status_code == 200
    body = r.json()
    assert body["reset"] == 1 and body["records"] == 1 and body["district_id"] == DL and body["scope"] == "record"
    with gdb.session_scope() as con:
        row = con.execute(text("SELECT status, primary_label, facets_json, note FROM label WHERE rec_key=:rk"),
                          {"rk": f"{DL}:r"}).fetchone()
    assert tuple(row) == ("unlabeled", None, None, None)


def test_reset_keeps_the_row_never_deletes_it(client, monkeypatch):
    """Unlabeled must stay a ROW (ingest models it as the DB-default status), not an absent row —
    a DELETE would diverge from how ingest represents an unlabeled record."""
    _no_backup_side_effects(monkeypatch)
    client.post("/api/reset-labels", json={"scope": "record", "target_id": f"{DL}:r"})
    with gdb.session_scope() as con:
        assert con.execute(text("SELECT COUNT(*) FROM label WHERE rec_key=:rk"), {"rk": f"{DL}:r"}).scalar() == 1


def test_reset_already_unlabeled_reports_zero_meaningful(client, monkeypatch):
    """Resetting an already-unlabeled record is a harmless no-op: records=1 touched, reset=0 meaningful."""
    _no_backup_side_effects(monkeypatch)
    r = client.post("/api/reset-labels", json={"scope": "record", "target_id": f"{DH}:r"})   # DH:r is unlabeled
    assert r.json()["reset"] == 0 and r.json()["records"] == 1


def test_reset_district_clears_every_record(client, monkeypatch):
    _no_backup_side_effects(monkeypatch)
    with gdb.session_scope() as con:   # a second labeled record so "all" is exercised, not just one
        con.execute(text("""INSERT INTO record (rec_key, district_id, url, tier, is_cluster_rep)
            VALUES (:rk,:d,'http://z/l2','A',1)"""), {"rk": f"{DL}:r2", "d": DL})
        con.execute(text("INSERT INTO label (rec_key, status, primary_label) VALUES (:rk,'labeled','target')"),
                    {"rk": f"{DL}:r2"})
    r = client.post("/api/reset-labels", json={"scope": "district", "target_id": DL})
    body = r.json()
    assert body["scope"] == "district" and body["records"] == 2 and body["reset"] == 2
    with gdb.session_scope() as con:
        rows = con.execute(text("SELECT l.status FROM label l JOIN record r USING (rec_key) WHERE r.district_id=:d"),
                           {"d": DL}).fetchall()
    assert rows and all(s == "unlabeled" for (s,) in rows)


def test_reset_rep_reverses_the_cluster_cascade(client, monkeypatch):
    """Resetting a cluster REPRESENTATIVE reverses the forward cascade — every current member returns
    to unlabeled too (same predicate labeling used), so a mistaken label leaves no stale member ground
    truth (#228 ask)."""
    _no_backup_side_effects(monkeypatch)
    rep, mem = f"{DH}:crep", f"{DH}:cmem"
    with gdb.session_scope() as con:
        for rk, is_rep in ((rep, 1), (mem, 0)):
            con.execute(text("""INSERT INTO record (rec_key, district_id, url, tier, is_cluster_rep,
                cluster_id, cluster_size) VALUES (:rk,:d,'http://z/c','A',:rep,'ZZRESETCL',2)"""),
                {"rk": rk, "d": DH, "rep": is_rep})
    client.post(f"/api/label/{rep}", json={"primary_label": "school_bell_table",
                                           "facets": {"schedule_table": "yes"}, "status": "labeled"})
    with gdb.session_scope() as con:
        assert con.execute(text("SELECT COUNT(*) FROM label WHERE rec_key IN (:a,:b) AND status!='unlabeled'"),
                           {"a": rep, "b": mem}).scalar() == 2      # cascade applied to both
    r = client.post("/api/reset-labels", json={"scope": "record", "target_id": rep})
    assert r.json()["records"] == 2 and r.json()["reset"] == 2
    with gdb.session_scope() as con:
        rows = con.execute(text("SELECT status FROM label WHERE rec_key IN (:a,:b)"), {"a": rep, "b": mem}).fetchall()
    assert all(s == "unlabeled" for (s,) in rows)


def test_reset_unknown_record_is_404(client, monkeypatch):
    _no_backup_side_effects(monkeypatch)
    assert client.post("/api/reset-labels", json={"scope": "record", "target_id": "NOPE:x"}).status_code == 404


def test_reset_district_with_no_records_is_404(client, monkeypatch):
    _no_backup_side_effects(monkeypatch)
    assert client.post("/api/reset-labels", json={"scope": "district", "target_id": "ZZNODISTRICT"}).status_code == 404


def test_reset_bad_scope_is_400(client):
    assert client.post("/api/reset-labels", json={"scope": "bogus", "target_id": "x"}).status_code == 400


def test_reset_labels_button_present_in_console():
    """UI-visibility regression (memory: catalog must-be-visible console features + guard them). The
    reset affordance must exist at BOTH the per-record and per-district sites, wired to the endpoint —
    so it can't silently disappear in a future refactor."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent   # the test_arch_manifest.py cwd-proof convention
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    assert "dist-resetbtn" in js, "district-level Reset labels button missing"
    assert "resetLabelBtn" in js, "per-record Reset label button missing"
    assert "async function resetLabels" in js and "/api/reset-labels" in js
    assert 'resetLabels("district"' in js and 'resetLabels("record"' in js
    # PR #242 review fixes: readable confirm text (URL, not the opaque rec_key), the .active row
    # highlight survives the post-reset tree rebuild, and a district reset refreshes the open panel
    # when the open record belongs to that district (no stale pre-reset label state on screen).
    assert "(DATA && DATA.url) || CURRENT" in js, "confirm() must show the URL, not the rec_key"
    assert 'CURRENT.startsWith(target_id + ":")' in js, "district reset must refresh the open panel"
    assert 'document.querySelector(`.rec-row[data-rec-key="${reselect}"]`)' in js, \
        "post-reset reselect must re-apply the .active row highlight"


# ----------------------------- #516 FP/FN error-review lanes + rec_key search -----------------------------
def _lane_recs(body):
    return [x for g in body["groups"] for d in g["districts"] for x in d["records"]]


def test_fp_lane_is_tier_a_labeled_absent(client):
    """The FP lane (money-leak queue) = tier-A records the human labeled `target_absent` — the machine
    would auto-send but the human said absent. It FOCUSES the list to only those, excluding a tier-A
    TARGET (a real send) and an unlabeled tier-C record."""
    with gdb.session_scope() as con:
        con.execute(text("INSERT INTO record (rec_key,district_id,url,tier,is_cluster_rep) "
                         "VALUES (:rk,:d,'http://z/fp','A',1)"), {"rk": f"{DH}:fp", "d": DH})
        con.execute(text("INSERT INTO label (rec_key,status,primary_label) VALUES (:rk,'labeled','target_absent')"),
                    {"rk": f"{DH}:fp"})
    recs = _lane_recs(client.get("/api/stage5/districts", params={"lane": "fp", "limit": 3000}).json())
    keys = {x["rec_key"] for x in recs}
    assert f"{DH}:fp" in keys                                        # the FP record surfaces
    assert all(x["tier"] == "A" and x["primary_label"] == "target_absent" for x in recs)
    assert f"{DL}:r" not in keys                                     # a tier-A TARGET (not absent) is excluded


def test_fn_lane_is_the_reject_audit_sample(client):
    """The FN lane surfaces the #211 tier-D reject-audit draw — the recall instrument, not raw
    disagreement. It SEEDS its own tier-D rejects (some the fixed-seed sampler draws, some not) so the
    test has real signal on a fresh CI DB too: a bare read of pre-existing tier-D passes vacuously as
    set()==set() where the reject bucket is empty (the CI govdb container self-bootstraps empty; #534)."""
    from infrastructure.acquisition.stage5_filter import exploration_live as EAL
    from infrastructure.acquisition.stage5_filter import exploration_audit as EA
    # Deterministic split under the FIXED audit seed: candidate rec_keys the sampler DOES vs DOESN'T draw.
    cand = [f"{DH}:d{i:03d}" for i in range(200)]
    drawn_keys = set(EA.select_audit_sample(cand))
    inc = [k for k in cand if k in drawn_keys][:2]                   # must surface in the FN lane
    exc = [k for k in cand if k not in drawn_keys][:2]              # tier-D but out of the sample
    assert inc and exc, "fixed-seed sampler must draw a non-trivial subset of 200 candidates"
    with gdb.session_scope() as con:
        for rk in inc + exc:                                        # canonical tier-D rejects under an existing district
            con.execute(text("INSERT INTO record (rec_key,district_id,url,tier,is_cluster_rep) "
                             "VALUES (:rk,:d,'http://z/d','D',1)"), {"rk": rk, "d": DH})
        s = EAL.audit_sample(con)
        drawn = {r["rec_key"] for r in s["audited"]} | {r["rec_key"] for r in s["pending"]}
    recs = _lane_recs(client.get("/api/stage5/districts", params={"lane": "fn", "limit": 3000}).json())
    keys = {x["rec_key"] for x in recs}
    assert keys == drawn                                            # the lane == the audit-sample draw (the invariant)
    assert set(inc) <= keys and not (set(exc) & keys)              # ...and genuinely non-vacuous on our seeds
    assert all(x["tier"] == "D" for x in recs)


def test_rec_key_search_focuses_to_matching_records(client):
    body = client.get("/api/stage5/districts", params={"q": DL, "limit": 3000}).json()
    dids = {d["district_id"] for g in body["groups"] for d in g["districts"]}
    assert DL in dids and DH not in dids                            # only the district holding a match
    assert all(DL in x["rec_key"] for x in _lane_recs(body))


def test_rec_key_search_escapes_like_wildcards(client):
    """A literal '_'/'%' in the search matches itself, not as a LIKE wildcard (#534). The fixture rec_keys
    ('ZZFACETL:r', 'ZZFACETH:r') contain no underscore, so a search for 'ZZFACET_' must match NEITHER —
    where an UNescaped '_' would wildcard-match both (the 'L'/'H'). A wildcard-free search still works."""
    esc = client.get("/api/stage5/districts", params={"q": "ZZFACET_", "limit": 3000}).json()
    hitkeys = {x["rec_key"] for x in _lane_recs(esc)}
    assert f"{DL}:r" not in hitkeys and f"{DH}:r" not in hitkeys     # '_' is literal → no wildcard match
    ctrl = client.get("/api/stage5/districts", params={"q": "ZZFACETL", "limit": 3000}).json()
    assert any(x["rec_key"] == f"{DL}:r" for x in _lane_recs(ctrl))  # the real substring still matches


def test_lane_focus_respects_active_record_filters(client):
    """#534 review fix: a lane must not surface a district whose only lane-matching record is excluded by
    an ALSO-active facet filter — otherwise the FP queue lists empty districts and total_districts
    overcounts. Combining lane=fp (implies a LABELED record) with label=unlabeled must yield nothing."""
    with gdb.session_scope() as con:
        con.execute(text("INSERT INTO record (rec_key,district_id,url,tier,is_cluster_rep) "
                         "VALUES (:rk,:d,'http://z/fp2','A',1)"), {"rk": f"{DH}:fp2", "d": DH})
        con.execute(text("INSERT INTO label (rec_key,status,primary_label) VALUES (:rk,'labeled','target_absent')"),
                    {"rk": f"{DH}:fp2"})
    body = client.get("/api/stage5/districts", params={"lane": "fp", "limit": 3000}).json()
    dh, _ = _find(body["groups"], DH)
    assert dh is not None and any(r["rec_key"] == f"{DH}:fp2" for r in dh["records"])   # shows WITH its record
    body2 = client.get("/api/stage5/districts", params={"lane": "fp", "label": "unlabeled", "limit": 3000}).json()
    assert _find(body2["groups"], DH)[0] is None                    # focused-out, never shown with zero records
    assert body2["total_districts"] == 0                            # no record is both target_absent AND unlabeled


def test_fp_fn_lanes_and_search_present_in_console():
    """UI-visibility regression (#516): the FP/FN lane controls + rec_key search + their wiring must exist,
    and the right pane must be reordered so the Label controls precede the provenance + Signals reference."""
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    assert 'data-lane="${v}"' in js, "lane button template missing"
    assert '"fp", "FP' in js and '"fn", "FN' in js, "FP/FN lane options missing"
    assert "VIEW.lane = b.dataset.lane" in js, "lane click handler missing"
    assert 's5-search' in js and "VIEW.q = search.value" in js, "rec_key search box/handler missing"
    assert 'p.set("lane"' in js and 'p.set("q"' in js, "lane/q not threaded into the districts query"
    # right-pane reorder: Label section BEFORE provenance BEFORE the objective Signals block
    i_label = js.index(">Label <span id=\"savedFlash\"")
    i_prov = js.index("${provenanceBlock(d)}")
    i_sig = js.index(">Signals <span")
    assert i_label < i_prov < i_sig, "Label controls must precede provenance + Signals (reference below)"


# ----------------------------- progress counts (issue #51) -----------------------------
def test_progress_counts_never_report_labeled_over_total(gov_session):
    """After a shrinking re-ingest the precious `label` table keeps rows whose record vanished; the
    progress readout must JOIN labels to current records, not count the bare table (issue #51).
    Uses connection-scoped TEMP tables that shadow the real ones."""
    from infrastructure.acquisition.process_governance import server
    gov_session.execute(text("CREATE TEMP TABLE record (rec_key text PRIMARY KEY)"))
    gov_session.execute(text("CREATE TEMP TABLE label (rec_key text PRIMARY KEY, status text)"))
    gov_session.execute(text("INSERT INTO record VALUES ('d:kept')"))
    gov_session.execute(text("INSERT INTO label VALUES ('d:kept','labeled'), ('d:orphan','labeled')"))
    counts = server._progress_counts(gov_session)
    assert counts == {"total": 1, "labeled": 1}       # the orphan label doesn't inflate `labeled`
    assert counts["labeled"] <= counts["total"]


def test_density_nav_nonstandard_regex_matches_build_signals_python():
    """No-drift guard (PR #538 review): DN_NONSTANDARD in app.js is a verbatim port of
    build_signals.NONSTANDARD_TERM_RE so the heat-strip can show the wrong-day evidence that can demote
    a lone table to review (#537 follow-on). Pin the pattern strings, same as DN_INSTRUCTIONAL/DN_PERIOD."""
    from pathlib import Path
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    from infrastructure.acquisition.stage5_filter import detectors as DET
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    import re
    m = re.search(r"const DN_NONSTANDARD = /(.+)/gi;", js)
    assert m, "DN_NONSTANDARD declaration must be present and in this exact shape"
    assert m.group(1) == BS.NONSTANDARD_TERM_RE.pattern
    assert 'push(m.index, "wrong_day")' in js, "wrong-day events must feed the heat-strip"
    assert "wrong_day" in DET.EVENT_WEIGHTS and DET.EVENT_WEIGHTS["wrong_day"] == (-1, 0.70)
