"""#212 / epic #209 Phase 2 — the group-aware non-inferiority promotion gate's PURE stats core.

The executable spec of the gate's invariant: *promote a Stage-5 config only when the challenger is provably
NOT-worse than the champion within a pre-declared margin Δ, on held-out DISTRICTS, with cluster-honest
variance.* These tests lock the decision logic before any live wiring (the harness/exploration_audit
precedent). No DB, no cash — proven-library stats over synthetic district-clustered fixtures.

The gate is deliberately CONSERVATIVE: it gates on the harm direction (A+B recall degradation) and treats
'can't prove not-worse' as 'don't promote'. Every test either pins a numeric definition (recall/precision,
DEFF) or a decision (promote / hold / raise)."""
import numpy as np
import pytest

from infrastructure.acquisition.stage5_filter import promotion_gate as PG  # noqa: E402


# ----------------------------- fixtures: synthetic district-clustered scored rows -----------------------------
def _rows_uniform(n_districts, n_targets, n_nontargets, target_tier="A", nontarget_tier="A"):
    """n_districts districts, each with n_targets target records + n_nontargets non-targets, all at the
    given tiers. Shape matches frontier._retier: (district_id, rec_key, tier, is_target)."""
    rows = []
    for di in range(n_districts):
        d = f"D{di}"
        for j in range(n_targets):
            rows.append((d, f"{d}-t{j}", target_tier, True))
        for j in range(n_nontargets):
            rows.append((d, f"{d}-n{j}", nontarget_tier, False))
    return rows


# ----------------------------- per-district metric (definitions, not estimators) -----------------------------
def test_per_district_recall_and_precision_are_the_textbook_ratios():
    # District D0: 2 targets, tiers A (TP) and D (FN); 1 nontarget at A (FP).
    rows = [("D0", "t0", "A", True), ("D0", "t1", "D", True), ("D0", "n0", "A", False)]
    rec = PG.per_district_metric(rows, positive=PG.POSITIVE_AB, metric="recall")
    prec = PG.per_district_metric(rows, positive=PG.POSITIVE_AB, metric="precision")
    assert rec["D0"] == pytest.approx(0.5)      # 1 of 2 targets reached A+B
    assert prec["D0"] == pytest.approx(0.5)      # 1 of 2 A+B predictions was a target


def test_per_district_metric_is_none_not_zero_when_the_denominator_is_empty():
    # A district with no targets has UNDEFINED recall (not 0.0 — issue #63's lesson); no A+B predictions -> undefined precision.
    rows = [("D0", "n0", "A", False)]           # one nontarget, sent
    assert PG.per_district_metric(rows, positive=PG.POSITIVE_AB, metric="recall")["D0"] is None
    rows2 = [("D0", "t0", "D", True)]            # one target, suppressed -> no positive prediction
    assert PG.per_district_metric(rows2, positive=PG.POSITIVE_AB, metric="precision")["D0"] is None


def test_per_district_metric_rejects_an_unknown_metric():
    with pytest.raises(ValueError):
        PG.per_district_metric([], positive=PG.POSITIVE_AB, metric="f1")


# ----------------------------- paired deltas -----------------------------
def test_paired_deltas_only_keep_districts_defined_under_both_and_carry_the_sign():
    champ = [("D0", "t0", "A", True), ("D1", "t0", "A", True), ("D2", "n0", "A", False)]
    chall = [("D0", "t0", "D", True), ("D1", "t0", "A", True), ("D2", "n0", "A", False)]
    deltas = PG.paired_district_deltas(champ, chall, positive=PG.POSITIVE_AB, metric="recall")
    # D2 has no targets -> undefined recall under both -> excluded. D0 regressed 1.0->0.0, D1 unchanged.
    by = {r["district"]: r for r in deltas}
    assert set(by) == {"D0", "D1"}
    assert by["D0"]["delta"] == pytest.approx(-1.0)
    assert by["D1"]["delta"] == pytest.approx(0.0)
    # sorted by district_id for determinism
    assert [r["district"] for r in deltas] == ["D0", "D1"]


# ----------------------------- LOGO fold guard -----------------------------
def test_logo_guard_fails_on_a_single_district_that_degrades_beyond_the_fold_margin():
    deltas = [{"district": "A", "delta": 0.0}, {"district": "B", "delta": -0.10}]
    g = PG.logo_fold_guard(deltas, fold_margin=0.04)
    assert g["passes"] is False and g["worst_district"] == "B" and g["worst_delta"] == -0.10
    # a milder worst-case within the fold margin passes
    assert PG.logo_fold_guard([{"district": "A", "delta": -0.02}], fold_margin=0.04)["passes"] is True
    # empty sample -> nothing to guard (None, not a crash)
    assert PG.logo_fold_guard([], fold_margin=0.04)["passes"] is None


