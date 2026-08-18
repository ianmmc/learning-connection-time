"""REQ-093 — Stage 5 keyword knobs load from config; the instructional-time regex is MINUTES-ONLY
(hours reverted after the harness proved it net-negative — a vision problem); an instructional-time
hit rescues a record from the n==0 / neg-keyword drop (now via the V2 detectors+combiner — the V1
tier_and_category cascade was deleted, issue #56)."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from infrastructure.acquisition.stage5_filter import build_signals as BS  # noqa: E402
from infrastructure.acquisition.stage5_filter import combiner as COMB  # noqa: E402


def _sig(**over):
    base = {"n_times": 0, "n_times_in_window": 0, "proximity_pairs": 0, "times_after_5pm": 0,
            "positive_kw": [], "negative_kw": {"board": [], "sports": [], "calendar": [], "transport": []},
            "neg_total": 0, "instructional_time": False, "has_table": False, "period_hits": 0,
            "roster_school_names_hit": 0, "max_text_chars": 500, "pages": []}
    base.update(over)
    return base


def test_keywords_loaded_from_config_including_class_schedule():
    assert "class schedule" in BS.POSITIVE_KW      # REQ-093 addition (ROY)
    assert "bell schedule" in BS.POSITIVE_KW        # baseline
    assert "academic calendar" in BS.NEG_CALENDAR   # baseline negative class


def test_instructional_regex_is_minutes_only_no_hours_false_positives():
    """REQ-093's standing intent — MINUTES only, hours stay reverted (a vision problem, not a
    regex one) and board 'minutes' never false-positives. #683 (2026-07-29) narrowed the POSITIVE
    side deliberately: a declaration now needs a NUMBER + an instruction referent + DAY scope, so
    the two shapes this test used to pin ('450 minutes of instruction' with no day scope — per
    week? per year? — and the number-less 'instructional minutes per day') are no longer matches.
    That is measured, not stylistic: over the labeled corpus the old form fired on 15 records and
    was wrong on 13. The hours/board assertions below are the part REQ-093 actually protects."""
    assert BS.INSTRUCTIONAL_RE.search("students receive 450 minutes of instruction per day")
    assert BS.INSTRUCTIONAL_RE.search("240 instructional minutes per school day")
    # hours reverted (vision problem) -> must NOT match, so no marketing-copy false positives:
    assert not BS.INSTRUCTIONAL_RE.search("our instructional hours are flexible")
    assert not BS.INSTRUCTIONAL_RE.search("147 days x 7.5 hrs/day")
    # board-meeting "minutes" never false-positives (the original anchor):
    assert not BS.INSTRUCTIONAL_RE.search("board meeting minutes approved")


def test_instructional_time_rescues_calendar_record_from_the_drop():
    # instr hit, no clock times, calendar keywords -> lf_explicit_minutes keeps it alive (never a
    # tier-D suppress via no-times, never a hard calendar drop) — the DUNSEITH rescue, V2-style
    out = COMB.score_record(
        _sig(instructional_time=True, neg_total=2,
             negative_kw={"board": [], "sports": [], "calendar": ["academic calendar", "holiday"], "transport": []}))
    assert out["decision"] == "send" and out["tier"] == "A"
    assert out["category"] == "explicit_instructional_time"


def test_no_times_no_instr_still_drops_to_D():
    out = COMB.score_record(_sig())
    assert out["decision"] == "suppress" and out["tier"] == "D"


def test_strong_target_still_tier_A_not_demoted_by_rescue():
    # a real bell schedule (time pair + positive kw) must remain A even if instr also true
    out = COMB.score_record(
        _sig(n_times=4, n_times_in_window=4, proximity_pairs=2, positive_kw=["bell schedule"],
             instructional_time=True))
    assert out["decision"] == "send" and out["tier"] == "A"


# ---- REQ-092 handbook page-harvest ----
def _pages(*counts):
    return [{"page": i + 1, "n_times": c} for i, c in enumerate(counts)]


def test_harvest_pinpoints_the_standout_schedule_page():
    # a 15-page handbook where page 3 is the schedule (42 times) -> harvest just page 3 (Pittsylvania chs)
    assert BS.harvest_schedule_pages(_pages(0, 0, 42, 0, 0, 0, 9, 4, 0, 0, 2, 2, 0, 6, 0)) == [3]


def test_harvest_returns_multiple_when_several_pages_stand_out():
    # two comparable schedule pages -> both harvested (>= half the peak, floor at min_times)
    assert BS.harvest_schedule_pages(_pages(0, 0, 0, 8, 2, 0, 2, 0, 6)) == [4, 9]


def test_harvest_empty_when_single_page_or_nothing_stands_out():
    assert BS.harvest_schedule_pages(_pages(42)) == []          # single page
    assert BS.harvest_schedule_pages(_pages(2, 3, 1, 0)) == []  # nothing clears the floor (min 6)
    assert BS.harvest_schedule_pages([]) == []


# ---- whole-document per-page extraction (the removed 60-page scan cap) ----
def _fake_pdftotext(monkeypatch, stdout, *, n_pages, per_page="PER-PAGE"):
    """Stub the two subprocess primitives: the whole-doc call returns `stdout` (None => it raised),
    and the per-page fallback returns a marker so a test can tell which path ran."""
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "-f" in cmd:                      # the per-page primitive
            return SimpleNamespace(stdout=f"{per_page}{cmd[cmd.index('-f') + 1]}")
        if stdout is None:
            raise subprocess.TimeoutExpired(cmd, 1)
        return SimpleNamespace(stdout=stdout)

    monkeypatch.setattr(BS.subprocess, "run", fake_run)
    monkeypatch.setattr(BS, "pdf_page_count", lambda _pdf: n_pages)
    return calls


def test_page_texts_drop_only_the_trailing_form_feed(monkeypatch):
    # pdftotext writes a form feed after the LAST page -> exactly one empty tail part to drop.
    _fake_pdftotext(monkeypatch, "a\fb\f", n_pages=2)
    assert BS.pdf_page_texts(Path("x.pdf")) == ["a", "b"]
    _fake_pdftotext(monkeypatch, "a\fb", n_pages=2)          # no trailing feed
    assert BS.pdf_page_texts(Path("x.pdf")) == ["a", "b"]


def test_page_texts_keep_a_blank_final_page_so_page_numbers_stay_true(monkeypatch):
    # a legitimately EMPTY last page must keep its slot — stripping it would shift every later
    # page number, and page numbers are user-visible (the send hint + the human _pages_list).
    _fake_pdftotext(monkeypatch, "a\f\f", n_pages=2)
    assert BS.pdf_page_texts(Path("x.pdf")) == ["a", ""]


def test_page_texts_fall_back_when_the_split_disagrees_with_the_page_count(monkeypatch):
    # 3 parts but pdfinfo says 5 pages -> an off-by-N would silently misnumber every page.
    calls = _fake_pdftotext(monkeypatch, "a\fb\fc\f", n_pages=5)
    assert BS.pdf_page_texts(Path("x.pdf")) == [f"PER-PAGE{p}" for p in range(1, 6)]
    assert sum("-f" in c for c in calls) == 5          # the per-page primitive really ran


def test_page_texts_never_return_empty_when_the_whole_doc_call_fails(monkeypatch):
    # The load-bearing guarantee: [] would empty harvest_pages, re-arm lf_no_times, and suppress
    # the record out of dispatch entirely — a silently lost district, not a visible error.
    _fake_pdftotext(monkeypatch, None, n_pages=3)
    assert BS.pdf_page_texts(Path("x.pdf")) == ["PER-PAGE1", "PER-PAGE2", "PER-PAGE3"]
    _fake_pdftotext(monkeypatch, "", n_pages=2)       # empty stdout is a failure too
    assert BS.pdf_page_texts(Path("x.pdf")) == ["PER-PAGE1", "PER-PAGE2"]


def test_no_per_page_scan_cap_is_reintroduced():
    # A cap lived here twice (15, then 60) and both times made pages past it structurally invisible
    # — Memphis 4700148:00f553bcfc read 3 times instead of 838 because its schedule is on pp.89-91.
    # The whole document is scanned; a reintroduced ceiling would silently restore that bug.
    assert not hasattr(BS, "HANDBOOK_MAX_PAGES")


def test_page_texts_scan_past_the_old_cap(monkeypatch):
    _fake_pdftotext(monkeypatch, "\f".join(f"page{p}" for p in range(1, 121)) + "\f", n_pages=120)
    out = BS.pdf_page_texts(Path("x.pdf"))
    assert len(out) == 120 and out[119] == "page120"


def test_page_time_signals_counts_times_and_flags_an_instructional_declaration():
    out = BS.page_time_signals(["nothing here", "doors open 7:45 a.m. and close 2:30 p.m.",
                                "We have 181 instructional days with 495 minutes of instruction per day."])
    assert [p["page"] for p in out] == [1, 2, 3]
    assert [p["n_times"] for p in out] == [0, 2, 0]
    # page 3 carries an explicit_instructional_time declaration and NO clock time — the colon-free
    # class a time count structurally cannot see.
    assert [p["instr"] for p in out] == [False, False, True]


# ---- #821 the ABSOLUTE time-bearing page floor ----
def _ipages(*specs):
    """specs: (n_times, instr) per page, 1-based."""
    return [{"page": i + 1, "n_times": n, "instr": ins} for i, (n, ins) in enumerate(specs)]


def test_floor_keeps_every_page_the_relative_harvest_throws_away():
    # MUST FAIL TODAY against harvest_schedule_pages: nothing clears its floor of 6, so it selects
    # NOTHING and the whole 10-page document is sent. The absolute floor keeps p2 and p5 (times),
    # p1 (identity) and the neighbours of the time-bearing pages — and drops pages 7-10.
    pages = _pages(0, 1, 0, 0, 3, 0, 0, 0, 0, 0)
    assert BS.harvest_schedule_pages(pages) == []
    assert BS.time_bearing_pages(pages) == [1, 2, 3, 4, 5, 6]


def test_floor_is_lossless_where_the_relative_harvest_is_not():
    # Memphis-shaped: a peak page sets cut = max(6, peak*0.5) and the tail is discarded. The floor
    # keeps EVERY page carrying a time — that is the whole property.
    pages = _pages(22, 22, 34, 56, 12, 0, 0, 0, 0, 0, 9, 0, 0, 0, 0)
    harvested = set(BS.harvest_schedule_pages(pages))
    floored = set(BS.time_bearing_pages(pages))
    lost_by_harvest = sum(p["n_times"] for p in pages if p["page"] not in harvested)
    lost_by_floor = sum(p["n_times"] for p in pages if p["page"] not in floored)
    assert harvested == {3, 4}          # cut = max(6, 56*0.5) = 28
    assert lost_by_harvest == 65        # p1, p2, p5 and p11 discarded despite carrying times
    assert lost_by_floor == 0           # the absolute floor cannot lose a time
    assert floored                      # and it still scopes: pages 7-10 and 13-15 are dropped


def test_floor_keeps_an_instructional_only_page():
    # MUST FAIL against a naive n_times>0 floor. explicit_instructional_time evidence is colon-free
    # ("495 minutes of instruction per day") so it scores zero clock times — Memphis
    # 4700148:00f553bcfc p39 is exactly this, and it is that record's ONLY such page.
    pages = _ipages((4, False), (0, False), (0, False), (0, False), (0, False),
                    (0, False), (0, True), (0, False), (0, False))
    assert 7 in BS.time_bearing_pages(pages)
    # and it is kept for the DECLARATION, not by neighbouring a time-bearing page
    assert 6 not in BS.time_bearing_pages(pages) and 8 not in BS.time_bearing_pages(pages)


def test_floor_keeps_page_one_and_the_neighbours_of_a_time_bearing_page():
    pages = _pages(0, 0, 0, 0, 9, 0, 0, 0)
    assert BS.time_bearing_pages(pages) == [1, 4, 5, 6]
    assert BS.time_bearing_pages(pages, keep_first=False) == [4, 5, 6]
    assert BS.time_bearing_pages(pages, keep_neighbors=False) == [1, 5]


def test_floor_declines_when_there_is_nothing_to_gain():
    assert BS.time_bearing_pages([]) == []
    assert BS.time_bearing_pages(_pages(9)) == []              # single page — nothing to scope
    assert BS.time_bearing_pages(_pages(0, 0, 0)) == []        # nothing qualifies -> full read
    # EVERY page qualifies -> a slice identical to the document is pure duplication
    assert BS.time_bearing_pages(_pages(3, 3, 3)) == []


def test_floor_is_inert_for_a_record_with_no_page_concept():
    # An HTML capture has no PDF and therefore no `pages` at all — the floor cannot fire.
    assert BS.time_bearing_pages(None) == []


def test_page_text_from_restores_the_per_page_form_feed():
    # pdf_page_texts splits ON the form feeds; pdf_page_text KEEPS the one for its page. Re-adding
    # it is what keeps a slice cut from cached texts byte-identical to one cut by re-extracting —
    # without it all 131 existing harvest slices shift by one char per page on re-ingest.
    assert BS.page_text_from(["alpha", "beta"], 1) == "alpha\f"
    assert BS.page_text_from(["alpha", "beta"], 2) == "beta\f"
    assert BS.page_text_from(["alpha"], 7) == ""           # out of range, caller re-extracts


def test_build_slice_labels_each_kind_and_shares_one_builder():
    got = BS.build_slice([1, 2], lambda p: f"page{p} 8:0{p} AM", BS.TIMEBEARING_SLICE_SOURCE)
    assert got is not None
    _, kw = got
    assert kw["source"] == BS.TIMEBEARING_SLICE_SOURCE
    assert kw["filename"] == BS.TIMEBEARING_SLICE_FILE and kw["usable"] == 1
    # the harvest wrapper is the SAME builder, only the labelling differs
    _, hkw = BS.build_slice([1], lambda p: "8:05 AM", BS.HARVEST_SLICE_SOURCE)
    assert hkw["filename"] == BS.HARVEST_SLICE_FILE
    assert BS.build_slice([1], lambda p: "   ", BS.HARVEST_SLICE_SOURCE) is None   # nothing usable


def test_slice_path_keeps_the_harvest_name_and_suffixes_the_others():
    # the harvest slice must not MOVE — every existing artifact keeps its path
    h = BS.slice_path("0100810", "0100810:abc123", BS.HARVEST_SLICE_SOURCE)
    t = BS.slice_path("0100810", "0100810:abc123", BS.TIMEBEARING_SLICE_SOURCE)
    assert h.name == "0100810_abc123.txt"
    assert t.name == f"0100810_abc123.{BS.TIMEBEARING_SLICE_SOURCE}.txt"
    assert h != t and h.parent == t.parent          # they coexist for one record


def test_is_handbook_needs_the_word_and_real_length():
    assert BS.is_handbook_doc("student parent handbook ...", {}, n_pages=15, max_chars=9000) is True
    assert BS.is_handbook_doc("bell schedule", {}, n_pages=1, max_chars=400) is False   # not a handbook
    assert BS.is_handbook_doc("", {"pdf": "student_handbook.pdf"}, n_pages=3, max_chars=500) is True  # filename
    assert BS.is_handbook_doc("handbook", {}, n_pages=1, max_chars=200) is False        # too short, single page


# ---- REQ-091 de-chrome: signals compute over MAIN when a page.main.txt segment exists ----
def test_signals_compute_over_dechromed_main_not_full_page(tmp_path):
    full = "Board of Education agenda. Athletics tournament. Footer Building Hours 7:15 AM - 3:15 PM."
    (tmp_path / "page.txt").write_text(full)
    texts = [{"usable": True, "text_file": "page.txt", "n_chars": len(full), "n_times": 2}]
    main = "Bell Schedule. School starts at 8:00 AM and dismissal is at 3:00 PM every day. " * 5  # clean, >120
    sig_full, _, _ = BS.compute_signals(tmp_path, texts, [], {}, main_text=None)
    sig_dech, _, _ = BS.compute_signals(tmp_path, texts, [], {}, main_text=main)
    assert sig_full["dechromed"] is False and sig_dech["dechromed"] is True
    # chrome negatives (board/sports) drop out when we score MAIN; the real positive kw is present
    assert sig_dech["neg_total"] < sig_full["neg_total"]
    assert "bell schedule" in sig_dech["positive_kw"]


def test_table_rep_read_once_not_twice(tmp_path, monkeypatch):
    """#353: the table_reps comprehension called read(t) twice per qualifying rep — once in the
    `'---' in read(t)` filter, once for the value — doubling disk I/O for every table-source rep.
    Assert the table rep's file is read exactly once during compute_signals."""
    tbl = "Period 1 08:00-08:50\n---\nGrant High 08:00 to 15:00 bell schedule dismissal"
    (tmp_path / "camelot.txt").write_text(tbl)
    texts = [{"usable": True, "text_file": "camelot.txt", "source": "camelot_hybrid",
              "n_chars": len(tbl), "n_times": 4}]
    reads = {}
    import pathlib
    real = pathlib.Path.read_text
    def counting_read_text(self, *a, **k):
        reads[self.name] = reads.get(self.name, 0) + 1
        return real(self, *a, **k)
    monkeypatch.setattr(pathlib.Path, "read_text", counting_read_text)
    BS.compute_signals(tmp_path, texts, [], {}, main_text=None)
    assert reads.get("camelot.txt", 0) == 1, (
        f"table rep read {reads.get('camelot.txt')}× — should be once (#353)")


