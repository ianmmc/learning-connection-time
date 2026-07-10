"""#213 / epic #209 Phase 2 — the end-to-end config promotion flow (shadow → gate → swap → record).

The executable spec of how the Phase-2 pieces compose: the shadow is level-appropriate (a patch runs the
cheap in-memory #212 gate; a knob/structural change is routed to the deferred re-ingest shadow, never
faked), actuate freezes artifacts + atomically swaps the pointer only on a promote (with GT + staleness
guards), and record_episode carries the verdict into the ledger. Pure evaluate + tmp-file/govdb actuation."""
import json

import pytest
from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import config_artifact as CA  # noqa: E402
from infrastructure.acquisition.stage5_filter import detectors as DET  # noqa: E402
from infrastructure.acquisition.stage5_filter import promotion_flow as PF  # noqa: E402
from infrastructure.acquisition.stage5_filter import promotion_pointers as PP  # noqa: E402


# ----------------------------- fixtures -----------------------------
def _sig(**over):
    base = {"n_times": 0, "n_times_in_window": 0, "proximity_pairs": 0, "times_after_5pm": 0,
            "positive_kw": [], "negative_kw": {"board": [], "sports": [], "calendar": [], "transport": []},
            "neg_total": 0, "instructional_time": False, "has_table": False, "period_hits": 0,
            "table_time_density": 0, "table_period_rows": 0, "roster_school_names_hit": 0,
            "max_text_chars": 500, "pages": []}
    base.update(over)
    return base


def _records(n_districts=6):
    """n_districts districts, each with one table target (A at default table_min_times=4, D when tightened
    to 5) + one empty non-target. Enough districts for the cluster bootstrap."""
    recs = []
    for di in range(n_districts):
        d = f"D{di}"
        recs.append((d, f"{d}:t", _sig(n_times=4, n_times_in_window=4, table_time_density=4,
                                        positive_kw=["bell schedule"]), "school_bell_table"))
        recs.append((d, f"{d}:n", _sig(max_text_chars=10), "target_absent"))
    return recs


_KNOBS = {"stage5_neg_board": {"entries": [{"value": "agenda"}]}}


def _artifact(detector_params, *, gt="gtLIVE", semver="1.0.0", knobs=None):
    return CA.build_artifact(detector_params, knobs or _KNOBS, gt, semver=semver, created_at="x")


# ----------------------------- shadow_evaluate -----------------------------
def test_evaluate_none_change_does_not_promote():
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS))
    d = PF.shadow_evaluate(champ, champ, _records(), margin=0.02)
    assert d["change_type"] == "none" and d["promote"] is False and d["verdict"] is None


def test_evaluate_patch_runs_the_in_memory_gate_and_promotes_a_non_inferior_challenger():
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS))
    # a LOOSER neg_dom_min is a patch that leaves the table targets at A -> non-inferior recall
    chall = _artifact({**DET.DEFAULT_DETECTOR_PARAMS, "neg_dom_min": 3})
    d = PF.shadow_evaluate(champ, chall, _records(), margin=0.02, seed=1)
    assert d["change_type"] == "patch" and d["shadow"] == "in_memory_rescore"
    assert d["promote"] is True and d["verdict"]["promote"] is True


def test_evaluate_patch_holds_a_recall_regressing_challenger():
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS))
    chall = _artifact({**DET.DEFAULT_DETECTOR_PARAMS, "table_min_times": 5})   # drops every table target
    d = PF.shadow_evaluate(champ, chall, _records(), margin=0.02, seed=1)
    assert d["change_type"] == "patch" and d["promote"] is False
    assert d["verdict"]["non_inferiority"]["passes"] is False


def test_evaluate_minor_and_major_route_to_the_reingest_shadow_and_do_not_promote():
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS))
    minor = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS), knobs={"stage5_neg_board": {"entries": [{"value": "x"}]}})
    dm = PF.shadow_evaluate(champ, minor, _records(), margin=0.02)
    assert dm["change_type"] == "minor" and dm["shadow"] == "needs_reingest_shadow" and dm["promote"] is False
    major = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS), knobs={**_KNOBS, "stage5_neg_new": {}})
    dj = PF.shadow_evaluate(champ, major, _records(), margin=0.02)
    assert dj["change_type"] == "major" and dj["shadow"] == "needs_reingest_shadow" and dj["promote"] is False


