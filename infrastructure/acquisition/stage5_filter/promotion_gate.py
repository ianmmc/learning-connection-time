#!/usr/bin/env python3
"""Group-aware non-inferiority promotion gate — the PURE stats core (#212, epic #209 Phase 2).

**Why this exists.** The moment a Stage-5 config change becomes even semi-automated, "the challenger
looks better" is no longer a safe reason to promote it. Two structural facts make the naive test
invalid at our scale (n≈440 labeled records over ~90 districts):

  * **Clustering.** Records inside one district share CMS chrome/templates, so they are NOT independent.
    The Kish design effect DEFF = 1 + (m̄−1)·ICC ≈ 2.4 (m̄≈4.9 targets/district, ICC~0.3) means a naive
    paired t-test understates variance ~2.4× and its SEs are off by √2.4 — it manufactures false wins.
  * **Wrong question.** At this n a challenger can almost never be *proven better*. The decision we can
    actually make is **"provably NOT worse within a pre-declared margin Δ"** — non-inferiority, gated on
    the A+B recall we defend (no target silently dropped below review), one-sided in the harm direction.

So the gate resamples **whole districts** (the unit of exchangeability), reads cluster-honest variance,
and promotes only if the challenger's district-level A+B-recall delta stays above −Δ. Δ is pre-declared
on domain grounds and this module **refuses to run without it** (a non-significant p-value is insufficient
power, never evidence of equivalence — the margin must be set *before* seeing the challenger).

**No hand-rolled statistical estimators** (Ian, 2026-07-10): every test comes from a proven library —
`scipy.stats` (Wilcoxon + the seeded cluster bootstrap), `statsmodels` (TOST, McNemar exact), `pingouin`
(ICC). The only arithmetic written here is the DEFF *definition* (1+(m̄−1)·ICC) and per-district
precision/recall (TP/(TP+FP), TP/(TP+FN)) — definitions, not estimators.

**The layered gate (FINDINGS-AND-DECISIONS §2 order), composed by `promotion_verdict`:**
  1. LOGO fold guard — no single held-out district degrades more than `fold_margin` (a district artifact
     that only helps one place is not a real win).
  2. Wilcoxon signed-rank on the per-district deltas (nonparametric paired difference — reported).
  3. McNemar exact on the send/suppress decision-flip concordance (the decision-mix shift — reported).
  4. Cluster ("cases") bootstrap over district deltas → the cluster-honest one-sided lower bound.
  5. TOST non-inferiority read (parametric corroboration — reported).
  6. ICC + DEFF alongside every verdict, so the reader sees the honest variance.
`promote` is gated on (1) AND (4): the LOGO guard holds AND the bootstrap lower bound > −Δ.

This module is PURE and side-effect-free (no DB, no cash, no config writes) so the invariant is locked in
code and unit-tested before any live wiring — the `harness.py`/`exploration_audit.py` precedent. It
consumes the per-district scored rows `frontier._retier(records, params)` already produces:
`[(district_id, rec_key, tier, is_target)]`. Design authority: STAGE5_FILTER_DESIGN §5c (to be written);
issue #212; production-quality-control-research/FINDINGS-AND-DECISIONS.md §2.
"""
import math

import numpy as np
from scipy.stats import bootstrap, wilcoxon
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.weightstats import ttost_paired

# The tier sets that count as a positive prediction. A+B = "reaches human review" (the recall the floor
# defends — harness.FLOOR_TIER); A alone = the auto-send / precision bucket.
POSITIVE_AB = frozenset({"A", "B"})
POSITIVE_A = frozenset({"A"})

DEFAULT_ALPHA = 0.05             # one-sided NI level → the (1−α) lower confidence bound
DEFAULT_N_RESAMPLES = 10000      # cluster-bootstrap replicates
_MCNEMAR_EXACT_MAX_DISCORDANT = 25   # b+c < this → exact binomial (chi-square approximation unreliable)
_MIN_DISTRICTS_FOR_BOOTSTRAP = 3     # below this the cluster bootstrap is meaningless (report, don't crash)


def _r(x, p=6):
    """Round floats for stable, comparable output; pass through None/ints unchanged (harness._r style)."""
    return round(x, p) if isinstance(x, float) else x