def test_dechrome_falls_back_when_main_too_thin(tmp_path):
    full = "School hours 8:00 AM to 3:00 PM bell schedule dismissal arrival every school day here."
    (tmp_path / "page.txt").write_text(full)
    texts = [{"usable": True, "text_file": "page.txt", "n_chars": len(full), "n_times": 2}]
    sig, _, _ = BS.compute_signals(tmp_path, texts, [], {}, main_text="too short")  # below USABLE_MIN_CHARS
    assert sig["dechromed"] is False  # graceful fallback to the full page — never worse than today


# ----------------------------- Q2.1: harvest-slice materialization -----------------------------
def test_build_harvest_slice_concatenates_pages_and_counts_times():
    pages = {4: "Lincoln High 08:00 to 14:30", 9: "Grant Middle 07:45 to 14:15"}
    out = BS.build_harvest_slice([4, 9], lambda p: pages.get(p, ""))
    assert out is not None
    slice_text, rep = out
    assert "Lincoln High" in slice_text and "Grant Middle" in slice_text
    assert rep["source"] == "harvest_slice" and rep["filename"] == "harvest_slice.txt"
    assert rep["file_kind"] == "text" and rep["usable"] == 1
    assert rep["n_chars"] == len(slice_text)
    assert rep["n_times"] == 4          # two start + two end times across the two pages


