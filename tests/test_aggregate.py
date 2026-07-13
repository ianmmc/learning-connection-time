"""Tests for the per-school consensus + gross-minutes aggregation (REQ-054/055/056).

Covers the INVARIANT (deterministic code computes minutes/mode — the half enforceable today),
GROSS metric, cross-family per-school consensus, the exact-mode (380-not-381) fix, and mode-stability.

REQ-054 invariant, prompt-side half ("models read TIMES only, never minutes / a picked 'typical'
schedule"): the GT-era extractors.py that once embodied this prompt was archived 2026-06-24 and its
top-level import broke when infrastructure/api was removed (2026-06-25). The bare `import extractors`
TestInvariant here imported that archived, broken module — a live test depending on archived code —
so it was removed 2026-06-26. The prompt-side invariant will be re-tested against the LIVE Stage-7
council extractor when it exists. The CODE-side half (Python computes gross = end-start and the
per-band MODE; the model never does) is live and tested below (TestGross, TestMode).
"""

from infrastructure.acquisition.stage8_aggregate import aggregate as A  # noqa: E402


# ---------------------------------------------------------------- REQ-055 gross
class TestGross:
    def test_gross_is_end_minus_start(self):
        rows = {"google/gemini-2.5-flash-lite": [{"grade_level": "elementary", "start_time": "08:00", "end_time": "14:30", "school_name": "A"}],
                "mistralai/mistral-small-24b-instruct-2501":     [{"grade_level": "elementary", "start_time": "08:00", "end_time": "14:30", "school_name": "A"}]}
        accepted, _ = A.consensus_school_facts(rows)
        assert accepted and accepted[0]["gross"] == 390  # 14:30-08:00 = 6h30 = 390, no deduction

    def test_no_deduction_applied(self):
        # even if a lunch is mentioned in another row, gross ignores it (end-start only)
        bands = A.district_bands_from_facts([{"band": "elementary", "school": "a", "start": "08:00", "end": "15:00", "gross": 420, "models": ["x", "y"], "method": "council_agree"}])
        assert bands["elementary"]["gross_minutes"] == 420

    def test_plausibility_gate_240_510(self):
        assert A.PLAUSIBLE == (240, 510)
        # a 500-min day (LA) is accepted; a 600-min one is not
        ok = {"google/gemini-2.5-flash-lite": [{"grade_level": "high", "start_time": "07:30", "end_time": "15:50", "school_name": "H"}],
              "deepseek/deepseek-v3.2":          [{"grade_level": "high", "start_time": "07:30", "end_time": "15:50", "school_name": "H"}]}
        acc, _ = A.consensus_school_facts(ok)
        assert acc and acc[0]["gross"] == 500
        bad = {"google/gemini-2.5-flash-lite": [{"grade_level": "high", "start_time": "06:00", "end_time": "16:30", "school_name": "H"}],
               "deepseek/deepseek-v3.2":          [{"grade_level": "high", "start_time": "06:00", "end_time": "16:30", "school_name": "H"}]}
        acc2, unres = A.consensus_school_facts(bad)
        assert not acc2 and any(u.get("reason") == "implausible" for u in unres)


# ---------------------------------------------------------------- REQ-056 consensus
class TestConsensus:
    def _rows(self, models_times):
        return {m: [{"grade_level": "elementary", "start_time": s, "end_time": e, "school_name": "Lincoln Elementary"}]
                for m, (s, e) in models_times.items()}

    def test_cross_family_required(self):
        rows = self._rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30"),
                           "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30"),
                           "qwen/qwen3-235b-a22b-2507": ("09:00", "15:00")})
        acc, _ = A.consensus_school_facts(rows)
        assert len(acc) == 1 and acc[0]["gross"] == 390
        assert {"google/gemini-2.5-flash-lite", "mistralai/mistral-small-24b-instruct-2501"} <= set(acc[0]["models"])

    def test_same_family_not_consensus(self):
        # two GOOGLE models agree, qwen differs -> NOT cross-family -> unresolved (no judge)
        rows = self._rows({"google/gemini-2.5-flash": ("08:00", "14:30"),
                           "google/gemini-2.5-flash-lite": ("08:00", "14:30"),
                           "qwen/qwen3-235b-a22b-2507": ("09:10", "15:00")})
        acc, unres = A.consensus_school_facts(rows)
        assert acc == [] and len(unres) == 1

    def test_unresolved_held_out(self):
        # all three disagree -> held out, not counted
        rows = self._rows({"google/gemini-2.5-flash-lite": ("08:00", "14:00"),
                           "mistralai/mistral-small-24b-instruct-2501": ("08:30", "15:00"),
                           "qwen/qwen3-235b-a22b-2507": ("09:00", "16:00")})
        acc, unres = A.consensus_school_facts(rows)
        assert acc == [] and len(unres) == 1

    def test_consensus_on_times_not_minutes(self):
        """Same DURATION via different start/end must NOT form consensus (it's on the pair)."""
        rows = self._rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30"),   # 390
                           "mistralai/mistral-small-24b-instruct-2501": ("07:30", "14:00"),        # 390 but different pair
                           "qwen/qwen3-235b-a22b-2507": ("09:00", "15:30")})              # 390 again, different pair
        acc, unres = A.consensus_school_facts(rows)
        # durations all equal 390, but no two share a (start,end) pair -> NO consensus
        assert acc == [] and len(unres) == 1

    def test_degenerate_school_name_routes_to_unresolved_not_accepted(self):
        # #245: a school_name of "" or a bare generic word normalizes (via norm_school's #236 empty-key
        # fallback) to a non-empty-but-junk key — even with full cross-family consensus on the TIMES,
        # this must never reach `accepted` (it isn't a real, distinct school).
        for junk_name in ("", "Schools", "The School District"):
            rows = {m: [{"grade_level": "elementary", "start_time": s, "end_time": e,
                        "school_name": junk_name}]
                   for m, (s, e) in {"google/gemini-2.5-flash-lite": ("08:00", "14:30"),
                                     "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30")}.items()}
            acc, unres = A.consensus_school_facts(rows)
            assert acc == [], f"{junk_name!r} must not reach accepted"
            assert len(unres) == 1 and unres[0]["reason"] == "degenerate_school_name"


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