# ----------------------------- per-district metrics (definitions, not estimators) -----------------------------
def per_district_metric(rows, *, positive, metric):
    """{district_id: value|None} for one config's scored rows.

    rows: iterable of (district_id, rec_key, tier, is_target). `positive` is the tier set counted as a
    positive prediction; `metric` is "recall" (TP/(TP+FN)) or "precision" (TP/(TP+FP)). None where the
    denominator is 0 (a district with no targets has undefined recall; with no positive predictions,
    undefined precision) — None is EXCLUDED downstream, never coerced to 0 (issue #63's lesson: a missing
    ratio is not a 0.0 ratio)."""
    if metric not in ("recall", "precision"):
        raise ValueError(f"metric must be 'recall' or 'precision' (got {metric!r})")
    per = {}
    for district_id, _rk, tier, is_target in rows:
        d = per.setdefault(district_id, {"tp": 0, "fp": 0, "fn": 0})
        pred_pos = tier in positive
        if pred_pos and is_target:
            d["tp"] += 1
        elif pred_pos and not is_target:
            d["fp"] += 1
        elif not pred_pos and is_target:
            d["fn"] += 1
    out = {}
    for district_id, c in per.items():
        denom = c["tp"] + (c["fn"] if metric == "recall" else c["fp"])
        out[district_id] = (c["tp"] / denom) if denom else None
    return out


def paired_district_deltas(champion_rows, challenger_rows, *, positive, metric):
    """The paired sample the whole gate rests on: [{district, champion, challenger, delta}, ...] over the
    districts where BOTH configs have a defined metric. delta = challenger − champion (positive = the
    challenger improved that district, negative = it degraded it). Sorted by district_id for determinism.

    Because both configs score the SAME records (only the tiering differs, never the ground-truth), a
    district's recall denominator (#targets) is identical across configs — the delta can't be an artifact
    of a shifting denominator (it is for precision, hence the both-defined filter)."""
    champ = per_district_metric(champion_rows, positive=positive, metric=metric)
    chall = per_district_metric(challenger_rows, positive=positive, metric=metric)
    out = []
    for district_id in sorted(champ.keys() & chall.keys()):
        cv, hv = champ[district_id], chall[district_id]
        if cv is None or hv is None:
            continue
        out.append({"district": district_id, "champion": _r(cv), "challenger": _r(hv),
                    "delta": _r(hv - cv)})
    return out


# ----------------------------- ICC + design effect (the honest-variance report) -----------------------------
def icc_deff(rows, *, positive=POSITIVE_AB):
    """ICC + Kish design effect for the A+B-recall estimate, clustered by district. The per-target-record
    binary outcome is 'did this target reach A+B (tier in `positive`)'; the cluster is the district; m̄ is
    the mean targets/district. ICC comes from `pingouin.intraclass_corr` (ICC1, one-way random effects —
    the cluster ICC, correlation of within-district outcomes); DEFF = 1 + (m̄−1)·ICC is the definition.

    Returns {icc, deff, mbar, n_targets, n_districts, note}. Degrades to icc/deff=None (never raises) when
    the outcome is degenerate — the common case here, since A+B recall ≈ 0.996 means nearly every target
    reaches A+B, so between/within variance is near-zero and the ICC is low-information (flagged in `note`).
    A report, not a gate input: the cluster bootstrap handles clustering directly by resampling districts."""
    import pandas as pd  # local: pandas is only needed for the ICC report path, not the gate decision
    import pingouin as pg

    targets = [(d, 1 if tier in positive else 0) for d, _rk, tier, is_target in rows if is_target]
    n_targets = len(targets)
    districts = {d for d, _o in targets}
    n_districts = len(districts)
    mbar = (n_targets / n_districts) if n_districts else None
    base = {"icc": None, "deff": None, "mbar": _r(mbar), "n_targets": n_targets,
            "n_districts": n_districts, "note": None}
    if n_districts < 2 or n_targets < 3:
        base["note"] = "too few targets/districts for an ICC"
        return base
    if len({o for _d, o in targets}) < 2:
        # every target reached the same tier bucket → zero outcome variance → ICC is 0 by construction.
        base["icc"], base["note"] = 0.0, "outcome is constant (all targets same side) → ICC=0, DEFF=1"
        base["deff"] = 1.0
        return base
    # pingouin.intraclass_corr wants long format (targets=cluster, raters=within-cluster index, ratings).
    # Unbalanced clusters are fine — we index each district's records 0..k-1 as pseudo-"raters".
    recs = []
    for d in sorted(districts):
        for i, o in enumerate([o for dd, o in targets if dd == d]):
            recs.append({"cluster": str(d), "within": i, "outcome": o})
    df = pd.DataFrame(recs)
    try:
        # A degenerate cluster structure (e.g. every cluster internally constant) makes pingouin's F-ratios
        # divide by a zero within-cluster MS; silence that numeric noise — the non-finite result is caught
        # right below and reported as unavailable, not surfaced as a warning.
        with np.errstate(divide="ignore", invalid="ignore"):
            icc_tbl = pg.intraclass_corr(data=df, targets="cluster", raters="within", ratings="outcome",
                                         nan_policy="omit")
        # ICC1 = one-way random, single measures = the cluster ICC we want. The Type label differs across
        # pingouin versions ("ICC1" in <0.6, "ICC(1,1)" in 0.6.x) — match either, don't pin one string.
        icc1 = icc_tbl.loc[icc_tbl["Type"].isin(["ICC1", "ICC(1,1)"]), "ICC"]
        icc = float(icc1.iloc[0]) if len(icc1) else None
    except Exception as e:                      # unbalanced/degenerate pivots can raise inside pingouin
        base["note"] = f"ICC estimation failed ({type(e).__name__}); reported as unavailable"
        return base
    if icc is None or not math.isfinite(icc):
        base["note"] = "ICC non-finite; reported as unavailable"
        return base
    icc = max(0.0, icc)                          # a small negative ICC is an estimation artifact → clamp to 0
    icc_r = _r(icc)
    base["icc"] = icc_r
    # DEFF from the REPORTED (rounded) ICC, so the two published fields are mutually consistent — a reader
    # can recompute 1+(m̄−1)·ICC from the printed values and get exactly the printed DEFF (cf. exploration_audit).
    base["deff"] = _r(1.0 + (mbar - 1.0) * icc_r)
    return base