def test_build_harvest_slice_returns_none_when_empty():
    assert BS.build_harvest_slice([], lambda p: "") is None
    assert BS.build_harvest_slice([1, 2], lambda p: "") is None
    assert BS.build_harvest_slice([1, 2], lambda p: None) is None


# ---- v2.1 label migration (REQ-114 v2.1) ----
def test_migrate_label_v21_renames_targets_and_folds_nontargets():
    # clean target renames
    assert BS.migrate_label_v21("school_bell_schedule", [], {})[0] == "school_bell_table"
    assert BS.migrate_label_v21("district_hub_schedule", [], {})[0] == "district_hub_by_school"
    assert BS.migrate_label_v21("target_other_shape" if False else "nonstandard_format", [], {})[0] == "target_other_shape"
    # unchanged targets
    assert BS.migrate_label_v21("school_start_end_prose", [], {})[0] == "school_start_end_prose"
    assert BS.migrate_label_v21("explicit_instructional_time", [], {})[0] == "explicit_instructional_time"
    assert BS.migrate_label_v21("unusable", [], {})[0] == "unusable"


def test_migrate_label_v21_nontarget_becomes_absent_plus_confounder_facet():
    p, f = BS.migrate_label_v21("embedded_feed", [], {})
    assert p == "target_absent" and f.get("news_feed") == "yes"
    p, f = BS.migrate_label_v21("board_schedule", [], {})
    assert p == "target_absent" and f.get("board") == "yes"


