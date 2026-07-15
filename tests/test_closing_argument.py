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

    def test_single_model_stated_minutes_is_not_agreement(self):
        # PR #252 review: one model reading a stated number is single-source evidence, not cross-model
        # agreement — agree must be None (unknown), never True.
        f = _fact("elementary", "oak", 435, rec_key="D:oak")
        f["evidence_json"] = json.dumps({
            "m1": {"quote": "q", "locus": "", "stated_minutes": 435, "stated_minutes_quote": "sq"},
            "m2": {"quote": "", "locus": "", "stated_minutes": None, "stated_minutes_quote": ""}})
        out = CA.build_closing_argument(
            "D", merged_accepted=[f], merged_unresolved=[], nces_total=3,
            nces_by_level={"Elementary": 3}, schools_by_band={})
        ce = out["bands"]["elementary"]["schools"][0]["council_evidence"]
        assert ce["stated_minutes"] == 435
        assert ce["stated_minutes_agree"] is None and ce["n_models_stated"] == 1

    def test_winning_facts_own_handoff_evidence_beats_reckey_fallback(self):
        # PR #252 review: the evidence shown must be the WINNING fact's own run's handoff record — the
        # rec_key fallback (which an earlier draft resolved in lexicographic hash order) is only for a
        # fact whose own receipt file is missing.
        f = _fact("middle", "north", 410, rec_key="D:north")
        f["handoff_evidence"] = {"url": "https://own-run.org/bell", "handoff_hash": "h-own"}
        fallback = {"D:north": {"url": "https://other-run.org/bell", "handoff_hash": "h-other"}}
        out = CA.build_closing_argument(
            "D", merged_accepted=[f], merged_unresolved=[], nces_total=2,
            nces_by_level={"Middle": 2}, schools_by_band={}, evidence_by_reckey=fallback)
        ev = out["bands"]["middle"]["schools"][0]["evidence"]
        assert ev["url"] == "https://own-run.org/bell"

    def test_source_file_folds_from_the_winning_fact(self):
        # PR #252 review: the "read via <reader>" line comes from the winning fact itself, never an
        # unordered sibling row sharing the rec_key.
        f = _fact("middle", "north", 410, rec_key="D:north")
        f["source_file"] = "pdftotext.txt"
        f["handoff_evidence"] = {"url": "https://ex.org/bell"}
        out = CA.build_closing_argument(
            "D", merged_accepted=[f], merged_unresolved=[], nces_total=2,
            nces_by_level={"Middle": 2}, schools_by_band={})
        assert out["bands"]["middle"]["schools"][0]["evidence"]["source_file"] == "pdftotext.txt"


