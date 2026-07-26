"""#120 — the extraction-time mode-stability early-exit (the open half of the sampling policy,
METHODOLOGY.md "Bell Schedule Sampling Policy"). District-grain: _run_district stops issuing paid
council calls once EVERY fillable target band's running mode is stable (aggregate.mode_stable), and
records the unprocessed reps as receipts — never silently absent. DB-free: paid calls + DB mocked."""
import contextlib
import json
from pathlib import Path

from infrastructure.acquisition.process_governance import stage7_run as R7

REPO = Path(__file__).resolve().parent.parent


# --------------------------- the config knob ---------------------------

def test_mode_stability_knob_ships_the_decided_params():
    """The parameters are config-as-data (versioned, provenance-carrying) — NOT console-editable
    numbers: changing them mid-corpus is methodology drift, reviewed by PR (Ian, 2026-07-15)."""
    p = R7.load_mode_stability()
    assert p["enabled"] in (True, False)
    assert p["window"] == 5 and p["min_n"] == 3 and p["min_share"] == 0.6


# --------------------------- _run_district early-exit ---------------------------

def _group(i):
    return {"rec_key": f"D:r{i}", "file": f"f{i}.txt", "kind": "text", "council_id": "lc",
            "voters": ["m1", "m2"], "prompt_ids": {"m1": "p", "m2": "p"}}


def _wire(monkeypatch, per_rep_facts):
    """Mock the paid path: rep i yields per_rep_facts[i] accepted facts (arrival order preserved)."""
    monkeypatch.setattr(R7, "resolve_content", lambda *a: "CONTENT")
    monkeypatch.setattr(R7, "_call", lambda m, p, k, c: R7.OR.CallResult(model=m, ok=True, content="[]"))
    monkeypatch.setattr(R7.PARSE, "parse_schedules", lambda c: [])
    seq = iter(per_rep_facts)
    monkeypatch.setattr(R7.AGG, "consensus_school_facts",
                        lambda rows, judge=None: (next(seq), []))
    monkeypatch.setattr(R7.AGG, "district_bands_from_facts", lambda facts: {})


def _fact(i, gross, band="elementary"):
    return {"band": band, "school": f"school {i}", "start": "08:00", "end": "14:30",
            "gross": gross, "method": "council_agree", "models": ["m1", "m2"]}


MS = {"enabled": True, "window": 5, "min_n": 3, "min_share": 0.6}


def test_early_exit_skips_remaining_reps_once_every_target_band_is_stable(monkeypatch):
    """8 queued reps, one elementary fact each at the same gross: the mode is stable after rep 5
    (window=5), so reps 6-8 are never sent — recorded as skipped receipts, NOT in `reps` (a skipped
    rep must never read as a barren rep to the request loop)."""
    _wire(monkeypatch, [[_fact(i, 390)] for i in range(8)])
    groups = [_group(i) for i in range(8)]
    pd = R7._run_district("D", "Dville", groups, {"lc": {"voters": ["m1", "m2"], "prompts": {}}},
                          None, use_judge=False,
                          early_exit_bands={"elementary"}, ms_params=MS)
    assert len(pd["reps"]) == 5 and pd["n_reps"] == 5          # reps 6-8 unsent
    assert pd["early_exit"]["reason"] == "mode_stable"
    assert pd["early_exit"]["n_reps_skipped"] == 3
    assert [s["rec_key"] for s in pd["skipped_reps"]] == ["D:r5", "D:r6", "D:r7"]
    assert all(s["reason"] == "mode_stable" for s in pd["skipped_reps"])
    sent_keys = {r["rec_key"] for r in pd["reps"]}
    assert sent_keys.isdisjoint({s["rec_key"] for s in pd["skipped_reps"]})


