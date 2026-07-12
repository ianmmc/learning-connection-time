#!/usr/bin/env python3
"""#211 / REQ-120 live wiring — the DB half of the anti-survivorship exploration quota.

The pure control law lives in `exploration_audit.py` (DB-free, cash-free — the invariant locked in code
and unit-tested before any plumbing existed). This module binds it to the live governance store: the three
pieces the design (§5a) named as the full #211 build —

  1. the **reject-population query** — the audit universe = the current tier-D (SUPPRESS) reject bucket;
  2. the **randomized audit queue** — the pure sampler bound to that live population, partitioned into the
     already-audited window and the pending queue the human works top-down (`select_audit_sample`);
  3. the **gate@5 demote-hook** — `resolve_gate5_mode`, the one live caller of
     `exploration_audit.resolve_gate_mode`, reading the configured toggle + stored deadband license from
     the `gate_mode` store (#104) against the live coverage.

**Enforcement ships DORMANT** (the `--assert-floor` pattern, #208): gate@5 is configured *manual* today, so
`resolve_gate_mode` returns "manual", the demote-hook writes nothing, and no record flow changes. The hook
only persists the deadband transition and surfaces coverage once a human sets gate@5 auto in Settings.

**Current-config scoping is STRUCTURAL, not a stored fingerprint.** The window is recomputed over the LIVE
tier-D population every call, and a re-ingest re-tiers records — so a reject *rescued* to tier B by a config
change simply leaves the population and drops out of the window automatically (design criterion (b), §5a: a
reject audited under an old config says nothing about the live one). There is therefore **no reject-audit
table**: the sampler is pure + growth-stable, so the draw is reproducible from `(seed, the DB's current
reject set)` and the outcome is the human's label already in `label` (precious, git-backed). The
auditability replay ("you rejected class X; your own random audit surfaced it N times") needs nothing
persisted beyond what the endpoints already return — seed, rec_key, tier, score, outcome.

Design authority: STAGE5_FILTER_DESIGN_2026-06.md §5a; PIPELINE_GOVERNANCE_AND_STATE_2026-06.md §11b;
production-quality-control-research/FINDINGS-AND-DECISIONS.md §0/§1.
"""
from sqlalchemy import text

from infrastructure.acquisition.common import gate_mode as GM
from infrastructure.acquisition.stage5_filter import build_signals as BS  # TARGET_LABELS
from infrastructure.acquisition.stage5_filter import exploration_audit as EA

GATE = "gate@5"
REJECT_TIER = EA.REJECT_TIER       # combiner tier D == decision "suppress" == the auto-reject bucket
DEFAULT_SEED = EA.DEFAULT_SEED


def _is_target(primary_label):
    """The load-bearing human judgment: was this rejected page actually a target (a filter false negative)?
    Config-independent — the human's target/non-target call does not depend on the scoring config."""
    return primary_label in BS.TARGET_LABELS


def _labeled(row):
    """A reject counts toward the window only once a human has actually labeled it (a real audit datum),
    not merely because a placeholder `unlabeled` label row exists."""
    return bool(row["label_status"]) and row["label_status"] != "unlabeled" and row["primary_label"] is not None


def reject_population(con):
    """The audit universe: the current tier-D (SUPPRESS) reject bucket — REPRESENTATIVE, non-duplicate
    records only (one row per physical page, matching how the console tree + label cascade already treat a
    near-dup cluster). Each row carries the fields the auditability log needs (rec_key, url, sort_score,
    tier) plus the human outcome joined from `label`. Ordered by rec_key (deterministic)."""
    rows = con.execute(text(
        """SELECT r.rec_key, r.district_id, r.url, r.sort_score, r.tier,
                  l.primary_label, l.status AS label_status
             FROM record r LEFT JOIN label l ON l.rec_key = r.rec_key
            WHERE r.tier = :t AND r.duplicate_of IS NULL
              AND (r.is_cluster_rep = 1 OR r.cluster_id IS NULL)
            ORDER BY r.rec_key"""), {"t": REJECT_TIER}).mappings().all()
    return [dict(r) for r in rows]


def audit_sample(con, p=EA.DEFAULT_SAMPLE_RATE, seed=DEFAULT_SEED):
    """The randomized reject-audit draw over the LIVE reject population — the pure sampler bound to the
    current tier-D set. Returns the drawn rows partitioned into `audited` (already human-labeled → the
    window) and `pending` (the queue the human works top-down), plus the population/sample sizes. One DB
    pass. Selection randomness is enforced HERE, at draw time (the human labels what it presents, never
    cherry-picks) — a cherry-picked audit biases the estimate and the license is theater."""
    pop = reject_population(con)
    selected = set(EA.select_audit_sample([r["rec_key"] for r in pop], p=p, seed=seed))
    drawn = [r for r in pop if r["rec_key"] in selected]
    audited = [r for r in drawn if _labeled(r)]
    pending = [r for r in drawn if not _labeled(r)]
    return {"population_size": len(pop), "sample_size": len(drawn),
            "audited": audited, "pending": pending}


