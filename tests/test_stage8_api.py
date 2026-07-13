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


def test_override_requires_fact_id_and_reason():
    r1 = client.post("/api/aggregate/override", json={"fact_id": 7})          # no reason
    r2 = client.post("/api/aggregate/override", json={"reason": "fix it"})    # no fact_id
    assert r1.status_code == 400 and r2.status_code == 400


def test_override_404_when_fact_missing(monkeypatch):
    _use(monkeypatch, _Con([_Result(rowcount=0)]))   # UPDATE affects 0 rows
    r = client.post("/api/aggregate/override",
                    json={"fact_id": 999, "reason": "wrong bell", "start_time": "08:00"})
    assert r.status_code == 404
