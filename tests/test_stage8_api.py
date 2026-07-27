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
    # DELETE (replace-on-repost) -> INSERT -> backup SELECT (quarantined under pytest) -> commit.
    # CCD-absent (roster None) skips the live-slot check — best-effort, never blocks.
    monkeypatch.setattr(SRV.SS_SAMPLING, "band_rosters_for_district", lambda d: None)
    _use(monkeypatch, _Con([_Result(), _Result(), _Result(rows=[])]))
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
    _use(monkeypatch, _Con([_Result(), _Result(), _Result(rows=[])]))
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
    _use(monkeypatch, _Con([_Result(rowcount=0)]))
    r = client.post("/api/aggregate/slot-assign/remove",
                    json={"district_id": "D1", "band": "elementary", "school": "Washington",
                          "roster_school_id": "001"})
    assert r.status_code == 404


def test_slot_assign_remove_deletes_and_backs_up(monkeypatch):
    _use(monkeypatch, _Con([_Result(rowcount=1), _Result(rows=[])]))
    r = client.post("/api/aggregate/slot-assign/remove",
                    json={"district_id": "D1", "band": "elementary", "school": "Washington",
                          "roster_school_id": "001"})
    assert r.status_code == 200 and r.json()["ok"]
