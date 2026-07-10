"""REQ-090 — the measurement harness scores config+signals vs labels correctly, with
reproducible fingerprints. Pure metric functions tested against synthetic inputs (not the
live DB, whose values shift as labels change); the score/fingerprint DB readers run against the
real governance Postgres via CONNECTION-SCOPED TEMP tables (the gov_session fixture)."""
import pytest
from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import harness  # noqa: E402

# gov_session tests must carry the govdb marker or CI never runs them: the DB-free job skips them
# (no Docker) and the govdb job deselects unmarked tests (#215 review).
govdb = pytest.mark.govdb


def test_tier_target_metrics_counts_and_thresholds():
    rows = [("A", True), ("A", True), ("A", False), ("B", False), ("C", True), ("D", False)]
    m = harness.tier_target_metrics(rows)
    assert m["per_tier"]["A"] == {"target": 2, "nontarget": 1}
    assert m["per_tier"]["C"] == {"target": 1, "nontarget": 0}
    a = m["thresholds"]["A"]
    assert (a["tp"], a["fp"], a["fn"]) == (2, 1, 1)
    assert a["precision"] == 0.6667 and a["recall"] == 0.6667
    ab = m["thresholds"]["A+B"]
    assert (ab["tp"], ab["fp"], ab["fn"]) == (2, 2, 1)  # B adds a false positive
    assert ab["precision"] == 0.5


def test_category_accuracy_overall_and_per_label():
    rows = [("a", "a"), ("a", "b"), ("c", "c"), ("x", "y")]
    m = harness.category_accuracy(rows)
    assert m["overall"] == 0.5 and m["n"] == 4 and m["correct"] == 2
    assert m["per_label"]["a"] == {"n": 1, "correct": 1}
    assert m["per_label"]["b"] == {"n": 1, "correct": 0}


def test_topology_coarse_agreement_excludes_non_hub_per_school():
    rows = [("D1", "hub", "district_hub"), ("D2", "per_school", "per_school"),
            ("D3", "hub", "per_school"), ("D4", "unknown", "single_school"),
            ("D5", "per_school", "none_found")]
    m = harness.topology_report(rows)
    assert m["coarse_den"] == 3        # D4/D5 excluded (not a hub/per-school claim)
    assert m["coarse_agree"] == 2      # D1, D2 agree; D3 disagrees
    assert m["coarse_agreement"] == 0.6667
    assert m["pairs"]["D3"] == ["hub", "per_school"]


def test_recall_floor_helpers_read_the_ab_tier():
    # #208: the canonical floor defends A+B recall (reaches-review), not tier-A. floor_satisfied is
    # False on a None recall and on a below-floor recall.
    assert harness.FLOOR_TIER == "A+B"
    card = {"tier_vs_target": {"thresholds": {"A": {"recall": 0.80}, "A+B": {"recall": 0.985}}}}
    assert harness.floor_recall(card) == 0.985                     # read from A+B, not the 0.80 tier-A
    assert harness.floor_satisfied(card) is True                   # 0.985 >= 0.98
    assert harness.floor_satisfied(card, floor=0.99) is False      # 0.985 < 0.99
    assert harness.floor_recall({"tier_vs_target": {"thresholds": {}}}) is None
    assert harness.floor_satisfied({"tier_vs_target": {"thresholds": {}}}) is False


def test_floor_helpers_degrade_on_malformed_scorecards():
    # #215 review: the ledger loads scorecards from arbitrary on-disk JSON, so a present-but-null or
    # wrong-typed field must read as None/unsatisfied — never an AttributeError (the try/except these
    # helpers replaced tolerated exactly these shapes).
    for bad in ({"tier_vs_target": None}, {"tier_vs_target": []}, {"tier_vs_target": {"thresholds": None}},
                {"tier_vs_target": {"thresholds": {"A+B": None}}}, {}, None):
        assert harness.floor_recall(bad) is None
        assert harness.floor_satisfied(bad) is False


def test_f1_is_zero_not_none_when_precision_and_recall_are_zero():
    # issue #63: tp=0 with fp>0 and fn>0 -> precision 0.0, recall 0.0 — LEGITIMATE values, so f1
    # must be 0.0 (computable), not None (not-computable)
    m = harness.tier_target_metrics([("A", False), ("B", True)])
    a = m["thresholds"]["A"]
    assert a["precision"] == 0.0 and a["recall"] == 0.0
    assert a["f1"] == 0.0


# ---- #108: facet-level per-detector diagnostics ----
def test_confounder_facets_parses_v21_dict_and_ignores_axis3():
    assert harness.confounder_facets('{"news_feed":"yes","_where":"footer","buried_handbook":"yes"}') == {"news_feed"}
    assert harness.confounder_facets("{}") == set()
    assert harness.confounder_facets(None) == set()
    assert harness.confounder_facets('["not","a","dict"]') == set()   # legacy/malformed shape -> no confounders
    # #199 review: only the literal "yes" counts — an explicit negative marker (or any other value a
    # future writer might store) must NOT read as a present confounder.
    assert harness.confounder_facets('{"news_feed":"no"}') == set()
    assert harness.confounder_facets('{"news_feed":true}') == set()


