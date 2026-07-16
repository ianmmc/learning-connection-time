"""Stage 6 release->routing bridge (REQ-101, slice 4 — app layer).

Verifies the bridge reads the release decision (via the stage5 `release` readers), runs the real
`release.decide()`, enriches send reps with size signals, and assembles the package — with the
DB readers monkeypatched, so no Postgres/Docker is needed (the live DB path is exercised by the
govdb integration suite).
"""
import math

from infrastructure.acquisition.process_governance import stage6_dispatch as BR
from infrastructure.acquisition.stage5_filter import release as REL

CLEAN_TEXT = 0.00050 + 0.00022 + 0.5 * 0.00060   # low-cost-text bootstrap = 0.00102


def _fake_record(rec_key, label, reps):
    # the shape stage5 release.load_district_records yields
    return {"rec_key": rec_key, "url": f"http://x/{rec_key}", "tier": "A", "category": None,
            "signals": {"visual_text_gap": False}, "is_emergent": 0, "intended_schools": [],
            "label": label, "flags": [], "reps": reps}


# ---------------------- #107 prefer-recent (pure, DB-free) ----------------------
def _s(rec_key, year, schools):
    return {"rec_key": rec_key, "year": year, "schools": schools}


def test_prefer_recent_holds_stale_same_school_siblings():
    # Redbank Valley HS shape: newest sends, the three older HOLD
    holds = BR._prefer_recent_holds([
        _s("d:2025", 2025, ["HS"]), _s("d:2021", 2021, ["HS"]),
        _s("d:2020", 2020, ["HS"]), _s("d:2018", 2018, ["HS"])])
    assert holds == {"d:2021", "d:2020", "d:2018"}


def test_prefer_recent_keeps_sole_doc_unknown_year_and_no_school():
    # zero recall cost: a sole doc for its school, an unknown year, and a no-intended-school record
    # can never be proven superseded → all kept
    holds = BR._prefer_recent_holds([
        _s("d:solo", 2019, ["ES"]),           # only doc for ES
        _s("d:noyear", None, ["HS"]),         # unknown year coexists (never auto-oldest)
        _s("d:noschool", 2015, [])])          # no school → can't establish supersession
    assert holds == set()


def test_prefer_recent_multi_school_held_only_when_superseded_everywhere():
    # a record covering HS+ES, superseded on HS but NEWEST on ES → KEPT (still ES's best evidence)
    base = [_s("d:hsnew", 2025, ["HS"]), _s("d:multi", 2019, ["HS", "ES"])]
    assert BR._prefer_recent_holds(base) == set()
    # add a newer ES doc → multi is now superseded on BOTH schools → held
    assert BR._prefer_recent_holds(base + [_s("d:esnew", 2024, ["ES"])]) == {"d:multi"}


def test_prefer_recent_co_newest_year_both_kept():
    holds = BR._prefer_recent_holds([_s("d:a", 2025, ["HS"]), _s("d:b", 2025, ["HS"])])
    assert holds == set()


