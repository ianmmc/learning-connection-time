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

    def test_ambiguous_pm_end_normalizes_to_afternoon(self):
        """#716 must-fail-today case (the Washoe shape): one voter echoes the document's 12-hour
        clock ('03:30'), the other normalizes to 24h ('15:30') — substantive agreement that used to
        land unresolved (clusters 720 min apart). Deterministic normalization at the consensus
        boundary accepts it with council_agree."""
        rows = {"google/gemini-2.5-flash": [{"grade_level": "elementary", "start_time": "09:30",
                                             "end_time": "03:30", "school_name": "Allen Elementary"}],
                "mistralai/mistral-small-24b-instruct-2501": [
                    {"grade_level": "elementary", "start_time": "09:30",
                     "end_time": "15:30", "school_name": "Allen Elementary"}]}
        accepted, unres = A.consensus_school_facts(rows)
        assert unres == [] and len(accepted) == 1
        f = accepted[0]
        assert f["method"] == "council_agree" and f["end"] == "15:30" and f["gross"] == 360

    def test_normalize_ambiguous_end_rules(self):
        """#716/#732: ONLY an end in 01:00-06:59 normalizes (+720) — everything else, including a
        genuinely transposed end-before-start pair (which must stay implausible → unresolved for
        human review, never be laundered into a fabricated fact), is untouched. The window bound
        also guarantees the result is a valid clock time (06:59+12h = 18:59 max)."""
        n = A._normalize_ambiguous_end
        assert n(9 * 60 + 30, 3 * 60 + 30) == 15 * 60 + 30      # 03:30 after a 09:30 start -> 15:30
        assert n(8 * 60, 60) == 13 * 60                          # 01:00 -> 13:00 (in-window)
        assert n(8 * 60, 6 * 60 + 59) == 18 * 60 + 59            # 06:59 -> 18:59 (window edge)
        # #732: end<start OUTSIDE the window is a garble, NOT an echo — untouched, so the negative
        # gross fails plausibility and the pair lands unresolved (the pre-#716 behavior, preserved)
        assert n(13 * 60, 7 * 60 + 45) == 7 * 60 + 45            # 13:00->07:45 transposition stays
        assert n(20 * 60, 15 * 60) == 15 * 60                    # can never mint a >23:59 string
        assert n(8 * 60, 12 * 60 + 30) == 12 * 60 + 30           # 12:30 early release stays
        assert n(8 * 60, 15 * 60 + 30) == 15 * 60 + 30           # already 24h stays
        assert n(None, 3 * 60) == 3 * 60 and n(8 * 60, None) is None   # missing values untouched

    def test_judge_rows_normalize_uniformly(self):
        """#716: the judge tiebreak path gets the SAME normalization — a judge echoing '3:15'
        resolves as 15:15, not a 210-minute-gross implausible."""
        rows = {"google/gemini-2.5-flash": [{"grade_level": "middle", "start_time": "08:00",
                                             "end_time": "14:00", "school_name": "B Middle"}],
                "mistralai/mistral-small-24b-instruct-2501": [
                    {"grade_level": "middle", "start_time": "09:00",
                     "end_time": "16:00", "school_name": "B Middle"}]}
        judge = {"qwen/qwen3-235b-a22b-2507": [{"grade_level": "middle", "start_time": "08:30",
                                                "end_time": "03:15", "school_name": "B Middle"}]}
        accepted, _ = A.consensus_school_facts(rows, judge_rows=judge)
        assert len(accepted) == 1 and accepted[0]["method"] == "judge"
        assert accepted[0]["end"] == "15:15" and accepted[0]["gross"] == 405

    def test_degenerate_band_referent_resolves_on_hub_label(self):
        """#707 must-fail-today (Little Rock's shape): a band referent ('elementary schools') with
        cross-family voter agreement on a district_hub_by_band record converts to an accepted
        band-grain fact (method=band_referent) instead of a silent degenerate_school_name drop."""
        rows = {"google/gemini-2.5-flash-lite": [{"grade_level": "elementary", "start_time": "07:40",
                                                  "end_time": "14:55", "school_name": "Elementary Schools"}],
                "mistralai/mistral-small-24b-instruct-2501": [
                    {"grade_level": "elementary", "start_time": "07:40",
                     "end_time": "14:55", "school_name": "Elementary Schools"}]}
        # without context: refused (the pre-#707 behavior, preserved)
        acc, unres = A.consensus_school_facts(rows)
        assert acc == [] and unres[0]["reason"] == "degenerate_school_name"
        # with the hub-label context: accepted, visibly marked
        acc, unres = A.consensus_school_facts(rows, context={"band_grain": True})
        assert unres == [] and len(acc) == 1
        f = acc[0]
        assert f["method"] == "band_referent" and f["school"] == "elementary schools"
        assert f["start"] == "07:40" and f["end"] == "14:55" and f["resolved_from"] == "elementary schools"

    def test_degenerate_resolves_uniquely_on_n1_roster(self):
        """#707 (Lewiston's shape): a bare 'hs' in a band whose roster has exactly ONE school
        resolves to that school (method=roster_unique) — and stays refused when the roster has >1."""
        rows = {"google/gemini-2.5-flash-lite": [{"grade_level": "high", "start_time": "07:45",
                                                  "end_time": "14:00", "school_name": "HS"}],
                "mistralai/mistral-small-24b-instruct-2501": [
                    {"grade_level": "high", "start_time": "07:45",
                     "end_time": "14:00", "school_name": "HS"}]}
        ctx1 = {"band_grain": False, "roster_by_band": {"high": ["Lewiston High School"]}}
        acc, unres = A.consensus_school_facts(rows, context=ctx1)
        assert unres == [] and acc[0]["method"] == "roster_unique"
        assert acc[0]["school"] == "lewiston" and acc[0]["resolved_from"] == "hs"
        # the >1-roster pin: 'hs' in a 6-high-school district stays unresolved — correctly
        ctx6 = {"band_grain": False, "roster_by_band": {"high": [f"School {i} High" for i in range(6)]}}
        acc, unres = A.consensus_school_facts(rows, context=ctx6)
        assert acc == [] and unres[0]["reason"] == "degenerate_school_name"

    def test_degenerate_never_converts_without_cross_family_agreement(self):
        """#707: only cross-family VOTER agreement converts — same-family agreement or a judge
        re-emission must not mint a fact the guard would otherwise refuse."""
        # two GOOGLE models agree -> same family -> still refused, even with full context
        rows = {"google/gemini-2.5-flash": [{"grade_level": "high", "start_time": "07:45",
                                             "end_time": "14:00", "school_name": "HS"}],
                "google/gemini-2.5-flash-lite": [{"grade_level": "high", "start_time": "07:45",
                                                  "end_time": "14:00", "school_name": "HS"}]}
        ctx = {"band_grain": True, "roster_by_band": {"high": ["Only High"]}}
        judge = {"qwen/qwen3-235b-a22b-2507": [{"grade_level": "high", "start_time": "07:45",
                                                "end_time": "14:00", "school_name": "HS"}]}
        acc, unres = A.consensus_school_facts(rows, judge_rows=judge, context=ctx)
        assert acc == [] and unres[0]["reason"] == "degenerate_school_name"

    def test_reaggregate_receipt_replays_stored_calls_zero_spend(self, tmp_path, monkeypatch):
        """#716 recovery path: reaggregate_receipt rebuilds consensus from the receipt's stored
        per-call facts (no model calls), and the new row carries cost_usd=0 so the REQ-051 spend
        governor never double-counts the original run."""
        from infrastructure.acquisition.process_governance import reaggregate as RA
        receipt = {"handoff_hash": "zzhash", "district": {
            "district_id": "ZZ716", "name": "Washoe-shape", "accepted": [], "n_reps": 1,
            "unresolved": [{"band": "elementary", "school": "allen elementary",
                            "starts": {"a": "09:30", "b": "09:30"},
                            "ends": {"a": "03:30", "b": "15:30"}}],
            "reps": [{"rec_key": "ZZ716:r1", "file": "f.txt", "kind": "text", "council_id": "c1",
                      "judged": False, "calls": [
                          {"model": "google/gemini-2.5-flash", "role": "voter", "facts": [
                              {"grade_level": "elementary", "start_time": "09:30",
                               "end_time": "03:30", "school_name": "Allen Elementary"}]},
                          {"model": "mistralai/mistral-small-24b-instruct-2501", "role": "voter",
                           "facts": [{"grade_level": "elementary", "start_time": "09:30",
                                      "end_time": "15:30", "school_name": "Allen Elementary"}]}]}]}}
        p = tmp_path / "extraction_zzhash_ZZ716_x.json"
        p.write_text(__import__("json").dumps(receipt))
        # dry run: pure, no persist
        out = RA.reaggregate_receipt(str(p), dry_run=True)
        assert out["was"] == {"accepted": 0, "unresolved": 1}
        assert out["now"] == {"accepted": 1, "unresolved": 0} and out["persisted"] is False
        # persist path: stub the DB write + receipt dir; assert cost_usd rides as 0 and the
        # ORIGINAL run_kind is threaded (#731) + satisfied directives withdraw (#739)
        seen, withdrew = {}, []
        monkeypatch.setattr(RA.S7R, "persist_run", lambda results, **kw: (
            seen.update(results=results, **kw) or
            {"districts": [{"extraction_id": 42, "district_id": "ZZ716"}]}))
        monkeypatch.setattr(RA, "_original_run_kind", lambda hh, did: "production")
        monkeypatch.setattr(RA.S7R, "withdraw_satisfied_requests",
                            lambda s, did, **kw: withdrew.append(did) or [(7, "note")])
        import contextlib
        from infrastructure.acquisition.common import db as gdb
        monkeypatch.setattr(gdb, "session_scope", lambda: contextlib.nullcontext(None))
        monkeypatch.setattr(RA.paths, "ACQUISITION", tmp_path)
        out = RA.reaggregate_receipt(str(p))
        assert out["persisted"] and out["extraction_id"] == 42
        pd = seen["results"]["districts"]["ZZ716"]
        assert seen["results"]["run_kind"] == "production"          # #731: threaded, not defaulted
        assert withdrew == ["ZZ716"] and out["withdrawn_requests"] == [7]   # #739
        assert pd["telemetry"]["cost_usd"] == 0.0 and pd["reaggregated_from"] == p.name
        assert seen["created_by"] == "auto:reaggregate-716"
        assert pd["accepted"][0]["end"] == "15:30" and pd["accepted"][0]["rec_key"] == "ZZ716:r1"

    def test_reaggregate_preserves_run_kind_and_original_judged_and_clears_error(self, tmp_path, monkeypatch):
        """#731: a benchmark receipt's replay stays benchmark (never leaks into production
        filters); #742: a judge that ran but returned zero facts still counts as judged; #741: a
        stale per-rep error from the original failure does not survive a successful recompute."""
        from infrastructure.acquisition.process_governance import reaggregate as RA
        receipt = {"handoff_hash": "zzbmh", "district": {
            "district_id": "ZZ716B", "name": "BM", "accepted": [], "unresolved": [], "n_reps": 1,
            "reps": [{"rec_key": "ZZ716B:r1", "file": "f.txt", "kind": "text", "council_id": "c1",
                      "judged": True, "error": "ValueError: consensus blew up",
                      "calls": [
                          {"model": "google/gemini-2.5-flash", "role": "voter", "facts": [
                              {"grade_level": "high", "start_time": "08:00",
                               "end_time": "14:30", "school_name": "Real High School"}]},
                          {"model": "mistralai/mistral-small-24b-instruct-2501", "role": "voter",
                           "facts": [{"grade_level": "high", "start_time": "08:00",
                                      "end_time": "14:30", "school_name": "Real High School"}]},
                          {"model": "qwen/qwen3-235b-a22b-2507", "role": "judge", "facts": []}]}]}}
        p = tmp_path / "extraction_zzbmh_ZZ716B_x.json"
        p.write_text(__import__("json").dumps(receipt))
        seen, withdrew = {}, []
        monkeypatch.setattr(RA.S7R, "persist_run", lambda results, **kw: (
            seen.update(results=results) or
            {"districts": [{"extraction_id": 43, "district_id": "ZZ716B"}]}))
        monkeypatch.setattr(RA, "_original_run_kind", lambda hh, did: "benchmark")
        monkeypatch.setattr(RA.S7R, "withdraw_satisfied_requests",
                            lambda s, did, **kw: withdrew.append(did) or [])
        monkeypatch.setattr(RA.paths, "ACQUISITION", tmp_path)
        out = RA.reaggregate_receipt(str(p))
        assert seen["results"]["run_kind"] == "benchmark" and out["run_kind"] == "benchmark"
        assert withdrew == []                       # #739: non-production never touches the request loop
        rep = seen["results"]["districts"]["ZZ716B"]["reps"][0]
        assert rep["judged"] is True                # #742: empty-facts judge call still = escalated
        assert "error" not in rep                   # #741: stale error cleared on successful recompute
        assert rep["accepted"] and rep["accepted"][0]["school"] == "real"

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

    def test_v2_evidence_carried_onto_accepted_fact(self):
        # v2 rows carry evidence_quote / stated_minutes; consensus attaches them per consensus model.
        rows = {"google/gemini-2.5-flash-lite": [{"grade_level": "elementary", "start_time": "08:00",
                    "end_time": "14:30", "school_name": "Lincoln Elementary",
                    "evidence_quote": "Hours: 8:00-2:30", "stated_minutes": 390}],
                "mistralai/mistral-small-24b-instruct-2501": [{"grade_level": "elementary",
                    "start_time": "08:00", "end_time": "14:30", "school_name": "Lincoln Elementary",
                    "evidence_quote": "8:00 AM to 2:30 PM"}]}
        acc, _ = A.consensus_school_facts(rows)
        assert len(acc) == 1
        ev = acc[0]["evidence"]
        assert ev["google/gemini-2.5-flash-lite"]["quote"] == "Hours: 8:00-2:30"
        assert ev["google/gemini-2.5-flash-lite"]["stated_minutes"] == 390

    def test_v1_rows_produce_no_evidence_key(self):
        # a fact built from v1-shaped rows (no evidence fields) stays byte-identical — no `evidence` key.
        rows = self._rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30"),
                           "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30")})
        acc, _ = A.consensus_school_facts(rows)
        assert len(acc) == 1 and "evidence" not in acc[0]
        assert "school_year" not in acc[0] and "applies_to" not in acc[0]   # #254: pre-v3 unchanged