def test_migrate_label_v21_folds_v20_flags_into_facets():
    p, f = BS.migrate_label_v21("school_start_end_prose",
                                ["building_hours_visible", "buried_in_long_doc", "target_image_only"], {})
    assert p == "school_start_end_prose"      # a target keeps its shape
    assert f.get("office_building_hours") == "yes" and f.get("buried_handbook") == "yes" and f.get("needs_vision") == "yes"


def test_every_migrated_primary_is_in_the_v21_vocabulary():
    vocab = BS.TARGET_LABELS | BS.NONTARGET_PRIMARIES
    for old in ["school_bell_schedule", "district_hub_schedule", "nonstandard_format", "none",
                "school_start_end_prose", "explicit_instructional_time", "unusable",
                "embedded_feed", "board_schedule", "sports_schedule", "academic_calendar",
                "community_calendar", "transportation_schedule", "other_schedule"]:
        assert BS.migrate_label_v21(old, [], {})[0] in vocab, old


# ---- issue #59: migrate_labels_v21 re-run guard (a real run must not re-fold flags over human edits) ----
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSess:
    """SELECT (no params) returns the seeded label rows; UPDATE (params) is recorded."""
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def execute(self, stmt, params=None):
        if params is None:
            return _FakeResult(self.rows)
        self.updates.append(params)
        return _FakeResult([])


