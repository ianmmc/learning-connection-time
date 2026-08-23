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


def test_console_badge_is_wired(app_js):
    """UI-visibility pin (the memory rule): the badge markup + the /api/progress drift key must exist
    in source, so the advisory surface can't silently disappear."""
    repo = Path(__file__).resolve().parent.parent
    js = app_js
    assert 'dataset.feat = "drift-badge"' in js and "retune recommended" in js
    css = (repo / "infrastructure/acquisition/process_governance/static/app.css").read_text()
    assert ".drift-badge" in css
    server = (repo / "infrastructure/acquisition/process_governance/server.py").read_text()
    assert 'out["drift"] = drift.detect()' in server


# ---- #543-#547 review fixes ----
def test_zero_tier_a_predictions_never_crashes(tmp_path):
    # harness's documented shape for zero tier-A predictions is precision=None — the unguarded first
    # build crashed with TypeError on the fresh-config segment this is most likely on.
    c = {"generated_at": "2026-07-18T00:00:00Z", "fingerprints": {"config": "cfgA", "label_set": "l", "data": "d"},
         "tier_vs_target": {"thresholds": {
             "A": {"tp": 0, "fp": 0, "precision": None, "fn": 0, "recall": 0.0, "f1": 0.0},
             H.FLOOR_TIER: {"tp": 10, "fn": 0, "fp": 0, "recall": 1.0, "precision": 0.0, "f1": 0.0}}}}
    Path(tmp_path, "scorecard_t0.json").write_text(json.dumps(c))
    v = DR.detect(tmp_path)
    assert v["retune_recommended"] is False
    assert v["precision"]["alert"] is False and v["precision"].get("note")
    assert v["recall"]["alert"] is False       # the recall stream still evaluated normally


def test_wilson_lower_clamps_k_above_n():
    # was ValueError: math domain error — a landmine for any caller outside the harness invariant
    assert DR.wilson_lower(15, 10) == DR.wilson_lower(10, 10)


def test_historical_best_is_reported_cross_config(tmp_path):
    """The precision baseline is deliberately self-referential (post-adoption drift only; adoption-time
    regression is the #212 promotion gate's jurisdiction) — historical_best is the informational field
    that lets a human see an adoption-level gap the CUSUM structurally cannot alert on."""
    card(tmp_path, "a0", "2026-07-10T00:00:00Z", "cfgOLD", 335, 54, 414, 3)     # 0.8612 era
    for i in range(3):
        card(tmp_path, f"b{i}", f"2026-07-1{i + 1}T00:00:00Z", "cfgNEW", 70, 30, 414, 3)  # adopted at 0.70
    v = DR.detect(tmp_path)
    assert v["retune_recommended"] is False    # flat-at-adoption never CUSUM-alerts (documented)
    assert v["precision"]["historical_best"] == 0.8612   # but the gap is visible to the human
    assert v["precision"]["baseline"] == 0.7
