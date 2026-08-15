"""gate@8 re-review of a decided district that gained evidence (#713).

The gap: Fairbanks `0200600` was incorporated 2026-07-29 off a one-rep dispatch, re-dispatched after
#691 landed, gained 26 accepted facts on 08-04 — and nothing happened. No queue surfaced it, no
directive named it; there was no state in which a district says "I am written, and I have new
evidence". This suite pins the mechanism AND the measured lesson that shaped it: the trigger is real
staleness, never "new facts" (Fairbanks' 26 moved nothing — `merge_fact_runs` is earliest-run-wins).
"""
import contextlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import server as SRV
from infrastructure.acquisition.stage8_aggregate import rereview as RRV
from tests.test_stage7_api import _Con, _Result

client = TestClient(SRV.app)


def _ca(bands):
    return {"district_id": "D1",
            "bands": {b: {"gross_minutes": g, "schools": [{"school": s, "gross": g} for s in ss]}
                      for b, (g, ss) in bands.items()}}


# ------------------------------- the delta (PURE) -------------------------------
def test_an_unchanged_picture_has_no_delta():
    ca = _ca({"elementary": (390, ["a", "b"])})
    d = RRV.delta_against_decision(ca, ca)
    assert d["moved"] is False and d["bands"]["elementary"]["moved"] is False


def test_a_moved_mode_is_the_headline():
    d = RRV.delta_against_decision(_ca({"high": (390, ["a"])}), _ca({"high": (420, ["a"])}))
    assert d["moved"] is True
    b = d["bands"]["high"]
    assert b["approved_gross"] == 390 and b["live_gross"] == 420 and b["moved"]


def test_the_same_number_on_different_evidence_still_counts_as_moved():
    """A human signed off on a value AND the schools it rests on — an unchanged number over a changed
    set is exactly the thing a re-review exists to show."""
    d = RRV.delta_against_decision(_ca({"middle": (390, ["a", "b"])}),
                                   _ca({"middle": (390, ["a", "c"])}))
    b = d["bands"]["middle"]
    assert b["moved"] and b["schools_added"] == ["c"] and b["schools_removed"] == ["b"]
    assert b["n_approved_schools"] == 2 and b["n_live_schools"] == 2


def test_a_band_that_appeared_or_vanished_is_visible():
    """The Fairbanks shape: a previously unheard band gaining facts. A delta keyed only on the frozen
    receipt's bands would render it as nothing at all."""
    d = RRV.delta_against_decision(_ca({"elementary": (390, ["a"])}),
                                   _ca({"elementary": (390, ["a"]), "high": (420, ["h"])}))
    assert d["bands"]["high"]["approved_gross"] is None and d["bands"]["high"]["live_gross"] == 420
    assert d["bands"]["high"]["moved"]
    d2 = RRV.delta_against_decision(_ca({"elementary": (390, ["a"]), "high": (420, ["h"])}),
                                    _ca({"elementary": (390, ["a"])}))
    assert d2["bands"]["high"]["live_gross"] is None and d2["bands"]["high"]["moved"]


def test_bands_render_in_pipeline_order():
    d = RRV.delta_against_decision(_ca({"high": (420, ["h"]), "elementary": (390, ["a"])}),
                                   _ca({"high": (420, ["h"]), "elementary": (390, ["a"])}))
    assert list(d["bands"]) == ["elementary", "high"]


def test_an_empty_receipt_degrades_instead_of_raising():
    d = RRV.delta_against_decision({}, _ca({"elementary": (390, ["a"])}))
    assert d["moved"] and d["bands"]["elementary"]["approved_gross"] is None


# ------------------------------- the trigger -------------------------------
def _cand_con(rows):
    return _Con([_Result(rows=rows)])


def test_new_facts_alone_never_flag_a_district(monkeypatch):
    """THE measured lesson (Fairbanks, 2026-08-14): 26 accepted facts arrived after the decision and
    moved NOTHING — identical modes, identical school sets — because merge_fact_runs is
    earliest-run-wins. A queue badge derived from the pre-filter would have cried wolf on the only
    district this mechanism has ever seen."""
    con = _cand_con([{"district_id": "0200600", "approval_id": 1569, "disposition": "approved",
                      "created_at": "t", "n_new_facts": 26, "n_new_judgments": 0}])
    monkeypatch.setattr(RRV.APV, "decision_status",
                        lambda s, d, current_fingerprint=None: {"is_stale": False})
    assert RRV.candidates(con) and RRV.needs_rereview(con, ca_loader=lambda s, d: {}) == {}


