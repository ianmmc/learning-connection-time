"""Unit tests for the #499 slot spine (REQ-144) — pure projection + roster drift.

Mirrors tests/test_closing_argument.py's posture: synthetic inputs, no DB/disk.
"""
from infrastructure.acquisition.common import slot_spine as SP


def _rec(school_id, name, **kw):
    return {"school_id": school_id, "name": name, "is_charter": kw.get("is_charter", "No"),
            "gslo": kw.get("gslo", "KG"), "gshi": kw.get("gshi", "05"),
            "level": kw.get("level", "Elementary"),
            "effective_band": kw.get("effective_band", "elementary"),
            "source": kw.get("source", "level_clean")}


def _rosters(recs_by_band):
    return {b: {"slot_recs": recs, "schools": [r["name"] for r in recs],
                "total": len(recs), "by_source": {}}
            for b, recs in recs_by_band.items()}


class TestProjectSlots:
    def test_filled_unfilled_and_stats(self):
        rosters = _rosters({"elementary": [_rec("001", "Oak Elementary School"),
                                           _rec("002", "Maple Elementary School")]})
        out = SP.project_slots(rosters, {"elementary": ["oak"]})   # facts carry the norm-ish name
        el = out["elementary"]
        by_id = {s["school_id"]: s for s in el["slots"]}
        assert by_id["001"]["slot_state"] == "filled"
        assert by_id["001"]["match"]["confidence"] == "matched"
        assert by_id["001"]["match"]["basis"] == ["exact_name"]
        assert by_id["002"]["slot_state"] == "unfilled" and by_id["002"]["match"] is None
        assert el["stats"] == {"n_slots": 2, "n_filled": 1, "n_unfilled": 1,
                               "n_extras": 0, "n_ambiguous": 0, "slot_coverage": 0.5}

    def test_unmatched_extra_is_first_class(self):
        rosters = _rosters({"high": [_rec("101", "North High School", effective_band="high")]})
        out = SP.project_slots(rosters, {"high": ["north", "lakeside academy"]})
        hi = out["high"]
        assert hi["stats"]["n_filled"] == 1
        assert [x["school_display"] for x in hi["extras"]] == ["lakeside academy"]
        assert hi["extras"][0]["confidence"] == "unmatched_extra"

    def test_collision_is_ambiguous_and_fills_nothing(self):
        # "Washington Elementary" and "Washington Academy" both normalize to "washington" —
        # the fact must attach to BOTH as ambiguous and fill NEITHER (resolution is PR-B's human
        # disposition, ramp-up posture).
        rosters = _rosters({"elementary": [_rec("001", "Washington Elementary School"),
                                           _rec("002", "Washington Academy")]})
        out = SP.project_slots(rosters, {"elementary": ["washington"]})
        el = out["elementary"]
        assert el["stats"]["n_filled"] == 0 and el["stats"]["n_ambiguous"] == 1
        for s in el["slots"]:
            assert s["slot_state"] == "unfilled"
            assert s["match"]["confidence"] == "ambiguous"
            assert len(s["match"]["candidates"]) == 2
        assert el["extras"] == []   # an ambiguous fact is NOT an extra

    def test_band_with_facts_but_no_roster_slots(self):
        # CCD gave this band no slot_recs (or the band key is absent) — facts surface as extras,
        # never dropped.
        out = SP.project_slots({"elementary": {"slot_recs": []}}, {"middle": ["riverside"]})
        assert out["middle"]["stats"]["n_slots"] == 0
        assert [x["school_display"] for x in out["middle"]["extras"]] == ["riverside"]

    def test_none_rosters_and_underscore_keys_tolerated(self):
        out = SP.project_slots(None, {"high": ["north"]})
        assert out["high"]["stats"]["n_slots"] == 0 and out["high"]["stats"]["n_extras"] == 1
        out2 = SP.project_slots({"_year": "2024_25", "_unattributed": ["x"],
                                 "elementary": {"slot_recs": [_rec("001", "Oak School")]}}, {})
        assert set(out2.keys()) == {"elementary"}


class TestRosterDrift:
    def _live(self):
        return {"elementary": [{"school_id": "001", "roster_school": "Oak"},
                               {"school_id": "003", "roster_school": "Birch"}],
                "middle": [{"school_id": "003", "roster_school": "Birch"}]}

    def test_no_baseline_returns_none(self):
        # A pre-#499 receipt carries no slots — nothing signed to diff against, the honest null.
        assert SP.roster_drift(self._live(), {}) is None
        assert SP.roster_drift(self._live(), {"elementary": []}) is None

    def test_no_drift_returns_empty(self):
        assert SP.roster_drift(self._live(), self._live()) == {}

    def test_added_removed_band_moved(self):
        receipt = {"elementary": [{"school_id": "001", "roster_school": "Oak"},
                                  {"school_id": "002", "roster_school": "Elm"},
                                  {"school_id": "003", "roster_school": "Birch"}]}
        d = SP.roster_drift(self._live(), receipt)
        assert [a["school_id"] for a in d["added"]] == []      # 003 exists in both (bands moved)
        assert [r["school_id"] for r in d["removed"]] == ["002"]   # Elm closed
        assert d["band_moved"] == [{"school_id": "003", "name": "Birch",
                                    "from": ["elementary"], "to": ["elementary", "middle"]}]

    def test_added_school(self):
        receipt = {"elementary": [{"school_id": "001", "roster_school": "Oak"}]}
        live = {"elementary": [{"school_id": "001", "roster_school": "Oak"},
                               {"school_id": "009", "roster_school": "New Dawn"}]}
        d = SP.roster_drift(live, receipt)
        assert d["added"] == [{"school_id": "009", "name": "New Dawn", "bands": ["elementary"]}]
        assert d["removed"] == [] and d["band_moved"] == []