# ------------------------------------------------- REQ-122 cumulative merge (#232, fill-not-overwrite)
def _f(ext, band, school, status, gross=None):
    return {"extraction_id": ext, "band": band, "school": school, "status": status,
            "gross_minutes": gross, "detail_json": None}


class TestMergeFactRuns:
    """REQ-122: a follow-up round FILLS GAPS, it never regresses solid signal advancing to Stage 8."""

    def test_the_brownsville_case_a_barren_retry_cannot_erase_an_earlier_accepted_run(self):
        # run 1 accepted 2 schools; the scoped 7->6 retry (run 2) yielded NOTHING for them.
        run1 = [_f(1, "elementary", "a", "accepted", 360), _f(1, "middle", "b", "accepted", 380)]
        run2 = []                                                    # the retry accepted 0 facts
        accepted, unresolved = A.merge_fact_runs(run1 + run2)
        assert [f["school"] for f in accepted] == ["a", "b"]         # solid signal survives
        assert unresolved == []

    def test_a_later_run_fills_a_gap_left_unresolved_by_an_earlier_run(self):
        facts = [_f(1, "high", "h", "unresolved"), _f(2, "high", "h", "accepted", 400)]
        accepted, unresolved = A.merge_fact_runs(facts)
        assert accepted[0]["extraction_id"] == 2 and unresolved == []   # gap filled

    def test_an_accepted_fact_beats_unresolved_in_either_run_order(self):
        # a later retry that DISAGREES (unresolved) must not displace the earlier accepted fact.
        facts = [_f(1, "high", "h", "accepted", 400), _f(2, "high", "h", "unresolved")]
        accepted, unresolved = A.merge_fact_runs(facts)
        assert accepted[0]["extraction_id"] == 1 and unresolved == []

    def test_among_duplicate_accepted_the_earliest_run_wins_fill_not_overwrite(self):
        # correcting a solid fact is a gate@8 human determination, never a silent later-run override.
        facts = [_f(2, "middle", "m", "accepted", 390), _f(1, "middle", "m", "accepted", 380)]
        accepted, _ = A.merge_fact_runs(facts)
        assert len(accepted) == 1
        assert accepted[0]["extraction_id"] == 1 and accepted[0]["gross_minutes"] == 380

    def test_among_unresolved_only_the_latest_diagnostic_wins(self):
        facts = [_f(1, "high", "h", "unresolved"), _f(2, "high", "h", "unresolved")]
        _, unresolved = A.merge_fact_runs(facts)
        assert len(unresolved) == 1 and unresolved[0]["extraction_id"] == 2

    def test_equal_run_ties_keep_the_first_row_seen(self):
        # two rows for the SAME (band, school) in the SAME run (two URLs both describing a school):
        # the tie-breaks are strict (< / >), so the first row encountered stands on both sides —
        # kills the PR #221 review's surviving Lt->LtE / Gt->GtE mutants on the tie-break lines.
        a1, a2 = _f(1, "elementary", "a", "accepted", 400), _f(1, "elementary", "a", "accepted", 410)
        accepted, _ = A.merge_fact_runs([a1, a2])
        assert accepted == [a1]
        u1, u2 = _f(2, "high", "h", "unresolved", 111), _f(2, "high", "h", "unresolved", 222)
        _, unresolved = A.merge_fact_runs([u1, u2])
        assert unresolved == [u1]

    def test_distinct_schools_and_bands_never_collide(self):
        facts = [_f(1, "elementary", "x", "accepted", 350), _f(2, "elementary", "y", "accepted", 355),
                 _f(2, "middle", "x", "accepted", 370)]              # same school name, other band
        accepted, _ = A.merge_fact_runs(facts)
        assert len(accepted) == 3

    def test_output_is_deterministic_band_school_sorted_and_input_order_free(self):
        facts = [_f(2, "middle", "b", "accepted", 1), _f(1, "elementary", "z", "accepted", 2),
                 _f(1, "elementary", "a", "unresolved")]
        a1, u1 = A.merge_fact_runs(facts)
        a2, u2 = A.merge_fact_runs(list(reversed(facts)))
        assert (a1, u1) == (a2, u2)
        assert [(f["band"], f["school"]) for f in a1] == [("elementary", "z"), ("middle", "b")]

    def test_merged_accepted_feed_the_band_rollup_unchanged(self):
        # the merge's output is what district_bands_from_facts consumes at gate@7 (server wiring).
        facts = [_f(1, "elementary", "a", "accepted", 360), _f(2, "elementary", "b", "accepted", 360)]
        accepted, _ = A.merge_fact_runs(facts)
        agg = [{"band": f["band"], "school": f["school"], "gross": f["gross_minutes"],
                "start": "08:00", "end": "14:00", "models": ["m1", "m2"], "method": "council_agree"}
               for f in accepted]
        bands = A.district_bands_from_facts(agg)
        assert bands["elementary"]["gross_minutes"] == 360 and bands["elementary"]["n_schools"] == 2

    def test_stale_vintage_persisted_keys_merge_with_current_keys(self):
        # PR #247 review: school_fact.school is PERSISTED at write time, so a stopword-list change
        # leaves old rows keyed under the old normalization ('lincoln unified district') while a new
        # run writes the current key ('lincoln'). The merge re-normalizes through the CURRENT
        # norm_school at read time — the same physical school must dedupe, not fragment.
        old = _f(1, "high", "lincoln unified district", "accepted", 400)   # pre-#236 vintage key
        new = _f(2, "high", "lincoln", "accepted", 410)                    # current-vintage key
        accepted, unresolved = A.merge_fact_runs([old, new])
        assert len(accepted) == 1 and unresolved == []
        assert accepted[0]["extraction_id"] == 1                            # earliest accepted stands


