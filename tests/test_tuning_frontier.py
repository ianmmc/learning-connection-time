"""REQ-096 / issue #56 — frontier / grid search over the Stage 5 V2 DETECTOR params.

Re-scores the LABELED records from the review DB under candidate detector/combiner params (no
re-ingest: the signal vectors + human labels are already stored) through the LIVE scoring path
(detectors.run_all -> combiner.combine), reuses the harness metric functions, and emits the
precision/recall frontier subject to the hard recall floor — plus which records move and a
LeaveOneGroupOut-by-district overfitting guard. Pure functions on synthetic signals; the DB
loader is exercised against connection-scoped TEMP tables on the real governance session.
"""
import json

import pytest

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


def test_exploration_cohort_catches_the_illusion_of_improvement():
    """#214 — the whole point. Tightening table_min_times to 5 REMOVES the tier-A lookalike FP (d2:b), so
    tier-A PRECISION rises 0.667→1.0 (a win, measured on the approved set) — while the SAME move suppresses
    a real target (d2:a) into tier D. Only the exploration cohort sees that pruned-tail collapse: reject-
    quality falls. The approved-set metric blesses the regression; the cohort metric catches it (FINDINGS §0)."""
    recs = _records()
    champ = DET.DEFAULT_DETECTOR_PARAMS
    chall = {**champ, "table_min_times": 5}
    assert FR.evaluate(recs, champ)["thresholds"]["A"]["precision"] == 0.6667   # approved-set: looks worse...
    assert FR.evaluate(recs, chall)["thresholds"]["A"]["precision"] == 1.0      # ...challenger looks like a WIN
    champ_rq = FR.reject_cohort_quality(recs, champ, p=1.0)
    chall_rq = FR.reject_cohort_quality(recs, chall, p=1.0)
    assert champ_rq["false_neg"] == 0 and champ_rq["rejection_quality"] == 1.0
    assert chall_rq["false_neg"] == 1                                          # a real target now in the tail
    assert chall_rq["rejection_quality"] < champ_rq["rejection_quality"]       # the illusion, caught


def test_grid_results_carry_the_exploration_cohort_reject_quality():
    # every grid config carries its OWN pruned-tail reject-quality beside precision/recall, so a measured-pass
    # reading the grid can't be blind to a tail regression.
    res = FR.grid_search(_records(), {"table_min_times": [4, 5]}, recall_floor=0.0)
    assert res and all("reject_quality" in r and "rejection_quality" in r["reject_quality"] for r in res)


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


def _weak_target():
    # a proximity pair with NO positive keyword -> only lf_weak_times fires -> review / tier B: the
    # record that makes tier-A recall and A+B recall DIFFERENT numbers (#215 review — without it a
    # floor_tier/positive_tier swap in grid_search would pass this test unnoticed).
    return _sig(n_times=2, n_times_in_window=2, proximity_pairs=1)


def test_grid_search_defaults_to_the_canonical_ab_recall_floor():
    # #208: the floor defends A+B recall (reaches-review), NOT tier-A recall, and uses the canonical
    # harness.RECALL_FLOOR — so the ranking tier (A precision) and the floor tier (A+B recall) differ.
    from infrastructure.acquisition.stage5_filter import harness
    recs = _records() + [("d3", "d3:a", _weak_target(), "school_bell_table")]   # a tier-B target
    res = FR.grid_search(recs, {"table_min_times": [4]})   # no floor args -> canonical defaults
    r = res[0]
    # the tier-B target splits the two recalls: A+B (the floored one) stays 1.0, tier-A drops to 2/3 —
    # so these assertions FAIL if grid_search ever reads the floor from positive_tier again.
    assert r["recall"] == r["metrics"]["thresholds"][harness.FLOOR_TIER]["recall"] == 1.0
    assert r["metrics"]["thresholds"]["A"]["recall"] == 0.6667
    assert r["recall"] != r["metrics"]["thresholds"]["A"]["recall"]
    assert r["precision"] == r["metrics"]["thresholds"]["A"]["precision"]
    assert r["feasible"]                                   # 1.0 >= the canonical 0.98 floor


def test_grid_search_rejects_unknown_tier_names():
    # #215 review: tier_target_metrics only builds "A" and "A+B" — an unknown tier must be a clean
    # ValueError at the API boundary, not a KeyError from deep inside the scoring loop.
    import pytest
    recs = _records()
    with pytest.raises(ValueError, match="floor_tier"):
        FR.grid_search(recs, {"table_min_times": [4]}, floor_tier="B")
    with pytest.raises(ValueError, match="positive_tier"):
        FR.grid_search(recs, {"table_min_times": [4]}, positive_tier="AB")


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


# ----------------------------- promotion gate (#212) — champion vs challenger over the same records -----------------------------
def _records_multi(n_districts=6):
    """n_districts districts, each with one table target (tier A at default, tier D when table_min_times is
    tightened to 5) + one empty non-target — enough districts to run the cluster bootstrap (min 3)."""
    recs = []
    for di in range(n_districts):
        d = f"dm{di}"
        recs.append((d, f"{d}:t", _table_sig(4), "school_bell_table"))   # target: A default, D when tightened
        recs.append((d, f"{d}:n", _empty_sig(), "target_absent"))         # non-target: D always
    return recs


