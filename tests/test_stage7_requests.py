"""Stage 7 request-more-evidence detection/routing (REQ-117, STAGE7 §4) — pure, no DB/network.
Feeds synthetic extraction results and asserts the routed requests at all three altitudes."""
from infrastructure.acquisition.common import model_families as MF
from infrastructure.acquisition.stage7_extract import requests as RQ


def _result(district_id="D1", reps=None, accepted=None):
    return {"district_id": district_id, "reps": reps or [], "accepted": accepted or [],
            "unresolved": [], "bands": {}}


def test_district_band_gap_routes_7to2():
    # elementary + middle have facts; claimed 'high' has none -> a 7->2 rediscover request
    res = _result(accepted=[{"band": "elementary", "school": "a"}, {"band": "middle", "school": "b"}])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary", "middle", "high"],
                              band_schools={"high": ["Central High", "East High"]})
    band_reqs = [r for r in reqs if r["altitude"] == "district"]
    assert len(band_reqs) == 1
    r = band_reqs[0]
    assert r["route"] == "7->2" and r["band"] == "high"
    assert r["params"]["schools"] == ["Central High", "East High"]
    assert "high" in r["reason"]


def test_no_gap_when_all_claimed_bands_present():
    res = _result(accepted=[{"band": b, "school": b} for b in ("elementary", "middle", "high")])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary", "middle", "high"])
    assert [r for r in reqs if r["altitude"] == "district"] == []


def test_band_7to2_defers_when_district_has_pending_7to6():
    # #159 — Marion's shape: MHS record failed (a 7->6 exists) AND the high band has 0 facts.
    # The band-gap 7->2 must be flagged DEFER (try the existing alternate rep first), not fired blind.
    res = _result(
        reps=[{"rec_key": "D1:mhs", "file": "harvest_slice.txt", "accepted": []}],
        accepted=[])   # nothing extracted -> high band empty AND the record is barren
    reqs = RQ.detect_requests(
        res, claimed_bands=["high"],
        alternates_by_rec={"D1:mhs": [{"file": "pdftotext.txt", "kind": "text", "n_times": 57}]})
    band = [r for r in reqs if r["altitude"] == "district"][0]
    assert band["route"] == "7->2"
    assert band["params"]["pending_alt_reps"] == 1        # the 7->6 counted
    assert "DEFER" in band["reason"]


def test_band_7to2_fires_normally_when_no_pending_7to6():
    # a band with no facts and NO existing-rep remedy -> a plain rediscover (no defer)
    res = _result(accepted=[{"band": "elementary", "school": "a"}])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary", "high"])
    band = [r for r in reqs if r["altitude"] == "district"][0]
    assert band["band"] == "high" and "pending_alt_reps" not in band["params"]
    assert "DEFER" not in band["reason"] and "targeted rediscover" in band["reason"]


def test_partial_result_with_covered_bands_fabricates_no_band_gaps():
    # F5 (review of 1f45ed5) — the Las Cruces shape: a 1-record 7->6 re-dispatch result covers
    # nothing by itself, but the district ALREADY has all three bands covered from prior
    # extractions. Without covered_bands this emitted a spurious 7->2 per claimed band
    # (live rows #285-287/#289-291).
    res = _result(reps=[{"rec_key": "D1:x", "file": "raster_p-01.png", "accepted": []}], accepted=[])
    reqs = RQ.detect_requests(
        res, claimed_bands=["elementary", "middle", "high"],
        covered_bands={"elementary", "middle", "high"})
    assert [r for r in reqs if r["altitude"] == "district"] == []   # no fabricated gaps
    # #176: the district is already fully covered — a barren rep's 7->3 recapture would add no coverage
    # either, so coverage gates ALL follow-ups here (was: the 7->3 fired regardless — pre-#176 waste).
    assert reqs == []


def test_covered_bands_only_fills_known_bands_not_all():
    # partial coverage: elementary known district-wide; high still genuinely empty -> exactly one 7->2
    res = _result(reps=[], accepted=[])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary", "high"],
                              covered_bands={"elementary"})
    bands = [r["band"] for r in reqs if r["altitude"] == "district"]
    assert bands == ["high"]