# ------------------------------------------------- #237 single-school-LEA over-extraction contamination
def _s(school, band="high"):
    """A minimal accepted fact — the detector only reads 'school' (already norm_school-normalized)."""
    return {"band": band, "school": school, "start": "08:00", "end": "15:00", "gross": 420, "models": []}


class TestDetectSingleSchoolOverExtraction:
    """#237: a nces_count==1 LEA yielding >1 distinct school is cross-LEA contamination (charter-network
    siblings on a shared CMO domain, or a blank-domain unscoped capture). Detect + flag, never auto-reject."""

    def test_not_flagged_when_not_single_school_lea(self):
        # a genuine multi-school LEA legitimately has many schools
        assert A.detect_single_school_over_extraction([_s("a"), _s("b")], nces_school_count=8) is None

    def test_not_flagged_when_nces_count_unknown(self):
        assert A.detect_single_school_over_extraction([_s("a"), _s("b")], nces_school_count=None) is None

    def test_single_school_lea_with_one_school_is_clean(self):
        # the correct outcome for a real single-school LEA: one school, no flag. School names here are
        # already norm_school-normalized (as they arrive from the extraction facts) — 'charter' is NOT
        # stripped, so the real Brownsville Ascend school normalizes to 'brownsville ascend charter'.
        one = [_s("brownsville ascend charter")]
        assert A.detect_single_school_over_extraction(one, nces_school_count=1) is None
        # multiple facts for the SAME normalized school (e.g. two bands) is still one distinct school
        two_bands = [_s("brownsville ascend charter", "elementary"), _s("brownsville ascend charter", "high")]
        assert A.detect_single_school_over_extraction(two_bands, nces_school_count=1) is None

    def test_single_school_lea_with_sibling_campuses_is_flagged(self):
        # Brownsville Ascend: 1-school LEA, but extraction pulled sibling campuses off the shared domain
        facts = [_s("brownsville ascend charter"), _s("brooklyn ascend charter"), _s("bushwick ascend charter")]
        got = A.detect_single_school_over_extraction(facts, nces_school_count=1)
        assert got is not None
        assert got["suspected"] is True
        assert got["reason"] == "single_school_lea_over_extraction"
        assert got["n_distinct_schools"] == 3
        assert got["distinct_schools"] == [
            "brooklyn ascend charter", "brownsville ascend charter", "bushwick ascend charter"]

    def test_roster_match_surfaces_the_reliable_keeper_when_available(self):
        facts = [_s("brownsville ascend charter"), _s("brooklyn ascend charter")]
        got = A.detect_single_school_over_extraction(
            facts, nces_school_count=1, roster_names=["Brownsville Ascend Charter School"])
        assert got["roster_matched"] == ["brownsville ascend charter"]   # only the LEA's own roster school

    def test_no_roster_means_no_keeper_hint_not_a_wrong_guess(self):
        # honest: without a roster we do NOT guess a keeper (shared 'ascend' name would mislead)
        facts = [_s("brownsville ascend charter"), _s("brooklyn ascend charter")]
        got = A.detect_single_school_over_extraction(facts, nces_school_count=1)
        assert got["roster_matched"] == []

    def test_junk_all_stopword_roster_entries_never_match(self):
        # PR #247 review: a scraped 'School District' header captured as a roster entry is junk, not
        # a school — it must be FILTERED (norm_school_strict), not smuggled through the empty-key
        # fallback where a junk-named fact could spuriously read as a trustworthy roster_matched hint.
        # Both FACTS here are real, distinct schools (not #245's degenerate-fact case, tested
        # separately) — only the ROSTER entries are junk.
        facts = [_s("millard south"), _s("brooklyn ascend charter")]
        got = A.detect_single_school_over_extraction(
            facts, nces_school_count=1, roster_names=["School District", "The School District"])
        assert got["roster_matched"] == []

    def test_stale_vintage_fact_keys_count_as_one_school(self):
        # PR #247 review: two facts for the SAME school persisted under different norm_school
        # vintages must not read as 2 distinct schools (a false contamination flag) — the detector
        # re-normalizes through the current function.
        facts = [_s("lincoln unified district"), _s("lincoln")]      # old + current vintage, same school
        assert A.detect_single_school_over_extraction(facts, nces_school_count=1) is None

    def test_degenerate_named_fact_does_not_trigger_a_false_contamination_flag(self):
        # #245: a real single-school LEA that also carries one degenerate-named fact (extraction noise,
        # e.g. an already-persisted 'schools' entry from before the consensus_school_facts fix) must
        # read as "2 distinct schools" ONLY if both are real — the junk name is excluded from the count.
        facts = [_s("brownsville ascend charter"), _s("schools")]
        assert A.detect_single_school_over_extraction(facts, nces_school_count=1) is None
        # but a genuine second REAL school alongside the same junk still gets flagged
        facts = [_s("brownsville ascend charter"), _s("brooklyn ascend charter"), _s("schools")]
        got = A.detect_single_school_over_extraction(facts, nces_school_count=1)
        assert got is not None and got["n_distinct_schools"] == 2   # the junk entry isn't counted