# ---------------------------------------------------------------- #254 v3 readings (year + scope)
def _v3_rows(per_model):
    """{model: (start, end, school_year, applies_to)} -> consensus_school_facts input (v3-shaped)."""
    return {m: [{"grade_level": "elementary", "start_time": s, "end_time": e,
                 "school_name": "Lincoln Elementary", "school_year": sy, "applies_to": at}]
            for m, (s, e, sy, at) in per_model.items()}


class TestConsensusYearAndScope:
    """#254: school_year/applies_to are categorical corroboration — never in the grouping key,
    never a vote on times. Year = all-parseable-readers-agree; scope = OR."""

    def test_agreeing_years_in_different_formats_normalize_onto_the_fact(self):
        rows = _v3_rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30", "2025-26", None),
                         "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30", "SY25-26", None)})
        acc, _ = A.consensus_school_facts(rows)
        assert len(acc) == 1 and acc[0]["school_year"] == "2025-26"   # deterministic normalization

    def test_disagreeing_years_store_null_but_keep_per_model_readings_in_evidence(self):
        rows = _v3_rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30", "2025-26", None),
                         "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30", "2024-25", None)})
        acc, _ = A.consensus_school_facts(rows)
        assert len(acc) == 1 and "school_year" not in acc[0]          # disagreement -> no consensus year
        ev = acc[0]["evidence"]
        assert ev["google/gemini-2.5-flash-lite"]["school_year"] == "2025-26"
        assert ev["mistralai/mistral-small-24b-instruct-2501"]["school_year"] == "2024-25"

    def test_single_source_year_is_accepted(self):
        # like stated_minutes: one reader is corroboration-grade metadata, not agreement to fake
        rows = _v3_rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30", "2025-26", None),
                         "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30", None, None)})
        acc, _ = A.consensus_school_facts(rows)
        assert acc[0]["school_year"] == "2025-26"

    def test_garbage_and_covid_readings_do_not_count_as_readings(self):
        # a COVID year and an unparseable string are rejected by the deterministic parse — the one
        # remaining valid reading stands alone (no false disagreement with garbage)
        rows = _v3_rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30", "2025-26", None),
                         "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30", "2021-22", None)})
        acc, _ = A.consensus_school_facts(rows)
        assert acc[0]["school_year"] == "2025-26"

    def test_applies_to_is_or_semantics(self):
        # ANY model reading a group scope flags the fact — a scope warning is a warning
        rows = _v3_rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30", None, "multiple"),
                         "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30", None, None)})
        acc, _ = A.consensus_school_facts(rows)
        assert acc[0]["applies_to"] == "multiple"
        # and a non-"multiple" string is not a scope flag
        rows2 = _v3_rows({"google/gemini-2.5-flash-lite": ("08:00", "14:30", None, "single"),
                          "mistralai/mistral-small-24b-instruct-2501": ("08:00", "14:30", None, None)})
        acc2, _ = A.consensus_school_facts(rows2)
        assert "applies_to" not in acc2[0]