def test_barren_rep_with_alternate_routes_7to6():
    res = _result(
        reps=[{"rec_key": "D1:aa", "file": "harvest_slice.txt", "accepted": []}],
        accepted=[])
    reqs = RQ.detect_requests(res, claimed_bands=[],
                              alternates_by_rec={"D1:aa": [{"file": "raster_p-1.png", "kind": "image"}]})
    rep_reqs = [r for r in reqs if r["altitude"] == "representation"]
    assert len(rep_reqs) == 1
    r = rep_reqs[0]
    assert r["route"] == "7->6" and r["target"] == "D1:aa"
    # only an image alternate exists -> vision escalation, honest reason
    assert r["params"]["alternate_reps"][0]["kind"] == "image"
    assert "VISION" in r["reason"]


def test_7to6_prefers_higher_yield_text_over_image():
    # the Marion/Pittsylvania case (#155): a failed slice, with a full pdftotext AND a raster image
    # available — the fuller text must rank first, NOT the image.
    res = _result(reps=[{"rec_key": "D1:mhs", "file": "harvest_slice.txt", "accepted": []}], accepted=[])
    alts = [
        {"file": "raster_p-01.png", "kind": "image", "n_times": None},
        {"file": "pdftotext.txt", "kind": "text", "n_times": 86},
        {"file": "pdfplumber_lines.txt", "kind": "text", "n_times": 0},
        {"file": "camelot_hybrid.txt", "kind": "text", "n_times": 67},
    ]
    reqs = RQ.detect_requests(res, claimed_bands=[], alternates_by_rec={"D1:mhs": alts})
    ranked = [a["file"] for a in reqs[0]["params"]["alternate_reps"]]
    # high-yield text (desc n_times) -> image -> zero-yield text
    assert ranked == ["pdftotext.txt", "camelot_hybrid.txt", "raster_p-01.png", "pdfplumber_lines.txt"]
    assert "higher-yield TEXT" in reqs[0]["reason"] and "pdftotext.txt" in reqs[0]["reason"]


def test_rank_alternates_is_pure_and_stable():
    alts = [{"file": "b.png", "kind": "image", "n_times": None},
            {"file": "a.txt", "kind": "text", "n_times": 10}]
    assert [a["file"] for a in RQ.rank_alternates(alts)] == ["a.txt", "b.png"]
    assert [a["file"] for a in RQ.rank_alternates([])] == []


def test_barren_rep_without_alternate_routes_7to3():
    res = _result(reps=[{"rec_key": "D1:bb", "file": "pdftotext.txt", "accepted": []}], accepted=[])
    reqs = RQ.detect_requests(res, claimed_bands=[])   # no alternates map
    url_reqs = [r for r in reqs if r["altitude"] == "url"]
    assert len(url_reqs) == 1 and url_reqs[0]["route"] == "7->3"


def test_rep_with_facts_produces_no_request():
    res = _result(
        reps=[{"rec_key": "D1:cc", "file": "pdftotext.txt",
               "accepted": [{"band": "elementary", "school": "x"}]}],
        accepted=[{"band": "elementary", "school": "x"}])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary"])
    assert reqs == []   # a productive rep + its only claimed band covered -> nothing to request


def test_multi_rep_url_barren_only_if_all_reps_barren():
    # two reps of the SAME rec_key; one produced facts -> the record is covered, no request
    res = _result(
        reps=[{"rec_key": "D1:dd", "file": "a.txt", "accepted": []},
              {"rec_key": "D1:dd", "file": "b.txt", "accepted": [{"band": "high", "school": "h"}]}],
        accepted=[{"band": "high", "school": "h"}])
    reqs = RQ.detect_requests(res, claimed_bands=["high"])
    assert reqs == []


# --- #175 / #170 / #176: coverage-aware gating via real_bands ---

