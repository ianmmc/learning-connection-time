"""gate@8 console API — HTTP wiring, DB-free (fake session_scope + fake connection). The heavy logic
(closing-argument assembly, approval record) is unit-tested in test_closing_argument / test_stage8_approval,
and exercised end-to-end by the Playwright self-verify against the live DB."""
import contextlib

from fastapi.testclient import TestClient

from infrastructure.acquisition.process_governance import server as SRV
from tests.test_stage7_api import _Con, _Result, _use   # reuse the fake session harness

client = TestClient(SRV.app)


def test_aggregate_districts_queue_shape(monkeypatch):
    _use(monkeypatch, _Con([_Result(rows=[
        {"district_id": "D1", "name": "One", "state": "AL", "n_accepted": 6,
         "n_unresolved": 1, "disposition": None}])]))
    r = client.get("/api/aggregate/districts")
    assert r.status_code == 200
    row = r.json()[0]
    assert row["district_id"] == "D1" and row["n_accepted"] == 6 and row["disposition"] is None


def test_withheld_endpoint_reports_what_the_queue_holds_back(monkeypatch):
    """#660: a benchmark-provenance district never reaches the queue, so nothing in the console said
    it existed — and REQ-169's escape hatch (strike the stale rep at gate@8, band_exclusion) is only
    usable by a human who can open the district. Same row shape as the queue, plus a reason."""
    _use(monkeypatch, _Con([_Result(rows=[
        {"district_id": "D9", "name": "Benchy", "state": "AL", "n_accepted": 4,
         "n_unresolved": 0, "disposition": None}])]))
    r = client.get("/api/aggregate/withheld")
    assert r.status_code == 200
    row = r.json()[0]
    assert row["district_id"] == "D9" and row["reason"] == "benchmark provenance"
    assert row["n_accepted"] == 4                       # renderable by the same districtRow()


def test_the_queue_and_the_withheld_list_are_exact_complements():
    """They must partition the same population, or "withheld: N" is a number an operator cannot
    trust. Asserted on the SQL: identical FROM/WHERE, differing only in the negation of the shared
    provenance predicate — so a future edit to one that is not mirrored is visible here."""
    import inspect
    q = inspect.getsource(SRV.aggregate_districts)
    w = inspect.getsource(SRV.aggregate_withheld)
    assert "AND NOT {IS_BENCHMARK_PROVENANCE_SQL" in q
    assert "AND {IS_BENCHMARK_PROVENANCE_SQL" in w and "AND NOT {IS_BENCHMARK_PROVENANCE_SQL" not in w
    for clause in ("run_kind='production'", "COALESCE(cf.n_accepted, 0) > 0",
                   "EX.RQ.OPEN_STATUSES_SQL"):
        assert clause in q and clause in w, f"the two endpoints disagree on: {clause}"


def test_the_withheld_district_is_still_openable():
    """Deliberately NOT a second wall: the detail endpoint has no provenance guard, which is what
    makes the withheld list a ROUTE to the escape hatch rather than a second dead end."""
    import inspect
    detail = inspect.getsource(SRV.aggregate_district_detail)
    assert "IS_BENCHMARK_PROVENANCE_SQL" not in detail and "is_benchmark_provenance" not in detail


def test_decision_rejects_bad_disposition():
    # validation happens BEFORE any DB access — no session needed
    r = client.post("/api/aggregate/decision/D1", json={"disposition": "maybe"})
    assert r.status_code == 400


def test_decision_requires_expected_fingerprint():
    # PR #252 review: the verdict must reference the picture the reviewer actually read
    r = client.post("/api/aggregate/decision/D1", json={"disposition": "approved"})
    assert r.status_code == 400
    assert "expected_fingerprint" in r.json()["detail"]