# ----------------------------- cluster bootstrap -----------------------------
def test_cluster_bootstrap_short_circuits_when_every_district_moved_identically():
    # A no-op change -> all deltas equal -> the bound IS that constant (no spurious CI, no scipy warning).
    out = PG.cluster_bootstrap_ci([0.0] * 6, seed=1)
    assert out["one_sided_lower"] == 0.0 and out["se"] == 0.0 and out["n_resamples"] == 0


def test_cluster_bootstrap_is_reproducible_for_a_fixed_seed():
    deltas = [-0.2, 0.0, 0.0, 0.1, -0.05, 0.0, 0.15, -0.1, 0.05, 0.0]
    a = PG.cluster_bootstrap_ci(deltas, seed=123, n_resamples=3000)
    b = PG.cluster_bootstrap_ci(deltas, seed=123, n_resamples=3000)
    c = PG.cluster_bootstrap_ci(deltas, seed=999, n_resamples=3000)
    assert a["one_sided_lower"] == b["one_sided_lower"]      # same seed -> identical bound, run to run
    assert a["ci_low"] == b["ci_low"] and a["ci_high"] == b["ci_high"]
    # a different seed draws a different resample -> the CI triple differs as a whole (a single coarse
    # quantile can coincide across seeds on discrete deltas, so compare the full CI, not just one bound).
    assert (a["ci_low"], a["ci_high"], a["one_sided_lower"]) != (c["ci_low"], c["ci_high"], c["one_sided_lower"])


def test_cluster_bootstrap_reports_but_does_not_crash_below_the_minimum_district_count():
    out = PG.cluster_bootstrap_ci([0.1, -0.1], seed=0)       # 2 districts < the min of 3
    assert out["one_sided_lower"] is None and out["n_resamples"] == 0


# ----------------------------- Wilcoxon + McNemar -----------------------------
def test_wilcoxon_is_none_on_all_zero_deltas_and_computes_otherwise():
    assert PG.wilcoxon_paired([0.0, 0.0, 0.0])["statistic"] is None
    w = PG.wilcoxon_paired([-0.2, -0.1, -0.15, -0.05, -0.3])
    assert w["n_nonzero"] == 5 and w["pvalue"] is not None


def test_mcnemar_uses_the_exact_binomial_when_discordant_pairs_are_few():
    # champion sends 3 nontargets that the challenger suppresses -> 3 discordant (< 25) -> exact.
    champ = _rows_uniform(1, 0, 3, nontarget_tier="A")
    chall = _rows_uniform(1, 0, 3, nontarget_tier="C")
    m = PG.mcnemar_decision_flips(champ, chall)
    assert m["exact"] is True and m["b"] == 3 and m["c"] == 0 and m["discordant"] == 3
    # identical decisions -> no discordant pairs -> a clean note, not a divide-by-zero
    same = PG.mcnemar_decision_flips(champ, champ)
    assert same["discordant"] == 0 and same["pvalue"] is None


def test_mcnemar_flips_the_exact_flag_above_the_discordant_threshold():
    champ = _rows_uniform(1, 0, 30, nontarget_tier="A")
    chall = _rows_uniform(1, 0, 30, nontarget_tier="C")     # 30 discordant >= 25 -> chi-square path
    assert PG.mcnemar_decision_flips(champ, chall)["exact"] is False


# ----------------------------- parametric TOST -----------------------------
def test_paired_tost_decides_a_constant_difference_directly():
    # every district improved by exactly +0.1 -> t-test undefined (zero variance); decided from the value.
    champ_vals, chall_vals = [0.8, 0.8, 0.8], [0.9, 0.9, 0.9]
    t = PG.paired_tost(champ_vals, chall_vals, margin=0.02)
    assert t["passes"] is True and "constant" in t["note"]


def test_paired_tost_runs_the_parametric_path_with_variance():
    champ_vals = [0.90, 0.85, 0.95, 0.88, 0.92]
    chall_vals = [0.91, 0.86, 0.94, 0.89, 0.93]             # tiny, non-inferior wobble around champion
    t = PG.paired_tost(champ_vals, chall_vals, margin=0.05)
    assert t["ni_pvalue"] is not None and t["passes"] is True