def test_phantom_claimed_band_emits_no_7to2():
    # #175: 'middle' is claimed but has NO real NCES school (real_bands={elementary,high}) — a
    # rediscover could never fill it, so it is never emitted (elem/high already covered).
    res = _result(accepted=[{"band": "elementary", "school": "a"}, {"band": "high", "school": "b"}])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary", "middle", "high"],
                              real_bands={"elementary", "high"})
    assert [r for r in reqs if r["altitude"] == "district"] == []


def test_real_missing_band_still_emits_7to2():
    # a REAL band (high) with no facts still fires — the phantom gate only drops UNreal bands.
    res = _result(accepted=[{"band": "elementary", "school": "a"}])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary", "high"],
                              real_bands={"elementary", "high"})
    assert [r["band"] for r in reqs if r["altitude"] == "district"] == ["high"]


def test_real_bands_none_preserves_legacy_behavior():
    # real_bands unknown -> NO phantom gating (back-compat): a claimed-but-unreal band still fires.
    res = _result(accepted=[{"band": "elementary", "school": "a"}])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary", "middle"])
    assert [r["band"] for r in reqs if r["altitude"] == "district"] == ["middle"]


def test_fully_covered_district_suppresses_barren_rep():
    # #170/#176 (the Aspire shape): every real band already covered; a barren rep with an alternate
    # would fire a 7->6, but it can add no net-new coverage -> suppressed (no 7->6, no 7->2).
    res = _result(
        reps=[{"rec_key": "D1:x", "file": "camelot_stream.txt", "accepted": []}],
        accepted=[{"band": b, "school": b} for b in ("elementary", "middle", "high")])
    reqs = RQ.detect_requests(
        res, claimed_bands=["elementary", "middle", "high"],
        real_bands={"elementary", "middle", "high"},
        alternates_by_rec={"D1:x": [{"file": "raster_p-1.png", "kind": "image", "n_times": 0}]})
    assert reqs == []


def test_not_fully_covered_still_fires_barren_rep():
    # a real band (high) still empty -> the barren rep's 7->6 fires; coverage is incomplete.
    res = _result(
        reps=[{"rec_key": "D1:x", "file": "camelot_stream.txt", "accepted": []}],
        accepted=[{"band": "elementary", "school": "a"}])
    reqs = RQ.detect_requests(
        res, claimed_bands=["elementary", "high"], real_bands={"elementary", "high"},
        alternates_by_rec={"D1:x": [{"file": "pdftotext.txt", "kind": "text", "n_times": 40}]})
    assert "7->6" in {r["route"] for r in reqs}                                   # barren-rep remedy
    assert any(r["band"] == "high" for r in reqs if r["altitude"] == "district")  # the real gap too


def test_phantom_band_does_not_block_full_coverage():
    # a phantom 'middle' must not keep a district from counting as fully covered: real bands are
    # {elementary, high}, both covered -> the barren rep is suppressed even though phantom 'middle' is empty.
    res = _result(
        reps=[{"rec_key": "D1:x", "file": "camelot_stream.txt", "accepted": []}],
        accepted=[{"band": "elementary", "school": "a"}, {"band": "high", "school": "b"}])
    reqs = RQ.detect_requests(
        res, claimed_bands=["elementary", "middle", "high"], real_bands={"elementary", "high"},
        alternates_by_rec={"D1:x": [{"file": "raster_p-1.png", "kind": "image", "n_times": 0}]})
    assert reqs == []


def test_all_phantom_district_suppresses_barren_reps_too():
    # review F5 (the all-phantom corner): claimed ∩ real is EMPTY — no claimed band can ever be
    # satisfied, so barren-rep remedies are suppressed too (they'd loop against the depth guard
    # for nothing), not just the 7->2s.
    res = _result(reps=[{"rec_key": "D1:x", "file": "camelot_stream.txt", "accepted": []}],
                  accepted=[])
    reqs = RQ.detect_requests(
        res, claimed_bands=["middle"], real_bands={"elementary", "high"},
        alternates_by_rec={"D1:x": [{"file": "pdftotext.txt", "kind": "text", "n_times": 12}]})
    assert reqs == []


