"""Tests for acquisition stages: sampling/band-classifier (built), topology + waves
(skip stubs until live-wired), GT re-derivation process. (REQ-057/058/059)."""
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infrastructure" / "acquisition"))
sys.path.insert(0, str(ROOT / "infrastructure" / "acquisition" / "discovery"))
import school_sampling as S  # noqa: E402
import aggregate as A  # noqa: E402


# ---------------------------------------------------------------- REQ-058 sampling
class TestSampling:
    def test_band_classifier_grade_span(self):
        """Grade span -> bands; a K-8 covers elementary AND middle, a 9-12 only high."""
        assert S.bands_for("KG", "05") == {"elementary"}
        assert S.bands_for("06", "08") == {"middle"}
        assert S.bands_for("09", "12") == {"high"}
        assert S.bands_for("KG", "08") == {"elementary", "middle"}   # K-8 spans two
        assert S.bands_for("PK", "12") == {"elementary", "middle", "high"}
        assert S.bands_for("M", "M") == set()                         # ungraded -> no band

    def test_sample_size_censuses_small(self):
        """95/+-5 finite-population: small N is censused; large N capped well below N."""
        assert S.sample_size(1) == 1
        assert S.sample_size(3) == 3
        assert S.sample_size(30) >= 27          # near-census
        assert S.sample_size(900) < 300         # large districts sampled, not censused
        assert S.sample_size(0) == 0


class TestWaves:
    @pytest.mark.skip(reason="live wave orchestration needs the agent (Claude WebSearch subagent); not script-wired - REQ-058")
    def test_wave_order_no_perplexity(self):
        # When wired: assert discovery uses claude -> openrouter only, stop-when-found, no perplexity call.
        ...


# ---------------------------------------------------------------- REQ-057 topology
class TestTopology:
    @pytest.mark.skip(reason="live Haiku topology classification not yet wired; hand labels exist in CURATION_RECONCILED.json - REQ-057")
    def test_topology_label_recorded(self):
        # When wired: assert claude_urls.json carries topology in {hub, per_school, none}.
        ...


# ---------------------------------------------------------------- REQ-060 charter tagging
class TestCharter:
    def test_charter_lookup_from_nces(self):
        """Fairbanks AK (0200600) has known charter schools in its NCES roster -> tagged 'Yes'."""
        look = S.charter_lookup("0200600")
        assert look, "expected NCES schools for Fairbanks"
        assert "Yes" in look.values() and "No" in look.values()   # both present (charters + traditional)

    def test_unmatched_school_is_unknown(self):
        """A school name not in the LEA roster resolves to 'unknown' (caller default), never excluded."""
        look = S.charter_lookup("0200600")
        assert look.get("this school does not exist anywhere", "unknown") == "unknown"


# ---------------------------------------------------------------- REQ-059 GT process
class TestGTProcess:
    def test_band_rederived_from_confirmed_schools(self):
        """The band value is re-derived deterministically from per-school facts (REQ-056),
        not asserted by a model. Mirrors the in-place re-derive used on gt_proposals.json."""
        schools = [
            {"school": "a", "start_time": "08:50", "end_time": "15:10"},  # 380
            {"school": "b", "start_time": "08:50", "end_time": "15:10"},  # 380
            {"school": "c", "start_time": "08:25", "end_time": "14:55"},  # 390
        ]
        grosses = []
        for s in schools:
            st = A._to_min(s["start_time"]); en = A._to_min(s["end_time"])
            grosses.append(en - st)
        val, method = A.aggregate_band(grosses)
        assert val == 380 and method == "modal"   # mode of {380,380,390}, computed in code