# ----------------------------- actuate guards (no DB needed) -----------------------------
def test_actuate_refuses_a_non_promote_decision():
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS))
    with pytest.raises(ValueError, match="non-promote"):
        PF.actuate(None, champ, champ, {"promote": False}, cycle=1)


def test_actuate_refuses_a_cross_gt_promotion():
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS), gt="gtA")
    chall = _artifact({**DET.DEFAULT_DETECTOR_PARAMS, "neg_dom_min": 3}, gt="gtB")
    with pytest.raises(ValueError, match="GT mismatch"):
        PF.actuate(None, champ, chall, {"promote": True}, cycle=1)


# ----------------------------- actuate happy path (govdb + tmp artifact dir) -----------------------------
@pytest.mark.govdb
def test_actuate_freezes_artifacts_and_swaps_the_champion_pointer(gov_session, tmp_path):
    con = gov_session
    con.execute(text("CREATE TEMP TABLE config_pointer (id integer PRIMARY KEY, state_json text, updated_at text)"))
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS))
    chall = _artifact({**DET.DEFAULT_DETECTOR_PARAMS, "neg_dom_min": 3})
    decision = {"promote": True, "verdict": None}
    state = PF.actuate(con, champ, chall, decision, cycle=1, updated_at="2026-07-10T00:00:00Z",
                       config_dir=tmp_path)
    # pointer swapped: challenger is champion, old champion retained as fallback
    assert state["champion"] == chall["version"]
    assert [f["version"] for f in state["fallbacks"]] == [champ["version"]]
    assert PP.load_state(con)["champion"] == chall["version"]
    # both artifacts frozen to disk, content-addressed
    assert PP.read_artifact(champ["version"], config_dir=tmp_path)["version"] == champ["version"]
    assert PP.read_artifact(chall["version"], config_dir=tmp_path)["version"] == chall["version"]


@pytest.mark.govdb
def test_actuate_refuses_when_the_live_champion_is_not_the_evaluated_one(gov_session, tmp_path):
    con = gov_session
    con.execute(text("CREATE TEMP TABLE config_pointer (id integer PRIMARY KEY, state_json text, updated_at text)"))
    # live pointer says champion is "someone_else"; evaluating against a different champion is stale.
    PP.save_state(con, PP.initial_state("someone_else"))
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS))
    chall = _artifact({**DET.DEFAULT_DETECTOR_PARAMS, "neg_dom_min": 3})
    with pytest.raises(ValueError, match="stale promotion"):
        PF.actuate(con, champ, chall, {"promote": True}, cycle=1, config_dir=tmp_path)


# ----------------------------- record_episode -----------------------------
def _scorecard(cfg, a_rec=0.98):
    return {"fingerprints": {"config": cfg, "label_set": "L", "data": "D"},
            "tier_vs_target": {"thresholds": {"A": {"precision": 0.85, "recall": 0.89},
                                              "A+B": {"precision": 0.5, "recall": a_rec}}}}


def test_record_episode_carries_the_verdict_summary(tmp_path):
    champ = _artifact(dict(DET.DEFAULT_DETECTOR_PARAMS))
    chall = _artifact({**DET.DEFAULT_DETECTOR_PARAMS, "neg_dom_min": 3})
    decision = PF.shadow_evaluate(champ, chall, _records(), margin=0.02, seed=1)
    ledger = tmp_path / "episodes.jsonl"
    ep = PF.record_episode(_scorecard("A"), _scorecard("B"), decision, knobs_touched=["neg_dom_min"],
                           rationale="loosen neg dominance", decided_by="test", ledger_path=ledger)
    assert ep["promotion_gate"] is not None and ep["promotion_gate"]["promote"] is True
    # persisted as one JSONL line carrying the verdict
    line = json.loads(ledger.read_text().splitlines()[-1])
    assert line["promotion_gate"]["margin"] == 0.02