class TestOverrideFeedsMode:
    def _ov(self, start=None, end=None, reason="recency"):
        return json.dumps({"start_time": start, "end_time": end, "reason": reason, "actor": "ian"})

    def test_overrides_move_the_band_mode_to_clean_modal(self):
        # The Santa Fe case: two schools already at 445, two stale at 440 corrected UP via overrides —
        # the band must read a clean modal 445, not a mean_tiebreak 442 (revised 2026-07-13).
        a = _fact("middle", "milagro", 445)                        # 08:00-15:25, current
        b = _fact("middle", "ortiz", 445)
        c = _fact("middle", "k8", 440)                             # 08:00-15:20, stale
        c["human_determination"] = self._ov(end="15:25")          # -> 08:00-15:25 = 445
        d = _fact("middle", "combined", 440)
        d["human_determination"] = self._ov(start="08:00", end="15:25")   # -> 445
        out = CA.build_closing_argument(
            "D", merged_accepted=[a, b, c, d], merged_unresolved=[], nces_total=2,
            nces_by_level={"Middle": 2}, schools_by_band={})
        mid = out["bands"]["middle"]
        assert mid["gross_minutes"] == 445 and mid["method"] == "modal"
        assert mid["sampling"]["plurality_share"] == 1.0

    def test_council_original_preserved_on_the_overridden_school(self):
        c = _fact("middle", "k8", 440, rec_key="D:k8")
        c["human_determination"] = self._ov(end="15:25")
        out = CA.build_closing_argument(
            "D", merged_accepted=[c], merged_unresolved=[], nces_total=1,
            nces_by_level={"Middle": 1}, schools_by_band={})
        sc = out["bands"]["middle"]["schools"][0]
        assert sc["gross"] == 445 and sc["end_time"] == "15:25"    # effective
        assert sc["council_gross"] == 440 and sc["council_end_time"] == "15:20"   # original kept

    def test_note_only_override_does_not_move_the_mode(self):
        # a reason with no times must annotate, not recompute (byte-identical gross)
        c = _fact("middle", "k8", 440)
        c["human_determination"] = json.dumps({"reason": "looks off", "actor": "ian"})
        out = CA.build_closing_argument(
            "D", merged_accepted=[c], merged_unresolved=[], nces_total=1,
            nces_by_level={"Middle": 1}, schools_by_band={})
        assert out["bands"]["middle"]["gross_minutes"] == 440
        sc = out["bands"]["middle"]["schools"][0]
        assert sc["override_applied"] is False and sc["override_error"] is None

    def test_valid_override_marks_applied(self):
        c = _fact("middle", "k8", 440)
        c["human_determination"] = self._ov(end="15:25")   # 08:00-15:25 = 445, plausible
        out = CA.build_closing_argument(
            "D", merged_accepted=[c], merged_unresolved=[], nces_total=1,
            nces_by_level={"Middle": 1}, schools_by_band={})
        sc = out["bands"]["middle"]["schools"][0]
        assert sc["override_applied"] is True and sc["override_error"] is None
        assert sc["gross"] == 445

    def test_unparseable_stored_override_surfaces_error_and_keeps_council(self):
        # 15c67c4 review: a stored "3pm" used to display as applied while gross silently reverted —
        # now the council values stand AND the error is a visible field, never a silent lie.
        c = _fact("middle", "k8", 440)
        c["human_determination"] = self._ov(end="3pm")
        out = CA.build_closing_argument(
            "D", merged_accepted=[c], merged_unresolved=[], nces_total=1,
            nces_by_level={"Middle": 1}, schools_by_band={})
        sc = out["bands"]["middle"]["schools"][0]
        assert out["bands"]["middle"]["gross_minutes"] == 440       # mode unmoved
        assert sc["start_time"] == "08:00" and sc["end_time"] == "15:20"   # council shown, not "3pm"
        assert sc["override_applied"] is False
        assert sc["override_error"] == "override_unparseable"

    def test_implausible_stored_override_gated_not_applied(self):
        # 15c67c4 review: an override yielding gross=125 must NOT become the modal determination —
        # the same REQ-055 gate the council path enforces applies to the human path.
        c = _fact("middle", "k8", 440)
        c["human_determination"] = self._ov(end="10:05")   # 08:00-10:05 = 125 min
        out = CA.build_closing_argument(
            "D", merged_accepted=[c], merged_unresolved=[], nces_total=1,
            nces_by_level={"Middle": 1}, schools_by_band={})
        sc = out["bands"]["middle"]["schools"][0]
        assert out["bands"]["middle"]["gross_minutes"] == 440       # council value stands
        assert sc["override_applied"] is False
        assert sc["override_error"] == "override_implausible"


class TestFingerprint:
    def test_stable_for_same_determination(self):
        acc = [_fact("elementary", "oak", 435, rec_key="D:oak")]
        kw = dict(merged_unresolved=[], nces_total=3, nces_by_level={"Elementary": 3}, schools_by_band={})
        fp1 = CA.fingerprint(CA.build_closing_argument("D", merged_accepted=acc, **kw))
        fp2 = CA.fingerprint(CA.build_closing_argument("D", merged_accepted=list(acc), **kw))
        assert fp1 == fp2

    def test_override_changes_fingerprint(self):
        # PR #252 review: an override recorded AFTER approval is a new human determination — it must
        # flip the approval stale. The old basis (band/gross/schools only) left the hash unchanged.
        base = _fact("elementary", "oak", 435, rec_key="D:oak")
        kw = dict(merged_unresolved=[], nces_total=3, nces_by_level={"Elementary": 3}, schools_by_band={})
        fp_before = CA.fingerprint(CA.build_closing_argument("D", merged_accepted=[base], **kw))
        overridden = dict(base)
        overridden["human_determination"] = json.dumps(
            {"start_time": "08:05", "end_time": "15:10", "reason": "wrong bell read", "actor": "ian"})
        fp_after = CA.fingerprint(CA.build_closing_argument("D", merged_accepted=[overridden], **kw))
        assert fp_before != fp_after


