"""REQ-120 / issue #211 — the anti-survivorship exploration quota's PURE control-law core.

These tests are the executable spec of the invariant: *the filter runs only as autonomously as its reject
audit is currently validating it; a lapse DEMOTES gate@5 to manual (never halts), with a deadband so it
can't flap.* They protect the design against regression before the live plumbing exists (harness/frontier
precedent). No DB, no cash — pure functions on synthetic inputs."""
import pytest

from infrastructure.acquisition.stage5_filter import exploration_audit as EA  # noqa: E402


# ----------------------------- rule of three (the sufficiency COUNT) -----------------------------
def test_rule_of_three_certifies_a_count_not_a_percentage():
    # ~300 zero-miss audited rejects ⇒ 95% confidence the reject FN-rate is < 1%. This is the number the
    # floor is set from; a percentage is deliberately NOT the binding bar.
    assert EA.rule_of_three_upper_bound(300) == pytest.approx(0.01)
    assert EA.rule_of_three_upper_bound(3) == pytest.approx(1.0)
    assert EA.rule_of_three_upper_bound(0) is None          # nothing observed -> no bound (not a crash)
    # monotonic: more audited rejects -> a tighter ceiling
    assert EA.rule_of_three_upper_bound(600) < EA.rule_of_three_upper_bound(300)
    assert EA.DEFAULT_FLOOR_N == 300


# ----------------------------- rejection quality (the honest reject-cohort signal) -----------------------------
def test_rejection_quality_measures_the_false_negative_rate_among_rejects():
    # 1 of 4 audited rejects was actually a target -> FN-rate 0.25, quality 0.75.
    m = EA.rejection_quality([True, False, False, False])
    assert m["n"] == 4 and m["false_neg"] == 1 and m["true_neg"] == 3
    assert m["false_negative_rate"] == 0.25 and m["rejection_quality"] == 0.75
    assert m["fnr_upper_bound_95"] is None                  # misses observed -> the observed rate stands


def test_rejection_quality_uses_the_rule_of_three_bound_when_zero_misses():
    # zero misses: the point estimate 0.0 understates risk, so report the rule-of-three ceiling instead.
    m = EA.rejection_quality([False] * 300)
    assert m["false_neg"] == 0 and m["false_negative_rate"] == 0.0
    assert m["fnr_upper_bound_95"] == pytest.approx(0.01)   # "<1% with 95% confidence", not "0%"


def test_rate_and_quality_are_exact_complements_after_rounding():
    # #216 review: independently rounding both fields let them sum to 0.999999 (e.g. 7/640). quality must be
    # the complement of the ROUNDED rate so the published pair always sums to exactly 1.0.
    m = EA.rejection_quality([True] * 7 + [False] * 633)     # n=640, the found counterexample
    assert m["false_negative_rate"] + m["rejection_quality"] == 1.0
    for n, fn in ((3, 1), (7, 2), (599, 13), (997, 41)):
        m = EA.rejection_quality([True] * fn + [False] * (n - fn))
        assert m["false_negative_rate"] + m["rejection_quality"] == 1.0


def test_rejection_quality_empty_cohort_is_all_none_not_a_crash():
    m = EA.rejection_quality([])
    assert m["n"] == 0 and m["false_neg"] == 0 and m["true_neg"] == 0   # #204: pin the empty-cohort counts
    assert m["false_negative_rate"] is None and m["rejection_quality"] is None
    assert m["fnr_upper_bound_95"] is None


def test_rejection_quality_is_reported_to_six_decimals():
    # #204: 1 of 3 audited rejects was a target -> fnr 1/3, quality 2/3, each rounded to SIX decimals —
    # the rounding grain the complementary-fields invariant (fnr + quality == 1.0) is built on.
    m = EA.rejection_quality([True, False, False])
    assert m["false_negative_rate"] == 0.333333
    assert m["rejection_quality"] == 0.666667


def test_default_sampler_rate_is_a_valid_probability():
    # #204: the p%-of-flow rate must be a real probability (a mutated 1.05 or -0.95 is not a flow rate).
    assert 0.0 < EA.DEFAULT_SAMPLE_RATE <= 1.0


# ----------------------------- the randomized draw (reproducible, unbiased, growth-stable) -----------------------------
def test_sample_is_reproducible_and_order_invariant():
    keys = [f"d{i}:rk{i}" for i in range(500)]
    a = EA.select_audit_sample(keys, p=0.05, seed="s1")
    b = EA.select_audit_sample(list(reversed(keys)), p=0.05, seed="s1")
    assert a == b                                           # same (keys,p,seed) -> identical, order-invariant
    assert a == sorted(a)                                   # deterministic sorted order


def test_sample_selection_depends_on_the_seed():
    keys = [f"rk{i}" for i in range(2000)]
    s1 = set(EA.select_audit_sample(keys, p=0.05, seed="s1"))
    s2 = set(EA.select_audit_sample(keys, p=0.05, seed="s2"))
    assert s1 != s2                                         # a different seed draws a different sample


