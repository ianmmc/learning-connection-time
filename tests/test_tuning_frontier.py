"""REQ-096 / issue #56 — frontier / grid search over the Stage 5 V2 DETECTOR params.

Re-scores the LABELED records from the review DB under candidate detector/combiner params (no
re-ingest: the signal vectors + human labels are already stored) through the LIVE scoring path
(detectors.run_all -> combiner.combine), reuses the harness metric functions, and emits the
precision/recall frontier subject to the hard recall floor — plus which records move and a
LeaveOneGroupOut-by-district overfitting guard. Pure functions on synthetic signals; the DB
loader is exercised against connection-scoped TEMP tables on the real governance session.
"""
import json

from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import combiner as COMB  # noqa: E402
from infrastructure.acquisition.stage5_filter import detectors as DET  # noqa: E402
from infrastructure.acquisition.stage5_filter import frontier as FR  # noqa: E402


def _sig(**over):
    base = {"n_times": 0, "n_times_in_window": 0, "proximity_pairs": 0, "times_after_5pm": 0,
            "positive_kw": [], "negative_kw": {"board": [], "sports": [], "calendar": [], "transport": []},
            "neg_total": 0, "instructional_time": False, "has_table": False, "period_hits": 0,
            "table_time_density": 0, "table_period_rows": 0,
            "roster_school_names_hit": 0, "max_text_chars": 500, "pages": []}
    base.update(over)
    return base


def _prose_target():
    # lf_prose_pair fires (strong target) -> send / tier A under any grid params here
    return _sig(n_times=4, n_times_in_window=3, proximity_pairs=2, positive_kw=["bell schedule"])


def _table_sig(density=4):
    # lf_time_table fires iff density >= table_min_times (with a positive kw); nothing else votes
    # (no proximity pair), so tightening table_min_times drops it from A to D — the moveable record.
    return _sig(n_times=density, n_times_in_window=density,
                table_time_density=density, positive_kw=["bell schedule"])


def _empty_sig():
    return _sig(max_text_chars=10)   # lf_no_times -> suppress / tier D


# ----------------------------- the knob surface is the LIVE one -----------------------------
def test_default_detector_params_reproduce_live_tiers():
    """The frontier's baseline params ARE detectors.DEFAULT_DETECTOR_PARAMS, and re-scoring goes
    through the live combiner path (the guard that the tool tunes the thing that ships)."""
    assert COMB.score_record(_prose_target(), DET.DEFAULT_DETECTOR_PARAMS)["tier"] == "A"
    assert COMB.score_record(_table_sig(4), DET.DEFAULT_DETECTOR_PARAMS)["tier"] == "A"
    assert COMB.score_record(_empty_sig(), DET.DEFAULT_DETECTOR_PARAMS)["tier"] == "D"


def test_params_change_the_table_threshold_boundary():
    """Tightening table_min_times so a 4-time table no longer qualifies drops it out of tier A."""
    rec = _table_sig(4)
    assert COMB.score_record(rec, DET.DEFAULT_DETECTOR_PARAMS)["tier"] == "A"   # default table_min_times=4
    tight = {**DET.DEFAULT_DETECTOR_PARAMS, "table_min_times": 5}
    assert COMB.score_record(rec, tight)["tier"] != "A"


# ----------------------------- re-score + evaluate over stored records -----------------------------
def _records():
    """(district, rec_key, signals, primary_label) tuples: 2 districts, a mix of targets/non."""
    return [
        ("d1", "d1:a", _prose_target(), "school_bell_table"),        # target -> A always
        ("d1", "d1:b", _empty_sig(), "target_absent"),                # non-target -> D
        ("d2", "d2:a", _table_sig(4), "school_bell_table"),          # target -> A at default, D when tightened
        ("d2", "d2:b", _table_sig(4), "target_absent"),               # table LOOKALIKE -> the tier-A FP at default
    ]


def test_evaluate_reuses_harness_metrics():
    recs = _records()
    m = FR.evaluate(recs, DET.DEFAULT_DETECTOR_PARAMS)
    # 2 targets in A (tp=2) + the lookalike FP -> precision 2/3, recall 1.0 at tier A
    assert m["thresholds"]["A"]["tp"] == 2
    assert m["thresholds"]["A"]["fp"] == 1
    assert m["thresholds"]["A"]["recall"] == 1.0
    assert m["thresholds"]["A"]["precision"] == 0.6667


