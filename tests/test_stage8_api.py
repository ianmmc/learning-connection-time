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
    markers + the struck-through render class."""
    from pathlib import Path
    js = (Path(SRV.__file__).parent / "static" / "stage8.js").read_text()
    for marker in ('data-feat="exclude"', 'data-feat="restore-exclusion"',
                   'data-feat="excluded-reason"', 'data-feat="excluded-row"',
                   'data-feat="band-exclusions"', "/api/aggregate/exclude"):
        assert marker in js, f"stage8.js lost the #257 marker {marker!r}"
    css = (Path(SRV.__file__).parent / "static" / "app.css").read_text()
    assert "line-through" in css and ".s8-excluded" in css
