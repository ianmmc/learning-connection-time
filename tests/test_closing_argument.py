"""Unit tests for the Stage-8 closing-argument assembler (pure composition, no DB/disk).

Mirrors tests/test_aggregate.py: synthetic school_fact-shaped inputs -> assertions on the
per-band claim, sampling sufficiency, evidence attachment, and the negative space.
"""
import json

from infrastructure.acquisition.stage8_aggregate import closing_argument as CA


def _fact(band, school, gross, *, rec_key=None, status="accepted", ext=1, models=("m1", "m2")):
    """A school_fact-shaped dict (start/end derived so gross is plausible & consistent)."""
    start_m, end_m = 8 * 60, 8 * 60 + gross
    return {"band": band, "school": school, "status": status, "extraction_id": ext,
            "start_time": f"{start_m//60:02d}:{start_m%60:02d}",
            "end_time": f"{end_m//60:02d}:{end_m%60:02d}", "gross_minutes": gross,
            "method": "council_agree", "models_json": json.dumps(list(models)),
            "rec_key": rec_key or f"D:{school}"}


class TestBandClaimAndSampling:
    def test_modal_value_and_plurality(self):
        # elementary: three schools at 400, one at 390 -> mode 400, plurality 3/4
        acc = [_fact("elementary", s, 400) for s in ("a", "b", "c")] + [_fact("elementary", "d", 390)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=10,
            nces_by_level={"Elementary": 8}, schools_by_band={})
        el = out["bands"]["elementary"]
        assert el["gross_minutes"] == 400
        assert el["sampling"]["n_sampled"] == 4
        assert el["sampling"]["n_total"] == 8          # clean Elementary LEVEL count
        assert el["sampling"]["coverage"] == 0.5
        assert el["sampling"]["plurality_share"] == 0.75

    def test_denominator_none_when_level_absent(self):
        acc = [_fact("high", "h1", 420)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=1,
            nces_by_level={"Elementary": 3}, schools_by_band={})   # no "High" key
        s = out["bands"]["high"]["sampling"]
        assert s["n_total"] is None and s["coverage"] is None


class TestEvidenceAttachment:
    def test_evidence_joined_by_reckey_and_missing_is_honest(self):
        acc = [_fact("middle", "north", 410, rec_key="D:north"),
               _fact("middle", "south", 410, rec_key="D:south")]
        evidence = {"D:north": {"url": "https://ex.org/bell", "reps": [{"file": "page.pdf"}]}}
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=5,
            nces_by_level={"Middle": 2}, schools_by_band={}, evidence_by_reckey=evidence)
        schools = {s["school"]: s for s in out["bands"]["middle"]["schools"]}
        assert schools["north"]["evidence"]["url"] == "https://ex.org/bell"
        assert schools["south"]["evidence"] is None      # no receipt -> surfaced, not hidden
        assert schools["north"]["rec_key"] == "D:north"


class TestNegativeSpace:
    def test_unsatisfied_bands_and_coverage_gaps(self):
        # district claims elementary+middle+high (roster), but only elementary has accepted facts
        acc = [_fact("elementary", "e1", 400)]
        sbb = {b: {"schools": [{"level": lvl}]}
               for b, lvl in (("elementary", "Elementary"), ("middle", "Middle"), ("high", "High"))}
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=6,
            nces_by_level={"Elementary": 4, "Middle": 1, "High": 1}, schools_by_band=sbb)
        ns = out["negative_space"]
        assert set(ns["claimed_bands"]) == {"elementary", "middle", "high"}
        assert set(ns["unsatisfied_bands"]) == {"middle", "high"}
        # elementary sampled 1 of 4 -> a coverage gap
        assert "elementary" in ns["coverage_gaps"]
        assert ns["coverage_gaps"]["elementary"]["n_sampled"] == 1

    def test_unresolved_and_unattributed_levels_surface(self):
        acc = [_fact("elementary", "e1", 400)]
        unres = [{"band": "middle", "school": "m1", "reason": "implausible"}]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=unres, nces_total=5,
            nces_by_level={"Elementary": 3, "Other": 2}, schools_by_band={})
        ns = out["negative_space"]
        assert ns["unresolved"] == unres
        assert ns["unattributed_level_schools"] == {"Other": 2}   # not folded into any band

    def test_contamination_flag_passes_through(self):
        # single-school NCES LEA whose accepted facts span two distinct schools -> #237 flag
        acc = [_fact("high", "ascend east", 420, rec_key="D:e"),
               _fact("high", "ascend west", 420, rec_key="D:w")]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=1,
            nces_by_level={"High": 1}, schools_by_band={})
        assert out["negative_space"]["contamination"]["suspected"] is True


class TestCouncilEvidence:
    def test_v2_evidence_json_surfaces_quote_and_stated_minutes(self):
        f = _fact("elementary", "oak", 435, rec_key="D:oak")
        f["evidence_json"] = json.dumps({
            "m1": {"quote": "School Hours: 8:00 AM - 3:15 PM", "locus": "p.2",
                   "stated_minutes": 435, "stated_minutes_quote": "instructional day: 435 minutes"},
            "m2": {"quote": "", "locus": "", "stated_minutes": 435, "stated_minutes_quote": ""}})
        out = CA.build_closing_argument(
            "D", merged_accepted=[f], merged_unresolved=[], nces_total=3,
            nces_by_level={"Elementary": 3}, schools_by_band={})
        ce = out["bands"]["elementary"]["schools"][0]["council_evidence"]
        assert ce["quote"] == "School Hours: 8:00 AM - 3:15 PM"      # first non-empty across models
        assert ce["locus"] == "p.2"
        assert ce["stated_minutes"] == 435 and ce["stated_minutes_agree"] is True

    def test_pre_v2_row_has_no_council_evidence(self):
        f = _fact("elementary", "oak", 435, rec_key="D:oak")   # no evidence_json (v1 vintage)
        out = CA.build_closing_argument(
            "D", merged_accepted=[f], merged_unresolved=[], nces_total=3,
            nces_by_level={"Elementary": 3}, schools_by_band={})
        assert out["bands"]["elementary"]["schools"][0]["council_evidence"] is None
