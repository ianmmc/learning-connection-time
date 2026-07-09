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


def _spend_seed(this_run=None, total=None):
    """Fake `_spend_by_district` (#147): one function serving both governor scopes — `handoff_hash=`
    returns this run's per-district spend (its SUM is the run seed), `district_ids=` the cumulative
    per-district total. Seeds are CONSISTENT by construction: run total = sum of the per-district
    dict, and each district's lifetime total is floored at its this-run spend (a run's rows ARE part
    of the cumulative SUM in real data) — unlike the old independent-mock trio that could set run=0
    while a district read 999."""
    this_run, total = this_run or {}, total or {}
    def _f(*, handoff_hash=None, district_ids=None):
        if district_ids is not None:
            return {d: max(total.get(d, 0.0), this_run.get(d, 0.0))
                    for d in set(total) | set(this_run)}
        return dict(this_run)
    return _f


def _mock_env(monkeypatch, already):
    monkeypatch.setattr(R7, "_run_district", _fake_pd)
    monkeypatch.setattr(R7, "_require_key", lambda: None)
    monkeypatch.setattr(R7, "district_dirs", lambda ids: {})
    monkeypatch.setattr(R7.gdb, "init_precious_schema", lambda: None)
    monkeypatch.setattr(R7.gdb, "session_scope", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(R7, "_already_extracted", lambda hh: set(already))
    # REQ-051 governor seed (DB SUM(cost_usd)) — one query now (#147); the shipped budget.json caps
    # ($25/run, $1/district, $3/district-total) don't trip on this test's $0.001/district, inert here.
    monkeypatch.setattr(R7, "_spend_by_district", _spend_seed())
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
    # prior run spend already over the $25 run cap (run seed = sum of this-run per-district spend).
    monkeypatch.setattr(R7, "_spend_by_district", _spend_seed(this_run={"ZZS1": 999.0}))
    out = R7.run_council_streaming(DOC, persist=True, resume=True)
    assert persisted == []                        # halted before the first paid district
    assert out["districts"] == {}


def test_budget_district_cap_skips_but_run_continues(monkeypatch):
    """REQ-051: a per-district (per-run) ceiling skips the over-budget district, continues to the next.
    ZZS1 at $2 clears the $1 per-district cap; the run total ($2) stays under the $25 run cap — the
    consolidated seed (#147) makes run = sum(per-district), so the value must isolate ONE cap."""
    persisted = _mock_env(monkeypatch, already=set())
    monkeypatch.setattr(R7, "_spend_by_district", _spend_seed(this_run={"ZZS1": 2.0}))
    out = R7.run_council_streaming(DOC, persist=True, resume=True)
    assert persisted == ["ZZS2"]                  # ZZS1 skipped (over $1), ZZS2 still runs (run $2 < $25)
    assert set(out["districts"]) == {"ZZS2"}


def test_budget_district_TOTAL_cap_skips_across_handoffs(monkeypatch):
    """REQ-051: the CUMULATIVE per-district cap (all handoffs) skips a district whose lifetime spend is
    over ceiling, even though THIS handoff's per-run spend is 0 — the request-loop runaway guard."""
    persisted = _mock_env(monkeypatch, already=set())
    # this run: nothing yet (run + per-run-district under cap); lifetime ZZS1 $4 > $3 total cap.
    monkeypatch.setattr(R7, "_spend_by_district", _spend_seed(total={"ZZS1": 4.0}))
    out = R7.run_council_streaming(DOC, persist=True, resume=True)
    assert persisted == ["ZZS2"]                  # ZZS1 skipped on the TOTAL cap; ZZS2 still runs
    assert set(out["districts"]) == {"ZZS2"}


def test_one_district_failure_does_not_abort_the_batch(monkeypatch):
    """#173: an unexpected failure computing ONE district is recorded and the run continues to the
    next — the original #122 symptom was a single bad rep stranding districts 16..18. The failed
    district lands in out['failed']; the healthy ones are still processed + persisted."""
    persisted = _mock_env(monkeypatch, already=set())

    def _boom_on_S1(did, name, *a, **k):
        if did == "ZZS1":
            raise FileNotFoundError("captures/…/harvest_slice.txt")   # the Marshall class of failure
        return _fake_pd(did, name)
    monkeypatch.setattr(R7, "_run_district", _boom_on_S1)

    out = R7.run_council_streaming(DOC, persist=True, resume=True)
    assert persisted == ["ZZS2"]                       # the healthy district still ran + persisted
    assert set(out["districts"]) == {"ZZS2"}
    assert [f["district_id"] for f in out["failed"]] == ["ZZS1"]
    assert "FileNotFoundError" in out["failed"][0]["error"]


def test_billing_auth_error_halts_the_whole_run(monkeypatch):
    """#173: BillingAuthError is the ONE per-district exception that must NOT be swallowed — every
    later paid call fails identically (bad key / exhausted balance), so the run halts, not skips."""
    import pytest
    _mock_env(monkeypatch, already=set())

    def _billing(did, name, *a, **k):
        raise R7.OR.BillingAuthError(f"{did}: HTTP 402 — insufficient balance")
    monkeypatch.setattr(R7, "_run_district", _billing)

    with pytest.raises(R7.OR.BillingAuthError):
        R7.run_council_streaming(DOC, persist=True, resume=True)


def test_run_district_isolates_one_unreadable_rep(monkeypatch):
    """#173 (the deeper half): a single unreadable rep must not lose the DISTRICT — it's recorded as a
    failed rep (no calls, carries the error, counted in telemetry) while the district's OTHER reps
    still extract. This is exactly the Marshall harvest_slice case: one bad rep of several."""
    def _resolve(ddir, rec_key, file, kind):
        if file == "bad.txt":
            raise FileNotFoundError(f"captures/…/{file}")
        return "GOOD CONTENT"
    monkeypatch.setattr(R7, "resolve_content", _resolve)
    monkeypatch.setattr(R7, "_call", lambda m, p, k, c: R7.OR.CallResult(model=m, ok=True, content="[]"))
    monkeypatch.setattr(R7.PARSE, "parse_schedules", lambda content: [{"school": "x"}])
    monkeypatch.setattr(R7.AGG, "consensus_school_facts", lambda rows, judge=None: (
        [{"band": "high", "school": "x", "start": "08:00", "end": "14:00",
          "gross": 360, "method": "council_agree", "models": ["m1", "m2"]}], []))
    monkeypatch.setattr(R7.AGG, "district_bands_from_facts", lambda facts: {})

    groups = [
        {"rec_key": "D:aa", "file": "bad.txt", "kind": "text", "council_id": "lc",
         "voters": ["m1", "m2"], "prompt_ids": {"m1": "p", "m2": "p"}},
        {"rec_key": "D:bb", "file": "good.txt", "kind": "text", "council_id": "lc",
         "voters": ["m1", "m2"], "prompt_ids": {"m1": "p", "m2": "p"}},
    ]
    councils = {"lc": {"voters": ["m1", "m2"], "prompts": {"default": "p"}}}   # no judge → no judge path

    pd = R7._run_district("D", "Dville", groups, councils, None, use_judge=True)

    assert pd["n_reps"] == 2                                   # both reps attempted
    bad = next(r for r in pd["reps"] if r["file"] == "bad.txt")
    assert bad["calls"] == [] and "FileNotFoundError" in bad["error"] and bad["accepted"] == []
    good = next(r for r in pd["reps"] if r["file"] == "good.txt")
    assert good["accepted"] and not good.get("error")         # the good rep extracted normally
    assert len(pd["accepted"]) == 1                           # the district still has its coverage
    assert pd["telemetry"]["errors"] == 1 and pd["telemetry"]["rep_errors"] == 1


def test_run_district_reraises_billing_from_a_rep(monkeypatch):
    """#173: a BillingAuthError raised while processing a rep propagates out of _run_district (halts),
    it is never caught by the per-rep skip guard."""
    import pytest
    monkeypatch.setattr(R7, "resolve_content", lambda *a: "CONTENT")

    def _billing(*a, **k):
        raise R7.OR.BillingAuthError("HTTP 402")
    monkeypatch.setattr(R7, "_call", _billing)

    groups = [{"rec_key": "D:aa", "file": "x.txt", "kind": "text", "council_id": "lc",
               "voters": ["m1"], "prompt_ids": {"m1": "p"}}]
    with pytest.raises(R7.OR.BillingAuthError):
        R7._run_district("D", "Dville", groups, {"lc": {"voters": ["m1"], "prompts": {}}}, None, False)


def test_run_district_failed_rep_keeps_already_billed_calls(monkeypatch):
    """#184: when a rep fails AFTER one or more voter calls already succeeded (and were billed), those
    calls are preserved in the failure record — their cost must not vanish from telemetry/receipts."""
    monkeypatch.setattr(R7, "resolve_content", lambda *a: "CONTENT")
    monkeypatch.setattr(R7, "_call", lambda m, p, k, c: R7.OR.CallResult(
        model=m, ok=True, content="[]", cost_usd=0.002, prompt_tokens=10, completion_tokens=5))
    monkeypatch.setattr(R7.PARSE, "parse_schedules", lambda content: [])

    def _consensus_boom(rows, judge=None):
        raise ValueError("consensus blew up AFTER both voters were billed")
    monkeypatch.setattr(R7.AGG, "consensus_school_facts", _consensus_boom)
    monkeypatch.setattr(R7.AGG, "district_bands_from_facts", lambda facts: {})

    groups = [{"rec_key": "D:aa", "file": "x.txt", "kind": "text", "council_id": "lc",
               "voters": ["m1", "m2"], "prompt_ids": {"m1": "p", "m2": "p"}}]
    pd = R7._run_district("D", "Dville", groups, {"lc": {"voters": ["m1", "m2"], "prompts": {}}},
                          None, use_judge=False)
    rep = pd["reps"][0]
    assert "consensus blew up" in rep["error"]
    assert len(rep["calls"]) == 2                          # BOTH billed voter calls preserved (#184)
    assert pd["telemetry"]["cost_usd"] == 0.004            # their $ still counted, not silently lost
    assert pd["telemetry"]["rep_errors"] == 1


def test_run_district_isolates_a_malformed_rep_group(monkeypatch):
    """#185: a rep-group missing a required key is isolated at the REP level (recorded + skipped) — it
    must not raise out of _run_district and strand the district's OTHER reps (the #122 symptom)."""
    monkeypatch.setattr(R7, "resolve_content", lambda *a: "CONTENT")
    monkeypatch.setattr(R7, "_call", lambda m, p, k, c: R7.OR.CallResult(model=m, ok=True, content="[]"))
    monkeypatch.setattr(R7.PARSE, "parse_schedules", lambda c: [])
    monkeypatch.setattr(R7.AGG, "consensus_school_facts", lambda rows, judge=None: ([], []))
    monkeypatch.setattr(R7.AGG, "district_bands_from_facts", lambda facts: {})

    groups = [
        {"rec_key": "D:aa", "kind": "text", "council_id": "lc", "prompt_ids": {}},   # MISSING file+voters
        {"rec_key": "D:bb", "file": "good.txt", "kind": "text", "council_id": "lc",
         "voters": ["m1"], "prompt_ids": {"m1": "p"}},
    ]
    pd = R7._run_district("D", "Dville", groups, {"lc": {"voters": ["m1"], "prompts": {}}}, None, False)
    assert pd["n_reps"] == 2                               # both attempted, neither stranded the other
    assert "KeyError" in pd["reps"][0]["error"]            # malformed group isolated at rep level, not raised
    assert pd["reps"][1].get("error") is None             # the healthy rep still ran


def test_run_district_bands_failure_preserves_billed_reps(monkeypatch):
    """#183: a bug in post-loop band aggregation must NOT discard the district's already-billed reps —
    the reps + telemetry survive (so the district persists + spend is recorded), bands go empty."""
    monkeypatch.setattr(R7, "resolve_content", lambda *a: "CONTENT")
    monkeypatch.setattr(R7, "_call", lambda m, p, k, c: R7.OR.CallResult(
        model=m, ok=True, content="[]", cost_usd=0.003))
    monkeypatch.setattr(R7.PARSE, "parse_schedules", lambda c: [{"school": "x"}])
    monkeypatch.setattr(R7.AGG, "consensus_school_facts", lambda rows, judge=None: (
        [{"band": "high", "school": "x", "start": "08:00", "end": "14:00", "gross": 360,
          "method": "council_agree", "models": ["m1"]}], []))

    def _bands_boom(facts):
        raise KeyError("gross_minutes")
    monkeypatch.setattr(R7.AGG, "district_bands_from_facts", _bands_boom)

    groups = [{"rec_key": "D:aa", "file": "x.txt", "kind": "text", "council_id": "lc",
               "voters": ["m1"], "prompt_ids": {"m1": "p"}}]
    pd = R7._run_district("D", "Dville", groups, {"lc": {"voters": ["m1"], "prompts": {}}}, None, False)
    assert pd["bands"] == {} and "district_bands" in pd["error"]   # aggregation failed → empty, not lost
    assert len(pd["reps"]) == 1 and pd["reps"][0]["accepted"]      # the billed rep survives
    assert pd["telemetry"]["cost_usd"] == 0.003                    # its spend is still recorded


def test_print_council_reports_failed_districts(capsys):
    """#188: the CLI summary surfaces out['failed'] — a redirected-to-log run must not read as clean
    when districts were skipped (the console path already alerts; the CLI path lagged)."""
    out = {"telemetry": {"calls": 1, "judge_calls": 0, "errors": 0, "prompt_tokens": 1,
                         "completion_tokens": 1, "cost_usd": 0.0, "truncated": 0},
           "districts": {}, "failed": [{"district_id": "ZZBAD", "error": "KeyError: 'x'"}]}
    R7._print_council(out)
    printed = capsys.readouterr().out
    assert "1 districts FAILED" in printed and "ZZBAD" in printed and "KeyError" in printed


def test_frozen_handoff_with_blind_image_judge_refused(monkeypatch):
    """#138 (the #82-recurrence guard): a frozen handoff EMBEDS its council configs, so a pre-swap
    image handoff still names the dead text-only judge — the run must refuse BEFORE any paid call
    (re-freeze under current configs), not 404 every judge call while paying for voters."""
    import copy
    import pytest
    doc = copy.deepcopy(DOC)
    doc["councils"]["image"] = {"voters": ["google/gemini-2.5-flash", "mistralai/mistral-large-2512"],
                                "judge": "deepseek/deepseek-v3.2",        # text-only — the #82 bug
                                "prompts": {"default": "stage6.extract.vision.v1"}}
    doc["districts"][0]["records"][0]["reps"] = [
        {"file": "raster_p-1.png", "kind": "image", "councils": ["image"]}]
    called = []
    monkeypatch.setattr(R7, "_run_district", lambda *a, **k: called.append(a) or None)
    with pytest.raises(ValueError, match="not vision-capable|404"):
        R7.run_council_streaming(doc, persist=False)
    assert called == []      # refused before any district ran


def test_current_image_council_passes_the_vision_check():
    """The amended (post-#82) image council — Qwen-VL judge — must pass the frozen-doc check."""
    from infrastructure.acquisition.stage6_handoff import councils as C6
    doc = {"councils": {"image": C6.get("image")},
           "districts": [{"district_id": "Z", "records": [
               {"rec_key": "Z:a", "reps": [{"file": "p.png", "kind": "image", "councils": ["image"]}]}]}]}
    R7._check_image_councils(doc)     # must not raise
