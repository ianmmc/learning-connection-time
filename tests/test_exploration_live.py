"""#211 / REQ-120 live wiring — the DB half of the anti-survivorship exploration quota.

The pure control law is unit-tested in test_exploration_audit.py; here we exercise the live binding against
the real governance Postgres (gov_session + connection-scoped TEMP tables shadowing record/label/gate_mode,
so nothing touches real data and no cleanup is needed). What must hold:
  - the reject population is exactly the tier-D (SUPPRESS) representative, non-duplicate bucket;
  - the randomized draw + coverage meter compute the honest window over the LIVE population;
  - the demote-hook is DORMANT while gate@5 is configured manual (writes nothing, returns manual) and LIVE
    (deadband demote + persisted license) once a human sets gate@5 auto.
"""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import gate_mode as GM
from infrastructure.acquisition.stage5_filter import exploration_live as EAL


def _temp_schema(s):
    """TEMP record/label/gate_mode with the columns the live module reads/writes — shadows the real tables
    for this connection only (auto-dropped at close), so assertions see only what this test inserts."""
    s.execute(text("""CREATE TEMP TABLE record (rec_key text PRIMARY KEY, district_id text, url text,
        sort_score double precision, tier text, duplicate_of text, is_cluster_rep integer, cluster_id text)"""))
    s.execute(text("CREATE TEMP TABLE label (rec_key text PRIMARY KEY, primary_label text, status text)"))
    s.execute(text("""CREATE TEMP TABLE gate_mode (gate text PRIMARY KEY, configured_mode text DEFAULT 'manual',
        license_state text, updated_at text, actor text)"""))


def _add(s, rk, tier="D", primary_label=None, status="unlabeled", *, did="D1", dup=None, rep=1, cluster=None):
    s.execute(text("""INSERT INTO record (rec_key, district_id, url, sort_score, tier, duplicate_of,
        is_cluster_rep, cluster_id) VALUES (:rk,:d,:u,:sc,:t,:dup,:rep,:cl)"""),
        {"rk": rk, "d": did, "u": f"http://x/{rk}", "sc": 0.1, "t": tier, "dup": dup, "rep": rep, "cl": cluster})
    s.execute(text("INSERT INTO label (rec_key, primary_label, status) VALUES (:rk,:pl,:st)"),
              {"rk": rk, "pl": primary_label, "st": status})


TGT = "school_bell_table"        # a TARGET_LABELS member — a filter false negative when found in tier D
NON = "target_absent"            # a correctly-rejected non-target


# ----------------------------- reject population (tier-D representatives only) -----------------------------
@pytest.mark.govdb
def test_reject_population_is_the_tier_d_representative_bucket(gov_session):
    s = gov_session
    _temp_schema(s)
    _add(s, "d:reject1", tier="D")
    _add(s, "d:reject2", tier="D", primary_label=TGT, status="labeled")
    _add(s, "d:sent", tier="A")                         # not a reject — auto-send
    _add(s, "d:review", tier="B")                       # not a reject — review
    _add(s, "d:dup", tier="D", dup="d:reject1")         # a duplicate — folded, not its own audit unit
    _add(s, "d:member", tier="D", rep=0, cluster="CL")  # a non-rep cluster member — the rep speaks for it
    pop = EAL.reject_population(s)
    keys = {r["rec_key"] for r in pop}
    assert keys == {"d:reject1", "d:reject2"}            # only tier-D reps, no dupes/members, no A/B
    assert next(r for r in pop if r["rec_key"] == "d:reject2")["primary_label"] == TGT
    s.rollback()


# ----------------------------- randomized draw + coverage meter -----------------------------
@pytest.mark.govdb
def test_audit_sample_partitions_drawn_rejects_into_audited_and_pending(gov_session):
    s = gov_session
    _temp_schema(s)
    _add(s, "d:r1", primary_label=TGT, status="labeled")   # audited (a false negative)
    _add(s, "d:r2", primary_label=NON, status="labeled")   # audited (a true negative)
    _add(s, "d:r3")                                        # pending (unlabeled)
    # p=1.0 draws the whole population deterministically (random() < 1.0 always), so the partition is exact.
    smp = EAL.audit_sample(s, p=1.0)
    assert smp["population_size"] == 3 and smp["sample_size"] == 3
    assert {r["rec_key"] for r in smp["audited"]} == {"d:r1", "d:r2"}
    assert {r["rec_key"] for r in smp["pending"]} == {"d:r3"}
    s.rollback()


@pytest.mark.govdb
def test_coverage_reports_window_count_and_reject_cohort_quality(gov_session):
    s = gov_session
    _temp_schema(s)
    _add(s, "d:r1", primary_label=TGT, status="labeled")   # 1 false negative
    _add(s, "d:r2", primary_label=NON, status="labeled")
    _add(s, "d:r3", primary_label=NON, status="labeled")
    _add(s, "d:r4", primary_label=NON, status="labeled")   # 3 true negatives
    cov = EAL.coverage(s, p=1.0, floor_n=4)
    assert cov["window_count"] == 4 and cov["floor_n"] == 4 and cov["promote_n"] == 5   # ceil(1.2*4)
    q = cov["quality"]
    assert q["n"] == 4 and q["false_neg"] == 1 and q["false_negative_rate"] == 0.25
    assert q["rejection_quality"] == 0.75
    s.rollback()


