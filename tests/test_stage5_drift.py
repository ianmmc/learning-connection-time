"""REQ-097 drift detector (#75) — CUSUM + Wilson two-gate over the scorecard series, advisory only.

The series is the fingerprinted scorecard directory; segmentation by config fingerprint IS the
config-induced vs new-district distinction (a config change starts a fresh segment; within-segment
movement can only come from new labels/data). Never auto-retunes."""
import json
from pathlib import Path

from infrastructure.acquisition.stage5_filter import drift as DR
from infrastructure.acquisition.stage5_filter import harness as H


def card(tmp, name, at, config, a_tp, a_fp, fl_tp, fl_fn):
    c = {"generated_at": at, "fingerprints": {"config": config, "label_set": "l", "data": "d"},
         "tier_vs_target": {"thresholds": {
             "A": {"tp": a_tp, "fp": a_fp, "precision": round(a_tp / (a_tp + a_fp), 4),
                   "fn": 0, "recall": 0.0, "f1": 0.0},
             H.FLOOR_TIER: {"tp": fl_tp, "fn": fl_fn, "fp": 0,
                            "recall": round(fl_tp / (fl_tp + fl_fn), 4), "precision": 0.0, "f1": 0.0}}}}
    Path(tmp, f"scorecard_{name}.json").write_text(json.dumps(c))


def test_healthy_series_recommends_nothing(tmp_path):
    for i in range(4):
        card(tmp_path, f"t{i}", f"2026-07-1{i}T00:00:00Z", "cfgA", 335, 50, 414, 3)
    v = DR.detect(tmp_path)
    assert v["retune_recommended"] is False and v["n_points"] == 4 and v["config"] == "cfgA"


def test_sustained_degradation_trips_the_two_gate(tmp_path):
    # the 2026-06-30 shape: same config, precision collapses as new districts accrue (0.87 -> 0.69)
    card(tmp_path, "t0", "2026-07-10T00:00:00Z", "cfgA", 335, 50, 414, 3)
    for i in range(1, 4):
        card(tmp_path, f"t{i}", f"2026-07-1{i}T00:00:00Z", "cfgA", 300, 135, 414, 3)
    v = DR.detect(tmp_path)
    assert v["precision"]["tripped"] and v["precision"]["breach"] and v["precision"]["alert"]
    assert v["retune_recommended"] is True
    assert v["recall"]["alert"] is False   # the recall stream stays clean — streams are separate


def test_recall_stream_trips_on_floor_breach(tmp_path):
    card(tmp_path, "t0", "2026-07-10T00:00:00Z", "cfgA", 335, 50, 414, 3)      # 0.9928
    for i in range(1, 4):
        card(tmp_path, f"t{i}", f"2026-07-1{i}T00:00:00Z", "cfgA", 335, 50, 380, 37)   # 0.911 << 0.98
    v = DR.detect(tmp_path)
    assert v["recall"]["alert"] and v["retune_recommended"] is True


def test_single_noisy_small_n_point_does_not_false_alarm(tmp_path):
    # criterion 2: one small-n dip must not alert — the CUSUM needs accumulated evidence AND the
    # Wilson lower bound must breach. A lone 8/10 recall point has a wide interval and one LLR term.
    card(tmp_path, "t0", "2026-07-10T00:00:00Z", "cfgA", 30, 3, 8, 2)
    v = DR.detect(tmp_path)
    assert v["retune_recommended"] is False


def test_config_change_resets_the_segment(tmp_path):
    # criterion 3, structural: degraded history under cfgA is NOT held against the new cfgB —
    # the tuning move's own effect is the ledger episode's business, not drift.
    for i in range(3):
        card(tmp_path, f"a{i}", f"2026-07-1{i}T00:00:00Z", "cfgA", 300, 135, 380, 37)
    card(tmp_path, "b0", "2026-07-15T00:00:00Z", "cfgB", 335, 50, 414, 3)
    v = DR.detect(tmp_path)
    assert v["config"] == "cfgB" and v["n_points"] == 1
    assert v["retune_recommended"] is False


def test_empty_and_malformed_scorecards_never_crash(tmp_path):
    Path(tmp_path, "scorecard_bad.json").write_text("{not json")
    v = DR.detect(tmp_path)
    assert v["retune_recommended"] is False and v["n_points"] == 0


def test_wilson_lower_bound_shape():
    assert DR.wilson_lower(0, 0) is None
    assert 0.0 <= DR.wilson_lower(8, 10) < 0.8       # below the point estimate
    assert DR.wilson_lower(999, 1000) > DR.wilson_lower(9, 10)   # tightens with n


def test_verdict_is_advisory_never_mutating(tmp_path):
    card(tmp_path, "t0", "2026-07-10T00:00:00Z", "cfgA", 335, 50, 414, 3)
    before = sorted(p.name for p in Path(tmp_path).iterdir())
    v = DR.detect(tmp_path)
    assert "never auto-retunes" in v["posture"]
    assert sorted(p.name for p in Path(tmp_path).iterdir()) == before   # pure read


def test_console_badge_is_wired():
    """UI-visibility pin (the memory rule): the badge markup + the /api/progress drift key must exist
    in source, so the advisory surface can't silently disappear."""
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "infrastructure/acquisition/process_governance/static/app.js").read_text()
    assert 'dataset.feat = "drift-badge"' in js and "retune recommended" in js
    css = (repo / "infrastructure/acquisition/process_governance/static/app.css").read_text()
    assert ".drift-badge" in css
    server = (repo / "infrastructure/acquisition/process_governance/server.py").read_text()
    assert 'out["drift"] = drift.detect()' in server