def test_a_genuinely_stale_decision_is_flagged(monkeypatch):
    con = _cand_con([{"district_id": "D1", "approval_id": 7, "disposition": "approved",
                      "created_at": "t", "n_new_facts": 3, "n_new_judgments": 0}])
    monkeypatch.setattr(RRV.APV, "decision_status",
                        lambda s, d, current_fingerprint=None: {"is_stale": True})
    got = RRV.needs_rereview(con, ca_loader=lambda s, d: {})
    assert got == {"D1": {"approval_id": 7, "disposition": "approved",
                          "n_new_facts": 3, "n_new_judgments": 0}}


def test_a_district_with_nothing_new_is_never_even_checked(monkeypatch):
    """The pre-filter's whole purpose: the authoritative check costs a closing-argument assembly
    (~28 ms), and the queue answers in ~27 ms for 66 districts."""
    con = _cand_con([{"district_id": "D1", "approval_id": 7, "disposition": "approved",
                      "created_at": "t", "n_new_facts": 0, "n_new_judgments": 0}])
    loaded = []
    monkeypatch.setattr(RRV.APV, "decision_status",
                        lambda s, d, current_fingerprint=None: {"is_stale": True})
    assert RRV.needs_rereview(con, ca_loader=lambda s, d: loaded.append(d) or {}) == {}
    assert loaded == []


def test_a_human_judgment_alone_can_trigger_it(monkeypatch):
    """An override/exclusion/human-add/slot-assign moves the fingerprint with no new fact row — the
    pre-filter must cover all five sources or the superset is unsound."""
    con = _cand_con([{"district_id": "D1", "approval_id": 7, "disposition": "approved",
                      "created_at": "t", "n_new_facts": 0, "n_new_judgments": 1}])
    monkeypatch.setattr(RRV.APV, "decision_status",
                        lambda s, d, current_fingerprint=None: {"is_stale": True})
    assert "D1" in RRV.needs_rereview(con, ca_loader=lambda s, d: {})


def test_the_prefilter_covers_every_fingerprint_source():
    """Source-pin on the SQL: the fingerprint is derived from accepted production facts + the four
    human-judgment tables, so all five must appear or a moved picture can slip through unseen.
    The override is an UPDATE onto school_fact, so it is dated by its embedded stamp, not created_at."""
    sql = RRV.CHANGED_SINCE_DECISION_SQL
    for tbl in ("school_fact", "band_exclusion", "human_added_fact", "slot_assignment"):
        assert tbl in sql, tbl
    assert "human_determination" in sql and "->> 'at'" in sql
    assert "run_kind = 'production'" in sql and "status = 'accepted'" in sql


# ------------------------------- endpoints -------------------------------
def _use(monkeypatch, con):
    @contextlib.contextmanager
    def _scope():
        yield con
    monkeypatch.setattr(SRV.gdb, "session_scope", _scope)


def test_the_queue_flags_and_fronts_a_district_needing_re_review(monkeypatch):
    """MUST FAIL against pre-#713 code: decided rows sort LAST and carried no such signal, so a
    written district on moved facts was invisible unless an operator opened it by hand."""
    _use(monkeypatch, _Con([_Result(rows=[
        {"district_id": "SETTLED", "name": "S", "state": "AK", "n_accepted": 5, "n_unresolved": 0,
         "disposition": "approved"},
        {"district_id": "0200600", "name": "Fairbanks", "state": "AK", "n_accepted": 26,
         "n_unresolved": 0, "disposition": "approved"}])]))
    monkeypatch.setattr(SRV.RRV8, "needs_rereview", lambda con: {
        "0200600": {"approval_id": 1569, "disposition": "approved", "n_new_facts": 26,
                    "n_new_judgments": 0}})
    rows = client.get("/api/aggregate/districts").json()
    assert [r["district_id"] for r in rows] == ["0200600", "SETTLED"]      # fronted
    assert rows[0]["needs_rereview"] is True and rows[0]["rereview"]["n_new_facts"] == 26
    assert rows[1]["needs_rereview"] is False and rows[1]["rereview"] is None


