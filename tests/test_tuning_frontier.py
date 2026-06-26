"""REQ-096 — frontier / grid search over the Stage 5 tier thresholds.

Re-scores the LABELED records from the review DB under candidate threshold params (no re-ingest:
the signal vectors + human labels are already stored), reuses the harness metric functions, and
emits the precision/recall frontier subject to the hard recall floor — plus which records move and
a LeaveOneGroupOut-by-district overfitting guard. Pure functions on synthetic signals; the DB
loader + LOGO are exercised against a tiny in-memory SQLite.
"""
import json
import sqlite3

from infrastructure.acquisition.stage5_filter import build_signals as BS  # noqa: E402
from infrastructure.acquisition.stage5_filter import frontier as FR  # noqa: E402


def _sig(**over):
    base = {"n_times": 0, "n_times_in_window": 0, "proximity_pairs": 0, "times_after_5pm": 0,
            "positive_kw": [], "negative_kw": {"board": [], "sports": [], "calendar": [], "transport": []},
            "neg_total": 0, "instructional_time": False, "has_table": False, "period_hits": 0,
            "roster_school_names_hit": 0, "max_text_chars": 500, "pages": []}
    base.update(over)
    return base


# ----------------------------- behavior-preserving parameterization -----------------------------
def test_default_params_reproduce_current_tiers():
    """The parameterized tier_and_category with DEFAULT_TIER_PARAMS must equal the old hardcoded
    behavior on representative signals (the guard that the refactor changed nothing)."""
    # strong target: proximity pair in-window + positive kw -> A
    a = _sig(n_times=4, n_times_in_window=4, proximity_pairs=2, positive_kw=["bell schedule"])
    assert BS.tier_and_category(a, 0)[0] == "A"
    assert BS.tier_and_category(a, 0, BS.DEFAULT_TIER_PARAMS)[0] == "A"
    # neg-dominant: 2 negs, 0 pos, win<=2 -> C
    c = _sig(n_times=2, n_times_in_window=1, neg_total=2,
             negative_kw={"board": ["board", "trustees"], "sports": [], "calendar": [], "transport": []})
    assert BS.tier_and_category(c, 0)[0] == "C"
    # no times, no pages -> D
    d = _sig(n_times=0, max_text_chars=20)
    assert BS.tier_and_category(d, 0)[0] == "D"


def test_params_change_neg_dominant_boundary():
    """Raising neg_dom_min so 2 negatives no longer dominate flips a C to B (the C->B knob)."""
    rec = _sig(n_times=3, n_times_in_window=2, neg_total=2,
               negative_kw={"board": ["board", "trustees"], "sports": [], "calendar": [], "transport": []})
    assert BS.tier_and_category(rec, 0)[0] == "C"                       # default neg_dom_min=2 -> dominant (win<=2)
    loose = {**BS.DEFAULT_TIER_PARAMS, "neg_dom_min": 3}
    assert BS.tier_and_category(rec, 0, loose)[0] == "B"                # 2 < 3 -> not dominant, win>=2 -> B


# ----------------------------- re-score + evaluate over stored records -----------------------------
def _records():
    """(district, rec_key, signals, primary_label) tuples: 2 districts, a mix of targets/non."""
    return [
        ("d1", "d1:a", _sig(proximity_pairs=2, n_times_in_window=3, positive_kw=["bell schedule"]),
         "school_bell_schedule"),                                       # target, -> A
        ("d1", "d1:b", _sig(n_times=2, n_times_in_window=2, neg_total=2,
                            negative_kw={"board": ["board", "trustees"], "sports": [], "calendar": [], "transport": []}),
         "board_schedule"),                                             # non-target, win<=2 -> C (floats to B when neg_dom loosened)
        ("d2", "d2:a", _sig(proximity_pairs=1, n_times_in_window=2, positive_kw=["school hours"]),
         "school_start_end_prose"),                                     # target, -> A
        ("d2", "d2:b", _sig(n_times=0, max_text_chars=10), "none"),     # non-target, -> D
    ]


def test_evaluate_reuses_harness_metrics():
    recs = _records()
    m = FR.evaluate(recs, BS.DEFAULT_TIER_PARAMS)
    # 2 targets, both land in A; no non-targets in A -> precision 1.0, recall 1.0 at tier A
    assert m["thresholds"]["A"]["tp"] == 2
    assert m["thresholds"]["A"]["fp"] == 0
    assert m["thresholds"]["A"]["recall"] == 1.0
    assert m["thresholds"]["A"]["precision"] == 1.0


def test_grid_search_filters_by_recall_floor_and_ranks_by_precision():
    recs = _records()
    grid = {"neg_dom_min": [2, 3], "neg_dom_win_max": [2]}
    res = FR.grid_search(recs, grid, recall_floor=0.99)
    assert res, "expected at least one feasible config"
    # all returned configs satisfy the recall floor, sorted by precision desc
    precs = [r["metrics"]["thresholds"]["A"]["precision"] for r in res]
    assert all(r["feasible"] for r in res)
    assert precs == sorted(precs, reverse=True)


def test_grid_search_reports_which_records_move_vs_baseline():
    recs = _records()
    grid = {"neg_dom_min": [3], "neg_dom_win_max": [2]}     # loosening neg_dom floats the C record
    res = FR.grid_search(recs, grid, recall_floor=0.0, baseline=BS.DEFAULT_TIER_PARAMS)
    moved = res[0]["moves"]
    assert any(mv["rec_key"] == "d1:b" and mv["from"] == "C" and mv["to"] == "B" for mv in moved)


# ----------------------------- LOGO-by-district overfitting guard -----------------------------
def test_logo_cv_holds_out_each_district():
    recs = _records()
    cv = FR.logo_cv(recs, BS.DEFAULT_TIER_PARAMS)
    assert cv["n_folds"] == 2                                # 2 districts -> 2 folds
    assert 0.0 <= cv["recall_mean"] <= 1.0
    assert "recall_std" in cv and "precision_mean" in cv


# ----------------------------- DB loader -----------------------------
def _mini_db(tmp_path):
    db = tmp_path / "review.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE record (rec_key TEXT PRIMARY KEY, district_id TEXT, tier TEXT,
            category_hypothesis TEXT, signals_json TEXT, duplicate_of TEXT,
            cluster_id TEXT, is_cluster_rep INTEGER);
        CREATE TABLE label (rec_key TEXT PRIMARY KEY, primary_label TEXT, status TEXT);
    """)
    for dist, rk, sig, lab in _records():
        con.execute("INSERT INTO record VALUES (?,?,?,?,?,?,?,?)",
                    (rk, dist, "A", "x", json.dumps(sig), None, None, 1))
        con.execute("INSERT INTO label VALUES (?,?,?)", (rk, lab, "labeled"))
    con.commit()
    return con


def test_load_labeled_reads_signals_and_labels(tmp_path):
    con = _mini_db(tmp_path)
    recs = FR.load_labeled(con)
    assert len(recs) == 4
    dists = {r[0] for r in recs}
    assert dists == {"d1", "d2"}
    # signals come back as dicts, labels intact
    by_key = {r[1]: r for r in recs}
    assert by_key["d1:a"][3] == "school_bell_schedule"
    assert isinstance(by_key["d1:a"][2], dict)