def _v20_rows():
    # (rec_key, primary_label, flags_json, facets_json) — a genuinely un-migrated v2.0 state
    return [("d:1", "school_bell_schedule", "[]", "{}"),
            ("d:2", "board_schedule", "[]", None)]


def _migrated_rows():
    # already v2.1: in-vocabulary primaries AND non-empty facets (possibly HUMAN-edited since)
    return [("d:1", "school_bell_table", '["building_hours_visible"]', '{"needs_vision": "yes"}'),
            ("d:2", "target_absent", "[]", '{"board": "yes"}')]


def test_migrate_labels_v21_real_run_works_on_fresh_v20_state():
    sess = _FakeSess(_v20_rows())
    moves = BS.migrate_labels_v21(sess, dry_run=False)
    assert sum(moves.values()) == 2
    assert len(sess.updates) == 2                     # both rows updated


def test_migrate_labels_v21_refuses_a_second_real_run():
    sess = _FakeSess(_migrated_rows())
    with pytest.raises(RuntimeError, match="already run"):
        BS.migrate_labels_v21(sess, dry_run=False)
    assert sess.updates == []                          # nothing touched — human facets are safe


def test_migrate_labels_v21_dry_run_and_force_still_allowed():
    # dry_run only tallies (never guarded); force=True explicitly overrides the guard
    sess = _FakeSess(_migrated_rows())
    moves = BS.migrate_labels_v21(sess, dry_run=True)
    assert sum(moves.values()) == 2 and sess.updates == []
    forced = _FakeSess(_migrated_rows())
    BS.migrate_labels_v21(forced, dry_run=False, force=True)
    assert len(forced.updates) == 2


# ---- issue #58: harvest slices are DERIVED artifacts — written under data/acquisition, never data/raw ----
def test_harvest_slice_path_is_under_acquisition_not_raw(monkeypatch, tmp_path):
    monkeypatch.setattr(BS, "HARVEST_SLICES_DIR", tmp_path / "acq" / "harvest_slices")
    p = BS.harvest_slice_path("0100810", "0100810:abc123")
    assert p == tmp_path / "acq" / "harvest_slices" / "0100810" / "0100810_abc123.txt"


def test_resolve_harvest_slice_prefers_new_location_falls_back_to_legacy(monkeypatch, tmp_path):
    new_root = tmp_path / "acq" / "harvest_slices"
    raw_root = tmp_path / "raw"
    monkeypatch.setattr(BS, "HARVEST_SLICES_DIR", new_root)
    monkeypatch.setattr(BS, "RAW_DIR", raw_root)
    did, ddir, rk = "0100810", "0100810_slug", "0100810:abc123"
    # neither exists -> None
    assert BS.resolve_harvest_slice(did, ddir, rk) is None
    # legacy pre-#58 slice (inside the raw capture dir) still readable
    legacy = raw_root / ddir / "captures" / "abc123" / BS.HARVEST_SLICE_FILE
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy slice")
    assert BS.resolve_harvest_slice(did, ddir, rk) == legacy
    # the new derived-artifact location wins when present
    new = BS.harvest_slice_path(did, rk)
    new.parent.mkdir(parents=True)
    new.write_text("new slice")
    assert BS.resolve_harvest_slice(did, ddir, rk) == new


# ---- #537 follow-on: positional non-regular-day evidence (signal + detector + combiner rule) ----
def test_nonstandard_positional_heading_and_near_times():
    # the DASD shape: the term TITLES the schedule and the times sit right under it
    t = "Early Dismissal Bell Schedule\nPeriod 1  8:00 AM - 8:35 AM\nPeriod 2  8:40 AM - 9:15 AM"
    tpos = [off for off, _ in BS.in_window_positions(t)]
    near, heading = BS.nonstandard_positional(t, tpos)
    assert near >= 1 and heading >= 1
    # summer-program times (no "schedule" word needed — near-times alone fires)
    t2 = "Summer School runs 8:00 AM to 12:00 PM daily in June."
    near2, _ = BS.nonstandard_positional(t2, [off for off, _ in BS.in_window_positions(t2)])
    assert near2 >= 1