# ----------------------------- ICC + DEFF -----------------------------
def test_icc_deff_is_degenerate_when_every_target_reaches_the_same_bucket():
    # champion recall ~1.0 -> constant outcome -> ICC 0, DEFF 1, m̄ = targets/district.
    rows = _rows_uniform(5, 4, 1, target_tier="A")
    icc = PG.icc_deff(rows)
    assert icc["icc"] == 0.0 and icc["deff"] == 1.0 and icc["mbar"] == pytest.approx(4.0)


def test_icc_deff_computes_a_finite_clustered_icc_and_the_deff_definition_holds():
    # Within-district correlation with REAL within-cluster variance (not perfect separation, which makes
    # every cluster internally constant -> MSW=0 -> the ICC F-ratio is undefined). "good" districts reach
    # A+B on 4 of 5 targets, "bad" on 1 of 5 -> between-district tendency + within-district spread -> a
    # finite positive ICC in (0,1) via pingouin.
    rows = []
    for di in range(8):
        d = f"D{di}"
        n_hit = 4 if di % 2 == 0 else 1
        for j in range(5):
            rows.append((d, f"{d}-t{j}", "A" if j < n_hit else "D", True))
    icc = PG.icc_deff(rows)
    assert icc["icc"] is not None and 0.0 <= icc["icc"] <= 1.0
    assert icc["mbar"] == pytest.approx(5.0)
    # DEFF is the DEFINITION 1 + (m̄−1)·ICC — pin it against the reported ICC/m̄ exactly.
    assert icc["deff"] == pytest.approx(1.0 + (icc["mbar"] - 1.0) * icc["icc"], abs=1e-6)


def test_icc_deff_degrades_cleanly_with_too_few_targets():
    icc = PG.icc_deff([("D0", "t0", "A", True)])
    assert icc["icc"] is None and "too few" in icc["note"]


# ----------------------------- the composed verdict -----------------------------
def test_verdict_requires_a_positive_pre_declared_margin():
    champ = _rows_uniform(5, 3, 0)
    for bad in (None, 0, -0.01, True, "0.02"):
        with pytest.raises(ValueError):
            PG.promotion_verdict(champ, champ, margin=bad)


def test_verdict_promotes_a_non_inferior_challenger_that_only_improves_precision():
    # Challenger keeps every target at A (recall unchanged) but demotes false-positive nontargets A->C.
    champ = _rows_uniform(8, 3, 2, target_tier="A", nontarget_tier="A")
    chall = _rows_uniform(8, 3, 2, target_tier="A", nontarget_tier="C")
    v = PG.promotion_verdict(champ, chall, margin=0.02, seed=42, n_resamples=2000)
    assert v["promote"] is True
    assert v["non_inferiority"]["passes"] is True
    assert v["precision_report"]["mean_delta"] > 0          # the intended benefit is visible beside the proof
    assert v["decision_flips_mcnemar"]["b"] > 0             # the send->suppress flips were counted


def test_verdict_rejects_a_challenger_that_regresses_recall_in_some_districts():
    champ = _rows_uniform(10, 5, 0, target_tier="A")
    chall = []
    for di in range(10):
        d = f"D{di}"
        for j in range(5):
            drop = di < 4 and j == 0                        # 4 districts lose one target below A+B
            chall.append((d, f"{d}-t{j}", "D" if drop else "A", True))
    v = PG.promotion_verdict(champ, chall, margin=0.02, seed=7, n_resamples=3000)
    assert v["promote"] is False
    assert v["logo_guard"]["passes"] is False               # a single district degrading > fold_margin blocks it
    assert v["non_inferiority"]["passes"] is False           # and the aggregate bound sits below -Δ
    assert any("non-inferiority" in r or "LOGO" in r for r in v["reasons"])


def test_verdict_fold_margin_defaults_to_twice_the_aggregate_margin():
    champ = _rows_uniform(5, 3, 0)
    v = PG.promotion_verdict(champ, champ, margin=0.02, n_resamples=500)
    assert v["fold_margin"] == pytest.approx(0.04)


def test_verdict_is_reproducible_for_a_fixed_seed():
    champ = _rows_uniform(9, 4, 1, target_tier="A", nontarget_tier="A")
    chall = []
    rng = np.random.default_rng(0)
    for di in range(9):
        d = f"D{di}"
        for j in range(4):
            chall.append((d, f"{d}-t{j}", "A" if rng.random() > 0.15 else "B", True))
        chall.append((d, f"{d}-n0", "C", False))
    a = PG.promotion_verdict(champ, chall, margin=0.03, seed=5, n_resamples=2000)
    b = PG.promotion_verdict(champ, chall, margin=0.03, seed=5, n_resamples=2000)
    assert a["bootstrap"]["one_sided_lower"] == b["bootstrap"]["one_sided_lower"]
    assert a["promote"] == b["promote"]