# ----------------------------- resampling + paired tests (all library-backed) -----------------------------
def cluster_bootstrap_ci(deltas, *, alpha=DEFAULT_ALPHA, n_resamples=DEFAULT_N_RESAMPLES, seed=0):
    """Cluster ('cases') bootstrap over the per-district deltas — the district is the resampling unit, so
    resampling the list of per-district deltas IS the cluster bootstrap (each district contributes one
    equally-weighted delta; within-district correlation is already collapsed into that summary). Uses
    `scipy.stats.bootstrap` with an explicitly seeded `np.random.default_rng(seed)` — reproducible across
    processes forever (the property this codebase never lets a random draw lose; cf. exploration_audit).

    Returns {mean, se, ci_low, ci_high (two-sided 1−2α), one_sided_lower (the NI bound, the α-quantile of
    the bootstrap mean distribution = a one-sided (1−α) lower confidence bound), n_districts, n_resamples}.
    `one_sided_lower=None` (never a crash) when there are too few districts to bootstrap."""
    deltas = [float(x) for x in deltas]
    n = len(deltas)
    mean = _r(sum(deltas) / n) if n else None
    if n < _MIN_DISTRICTS_FOR_BOOTSTRAP:
        return {"mean": mean, "se": None, "ci_low": None, "ci_high": None, "one_sided_lower": None,
                "n_districts": n, "n_resamples": 0,
                "note": f"fewer than {_MIN_DISTRICTS_FOR_BOOTSTRAP} districts — bootstrap not run"}
    arr = np.asarray(deltas, dtype=float)
    if float(np.ptp(arr)) == 0.0:
        # every district moved identically (e.g. a no-op change) → degenerate distribution; the bound IS
        # that constant. Short-circuit so scipy doesn't warn on a zero-variance resample.
        c = float(arr[0])
        return {"mean": _r(c), "se": 0.0, "ci_low": _r(c), "ci_high": _r(c), "one_sided_lower": _r(c),
                "n_districts": n, "n_resamples": 0, "note": "all district deltas identical"}
    rng = np.random.default_rng(seed)
    res = bootstrap((arr,), np.mean, n_resamples=n_resamples, confidence_level=1 - 2 * alpha,
                    method="percentile", rng=rng)
    one_sided_lower = float(np.quantile(res.bootstrap_distribution, alpha))
    return {"mean": mean, "se": _r(float(res.standard_error)),
            "ci_low": _r(float(res.confidence_interval.low)),
            "ci_high": _r(float(res.confidence_interval.high)),
            "one_sided_lower": _r(one_sided_lower),
            "n_districts": n, "n_resamples": int(n_resamples), "note": None}


def wilcoxon_paired(deltas):
    """Wilcoxon signed-rank on the per-district deltas (nonparametric paired difference vs. zero) — robust
    to the skew/heavy tails of per-district recall deltas. `scipy.stats.wilcoxon`. Reported, not gated (NI
    does not require a significant difference). {statistic, pvalue, n_nonzero, note}; None when every delta
    is zero (no signed ranks to compute — a genuine no-op change, not an error)."""
    nz = [d for d in deltas if d != 0]
    if not nz:
        return {"statistic": None, "pvalue": None, "n_nonzero": 0, "note": "all deltas zero"}
    try:
        stat, p = wilcoxon(nz)                  # one-sample form: signed ranks of the differences
    except ValueError as e:
        return {"statistic": None, "pvalue": None, "n_nonzero": len(nz), "note": str(e)}
    return {"statistic": _r(float(stat)), "pvalue": _r(float(p)), "n_nonzero": len(nz), "note": None}