class TestBandExclusion:
    """#257: human 'exclude school from band' — a fact whose observation is CORRECT but whose band
    membership is stale (Coffee County: Kinston/Zion Chapel tagged PK-12 in 2023-24 NCES, presenting
    as high schools in 2025-26, contaminating the elementary band with high-school hours)."""

    KW = dict(merged_unresolved=[], nces_total=4, nces_by_level={"Elementary": 3}, schools_by_band={})

    def _excl(self, band, school, reason="reconfigured to high school (district site, 2025-26)"):
        return {"band": band, "school": school, "reason": reason, "actor": "ian",
                "created_at": "2026-07-14T00:00:00Z"}

    def test_excluded_school_leaves_the_mode_but_stays_visible(self):
        # Coffee County shape: NBES et al. at 435; Kinston + Zion Chapel at 465 (high-school hours)
        # drag the elementary mode. Excluding them recomputes the mode over the remaining schools.
        acc = ([_fact("elementary", s, 435) for s in ("nbes", "cces")]
               + [_fact("elementary", s, 465) for s in ("kinston", "zion chapel")])
        polluted = CA.build_closing_argument("D", merged_accepted=acc, **self.KW)
        assert polluted["bands"]["elementary"]["method"] == "mean_tiebreak"  # 2-2 tie: the distortion

        out = CA.build_closing_argument(
            "D", merged_accepted=acc,
            exclusions=[self._excl("elementary", "kinston"), self._excl("elementary", "Zion Chapel")],
            **self.KW)
        el = out["bands"]["elementary"]
        assert el["gross_minutes"] == 435 and el["method"] == "modal"
        assert el["sampling"]["n_sampled"] == 2                    # excluded don't count
        # excluded schools stay VISIBLE in the band (struck-through at render), never silently dropped
        excluded_rows = [s for s in el["schools"] if s.get("excluded")]
        assert {s["school"] for s in excluded_rows} == {"kinston", "zion chapel"}
        assert all(s["excluded"]["reason"] for s in excluded_rows)
        included_rows = [s for s in el["schools"] if not s.get("excluded")]
        assert {s["school"] for s in included_rows} == {"nbes", "cces"}

    def test_exclusion_is_scoped_per_band(self):
        # a genuine K-12 can be excluded from elementary but kept in high (#257 scoping requirement)
        acc = [_fact("elementary", "k12 school", 465), _fact("elementary", "oak", 435),
               _fact("high", "k12 school", 465)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, exclusions=[self._excl("elementary", "k12 school")],
            merged_unresolved=[], nces_total=3, nces_by_level={"Elementary": 2, "High": 1},
            schools_by_band={})
        assert out["bands"]["elementary"]["gross_minutes"] == 435
        assert out["bands"]["high"]["gross_minutes"] == 465        # untouched in its real band

    def test_fully_excluded_band_vanishes_and_surfaces_in_negative_space(self):
        acc = [_fact("elementary", "kinston", 465)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, exclusions=[self._excl("elementary", "kinston")], **self.KW)
        assert "elementary" not in out["bands"]
        assert "elementary" in out["negative_space"]["unsatisfied_bands"] or \
               "elementary" not in out["negative_space"]["claimed_bands"]
        # the audit surface: every applied exclusion is in the negative space regardless of band fate
        ns = out["negative_space"]["band_exclusions"]
        assert [(e["band"], e["school"]) for e in ns] == [("elementary", "kinston")]

    def test_exclusion_matches_on_normalized_school_name(self):
        # the stored exclusion normalizes like the merge does — 'Kinston School' vs 'kinston'
        acc = [_fact("elementary", "Kinston School", 465), _fact("elementary", "oak", 435)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, exclusions=[self._excl("elementary", "kinston school")], **self.KW)
        assert out["bands"]["elementary"]["gross_minutes"] == 435

    def test_exclusion_changes_fingerprint(self):
        # same PR #252 posture as overrides: an exclusion recorded after approval must flip it stale
        acc = [_fact("elementary", "kinston", 465), _fact("elementary", "oak", 435)]
        fp_before = CA.fingerprint(CA.build_closing_argument("D", merged_accepted=acc, **self.KW))
        fp_after = CA.fingerprint(CA.build_closing_argument(
            "D", merged_accepted=acc, exclusions=[self._excl("elementary", "kinston")], **self.KW))
        assert fp_before != fp_after