def coverage(con, p=EA.DEFAULT_SAMPLE_RATE, seed=DEFAULT_SEED, floor_n=EA.DEFAULT_FLOOR_N):
    """The coverage meter: `window_count` (audited sampled rejects, drawn from the live config generation)
    plus the honest reject-cohort signal — `rejection_quality` over their human labels (the fraction of the
    reject pile the filter got right, with the rule-of-three ceiling when zero misses were seen)."""
    s = audit_sample(con, p=p, seed=seed)
    labels = [_is_target(r["primary_label"]) for r in s["audited"]]
    return {"population_size": s["population_size"], "sample_size": s["sample_size"],
            "window_count": len(s["audited"]), "floor_n": floor_n,
            "promote_n": EA.promote_threshold(floor_n), "quality": EA.rejection_quality(labels),
            "seed": seed, "sample_rate": p, "n_pending": len(s["pending"])}


def resolve_gate5_mode(con, *, persist=True, actor="auto:exploration-audit",
                       p=EA.DEFAULT_SAMPLE_RATE, seed=DEFAULT_SEED, floor_n=EA.DEFAULT_FLOOR_N):
    """THE gate@5 demote-hook (#211): the live effective mode. Reads the human's configured toggle + the
    stored deadband license from the `gate_mode` store (#104), computes the live `window_count`, and applies
    the pure control law (`exploration_audit.resolve_gate_mode`).

    - configured **manual** (today, always): the law is INERT (census mode) — returns "manual", writes
      nothing. This is the dormant state.
    - configured **auto**: the law is LIVE — auto while the audit validates the filter, demoted to manual
      the instant coverage lapses; the deadband transition is PERSISTED back to `license_state` (the
      hysteresis memory) so a demoted gate re-promotes only above the deadband, never flaps.

    A missing stored license defaults to "manual" — start demoted, earn auto (the safe direction). Returns
    the full status dict (mode + coverage metrics) so the same call serves both the hook and the console."""
    cov = coverage(con, p=p, seed=seed, floor_n=floor_n)
    configured = GM.get_configured_mode(con, GATE)
    license_state = GM.get_license_state(con, GATE) or "manual"
    effective = EA.resolve_gate_mode(configured, license_state, cov["window_count"], floor_n=floor_n)
    # Persist the deadband transition ONLY when the law is live (configured auto) AND it actually moved —
    # in census mode the license is inert, and writing it would churn precious state for nothing.
    if persist and configured == "auto" and effective != license_state:
        GM.set_license_state(con, GATE, effective, actor=actor)
    return {"configured_mode": configured, "effective_mode": effective,
            "license_state": effective if configured == "auto" else license_state,
            "window_count": cov["window_count"], "floor_n": cov["floor_n"], "promote_n": cov["promote_n"],
            "quality": cov["quality"], "population_size": cov["population_size"],
            "sample_size": cov["sample_size"], "n_pending": cov["n_pending"],
            "seed": seed, "sample_rate": p}


def calibrate_against_census(con, p=EA.DEFAULT_SAMPLE_RATE, seed=DEFAULT_SEED):
    """The "calibrate NOW against census truth" step (§5a; feeds #214's measured-pass). While census-
    labeling is still live, every reject in a completed district is already labeled — so we can ask the
    load-bearing question retrospectively: does a p% random draw over the FULLY-LABELED reject bucket
    REPRODUCE the reject-quality the full census reports? Compares `rejection_quality` over ALL labeled
    rejects (census truth) vs. over the sampled subset. A close match earns trust in the sampler before
    census-labeling stops; a gap means N must be larger *first*. Worst-case by construction — completed
    districts are attention-sorted (messiest-first), so this is a floor on the sampler's fidelity, not the
    average case."""
    census = [r for r in reject_population(con) if _labeled(r)]
    selected = set(EA.select_audit_sample([r["rec_key"] for r in census], p=p, seed=seed))
    census_labels = [_is_target(r["primary_label"]) for r in census]
    sample_labels = [_is_target(r["primary_label"]) for r in census if r["rec_key"] in selected]
    return {"census": EA.rejection_quality(census_labels), "sample": EA.rejection_quality(sample_labels),
            "census_n": len(census), "sample_n": len(sample_labels), "seed": seed, "sample_rate": p}