def test_grid_search_filters_by_recall_floor_and_ranks_by_precision():
    recs = _records()
    grid = {"table_min_times": [4, 5]}
    # floor_tier="A" here exercises the floor MECHANISM on the synthetic set (tier-A recall drops to 0.5
    # when tightening to 5). The CANONICAL default floor_tier is A+B — see the next test.
    res = FR.grid_search(recs, grid, recall_floor=0.99, floor_tier="A")
    assert res, "expected at least one feasible config"
    # tightening to 5 drops a real target (recall 0.5) -> infeasible; only the default survives
    assert all(r["feasible"] for r in res)
    assert [r["params"]["table_min_times"] for r in res] == [4]
    precs = [r["metrics"]["thresholds"]["A"]["precision"] for r in res]
    assert precs == sorted(precs, reverse=True)


def test_grid_search_defaults_to_the_canonical_ab_recall_floor():
    # #208: the floor defends A+B recall (reaches-review), NOT tier-A recall, and uses the canonical
    # harness.RECALL_FLOOR — so the ranking tier (A precision) and the floor tier (A+B recall) differ.
    from infrastructure.acquisition.stage5_filter import harness
    recs = _records()
    res = FR.grid_search(recs, {"table_min_times": [4]})   # no floor args -> canonical defaults
    r = res[0]
    # r["recall"] is now the A+B (floor-tier) recall, r["precision"] the A (ranking-tier) precision
    assert r["recall"] == r["metrics"]["thresholds"][harness.FLOOR_TIER]["recall"]
    assert r["precision"] == r["metrics"]["thresholds"]["A"]["precision"]


def test_grid_search_reports_which_records_move_vs_baseline():
    recs = _records()
    grid = {"table_min_times": [5]}      # tightening moves BOTH d2 table records out of A
    res = FR.grid_search(recs, grid, recall_floor=0.0, baseline=DET.DEFAULT_DETECTOR_PARAMS)
    moved = res[0]["moves"]
    assert any(mv["rec_key"] == "d2:b" and mv["from"] == "A" and not mv["is_target"] for mv in moved)
    assert any(mv["rec_key"] == "d2:a" and mv["from"] == "A" and mv["is_target"] for mv in moved)


# ----------------------------- LOGO-by-district overfitting guard -----------------------------
def test_logo_cv_holds_out_each_district():
    recs = _records()
    cv = FR.logo_cv(recs, DET.DEFAULT_DETECTOR_PARAMS)
    assert cv["n_folds"] == 2                                # 2 districts -> 2 folds
    assert 0.0 <= cv["recall_mean"] <= 1.0
    assert "recall_std" in cv and "precision_mean" in cv


# ----------------------------- DB loader (real governance Postgres, TEMP tables) -----------------------------
def _seed_mini(sess):
    """Stand up the two columns load_labeled() needs as CONNECTION-SCOPED TEMP tables on the
    governance session, seeded with _records(). Auto-dropped when the fixture closes the connection."""
    sess.execute(text("""CREATE TEMP TABLE record (rec_key text PRIMARY KEY, district_id text, tier text,
        category_hypothesis text, signals_json text, duplicate_of text,
        cluster_id text, is_cluster_rep integer)"""))
    sess.execute(text("CREATE TEMP TABLE label (rec_key text PRIMARY KEY, primary_label text, status text)"))
    for dist, rk, sig, lab in _records():
        sess.execute(text("""INSERT INTO record (rec_key, district_id, tier, category_hypothesis,
            signals_json, duplicate_of, cluster_id, is_cluster_rep)
            VALUES (:rk,:d,'A','x',:sj,NULL,NULL,1)"""), {"rk": rk, "d": dist, "sj": json.dumps(sig)})
        sess.execute(text("INSERT INTO label (rec_key, primary_label, status) VALUES (:rk,:lab,'labeled')"),
                     {"rk": rk, "lab": lab})
    return sess


def test_load_labeled_reads_signals_and_labels(gov_session):
    con = _seed_mini(gov_session)
    recs = FR.load_labeled(con)
    assert len(recs) == 4
    dists = {r[0] for r in recs}
    assert dists == {"d1", "d2"}
    # signals come back as dicts, labels intact
    by_key = {r[1]: r for r in recs}
    assert by_key["d1:a"][3] == "school_bell_table"
    assert isinstance(by_key["d1:a"][2], dict)
