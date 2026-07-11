"""Stage 7 request-more-evidence detection/routing (REQ-117, STAGE7 §4) — pure, no DB/network.
Feeds synthetic extraction results and asserts the routed requests at all three altitudes."""
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
    assert explain == {"phantom_bands": ["middle"], "suppressed_barren_reps": 1}


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