def test_decision_409_when_facts_moved_after_review(monkeypatch):
    # PR #252 review (TOCTOU): a Stage-7 run landing between the reviewer's GET and their click must
    # refuse the verdict — the decision may only freeze the picture the human actually saw.
    _use(monkeypatch, _Con([]))
    ca = {"district_id": "D1", "bands": {"elementary": {"gross_minutes": 400, "sampling": {"coverage": 1.0},
                                                        "schools": [{"school": "a", "gross": 400}]}}}
    monkeypatch.setattr(SRV.CA8, "load_closing_argument", lambda con, did: ca)
    live_fp = SRV.CA8.fingerprint(ca)
    r = client.post("/api/aggregate/decision/D1",
                    json={"disposition": "approved", "expected_fingerprint": "stale" + live_fp})
    assert r.status_code == 409
    assert "changed after you loaded" in r.json()["detail"]


def test_override_requires_fact_id_and_reason():
    r1 = client.post("/api/aggregate/override", json={"fact_id": 7})          # no reason
    r2 = client.post("/api/aggregate/override", json={"reason": "fix it"})    # no fact_id
    assert r1.status_code == 400 and r2.status_code == 400


def test_override_fact_id_zero_is_not_missing(monkeypatch):
    # PR #252 review (falsy-zero): a present-but-falsy id must reach the lookup and 404 honestly,
    # never be misreported as a missing field.
    _use(monkeypatch, _Con([_Result(rows=[])]))   # SELECT finds no such fact
    r = client.post("/api/aggregate/override", json={"fact_id": 0, "reason": "fix it"})
    assert r.status_code == 404


def test_override_rejects_unparseable_time(monkeypatch):
    # 15c67c4 review: a "3pm" typo used to be stored verbatim and silently fail downstream — now the
    # endpoint validates the EFFECTIVE pair via the canonical gross_from_times and 400s immediately.
    _use(monkeypatch, _Con([_Result(rows=[{"start_time": "08:00", "end_time": "15:20"}])]))
    r = client.post("/api/aggregate/override",
                    json={"fact_id": 7, "end_time": "3pm", "reason": "recency"})
    assert r.status_code == 400 and "unparseable" in r.json()["detail"]


def test_override_rejects_implausible_gross(monkeypatch):
    # 15c67c4 review: the REQ-055 PLAUSIBLE gate applies to the human path too — a typo'd pair
    # yielding gross=125 is rejected at the door, not published as a modal determination.
    _use(monkeypatch, _Con([_Result(rows=[{"start_time": "08:00", "end_time": "15:20"}])]))
    r = client.post("/api/aggregate/override",
                    json={"fact_id": 7, "end_time": "10:05", "reason": "typo'd, meant 18:05"})
    assert r.status_code == 400 and "implausible" in r.json()["detail"]