def test_nonstandard_positional_ignores_policy_prose_far_from_times():
    # the measured false-claim driver: bare "inclement weather" POLICY prose nowhere near the schedule
    policy = "In case of inclement weather, please monitor local news for closure information. " * 3
    sched = "\n" + ("x" * 300) + "\nSchool Hours: 8:00 AM - 3:00 PM"
    t = policy + sched
    tpos = [off for off, _ in BS.in_window_positions(t)]
    near, heading = BS.nonstandard_positional(t, tpos)
    assert near == 0 and heading == 0


def test_lf_nonstandard_day_two_strengths():
    from infrastructure.acquisition.stage5_filter import detectors as DET
    strong = DET.lf_nonstandard_day(_sig(nonstandard_near_times=1), DET.DEFAULT_DETECTOR_PARAMS)
    assert strong.strength == "strong" and strong.confidence == 0.7
    soft = DET.lf_nonstandard_day(_sig(nonstandard_day=True), DET.DEFAULT_DETECTOR_PARAMS)
    assert soft.strength == "soft" and soft.confidence == 0.45
    assert DET.lf_nonstandard_day(_sig(), DET.DEFAULT_DETECTOR_PARAMS) is None


def _table_sig(**over):
    # a lone schedule TABLE (no footer/heading hours, no explicit minutes) — the #528/#530 lone-table shape
    return _sig(table_time_density=6, table_period_rows=4, has_table=True, n_times=6,
                n_times_in_window=6, **over)


def test_lone_table_with_strong_wrong_day_routes_to_review():
    # DASD: "Early Dismissal Bell Schedule" as a lone table -> the table's times ARE the irregular day's
    out = COMB.score_record(_table_sig(nonstandard_heading=1, nonstandard_day=True))
    assert out["decision"] == "review" and out["tier"] == "B"


def test_lone_table_with_soft_wrong_day_mention_still_sends():
    # #60/#528 held: a real schedule table + a bare weather-policy MENTION elsewhere must still send
    out = COMB.score_record(_table_sig(nonstandard_day=True))
    assert out["decision"] == "send" and out["tier"] == "A"


def test_strong_structural_beats_strong_wrong_day():
    # an intentional hours block still sends (structure beats noise — the combiner's core rule)
    out = COMB.score_record(_sig(instructional_time=True, nonstandard_near_times=2))
    assert out["decision"] == "send" and out["tier"] == "A"


def test_wrong_day_only_evidence_is_review_not_suppress():
    # positional wrong-day evidence with no target detector: a genuine schedule of the wrong day ->
    # review (C), never a confident suppress
    out = COMB.score_record(_sig(n_times_in_window=1, nonstandard_near_times=1))
    assert out["decision"] == "review" and out["tier"] == "C"


def test_regular_day_language_guard_downgrades_strong_to_soft():
    # rule S3 (measured): a page that declares its regular day is a regular page listing variants —
    # positional wrong-day evidence downgrades to a mention, so a real bell table still sends
    from infrastructure.acquisition.stage5_filter import detectors as DET
    v = DET.lf_nonstandard_day(_sig(nonstandard_heading=1, regular_day_language=True), DET.DEFAULT_DETECTOR_PARAMS)
    assert v.strength == "soft"
    out = COMB.score_record(_table_sig(nonstandard_heading=1, regular_day_language=True))
    assert out["decision"] == "send" and out["tier"] == "A"


# ---- PR #538 review fixes: precedence pins, regex hygiene, vocabulary invariants, table basis ----
def test_no_times_suppress_floor_outranks_wrong_day_heading():
    """PR #538 review: a wrong-day HEADING with zero in-window times anywhere (nonstandard_heading needs
    no times) is a page with nothing extractable — the measured suppress floor wins over wrong-day-only
    review. This precedence is deliberate, not an elif-ordering accident; the one-hop-away case is #517."""
    out = COMB.score_record(_sig(nonstandard_heading=1))
    assert out["decision"] == "suppress" and out["tier"] == "D"


def test_nonstandard_sched_re_is_word_bounded():
    """PR #538 review: bare 'schedule'/'bell' substring-matched inside 'unscheduled'/'Bellevue'."""
    assert not BS.NONSTANDARD_SCHED_RE.search("unscheduled closure")
    assert not BS.NONSTANDARD_SCHED_RE.search("Bellevue Elementary")
    assert not BS.NONSTANDARD_SCHED_RE.search("rescheduled event")
    assert BS.NONSTANDARD_SCHED_RE.search("Bell Schedule")
    assert BS.NONSTANDARD_SCHED_RE.search("schedules for the week")
    assert BS.NONSTANDARD_SCHED_RE.search("hours of operation")


