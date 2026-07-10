#!/usr/bin/env python3
"""Anti-survivorship exploration quota — the PURE control-law core (REQ-120, issue #211).

The Stage-5 filter's autonomy is *licensed by a live human signal*: it may run as autonomously as its
reject audit is currently validating it, and the moment that validation lapses the license is revoked —
gate@5 auto DEMOTES to manual (census mode), it does NOT halt the pipeline. This module is the pure,
side-effect-free heart of that control law — no DB, no cash, no live wiring — so the invariant is locked
in code and unit-tested before any of the live plumbing exists (the harness/frontier precedent). The live
half (querying the reject population, presenting the randomized audit queue in the console, hooking the
demote decision onto the gate@5 auto toggle) is the full #211 build; its enforcement stays dormant until
gate@5 is actually set to auto.

Design authority: STAGE5_FILTER_DESIGN_2026-06.md §5a; PIPELINE_GOVERNANCE_AND_STATE_2026-06.md §11b;
production-quality-control-research/FINDINGS-AND-DECISIONS.md §0/§1.

Four pure pieces, each killing a named failure mode:
  - rule_of_three_upper_bound(n)      — the count that makes the audit statistically sufficient
  - rejection_quality(labels)         — the honest reject-cohort signal (FN-rate among audited rejects)
  - select_audit_sample(keys, p, seed)— reproducible, unbiased, GROWTH-STABLE random selection
  - resolve_gate_mode(...)            — the revocable license: dormant-until-auto, demote-not-halt, deadband
"""
import hashlib
import math

# The audit's binding sufficiency bar is a COUNT, not a percentage (a % is too thin on small streams and
# re-imports the manual-inspection-at-100k-scale problem on big ones — commandment 2). Rule of three:
# ~300 randomly-audited rejects with ZERO misses ⇒ 95% confidence the reject false-negative rate is < 1%.
DEFAULT_FLOOR_N = 300
# The p%-of-flow sampler sets the FLOW that feeds the count; the count (FLOOR_N) sets sufficiency.
DEFAULT_SAMPLE_RATE = 0.05
# Deadband: re-promote to auto only once coverage clears PROMOTE_FACTOR·floor, so a count hovering at the
# floor cannot flap the gate auto↔manual every batch.
PROMOTE_FACTOR = 1.2


def rule_of_three_upper_bound(n):
    """95% upper bound on an event rate given 0 events observed in n independent trials (≈ 3/n). This is
    the number that certifies the audit: to bound the reject false-negative rate below r, you need ~3/r
    zero-miss audited rejects. None for n <= 0 (nothing observed ⇒ no bound)."""
    if n <= 0:
        return None
    return 3.0 / n


def promote_threshold(floor_n, factor=PROMOTE_FACTOR):
    """The upper edge of the deadband — coverage must reach this (not merely the floor) to RE-promote a
    demoted gate back to auto. ceil so it is always strictly above floor_n for any factor > 1."""
    return math.ceil(floor_n * factor)


def rejection_quality(labels):
    """The honest reject-cohort signal from a batch of AUDITED rejects. `labels` is an iterable of bool:
    True  = the human said this rejected page WAS a target  → a filter FALSE NEGATIVE (wrongly rejected)
    False = the human agreed it was a non-target            → a filter TRUE NEGATIVE (correctly rejected)

    Returns counts, the false-negative RATE among rejects (FN / (FN+TN) — what fraction of the reject pile
    was actually good), its complement `rejection_quality` (correctly-rejected fraction = 1 − FNR, what the
    research loosely calls reject-cohort TNR), and — when zero misses were seen — the rule-of-three 95%
    upper bound on the true FN-rate. All-None (never a crash) on an empty cohort."""
    labels = list(labels)
    n = len(labels)
    false_neg = sum(1 for is_target in labels if is_target)
    true_neg = n - false_neg
    if n == 0:
        return {"n": 0, "false_neg": 0, "true_neg": 0,
                "false_negative_rate": None, "rejection_quality": None, "fnr_upper_bound_95": None}
    fnr = false_neg / n
    # When we observed zero misses, the point estimate (0.0) understates the risk — report the rule-of-three
    # bound as the honest ceiling; when we DID see misses, the observed rate is the estimate.
    bound = rule_of_three_upper_bound(n) if false_neg == 0 else None
    return {"n": n, "false_neg": false_neg, "true_neg": true_neg,
            "false_negative_rate": round(fnr, 6), "rejection_quality": round(1.0 - fnr, 6),
            "fnr_upper_bound_95": bound}


