"""gate@8 send-back routing — the 8->1/8->6 back-edges (#689).

The gap: four docstrings and the console promised these edges; a grep for consumers found only the
docstrings. Clicking Send back recorded the (correct, precious) decision and routed NOTHING —
`furthest_stage` stayed 8, no queue received the district, and the reason (which IS the routing
instruction) waited for a human to remember it. Broward `1200180` sat that way for weeks.

DB-free: fake session, and the composition machinery stubbed at its own module seams (each piece is
tested where it lives). What's asserted here is the ROUTING — the decision→artifact edge, its record,
and the refusals — plus the govdb round-trip of the linkage at the bottom.
"""
import contextlib
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import server as SRV
from infrastructure.acquisition.process_governance import stage8_sendback as SB
from tests.test_stage7_api import _Con, _Result

client = TestClient(SRV.app)

SENT_BACK = {"approval_id": 1568, "district_id": "1200180", "disposition": "sent_back",
             "actor": "ian", "reason": "the sample is thin — find the updated PDF",
             "facts_fingerprint": "fp", "created_at": "2026-07-29T05:10:12Z"}


class _RecCon(_Con):
    """A fake connection that also REMEMBERS the state_event inserts, so the linkage can be asserted
    without a DB (the insert is the whole point of the feature)."""
    def __init__(self, results=None):
        super().__init__(results or [])
        self.events = []

    def execute(self, stmt, params=None, *a, **k):
        if "pg_advisory_xact_lock" in str(stmt):    # #754: the per-district serializer — a no-op here
            return _Result()
        if params and params.get("checkpoint") == SB.ROUTED_CHECKPOINT:
            self.events.append(dict(params))
            return _Result()
        return super().execute(stmt, params, *a, **k)


def _stub_compose(monkeypatch, *, districts=1, bands=("elementary", "middle", "high")):
    """Stub the SHARED composition machinery at its own seams — this test is about routing, not about
    re-testing build_followup_batch / the draft store / the slot projection."""
    monkeypatch.setattr(SB, "_district_target_bands",
                        lambda s, dids: ({d: list(bands) for d in dids}, {}, {}))
    monkeypatch.setattr(SB, "_attempted_schools", lambda s, dids: {})
    monkeypatch.setattr(SB, "_unfilled_slots_now", lambda s, dids: {})
    monkeypatch.setattr(SB.CA8, "load_closing_argument",
                        lambda s, did, record_drift_event=False: {"district_id": did, "bands": {}})
    monkeypatch.setattr(SB.DDOM, "all_confirmed", lambda s: {})
    # #752: default the diagnosis to domain-having; scope tests override this
    monkeypatch.setattr(SB.Q1, "usable_scoping_domains",
                        lambda year, dids, dd: {d: ("example.org", "nces") for d in dids})
    monkeypatch.setattr(SB.EX7, "_defer_76_districts", lambda s, dids, maxr: set())   # #769
    monkeypatch.setattr(SB.BUD, "load_budget", lambda: type("B", (), {"max_request_rounds": 2})())
    monkeypatch.setattr(SB.BSTORE, "next_batch_number", lambda s: 43)
    monkeypatch.setattr(SB.BSTORE, "create_batch", lambda s, doc, **kw: None)
    monkeypatch.setattr(SB.Q1, "build_followup_batch",
                        lambda *a, **k: ({"districts": [{"district_id": "1200180", "schools": [1, 2]}]
                                          if districts else []}, []))


_NO_DECISION = object()   # #768: a sentinel, so SENT_BACK (a module dict) is never a default arg


def _con_for(decision=_NO_DECISION, name="Broward"):
    if decision is _NO_DECISION:
        decision = dict(SENT_BACK)   # a copy per call — a test mutating it can't leak to the next
    return _RecCon([_Result(rows=[decision] if decision else []),      # latest_decision
                    _Result(rows=[]),                                  # routing_for
                    _Result(rows=[{"name": name, "state": "FL"}])])    # district meta


