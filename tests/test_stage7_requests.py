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


def test_barren_rep_with_alternate_routes_7to6():
    res = _result(
        reps=[{"rec_key": "D1:aa", "file": "pdftotext.txt", "accepted": []}],
        accepted=[])
    reqs = RQ.detect_requests(res, claimed_bands=[],
                              alternates_by_rec={"D1:aa": [{"file": "raster_p-1.png", "kind": "image"}]})
    rep_reqs = [r for r in reqs if r["altitude"] == "representation"]
    assert len(rep_reqs) == 1
    r = rep_reqs[0]
    assert r["route"] == "7->6" and r["target"] == "D1:aa"
    assert r["params"]["alternate_reps"][0]["kind"] == "image"


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