class TestNameLevelMismatch:
    """#258: detect-and-flag when a school NAME's level token contradicts its NCES level or its
    assigned band — the detector half of the Coffee County class (#257 is the correction half).
    Never auto-rejects; a name token is a hint, not ground truth."""

    def test_zion_chapel_signature_flags(self):
        # the acceptance case: "High School" name + ambiguous PK-12 NCES tag + elementary band
        from infrastructure.acquisition.common import school_sampling as SS
        m = SS.name_level_mismatch("Zion Chapel High School", "Other", ["elementary"])
        assert m and m["implied_bands"] == ["high"]
        assert any(c["kind"] == "band" and c["band"] == "elementary" for c in m["conflicts"])

    def test_name_vs_nces_level_contradiction_flags(self):
        from infrastructure.acquisition.common import school_sampling as SS
        m = SS.name_level_mismatch("Lincoln High School", "Elementary", [])
        assert m and any(c["kind"] == "nces_level" for c in m["conflicts"])

    def test_legitimate_names_do_not_flag(self):
        from infrastructure.acquisition.common import school_sampling as SS
        # no false alarms on normal names (acceptance requirement)
        assert SS.name_level_mismatch("Highland Elementary", "Elementary", ["elementary"]) is None
        assert SS.name_level_mismatch("Oak Park Junior High", "Middle", ["middle"]) is None
        assert SS.name_level_mismatch("zion chapel k12", "Other", ["elementary", "high"]) is None
        assert SS.name_level_mismatch("Washington School", "Other", ["middle"]) is None  # no token
        assert SS.name_level_mismatch("", None, ["high"]) is None

    def test_junior_high_is_middle_not_high(self):
        from infrastructure.acquisition.common import school_sampling as SS
        assert SS.name_level_mismatch("Roosevelt Junior High School", "Middle", ["middle"]) is None
        m = SS.name_level_mismatch("Roosevelt Junior High School", "High", [])
        assert m and any(c["kind"] == "nces_level" for c in m["conflicts"])

    def test_wired_into_negative_space_from_roster_and_facts(self):
        # roster side: Stage 1 placed a "High School"-named school in elementary;
        # facts side: an accepted fact named "X High School" landed in the elementary band.
        acc = [_fact("elementary", "Sunrise High School", 434),
               _fact("elementary", "oak", 435)]
        sbb = {"elementary": {"schools": [
            {"school": "Zion Chapel High School", "level": "Other"},
            {"school": "Oak Elementary", "level": "Elementary"}]}}
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=4,
            nces_by_level={"Elementary": 3}, schools_by_band=sbb)
        flagged = {m["school"] for m in out["negative_space"]["name_level_mismatches"]}
        assert flagged == {"Zion Chapel High School", "Sunrise High School"}