# ------------------------------- the 8->1 edge -------------------------------
def test_send_back_composes_a_stage1_followup_batch(monkeypatch):
    """MUST FAIL against pre-#689 code: nothing composed either edge."""
    _stub_compose(monkeypatch)
    con = _con_for()
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, session=con)
    assert out["ok"] and out["route"] == "8->1" and out["artifact"] == "batch_00043"
    assert out["targets"] == ["elementary", "middle", "high"]
    assert out["approval_id"] == 1568


def test_the_routing_is_recorded_against_the_approval_that_caused_it(monkeypatch):
    """#689 acceptance 2: given approval_id 1568, the DB must answer "what did this send-back
    produce?" — today nothing can."""
    _stub_compose(monkeypatch)
    con = _con_for()
    SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, session=con)
    assert len(con.events) == 1
    ev = con.events[0]
    assert ev["stage"] == 8 and ev["checkpoint"] == SB.ROUTED_CHECKPOINT and ev["outcome"] == "8->1"
    assert ev["batch_id"] == "batch_00043"
    fp = json.loads(ev["fingerprints_json"])
    assert fp["approval_id"] == 1568 and fp["artifact"] == "batch_00043"
    assert "the sample is thin" in ev["note"]          # the reason rides onto the artifact's record


def test_the_send_back_reason_rides_onto_the_composed_artifact(monkeypatch):
    _stub_compose(monkeypatch)
    con = _con_for()
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, session=con)
    assert out["reason_given"] == SENT_BACK["reason"]


def test_a_dry_run_persists_nothing(monkeypatch):
    _stub_compose(monkeypatch)
    created = []
    monkeypatch.setattr(SB.BSTORE, "create_batch", lambda s, doc, **kw: created.append(doc))
    con = _con_for()
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, dry_run=True, session=con)
    assert out["ok"] and out["dry_run"] and out["artifact"] == "batch_00043"
    assert created == [] and con.events == []


def test_req149_satisfied_bands_are_spared_and_thin_bands_are_not(monkeypatch):
    """#771: the signal is REQ-149's per-band `satisfied`, never the cruder zero-facts-only
    `unsatisfied_bands`. The scenario the issue names: high is satisfied (spared), middle has ZERO
    facts (targeted), elementary holds ONE thin fact — present, so absent from unsatisfied_bands,
    but NOT REQ-149 satisfied. The send-back is about elementary; it must be targeted too, never
    eclipsed by the zero-fact sibling."""
    _stub_compose(monkeypatch)
    ca = {"district_id": "D", "bands": {
        "high": {"satisfied": {"satisfied": True}},
        "elementary": {"satisfied": {"satisfied": False}}},     # middle: zero facts, no entry
        "negative_space": {"unsatisfied_bands": ["middle"]}}
    assert SB._target_bands(_Con([]), "1200180", ca) == ["elementary", "middle"]
    # nothing satisfied (Broward's thin-evidence shape) -> the whole pool
    assert SB._target_bands(_Con([]), "1200180", {"bands": {}}) == \
        ["elementary", "middle", "high"]
    # EVERYTHING satisfied but the human still sent it back -> honor the instruction: whole pool
    ca_all = {"bands": {b: {"satisfied": {"satisfied": True}}
                        for b in ("elementary", "middle", "high")}}
    assert SB._target_bands(_Con([]), "1200180", ca_all) == ["elementary", "middle", "high"]


def test_a_present_but_empty_real_set_is_authoritative_not_a_fallback(monkeypatch):
    """#757: `real_bands_for_district` can legitimately return an EMPTY set for a PRESENT district
    (zero-school roster, crosswalk-degenerate record) — an authoritative "no real bands". The falsy
    `real.get(did) or claimed...` idiom treated it as absence and fell through to phantom claimed
    bands, contradicting the sibling compose gate's membership test."""
    monkeypatch.setattr(SB, "_district_target_bands",
                        lambda s, dids: ({d: ["elementary", "high"] for d in dids},
                                         {d: set() for d in dids}, {}))
    assert SB._target_bands(_Con([]), "D", {"bands": {}}) == []