class TestParseSchoolYear:
    """#254: defensive, deterministic — the model's formatting is never trusted."""

    def test_accepted_formats_all_yield_the_start_year(self):
        for s in ("2025-26", "2025-2026", "SY25-26", "25-26", "2025/26",
                  "2025-2026 School Year", "Bell Schedule 2025–26"):
            assert A.parse_school_year(s) == 2025, s

    def test_covid_years_rejected(self):
        for s in ("2019-20", "2020-21", "2021-22", "2022-23"):
            assert A.parse_school_year(s) is None, s

    def test_window_2023_through_current_plus_one(self):
        from infrastructure.utilities.school_year import current_school_year
        cur = int(current_school_year()[:4])
        assert A.parse_school_year("2023-24") == 2023                       # the floor
        assert A.parse_school_year(A.format_school_year(cur + 1)) == cur + 1  # one year forward slack
        assert A.parse_school_year(A.format_school_year(cur + 2)) is None
        assert A.parse_school_year("2010-11") is None

    def test_garbage_is_none_never_a_raise(self):
        for s in (None, "", "bell schedule", "2025", "2025-27", "8:15-3:20", 2025, "grades 6-8"):
            assert A.parse_school_year(s) is None, repr(s)

    def test_format_school_year_round_trips(self):
        assert A.format_school_year(2025) == "2025-26"
        assert A.parse_school_year(A.format_school_year(2023)) == 2023