def test_no_early_exit_while_any_target_band_is_unstable(monkeypatch):
    """A second target band with no facts (or a scattered one) blocks the exit — district-grain
    means ALL fillable target bands must be stable (decision A, Ian 2026-07-15)."""
    _wire(monkeypatch, [[_fact(i, 390)] for i in range(8)])
    groups = [_group(i) for i in range(8)]
    pd = R7._run_district("D", "Dville", groups, {"lc": {"voters": ["m1", "m2"], "prompts": {}}},
                          None, use_judge=False,
                          early_exit_bands={"elementary", "high"}, ms_params=MS)
    assert len(pd["reps"]) == 8 and "early_exit" not in pd and not pd.get("skipped_reps")


def test_no_early_exit_when_targets_unknown_or_disabled(monkeypatch):
    """No target bands (missing district_target row → None) or a disabled knob ⇒ the full census —
    unknown is never assumed satisfied."""
    _wire(monkeypatch, [[_fact(i, 390)] for i in range(8)] + [[_fact(i, 390)] for i in range(8)])
    groups = [_group(i) for i in range(8)]
    councils = {"lc": {"voters": ["m1", "m2"], "prompts": {}}}
    pd = R7._run_district("D", "Dville", groups, councils, None, use_judge=False,
                          early_exit_bands=None, ms_params=MS)
    assert len(pd["reps"]) == 8 and "early_exit" not in pd
    pd2 = R7._run_district("D", "Dville", groups, councils, None, use_judge=False,
                           early_exit_bands={"elementary"},
                           ms_params={**MS, "enabled": False})
    assert len(pd2["reps"]) == 8 and "early_exit" not in pd2


def test_scattered_band_never_exits(monkeypatch):
    """min_share=0.6 holds: a genuinely scattered band keeps sampling to the end (the mode_stable
    plurality condition — an early lock-in must not mask disagreement)."""
    _wire(monkeypatch, [[_fact(i, g)] for i, g in enumerate([390, 450, 300, 480, 330, 420, 360, 510])])
    groups = [_group(i) for i in range(8)]
    pd = R7._run_district("D", "Dville", groups, {"lc": {"voters": ["m1", "m2"], "prompts": {}}},
                          None, use_judge=False,
                          early_exit_bands={"elementary"}, ms_params=MS)
    assert len(pd["reps"]) == 8 and "early_exit" not in pd


# --------------------------- streaming wiring ---------------------------

DOC = {
    "handoff_hash": "mstest",
    "councils": {"lc": {"voters": ["m1", "m2"], "judge": "j1",
                        "prompts": {"default": "stage6.extract.v1"}}},
    "districts": [
        {"district_id": "ZZM1", "name": "M1", "records": [
            {"rec_key": "ZZM1:aa", "decision": "send",
             "reps": [{"file": "x.txt", "kind": "text", "councils": ["lc"]}]}]},
    ],
}