def test_gate_promotes_an_identical_challenger_trivially():
    recs = _records_multi()
    v = FR.gate(recs, DET.DEFAULT_DETECTOR_PARAMS, DET.DEFAULT_DETECTOR_PARAMS, margin=0.02, seed=3)
    assert v["promote"] is True                            # no change -> non-inferior by construction
    assert v["non_inferiority"]["lower_bound"] == 0.0


def test_gate_holds_a_challenger_that_regresses_recall_across_districts():
    recs = _records_multi()
    tightened = {**DET.DEFAULT_DETECTOR_PARAMS, "table_min_times": 5}   # drops every table target A->D
    v = FR.gate(recs, DET.DEFAULT_DETECTOR_PARAMS, tightened, margin=0.02, seed=3)
    assert v["promote"] is False
    assert v["logo_guard"]["passes"] is False              # every district loses its only target
    assert v["non_inferiority"]["passes"] is False


def test_gate_requires_a_pre_declared_margin():
    recs = _records_multi()
    with pytest.raises(ValueError):
        FR.gate(recs, DET.DEFAULT_DETECTOR_PARAMS, DET.DEFAULT_DETECTOR_PARAMS, margin=None)


def test_gate_forwards_every_kwarg_to_the_verdict(monkeypatch):
    # PR #220 review: alpha was silently unplumbed — gate() had no parameter for it, so no caller could
    # ever change the NI confidence level. Every kwarg must now reach promotion_verdict.
    captured = {}

    def fake_verdict(champ_rows, chall_rows, **kw):
        captured.update(kw)
        return {"promote": False}

    monkeypatch.setattr(FR.PG, "promotion_verdict", fake_verdict)
    FR.gate(_records_multi(), DET.DEFAULT_DETECTOR_PARAMS,
            {**DET.DEFAULT_DETECTOR_PARAMS, "neg_dom_min": 3},
            margin=0.02, fold_margin=0.1, alpha=0.25, seed=9, n_resamples=77)
    assert captured == {"margin": 0.02, "fold_margin": 0.1, "alpha": 0.25, "seed": 9, "n_resamples": 77}


def test_default_challenger_refuses_an_infeasible_grid_top():
    # PR #220 review: grid_search falls back to the full INFEASIBLE list when nothing clears the recall
    # floor — the CLI's default challenger must never silently gate against a floor-violating config (#208).
    champion = dict(DET.DEFAULT_DETECTOR_PARAMS)
    feasible = [{"feasible": True, "params": {"table_min_times": 3}}]
    infeasible = [{"feasible": False, "params": {"table_min_times": 5}}]
    assert FR.default_challenger(champion, feasible) == {**champion, "table_min_times": 3}
    assert FR.default_challenger(champion, infeasible) is None
    assert FR.default_challenger(champion, []) is None


# ----------------------------- DB loader (real governance Postgres, TEMP tables) -----------------------------
def _seed(sess, records):
    """Stand up the two columns load_labeled() needs as CONNECTION-SCOPED TEMP tables on the governance
    session, seeded with the given records. Auto-dropped when the fixture closes the connection."""
    sess.execute(text("""CREATE TEMP TABLE record (rec_key text PRIMARY KEY, district_id text, tier text,
        category_hypothesis text, signals_json text, duplicate_of text,
        cluster_id text, is_cluster_rep integer)"""))
    sess.execute(text("CREATE TEMP TABLE label (rec_key text PRIMARY KEY, primary_label text, status text)"))
    for dist, rk, sig, lab in records:
        sess.execute(text("""INSERT INTO record (rec_key, district_id, tier, category_hypothesis,
            signals_json, duplicate_of, cluster_id, is_cluster_rep)
            VALUES (:rk,:d,'A','x',:sj,NULL,NULL,1)"""), {"rk": rk, "d": dist, "sj": json.dumps(sig)})
        sess.execute(text("INSERT INTO label (rec_key, primary_label, status) VALUES (:rk,:lab,'labeled')"),
                     {"rk": rk, "lab": lab})
    return sess


@pytest.mark.govdb   # unmarked gov_session tests never run in CI (#215 review)
def test_load_labeled_reads_signals_and_labels(gov_session):
    con = _seed(gov_session, _records())
    recs = FR.load_labeled(con)
    assert len(recs) == 4
    dists = {r[0] for r in recs}
    assert dists == {"d1", "d2"}
    # signals come back as dicts, labels intact
    by_key = {r[1]: r for r in recs}
    assert by_key["d1:a"][3] == "school_bell_table"
    assert isinstance(by_key["d1:a"][2], dict)


@pytest.mark.govdb
def test_gate_runs_end_to_end_through_the_db_loader(gov_session):
    # the #212 gate over records read from the real governance session (load_labeled -> _retier ->
    # promotion_verdict): a tightened challenger that drops every table target must HOLD, on real DB shape.
    con = _seed(gov_session, _records_multi())
    recs = FR.load_labeled(con)
    assert {r[0] for r in recs} == {f"dm{i}" for i in range(6)}
    tightened = {**DET.DEFAULT_DETECTOR_PARAMS, "table_min_times": 5}
    v = FR.gate(recs, DET.DEFAULT_DETECTOR_PARAMS, tightened, margin=0.02, seed=1)
    assert v["promote"] is False and v["non_inferiority"]["passes"] is False
