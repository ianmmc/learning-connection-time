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
    # PR #252 review (falsy-zero): a present-but-falsy id must reach the UPDATE and 404 honestly,
    # never be misreported as a missing field.
    _use(monkeypatch, _Con([_Result(rowcount=0)]))
    r = client.post("/api/aggregate/override", json={"fact_id": 0, "reason": "fix it"})
    assert r.status_code == 404


def test_override_404_when_fact_missing(monkeypatch):
    _use(monkeypatch, _Con([_Result(rowcount=0)]))   # UPDATE affects 0 rows
    r = client.post("/api/aggregate/override",
                    json={"fact_id": 999, "reason": "wrong bell", "start_time": "08:00"})
    assert r.status_code == 404