def test_a_phantom_unsatisfied_band_never_becomes_a_target(monkeypatch):
    """`real` bands are the authority (the same definition the 7->2 compose gate uses) — an
    unsatisfied band the district does not really serve must not be re-discovered."""
    monkeypatch.setattr(SB, "_district_target_bands",
                        lambda s, dids: ({}, {d: ["elementary"] for d in dids}, {}))
    got = SB._target_bands(_Con([]), "D", {"bands": {}})
    assert got == ["elementary"]


# ------------------------------- the 8->6 edge -------------------------------
def test_the_cheap_route_seeds_a_gate6_draft(monkeypatch):
    monkeypatch.setattr(SB.DSTORE6, "create_draft", lambda s, actor: "draft_00007")
    added = []
    monkeypatch.setattr(SB.DSTORE6, "add_district",
                        lambda s, d, did, meta=None: added.append((d, did)))
    con = _con_for()
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISPATCH, session=con)
    assert out["ok"] and out["artifact"] == "draft_00007"
    assert added == [("draft_00007", "1200180")]
    assert json.loads(con.events[0]["fingerprints_json"])["route"] == "8->6"
    assert con.events[0]["batch_id"] is None        # a draft is not a batch


def test_a_domainless_district_routes_geo_not_into_the_229_wall(monkeypatch):
    """#752: the scope is a DIAGNOSIS (#719/#726), not a hardcoded "domain". A domain-less district's
    8->1 used to hit build_followup_batch's #229 refusal and dead-end — for exactly the class geo
    exists for, with the human explicitly asking for rediscovery."""
    _stub_compose(monkeypatch)
    monkeypatch.setattr(SB.Q1, "usable_scoping_domains",
                        lambda year, dids, dd: {d: ("", "") for d in dids})
    seen = {}
    monkeypatch.setattr(SB.Q1, "build_followup_batch",
                        lambda year, bid, targets, **kw: (seen.update(kw) or
                                                          ({"districts": [{"district_id": "1602100",
                                                                           "schools": [1]}]}, [])))
    out = SB.route_send_back("1602100", route=SB.ROUTE_REDISCOVER,
                             session=_con_for({**SENT_BACK, "district_id": "1602100"}))
    assert out["ok"] and out["scope"] == "geo" and seen["scope"] == "geo"

    monkeypatch.setattr(SB.Q1, "usable_scoping_domains",
                        lambda year, dids, dd: {d: ("westada.org", "discovered") for d in dids})
    out2 = SB.route_send_back("1602100", route=SB.ROUTE_REDISCOVER,
                              session=_con_for({**SENT_BACK, "district_id": "1602100"}))
    assert out2["ok"] and out2["scope"] == "domain" and seen["scope"] == "domain"


def test_the_composer_signs_the_batch_it_mints(monkeypatch):
    """#764: followup_rounds counts every approved follow-up batch toward the shared escalation
    ladder regardless of composer (deliberate — spend is spend), so the batch must DECLARE who
    composed it, or an exhausted ladder is unexplainable."""
    _stub_compose(monkeypatch)
    docs = []
    monkeypatch.setattr(SB.BSTORE, "create_batch", lambda s, doc, **kw: docs.append(doc))
    monkeypatch.setattr(SB.Q1, "build_followup_batch",
                        lambda year, bid, targets, **kw: (
                            {"districts": [{"district_id": "1200180", "schools": [1]}]}, []))
    SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, session=_con_for())
    assert docs and "8->1 send-back routing (approval 1568)" in docs[0]["composed_by"]
    assert "the sample is thin" in docs[0]["composed_by"]


def test_the_free_alternate_rep_is_surfaced_before_spending_on_discovery(monkeypatch):
    """#769: the #159 hold is SURFACED, never enforced — an 8->1 is the human's explicit choice, but
    the human deserves to see that a free, already-captured alternate rep (an open 7->6) is sitting
    unexecuted before spending on new discovery."""
    _stub_compose(monkeypatch)
    monkeypatch.setattr(SB.EX7, "_defer_76_districts", lambda s, dids, maxr: set(dids))
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, dry_run=True,
                             session=_con_for())
    assert out["ok"] and out["open_76"] is True         # surfaced, not refused