# ------------------------------------------------- REQ-055 gate, shared string-input path (15c67c4 review)
class TestGrossFromTimes:
    def test_valid_pair(self):
        assert A.gross_from_times("08:00", "15:25") == (445, None)

    def test_unparseable(self):
        # the "3pm" typo class — must be a named error, never a silent fallback
        assert A.gross_from_times("08:00", "3pm") == (None, "unparseable")
        assert A.gross_from_times(None, "15:00") == (None, "unparseable")

    def test_implausible_gated(self):
        # same REQ-055 gate the council path enforces — a typo'd pair can't slip through as a gross
        assert A.gross_from_times("08:00", "10:05") == (None, "implausible")   # 125 min
        assert A.gross_from_times("08:00", "18:00") == (None, "implausible")   # 600 min
        assert A.is_plausible(240) and A.is_plausible(510) and not A.is_plausible(None)


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

    def test_none_gross_facts_dont_crash_the_band_rollup(self):
        """#403: a fact with gross=None reaching district_bands_from_facts must not TypeError —
        aggregate_band already ignores None VALUES, but the representative-school min() over
        `abs(f['gross'] - val)` didn't. The None-gross fact stays visible in schools[] (it's an
        accepted fact; hiding it would be a silent drop) but can't be the representative."""
        base = {"band": "elementary", "start": "08:00", "end": "15:00", "models": ["x", "y"],
                "method": "council_agree"}
        mixed = [{**base, "school": "a", "gross": 420},
                 {**base, "school": "b", "gross": None, "start": None, "end": None}]
        bands = A.district_bands_from_facts(mixed)
        assert bands["elementary"]["gross_minutes"] == 420
        assert bands["elementary"]["start_time"] == "08:00"   # rep must be the non-None fact
        assert {s["school"] for s in bands["elementary"]["schools"]} == {"a", "b"}

    def test_mean_tiebreak_band_emits_no_representative_times(self):
        """#627: two schools, distinct grosses (415 & 435) -> no mode -> mean_tiebreak value 425.
        425 matches NEITHER school's span, so carrying a school's real times would store an
        internally-inconsistent band (gross != span) that Stage 9's bell_schedules cross-check
        (minutes ≤ end−start) fails loud on. The band must emit the value WITHOUT times; the two
        real per-school schedules stay in schools[]."""
        base = {"band": "middle", "models": ["x", "y"], "method": "council_agree"}
        facts = [{**base, "school": "midview", "start": "07:25", "end": "14:20", "gross": 415},
                 {**base, "school": "midview east", "start": "07:20", "end": "14:35", "gross": 435}]
        band = A.district_bands_from_facts(facts)["middle"]
        assert band["gross_minutes"] == 425 and band["method"] == "mean_tiebreak"
        assert band["start_time"] is None and band["end_time"] is None
        # the real per-school times are NOT lost — they remain on the fact rows
        assert {(s["start_time"], s["end_time"]) for s in band["schools"]} == \
            {("07:25", "14:20"), ("07:20", "14:35")}

    def test_modal_band_keeps_consistent_times(self):
        """Sibling to the above: a modal band takes a single real school's (start,end,gross)
        verbatim, so gross == span and the representative times ARE kept (the fix is scoped to the
        synthetic mean_tiebreak case, not a blanket times-drop)."""
        base = {"band": "high", "models": ["x", "y"], "method": "council_agree"}
        facts = [{**base, "school": "a", "start": "07:40", "end": "14:35", "gross": 415},
                 {**base, "school": "b", "start": "07:40", "end": "14:35", "gross": 415}]
        band = A.district_bands_from_facts(facts)["high"]
        assert band["method"] == "modal"
        assert band["start_time"] == "07:40" and band["end_time"] == "14:35"

    def test_all_none_gross_band_is_omitted_not_crashed(self):
        """#403 sibling: a band whose every accepted fact has gross=None has nothing aggregable —
        omit it (same posture as an empty band), don't TypeError on min() over an empty candidate
        set or on abs(None - None)."""
        f = {"band": "middle", "school": "m", "start": None, "end": None, "gross": None,
             "models": ["x"], "method": "council_agree"}
        assert A.district_bands_from_facts([f]) == {}


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