def test_real_unknown_empty_claim_keeps_barren_rep_remedies():
    # with real UNKNOWN an empty/all-covered-less claim must NOT suppress (can't tell all-phantom
    # from no-data) — the barren rep's remedy still fires.
    res = _result(reps=[{"rec_key": "D1:x", "file": "a.txt", "accepted": []}], accepted=[])
    reqs = RQ.detect_requests(res, claimed_bands=[])
    assert [r["route"] for r in reqs] == ["7->3"]


def test_explain_reports_detect_time_suppression():
    # review F7-adjacent: detect-time suppression is non-emission — `explain` is the caller's hook
    # to log it (suppressed barren reps + phantom bands).
    res = _result(reps=[{"rec_key": "D1:x", "file": "a.txt", "accepted": []}],
                  accepted=[{"band": "elementary", "school": "e"}])
    explain = {}
    reqs = RQ.detect_requests(res, claimed_bands=["elementary", "middle"],
                              real_bands={"elementary"}, explain=explain)
    assert reqs == []                                       # e covered; middle phantom; rep suppressed
    assert explain == {"phantom_bands": ["middle"], "suppressed_barren_reps": 1,
                       "suppressed_degraded_reps": 0, "suppressed_truncated_reps": 0,
                       "suppressed_looped_reps": 0,
                       "suppressed_nameless_reps": 0}      # #710


# --------------------------- #793: a truncated read is not a barren one ---------------------------
def _degraded_rep(kind, rec_key="D1:x"):
    return {"rec_key": rec_key, "file": "a.txt", "accepted": [],
            "council_degraded": {"models": ["m"], "reasons": {"m": "…"}, "kinds": {"m": kind}}}


def test_793_truncated_suppression_counts_apart_from_refusal_and_barren():
    """P5: the two degradation shapes mislead differently — a refusal invites "the document was
    empty", a truncation invites "that was the whole roster". `explain` must not fold them."""
    counts = {}
    for kind in (MF.DEGRADED_TRUNCATED, MF.DEGRADED_REFUSED):
        explain = {}
        RQ.detect_requests(_result(reps=[_degraded_rep(kind)],
                                   accepted=[{"band": "elementary", "school": "e"}]),
                           claimed_bands=["elementary"], real_bands={"elementary"}, explain=explain)
        counts[kind] = explain
    assert counts[MF.DEGRADED_TRUNCATED]["suppressed_truncated_reps"] == 1
    assert counts[MF.DEGRADED_TRUNCATED]["suppressed_degraded_reps"] == 0
    assert counts[MF.DEGRADED_REFUSED]["suppressed_degraded_reps"] == 1
    assert counts[MF.DEGRADED_REFUSED]["suppressed_truncated_reps"] == 0
    for e in counts.values():
        assert e["suppressed_barren_reps"] == 0             # neither is evidence of an empty doc


def test_793_truncated_remedy_says_partial_not_empty():
    """The emitted remedy must name the truncation — a reader deciding what to do next has to know
    the read was PARTIAL, not that the document had nothing in it."""
    reqs = RQ.detect_requests(
        _result(reps=[_degraded_rep(MF.DEGRADED_TRUNCATED)], accepted=[]), claimed_bands=[])
    assert [r["route"] for r in reqs] == ["7->3"]
    assert reqs[0]["params"]["council_degraded"] is True
    assert "TRUNCATED" in reqs[0]["reason"]
    assert "incomplete" in reqs[0]["reason"].lower()


def test_793_rep_with_both_shapes_reports_the_refusal():
    """A rep where one voter was refused and another truncated is a REFUSAL rep — the stronger
    statement about the council wins, and the counts stay disjoint (never double-counted)."""
    rep = _degraded_rep(MF.DEGRADED_TRUNCATED)
    rep["council_degraded"]["kinds"]["m2"] = MF.DEGRADED_REFUSED
    explain = {}
    RQ.detect_requests(_result(reps=[rep], accepted=[{"band": "elementary", "school": "e"}]),
                       claimed_bands=["elementary"], real_bands={"elementary"}, explain=explain)
    assert explain["suppressed_degraded_reps"] == 1
    assert explain["suppressed_truncated_reps"] == 0