def mcnemar_decision_flips(champion_rows, challenger_rows, *, send_tiers=POSITIVE_AB):
    """McNemar exact test on the per-record send/suppress decision concordance — does the challenger shift
    the reaches-review (tier in `send_tiers`) rate? Builds the 2×2 of (champion sends?) × (challenger
    sends?) over records present in both, and calls `statsmodels...mcnemar` with the EXACT binomial when
    the discordant count b+c < 25 (the chi-square approximation is unreliable there). Reported, not gated.
    {b, c, discordant, exact, statistic, pvalue, note}."""
    champ = {rk: (tier in send_tiers) for _d, rk, tier, _g in champion_rows}
    chall = {rk: (tier in send_tiers) for _d, rk, tier, _g in challenger_rows}
    a = b = c = d = 0
    for rk in champ.keys() & chall.keys():
        cs, hs = champ[rk], chall[rk]
        if cs and hs:
            a += 1
        elif cs and not hs:
            b += 1                              # champion sent, challenger suppressed
        elif not cs and hs:
            c += 1                              # champion suppressed, challenger sent
        else:
            d += 1
    discordant = b + c
    if discordant == 0:
        return {"b": b, "c": c, "discordant": 0, "exact": None, "statistic": None, "pvalue": None,
                "note": "no discordant records — identical send/suppress decisions"}
    exact = discordant < _MCNEMAR_EXACT_MAX_DISCORDANT
    res = mcnemar([[a, b], [c, d]], exact=exact, correction=not exact)
    return {"b": b, "c": c, "discordant": discordant, "exact": exact,
            "statistic": _r(float(res.statistic)), "pvalue": _r(float(res.pvalue)), "note": None}


def paired_tost(champion_vals, challenger_vals, *, margin, alpha=DEFAULT_ALPHA):
    """Parametric non-inferiority read via `statsmodels...ttost_paired` — corroborates the (load-bearing)
    cluster-bootstrap bound with a paired-t equivalence test. Tests the challenger−champion difference
    against the lower bound −margin (the upper bound is set wide so only the harm-side one-sided test binds
    — a big improvement must not fail an NI check). Returns {ni_pvalue, passes, note}; `passes` is the
    one-sided lower test at `alpha`. Reported; the gate decision rests on the cluster bootstrap, which is
    cluster-honest where this parametric test assumes iid districts."""
    x1 = np.asarray([float(v) for v in challenger_vals], dtype=float)
    x2 = np.asarray([float(v) for v in champion_vals], dtype=float)
    if len(x1) != len(x2) or len(x1) < 2:
        return {"ni_pvalue": None, "passes": None, "note": "need ≥2 paired districts"}
    if float(np.ptp(x1 - x2)) == 0.0:
        # constant paired difference → t-test undefined (zero variance). Decide from the constant directly.
        diff = float((x1 - x2)[0])
        return {"ni_pvalue": None, "passes": diff > -margin,
                "note": "constant paired difference; decided directly from the value"}
    try:
        # ttost_paired(x1, x2, low, upp) → (pvalue, res_low, res_upp); res_low tests H0: mean(x1−x2) <= low.
        _p, res_low, _res_upp = ttost_paired(x1, x2, -margin, abs(margin) * 1e6 + 1.0)
        ni_p = float(res_low[1])
    except Exception as e:
        return {"ni_pvalue": None, "passes": None, "note": f"{type(e).__name__}: {e}"}
    return {"ni_pvalue": _r(ni_p), "passes": ni_p < alpha, "note": None}


def logo_fold_guard(deltas, *, fold_margin):
    """LOGO-CV guardrail: with GLOBAL thresholds, leave-one-district-out CV reduces to 'no single held-out
    district degrades more than `fold_margin`' — a config that wins only by leaning on one district's
    artifacts is rejected here even if the aggregate looks fine. Returns {passes, worst_delta,
    worst_district, fold_margin}. `passes=None` on an empty sample (nothing to guard)."""
    if not deltas:
        return {"passes": None, "worst_delta": None, "worst_district": None, "fold_margin": fold_margin}
    worst = min(deltas, key=lambda r: r["delta"])
    return {"passes": worst["delta"] >= -fold_margin, "worst_delta": worst["delta"],
            "worst_district": worst["district"], "fold_margin": fold_margin}