# ------------------------------------------------- #254 school-year precedence in the merge
def _fy(ext, school, status, gross, year, band="elementary"):
    return {**_f(ext, band, school, status, gross), "school_year": year, "source_file": f"src{ext}.pdf"}


class TestMergeYearPrecedence:
    """#254: between ACCEPTED facts only, a known NEWER parseable school_year supersedes a known
    older one regardless of extraction order; unknown-year facts COEXIST (Ian's decision — never
    auto-oldest); ties and unknown cases fall through to the existing rules unchanged."""

    def test_newer_known_year_beats_older_known_regardless_of_run_order(self):
        stale = _fy(1, "s", "accepted", 440, "2023-24")     # earlier run, dated older
        fresh = _fy(2, "s", "accepted", 445, "2025-26")     # later run, dated newer
        for order in ([stale, fresh], [fresh, stale]):
            accepted, _ = A.merge_fact_runs(order)
            assert len(accepted) == 1 and accepted[0]["gross_minutes"] == 445

    def test_superseded_fact_is_kept_and_returned_not_dropped(self):
        stale, fresh = _fy(1, "s", "accepted", 440, "2023-24"), _fy(2, "s", "accepted", 445, "2025-26")
        accepted, unresolved, superseded = A.merge_fact_runs([stale, fresh], with_superseded=True)
        assert accepted[0]["gross_minutes"] == 445 and unresolved == []
        assert superseded == [stale]                        # no-silent-caps: the loser stays visible

    def test_unknown_year_coexists_precedence_never_touches_it(self):
        # a dated fact must NOT supersede an undated one (every pre-v3 fact is undated) — the
        # existing earliest-accepted-wins rule decides, in both directions
        undated = _fy(1, "s", "accepted", 400, None)
        dated = _fy(2, "s", "accepted", 410, "2025-26")
        accepted, _, superseded = A.merge_fact_runs([undated, dated], with_superseded=True)
        assert accepted[0]["gross_minutes"] == 400          # earliest accepted stands
        assert superseded == []
        # and an undated LATER fact doesn't supersede a dated earlier one either
        accepted2, _, sup2 = A.merge_fact_runs(
            [_fy(1, "s", "accepted", 410, "2023-24"), _fy(2, "s", "accepted", 400, None)],
            with_superseded=True)
        assert accepted2[0]["gross_minutes"] == 410 and sup2 == []

    def test_same_year_tie_falls_through_to_earliest_accepted(self):
        a, b = _fy(2, "s", "accepted", 445, "2025-26"), _fy(1, "s", "accepted", 440, "2025-26")
        accepted, _, superseded = A.merge_fact_runs([a, b], with_superseded=True)
        assert accepted[0]["extraction_id"] == 1 and superseded == []

    def test_never_regress_untouched_by_year_precedence(self):
        # an unresolved later diagnostic still can't evict an accepted fact, dated or not
        acc = _fy(1, "s", "accepted", 440, "2023-24")
        diag = _fy(2, "s", "unresolved", None, "2025-26")
        accepted, unresolved, superseded = A.merge_fact_runs([acc, diag], with_superseded=True)
        assert accepted == [acc] and unresolved == [] and superseded == []

    def test_unparseable_year_string_is_unknown_not_a_precedence_claim(self):
        garbage = _fy(1, "s", "accepted", 400, "see calendar")
        dated = _fy(2, "s", "accepted", 410, "2025-26")
        accepted, _, superseded = A.merge_fact_runs([garbage, dated], with_superseded=True)
        assert accepted[0]["gross_minutes"] == 400 and superseded == []

    def test_selection_is_set_wise_order_independent_on_the_known_unknown_triangle(self):
        # the pairwise-fold trap: A(2025, eid 3) / B(undated, eid 2) / C(2024, eid 1) is a
        # preference cycle under pairwise rules — the set-wise selection must be order-free
        import itertools
        A_, B_, C_ = (_fy(3, "s", "accepted", 445, "2025-26"),
                      _fy(2, "s", "accepted", 400, None),
                      _fy(1, "s", "accepted", 430, "2024-25"))
        outs = {tuple(f["extraction_id"] for f in A.merge_fact_runs(list(p), with_superseded=True)[0])
                for p in itertools.permutations([A_, B_, C_])}
        assert len(outs) == 1                               # one winner, every order
        # C (older known) is superseded by A; A and B coexist -> earliest of the survivors wins (B)
        accepted, _, superseded = A.merge_fact_runs([A_, B_, C_], with_superseded=True)
        assert accepted[0]["extraction_id"] == 2 and superseded == [C_]


