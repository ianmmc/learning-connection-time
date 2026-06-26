"""REQ-090 — the measurement harness scores config+signals vs labels correctly, with
reproducible fingerprints. Pure metric functions tested against synthetic inputs (not the
live DB, whose values shift as labels change)."""
import sqlite3
import sys
from pathlib import Path

STAGE5 = Path(__file__).resolve().parents[1] / "infrastructure" / "acquisition" / "stage5_filter"
sys.path.insert(0, str(STAGE5))
import harness  # noqa: E402


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


def test_empty_inputs_dont_crash():
    assert harness.category_accuracy([])["overall"] is None
    assert harness.tier_target_metrics([])["thresholds"]["A"]["precision"] is None
    assert harness.topology_report([])["coarse_agreement"] is None


def _mini_db():
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE record (rec_key TEXT, tier TEXT, category_hypothesis TEXT);
        CREATE TABLE label (rec_key TEXT, primary_label TEXT, status TEXT, flags_json TEXT);
        CREATE TABLE district (district_id TEXT, name TEXT, guessed_topology TEXT,
                               labeled_topology TEXT, nces_school_count INTEGER);
        INSERT INTO record VALUES ('d:1','A','school_bell_schedule'),('d:2','D','none');
        INSERT INTO label VALUES ('d:1','school_bell_schedule','labeled','[]'),
                                 ('d:2','none','labeled','[]');
        INSERT INTO district VALUES ('d','D','per_school','per_school',3);
    """)
    con.commit()
    return con


def test_score_and_fingerprints_are_deterministic():
    con = _mini_db()
    s1 = harness.score(con)
    assert s1["counts"]["labeled"] == 2 and s1["counts"]["targets"] == 1
    assert s1["category_accuracy"]["overall"] == 1.0   # both guesses match labels here
    fp1 = harness.fingerprints(con)
    fp2 = harness.fingerprints(con)
    assert fp1 == fp2 and set(fp1) == {"config", "label_set", "data"}