# ----------------------------- the demote-hook: DORMANT while manual -----------------------------
@pytest.mark.govdb
def test_resolve_is_dormant_while_gate5_is_configured_manual(gov_session):
    s = gov_session
    _temp_schema(s)
    _add(s, "d:r1", primary_label=NON, status="labeled")
    # configured manual (the default) → the law is inert: NOTHING is written to license_state (census
    # mode has nothing to demote), and — PR #248 review — the FAST PATH skips the reject-bucket scan
    # entirely (this hook runs on every save_label; dead work on the hottest write path). Coverage
    # fields are None on the fast path: no numbers were computed, and None must not read as zero.
    out = EAL.resolve_gate5_mode(s, p=1.0, floor_n=1)
    assert out["configured_mode"] == "manual" and out["effective_mode"] == "manual"
    assert out["window_count"] is None                     # skipped, not computed-and-discarded
    assert GM.get_license_state(s, "gate@5") is None       # the hook wrote nothing
    # a caller that DOES hold coverage (the status endpoint) still gets the full dormant readout
    cov = EAL.coverage(s, p=1.0, floor_n=1)
    full = EAL.resolve_gate5_mode(s, p=1.0, floor_n=1, cov=cov)
    assert full["effective_mode"] == "manual" and full["window_count"] == 1
    assert GM.get_license_state(s, "gate@5") is None       # still nothing written
    s.rollback()


@pytest.mark.govdb
def test_coverage_reuses_a_precomputed_sample(gov_session):
    # PR #248 review: the status endpoint draws ONCE and threads the sample through coverage +
    # resolve — the same numbers must come out as a fresh internal draw (one snapshot, no re-query).
    s = gov_session
    _temp_schema(s)
    _add(s, "d:r1", primary_label=NON, status="labeled")
    _add(s, "d:r2")
    sample = EAL.audit_sample(s, p=1.0)
    assert EAL.coverage(s, p=1.0, sample=sample) == EAL.coverage(s, p=1.0)
    s.rollback()


# ----------------------------- the demote-hook: LIVE once auto -----------------------------
@pytest.mark.govdb
def test_resolve_demotes_and_persists_the_license_when_coverage_lapses(gov_session):
    s = gov_session
    _temp_schema(s)
    _add(s, "d:r1", primary_label=NON, status="labeled")   # window_count = 1
    GM.set_configured_mode(s, "gate@5", "auto", actor="ian")
    GM.set_license_state(s, "gate@5", "auto", actor="seed")  # currently licensed auto
    # coverage (1) is below the floor (5) → the license DEMOTES to manual and the transition PERSISTS
    # (the hysteresis memory), while the human's configured toggle stays auto.
    out = EAL.resolve_gate5_mode(s, p=1.0, floor_n=5)
    assert out["window_count"] == 1                        # the whole bucket, still short of the floor
    assert out["effective_mode"] == "manual" and out["configured_mode"] == "auto"
    assert GM.get_license_state(s, "gate@5") == "manual"    # demote was written back
    assert GM.get_configured_mode(s, "gate@5") == "auto"    # human toggle untouched
    s.rollback()


@pytest.mark.govdb
def test_resolve_holds_auto_while_coverage_meets_the_floor(gov_session):
    s = gov_session
    _temp_schema(s)
    _add(s, "d:r1", primary_label=NON, status="labeled")
    _add(s, "d:r2", primary_label=NON, status="labeled")
    GM.set_configured_mode(s, "gate@5", "auto", actor="ian")
    GM.set_license_state(s, "gate@5", "auto", actor="seed")
    out = EAL.resolve_gate5_mode(s, p=1.0, floor_n=1)       # window 2 >= floor 1 → stays licensed
    assert out["window_count"] == 2 and out["effective_mode"] == "auto"
    assert GM.get_license_state(s, "gate@5") == "auto"
    s.rollback()


# ----------------------------- retrospective calibration (feeds #214) -----------------------------
@pytest.mark.govdb
def test_calibrate_against_census_compares_sample_to_full_labels(gov_session):
    s = gov_session
    _temp_schema(s)
    # 10 fully-labeled rejects, 2 of them false negatives → census quality 0.8. A p=1.0 draw sees the whole
    # census, so sample quality must equal census quality exactly (the sampler reproduces the truth).
    for i in range(2):
        _add(s, f"d:fn{i}", primary_label=TGT, status="labeled")
    for i in range(8):
        _add(s, f"d:tn{i}", primary_label=NON, status="labeled")
    _add(s, "d:pending")                                   # an UNlabeled reject — excluded from census truth
    out = EAL.calibrate_against_census(s, p=1.0)
    assert out["census_n"] == 10 and out["sample_n"] == 10
    assert out["census"]["rejection_quality"] == 0.8
    assert out["sample"]["rejection_quality"] == out["census"]["rejection_quality"]
    s.rollback()
