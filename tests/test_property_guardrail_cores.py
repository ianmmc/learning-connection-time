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


# ----------------------------- stage-8 cumulative merge (REQ-122, #232) -----------------------------
# PR #221 review: the merge core shipped with only incident-pinned example tests (the Brownsville
# case). These are the general invariants — any run count, any order, forced key collisions.
from infrastructure.acquisition.stage8_aggregate import aggregate as AGG  # noqa: E402

_fact = st.fixed_dictionaries({
    "extraction_id": st.integers(min_value=1, max_value=9),
    "band": st.sampled_from(["elementary", "middle", "high"]),
    "school": st.sampled_from(["a", "b", "c"]),
    "status": st.sampled_from(["accepted", "unresolved"]),
})


@given(facts=st.lists(_fact, max_size=30), data=st.data())
def test_merge_fact_runs_is_order_independent_and_never_evicts_an_accept(facts, data):
    accepted, unresolved = AGG.merge_fact_runs(facts)
    # order-independence: any permutation of the rows merges to the same cumulative truth
    perm = data.draw(st.permutations(facts))
    assert AGG.merge_fact_runs(list(perm)) == (accepted, unresolved)
    # the winners PARTITION the input keys — one winner per (band, school), no key on both sides
    keys_in = {(f["band"], f["school"]) for f in facts}
    keys_acc = [(f["band"], f["school"]) for f in accepted]
    keys_unr = [(f["band"], f["school"]) for f in unresolved]
    assert len(keys_acc) == len(set(keys_acc)) and len(keys_unr) == len(set(keys_unr))
    assert set(keys_acc) | set(keys_unr) == keys_in and not set(keys_acc) & set(keys_unr)
    # a key ever accepted in ANY run is accepted in the merge — no barren echo can evict it
    assert set(keys_acc) == {(f["band"], f["school"]) for f in facts if f["status"] == "accepted"}
    # tie-breaks: earliest accepted stands (fill gaps, never overwrite); pure-unresolved keys keep
    # the freshest diagnostic
    for f in accepted:
        assert f["extraction_id"] == min(
            x["extraction_id"] for x in facts if x["status"] == "accepted"
            and (x["band"], x["school"]) == (f["band"], f["school"]))
    for f in unresolved:
        assert f["extraction_id"] == max(
            x["extraction_id"] for x in facts
            if (x["band"], x["school"]) == (f["band"], f["school"]))


# ----------------------------- sent-files lineage (#231) -----------------------------
_rep = st.fixed_dictionaries({
    "rec_key": st.sampled_from(["r1", "r2", "r3"]),
    "file": st.one_of(st.none(), st.sampled_from(["a.txt", "b.txt", "c.png"])),
})


@given(reps=st.lists(_rep, max_size=15))
def test_sent_file_and_sent_files_are_two_views_of_one_send(reps):
    result = {"reps": reps}
    first, full = RQ._sent_file(result), RQ._sent_files(result)
    assert set(first) == set(full)                       # same rec_key coverage
    # first-seen semantics: exactly the first rep's file per rec_key, even a None
    seen: dict = {}
    for rep in reps:
        seen.setdefault(rep["rec_key"], rep.get("file"))
    assert first == seen
    # full-send semantics: sorted, deduped, no falsy — and COMPLETE (every sent file is recorded,
    # so the next round's history exclusion can never re-offer one)
    for k, files in full.items():
        assert files == sorted(set(files)) and all(files)
    for rep in reps:
        if rep["file"]:
            assert rep["file"] in full[rep["rec_key"]]
