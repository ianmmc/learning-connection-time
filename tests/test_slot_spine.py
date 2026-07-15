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
        assert el["stats"] == {"n_slots": 2, "n_filled": 1, "n_projected": 0, "n_unfilled": 1,
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


def _asg(band, slot_id, fact, disposition, **kw):
    return {"band": band, "roster_school_id": slot_id, "norm_school_fact": fact,
            "school": kw.get("school", fact), "disposition": disposition,
            "reason": kw.get("reason", "r"), "actor": "ian", "created_at": "t"}


class TestIntentTieBreak:
    """REQ-145: the Stage-2 discovery-intent prior — tie-breaker ONLY, weight never override."""

    def _rosters(self):
        return _rosters({"elementary": [_rec("001", "Washington Elementary School"),
                                        _rec("002", "Washington Academy")]})

    def test_exactly_one_intent_hit_resolves(self):
        out = SP.project_slots(self._rosters(),
                               {"elementary": [{"school": "washington", "rec_key": "rk1"}]},
                               intent_by_reckey={"rk1": ["Washington Academy"]})
        by_id = {s["school_id"]: s for s in out["elementary"]["slots"]}
        assert by_id["002"]["slot_state"] == "filled"
        assert by_id["002"]["match"]["basis"] == ["exact_name", "discovery_intent"]
        assert by_id["001"]["slot_state"] == "unfilled" and by_id["001"]["match"] is None
        assert out["elementary"]["stats"]["n_ambiguous"] == 0

    def test_zero_intent_hits_stays_ambiguous(self):
        out = SP.project_slots(self._rosters(),
                               {"elementary": [{"school": "washington", "rec_key": "rk1"}]},
                               intent_by_reckey={"rk1": ["Lincoln Elementary School"]})
        assert out["elementary"]["stats"]["n_ambiguous"] == 1
        assert out["elementary"]["stats"]["n_filled"] == 0

    def test_both_candidates_in_intent_stays_ambiguous(self):
        # the URL was discovered for BOTH candidates — intent can't distinguish, must not guess
        out = SP.project_slots(self._rosters(),
                               {"elementary": [{"school": "washington", "rec_key": "rk1"}]},
                               intent_by_reckey={"rk1": ["Washington Academy",
                                                         "Washington Elementary School"]})
        assert out["elementary"]["stats"]["n_ambiguous"] == 1

    def test_intent_never_creates_a_match_for_clean_facts(self):
        # a clean 1:1 name match is matched on the name; intent doesn't change basis
        rosters = _rosters({"high": [_rec("101", "North High School", effective_band="high")]})
        out = SP.project_slots(rosters, {"high": [{"school": "north", "rec_key": "rk9"}]},
                               intent_by_reckey={"rk9": ["North High School"]})
        assert out["high"]["slots"][0]["match"]["basis"] == ["exact_name"]

    def test_extras_carry_intent_provenance(self):
        rosters = _rosters({"high": [_rec("101", "North High School", effective_band="high")]})
        out = SP.project_slots(rosters, {"high": [{"school": "lakeside", "rec_key": "rk2"}]},
                               intent_by_reckey={"rk2": ["North High School"]})
        assert out["high"]["extras"][0]["intent_schools"] == ["North High School"]


class TestDispositions:
    """REQ-145: human dispositions — precedence over name/intent; the escape hatch counts."""

    def _rosters(self):
        return _rosters({"elementary": [_rec("001", "Washington Elementary School"),
                                        _rec("002", "Washington Academy")]})

    def test_assign_binds_ambiguous_fact(self):
        out = SP.project_slots(self._rosters(), {"elementary": ["washington"]},
                               assignments=[_asg("elementary", "001", "washington", "assign")])
        by_id = {s["school_id"]: s for s in out["elementary"]["slots"]}
        assert by_id["001"]["slot_state"] == "filled"
        assert by_id["001"]["match"]["basis"] == ["disposition"]
        assert by_id["001"]["match"]["disposition"]["kind"] == "assign"
        assert out["elementary"]["stats"]["n_ambiguous"] == 0

    def test_assign_beats_intent(self):
        # disposition > intent: intent points at 002, the human said 001
        out = SP.project_slots(self._rosters(),
                               {"elementary": [{"school": "washington", "rec_key": "rk1"}]},
                               assignments=[_asg("elementary", "001", "washington", "assign")],
                               intent_by_reckey={"rk1": ["Washington Academy"]})
        by_id = {s["school_id"]: s for s in out["elementary"]["slots"]}
        assert by_id["001"]["slot_state"] == "filled"
        assert by_id["002"]["slot_state"] == "unfilled"

    def test_reject_collapses_ambiguity_to_survivor(self):
        out = SP.project_slots(self._rosters(), {"elementary": ["washington"]},
                               assignments=[_asg("elementary", "002", "washington", "reject")])
        by_id = {s["school_id"]: s for s in out["elementary"]["slots"]}
        assert by_id["001"]["slot_state"] == "filled"
        assert by_id["001"]["match"]["basis"] == ["exact_name", "disposition"]
        assert by_id["002"]["slot_state"] == "unfilled" and by_id["002"]["match"] is None

    def test_confirm_extra_becomes_human_confirmed_slot_and_counts(self):
        rosters = _rosters({"high": [_rec("101", "North High School", effective_band="high")]})
        out = SP.project_slots(rosters, {"high": ["north", "lakeside"]},
                               assignments=[_asg("high", "", "lakeside", "confirm_extra",
                                                 school="Lakeside Academy")])
        hi = out["high"]
        assert hi["extras"] == []                              # no longer an extra
        assert hi["stats"]["n_slots"] == 2                     # denominator +1 (Ian, 2026-07-15)
        assert hi["stats"]["n_filled"] == 2
        hc = [s for s in hi["slots"] if s["roster_source"] == "human_confirmed"]
        assert len(hc) == 1 and hc[0]["school_id"] == ""
        assert hc[0]["match"]["disposition"]["kind"] == "confirm_extra"

    def test_orphaned_assign_flagged_when_slot_gone(self):
        # the disposition references a school_id no longer in the live roster
        out = SP.project_slots(self._rosters(), {"elementary": []},
                               assignments=[_asg("elementary", "999", "washington", "assign")])
        o = out["elementary"]["orphaned_dispositions"]
        assert o[0]["kind"] == "slot_gone_from_roster" and o[0]["roster_school_id"] == "999"

    def test_confirm_extra_flagged_when_nces_catches_up(self):
        # the confirmed-extra's key NOW matches a real roster slot — double-count risk, flag it
        rosters = _rosters({"high": [_rec("101", "Lakeside Academy", effective_band="high")]})
        out = SP.project_slots(rosters, {"high": ["lakeside"]},
                               assignments=[_asg("high", "", "lakeside", "confirm_extra")])
        kinds = [o["kind"] for o in out["high"]["orphaned_dispositions"]]
        assert "extra_now_in_roster" in kinds


class TestBandFactProjection:
    """REQ-146: band-grain facts — conjunction fills named slots; blankets project; the band
    fact's own name is never an extra."""

    def _rosters3(self):
        return _rosters({"elementary": [_rec("001", "Milagro Elementary School"),
                                        _rec("002", "Ortiz Elementary School"),
                                        _rec("003", "Sunset Elementary School")]})

    def test_conjunction_fills_named_slots(self):
        bf = {"norm_school_fact": "milagro and ortiz", "school_display": "milagro and ortiz schools",
              "kind": "conjunction",
              "campuses": ["Milagro Elementary School", "Ortiz Elementary School"]}
        out = SP.project_slots(self._rosters3(), {"elementary": ["milagro and ortiz schools"]},
                               band_facts={"elementary": bf})
        by_id = {s["school_id"]: s for s in out["elementary"]["slots"]}
        assert by_id["001"]["slot_state"] == "filled"
        assert by_id["001"]["match"]["basis"] == ["conjunction"]
        assert by_id["002"]["slot_state"] == "filled"
        assert by_id["003"]["slot_state"] == "unfilled"       # conjunction never blankets
        assert out["elementary"]["extras"] == []              # the group name is not an extra
        assert out["elementary"]["stats"]["n_filled"] == 2

    def test_blanket_projects_onto_unheard_slots_only(self):
        bf = {"norm_school_fact": "k8", "school_display": "k8 schools",
              "kind": "group_descriptor", "campuses": []}
        out = SP.project_slots(self._rosters3(),
                               {"elementary": ["k8 schools", "milagro"]},
                               band_facts={"elementary": bf})
        by_id = {s["school_id"]: s for s in out["elementary"]["slots"]}
        assert by_id["001"]["slot_state"] == "filled"          # direct fact wins the slot
        assert by_id["002"]["slot_state"] == "projected"
        assert by_id["002"]["projected_by"] == "k8"
        assert by_id["003"]["slot_state"] == "projected"
        st = out["elementary"]["stats"]
        assert st["n_filled"] == 1 and st["n_projected"] == 2 and st["n_unfilled"] == 0

    def test_blanket_does_not_project_over_ambiguous(self):
        rosters = _rosters({"elementary": [_rec("001", "Washington Elementary School"),
                                           _rec("002", "Washington Academy")]})
        bf = {"norm_school_fact": "all elementary", "school_display": "All Elementary Schools",
              "kind": "group_descriptor", "campuses": []}
        out = SP.project_slots(rosters, {"elementary": ["All Elementary Schools", "washington"]},
                               band_facts={"elementary": bf})
        # the ambiguous direct fact is STRONGER information than the blanket — slots stay ambiguous
        assert out["elementary"]["stats"]["n_ambiguous"] == 1
        assert out["elementary"]["stats"]["n_projected"] == 0


class TestConflictLadder:
    """REQ-146: fixed rung order sufficiency → hub-exception → vintage; advice only."""

    def test_rung_a_reliable_mode_direct_on_mode(self):
        v = SP.resolve_slot_conflict({"gross": 400, "school": "Oak"}, {"gross": 380},
                                     {"n_sampled": 4, "plurality_share": 0.75,
                                      "gross_minutes": 400})
        assert v["rung"] == "sample_sufficiency" and v["leans"] == "direct"

    def test_rung_a_blanket_on_mode(self):
        v = SP.resolve_slot_conflict({"gross": 380, "school": "Oak"}, {"gross": 400},
                                     {"n_sampled": 4, "plurality_share": 0.75,
                                      "gross_minutes": 400})
        assert v["rung"] == "sample_sufficiency" and v["leans"] == "band_fact"

    def test_rung_a_skipped_when_band_thin_then_b_fires(self):
        # n < 3: sufficiency can't decide; the exception list (v4's reading) names the school
        v = SP.resolve_slot_conflict({"gross": 400, "school": "Oak K-8"}, {"gross": 380},
                                     {"n_sampled": 2, "plurality_share": 1.0,
                                      "gross_minutes": 400},
                                     exceptions=["Oak K-8"])
        assert v["rung"] == "hub_exception" and v["leans"] == "direct"

    def test_rung_c_vintage_newer_year_leans(self):
        v = SP.resolve_slot_conflict({"gross": 400, "school": "Oak", "school_year": "2025-26"},
                                     {"gross": 380, "school_year": "2024-25"},
                                     {"n_sampled": 1, "plurality_share": None,
                                      "gross_minutes": None})
        assert v["rung"] == "vintage" and v["leans"] == "direct"

    def test_rung_c_dated_beats_undated(self):
        v = SP.resolve_slot_conflict({"gross": 400, "school": "Oak"},
                                     {"gross": 380, "school_year": "2025-26"},
                                     {"n_sampled": 1, "plurality_share": None,
                                      "gross_minutes": None})
        assert v["rung"] == "vintage" and v["leans"] == "band_fact"

    def test_unresolved_when_no_rung_decides(self):
        v = SP.resolve_slot_conflict({"gross": 400, "school": "Oak"}, {"gross": 380},
                                     {"n_sampled": 2, "plurality_share": 1.0,
                                      "gross_minutes": 400})
        assert v["rung"] == "unresolved" and v["leans"] is None

    def test_rung_a_neither_on_mode_falls_through(self):
        # a reliable mode neither side sits on decides nothing (both are outliers)
        v = SP.resolve_slot_conflict({"gross": 350, "school": "Oak"}, {"gross": 380},
                                     {"n_sampled": 5, "plurality_share": 0.8,
                                      "gross_minutes": 400})
        assert v["rung"] == "unresolved"


class TestCampusShorthand:
    def test_page_shorthand_campus_fills_full_roster_name(self):
        # REQ-148 (live Santa Fe, 2026-07-15): the page writes "Milagro"; the roster writes
        # "Milagro Middle School" — the norm key joins them; a colliding key fills nothing.
        rosters = _rosters({"middle": [
            _rec("101", "Milagro Middle School", effective_band="middle"),
            _rec("102", "Ortiz Middle School", effective_band="middle"),
            _rec("103", "Washington Middle School", effective_band="middle"),
            _rec("104", "Washington Academy", effective_band="middle")]})
        bf = {"norm_school_fact": "milagro and ortiz", "school_display": "milagro and ortiz schools",
              "kind": "conjunction", "campuses": ["Milagro", "Ortiz Middle", "Washington"]}
        out = SP.project_slots(rosters, {"middle": ["milagro and ortiz schools"]},
                               band_facts={"middle": bf})
        by_id = {s["school_id"]: s for s in out["middle"]["slots"]}
        assert by_id["101"]["slot_state"] == "filled"      # Milagro (shorthand) joins
        assert by_id["102"]["slot_state"] == "filled"      # Ortiz Middle joins
        assert by_id["103"]["slot_state"] == "unfilled"    # "Washington" collides (103/104) — no guess
        assert by_id["104"]["slot_state"] == "unfilled"