# ------------- #797/#798/#799: the review round on #793's own wiring -------------
def test_797_truncated_with_facts_emits_partial_read_remedy():
    """#797: a truncated rep WITH facts is a known-PARTIAL read — Baldwin kept 355 facts and read
    as clean. With a fillable gap and an unexhausted alternate, a 7->6 fires on fact-count
    evidence, not zero-yield."""
    rep = _degraded_rep(MF.DEGRADED_TRUNCATED)
    rep["accepted"] = [{"band": "elementary", "school": f"s{i}"} for i in range(5)]
    reqs = RQ.detect_requests(
        _result(reps=[rep], accepted=rep["accepted"]), claimed_bands=[],
        alternates_by_rec={"D1:x": [{"file": "pdftotext.txt", "kind": "text", "n_times": 90}]})
    assert [r["route"] for r in reqs] == ["7->6"]
    assert reqs[0]["params"]["partial_read"] is True
    assert reqs[0]["params"]["council_degraded"] is True
    # #812: the reason states what is KNOWN (the read was cut, so the facts are not known to be
    # the whole document) and must NOT assert a shape — every truncation measured in the corpus
    # was a repetition loop, not a dropped tail, so "the head of the document" would be false.
    assert "INCOMPLETE" in reqs[0]["reason"] and "TRUNCATED" in reqs[0]["reason"]
    assert "head of the document" not in reqs[0]["reason"]


def test_797_truncated_with_facts_all_covered_is_counted_not_silent():
    """The filed scenario verbatim: all bands covered, facts present, truncated — before #797 this
    produced zero remedies AND zero explain counts (the district read DONE-ENOUGH on a partial
    roster). Now the suppression is at least counted."""
    rep = _degraded_rep(MF.DEGRADED_TRUNCATED)
    rep["accepted"] = [{"band": b, "school": f"s{b}"} for b in ("elementary", "middle", "high")]
    explain = {}
    reqs = RQ.detect_requests(
        _result(reps=[rep], accepted=rep["accepted"]),
        claimed_bands=["elementary", "middle", "high"],
        real_bands={"elementary", "middle", "high"}, explain=explain)
    assert reqs == []
    assert explain["suppressed_truncated_reps"] == 1


def test_797_truncated_with_facts_no_alternate_counts_not_recaptures():
    """No alternate rep: recapturing the same URL re-reads the same document into the same window
    — no 7->3 fires, but the partial read is counted, never silent."""
    rep = _degraded_rep(MF.DEGRADED_TRUNCATED)
    rep["accepted"] = [{"band": "elementary", "school": "s"}]
    explain = {}
    reqs = RQ.detect_requests(_result(reps=[rep], accepted=rep["accepted"]),
                              claimed_bands=[], explain=explain)
    assert reqs == []
    assert explain["suppressed_truncated_reps"] == 1


def test_797_refused_rep_with_facts_from_sibling_stays_quiet():
    """The zero-yield gate is still the RIGHT gate for refusals: a refusal yields zero by
    construction, so a record with facts got them from a complete surviving read — no remedy."""
    rep = _degraded_rep(MF.DEGRADED_REFUSED)
    rep["accepted"] = [{"band": "elementary", "school": "s"}]
    explain = {}
    reqs = RQ.detect_requests(_result(reps=[rep], accepted=rep["accepted"]),
                              claimed_bands=[], explain=explain)
    assert reqs == []
    assert explain["suppressed_truncated_reps"] == 0


def test_799_multi_rep_record_merges_kinds_refusal_wins():
    """#799: two reps of ONE record — first refused, second truncated. Last-write-wins would call
    the record 'truncated'; the merge must report the refusal (the stronger statement)."""
    refused = _degraded_rep(MF.DEGRADED_REFUSED)
    refused["file"] = "page.txt"
    truncated = _degraded_rep(MF.DEGRADED_TRUNCATED)
    truncated["file"] = "camelot_hybrid.txt"
    explain = {}
    reqs = RQ.detect_requests(_result(reps=[refused, truncated], accepted=[]),
                              claimed_bands=[], explain=explain)
    assert [r["route"] for r in reqs] == ["7->3"]
    assert "refused" in reqs[0]["reason"]           # refusal wording, not 'TRUNCATED'
    assert "TRUNCATED" not in reqs[0]["reason"]