def test_the_detail_carries_the_delta_only_when_the_decision_is_stale(monkeypatch):
    ca = _ca({"elementary": (390, ["a"])})
    monkeypatch.setattr(SRV.CA8, "load_closing_argument", lambda con, did: ca)
    monkeypatch.setattr(SRV.LEDGER9, "latest_attempt", lambda con, did: None)
    monkeypatch.setattr(SRV.APV8, "latest_decision", lambda con, did, with_receipt=False:
                        {"approval_id": 1, "disposition": "approved",
                         "receipt_json": json.dumps(_ca({"elementary": (360, ["a"])}))})
    _use(monkeypatch, _Con([]))

    monkeypatch.setattr(SRV.APV8, "decision_status", lambda con, did, current_fingerprint=None:
                        {"decided": True, "is_stale": True, "disposition": "approved",
                         "latest": {"approval_id": 1, "disposition": "approved"}})
    d = client.get("/api/aggregate/district/D1").json()["rereview_delta"]
    assert d["moved"] and d["bands"]["elementary"]["approved_gross"] == 360
    assert d["bands"]["elementary"]["live_gross"] == 390

    monkeypatch.setattr(SRV.APV8, "decision_status", lambda con, did, current_fingerprint=None:
                        {"decided": True, "is_stale": False, "disposition": "approved",
                         "latest": {"approval_id": 1, "disposition": "approved"}})
    assert client.get("/api/aggregate/district/D1").json()["rereview_delta"] is None


def test_an_unparseable_receipt_does_not_break_the_detail_view(monkeypatch):
    """The badge still says stale, honestly — a delta we cannot compute must not 500 the review."""
    monkeypatch.setattr(SRV.CA8, "load_closing_argument", lambda con, did: _ca({}))
    monkeypatch.setattr(SRV.LEDGER9, "latest_attempt", lambda con, did: None)
    monkeypatch.setattr(SRV.APV8, "decision_status", lambda con, did, current_fingerprint=None:
                        {"decided": True, "is_stale": True, "disposition": "approved",
                         "latest": {"approval_id": 1, "disposition": "approved"}})
    monkeypatch.setattr(SRV.APV8, "latest_decision", lambda con, did, with_receipt=False:
                        {"receipt_json": "{not json"})
    _use(monkeypatch, _Con([]))
    r = client.get("/api/aggregate/district/D1")
    assert r.status_code == 200 and r.json()["rereview_delta"] is None


def test_stage8_js_shows_the_delta_not_the_whole_district_713():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "infrastructure/acquisition/process_governance"
          / "static/stage8.js").read_text()
    assert 'data-feat="rereview-delta"' in js and 'data-feat="needs-rereview"' in js
    assert "Review the delta — not the whole district." in js
    assert "schools_added" in js and "schools_removed" in js


# ============================= govdb: the SQL actually runs =============================
@pytest.mark.govdb
def test_the_prefilter_runs_against_real_postgres(gov_session):
    """The pre-filter is nontrivial SQL over five tables with a JSON extraction that RAISES on the
    empty string ('' is a real value in school_fact.human_determination). A shape only ever asserted
    against a fake is a shape nobody has seen the DB accept (the #641 lesson)."""
    gdb.init_precious_schema()
    rows = gov_session.execute(text(RRV.CHANGED_SINCE_DECISION_SQL)).mappings().all()
    for r in rows:
        assert r["n_new_facts"] is not None and r["n_new_judgments"] is not None