class TestHumanAddedFacts:
    """#474: last-resort hand-entered schools/bands — cited-source, plausibility-gated upstream,
    voting in the mode like any human determination (§2a.3), visibly tagged, in the fingerprint."""

    KW = dict(merged_unresolved=[], nces_total=3, nces_by_level={"Elementary": 2, "Middle": 1},
              schools_by_band={})

    def _ha(self, band, school, start, end, url="https://tusd.org/hub.pdf"):
        return {"band": band, "school": school, "start_time": start, "end_time": end,
                "source_url": url, "reason": "elementary table unreadable by council",
                "actor": "ian", "created_at": "2026-07-14T00:00:00Z"}

    def test_human_add_fills_an_empty_band_and_votes(self):
        # TUSD shape: middle extracted, elementary empty — two hand-adds create the band
        acc = [_fact("middle", "kawameeh", 424)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc,
            human_added=[self._ha("elementary", "battle hill", "08:45", "15:10"),
                         self._ha("elementary", "washington", "08:45", "15:10")], **self.KW)
        el = out["bands"]["elementary"]
        assert el["gross_minutes"] == 385 and el["method"] == "modal"
        assert el["sampling"]["n_sampled"] == 2
        rows = el["schools"]
        assert all(r.get("human_added") for r in rows)
        assert all(r["human_added"]["source_url"] == "https://tusd.org/hub.pdf" for r in rows)
        # elementary no longer unsatisfied
        assert "elementary" not in out["negative_space"]["unsatisfied_bands"]

    def test_human_add_votes_alongside_extracted_facts(self):
        acc = [_fact("middle", "a", 424), _fact("middle", "b", 430)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc,
            human_added=[self._ha("middle", "c", "08:00", "15:10")], **self.KW)  # 430
        m = out["bands"]["middle"]
        assert m["gross_minutes"] == 430 and m["method"] == "modal"   # the hand-add broke the tie
        assert sum(1 for r in m["schools"] if r.get("human_added")) == 1

    def test_exclusion_beats_human_add_on_same_school(self):
        # belt-and-braces: an excluded (band, school) can't be re-injected by a stale hand-add
        acc = []
        out = CA.build_closing_argument(
            "D", merged_accepted=acc,
            human_added=[self._ha("elementary", "battle hill", "08:45", "15:10")],
            exclusions=[{"band": "elementary", "school": "battle hill", "reason": "r",
                         "actor": "ian", "created_at": "2026-07-14T00:00:00Z"}], **self.KW)
        assert "elementary" not in out["bands"]

    def test_human_add_changes_fingerprint(self):
        acc = [_fact("middle", "a", 424)]
        fp1 = CA.fingerprint(CA.build_closing_argument("D", merged_accepted=acc, **self.KW))
        fp2 = CA.fingerprint(CA.build_closing_argument(
            "D", merged_accepted=acc,
            human_added=[self._ha("elementary", "battle hill", "08:45", "15:10")], **self.KW))
        assert fp1 != fp2


class TestRecoverableBandDetector:
    """#473 detector: an unsatisfied band whose SIBLING bands were extracted from an already-captured
    rep is flagged 'the data may be there, re-read it' — surfaced for the reviewer, like #258."""

    def test_tusd_shape_flags_elementary_with_the_sibling_rep(self):
        acc = [_fact("middle", "kawameeh", 424, rec_key="D:hub"),
               _fact("high", "uhs", 430, rec_key="D:hub")]
        ev = {"D:hub": {"url": "https://tusd.org/hub", "reps": []}}
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=6,
            nces_by_level={"Elementary": 3, "Middle": 2, "High": 1},
            schools_by_band={}, evidence_by_reckey=ev)
        rb = out["negative_space"]["recoverable_bands"]
        assert [r["band"] for r in rb] == ["elementary"]
        assert rb[0]["from_reps"][0]["rec_key"] == "D:hub"
        assert rb[0]["from_reps"][0]["url"] == "https://tusd.org/hub"

    def test_no_flag_when_all_claimed_bands_satisfied(self):
        acc = [_fact("elementary", "e", 400, rec_key="D:hub")]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=1,
            nces_by_level={"Elementary": 1}, schools_by_band={})
        assert out["negative_space"]["recoverable_bands"] == []