def test_798_marker_with_no_kinds_reads_as_refusal():
    """#798: a marker with absent `kinds` (a receipt written between #709 and #793) must NOT be
    vacuously worded as a truncation — the shared default is the stronger refusal."""
    rep = {"rec_key": "D1:x", "file": "a.txt", "accepted": [],
           "council_degraded": {"models": ["m"], "reasons": {"m": "…"}}}   # no 'kinds' at all
    explain = {}
    reqs = RQ.detect_requests(_result(reps=[rep], accepted=[]),
                              claimed_bands=[], explain=explain)
    assert [r["route"] for r in reqs] == ["7->3"]
    assert "refused" in reqs[0]["reason"] and "TRUNCATED" not in reqs[0]["reason"]
    explain2 = {}
    RQ.detect_requests(_result(reps=[rep], accepted=[{"band": "elementary", "school": "e"}]),
                       claimed_bands=["elementary"], real_bands={"elementary"}, explain=explain2)
    assert explain2["suppressed_degraded_reps"] == 1    # counted as degraded, not truncated


# --------------------------- #231: the request records its FULL send (round lineage) ---------------------------
def test_7to6_params_record_all_sent_files_not_just_the_first():
    # One dispatch sent TWO reps of the same record, both barren. The single first-seen `sent_file`
    # stays for the human reason, but `sent_files` must name BOTH — it is the lineage the next
    # round's history exclusion subtracts, so a file it omits could be circularly re-offered (#231).
    res = _result(reps=[{"rec_key": "D1:aa", "file": "page.txt", "accepted": []},
                        {"rec_key": "D1:aa", "file": "harvest_slice.txt", "accepted": []}])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary"],
                              alternates_by_rec={"D1:aa": [{"file": "page.png", "kind": "image"}]})
    r = next(r for r in reqs if r["route"] == RQ.ROUTE_ALT_REP)
    assert r["params"]["sent_file"] == "page.txt"                       # first seen, for the reason
    assert r["params"]["sent_files"] == ["harvest_slice.txt", "page.txt"]   # the FULL send, sorted


def test_7to3_recapture_params_also_record_sent_files():
    # The recapture route is part of the same lineage: after a recapture produces new reps, the old
    # failed file must still be excludable from future 7->6 alternate lists.
    res = _result(reps=[{"rec_key": "D1:bb", "file": "page.txt", "accepted": []}])
    reqs = RQ.detect_requests(res, claimed_bands=["elementary"])        # no alternates -> 7->3
    r = next(r for r in reqs if r["route"] == RQ.ROUTE_RECAPTURE)
    assert r["params"]["sent_files"] == ["page.txt"]


# --------------------------- #812: a loop is not a truncation ---------------------------
def _looped_rep(rec_key="D1:x"):
    return {"rec_key": rec_key, "file": "camelot_hybrid.txt", "accepted": [],
            "council_degraded": {"models": ["m"], "reasons": {"m": "repetition loop"},
                                 "kinds": {"m": MF.DEGRADED_LOOPED}}}


def test_812_looped_rep_with_facts_says_loop_not_dropped_tail():
    """The remedy must name the actionable diagnosis: the model looped, so a bigger window is
    futile and only a different rep can help."""
    rep = _looped_rep()
    rep["accepted"] = [{"band": "high", "school": "mcti"}]
    reqs = RQ.detect_requests(
        _result(reps=[rep], accepted=rep["accepted"]), claimed_bands=[],
        alternates_by_rec={"D1:x": [{"file": "pdftotext.txt", "kind": "text", "n_times": 90}]})
    assert [r["route"] for r in reqs] == ["7->6"]
    assert reqs[0]["params"]["degenerate_repetition"] is True
    assert "REPETITION LOOP" in reqs[0]["reason"]
    assert "more duplicates" in reqs[0]["reason"]
    assert "dropped tail" not in reqs[0]["reason"]