def test_bridge_reads_decides_enriches_and_assembles(monkeypatch):
    reps = [{"source": "extracted", "filename": "extracted.txt", "file_kind": "text",
             "n_chars": 1500, "n_times": 6, "usable": 1}]
    records = [
        _fake_record("a", "school_bell_table", reps),     # a TARGET label -> send
        _fake_record("z", "board_calendar", reps),           # non-target -> reject
    ]
    monkeypatch.setattr(REL, "load_district",
                        lambda s, did: {"district_id": did, "name": "X", "district_dir": f"{did}_x",
                                        "labeled_topology": "per_school",
                                        "nces_denominator": {"total": 3, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: records)

    pkg = BR.build_handoff_package(session=None, district_ids=["0100810"])

    assert len(pkg["districts"]) == 1
    block = pkg["districts"][0]
    assert block["district_id"] == "0100810"
    assert block["n_send_reps"] == 1                       # only the target record routed
    sent = [r for r in block["records"] if r["decision"] == "send"][0]
    assert sent["reps"][0]["councils"] == ["low-cost-text"]
    assert math.isclose(sent["reps"][0]["est_usd"], CLEAN_TEXT, rel_tol=1e-9)
    # the reject is still recorded, with no reps
    rej = [r for r in block["records"] if r["decision"] == "reject"][0]
    assert rej["reps"] == []
    assert math.isclose(pkg["cost"]["total_usd"], CLEAN_TEXT, rel_tol=1e-9)
    assert pkg["cost"]["provenance"] == "bootstrap"


def test_verified_only_holds_the_unlabeled_tier_A_sends(monkeypatch):
    """gate@6 training-grade mode: keep only human-labeled target sends; the speculative unlabeled
    tier-A auto-send is downgraded to `hold` (traceable), not routed/priced."""
    reps = [{"source": "extracted", "filename": "extracted.txt", "file_kind": "text",
             "n_chars": 1500, "n_times": 6, "usable": 1}]
    records = [
        _fake_record("a", "school_bell_table", reps),     # labeled TARGET -> send in both modes
        _fake_record("b", None, reps),                       # unlabeled tier-A -> send by default, HELD when verified
    ]
    monkeypatch.setattr(REL, "load_district",
                        lambda s, did: {"district_id": did, "name": "X", "district_dir": f"{did}_x",
                                        "labeled_topology": "per_school",
                                        "nces_denominator": {"total": 3, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: records)

    default = BR.build_handoff_package(session=None, district_ids=["0100810"])
    assert default["districts"][0]["n_send_reps"] == 2        # target + auto:tier-A both routed
    assert default["verified_only"] is False

    verified = BR.build_handoff_package(session=None, district_ids=["0100810"], verified_only=True)
    block = verified["districts"][0]
    assert block["n_send_reps"] == 1                          # only the labeled target routed
    assert verified["verified_only"] is True
    sent = [r for r in block["records"] if r["decision"] == "send"]
    assert [r["rec_key"] for r in sent] == ["a"]
    held = [r for r in block["records"] if r["decision"] == "hold"][0]
    assert held["rec_key"] == "b" and held["reason"].startswith("verified-only:held")
    assert held["reps"] == []


def test_enrich_send_threads_n_schools_and_n_bytes(tmp_path, monkeypatch):
    """Issue #55: the bridge populates the size inputs cost.py documents — `n_schools` from the
    record's intended_schools, and `n_bytes` (file size, the documented proxy) for a binary rep
    whose n_chars is None. Bootstrap dollar numbers are untouched (flat pricing reads neither)."""
    monkeypatch.setattr(BR.paths, "RAW_CAPTURES", tmp_path)
    ddir, h = "0100810_x", "abc123"
    png = tmp_path / ddir / "captures" / h / "page.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"\x89PNG" + b"0" * 96)                    # 100 bytes on disk
    reps = [{"source": "capture:png", "filename": "page.png", "file_kind": "image",
             "n_chars": None, "n_times": None, "usable": 1},
            {"source": "extracted", "filename": "t.txt", "file_kind": "text",
             "n_chars": 1500, "n_times": 6, "usable": 1}]
    rec = {"rec_key": f"0100810:{h}", "intended_schools": ["A Elem", "B Middle"]}

    out = BR._enrich_send([{"file": "page.png", "kind": "image"},
                           {"file": "t.txt", "kind": "text"}], reps, rec, ddir)
    img, txt = out[0], out[1]
    assert img["n_schools"] == 2                               # intended_schools count threaded
    assert img["n_bytes"] == 100                               # binary size proxy (n_chars is None)
    assert txt["n_chars"] == 1500 and txt["n_times"] == 6
    assert "n_bytes" not in txt                                # text reps keep their real n_chars
    # a binary whose file is absent degrades to None, never raises
    missing = BR._enrich_send([{"file": "gone.png", "kind": "image"}], reps, rec, ddir)[0]
    assert missing["n_bytes"] is None
    # no intended_schools -> n_schools None (cost._n_schools then falls back to n_times/default)
    none_rec = {"rec_key": f"0100810:{h}", "intended_schools": []}
    assert BR._enrich_send([{"file": "t.txt", "kind": "text"}], reps, none_rec, ddir)[0]["n_schools"] is None


def test_missing_district_is_skipped(monkeypatch):
    monkeypatch.setattr(REL, "load_district", lambda s, did: None)
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: [])
    pkg = BR.build_handoff_package(session=None, district_ids=["9999999"])
    assert pkg["districts"] == []
    assert pkg["cost"]["total_usd"] == 0