class TestDegenerateSchoolFacts:
    """#245: an accepted fact whose school name is empty or purely generic (e.g. 'schools') is
    extraction noise, not a real distinct school — found validating #236 against real Stage-7 data
    (Elmbrook, district 5501770, middle band). Excluded from district_bands_from_facts' rollup and
    surfaced (never silently dropped) via degenerate_school_facts()."""

    def test_identifies_empty_and_generic_only_names(self):
        facts = [_s("lincoln elementary"), _s(""), _s("schools"), _s("the school district")]
        degenerate = A.degenerate_school_facts(facts)
        assert {f["school"] for f in degenerate} == {"", "schools", "the school district"}

    def test_real_names_are_never_flagged_degenerate(self):
        facts = [_s("lincoln elementary"), _s("union hill isd")]
        assert A.degenerate_school_facts(facts) == []

    def test_district_bands_from_facts_excludes_degenerate_facts_from_the_rollup(self):
        # a junk-named fact must not inflate n_schools or appear in schools[], and must not skew the
        # modal gross-minutes value either.
        facts = [_s("lincoln elementary", "high"), _s("union hill", "high"), _s("schools", "high")]
        bands = A.district_bands_from_facts(facts)
        assert bands["high"]["n_schools"] == 2
        assert {s["school"] for s in bands["high"]["schools"]} == {"lincoln elementary", "union hill"}

    def test_district_bands_from_facts_handles_an_all_degenerate_band(self):
        # if EVERY fact in a band is junk, the band must not appear at all (not a phantom zero-school entry)
        facts = [_s("", "high"), _s("schools", "high")]
        bands = A.district_bands_from_facts(facts)
        assert "high" not in bands