# ----------------------------- the composed verdict -----------------------------
def promotion_verdict(champion_rows, challenger_rows, *, margin, fold_margin=None,
                      alpha=DEFAULT_ALPHA, seed=0, n_resamples=DEFAULT_N_RESAMPLES,
                      positive=POSITIVE_AB, metric="recall"):
    """The layered group-aware non-inferiority gate. `margin` (Δ) is the pre-declared, cluster-adjusted
    non-inferiority margin on the district-level metric (e.g. 0.02 = tolerate ≤2 pp district A+B-recall
    degradation) and is REQUIRED — this function raises without a positive Δ, because 'set Δ before seeing
    the challenger' is the discipline that makes non-inferiority meaningful (a p-value tuned after the fact
    is reverse-engineering, not evidence). `fold_margin` (defaults to 2·Δ — one district is noisier than
    the aggregate) bounds the worst single held-out district.

    `promote` is True iff the LOGO fold guard holds AND the cluster-bootstrap one-sided lower bound on the
    mean district delta exceeds −Δ. Wilcoxon, McNemar, the parametric TOST, and ICC/DEFF are computed and
    returned for the record (the honest-variance context) but do not gate. The tier-A precision delta (the
    intended *improvement*) is reported so a reader sees the benefit beside the non-inferiority proof."""
    if not isinstance(margin, (int, float)) or isinstance(margin, bool) or margin <= 0:
        raise ValueError(f"margin (Δ) must be a positive pre-declared number (got {margin!r}) — "
                         "non-inferiority requires a domain-set margin, not a p-value threshold")
    fold_margin = 2.0 * margin if fold_margin is None else fold_margin
    if fold_margin <= 0:
        raise ValueError(f"fold_margin must be positive (got {fold_margin!r})")

    deltas = paired_district_deltas(champion_rows, challenger_rows, positive=positive, metric=metric)
    delta_vals = [r["delta"] for r in deltas]

    logo = logo_fold_guard(deltas, fold_margin=fold_margin)
    boot = cluster_bootstrap_ci(delta_vals, alpha=alpha, n_resamples=n_resamples, seed=seed)
    wilcox = wilcoxon_paired(delta_vals)
    flips = mcnemar_decision_flips(champion_rows, challenger_rows, send_tiers=positive)
    tost = paired_tost([r["champion"] for r in deltas], [r["challenger"] for r in deltas],
                       margin=margin, alpha=alpha)
    icc = icc_deff(champion_rows, positive=positive)

    # The intended benefit, reported beside the non-inferiority proof (tier-A precision = the auto-send bucket).
    prec_deltas = paired_district_deltas(champion_rows, challenger_rows, positive=POSITIVE_A,
                                         metric="precision")
    prec_vals = [r["delta"] for r in prec_deltas]
    precision_report = {"n_districts": len(prec_vals),
                        "mean_delta": _r(sum(prec_vals) / len(prec_vals)) if prec_vals else None}

    ni_lower = boot["one_sided_lower"]
    ni_pass = ni_lower is not None and ni_lower > -margin
    logo_pass = logo["passes"] is True
    promote = bool(logo_pass and ni_pass)

    reasons = []
    if not deltas:
        reasons.append("no districts with a defined metric under both configs")
    if logo["passes"] is False:
        reasons.append(f"LOGO fold guard: district {logo['worst_district']} degrades "
                       f"{logo['worst_delta']} < −{fold_margin}")
    if ni_lower is None:
        reasons.append(boot.get("note") or "non-inferiority bound unavailable")
    elif not ni_pass:
        reasons.append(f"non-inferiority: bootstrap lower bound {ni_lower} ≤ −Δ (−{margin})")
    if promote:
        reasons.append(f"non-inferior within Δ={margin}: lower bound {ni_lower} > −{margin}; "
                       f"worst district {logo['worst_delta']} ≥ −{fold_margin}")

    return {
        "promote": promote,
        "margin": margin,
        "fold_margin": fold_margin,
        "metric": metric,
        "positive_tier": "A+B" if positive == POSITIVE_AB else ("A" if positive == POSITIVE_A else sorted(positive)),
        "n_districts": len(deltas),
        "deltas": deltas,
        "logo_guard": logo,
        "bootstrap": boot,
        "non_inferiority": {"lower_bound": ni_lower, "passes": ni_pass, "method": "cluster_bootstrap"},
        "wilcoxon": wilcox,
        "decision_flips_mcnemar": flips,
        "tost_parametric": tost,
        "icc_deff": icc,
        "precision_report": precision_report,
        "reasons": reasons,
    }