class TestBandRosterDenominator:
    """#253 Part B: the live band-SERVING denominator replaces the clean-LEVEL count when the
    roster is supplied; the LEVEL count stays alongside for continuity + fallback."""

    _ROSTERS = {"middle": {"total": 9, "by_source": {"level_clean": 2, "grade_span": 7},
                           "schools": ["Ortiz Middle", "Milagro Middle", "Gonzales K8"]},
                "_unattributed": [], "_year": "2024_25"}

    def test_roster_denominator_replaces_level_count(self):
        # the Santa Fe signature: 4 sampled, LEVEL says 2 (200%), the serving roster says 9
        acc = [_fact("middle", s, 445) for s in ("milagro", "ortiz", "k8 schools", "milagro and ortiz schools")]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=25,
            nces_by_level={"Middle": 2}, schools_by_band={}, band_rosters=self._ROSTERS)
        s = out["bands"]["middle"]["sampling"]
        assert s["n_total"] == 9 and s["n_total_level_only"] == 2
        assert s["coverage"] == round(4 / 9, 3)          # not 2.0
        assert s["denominator"]["source"] == "band_roster"
        assert s["denominator"]["by_source"] == {"level_clean": 2, "grade_span": 7}
        assert s["denominator"]["nces_year"] == "2024_25"

    def test_no_roster_falls_back_to_level_count_marked_as_such(self):
        acc = [_fact("middle", "m1", 410)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=3,
            nces_by_level={"Middle": 2}, schools_by_band={}, band_rosters=None)
        s = out["bands"]["middle"]["sampling"]
        assert s["n_total"] == 2 and s["denominator"]["source"] == "nces_level"

    def test_criteria_disclaimer_and_unattributed_surface(self):
        acc = [_fact("middle", "m1", 410)]
        rosters = {**self._ROSTERS, "_unattributed": ["Weird Ungraded Center"]}
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=3,
            nces_by_level={}, schools_by_band={}, band_rosters=rosters)
        assert "virtual" in out["provenance"]["denominator"]["criteria"]
        assert out["provenance"]["denominator"]["source"] == "band_roster"
        assert out["negative_space"]["unattributed_roster_schools"] == ["Weird Ungraded Center"]

    def test_coverage_gap_uses_roster_total(self):
        acc = [_fact("middle", "m1", 410)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=9,
            nces_by_level={"Middle": 2}, schools_by_band={}, band_rosters=self._ROSTERS)
        assert out["negative_space"]["coverage_gaps"]["middle"]["n_total"] == 9


class TestCombinedScopeFlags:
    """#253 A1: combined-scope extracted names flag (detect-and-flag) — the row keeps its vote."""

    def test_group_and_conjunction_flag_but_keep_voting(self):
        acc = [_fact("middle", s, 445) for s in ("milagro", "ortiz")] + \
              [_fact("middle", "k8 schools", 445), _fact("middle", "milagro and ortiz schools", 445)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=25,
            nces_by_level={"Middle": 2}, schools_by_band={})
        cs = out["negative_space"]["combined_scope_facts"]
        assert {c["school"] for c in cs} == {"k8 schools", "milagro and ortiz schools"}
        assert all(not c["excluded"] for c in cs)
        # still voting: all four count in the band
        assert out["bands"]["middle"]["sampling"]["n_sampled"] == 4
        rows = {s["school"]: s for s in out["bands"]["middle"]["schools"]}
        assert rows["k8 schools"]["combined_scope"]["kind"] == "group_descriptor"
        assert rows["milagro"]["combined_scope"] is None

    def test_excluded_combined_scope_is_marked(self):
        acc = [_fact("middle", "milagro", 445), _fact("middle", "k8 schools", 440)]
        excl = [{"band": "middle", "school": "k8 schools", "reason": "duplicate of K-8 rows",
                 "actor": "ian", "created_at": "2026-07-14"}]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=25,
            nces_by_level={"Middle": 2}, schools_by_band={}, exclusions=excl)
        cs = out["negative_space"]["combined_scope_facts"]
        assert cs and cs[0]["excluded"] is True
        assert out["bands"]["middle"]["sampling"]["n_sampled"] == 1  # exclusion still removes the vote

    def test_conjunction_resolves_campuses_against_live_roster(self):
        acc = [_fact("middle", "Milagro Middle and Edward Ortiz Middle", 445)]
        rosters = {"middle": {"total": 2, "by_source": {"level_clean": 2, "grade_span": 0},
                              "schools": ["MILAGRO MIDDLE", "EDWARD ORTIZ MIDDLE"]},
                   "_unattributed": [], "_year": "2024_25"}
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=2,
            nces_by_level={"Middle": 2}, schools_by_band={}, band_rosters=rosters)
        cs = out["negative_space"]["combined_scope_facts"][0]
        assert cs["kind"] == "conjunction"
        assert set(cs["campuses"]) == {"MILAGRO MIDDLE", "EDWARD ORTIZ MIDDLE"}

    def test_fingerprint_unmoved_by_flags(self):
        # flags are derived observations, not determinations — an approval must not go stale
        # because the detector shipped (denominator/coverage are likewise outside the basis)
        acc = [_fact("middle", "k8 schools", 445)]
        with_flag = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=2,
            nces_by_level={"Middle": 2}, schools_by_band={})
        no_ns = dict(with_flag)
        no_ns["negative_space"] = {**with_flag["negative_space"], "combined_scope_facts": []}
        for b in no_ns["bands"].values():
            for s in b["schools"]:
                s.pop("combined_scope", None)
        assert CA.fingerprint(with_flag) == CA.fingerprint(no_ns)