# ===================== 2026-08-15 review round (#751/#753/#756/#760/#772) =====================
def test_a_stale_sent_back_district_is_not_flagged_for_rereview(monkeypatch):
    """#760: "re-review" is approval-specific — production may hold minutes resting on facts nobody
    signed off. A stale SENT-BACK district is the normal pending-re-decision flow (its facts moving
    is the #689 8->1 route's DESIGNED outcome), and the panel's copy ("since you approved this",
    "Stage 9 re-writes") would be false for it — rendering beside the send-back routing panel with
    the two contradicting each other."""
    con = _cand_con([{"district_id": "D1", "approval_id": 7, "disposition": "sent_back",
                      "created_at": "t", "n_new_facts": 3, "n_new_judgments": 0}])
    monkeypatch.setattr(RRV.APV, "decision_status",
                        lambda s, d, current_fingerprint=None: {"is_stale": True})
    assert RRV.needs_rereview(con, ca_loader=lambda s, d: {}) == {}


def test_detail_withholds_the_delta_from_a_stale_sent_back(monkeypatch):
    ca = _ca({"elementary": (390, ["a"])})
    monkeypatch.setattr(SRV.CA8, "load_closing_argument", lambda con, did: ca)
    monkeypatch.setattr(SRV.LEDGER9, "latest_attempt", lambda con, did: None)
    monkeypatch.setattr(SRV.SB8, "routing_for", lambda con, did, aid: None)
    monkeypatch.setattr(SRV.APV8, "decision_status", lambda con, did, current_fingerprint=None:
                        {"decided": True, "is_stale": True, "disposition": "sent_back",
                         "latest": {"approval_id": 1, "disposition": "sent_back"}})
    _use(monkeypatch, _Con([]))
    assert client.get("/api/aggregate/district/D1").json()["rereview_delta"] is None


def test_delta_identity_is_norm_school_so_a_human_add_never_phantom_swaps():
    """#753: the #474 human-add path stores the RAW typed string; the council fact for the same
    school persisted as its normalized key. Identity must be norm_school — the ONE school-identity
    function — or the delta reports one removed + one added for the SAME school."""
    frozen = _ca({"elementary": (390, ["lincoln"])})
    live = _ca({"elementary": (390, ["Lincoln Elementary School"])})
    d = RRV.delta_against_decision(frozen, live)
    b = d["bands"]["elementary"]
    assert b["schools_added"] == [] and b["schools_removed"] == [] and not b["moved"]


def test_delta_school_names_keep_their_display_casing():
    """#772: the panel renders names the way every other gate@8 surface does, never lowercased
    identity keys."""
    d = RRV.delta_against_decision(_ca({"middle": (390, ["Adams MS"])}),
                                   _ca({"middle": (390, ["Jefferson Middle School"])}))
    b = d["bands"]["middle"]
    assert b["schools_added"] == ["Jefferson Middle School"]
    assert b["schools_removed"] == ["Adams MS"]


def test_band_union_never_duplicates_a_canonical_band():
    """#756: set `-` binds tighter than `|` — the unparenthesized union re-injected fz_bands
    unfiltered. Masked today (dict reassignment), pinned so no refactor trips the landmine."""
    fz = _ca({"elementary": (390, ["a"]), "ungraded": (300, ["u"])})
    d = RRV.delta_against_decision(fz, _ca({}))
    assert list(d["bands"]) == ["elementary", "ungraded"]      # each once, canonical first


@pytest.mark.govdb
def test_a_legacy_non_json_override_value_cannot_500_the_queue(gov_session):
    """#751: school_fact.human_determination legitimately holds legacy plain-text values
    (closing_argument's _override tolerates them by design). One such row anywhere used to raise
    InvalidTextRepresentation through the whole gate@8 queue endpoint. The CASE guard (CASE
    guarantees evaluation order; a WHERE's AND does not in Postgres) makes the cast unreachable for
    a value that isn't a JSON object."""
    gdb.init_precious_schema()
    fid = gov_session.execute(text("SELECT fact_id FROM school_fact LIMIT 1")).scalar()
    if fid is None:
        pytest.skip("no school_fact rows to seed against")
    gov_session.execute(text("UPDATE school_fact SET human_determination = 'legacy plain-text note' "
                             "WHERE fact_id = :f"), {"f": fid})
    rows = gov_session.execute(text(RRV.CHANGED_SINCE_DECISION_SQL)).mappings().all()
    assert all(r["n_new_judgments"] is not None for r in rows)   # ran clean, no raise