def test_nonstandard_term_re_covers_legacy_kw():
    """PR #538 review: the legacy anywhere-in-text NONSTANDARD_DAY_KW and the positional
    NONSTANDARD_TERM_RE are two vocabularies for one class — pin the subset invariant so tuning the
    class regex can never silently strand a legacy term."""
    for kw in BS.NONSTANDARD_DAY_KW:
        assert BS.NONSTANDARD_TERM_RE.search(kw), f"legacy term not covered by NONSTANDARD_TERM_RE: {kw!r}"


def test_generic_terms_require_event_qualifier():
    """PR #538 review: bare 'registration'/'substitute' matched ordinary school-site content (course
    registration forms, substitute-teacher hiring). They now fire only in event-time/schedule phrasing."""
    for benign in ("online registration form", "register here", "substitute teacher application",
                   "apply to be a substitute", "Registration Hours: 8:00 AM"):
        assert not BS.NONSTANDARD_TERM_RE.search(benign), f"should not match: {benign!r}"
    for real in ("school registration times", "fall registration", "kindergarten registration",
                 "registration day", "substitute schedule", "substitute bell schedule"):
        assert BS.NONSTANDARD_TERM_RE.search(real), f"should match: {real!r}"


def test_regular_guard_covers_traditional_and_standard_phrasings():
    """PR #538 review: 'Traditional Schedule' / 'Standard Day' sites slipped the S3 guard."""
    for phrase in ("Traditional Schedule", "traditional bell schedule", "Standard Bell Schedule",
                   "standard school day", "Regular Schedule", "daily schedule"):
        assert BS.NONSTANDARD_REGULAR_RE.search(phrase), f"guard must cover: {phrase!r}"


def test_nonstandard_positional_reads_table_reps_too(tmp_path):
    """PR #538 review: the table evidence lf_time_table scores can come from a camelot/pdfplumber rep
    that is NOT best_text — the wrong-day scan must cover it, or the DASD shape (an 'Early Dismissal
    Bell Schedule' TABLE whose surrounding prose never says so) slips the STRONG vote."""
    prose = ("Welcome to our school. Doors open at 7:45 AM and classes begin at 8:00 AM. "
             "Dismissal is at 3:00 PM. " * 4)
    (tmp_path / "page.txt").write_text(prose)
    tbl = ("Early Dismissal Bell Schedule\n---\n"
           "Period 1 | 8:00 AM | 8:25 AM\nPeriod 2 | 8:30 AM | 8:55 AM\nPeriod 3 | 9:00 AM | 9:25 AM")
    (tmp_path / "camelot.txt").write_text(tbl)
    texts = [{"usable": True, "text_file": "page.txt", "n_chars": len(prose), "n_times": 6},
             {"usable": True, "text_file": "camelot.txt", "source": "camelot_hybrid",
              "n_chars": len(tbl), "n_times": 6}]
    sig, _, _ = BS.compute_signals(tmp_path, texts, [], {}, main_text=None)
    assert sig["nonstandard_heading"] >= 1, "the table rep's wrong-day title must be seen"


def test_regular_day_guard_only_computed_with_positional_evidence(tmp_path):
    """PR #538 review (efficiency + semantics): regular_day_language is consulted only to guard
    positional evidence — with none, it reads False (not-applicable), and the guard regex isn't the
    thing keeping the record alive."""
    t = "Our regular schedule is great. School Hours: 8:00 AM - 3:00 PM. " * 3
    (tmp_path / "page.txt").write_text(t)
    texts = [{"usable": True, "text_file": "page.txt", "n_chars": len(t), "n_times": 2}]
    sig, _, _ = BS.compute_signals(tmp_path, texts, [], {}, main_text=None)
    assert not (sig["nonstandard_near_times"] or sig["nonstandard_heading"])
    assert sig["regular_day_language"] is False


def test_sort_score_symmetric_across_undermine_kinds():
    """PR #538 review: two lone tables, one undermined by lf_news_feed (hard_neg) and one by the STRONG
    lf_nonstandard_day (wrong_day_strong), both confidence 0.7 -> identical sort_score. The wrong-day
    vote rides nconf like every other hard-undermining negative."""
    table = {"name": "lf_time_table", "polarity": "target", "strength": "strong",
             "confidence": 0.85, "reason": "t", "category": "school_bell_table"}
    feed = {"name": "lf_news_feed", "polarity": "negative", "strength": "strong",
            "confidence": 0.7, "reason": "f", "category": "embedded_feed"}
    wrong = {"name": "lf_nonstandard_day", "polarity": "negative", "strength": "strong",
             "confidence": 0.7, "reason": "w", "category": "other_schedule"}
    a, b = COMB.combine([table, feed]), COMB.combine([table, wrong])
    assert a["decision"] == b["decision"] == "review" and a["tier"] == b["tier"] == "B"
    assert a["sort_score"] == b["sort_score"]


