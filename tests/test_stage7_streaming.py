"""Stage 7 streaming/resumable run (REQ-117): the durability harness — process one district at a
time, persist each as it finishes, skip already-done districts on a re-run. DB + network fully
mocked (the DB writes themselves are covered by test_stage7_persist), so this tests the ORCHESTRATION:
per-district persist, resume-skip, and that skipped districts don't come back in this session's result."""
import contextlib

from infrastructure.acquisition.process_governance import stage7_run as R7
from infrastructure.acquisition.stage6_handoff import requests as R6


DOC = {
    "handoff_hash": "streamtest",
    "councils": {"lc": {"voters": ["m1", "m2"], "judge": "j1", "prompts": {"default": "stage6.extract.v1"}}},
    "districts": [
        {"district_id": "ZZS1", "name": "S1", "records": [
            {"rec_key": "ZZS1:aa", "decision": "send",
             "reps": [{"file": "x.txt", "kind": "text", "councils": ["lc"]}]}]},
        {"district_id": "ZZS2", "name": "S2", "records": [
            {"rec_key": "ZZS2:bb", "decision": "send",
             "reps": [{"file": "y.txt", "kind": "text", "councils": ["lc"]}]}]},
    ],
}


def _fake_pd(did, name, *_a, **_k):
    return {"district_id": did, "name": name, "n_reps": 1, "n_judged": 0,
            "reps": [{"rec_key": f"{did}:aa", "file": "x", "kind": "text", "council_id": "lc",
                      "judged": False, "accepted": [], "unresolved": [],
                      "calls": [{"model": "m1", "role": "voter", "ok": True, "error": None,
                                 "n_facts": 1, "facts": [], "prompt_tokens": 10,
                                 "completion_tokens": 5, "cost_usd": 0.001, "latency_ms": 100}]}],
            "accepted": [{"band": "elementary", "school": "a", "start": "08:00", "end": "14:00",
                          "gross": 360, "models": ["m1"], "method": "council_agree"}],
            "unresolved": [],
            "bands": {"elementary": {"gross_minutes": 360, "start_time": "08:00", "end_time": "14:00",
                                     "n_schools": 1, "method": "modal"}},
            "telemetry": {"calls": 1, "judge_calls": 0, "errors": 0, "prompt_tokens": 10,
                          "completion_tokens": 5, "cost_usd": 0.001}}


def _mock_env(monkeypatch, already):
    monkeypatch.setattr(R7, "_run_district", _fake_pd)
    monkeypatch.setattr(R7, "_require_key", lambda: None)
    monkeypatch.setattr(R7, "district_dirs", lambda ids: {})
    monkeypatch.setattr(R7.gdb, "init_precious_schema", lambda: None)
    monkeypatch.setattr(R7.gdb, "session_scope", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(R7, "_already_extracted", lambda hh: set(already))
    # REQ-051 governor seeds (DB SUM(cost_usd)) — stub like the other DB reads; the shipped budget.json
    # caps ($25/run) don't trip on this test's $0.001/district, so the governor is inert here.
    monkeypatch.setattr(R7, "_run_spend", lambda hh: 0.0)
    monkeypatch.setattr(R7, "_district_spend", lambda hh: {})
    monkeypatch.setattr(R7, "write_district_receipt", lambda pd, hh, **k: "/tmp/r.json")
    monkeypatch.setattr(R7.DS, "export_status", lambda s: None)
    # the request-loop detect/persist runs in the same persist txn — no-op it here (its own tests cover it)
    monkeypatch.setattr(R7, "detect_and_persist_requests", lambda s, pd, hh: 0)
    persisted = []
    monkeypatch.setattr(R7, "persist_run_session",
                        lambda s, results, **kw: persisted.append(next(iter(results["districts"]))))
    return persisted


def test_group_reps_by_district():
    by = R7._group_reps_by_district(R6.plan_requests(DOC))
    assert set(by) == {"ZZS1", "ZZS2"}
    assert len(by["ZZS1"]) == 1 and by["ZZS1"][0]["voters"] == ["m1", "m2"]


def test_streaming_persists_each_district(monkeypatch):
    persisted = _mock_env(monkeypatch, already=set())
    out = R7.run_council_streaming(DOC, persist=True, resume=True)
    # both districts persisted, in order, each on its own (durable as it finishes)
    assert persisted == ["ZZS1", "ZZS2"]
    assert set(out["districts"]) == {"ZZS1", "ZZS2"}


def test_resume_skips_already_extracted(monkeypatch):
    persisted = _mock_env(monkeypatch, already={"ZZS1"})   # S1 already done last run
    out = R7.run_council_streaming(DOC, persist=True, resume=True)
    assert persisted == ["ZZS2"]                 # only the unfinished district re-run/persisted
    assert set(out["districts"]) == {"ZZS2"}     # skipped district not re-collected this session


def test_no_resume_reruns_everything(monkeypatch):
    persisted = _mock_env(monkeypatch, already={"ZZS1"})
    R7.run_council_streaming(DOC, persist=True, resume=False)
    assert persisted == ["ZZS1", "ZZS2"]         # resume off → the skip-set is ignored


def test_no_persist_makes_no_db_calls(monkeypatch):
    persisted = _mock_env(monkeypatch, already={"ZZS1", "ZZS2"})
    out = R7.run_council_streaming(DOC, persist=False, resume=True)
    assert persisted == []                        # persist=False → nothing written, nothing skipped
    assert set(out["districts"]) == {"ZZS1", "ZZS2"}


def test_budget_run_cap_halts_before_paid_district(monkeypatch):
    """REQ-051: the run halts cleanly at the run cap — the already-spent prior run seeds the governor
    over ceiling, so NO further district is extracted (durability: nothing new persisted)."""
    persisted = _mock_env(monkeypatch, already=set())
    monkeypatch.setattr(R7, "_run_spend", lambda hh: 999.0)       # prior spend already over any cap
    out = R7.run_council_streaming(DOC, persist=True, resume=True)
    assert persisted == []                        # halted before the first paid district
    assert out["districts"] == {}


def test_budget_district_cap_skips_but_run_continues(monkeypatch):
    """REQ-051: a per-district ceiling skips the over-budget district and continues to the next."""
    persisted = _mock_env(monkeypatch, already=set())
    monkeypatch.setattr(R7, "_district_spend", lambda hh: {"ZZS1": 999.0})   # ZZS1 already over cap
    out = R7.run_council_streaming(DOC, persist=True, resume=True)
    assert persisted == ["ZZS2"]                  # ZZS1 skipped, ZZS2 still runs
    assert set(out["districts"]) == {"ZZS2"}