def _mock_streaming(monkeypatch, targets):
    seen = {}

    def _fake_run_district(did, name, groups, councils, ddir, use_judge,
                           early_exit_bands=None, ms_params=None):
        seen[did] = early_exit_bands
        return {"district_id": did, "name": name, "n_reps": 1, "n_judged": 0, "reps": [],
                "accepted": [], "unresolved": [], "bands": {},
                "telemetry": {"calls": 0, "judge_calls": 0, "errors": 0,
                              "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}}
    monkeypatch.setattr(R7, "_run_district", _fake_run_district)
    monkeypatch.setattr(R7, "_require_key", lambda: None)
    monkeypatch.setattr(R7, "district_dirs", lambda ids: {})
    monkeypatch.setattr(R7.gdb, "init_precious_schema", lambda: None)
    monkeypatch.setattr(R7.gdb, "session_scope", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(R7, "_early_exit_targets", lambda ids: targets)
    return seen


def test_streaming_passes_the_district_target_bands(monkeypatch):
    seen = _mock_streaming(monkeypatch, {"ZZM1": {"elementary", "high"}})
    R7.run_council_streaming(DOC, persist=False)
    assert seen["ZZM1"] == {"elementary", "high"}


def test_streaming_disables_early_exit_for_probes_and_gt_runs(monkeypatch):
    """A probe measures a council variant and a GT run scores against the curated corpus — both want
    the full census, never the spend shortcut (benchmark-batch members are additionally exempted in
    _early_exit_targets itself — see the govdb section below, #621)."""
    seen = _mock_streaming(monkeypatch, {"ZZM1": {"elementary"}})
    probe = dict(DOC, run_kind="probe")
    R7.run_council_streaming(probe, persist=False)
    assert seen["ZZM1"] is None
    seen2 = _mock_streaming(monkeypatch, {"ZZM1": {"elementary"}})
    R7.run_council_streaming(DOC, persist=False, gt_data={"OTHER": {}})
    assert seen2["ZZM1"] is None


# --------------------------- console visibility (the UI-visibility rule) ---------------------------

def test_gate7_console_shows_the_skip_and_settings_carries_the_toggle():
    """A band value computed from 5 of 8 reps must SAY so at gate@7 (n=5 must not read as "capture
    only found 5"), and the on/off kill-switch lives in Settings (operational, gate-mode precedent) —
    while the numeric params deliberately do NOT (config-as-data, changed by PR)."""
    js = (REPO / "infrastructure/acquisition/process_governance/static/stage7.js").read_text()
    assert 'data-feat="mode-stability-skip"' in js and "n_reps_skipped" in js
    sjs = (REPO / "infrastructure/acquisition/process_governance/static/settings.js").read_text()
    assert 'data-feat="mode-stability-toggle"' in sjs
    assert "/api/stage7/mode-stability" in sjs


# --------------------------- the benchmark exemption (govdb): #621 ---------------------------
# The REQ-151 exemption ("measurement wants the census, not the shortcut") used to key on the
# `batch_00000` ID LITERAL while every other benchmark guard keys on `batch_type`. These exercise the
# REAL SQL against Postgres, with benchmark batch ids that are deliberately NOT `batch_00000`.

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from infrastructure.acquisition.common import benchmark as BM  # noqa: E402
from infrastructure.acquisition.common import db as gdb  # noqa: E402
from infrastructure.acquisition.stage5_filter import build_signals as BS  # noqa: E402

govdb = pytest.mark.govdb


def _seed_target(s, did, bands):
    s.execute(text("DELETE FROM district_target WHERE district_id = :d"), {"d": did})
    s.execute(text("INSERT INTO district_target (district_id, lea_claimed_bands_json, "
                   "schools_by_band_json, nces_by_level_json) VALUES (:d, :c, '{}', '{}')"),
              {"d": did, "c": json.dumps(bands)})


def _seed_batch(s, batch_id, batch_type, district_id):
    from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict
    s.add(Batch(batch_id=batch_id, batch_type=batch_type, status="approved", nces_year="2024_25",
                created_at="t", created_by="zz", meta_json={}))
    s.add(BatchDistrict(batch_id=batch_id, district_id=district_id, ord=0, name="ZZ", state="AK",
                        domain="", enrollment_k12=None, lea_claimed_bands=[], nces_school_counts={},
                        band_processing_order=[], band_meta={}, included=True))
    s.flush()


def _use_test_session(monkeypatch, sess):
    """_early_exit_targets opens its OWN session; point it at the test's (rolled back at teardown).
    Also stub the NCES roster reads — this exercises the walled-set SQL, not band derivation."""
    monkeypatch.setattr(R7.gdb, "session_scope", lambda: contextlib.nullcontext(sess))
    monkeypatch.setattr(R7.SS, "band_rosters_for_district", lambda did: {})
    monkeypatch.setattr(R7.SS, "real_bands_for_district",
                        lambda by_level, sbb, band_rosters=None: {"elementary", "middle", "high"})


@govdb
def test_early_exit_no_longer_keys_on_benchmark_batch_membership(gov_session, monkeypatch):
    """#619 INVERTED this. It used to assert that a benchmark-batch district is absent from the
    targets (full census); the exemption has moved to the run level, so membership no longer decides
    anything here and a benchmark-batch district gets targets exactly like any other.

    Its predecessor was #621's regression guard, which fixed the exemption keying on the
    `batch_00000` LITERAL rather than `batch_type`. That lesson didn't die with the exemption — it is
    why the replacement reads the frozen handoff's `dispatch_type` instead of any id."""
    gdb.init_precious_schema()
    s = gov_session
    BS.ensure_signal_schema(s)                    # district_target lives in the signal schema
    _seed_batch(s, "batch_zz621_bm", "benchmark", "ZZ621BM")
    _seed_batch(s, "batch_zz621_fr", "first-run", "ZZ621OK")
    _seed_target(s, "ZZ621BM", ["elementary", "high"])
    _seed_target(s, "ZZ621OK", ["elementary", "high"])
    _use_test_session(monkeypatch, s)

    out = R7._early_exit_targets(["ZZ621BM", "ZZ621OK"])
    assert out["ZZ621BM"] == {"elementary", "high"}   # was: absent. Membership decides nothing now.
    assert out["ZZ621OK"] == {"elementary", "high"}   # ordinary district: unchanged behavior


@govdb
def test_early_exit_reaches_a_district_in_both_a_benchmark_and_a_production_batch(
        gov_session, monkeypatch):
    """THE #619 INVERSION, on the exact shape epic #617's re-run campaign creates: a batch_00000
    district that later runs in a production follow-up batch (#620). Pre-#619 this asserted `== {}`
    — the district was exempted forever on membership alone, so all 27 re-run districts would have
    paid a full-census extraction on every future production run.

    REQ-151's "a measurement run wants the census" case did not go away; it moved to the run-level
    disablers, which the next test covers. The distinction that matters: THIS run measures nothing,
    so there is nothing for the shortcut to distort."""
    gdb.init_precious_schema()
    s = gov_session
    BS.ensure_signal_schema(s)
    _seed_batch(s, "batch_zz621_bm2", "benchmark", "ZZ621BOTH")
    _seed_batch(s, "batch_zz621_fu", "follow-up", "ZZ621BOTH")
    _seed_target(s, "ZZ621BOTH", ["high"])
    _use_test_session(monkeypatch, s)

    assert R7._early_exit_targets(["ZZ621BOTH"]) == {"ZZ621BOTH": {"high"}}


def test_early_exit_is_disabled_for_a_benchmark_dispatch():
    """Where REQ-151's exemption LIVES post-#619: the run level, read off the frozen handoff. A
    benchmark dispatch (#618) is the Stages-6/7 A/B harness, so it wants the full census for the same
    reason a probe or a GT-scored run does — and unlike district membership, this can see a Council
    Lab A/B composed entirely of production reps.

    Asserted on `_early_exit_enabled` — the real predicate the run path calls — rather than through
    `run_council_streaming`, which is a paid OpenRouter path. The disabler was extracted into that
    named function precisely so this could pin the code instead of a copy of the condition."""
    on = {"enabled": True}
    ok = dict(run_kind="production", gt_data=None, ms_params=on)

    assert R7._early_exit_enabled({"dispatch_type": BM.DISPATCH_PRODUCTION}, **ok) is True
    assert R7._early_exit_enabled({}, **ok) is True                   # unstamped => production
    assert R7._early_exit_enabled({"dispatch_type": BM.DISPATCH_BENCHMARK}, **ok) is False
    # the three sibling disablers still hold independently
    assert R7._early_exit_enabled({}, "probe", None, on) is False
    assert R7._early_exit_enabled({}, "production", {"x": 1}, on) is False
    assert R7._early_exit_enabled({}, "production", None, {"enabled": False}) is False
