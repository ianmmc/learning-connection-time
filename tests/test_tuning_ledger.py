"""REQ-095 — the tuning-episode ledger records each tuning round as a durable transition
between two scorecards (before -> after): fingerprints, metric deltas, the recall-constraint
check, and the human rationale. Pure functions tested against synthetic scorecards; the I/O
shell tested against a tmp JSONL file. Append-only; reuses the harness fingerprint scheme."""
import json

from infrastructure.acquisition.stage5_filter import tuning_ledger as TL  # noqa: E402


def _scorecard(cfg, labels, data, a_prec, a_rec, ab_prec=0.5, ab_rec=None, cat=0.43, topo=0.8,
               records=150, labeled=150, targets=41, districts=12):
    """A minimal scorecard in the harness's output shape (only the fields the ledger reads). `ab_rec`
    (the A+B recall the floor defends, #208) defaults to a_rec for the legacy fixtures."""
    ab_rec = a_rec if ab_rec is None else ab_rec
    return {
        "generated_at": "2026-06-25T00:00:00Z",
        "fingerprints": {"config": cfg, "label_set": labels, "data": data},
        "counts": {"records": records, "labeled": labeled, "targets": targets, "districts": districts},
        "tier_vs_target": {"thresholds": {
            "A": {"precision": a_prec, "recall": a_rec, "f1": 0.9, "tp": 40, "fp": 7, "fn": 1},
            "A+B": {"precision": ab_prec, "recall": ab_rec, "f1": 0.6, "tp": 40, "fp": 13, "fn": 1},
        }},
        "category_accuracy": {"overall": cat, "n": labeled, "correct": int(cat * labeled)},
        "topology": {"coarse_agreement": topo, "coarse_agree": 8, "coarse_den": 10, "pairs": {}},
    }


# ----------------------------- pure: build_episode -----------------------------
def test_episode_carries_before_after_fingerprints():
    before = _scorecard("cfgA", "lab1", "dat1", a_prec=0.85, a_rec=0.98)
    after = _scorecard("cfgB", "lab1", "dat1", a_prec=0.90, a_rec=0.98)
    ep = TL.build_episode(before, after, knobs_touched=["stage5_neg_board"],
                          rationale="tightened board negs", decided_by="chat")
    assert ep["before"]["config"] == "cfgA"
    assert ep["after"]["config"] == "cfgB"
    assert ep["before"]["label_set"] == ep["after"]["label_set"] == "lab1"


def test_episode_computes_metric_deltas():
    before = _scorecard("cfgA", "lab1", "dat1", a_prec=0.85, a_rec=0.98, cat=0.43)
    after = _scorecard("cfgB", "lab1", "dat1", a_prec=0.90, a_rec=0.98, cat=0.60)
    ep = TL.build_episode(before, after, knobs_touched=["x"], rationale="r", decided_by="chat")
    d = ep["deltas"]
    assert round(d["tier_A_precision"], 4) == 0.05
    assert round(d["category_accuracy"], 4) == 0.17
    assert d["tier_A_recall"] == 0.0


def test_recall_constraint_holds_when_after_recall_meets_floor():
    before = _scorecard("cfgA", "lab1", "dat1", a_prec=0.85, a_rec=0.98)
    after = _scorecard("cfgB", "lab1", "dat1", a_prec=0.90, a_rec=0.98)
    ep = TL.build_episode(before, after, knobs_touched=["x"], rationale="r",
                          decided_by="chat", recall_floor=0.98)
    assert ep["constraint"]["recall_floor"] == 0.98
    assert ep["constraint"]["floor_tier"] == "A+B"        # #208: the floor defends A+B, not tier-A
    assert ep["constraint"]["after_recall"] == 0.98
    assert ep["constraint"]["satisfied"] is True


def test_recall_constraint_violated_when_after_recall_drops_below_floor():
    before = _scorecard("cfgA", "lab1", "dat1", a_prec=0.85, a_rec=0.98)
    after = _scorecard("cfgB", "lab1", "dat1", a_prec=0.95, a_rec=0.90)  # bought precision with recall
    ep = TL.build_episode(before, after, knobs_touched=["x"], rationale="r",
                          decided_by="chat", recall_floor=0.98)
    assert ep["constraint"]["satisfied"] is False


def test_floor_reads_ab_recall_not_tier_a_recall():
    # #208: a config with GREAT tier-A recall but a target dropped BELOW review (A+B recall < floor) must
    # FAIL the constraint — the floor defends reaches-review, not the auto-send bucket.
    before = _scorecard("cfgA", "lab1", "dat1", a_prec=0.85, a_rec=0.90, ab_rec=0.99)
    after = _scorecard("cfgB", "lab1", "dat1", a_prec=0.95, a_rec=0.99, ab_rec=0.95)  # tier-A up, A+B dropped
    ep = TL.build_episode(before, after, knobs_touched=["x"], rationale="r",
                          decided_by="chat", recall_floor=0.98)
    assert ep["constraint"]["after_recall"] == 0.95      # read from A+B, not the 0.99 tier-A
    assert ep["constraint"]["satisfied"] is False
    assert round(ep["deltas"]["tier_AB_recall"], 4) == -0.04   # the floored metric is now a visible delta