class TestSchoolYearSurfaces:
    """#254: the year chip, the superseded-facts surface, the year-conflict flags, and the
    council applies_to union into the #253 combined-scope surface."""

    def test_school_year_rides_the_school_row(self):
        f = _fact("elementary", "oak", 435)
        f["school_year"] = "2025-26"
        out = CA.build_closing_argument(
            "D", merged_accepted=[f], merged_unresolved=[], nces_total=3,
            nces_by_level={"Elementary": 3}, schools_by_band={})
        (row,) = out["bands"]["elementary"]["schools"]
        assert row["school_year"] == "2025-26"

    def test_pre_v3_fact_renders_no_year(self):
        out = CA.build_closing_argument(
            "D", merged_accepted=[_fact("elementary", "oak", 435)], merged_unresolved=[],
            nces_total=3, nces_by_level={"Elementary": 3}, schools_by_band={})
        assert out["bands"]["elementary"]["schools"][0]["school_year"] is None

    def test_superseded_facts_surface_with_both_years_and_grosses(self):
        win = _fact("elementary", "oak", 445)
        win["school_year"] = "2025-26"
        lose = _fact("elementary", "oak", 440, ext=1)
        lose["school_year"] = "2023-24"
        lose["source_file"] = "capture.html"
        out = CA.build_closing_argument(
            "D", merged_accepted=[win], merged_unresolved=[], nces_total=3,
            nces_by_level={"Elementary": 3}, schools_by_band={}, merged_superseded=[lose])
        (s,) = out["negative_space"]["superseded_facts"]
        assert s["school_year"] == "2023-24" and s["gross"] == 440
        assert s["superseded_by"]["school_year"] == "2025-26" and s["superseded_by"]["gross"] == 445
        assert s["source_file"] == "capture.html"           # the format hint rides both sides

    def test_year_conflicts_pass_through_negative_space(self):
        conflicts = [{"band": "elementary", "school": "oak", "years": ["2023-24", "2025-26"],
                      "mixes_unknown": False, "resolved": True,
                      "sides": [{"extraction_id": 1, "school_year": "2023-24", "gross": 440,
                                 "source_file": "page.html"}]}]
        out = CA.build_closing_argument(
            "D", merged_accepted=[_fact("elementary", "oak", 445)], merged_unresolved=[],
            nces_total=3, nces_by_level={"Elementary": 3}, schools_by_band={},
            year_conflicts=conflicts)
        assert out["negative_space"]["year_conflicts"] == conflicts
        # absent ingredients stay honest empties, not missing keys
        out2 = CA.build_closing_argument(
            "D", merged_accepted=[_fact("elementary", "oak", 445)], merged_unresolved=[],
            nces_total=3, nces_by_level={"Elementary": 3}, schools_by_band={})
        assert out2["negative_space"]["superseded_facts"] == []
        assert out2["negative_space"]["year_conflicts"] == []

    def test_council_applies_to_merges_into_the_combined_scope_surface(self):
        # a council "multiple" reading on a name the deterministic detector can't flag
        f = _fact("middle", "milagro", 445)
        f["applies_to"] = "multiple"
        out = CA.build_closing_argument(
            "D", merged_accepted=[f], merged_unresolved=[], nces_total=2,
            nces_by_level={"Middle": 2}, schools_by_band={})
        (cs,) = out["negative_space"]["combined_scope_facts"]
        assert cs["kind"] == "council_scope" and cs["source"] == "council"
        assert out["bands"]["middle"]["schools"][0]["combined_scope"]["source"] == "council"
        # union: the name detector AND the council both flagging -> one entry, source names both
        g = _fact("middle", "k8 schools", 445)
        g["applies_to"] = "multiple"
        out2 = CA.build_closing_argument(
            "D", merged_accepted=[g], merged_unresolved=[], nces_total=2,
            nces_by_level={"Middle": 2}, schools_by_band={})
        (cs2,) = out2["negative_space"]["combined_scope_facts"]
        assert cs2["kind"] == "group_descriptor" and cs2["source"] == "name+council"

    def test_santa_fe_end_to_end_newer_year_wins_the_mode_cleanly(self):
        # the motivating case, synthetically: the same two schools extracted twice — a stale
        # 2023-24 page read 440, a current 2025-26 page read 445. Year precedence must hand the
        # mode 445 OUTRIGHT (modal, never a 2-2 mean_tiebreak) and surface the 440s as superseded.
        from infrastructure.acquisition.stage8_aggregate import aggregate as AGG
        raw = []
        for ext, gross, year, src in ((1, 440, "2023-24", "stale.html"),
                                      (2, 445, "2025-26", "current.pdf")):
            for school in ("milagro", "ortiz"):
                f = _fact("middle", school, gross, ext=ext)
                f["school_year"] = year
                f["source_file"] = src
                raw.append(f)
        accepted, unresolved, superseded = AGG.merge_fact_runs(raw, with_superseded=True)
        conflicts = AGG.detect_year_conflicts(raw)
        out = CA.build_closing_argument(
            "D", merged_accepted=accepted, merged_unresolved=unresolved, nces_total=9,
            nces_by_level={"Middle": 2}, schools_by_band={},
            merged_superseded=superseded, year_conflicts=conflicts)
        mid = out["bands"]["middle"]
        assert mid["gross_minutes"] == 445 and mid["method"] == "modal"     # no mean_tiebreak
        assert mid["sampling"]["n_sampled"] == 2
        sup = out["negative_space"]["superseded_facts"]
        assert {(s["school"], s["gross"]) for s in sup} == {("milagro", 440), ("ortiz", 440)}
        assert all(s["superseded_by"]["gross"] == 445 for s in sup)
        assert len(out["negative_space"]["year_conflicts"]) == 2            # both schools flagged
        assert all(c["resolved"] for c in out["negative_space"]["year_conflicts"])
