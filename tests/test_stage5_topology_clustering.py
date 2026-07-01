"""REQ-105/106/107 — protect the built-but-previously-untested Stage 5 plumbing:
labeled-topology derivation, near-duplicate clustering, and the funnel ingredients (URL->school
map). Pure-function tests over synthetic inputs (no live DB / no NCES read), so they pin the
deterministic logic without external data. The funnel coverage is deliberately light — the analysis
layer is still far off — but the plumbing must not silently break.
"""
import json

from infrastructure.acquisition.stage5_filter import build_signals as BS  # noqa: E402


# ----------------------------- labeled topology (REQ-105) -----------------------------
class TestLabeledTopology:
    def test_unknown_when_nothing_labeled(self):
        assert BS.derive_labeled_topology([], nces_count=3) == "unknown"
        assert BS.derive_labeled_topology([None, None], nces_count=3) == "unknown"

    def test_none_found_when_labeled_but_no_targets(self):
        # reviewed, zero targets -> re-discovery signal (precedence BEFORE single_school)
        assert BS.derive_labeled_topology(["board_schedule", "none"], nces_count=1) == "none_found"

    def test_single_school_nces_confirmed(self):
        assert BS.derive_labeled_topology(["school_bell_table"], nces_count=1) == "single_school"

    def test_mixed_hub_plus_school_level(self):
        got = BS.derive_labeled_topology(
            ["district_hub_by_school", "school_bell_table"], nces_count=10)
        assert got == "mixed"

    def test_district_hub_only(self):
        assert BS.derive_labeled_topology(["district_hub_by_school"], nces_count=10) == "district_hub"

    def test_incomplete_coverage_exact_criterion(self):
        # exactly one target, it's school_bell_table, NCES says >1 school
        assert BS.derive_labeled_topology(["school_bell_table"], nces_count=5) == "incomplete_coverage"

    def test_per_school_multiple_school_level_targets(self):
        got = BS.derive_labeled_topology(
            ["school_bell_table", "school_start_end_prose"], nces_count=8)
        assert got == "per_school"

    def test_incomplete_coverage_does_not_fire_for_prose_single(self):
        # one target but it's prose, not school_bell_table -> per_school, not incomplete_coverage
        assert BS.derive_labeled_topology(["school_start_end_prose"], nces_count=5) == "per_school"

    def test_none_found_precedes_single_school(self):
        # a 1-school LEA reviewed with no target is none_found (re-discover), not single_school
        assert BS.derive_labeled_topology(["none"], nces_count=1) == "none_found"


# ----------------------------- shingles + jaccard (REQ-106) -----------------------------
class TestShingleJaccard:
    def test_identical_text_jaccard_is_one(self):
        a = BS.shingles("the quick brown fox jumps")
        b = BS.shingles("the quick brown fox jumps")
        assert BS.jaccard(a, b) == 1.0

    def test_disjoint_text_jaccard_is_zero(self):
        a = BS.shingles("alpha beta gamma delta")
        b = BS.shingles("one two three four")
        assert BS.jaccard(a, b) == 0.0

    def test_both_empty_is_one_one_empty_is_zero(self):
        assert BS.jaccard(frozenset(), frozenset()) == 1.0
        assert BS.jaccard(BS.shingles("alpha beta gamma"), frozenset()) == 0.0

    def test_short_text_below_k_falls_back_to_tokens(self):
        # fewer than SHINGLE_K words -> frozenset of the tokens themselves
        assert BS.shingles("hi there") == frozenset({"hi", "there"})

    def test_partial_overlap_between_zero_and_one(self):
        a = BS.shingles("the quick brown fox jumps over")
        b = BS.shingles("the quick brown cat jumps over")
        j = BS.jaccard(a, b)
        assert 0.0 < j < 1.0


# ----------------------------- clustering (REQ-106) -----------------------------
class TestClusterDistrict:
    def _items(self):
        sa = frozenset({"a b c", "b c d", "c d e"})       # r1, r2 share these -> jaccard 1.0
        sc = frozenset({"x y z"})                          # r3 distinct -> singleton
        return [
            ("d1:r1", sa, "B", 50.0),
            ("d1:r2", sa, "A", 90.0),
            ("d1:r3", sc, "C", 10.0),
        ]

    def test_near_dups_cluster_singleton_stays_alone(self):
        out = BS.cluster_district(self._items(), splits=set())
        # r1, r2 share a cluster id; r3 is a singleton (None)
        assert out["d1:r1"][0] is not None
        assert out["d1:r1"][0] == out["d1:r2"][0]
        assert out["d1:r3"][0] is None
        assert out["d1:r1"][2] == 2 and out["d1:r3"][2] == 1   # cluster_size

    def test_representative_is_best_tier(self):
        out = BS.cluster_district(self._items(), splits=set())
        # rep = min by (tier rank, -score, key) -> r2 is tier A (rank 0) -> is_rep=1; r1 not
        assert out["d1:r2"][1] == 1
        assert out["d1:r1"][1] == 0

    def test_human_split_keeps_a_record_out_of_its_cluster(self):
        out = BS.cluster_district(self._items(), splits={"d1:r2"})
        # r2 forced out -> r1 has no remaining match -> both singletons
        assert out["d1:r2"][0] is None
        assert out["d1:r1"][0] is None
        assert out["d1:r3"][0] is None


# ----------------------------- funnel ingredients (REQ-107, light) -----------------------------
class TestFunnelPlumbing:
    def test_load_candidates_parses_url_to_school_map(self, tmp_path):
        (tmp_path / "candidates.json").write_text(json.dumps({"candidates": [
            {"url": "https://a.org/bell", "schools": ["S1", "S2"], "tools": ["claude"]},
            {"url": "https://b.org/hours", "schools": ["S3"], "tools": ["openrouter"]},
        ]}))
        cmap = BS.load_candidates(tmp_path)
        assert set(cmap) == {"https://a.org/bell", "https://b.org/hours"}
        assert cmap["https://a.org/bell"]["schools"] == ["S1", "S2"]
        assert cmap["https://b.org/hours"]["tools"] == ["openrouter"]

    def test_load_candidates_missing_file_is_empty(self, tmp_path):
        assert BS.load_candidates(tmp_path) == {}

    def test_emergent_is_a_url_absent_from_the_candidate_map(self, tmp_path):
        # the funnel's emergent rule: a captured URL not in candidates.json was never planned.
        (tmp_path / "candidates.json").write_text(json.dumps({"candidates": [
            {"url": "https://planned.org/bell", "schools": ["S1"], "tools": ["claude"]},
        ]}))
        cmap = BS.load_candidates(tmp_path)
        assert ("https://planned.org/bell" in cmap) is True       # planned
        assert ("https://5il.co/emergent-pdf" in cmap) is False    # emergent (discovered mid-capture)
