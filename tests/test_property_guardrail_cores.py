"""#203 / epic #200 — property-based (hypothesis) tests of the pure guardrail cores.

Complements the example-based suites with invariants that must hold across RANDOM inputs — the properties
the PR #220 review had to reason about by hand (complementary rounding, order-independent fingerprints,
bounded ratios, growth-stable sampling). All pure: no DB, no cash."""
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from infrastructure.acquisition.stage5_filter import config_artifact as CA  # noqa: E402
from infrastructure.acquisition.stage5_filter import exploration_audit as EA  # noqa: E402
from infrastructure.acquisition.stage5_filter import promotion_gate as PG  # noqa: E402
from infrastructure.acquisition.stage7_extract import requests as RQ  # noqa: E402  (request-loop pure core)

_TIERS = ("A", "B", "C", "D")


# ----------------------------- request-loop directives (pure ranking core) -----------------------------
_alt = st.fixed_dictionaries({
    "kind": st.sampled_from(["text", "image", None, "other"]),
    "n_times": st.one_of(st.none(), st.integers(min_value=0, max_value=200)),
    "file": st.text(max_size=10),
})


def _alt_tier(a):
    if a.get("kind") == "text" and (a.get("n_times") or 0) > 0:
        return 0                                          # yield-bearing text — the cheapest high-yield retry
    return 1 if a.get("kind") == "image" else 2           # vision escalation, then zero-yield text (last)


@given(alts=st.lists(_alt, max_size=20))
def test_rank_alternates_is_a_stable_permutation_respecting_the_escalation_ladder(alts):
    ranked = RQ.rank_alternates(alts)
    assert sorted(ranked, key=repr) == sorted(alts, key=repr)          # a permutation (same multiset)
    assert RQ.rank_alternates(ranked) == ranked                        # idempotent (already best-first)
    tiers = [_alt_tier(a) for a in ranked]
    assert tiers == sorted(tiers)                                      # ladder: text-yield < image < zero-text
    yields = [(a.get("n_times") or 0) for a in ranked if _alt_tier(a) == 0]
    assert yields == sorted(yields, reverse=True)                      # within the text tier, highest yield first


# ----------------------------- exploration_audit -----------------------------
@given(labels=st.lists(st.booleans(), min_size=1, max_size=2000))
def test_rejection_quality_fields_are_exact_complements(labels):
    # The review-hardened property: false_negative_rate + rejection_quality == 1.0 EXACTLY (the two are
    # complements of the same ROUNDED rate, so they can never drift to 0.999999).
    m = EA.rejection_quality(labels)
    assert m["false_negative_rate"] + m["rejection_quality"] == 1.0
    assert 0.0 <= m["false_negative_rate"] <= 1.0


@given(n=st.integers(min_value=1, max_value=10_000))
def test_rule_of_three_is_three_over_n_and_monotone(n):
    b = EA.rule_of_three_upper_bound(n)
    assert b == pytest.approx(3.0 / n)
    assert EA.rule_of_three_upper_bound(n + 1) < b        # tighter ceiling with more clean audits


@given(keys=st.lists(st.text(min_size=1, max_size=8), unique=True, max_size=200),
       extra=st.lists(st.text(min_size=1, max_size=8), unique=True, max_size=200),
       p=st.floats(min_value=0.0, max_value=1.0), seed=st.text(max_size=12))
def test_audit_sample_is_deterministic_and_growth_stable(keys, extra, p, seed):
    fresh_extra = [k for k in extra if k not in set(keys)]
    sub = EA.select_audit_sample(keys, p=p, seed=seed)
    assert sub == EA.select_audit_sample(keys, p=p, seed=seed)          # deterministic
    sup = EA.select_audit_sample(keys + fresh_extra, p=p, seed=seed)
    # growth-stable: a key already in the population keeps its exact selection decision as it grows —
    # the property that lets audit windows accumulate cleanly (a key never flips in or out).
    assert set(sub) == set(sup) & set(keys)