class TestMismatchFlagCarriesSpanAndDedupes:
    """#258 copy rework (Ian, 2026-07-14): the flag explains itself with the school's grade span
    (a 7-12 'High' legitimately serves middle), and the roster/fact surfaces dedupe on the
    NORMALIZED name — one school, one note, roster surface (span-bearing) wins."""

    def test_span_rides_the_roster_flag_and_casing_dedupes(self):
        acc = [_fact("middle", "riverside high school", 447)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=3,
            nces_by_level={"High": 1},
            schools_by_band={"middle": {"schools": [
                {"school": "RIVERSIDE HIGH SCHOOL", "level": "High", "gslo": "07", "gshi": "12"}]}})
        mm = out["negative_space"]["name_level_mismatches"]
        assert len(mm) == 1                       # roster + fact casings collapse to one note
        assert mm[0]["surface"] == "roster"       # the span-bearing surface wins
        assert (mm[0]["gslo"], mm[0]["gshi"]) == ("07", "12")

    def test_fact_only_flag_still_fires_without_span(self):
        acc = [_fact("elementary", "northside high", 410)]
        out = CA.build_closing_argument(
            "D", merged_accepted=acc, merged_unresolved=[], nces_total=3,
            nces_by_level={"Elementary": 2}, schools_by_band={})
        mm = out["negative_space"]["name_level_mismatches"]
        assert len(mm) == 1 and mm[0]["surface"] == "fact" and "gslo" not in mm[0]