def test_812_loop_and_truncation_counted_apart():
    """Three shapes, three counters — a run log that says 'truncated' for a loop points the human
    at document size when the document is fine."""
    got = {}
    for kind in (MF.DEGRADED_LOOPED, MF.DEGRADED_TRUNCATED, MF.DEGRADED_REFUSED):
        rep = _looped_rep()
        rep["council_degraded"]["kinds"] = {"m": kind}
        rep["accepted"] = [{"band": "high", "school": "h"}]
        explain = {}
        RQ.detect_requests(_result(reps=[rep], accepted=rep["accepted"]),
                           claimed_bands=["high"], real_bands={"high"}, explain=explain)
        got[kind] = explain
    assert got[MF.DEGRADED_LOOPED]["suppressed_looped_reps"] == 1
    assert got[MF.DEGRADED_LOOPED]["suppressed_truncated_reps"] == 0
    assert got[MF.DEGRADED_TRUNCATED]["suppressed_truncated_reps"] == 1
    assert got[MF.DEGRADED_TRUNCATED]["suppressed_looped_reps"] == 0
    # a REFUSAL with facts is not counted here at all, and that is correct (#797): a refused
    # voter yields zero by construction, so the record's facts came from a complete surviving
    # read — there is nothing incomplete to report. Its counter is exercised on the zero-yield
    # path below.
    assert got[MF.DEGRADED_REFUSED]["suppressed_degraded_reps"] == 0
    rep = _looped_rep()
    rep["council_degraded"]["kinds"] = {"m": MF.DEGRADED_REFUSED}
    explain = {}
    RQ.detect_requests(_result(reps=[rep], accepted=[{"band": "high", "school": "h"}]),
                       claimed_bands=["high"], real_bands={"high"}, explain=explain)
    assert explain["suppressed_degraded_reps"] == 1      # zero-yield rep, refused council
    for e in got.values():
        assert e["suppressed_barren_reps"] == 0


def test_812_zero_yield_loop_reason_names_the_loop():
    reqs = RQ.detect_requests(_result(reps=[_looped_rep()], accepted=[]), claimed_bands=[])
    assert [r["route"] for r in reqs] == ["7->3"]
    assert "REPETITION LOOP" in reqs[0]["reason"]
    # #820: states what is known — the zero is about the council's read, never an assertion
    # that the document is unreadable/empty
    assert "council's read" in reqs[0]["reason"]
    assert "could not read" not in reqs[0]["reason"]


# --------------------------- #710/#711: outcomes that are not evidence ---------------------------
def test_710_nameless_yield_gets_one_more_rung_then_stops(monkeypatch):
    """#710 — Little Rock 0509000:9f652a5606: a 36-time bell-schedule PDF whose every fact returns
    school_name=None because the DOCUMENT never names its school. The ladder walked four reps
    against a defect no representation can fix. First occurrence still tries one more rep (it could
    be a bad read); the SECOND stops."""
    rep = {"rec_key": "D1:x", "file": "camelot_hybrid.txt", "accepted": [], "unresolved": [],
           "calls": [], "nameless_yield": True}
    alts = {"D1:x": [{"file": "pdftotext.txt", "kind": "text", "n_times": 34}]}

    first = RQ.detect_requests(_result(reps=[rep], accepted=[]), claimed_bands=[],
                               alternates_by_rec=alts, prior_nameless=set())
    assert [r["route"] for r in first] == ["7->6"]
    assert first[0]["params"]["nameless_yield"] is True
    assert "not one carries a school name" in first[0]["reason"].lower()

    explain = {}
    second = RQ.detect_requests(_result(reps=[rep], accepted=[]), claimed_bands=[],
                                alternates_by_rec=alts, prior_nameless={"D1:x"}, explain=explain)
    assert [r["route"] for r in second] == []          # MUST FAIL today: a 7->6 would be raised
    assert explain["suppressed_nameless_reps"] == 1