def test_the_route_takes_the_per_district_lock_before_the_already_routed_read(monkeypatch):
    """#754: the idempotency check is read-then-act over an append-only table with no unique key —
    two concurrent routes could both read prior=None and mint two artifacts. The advisory
    transaction lock serializes them; the second waits, reads the first's committed record, refuses.
    Source-ordering pin: the lock must be taken BEFORE routing_for's read, and only on real runs."""
    import inspect
    src = inspect.getsource(SB.route_send_back)
    assert "pg_advisory_xact_lock" in src
    assert src.index("pg_advisory_xact_lock") < src.index("routing_for(s, district_id")
    lock_block = src[src.index("if not dry_run:"):src.index("latest = ")]
    assert "pg_advisory_xact_lock" in lock_block        # dry-run (read-only) skips the lock


# ------------------------------- refusals -------------------------------
def test_only_a_sent_back_district_has_a_back_edge():
    con = _con_for(decision={**SENT_BACK, "disposition": "approved"})
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, session=con)
    assert not out["ok"] and "not 'sent_back'" in out["reason"]
    assert con.events == []


def test_an_undecided_district_is_refused():
    out = SB.route_send_back("D", route=SB.ROUTE_REDISCOVER, session=_con_for(decision=None))
    assert not out["ok"] and "no gate@8 decision" in out["reason"]


def test_an_unknown_route_is_refused():
    out = SB.route_send_back("D", route="8->9", session=_Con([]))
    assert not out["ok"] and "must be one of" in out["reason"]


def test_the_same_send_back_never_composes_twice(monkeypatch):
    """Idempotency at the human grain: a second click must name the artifact that already exists
    rather than mint a second draft batch for the same instruction."""
    _stub_compose(monkeypatch)
    con = _RecCon([_Result(rows=[SENT_BACK]),
                   _Result(rows=[{"outcome": "8->1", "note": "8->1 → batch_00043",
                                  "fingerprints_json": json.dumps({"approval_id": 1568,
                                                                   "artifact": "batch_00043"}),
                                  "created_at": "t"}])])
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, session=con)
    assert not out["ok"] and "already routed" in out["reason"] and "batch_00043" in out["reason"]
    assert con.events == []
    # #761: the refusal is UNIFORM — a dry-run of an already-routed send-back used to fall through
    # and return a fake fresh preview with no hint the routing already happened.
    con2 = _RecCon([_Result(rows=[SENT_BACK]),
                    _Result(rows=[{"outcome": "8->1", "note": "8->1 → batch_00043",
                                   "fingerprints_json": json.dumps({"approval_id": 1568,
                                                                    "artifact": "batch_00043"}),
                                   "created_at": "t"}])])
    dry = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, dry_run=True, session=con2)
    assert not dry["ok"] and dry["already_routed"]["artifact"] == "batch_00043"


def test_an_uncomposable_district_is_refused_honestly(monkeypatch):
    """#646's class (no usable scoping domain) must surface as the builder's own words, not as a
    silently empty batch."""
    _stub_compose(monkeypatch)
    monkeypatch.setattr(SB.Q1, "build_followup_batch", lambda *a, **k: (
        {"districts": []}, [{"district_id": "1200180", "reason": "no usable scoping domain (#229)"}]))
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, session=_con_for())
    assert not out["ok"] and "no usable scoping domain" in out["reason"]


def test_a_district_with_no_bands_is_refused_before_an_empty_batch(monkeypatch):
    _stub_compose(monkeypatch)
    monkeypatch.setattr(SB, "_district_target_bands", lambda s, dids: ({}, {}, {}))
    out = SB.route_send_back("1200180", route=SB.ROUTE_REDISCOVER, session=_con_for())
    assert not out["ok"] and "no target band" in out["reason"]