def _unit_interval(seed, key):
    """A STABLE hash of (seed, key) into [0, 1). Uses hashlib, NOT Python's builtin hash() — builtin hash
    is salted per-process (PYTHONHASHSEED) so it would make selection non-reproducible across runs, the
    exact footgun this audit cannot tolerate. Reproducible given (seed, key) forever."""
    h = hashlib.md5(f"{seed}:{key}".encode("utf-8")).hexdigest()
    return int(h[:12], 16) / 0x1000000000000        # top 48 bits → [0, 1)


def select_audit_sample(reject_keys, p=DEFAULT_SAMPLE_RATE, seed="exploration-audit"):
    """The RANDOMIZED reject-audit draw — the whole ballgame. Selection randomness is enforced HERE, at
    draw time: the system decides which rejects the human audits, the human never cherry-picks (a
    cherry-picked audit biases the estimate and makes the license theater). Consistent hashing on
    (seed, key): each key is included iff its stable unit-interval draw < p. Three properties the invariant
    needs, all guaranteed by construction:
      - reproducible: same (keys, p, seed) → identical selection, run after run;
      - unbiased:     each key's inclusion is an independent ~Bernoulli(p), set-invariant (input order
                      cannot change the result);
      - growth-stable: a key's decision never changes as the reject population grows — a key already
                      audited (or already skipped) stays decided, so windows accumulate cleanly.
    Returns the selected keys, sorted (deterministic order)."""
    return sorted(k for k in set(reject_keys) if _unit_interval(seed, k) < p)


def next_license_state(current, window_count, floor_n=DEFAULT_FLOOR_N, promote_n=None):
    """The deadband license transition for a gate that is CONFIGURED auto. `current` in {"auto","manual"}:
      - auto   → demote to "manual" once coverage falls BELOW floor_n (revoke the license, the safe way);
      - manual → re-promote to "auto" only once coverage clears promote_n (> floor_n) — the hysteresis gap
                 that stops auto↔manual flapping when the count hovers near the floor.
    Returns only "auto"/"manual" — never "halt": losing the audit demotes autonomy one level, it does not
    stop the pipeline."""
    promote_n = promote_threshold(floor_n) if promote_n is None else promote_n
    if current == "auto":
        return "auto" if window_count >= floor_n else "manual"
    return "auto" if window_count >= promote_n else "manual"


def resolve_gate_mode(configured_mode, license_state, window_count,
                      floor_n=DEFAULT_FLOOR_N, promote_n=None):
    """The effective gate@5 mode, with the control law's enforcement shipping DORMANT (the --assert-floor
    pattern, #208). `configured_mode` is the operator's gate@5 toggle:
      - "manual": the control law is INERT — the human is census-labeling, there is nothing to demote, so
                  the effective mode is manual regardless of audit coverage (the demote-hook is a no-op);
      - "auto":   the control law is LIVE — the effective mode is the deadband transition of `license_state`
                  against `window_count`, i.e. auto while the audit validates the filter, demoted to manual
                  the moment coverage lapses.
    This is the one function the live gate@5 toggle will call once auto exists; until then it always
    returns "manual" because configured_mode is "manual"."""
    if configured_mode != "auto":
        return "manual"
    return next_license_state(license_state, window_count, floor_n, promote_n)