def test_override_accepts_valid_single_endpoint(monkeypatch):
    # one endpoint overridden, the council's other endpoint completes the pair: 08:00-15:25 = 445, ok
    _use(monkeypatch, _Con([_Result(rows=[{"start_time": "08:00", "end_time": "15:20"}]),
                            _Result(rowcount=1)]))
    r = client.post("/api/aggregate/override",
                    json={"fact_id": 7, "end_time": "15:25", "reason": "2025-26 schedule"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_override_404_when_fact_missing(monkeypatch):
    _use(monkeypatch, _Con([_Result(rowcount=0)]))   # UPDATE affects 0 rows
    r = client.post("/api/aggregate/override",
                    json={"fact_id": 999, "reason": "wrong bell", "start_time": "08:00"})
    assert r.status_code == 404


# ---------------------------------------------------------------- #257 exclude-from-band
def test_exclude_requires_fields_and_valid_band():
    r1 = client.post("/api/aggregate/exclude", json={"district_id": "D1", "band": "elementary",
                                                     "school": "Kinston"})            # no reason
    r2 = client.post("/api/aggregate/exclude", json={"district_id": "D1", "band": "college",
                                                     "school": "Kinston", "reason": "x"})  # bad band
    r3 = client.post("/api/aggregate/exclude", json={"band": "elementary",
                                                     "school": "Kinston", "reason": "x"})   # no district
    assert r1.status_code == 400 and r2.status_code == 400 and r3.status_code == 400


def test_exclude_upserts_and_backs_up(monkeypatch):
    # DELETE (replace-on-re-exclude) -> INSERT -> backup SELECT (quarantined under pytest) -> commit
    con = _Con([_Result(), _Result(), _Result(rows=[])])
    _use(monkeypatch, con)
    r = client.post("/api/aggregate/exclude",
                    json={"district_id": "0100810", "band": "elementary",
                          "school": "Kinston School", "reason": "presents as a high school (2025-26)"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["norm_school"]        # normalized key computed server-side


def test_exclude_rejects_name_that_normalizes_to_nothing():
    r = client.post("/api/aggregate/exclude",
                    json={"district_id": "D1", "band": "elementary",
                          "school": "Schools", "reason": "x"})   # pure stopword name (#245 class)
    assert r.status_code == 400


def test_restore_404s_when_no_exclusion(monkeypatch):
    _use(monkeypatch, _Con([_Result(rowcount=0)]))
    r = client.post("/api/aggregate/exclude/restore",
                    json={"district_id": "D1", "band": "elementary", "school": "Kinston"})
    assert r.status_code == 404


def test_restore_deletes_and_backs_up(monkeypatch):
    _use(monkeypatch, _Con([_Result(rowcount=1), _Result(rows=[])]))
    r = client.post("/api/aggregate/exclude/restore",
                    json={"district_id": "D1", "band": "elementary", "school": "Kinston"})
    assert r.status_code == 200 and r.json()["ok"]


def test_stage8_console_carries_the_exclusion_ui_markers():
    """UI-visibility regression (the console-features rule): the #257 exclude-from-band affordances
    must not silently disappear from the gate@8 console. Source-presence check on the data-feat
    markers + the struck-through render class. The negative-space flag lists render through the
    shared pushFlag helper (PR #500 review round), so THOSE feats appear in source as pushFlag's
    first argument ('band-exclusions', ...) rather than an inline data-feat attribute — the grep
    asserts the call-site literal, which disappearing still means the feature disappeared."""
    from pathlib import Path
    js = (Path(SRV.__file__).parent / "static" / "stage8.js").read_text()
    for marker in ('data-feat="exclude"', 'data-feat="restore-exclusion"',
                   'data-feat="excluded-reason"', 'data-feat="excluded-row"',
                   "/api/aggregate/exclude",
                   'data-feat="human-add"', 'data-feat="human-added"',
                   'data-feat="human-add-remove"', 'data-feat="recover-band"',
                   'data-feat="recoverable-band"', "/api/aggregate/human-add",
                   "/api/aggregate/recover-band",
                   # #253: the per-row combined-scope flag + denominator provenance/criteria
                   'data-feat="combined-scope"',
                   'data-feat="denominator-provenance"', 'data-feat="denominator-criteria"',
                   # #254: the per-school year chip
                   'data-feat="school-year"',
                   # the pushFlag-rendered negative-space lists (call-site feat literals)
                   'pushFlag("band-exclusions"', 'pushFlag("name-level-mismatch"',
                   'pushFlag("combined-scope-facts"', 'pushFlag("level-override"',
                   'pushFlag("stale-roster-band"',
                   'pushFlag("superseded-facts"', 'pushFlag("year-conflicts"',
                   # #499 (REQ-144): the slot spine — the strip, its states, and the drift flags
                   'data-feat="slot-view"', 'data-feat="slot-stats"', 'data-feat="slot-filled"',
                   'data-feat="slot-unfilled"', 'data-feat="slot-ambiguous"',
                   'data-feat="slot-extra"', 'data-feat="slot-unheard"',
                   'pushFlag("slot-drift-added"', 'pushFlag("slot-drift-removed"',
                   'pushFlag("slot-drift-band-moved"',
                   # #499 REQ-145: the slot-disposition affordances + intent hint + orphan flag
                   'data-feat="slot-assign"', 'data-feat="slot-reject"',
                   'data-feat="slot-extra-confirm"', 'data-feat="slot-intent-hint"',
                   'data-feat="slot-disposition-remove"',
                   "/api/aggregate/slot-assign",
                   'pushFlag("slot-orphaned-disposition"',
                   # review round 2: per-KIND orphan copy + the displaced/duplicate extras — the
                   # old grep only pinned the pushFlag call-site, so a kind falling into the
                   # wrong message branch was invisible to the suite
                   "assign_shadowed:", "assign_fact_absent:", "still_in_district_roster",
                   'data-feat="slot-extra-displaced"', 'data-feat="slot-extra-duplicate"',
                   # #499 REQ-146: band-grain fact + projection + the conflict ladder
                   'data-feat="band-fact"', 'data-feat="slot-projected"',
                   'data-feat="conflict-rung"', 'pushFlag("slot-conflict"',
                   # #499 REQ-149: the satisfied badge
                   'data-feat="band-satisfied"'):
        assert marker in js, f"stage8.js lost the marker {marker!r}"
    css = (Path(SRV.__file__).parent / "static" / "app.css").read_text()
    assert "line-through" in css and ".s8-excluded" in css


# ---------------------------------------------------------------- #474 human-add
def test_human_add_requires_citation_and_both_times():
    base = {"district_id": "D1", "band": "elementary", "school": "Battle Hill",
            "start_time": "08:45", "end_time": "15:10", "reason": "council can't read the table"}
    r1 = client.post("/api/aggregate/human-add", json=base)                          # no source_url
    r2 = client.post("/api/aggregate/human-add", json={**base, "source_url": "https://tusd.org/x",
                                                       "end_time": ""})              # one time only
    assert r1.status_code == 400 and "source" in r1.json()["detail"].lower()
    assert r2.status_code == 400


def test_human_add_enforces_the_plausibility_gate():
    r = client.post("/api/aggregate/human-add", json={
        "district_id": "D1", "band": "elementary", "school": "Battle Hill",
        "start_time": "08:45", "end_time": "10:00",                     # gross 75 — implausible
        "source_url": "https://tusd.org/x", "reason": "r"})
    assert r.status_code == 400 and "implausible" in r.json()["detail"]


def test_human_add_refused_when_school_is_excluded(monkeypatch):
    # #257 and #474 must never fight silently: an excluded (band, school) refuses a hand-add
    _use(monkeypatch, _Con([_Result(rows=[{"reason": "reconfigured"}])]))
    r = client.post("/api/aggregate/human-add", json={
        "district_id": "D1", "band": "elementary", "school": "Kinston",
        "start_time": "08:45", "end_time": "15:10",
        "source_url": "https://x.org/doc", "reason": "r"})
    assert r.status_code == 409 and "excluded" in r.json()["detail"]


def test_human_add_upserts_and_backs_up(monkeypatch):
    # exclusion check (none) -> accepted-fact dup check (none) -> DELETE -> INSERT -> backup -> commit
    _use(monkeypatch, _Con([_Result(rows=[]), _Result(rows=[]), _Result(), _Result(),
                            _Result(rows=[])]))
    r = client.post("/api/aggregate/human-add", json={
        "district_id": "3416500", "band": "elementary", "school": "Battle Hill",
        "start_time": "08:45", "end_time": "15:10",
        "source_url": "https://tusd.org/hub.pdf", "reason": "re-extraction failed; table is an image"})
    assert r.status_code == 200 and r.json()["gross"] == 385


def test_human_add_refused_when_school_already_has_an_accepted_fact(monkeypatch):
    # Review round 2: a hand-add duplicating a still-accepted council fact would double-vote the
    # mode and silently duplicate in the projection — corrections go through the override.
    _use(monkeypatch, _Con([_Result(rows=[]),                              # no exclusion
                            _Result(rows=[{"school": "Battle Hill El Sch"}])]))  # accepted fact
    r = client.post("/api/aggregate/human-add", json={
        "district_id": "3416500", "band": "elementary", "school": "Battle Hill",
        "start_time": "08:45", "end_time": "15:10",
        "source_url": "https://tusd.org/hub.pdf", "reason": "r"})
    assert r.status_code == 409 and "override" in r.json()["detail"]


def test_human_add_remove_404s_when_absent(monkeypatch):
    _use(monkeypatch, _Con([_Result(rowcount=0)]))
    r = client.post("/api/aggregate/human-add/remove",
                    json={"district_id": "D1", "band": "elementary", "school": "Battle Hill"})
    assert r.status_code == 404


# ---------------------------------------------------------------- #473 recover-band
def test_recover_band_validates_fields():
    r = client.post("/api/aggregate/recover-band", json={"district_id": "D1", "band": "elementary"})
    assert r.status_code == 400


def test_recover_band_maps_executor_refusal(monkeypatch):
    monkeypatch.setattr(SRV.EX, "recover_band_dispatch",
                        lambda *a, **k: {"ok": False, "reason": "record X not found"})
    r = client.post("/api/aggregate/recover-band", json={
        "district_id": "D1", "band": "elementary", "rec_key": "D1:hub", "file": "camelot_hybrid.txt"})
    assert r.status_code == 400 and "not found" in r.json()["detail"]


def test_recover_band_depth_guard_is_409(monkeypatch):
    monkeypatch.setattr(SRV.EX, "recover_band_dispatch",
                        lambda *a, **k: {"ok": False, "blocked": True, "reason": "depth guard"})
    r = client.post("/api/aggregate/recover-band", json={
        "district_id": "D1", "band": "elementary", "rec_key": "D1:hub", "file": "camelot_hybrid.txt"})
    assert r.status_code == 409


def test_recover_band_success_passthrough(monkeypatch):
    monkeypatch.setattr(SRV.EX, "recover_band_dispatch",
                        lambda *a, **k: {"ok": True, "handoff_hash": "abc123", "request_id": 9,
                                         "file": "camelot_hybrid.txt", "next": "run at gate@7"})
    r = client.post("/api/aggregate/recover-band", json={
        "district_id": "3416500", "band": "elementary", "rec_key": "3416500:hub",
        "file": "camelot_hybrid.txt"})
    assert r.status_code == 200 and r.json()["handoff_hash"] == "abc123"


# ---------------------------------------------------------------- #499 REQ-145 slot dispositions
def test_slot_assign_validation():
    r1 = client.post("/api/aggregate/slot-assign", json={"district_id": "D1", "band": "elementary",
                                                         "school": "Oak", "disposition": "assign",
                                                         "reason": "x"})   # assign needs a slot id
    r2 = client.post("/api/aggregate/slot-assign", json={"district_id": "D1", "band": "elementary",
                                                         "school": "Oak", "roster_school_id": "001",
                                                         "disposition": "confirm_extra",
                                                         "reason": "x"})   # confirm_extra takes none
    r3 = client.post("/api/aggregate/slot-assign", json={"district_id": "D1", "band": "elementary",
                                                         "school": "Oak", "roster_school_id": "001",
                                                         "disposition": "maybe", "reason": "x"})
    r4 = client.post("/api/aggregate/slot-assign", json={"district_id": "D1", "band": "elementary",
                                                         "school": "Oak", "roster_school_id": "001",
                                                         "disposition": "assign"})   # no reason
    r5 = client.post("/api/aggregate/slot-assign", json={"district_id": "D1", "band": "elementary",
                                                         "school": "Schools",
                                                         "disposition": "confirm_extra",
                                                         "reason": "x"})   # degenerate name (#245)
    assert [r.status_code for r in (r1, r2, r3, r4, r5)] == [400, 400, 400, 400, 400]


def test_slot_assign_upserts_and_backs_up(monkeypatch):
    # SELECT (find replaceable rows through the CURRENT normalizer, #783) -> INSERT -> backup
    # SELECT (quarantined under pytest) -> commit. CCD-absent (roster None) skips the live-slot
    # check — best-effort, never blocks.
    monkeypatch.setattr(SRV.SS_SAMPLING, "band_rosters_for_district", lambda d: None)
    _use(monkeypatch, _Con([_Result(rows=[]), _Result(), _Result(rows=[])]))
    r = client.post("/api/aggregate/slot-assign",
                    json={"district_id": "0100810", "band": "elementary", "school": "Washington",
                          "roster_school_id": "010081000001", "disposition": "assign",
                          "reason": "district site lists it as the elementary campus"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["norm_school_fact"] == "washington" and body["disposition"] == "assign"


def test_slot_assign_rejects_a_slot_id_not_in_the_live_roster(monkeypatch):
    # Epic-#499 review round: a mistyped/stale slot_id must 400 at write time — inserted, it
    # would surface only later as an orphan, byte-identical to legitimate roster drift.
    rosters = {"elementary": {"slot_recs": [
        {"school_id": "010081000001", "name": "Washington Elementary School", "is_charter": "No",
         "gslo": "KG", "gshi": "05", "level": "Elementary", "effective_band": "elementary",
         "source": "level_clean"}]}, "_year": "2024_25"}
    monkeypatch.setattr(SRV.SS_SAMPLING, "band_rosters_for_district", lambda d: rosters)
    _use(monkeypatch, _Con([_Result(rows=[]), _Result(), _Result(rows=[])]))
    bad = client.post("/api/aggregate/slot-assign",
                      json={"district_id": "0100810", "band": "elementary", "school": "Washington",
                            "roster_school_id": "999NOTASLOT", "disposition": "assign",
                            "reason": "x"})
    assert bad.status_code == 400 and "not a live" in bad.json()["detail"]
    good = client.post("/api/aggregate/slot-assign",
                       json={"district_id": "0100810", "band": "elementary", "school": "Washington",
                             "roster_school_id": "010081000001", "disposition": "assign",
                             "reason": "x"})
    assert good.status_code == 200


def test_slot_assign_remove_404s_when_absent(monkeypatch):
    _use(monkeypatch, _Con([_Result(rows=[])]))   # SELECT finds no candidate rows -> 404
    r = client.post("/api/aggregate/slot-assign/remove",
                    json={"district_id": "D1", "band": "elementary", "school": "Washington",
                          "roster_school_id": "001"})
    assert r.status_code == 404


def test_slot_assign_remove_deletes_and_backs_up(monkeypatch):
    _use(monkeypatch, _Con([
        _Result(rows=[{"assignment_id": 7, "norm_school_fact": "washington"}]),   # SELECT
        _Result(rowcount=1),                                                       # DELETE by id
        _Result(rows=[])]))                                                        # backup
    r = client.post("/api/aggregate/slot-assign/remove",
                    json={"district_id": "D1", "band": "elementary", "school": "Washington",
                          "roster_school_id": "001"})
    assert r.status_code == 200 and r.json()["ok"]


def test_783_stale_raw_key_still_replaced_and_removable(monkeypatch):
    """#783 (review round): a row persisted under an OLDER normalizer ('lewis and clark') must
    still be found by the current key ('lewis clark') — the upsert replaces it instead of
    minting a duplicate, and the remove succeeds instead of 404ing."""
    monkeypatch.setattr(SRV.SS_SAMPLING, "band_rosters_for_district", lambda d: None)
    stale = {"assignment_id": 3, "norm_school_fact": "lewis and clark"}
    con = _Con([_Result(rows=[stale]),      # SELECT: the stale row, matched via re-norm
                _Result(rowcount=1),         # DELETE by assignment_id
                _Result(),                   # INSERT
                _Result(rows=[])])           # backup
    _use(monkeypatch, con)
    r = client.post("/api/aggregate/slot-assign",
                    json={"district_id": "D1", "band": "elementary", "school": "Lewis Clark",
                          "roster_school_id": "001", "disposition": "assign", "reason": "x"})
    assert r.status_code == 200 and r.json()["norm_school_fact"] == "lewis clark"
    _use(monkeypatch, _Con([_Result(rows=[stale]), _Result(rowcount=1), _Result(rows=[])]))
    r = client.post("/api/aggregate/slot-assign/remove",
                    json={"district_id": "D1", "band": "elementary", "school": "Lewis Clark",
                          "roster_school_id": "001"})
    assert r.status_code == 200 and r.json()["ok"]


# ===================== #682: the approve → Stage-9 write arrow =====================
# The gap this closes: the gate model documents "gate@8 (Aggregate — Stage 9 then auto-writes)", but
# the decide endpoint recorded the approval and returned. Worcester 2513230 was approved 2026-07-28
# and `district_grade_minutes` stayed EMPTY until someone remembered the CLI 25 minutes later.


class _Res9:
    """Stand-in for IncorporationResult (the endpoint reads only these fields)."""
    def __init__(self, status, reason=None, written=(), grades=0):
        self.status, self.reason, self.written, self.grades = status, reason, list(written), grades


def _approve(monkeypatch, *, result=None, raises=None, disposition="approved"):
    """Drive the real decide endpoint through to the #682 wiring, DB-free."""
    ca = {"district_id": "D1", "bands": {"elementary": {"gross_minutes": 400,
          "sampling": {"coverage": 0.9}, "schools": [{"school": "a", "gross": 400}]}}}
    monkeypatch.setattr(SRV.CA8, "load_closing_argument", lambda con, did: ca)
    monkeypatch.setattr(SRV.APV8, "record_decision", lambda *a, **k: 42)
    monkeypatch.setattr(SRV, "_backup_stage8_approvals", lambda con: 0)
    monkeypatch.setattr(SRV, "_gate8_refresh_twin_and_receipt", lambda *a, **k: None)
    monkeypatch.setattr(SRV.CAL, "record_calibration", lambda con, rec: None)
    seen = {"calls": [], "blocked": []}

    def _inc(did, **kw):
        seen["calls"].append((did, kw))
        if raises:
            raise raises
        return result or _Res9("incorporated", written=[{"grade_level": "elementary"}], grades=6)

    monkeypatch.setattr(SRV.INC9, "incorporate_district", _inc)
    monkeypatch.setattr(SRV.LEDGER9, "record_incorporation_blocked",
                        lambda con, did, **kw: seen["blocked"].append((did, kw)))
    _use(monkeypatch, _Con([_Result(rows=[{"name": "Test District", "state": "PA"}])]))
    r = client.post("/api/aggregate/decision/D1",
                    json={"disposition": disposition, "expected_fingerprint": SRV.CA8.fingerprint(ca),
                          "reason": "thin" if disposition == "sent_back" else None, "actor": "ian"})
    return r, seen


def test_approval_fires_the_stage9_write(monkeypatch):
    """MUST FAIL against pre-#682 code: the endpoint used to record the approval and return."""
    r, seen = _approve(monkeypatch)
    assert r.status_code == 200
    assert [d for d, _ in seen["calls"]] == ["D1"]
    assert seen["calls"][0][1]["actor"] == "ian"        # the gate actor, not a generic machine actor
    inc = r.json()["incorporation"]
    assert inc["status"] == "incorporated" and inc["bands"] == ["elementary"] and inc["grades"] == 6
    assert not seen["blocked"]                          # a successful write stamps nothing extra


def test_send_back_never_fires_the_write(monkeypatch):
    r, seen = _approve(monkeypatch, disposition="sent_back")
    assert r.status_code == 200 and seen["calls"] == []
    assert "incorporation" not in r.json()


def test_a_faulted_write_never_takes_the_approval_with_it(monkeypatch):
    """The approval is precious and ALREADY COMMITTED when the write runs — a fault is reported, never
    rolled back, and never turned into a 500 that would leave the operator thinking they must re-decide."""
    r, seen = _approve(monkeypatch, raises=RuntimeError("Stage 9 verify failed"))
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["approval_id"] == 42     # the decision stands
    assert body["incorporation"]["status"] == "error"
    assert "Stage 9 verify failed" in body["incorporation"]["reason"]
    assert [d for d, _ in seen["blocked"]] == ["D1"]    # and the miss is on the record


def test_a_blocked_write_makes_approved_but_unwritten_queryable(monkeypatch):
    """A guard refusal (benchmark provenance is the common one) is not an error — but it MUST leave a
    trace, or the timeline ends at 'approved' with production holding nothing (the #682 silence)."""
    r, seen = _approve(monkeypatch,
                       result=_Res9("not_eligible", reason="benchmark provenance — walled off"))
    assert r.status_code == 200 and r.json()["incorporation"]["status"] == "not_eligible"
    assert len(seen["blocked"]) == 1
    did, kw = seen["blocked"][0]
    assert did == "D1" and kw["status"] == "not_eligible"
    assert "benchmark provenance" in kw["reason"]
    assert kw["approval_id"] == 42 and kw["actor"] == "ian"


def test_a_ledger_hiccup_is_reported_not_raised(monkeypatch):
    """The blocked-stamp is the observability layer, not a THIRD place to lose the approval: if the
    stamp itself fails, the caller still gets its answer (with the hiccup named), never an exception."""
    def _boom(con, did, **kw):
        raise RuntimeError("gov_db went away")
    monkeypatch.setattr(SRV.INC9, "incorporate_district",
                        lambda did, **kw: _Res9("no_bands", reason="receipt carried no bands"))
    monkeypatch.setattr(SRV.LEDGER9, "record_incorporation_blocked", _boom)
    _use(monkeypatch, _Con([]))
    out = SRV._incorporate_after_approval("D1", actor="ian", approval_id=1, fingerprint="fp")
    assert out["status"] == "no_bands" and "gov_db went away" in out["ledger_warning"]


def test_the_endpoint_and_the_cli_share_one_entry_point():
    """The issue's explicit consistency requirement: two callers, ONE `incorporate_district`, so the
    console path and the CLI can never drift into two behaviours."""
    import inspect
    from infrastructure.acquisition.stage9_incorporate import __main__ as CLI9
    assert "INC9.incorporate_district(" in inspect.getsource(SRV._incorporate_after_approval)
    assert "incorporate_district(" in inspect.getsource(CLI9.main)


def test_the_write_runs_after_the_approval_session_commits():
    """Stage 9 re-validates the decision from the DB in its OWN session (the TOCTOU re-check), so it
    must be called with the approval committed — i.e. OUTSIDE the endpoint's `with gdb.session_scope()`."""
    import inspect
    src = inspect.getsource(SRV.aggregate_decision)
    body = src[src.index("with gdb.session_scope"):]
    with_block, _, after = body.partition("\n    out = ")
    assert "_incorporate_after_approval" not in with_block
    assert "_incorporate_after_approval" in after


def test_detail_reports_what_the_write_did(monkeypatch):
    """#682: approval and incorporation are two records — the detail view carries both, and a district
    written from facts that have since MOVED reads as written-but-not-current."""
    ca = {"district_id": "D1", "bands": {"elementary": {"gross_minutes": 400,
          "sampling": {"coverage": 0.9}, "schools": [{"school": "a", "gross": 400}]}}}
    monkeypatch.setattr(SRV.CA8, "load_closing_argument", lambda con, did: ca)
    monkeypatch.setattr(SRV.APV8, "decision_status", lambda con, did, current_fingerprint=None: {})
    fp = SRV.CA8.fingerprint(ca)
    _use(monkeypatch, _Con([]))

    for att, expect_current in (
            ({"kind": "incorporated", "fingerprint": fp}, True),
            ({"kind": "incorporated", "fingerprint": "older"}, False),
            ({"kind": "incorporation_blocked", "fingerprint": fp}, False)):
        monkeypatch.setattr(SRV.LEDGER9, "latest_attempt", lambda con, did, a=att: dict(a))
        got = client.get("/api/aggregate/district/D1").json()["incorporation"]
        assert got["current"] is expect_current, att

    monkeypatch.setattr(SRV.LEDGER9, "latest_attempt", lambda con, did: None)
    assert client.get("/api/aggregate/district/D1").json()["incorporation"] is None


def test_stage8_js_shows_the_write_beside_the_decision_682():
    """Source-pin (no JS harness): an approved district must never render as done when production
    never received it — the badge is the standing surface for that distinction."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "infrastructure/acquisition/process_governance"
          / "static/stage8.js").read_text()
    assert 'data-feat="incorporation"' in js
    assert "approved, not written" in js and "written — from earlier facts" in js
    assert "reportIncorporation(did, out.incorporation)" in js