def test_852_a_nameless_rep_that_roster_unique_RESOLVED_starts_no_ladder_at_all():
    """#852 (PR #850 review) asked why the ladder-stop is unreachable when the nameless facts
    were accepted via `roster_unique` (#707: a one-school band resolves the degenerate group onto
    the district's one school). It is unreachable because there is NO LADDER: the record has
    accepted facts, so it never enters the zero-yield gate and no 7->6 is raised in the first
    place — nothing to stop. Folding `nameless_yield` into `incomplete` (the proposed fix) would
    do the OPPOSITE of #710: spend a rung on a record that resolved correctly, against a document
    a different rep cannot improve. Pinned: no request, first OR second occurrence, and the read
    stays visible on the rep for the telemetry rollup."""
    rep = {"rec_key": "D1:x", "file": "bell.txt", "nameless_yield": True, "calls": [],
           "accepted": [{"band": "high", "school": "little rock central high",
                         "identity": {"rule": "roster_unique"}}],
           "unresolved": []}
    alts = {"D1:x": [{"file": "pdftotext.txt", "kind": "text", "n_times": 34},
                     {"file": "raster_p-1.png", "kind": "image"}]}
    acc = [{"band": "high", "school": "little rock central high"}]
    for prior in (set(), {"D1:x"}):
        explain = {}
        reqs = RQ.detect_requests(_result(reps=[rep], accepted=acc), claimed_bands=["high"],
                                  alternates_by_rec=alts, prior_nameless=prior, explain=explain)
        assert [r for r in reqs if r["altitude"] == "representation"] == []
        assert explain["suppressed_nameless_reps"] == 0     # not "stopped" — never started
    assert rep["nameless_yield"] is True                     # the observation about the DOCUMENT stands


def test_710_partial_namelessness_is_untouched():
    """20 corpus rounds are PARTIALLY nameless (a hub listing five schools plus one unattributed
    table). That is a normal read and must not trip the stop."""
    from infrastructure.acquisition.stage7_extract.parse import nameless_yield
    assert nameless_yield([{"school_name": "Lincoln"}, {"school_name": None}]) is False
    assert nameless_yield([]) is False                             # barren is a different outcome
    assert nameless_yield([{"school_name": None}, {"school_name": " "}]) is True


def test_711_a_transient_429_retries_the_same_rep_then_the_ladder_is_untouched(monkeypatch):
    """#711 — a 429 says nothing about the document; retrying the SAME rep is obviously correct.
    Asserts the bounded retry happens at the call layer and is visible in the record."""
    import openai
    from infrastructure.acquisition.stage7_extract import openrouter as OR
    calls = {"n": 0}

    class _Completions:
        def create(self, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise openai.APITimeoutError(request=None)     # transient
            raise openai.APITimeoutError(request=None)

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    monkeypatch.setattr(openai, "OpenAI", _Client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    res = OR.call({"model": "google/gemini-2.5-flash-lite",
                   "messages": [{"role": "user", "content": "x"}]})
    assert not res.ok and res.error_kind == "transient"
    assert calls["n"] == 1 + OR.TRANSIENT_RETRIES        # the same rep was re-attempted, bounded
    assert res.transient_retries == OR.TRANSIENT_RETRIES  # ...and the count is auditable


def test_711_a_structural_context_error_is_NOT_retried(monkeypatch):
    """The taxonomy that matters: transient retries the same rep, STRUCTURAL does not (the
    identical request fails identically — #709). Retrying a context 400 would just burn money."""
    import httpx
    import openai
    from infrastructure.acquisition.stage7_extract import openrouter as OR
    calls = {"n": 0}
    msg = "Error code: 400 - This endpoint's maximum context length is 32768 tokens."
    resp = httpx.Response(400, request=httpx.Request("POST", "https://openrouter.ai/x"), text=msg)

    class _Completions:
        def create(self, **kw):
            calls["n"] += 1
            raise openai.APIStatusError(msg, response=resp, body=None)

    class _Chat:
        completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    monkeypatch.setattr(openai, "OpenAI", _Client)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    res = OR.call({"model": "google/gemini-2.5-flash-lite",
                   "messages": [{"role": "user", "content": "x"}]})
    assert not res.ok and res.error_kind == "context"
    assert calls["n"] == 1                    # exactly once — no retry
    assert res.transient_retries == 0