def test_sample_is_growth_stable_a_keys_decision_never_flips_as_the_population_grows():
    # THE property that lets audit windows accumulate cleanly: adding new rejects must not change whether
    # an already-seen key was selected (else "already audited" churns and coverage is uncomputable).
    small = [f"rk{i}" for i in range(200)]
    big = small + [f"rk{i}" for i in range(200, 1000)]
    sel_small = set(EA.select_audit_sample(small, p=0.1, seed="s1"))
    sel_big = set(EA.select_audit_sample(big, p=0.1, seed="s1"))
    assert sel_small == {k for k in sel_big if k in set(small)}


def test_sample_rate_is_approximately_p_and_unbiased():
    keys = [f"rk{i}" for i in range(10000)]
    sel = EA.select_audit_sample(keys, p=0.05, seed="s1")
    assert 0.04 < len(sel) / len(keys) < 0.06              # ~5% of the flow, independent per key


def test_sample_draw_is_deterministic_and_uses_the_codebase_seeding_pattern():
    # builtin hash() is PYTHONHASHSEED-salted -> non-reproducible across processes, fatal for an audit that
    # must replay. The draw uses random.Random(string_seed) — the same deterministic (sha512-seeded) pattern
    # queue_batch.py already trusts for stratified_pick/select_schools (#216 review: one precedent, not two).
    import random
    assert EA._unit_interval("s", "k") == EA._unit_interval("s", "k")
    assert 0.0 <= EA._unit_interval("s", "k") < 1.0
    assert EA._unit_interval("s", "k") == random.Random("s:k").random()   # pinned to the shared pattern


# ----------------------------- the license state machine (deadband, demote-not-halt) -----------------------------
def test_auto_holds_while_coverage_meets_the_floor_and_demotes_below_it():
    assert EA.next_license_state("auto", 300, floor_n=300) == "auto"     # exactly AT the floor holds
    assert EA.next_license_state("auto", 299, floor_n=300) == "manual"   # below -> demote (revoke license)


def test_deadband_prevents_flapping_between_floor_and_promote():
    # a count in the (floor, promote) gap must NOT flip either state — the anti-flap invariant.
    floor, promote = 300, EA.promote_threshold(300)         # promote = ceil(1.2*300) = 360
    assert promote == 360
    for count in (300, 330, 359):
        assert EA.next_license_state("auto", count, floor_n=floor) == "auto"     # stays up
        assert EA.next_license_state("manual", count, floor_n=floor) == "manual"  # stays down (no premature re-promote)
    assert EA.next_license_state("manual", 360, floor_n=floor) == "auto"          # only clears at promote


def test_license_never_returns_halt_only_demotes():
    # losing the audit demotes autonomy one level; it must never return a pipeline-stopping state.
    for cur in ("auto", "manual"):
        for count in (0, 150, 300, 1000):
            assert EA.next_license_state(cur, count) in {"auto", "manual"}


def test_deadband_cannot_be_collapsed_or_inverted():
    # #216 review: promote_n <= floor_n collapses the deadband to a point (or inverts it) — a demoted gate
    # would re-promote at a coverage that immediately re-demotes, flapping auto↔manual every batch. Both
    # entry points must refuse: a factor <= 1 and an explicit promote_n <= floor_n.
    with pytest.raises(ValueError, match="factor"):
        EA.promote_threshold(300, factor=1.0)
    with pytest.raises(ValueError, match="factor"):
        EA.promote_threshold(300, factor=0.5)
    with pytest.raises(ValueError, match="promote_n"):
        EA.next_license_state("manual", 300, floor_n=300, promote_n=300)   # collapsed to a point
    with pytest.raises(ValueError, match="promote_n"):
        EA.next_license_state("manual", 250, floor_n=300, promote_n=200)   # inverted (promote below floor)


def test_unknown_gate_mode_strings_raise_not_silently_demote():
    # #216 review: a typo'd stored state ("Auto", None) must surface as a wiring bug — silently routing it
    # into the manual branch would mask a persistent caller bug as a conservative-looking demotion.
    with pytest.raises(ValueError, match="license state"):
        EA.next_license_state("Auto", 1000, floor_n=300)
    with pytest.raises(ValueError, match="license state"):
        EA.next_license_state(None, 1000, floor_n=300)
    with pytest.raises(ValueError, match="configured_mode"):
        EA.resolve_gate_mode("Manual", "auto", window_count=0)
    with pytest.raises(ValueError, match="configured_mode"):
        EA.resolve_gate_mode(None, "auto", window_count=0)


# ----------------------------- enforcement ships DORMANT (the --assert-floor pattern) -----------------------------
def test_configured_manual_is_inert_regardless_of_coverage():
    # census mode: the control law does nothing while gate@5 is configured manual — the demote-hook is a
    # no-op until auto exists. Even zero coverage cannot force anything.
    assert EA.resolve_gate_mode("manual", "manual", window_count=0) == "manual"
    assert EA.resolve_gate_mode("manual", "auto", window_count=100000) == "manual"


def test_configured_auto_is_live_and_gated_by_the_audit():
    # once gate@5 is set to auto the license is live: auto while the audit validates the filter, demoted
    # to manual the instant coverage lapses.
    assert EA.resolve_gate_mode("auto", "auto", window_count=300, floor_n=300) == "auto"
    assert EA.resolve_gate_mode("auto", "auto", window_count=299, floor_n=300) == "manual"
    assert EA.resolve_gate_mode("auto", "manual", window_count=360, floor_n=300) == "auto"   # re-promote at deadband