def test_parse_facets_is_the_single_tagged_predicate():
    # #199 review: `tagged` and `confounder_facets` previously used INDEPENDENT checks (raw string vs
    # dict-shape), letting a non-dict legacy value count into the facet-tagged denominator while never
    # contributing a hit. parse_facets is now the one predicate: dict-with-content -> reviewed; anything
    # else (empty, null, non-dict, unparseable) -> not reviewed.
    assert harness.parse_facets('{"sports":"yes"}') == {"sports": "yes"}
    assert harness.parse_facets('{"_where":"footer"}') == {"_where": "footer"}   # axis-3-only still = reviewed
    assert harness.parse_facets("{}") is None
    assert harness.parse_facets(None) is None
    assert harness.parse_facets("null") is None
    assert harness.parse_facets('["not","a","dict"]') is None   # the shape that used to inflate the denominator


def test_facet_detector_diagnostics_scores_confounder_not_just_nontarget():
    # A negative detector firing on a record that IS a target but carries its confounder facet is a HIT
    # (the #108 point — a target can co-occur with a confounder). Untagged records don't count against it.
    rows = [
        (["lf_news_feed"], {"news_feed"}, True),        # correct confounder id (even if the page is a target)
        (["lf_news_feed"], {"board"}, True),            # fired, but the tagged confounder is board -> miss
        (["lf_news_feed"], set(), False),               # untagged record -> excluded from the denominator
        (["lf_board"], {"board"}, True),                # a different detector, correct
    ]
    out = harness.facet_detector_diagnostics(rows)["per_detector"]
    nf = out["lf_news_feed"]
    assert nf["fires"] == 3 and nf["fires_facet_tagged"] == 2 and nf["hits"] == 1
    assert nf["facet_precision"] == 0.5
    assert out["lf_board"]["facet_precision"] == 1.0
    assert out["lf_transport"]["facet_precision"] is None   # never fired -> not computable


def test_empty_inputs_dont_crash():
    assert harness.category_accuracy([])["overall"] is None
    assert harness.tier_target_metrics([])["thresholds"]["A"]["precision"] is None
    assert harness.topology_report([])["coarse_agreement"] is None


def _seed_mini(sess):
    """The three tables harness.score/fingerprints read, as CONNECTION-SCOPED TEMP tables on the
    governance session (auto-dropped at close — never touches real governance data)."""
    sess.execute(text("CREATE TEMP TABLE record (rec_key text, tier text, category_hypothesis text, signals_json text)"))
    sess.execute(text("CREATE TEMP TABLE label (rec_key text, primary_label text, status text, facets_json text)"))
    sess.execute(text("""CREATE TEMP TABLE district (district_id text, name text, guessed_topology text,
                               labeled_topology text, nces_school_count integer)"""))
    # signals_json carries the V2 fired detectors (REQ-113) the harness reads for per-detector diagnostics.
    sess.execute(text("""INSERT INTO record VALUES
        ('d:1','A','school_bell_table','{\"detectors\": [{\"name\": \"lf_time_table\"}]}'),
        ('d:2','D','none','{\"detectors\": [{\"name\": \"lf_no_times\"}]}')"""))
    sess.execute(text("""INSERT INTO label VALUES ('d:1','school_bell_table','labeled','[]'),
                                 ('d:2','none','labeled','[]')"""))
    sess.execute(text("INSERT INTO district VALUES ('d','D','per_school','per_school',3)"))
    return sess


@govdb
def test_score_and_fingerprints_are_deterministic(gov_session):
    con = _seed_mini(gov_session)
    s1 = harness.score(con)
    assert s1["counts"]["labeled"] == 2 and s1["counts"]["targets"] == 1
    assert s1["category_accuracy"]["overall"] == 1.0   # both guesses match labels here
    fp1 = harness.fingerprints(con)
    fp2 = harness.fingerprints(con)
    assert fp1 == fp2 and set(fp1) == {"config", "label_set", "data"}


@govdb
def test_assert_floor_passes_and_returns_the_ab_recall(gov_session):
    # _seed_mini's one target sits in tier A -> A+B recall = 1.0 >= 0.98: the gate passes and reports it.
    con = _seed_mini(gov_session)
    assert harness.assert_floor(con) == 1.0


@govdb
def test_assert_floor_raises_systemexit_on_violation(gov_session):
    # #215 review: the enforcement branch — a TARGET suppressed to tier D drops A+B recall to 0.5 < 0.98.
    # assert_floor runs INSIDE the ingest transaction, so this raise is what keeps a violating config's
    # tiers out of the working store (SystemExit skips session_scope's commit).
    con = _seed_mini(gov_session)
    con.execute(text("""INSERT INTO record VALUES
        ('d:3','D','none','{\"detectors\": [{\"name\": \"lf_no_times\"}]}')"""))
    con.execute(text("INSERT INTO label VALUES ('d:3','school_bell_table','labeled','[]')"))
    with pytest.raises(SystemExit, match="RECALL FLOOR VIOLATED"):
        harness.assert_floor(con)
    assert harness.assert_floor(con, floor=0.5) == 0.5   # explicit floor: exactly AT the floor passes
