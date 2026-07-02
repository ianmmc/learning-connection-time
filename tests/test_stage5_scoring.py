"""REQ-093 — Stage 5 keyword knobs load from config; the instructional-time regex is MINUTES-ONLY
(hours reverted after the harness proved it net-negative — a vision problem); an instructional-time
hit rescues a record from the n==0 / neg-keyword drop (now via the V2 detectors+combiner — the V1
tier_and_category cascade was deleted, issue #56)."""
import json

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
    assert BS.INSTRUCTIONAL_RE.search("students receive 450 minutes of instruction")
    assert BS.INSTRUCTIONAL_RE.search("instructional minutes per day")
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
    sig_full, _ = BS.compute_signals(tmp_path, texts, [], {}, main_text=None)
    sig_dech, _ = BS.compute_signals(tmp_path, texts, [], {}, main_text=main)
    assert sig_full["dechromed"] is False and sig_dech["dechromed"] is True
    # chrome negatives (board/sports) drop out when we score MAIN; the real positive kw is present
    assert sig_dech["neg_total"] < sig_full["neg_total"]
    assert "bell schedule" in sig_dech["positive_kw"]


def test_dechrome_falls_back_when_main_too_thin(tmp_path):
    full = "School hours 8:00 AM to 3:00 PM bell schedule dismissal arrival every school day here."
    (tmp_path / "page.txt").write_text(full)
    texts = [{"usable": True, "text_file": "page.txt", "n_chars": len(full), "n_times": 2}]
    sig, _ = BS.compute_signals(tmp_path, texts, [], {}, main_text="too short")  # below USABLE_MIN_CHARS
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
