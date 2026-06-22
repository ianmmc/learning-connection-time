"""Tests for the per-school consensus + gross-minutes aggregation (REQ-054/055/056).

Covers the INVARIANT (models read times, code computes minutes/mode), GROSS metric,
cross-family per-school consensus, the exact-mode (380-not-381) fix, and mode-stability.
"""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infrastructure" / "acquisition"))
sys.path.insert(0, str(ROOT / "infrastructure" / "acquisition" / "discovery"))
import aggregate as A  # noqa: E402


# ---------------------------------------------------------------- REQ-054 invariant
class TestInvariant:
    def test_extractor_prompt_requests_times_not_minutes(self):
        """Models are asked for start/end times, NOT instructional minutes."""
        import extractors as E
        p = E.LEAN_SYSTEM_PROMPT.lower()
        assert "start" in p and "end" in p
        # must not instruct the model to compute/return minutes or pick a typical schedule
        assert "instructional minutes" not in p
        assert "most common" not in p and "typical full-day" not in p

    def test_no_triage_prompt_asks_model_to_pick_typical(self):
        """The removed triage prompt (model picks the modal schedule) must stay gone."""
        import extractors as E
        assert not hasattr(E, "TRIAGE_SYSTEM_PROMPT")


# ---------------------------------------------------------------- REQ-055 gross
class TestGross:
    def test_gross_is_end_minus_start(self):
        rows = {"gemini-2.5-flash-lite": [{"grade_level": "elementary", "start_time": "08:00", "end_time": "14:30", "school_name": "A"}],
                "mistral-small-24b":     [{"grade_level": "elementary", "start_time": "08:00", "end_time": "14:30", "school_name": "A"}]}
        accepted, _ = A.consensus_school_facts(rows)
        assert accepted and accepted[0]["gross"] == 390  # 14:30-08:00 = 6h30 = 390, no deduction

    def test_no_deduction_applied(self):
        # even if a lunch is mentioned in another row, gross ignores it (end-start only)
        bands = A.district_bands_from_facts([{"band": "elementary", "school": "a", "start": "08:00", "end": "15:00", "gross": 420, "models": ["x", "y"], "method": "council_agree"}])
        assert bands["elementary"]["gross_minutes"] == 420

    def test_plausibility_gate_240_510(self):
        assert A.PLAUSIBLE == (240, 510)
        # a 500-min day (LA) is accepted; a 600-min one is not
        ok = {"gemini-2.5-flash-lite": [{"grade_level": "high", "start_time": "07:30", "end_time": "15:50", "school_name": "H"}],
              "deepseek-v3.2":          [{"grade_level": "high", "start_time": "07:30", "end_time": "15:50", "school_name": "H"}]}
        acc, _ = A.consensus_school_facts(ok)
        assert acc and acc[0]["gross"] == 500
        bad = {"gemini-2.5-flash-lite": [{"grade_level": "high", "start_time": "06:00", "end_time": "16:30", "school_name": "H"}],
               "deepseek-v3.2":          [{"grade_level": "high", "start_time": "06:00", "end_time": "16:30", "school_name": "H"}]}
        acc2, unres = A.consensus_school_facts(bad)
        assert not acc2 and any(u.get("reason") == "implausible" for u in unres)


# ---------------------------------------------------------------- REQ-056 consensus
class TestConsensus:
    def _rows(self, models_times):
        return {m: [{"grade_level": "elementary", "start_time": s, "end_time": e, "school_name": "Lincoln Elementary"}]
                for m, (s, e) in models_times.items()}

    def test_cross_family_required(self):
        rows = self._rows({"gemini-2.5-flash-lite": ("08:00", "14:30"),
                           "mistral-small-24b": ("08:00", "14:30"),
                           "qwen3-235b": ("09:00", "15:00")})
        acc, _ = A.consensus_school_facts(rows)
        assert len(acc) == 1 and acc[0]["gross"] == 390
        assert {"gemini-2.5-flash-lite", "mistral-small-24b"} <= set(acc[0]["models"])

    def test_same_family_not_consensus(self):
        # two GOOGLE models agree, qwen differs -> NOT cross-family -> unresolved (no judge)
        rows = self._rows({"gemini-2.5-flash": ("08:00", "14:30"),
                           "gemini-2.5-flash-lite": ("08:00", "14:30"),
                           "qwen3-235b": ("09:10", "15:00")})
        acc, unres = A.consensus_school_facts(rows)
        assert acc == [] and len(unres) == 1

    def test_unresolved_held_out(self):
        # all three disagree -> held out, not counted
        rows = self._rows({"gemini-2.5-flash-lite": ("08:00", "14:00"),
                           "mistral-small-24b": ("08:30", "15:00"),
                           "qwen3-235b": ("09:00", "16:00")})
        acc, unres = A.consensus_school_facts(rows)
        assert acc == [] and len(unres) == 1

    def test_consensus_on_times_not_minutes(self):
        """Same DURATION via different start/end must NOT form consensus (it's on the pair)."""
        rows = self._rows({"gemini-2.5-flash-lite": ("08:00", "14:30"),   # 390
                           "mistral-small-24b": ("07:30", "14:00"),        # 390 but different pair
                           "qwen3-235b": ("09:00", "15:30")})              # 390 again, different pair
        acc, unres = A.consensus_school_facts(rows)
        # durations all equal 390, but no two share a (start,end) pair -> NO consensus
        assert acc == [] and len(unres) == 1


# ---------------------------------------------------------------- REQ-056 exact mode
class TestMode:
    def test_exact_mode_not_cluster_mean_380_not_381(self):
        """The user-caught bug: {380x26, 390x2, 345x1} must give 380, not a cluster-mean 381."""
        vals = [345] + [380] * 26 + [390] * 2
        val, method = A.aggregate_band(vals)
        assert val == 380 and method == "modal"

    def test_mean_tiebreak_on_distinct_tie(self):
        val, method = A.aggregate_band([390, 470])  # 1-1 tie between distinct values
        assert val == 430 and method == "mean_tiebreak"

    def test_strong_mode(self):
        val, method = A.aggregate_band([400, 400, 400, 405])
        assert val == 400 and method == "modal"


# ---------------------------------------------------------------- REQ-056 mode stability
class TestModeStability:
    def test_stable_run_and_plurality(self):
        assert A.mode_stable([390, 392, 388, 391, 389, 390]) is True

    def test_not_stable_when_scattered_or_bimodal(self):
        assert A.mode_stable([390, 450, 395, 470, 300, 360]) is False   # drift, low share
        assert A.mode_stable([390, 390, 470, 470, 390, 470]) is False   # 50/50 bimodal