@given(window=st.integers(min_value=0, max_value=2000), floor=st.integers(min_value=1, max_value=500))
def test_license_transition_respects_the_deadband(window, floor):
    promote_n = EA.promote_threshold(floor)
    assert promote_n > floor                                            # the hysteresis gap always exists
    # in the deadband (floor <= window < promote_n): auto stays auto, manual stays manual — no flapping.
    if floor <= window < promote_n:
        assert EA.next_license_state("auto", window, floor_n=floor) == "auto"
        assert EA.next_license_state("manual", window, floor_n=floor) == "manual"


# ----------------------------- config_artifact -----------------------------
_json_scalars = st.one_of(st.integers(), st.booleans(), st.text(max_size=12), st.none())
_knob_docs = st.dictionaries(st.text(min_size=1, max_size=8), _json_scalars, max_size=6)


@given(dp=st.dictionaries(st.text(min_size=1, max_size=6), _json_scalars, max_size=6),
       knobs=st.dictionaries(st.text(min_size=1, max_size=6), _knob_docs, max_size=4),
       gt=st.text(max_size=12))
def test_surface_fingerprint_is_key_order_independent_and_stable(dp, knobs, gt):
    fp = CA.surface_fingerprint(dp, knobs, gt)
    assert fp == CA.surface_fingerprint(dp, knobs, gt)                  # stable
    dp_rev = dict(reversed(list(dp.items())))
    knobs_rev = dict(reversed(list(knobs.items())))
    assert CA.surface_fingerprint(dp_rev, knobs_rev, gt) == fp          # canonical_json sorts keys


@given(dp=st.dictionaries(st.text(min_size=1, max_size=6), _json_scalars, max_size=6),
       knobs=st.dictionaries(st.text(min_size=1, max_size=6), _knob_docs, max_size=4),
       gt=st.text(max_size=12), semver=st.text(max_size=8))
def test_classify_change_is_reflexive(dp, knobs, gt, semver):
    a = CA.build_artifact(dp, knobs, gt, semver=semver, created_at="x")
    assert CA.classify_change(a, a) == "none"                          # identical surface -> never a change


@given(major=st.integers(0, 50), minor=st.integers(0, 50), patch=st.integers(0, 50))
def test_bump_semver_zeros_lower_components(major, minor, patch):
    s = f"{major}.{minor}.{patch}"
    assert CA.bump_semver(s, "patch") == f"{major}.{minor}.{patch + 1}"
    assert CA.bump_semver(s, "minor") == f"{major}.{minor + 1}.0"       # minor zeros patch
    assert CA.bump_semver(s, "major") == f"{major + 1}.0.0"             # major zeros minor + patch


# ----------------------------- promotion_gate -----------------------------
@st.composite
def _scored_rows(draw, min_size=1, max_size=30):
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    dists = draw(st.lists(st.sampled_from(["D0", "D1", "D2", "D3", "D4"]), min_size=n, max_size=n))
    tiers = draw(st.lists(st.sampled_from(_TIERS), min_size=n, max_size=n))
    tgts = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    return [(dists[i], f"r{i}", tiers[i], tgts[i]) for i in range(n)]


@given(rows=_scored_rows())
def test_per_district_metric_is_none_or_a_probability(rows):
    for metric in ("recall", "precision"):
        for v in PG.per_district_metric(rows, positive=PG.POSITIVE_AB, metric=metric).values():
            assert v is None or (0.0 <= v <= 1.0)


@given(rows=_scored_rows())
def test_identical_config_has_zero_deltas(rows):
    # A config scored against itself moves no district — the delta sample is all zeros.
    deltas = PG.paired_district_deltas(rows, rows, positive=PG.POSITIVE_AB, metric="recall")
    assert all(d["delta"] == 0.0 for d in deltas)
    assert all(-1.0 <= d["delta"] <= 1.0 for d in deltas)


@settings(max_examples=50, deadline=None)
@given(rows=_scored_rows(min_size=6, max_size=40), margin=st.floats(min_value=0.001, max_value=0.2))
def test_a_config_is_non_inferior_to_itself(rows, margin):
    # Self-comparison is the definitional floor of the gate: it must never REJECT an unchanged config,
    # at any pre-declared margin.
    v = PG.promotion_verdict(rows, rows, margin=margin, seed=0, n_resamples=500)
    if v["n_districts"] >= PG._MIN_DISTRICTS_FOR_BOOTSTRAP:
        assert v["promote"] is True
        assert v["non_inferiority"]["lower_bound"] == 0.0