def test_variant_dominated_page_overrides_regular_guard():
    """PR #538 review (measured): >= wrong_day_dominance_min variant-schedule titles = a
    variant-dominated page (DASD/MUSD shape) — one stray 'regular hours' phrase must not mute it."""
    from infrastructure.acquisition.stage5_filter import detectors as DET
    muted = DET.lf_nonstandard_day(_sig(nonstandard_heading=2, regular_day_language=True),
                                   DET.DEFAULT_DETECTOR_PARAMS)
    assert muted.strength == "soft"
    dominated = DET.lf_nonstandard_day(_sig(nonstandard_heading=4, regular_day_language=True),
                                       DET.DEFAULT_DETECTOR_PARAMS)
    assert dominated.strength == "strong"


# ---- #226: bounded "feed" tokens in the URL are the feed signal; feeder/feedback are not ----
def test_feed_url_matches_bounded_feed_tokens():
    # the live uncovered shapes from batch_00013 / the census labels (regression fixtures)
    for url in [
        "https://www.jefcoed.com/o/gardendalees/live_feeds/12479060",       # underscore permalink
        "https://amybiehl.sfps.info/o/abcs/live_feeds/12068602",
        "https://core-docs.s3.amazonaws.com/gallup-mckinley_county_schools_ar/live_feed_image/image/17728373/large_x.png",
        "https://tups.org/index.php?pageID=smartSiteFeed&psqFeed=true&articleID=82782328",  # camelCase query tokens
        "https://example.org/feed/",                                        # generic bounded segment
        "https://example.org/feeds/school-news",
        "https://example.org/?feed=rss2",
        "https://example.org/news-feed",
    ]:
        assert BS.feed_url(url), url


def test_feed_url_does_not_match_feeder_or_feedback():
    # "feeder" is a real K-12 term (feeder pattern/schools) and must never be penalized; "feedback" is unrelated.
    for url in [
        "https://example.org/schools/feeder-pattern",
        "https://example.org/o/hs/feeder-schools",
        "https://example.org/about/feedback",
        "https://example.org/community/coffee-with-the-principal",
    ]:
        assert not BS.feed_url(url), url


# ---- #532: the rootish-URL signal (the page-focus URL half) ----
def test_rootish_url_matches_homepage_shapes_only():
    yes = ["https://www.sfps.info/", "https://www.millard.k12.ut.us", "https://ortiz.sfps.info/?page_no=2",
           "https://www.midviewk12.org/o/mms", "https://carlosgilbert.sfps.info/o/cge/"]
    no = ["https://www.midviewk12.org/o/mms/live-feed", "https://ahl.cpsk12.org/about/schedule",
          "https://x.org/page/bell-schedules", "gt://gt_curation_x/district/file.pdf",
          "https://x.org/o/mms/article/123"]
    for u in yes:
        assert BS.rootish_url(u), u
    for u in no:
        assert not BS.rootish_url(u), u


# ---- PR #538/#539/#541 review fixes: regex tightening pins ----
def test_feed_url_matches_case_normalized_glued_tokens():
    # The camelCase alternative was exact-case ((?-i:[a-z]Feed)) and missed case-normalized variants of
    # the PR's own fixture. Now the glued-token alternative folds case like the rest of the pattern.
    for u in [
        "https://tups.org/index.php?pageID=smartsitefeed&psqfeed=true",   # lowercased proxy/CMS
        "https://tups.org/index.php?pageID=SMARTSITEFEED&psqFEED=true",   # uppercased legacy CMS
        "https://tups.org/index.php?pageID=smartSiteFeed&psqFeed=true",   # the original camelCase
    ]:
        assert BS.feed_url(u), u
    for u in ["https://example.org/schools/feeder-pattern", "https://example.org/about/feedback",
              "https://example.org/FEEDER-schools"]:
        assert not BS.feed_url(u), u


def test_nonstandard_term_separators_are_space_or_hyphen_only():
    # 'half.day' / '(?:2|two).hour' / 'back.to.school' used a bare `.` (any character); now a [- ] class.
    for hit in ["half day", "half-day", "2-hour delay", "two hour delay", "back to school", "back-to-school"]:
        assert BS.NONSTANDARD_TERM_RE.search(hit), hit
    for miss in ["halfXday", "2Xhour delay", "backXtoXschool"]:
        assert not BS.NONSTANDARD_TERM_RE.search(miss), miss


# ---- #517: the schedule_link_only shape (detection is pure signal derivation) ----
def test_schedule_link_only_fires_on_the_link_hub_shape():
    # the measured shape (78/78 target_absent on the census): schedule-intent keywords, no time content
    assert BS.schedule_link_only({"positive_kw": ["bell schedule"], "n_times_in_window": 0,
                                  "table_time_density": 0})
    assert BS.schedule_link_only({"positive_kw": ["Calendars and Bell Schedules"],
                                  "n_times_in_window": 1, "table_time_density": 0})


def test_schedule_link_only_never_fires_with_time_content():
    # zero collateral by construction: a real target HAS times / a table
    assert not BS.schedule_link_only({"positive_kw": ["bell schedule"], "n_times_in_window": 4,
                                      "table_time_density": 0})
    assert not BS.schedule_link_only({"positive_kw": ["bell schedule"], "n_times_in_window": 0,
                                      "table_time_density": 6})
    assert not BS.schedule_link_only({"positive_kw": ["dress code"], "n_times_in_window": 0,
                                      "table_time_density": 0})   # no schedule intent