# ------------------------------- the queryable silence -------------------------------
def test_unrouted_send_backs_lists_only_the_forgotten_ones():
    """#689 acceptance 3. Keyed on approval_id, so a district sent back AGAIN after an earlier
    routing correctly reappears — the routing belongs to the instruction, not to the district."""
    approvals = [
        {"district_id": "A", "approval_id": 1, "disposition": "sent_back", "reason": "r",
         "actor": "ian", "created_at": "t"},
        {"district_id": "B", "approval_id": 2, "disposition": "sent_back", "reason": "r",
         "actor": "ian", "created_at": "t"},
        {"district_id": "C", "approval_id": 3, "disposition": "approved", "reason": None,
         "actor": "ian", "created_at": "t"}]
    con = _Con([_Result(rows=approvals),
                _Result(rows=[{"fingerprints_json": json.dumps({"approval_id": 2})}])])
    got = SB.unrouted_send_backs(con)
    assert [r["district_id"] for r in got] == ["A"]


# ------------------------------- endpoints + console -------------------------------
def _use(monkeypatch, con):
    @contextlib.contextmanager
    def _scope():
        yield con
    monkeypatch.setattr(SRV.gdb, "session_scope", _scope)


def test_route_endpoint_400s_on_a_refusal(monkeypatch):
    monkeypatch.setattr(SRV.SB8, "route_send_back",
                        lambda did, **kw: {"ok": False, "reason": "not sent back"})
    r = client.post("/api/aggregate/send-back/D1/route", json={"route": "8->1"})
    assert r.status_code == 400 and "not sent back" in r.json()["detail"]


def test_route_endpoint_passes_the_choice_through(monkeypatch):
    seen = {}
    monkeypatch.setattr(SRV.SB8, "route_send_back",
                        lambda did, **kw: (seen.update({"did": did, **kw}) or
                                           {"ok": True, "route": kw["route"], "artifact": "x"}))
    r = client.post("/api/aggregate/send-back/D1/route",
                    json={"route": "8->6", "dry_run": True, "actor": "ian"})
    assert r.status_code == 200
    assert seen["did"] == "D1" and seen["route"] == "8->6" and seen["dry_run"] is True


def test_send_backs_endpoint_reports_the_unrouted(monkeypatch):
    monkeypatch.setattr(SRV.SB8, "unrouted_send_backs", lambda con: [{"district_id": "1200180"}])
    _use(monkeypatch, _Con([]))
    r = client.get("/api/aggregate/send-backs")
    assert r.status_code == 200 and r.json()[0]["district_id"] == "1200180"


def test_stage8_js_offers_the_route_the_docstrings_promised_689():
    """Source-pin (no JS harness): a sent-back district must show WHERE it can go, and a routed one
    must show where it went — the console said "send back → 8→1" while nothing routed anywhere."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "infrastructure/acquisition/process_governance"
          / "static/stage8.js").read_text()
    assert 'data-feat="send-back-route"' in js
    assert 'data-route="8-&gt;1"' in js and 'data-route="8-&gt;6"' in js
    assert "sent back — not re-routed" in js and "re-routed" in js
    assert "dry_run: true" in js          # preview before commit


# ============================= govdb: the linkage round-trips =============================
@pytest.mark.govdb
def test_the_routing_record_round_trips_in_the_real_log(gov_session):
    """The DB-free tests assert the INSERT's parameters; this asserts the state_event actually reads
    back — the #641 lesson (a shape that is only ever asserted against a fake is a shape nobody has
    seen the DB accept)."""
    gdb.init_precious_schema()
    SB._record_routing(gov_session, "ZZSB001", route=SB.ROUTE_REDISCOVER, approval_id=99,
                       artifact="batch_09999", actor="ian", reason="thin sample", name="Z", state="ZZ")
    gov_session.flush()
    got = SB.routing_for(gov_session, "ZZSB001", 99)
    assert got["route"] == "8->1" and got["artifact"] == "batch_09999"
    assert SB.routing_for(gov_session, "ZZSB001", 100) is None      # keyed on THIS approval
    gov_session.execute(text("DELETE FROM state_event WHERE district_id = 'ZZSB001'"))