class TestDetectYearConflicts:
    def test_known_vs_known_flags_as_resolved(self):
        rows = [_fy(1, "s", "accepted", 440, "2023-24"), _fy(2, "s", "accepted", 445, "2025-26")]
        (c,) = A.detect_year_conflicts(rows)
        assert c["years"] == ["2023-24", "2025-26"] and c["resolved"] is True
        assert {s["source_file"] for s in c["sides"]} == {"src1.pdf", "src2.pdf"}   # the format hint

    def test_known_vs_unknown_flags_as_unresolved(self):
        rows = [_fy(1, "s", "accepted", 400, None), _fy(2, "s", "accepted", 410, "2025-26")]
        (c,) = A.detect_year_conflicts(rows)
        assert c["mixes_unknown"] is True and c["resolved"] is False

    def test_no_flag_when_years_are_uniform_or_all_unknown(self):
        assert A.detect_year_conflicts(
            [_fy(1, "s", "accepted", 440, "2025-26"), _fy(2, "s", "accepted", 445, "2025-26")]) == []
        assert A.detect_year_conflicts(
            [_fy(1, "s", "accepted", 440, None), _fy(2, "s", "accepted", 445, None)]) == []
        # unresolved rows never enter the conflict scan
        assert A.detect_year_conflicts(
            [_fy(1, "s", "unresolved", None, "2023-24"), _fy(2, "s", "accepted", 445, "2025-26")]) == []


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


def test_consensus_campus_names_union_across_models():
    """#499 REQ-148 (v4): campus_names = sorted union of the verbatim names ANY model read; attached
    only when non-empty (pre-v4 facts byte-identical); never part of the grouping key or a vote."""
    from infrastructure.acquisition.stage8_aggregate.aggregate import consensus_school_facts
    rows = {
        "google/gemini-x": [{"grade_level": "middle", "start_time": "08:00", "end_time": "15:00",
                             "school_name": "k8 schools",
                             "campus_names": ["Milagro Middle", "Ortiz Middle"]}],
        "mistralai/mist-x": [{"grade_level": "middle", "start_time": "08:00", "end_time": "15:00",
                              "school_name": "k8 schools",
                              "campus_names": ["Ortiz Middle", "Sunset K-8", "  "]}],
    }
    acc, unres = consensus_school_facts(rows)
    assert len(acc) == 1
    assert acc[0]["campus_names"] == ["Milagro Middle", "Ortiz Middle", "Sunset K-8"]
    # absent everywhere -> key absent
    for m in rows.values():
        m[0].pop("campus_names")
    acc2, _ = consensus_school_facts(rows)
    assert "campus_names" not in acc2[0]