def test_malformed_after_scorecard_degrades_to_unsatisfied_not_crash():
    # #215 review: record_from_files loads scorecards from arbitrary on-disk JSON — a null/legacy
    # tier_vs_target must record an episode with after_recall=None / satisfied=False, not raise.
    before = _scorecard("cfgA", "lab1", "dat1", a_prec=0.85, a_rec=0.98)
    after = {**_scorecard("cfgB", "lab1", "dat1", a_prec=0.90, a_rec=0.98), "tier_vs_target": None}
    ep = TL.build_episode(before, after, knobs_touched=["x"], rationale="r", decided_by="chat")
    assert ep["constraint"]["after_recall"] is None
    assert ep["constraint"]["satisfied"] is False
    assert ep["deltas"]["tier_AB_recall"] is None        # the getters degrade the same way


def test_episode_records_provenance_fields():
    before = _scorecard("cfgA", "lab1", "dat1", a_prec=0.85, a_rec=0.98)
    after = _scorecard("cfgB", "lab1", "dat1", a_prec=0.90, a_rec=0.98)
    ep = TL.build_episode(before, after, knobs_touched=["stage5_neg_board", "stage5_neg_sports"],
                          rationale="de-chrome retune", decided_by="ian+claude")
    assert ep["knobs_touched"] == ["stage5_neg_board", "stage5_neg_sports"]
    assert ep["rationale"] == "de-chrome retune"
    assert ep["decided_by"] == "ian+claude"
    assert "recorded_at" in ep


def test_label_or_data_change_flagged_not_pure_config_move():
    """A delta where labels/data ALSO changed is not a clean config-vs-config comparison;
    the episode must flag it so the recommender never treats it as a pure tuning move."""
    before = _scorecard("cfgA", "lab1", "dat1", a_prec=0.85, a_rec=0.98)
    after = _scorecard("cfgB", "lab2", "dat2", a_prec=0.90, a_rec=0.98)  # labels+data moved too
    ep = TL.build_episode(before, after, knobs_touched=["x"], rationale="r", decided_by="chat")
    assert ep["pure_config_move"] is False
    same = TL.build_episode(_scorecard("cfgA", "lab1", "dat1", 0.85, 0.98),
                            _scorecard("cfgB", "lab1", "dat1", 0.90, 0.98),
                            knobs_touched=["x"], rationale="r", decided_by="chat")
    assert same["pure_config_move"] is True


# ----------------------------- I/O shell: append + read -----------------------------
def test_append_and_read_roundtrip_is_jsonl_append_only(tmp_path):
    led = tmp_path / "ledger.jsonl"
    ep1 = TL.build_episode(_scorecard("a", "l", "d", 0.85, 0.98),
                           _scorecard("b", "l", "d", 0.90, 0.98),
                           knobs_touched=["x"], rationale="first", decided_by="chat")
    ep2 = TL.build_episode(_scorecard("b", "l", "d", 0.90, 0.98),
                           _scorecard("c", "l", "d", 0.92, 0.98),
                           knobs_touched=["y"], rationale="second", decided_by="chat")
    TL.append_episode(ep1, led)
    TL.append_episode(ep2, led)
    lines = led.read_text().strip().splitlines()
    assert len(lines) == 2                      # append-only, one object per line
    assert json.loads(lines[0])["rationale"] == "first"
    assert json.loads(lines[1])["rationale"] == "second"
    eps = TL.read_episodes(led)
    assert [e["rationale"] for e in eps] == ["first", "second"]


def test_record_from_files_builds_and_appends(tmp_path):
    before_p = tmp_path / "before.json"
    after_p = tmp_path / "after.json"
    before_p.write_text(json.dumps(_scorecard("a", "l", "d", 0.85, 0.98)))
    after_p.write_text(json.dumps(_scorecard("b", "l", "d", 0.90, 0.98)))
    led = tmp_path / "ledger.jsonl"
    ep = TL.record_from_files(before_p, after_p, knobs_touched=["stage5_neg_board"],
                              rationale="retune board negs after de-chrome",
                              decided_by="chat", ledger_path=led)
    assert ep["before"]["config"] == "a" and ep["after"]["config"] == "b"
    assert len(TL.read_episodes(led)) == 1


def test_read_missing_ledger_returns_empty(tmp_path):
    assert TL.read_episodes(tmp_path / "nope.jsonl") == []
