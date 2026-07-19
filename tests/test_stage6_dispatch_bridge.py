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


# ---------------------- REQ-116/#83 hub-priority narrowing (pure, DB-free) ----------------------
def _h(rec_key, label=None, year=None, n_times=0):
    return {"rec_key": rec_key, "label": label, "year": year, "n_times": n_times, "schools": []}


def test_hub_priority_narrows_to_the_labeled_hub():
    winner, holds = BR._hub_priority_holds([
        _h("d:hub", "district_hub_by_band", 2025, 30),
        _h("d:es", "school_bell_table", 2025, 10),
        _h("d:hs", "school_start_end_list", 2024, 8)])
    assert winner == "d:hub" and holds == {"d:es", "d:hs"}


def test_no_labeled_hub_means_no_narrowing():
    # the unlabeled-tier-A arm is structurally ready but INACTIVE (no detector emits a hub category) —
    # an all-unlabeled or all-school-shape send set is never narrowed.
    winner, holds = BR._hub_priority_holds([
        _h("d:a", None, 2025, 30), _h("d:b", "school_bell_table", 2025, 10)])
    assert winner is None and holds == set()


def test_newest_then_densest_hub_wins_between_hubs():
    winner, holds = BR._hub_priority_holds([
        _h("d:old_hub", "district_hub_by_school", 2019, 90),
        _h("d:new_hub", "district_hub_by_band", 2025, 12),
        _h("d:es", "school_bell_table", 2025, 10)])
    assert winner == "d:new_hub" and holds == {"d:old_hub", "d:es"}
    # same year -> density breaks the tie
    winner2, _ = BR._hub_priority_holds([
        _h("d:sparse", "district_hub_by_band", 2025, 5),
        _h("d:dense", "district_hub_by_school", 2025, 40)])
    assert winner2 == "d:dense"


def test_unknown_year_hub_loses_to_dated_hub_but_still_narrows_alone():
    winner, _ = BR._hub_priority_holds([
        _h("d:noyear", "district_hub_by_band", None, 99),
        _h("d:dated", "district_hub_by_school", 2023, 5)])
    assert winner == "d:dated"                      # a known year outranks unknown (never auto-newest)
    winner_solo, holds_solo = BR._hub_priority_holds([
        _h("d:noyear", "district_hub_by_band", None, 99), _h("d:es", "school_bell_table", 2024, 3)])
    assert winner_solo == "d:noyear" and holds_solo == {"d:es"}


def test_hub_priority_composes_after_prefer_recent(monkeypatch):
    """Integration through district_release_input: a STALE hub held by prefer-recent must not win;
    the surviving newest hub narrows the rest. DB readers monkeypatched (the file's convention)."""
    def rec(rec_key, label, year, schools, n_times=20):
        return {"rec_key": rec_key, "url": f"http://x/{rec_key}", "tier": "A", "category": None,
                "signals": {"content_school_year": f"{year}-{(year + 1) % 100:02d}" if year else None,
                            "n_times_in_window": 4, "proximity_pairs": 2, "positive_kw": ["bell schedule"]},
                "is_emergent": 0, "intended_schools": schools, "label": label, "facets": {},
                "reps": [{"source": "extracted", "filename": "e.txt", "file_kind": "text",
                          "n_chars": 1000, "n_times": n_times, "usable": 1}]}
    records = [rec("d:hub_old", "district_hub_by_band", 2019, ["HS"]),      # superseded on HS
               rec("d:hub_new", "district_hub_by_band", 2025, ["HS"]),
               rec("d:es", "school_bell_table", 2024, ["ES"])]
    monkeypatch.setattr(REL, "load_district", lambda s, d: {"district_id": d, "name": "X", "state": "ZZ",
                                                            "district_dir": "x", "labeled_topology": None,
                                                            "nces_denominator": {"total": 3, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, d: records)
    _, out = BR.district_release_input(None, "D1")
    by = {r["rec_key"]: r for r in out}
    assert by["d:hub_new"]["decision"] == "send"
    assert by["d:hub_old"]["decision"] == "hold" and "stale-sibling" in by["d:hub_old"]["reason"]
    assert by["d:es"]["decision"] == "hold" and "hub-priority" in by["d:es"]["reason"]
    assert "d:hub_new" in by["d:es"]["reason"]      # the reason names the winner (traceable)


# ---------------------- #540 Edlio sibling-variant holds (pure, DB-free) ----------------------
def _e(rec_key, url, wd_strong=False, year=None, n_times=0):
    return {"rec_key": rec_key, "url": url, "wd_strong": wd_strong, "year": year,
            "n_times": n_times, "label": None, "schools": []}


def test_sibling_variant_family_sends_the_regular_day_page():
    # the DASD shape: variant permalinks (strong wrong-day votes) hold; the clean page sends
    holds = BR._sibling_variant_holds([
        _e("d:reg", "https://ms.dasd.us/apps/bell_schedules/index.jsp?id=100", wd_strong=False),
        _e("d:early", "https://ms.dasd.us/apps/bell_schedules/index.jsp?id=101", wd_strong=True),
        _e("d:remote", "https://ms.dasd.us/apps/bell_schedules/index.jsp?id=102", wd_strong=True)])
    assert set(holds) == {"d:early", "d:remote"} and set(holds.values()) == {"d:reg"}


def test_bare_app_hub_beats_variant_permalinks():
    holds = BR._sibling_variant_holds([
        _e("d:hub", "https://gv.dasd.us/apps/bell_schedules/", wd_strong=False),
        _e("d:var", "https://gv.dasd.us/apps/bell_schedules/index.jsp?id=200", wd_strong=False)])
    assert holds == {"d:var": "d:hub"}


def test_variant_only_family_still_sends_its_best():
    # zero recall cost: a family with ONLY variant pages keeps one (no fresher/cleaner sibling exists)
    holds = BR._sibling_variant_holds([
        _e("d:v1", "https://x.org/apps/bell_schedules/index.jsp?id=1", wd_strong=True, n_times=9),
        _e("d:v2", "https://x.org/apps/bell_schedules/index.jsp?id=2", wd_strong=True, n_times=3)])
    assert holds == {"d:v2": "d:v1"}


def test_different_hosts_are_different_families():
    # ms.dasd.us and hs.dasd.us are different SCHOOLS — never collapsed into one family
    holds = BR._sibling_variant_holds([
        _e("d:ms", "https://ms.dasd.us/apps/bell_schedules/", wd_strong=False),
        _e("d:hs", "https://hs.dasd.us/apps/bell_schedules/", wd_strong=False)])
    assert holds == {}


def test_non_edlio_urls_never_form_a_family():
    holds = BR._sibling_variant_holds([
        _e("d:a", "https://x.org/bell-schedules/a"), _e("d:b", "https://x.org/bell-schedules/b")])
    assert holds == {}
