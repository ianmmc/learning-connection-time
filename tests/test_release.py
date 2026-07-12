"""REQ-094 — the Stage 5→6 release generator: the deterministic record→representation descent that
emits one traceable `filtered.json` per district.

The descent (best_send / decide / build_doc) is PURE — unit-tested with synthetic records, no DB.
The DB read→build→write path (generate) is exercised against the real governance Postgres via the
gov_session fixture: a synthetic district/record/label/representation is inserted on the session
(test-specific ids), generate() writes filtered.json to a tmp dir, and the session is ROLLED BACK
at teardown so the live data is untouched.
"""
import json

import pytest
from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import release as R
from infrastructure.acquisition.stage5_filter import build_signals as BS


def _rec(label=None, tier="A", reps=None, signals=None, facets=None, **over):
    base = {"rec_key": "d:1", "url": "http://x/a", "tier": tier, "category": "x",
            "label": label, "signals": signals or {}, "facets": facets or {},
            "is_emergent": 0, "intended_schools": [], "reps": reps or []}
    base.update(over)
    return base


def _text_rep(filename, n_times=0, n_chars=100, usable=1, source="pdftotext"):
    return {"source": source, "filename": filename, "file_kind": "text",
            "n_chars": n_chars, "n_times": n_times, "usable": usable}


# ----------------------------- best_send (one best representation) -----------------------------
def test_best_send_picks_densest_usable_text():
    reps = [_text_rep("a.txt", n_times=1), _text_rep("b.txt", n_times=5), _text_rep("c.txt", n_times=2)]
    assert R.best_send(reps, {}, {}) == [{"file": "b.txt", "kind": "text"}]


def test_best_send_image_when_visual_text_gap():
    reps = [_text_rep("a.txt", n_times=3),
            {"source": "capture:png", "filename": "page.png", "file_kind": "image"}]
    assert R.best_send(reps, {"visual_text_gap": True}, {}) == [{"file": "page.png", "kind": "image"}]


def test_best_send_image_when_human_facets_needs_vision():
    # v2.1 (REQ-114 Axis 3): the human's needs_vision facet routes to the image rep — this replaced
    # the v2.0 target_image_only flag (flags_json is a retired, inert archive).
    reps = [_text_rep("a.txt", n_times=9),
            {"source": "raster", "filename": "raster_p1.png", "file_kind": "image"}]
    assert R.best_send(reps, {}, {"needs_vision": "yes"}) == [{"file": "raster_p1.png", "kind": "image"}]
    # tri-state: only an explicit "yes" routes; "no"/"unsure"/absent do not
    assert R.best_send(reps, {}, {"needs_vision": "no"}) == [{"file": "a.txt", "kind": "text"}]


def test_best_send_handbook_prefers_the_materialized_slice():
    # Q2.1: when the harvest_slice.txt rep exists, send THAT (a small text doc), not the whole PDF —
    # and the slice is never chosen as a plain "densest text" for a non-handbook.
    reps = [_text_rep("harvest_slice.txt", n_times=30, n_chars=900, source="harvest_slice"),
            _text_rep("a.txt", n_times=4),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf"}]
    sig = {"is_handbook": True, "harvest_pages": [4, 9]}
    assert R.best_send(reps, sig, {}) == [{"file": "harvest_slice.txt", "kind": "text", "pages": [4, 9]}]


def test_best_send_handbook_falls_back_to_pdf_when_no_slice():
    reps = [_text_rep("a.txt", n_times=4),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf"}]
    sig = {"is_handbook": True, "harvest_pages": [2, 3]}
    assert R.best_send(reps, sig, {}) == [{"file": "page.pdf", "kind": "pdf", "pages": [2, 3]}]


def test_best_send_handbook_slice_loses_to_a_denser_general_text_rep():
    # #230 (Redbank Valley): the slice used to be sent UNCONDITIONALLY — round 1 dispatched
    # harvest_slice.txt (n_times=26) while pdftotext.txt (n_times=90) sat unsent as an alternate,
    # wasting a paid round before the 7->6 retry self-corrected. Yield now decides. The rep set
    # INCLUDES the pdf rep every real handbook record carries — the review of this fix caught the
    # pdf+pages fallback intercepting the fall-through and sending the whole PDF instead.
    reps = [_text_rep("harvest_slice.txt", n_times=26, source="harvest_slice"),
            _text_rep("pdftotext.txt", n_times=90),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf"}]
    sig = {"is_handbook": True, "harvest_pages": [12]}
    assert R.best_send(reps, sig, {}) == [{"file": "pdftotext.txt", "kind": "text"}]


def test_best_send_handbook_slice_wins_ties_and_zero_yield_records():
    # ties go to the slice (the purpose-built handbook rep) ...
    reps = [_text_rep("harvest_slice.txt", n_times=8, source="harvest_slice"),
            _text_rep("a.txt", n_times=8)]
    sig = {"is_handbook": True, "harvest_pages": [3]}
    assert R.best_send(reps, sig, {}) == [{"file": "harvest_slice.txt", "kind": "text", "pages": [3]}]
    # ... and a slice-only record (no usable general text) still sends the slice, even at 0 yield
    only_slice = [_text_rep("harvest_slice.txt", n_times=0, source="harvest_slice")]
    assert R.best_send(only_slice, sig, {}) == [{"file": "harvest_slice.txt", "kind": "text", "pages": [3]}]


def test_best_send_empty_when_no_reps():
    assert R.best_send([], {}, {}) == []


# ----------------------------- decide (the release rule) -----------------------------
def test_decide_target_label_sends():
    rec = _rec(label="school_bell_table", reps=[_text_rep("page.txt", n_times=4)])
    d = R.decide(rec)
    assert d["decision"] == "send"
    assert d["reason"] == "target-label:school_bell_table"
    assert d["send"] == [{"file": "page.txt", "kind": "text"}]


def test_decide_labeled_non_target_rejects():
    d = R.decide(_rec(label="board_schedule", reps=[_text_rep("page.txt", n_times=4)]))
    assert d["decision"] == "reject" and d["reason"] == "non-target:board_schedule" and d["send"] == []


def test_decide_target_with_no_usable_rep_flags_it():
    d = R.decide(_rec(label="school_bell_table", reps=[]))
    assert d["decision"] == "send" and d["reason"].endswith(";no-usable-rep") and d["send"] == []


def test_decide_unlabeled_is_tier_gated():
    # only tier A auto-dispatches; B/C are HELD pending a gate@5 label; D is a confident reject
    a = R.decide(_rec(label=None, tier="A", reps=[_text_rep("p.txt", n_times=2)]))
    assert a["decision"] == "send" and a["reason"] == "auto:tier-A"
    for t in ("B", "C"):
        h = R.decide(_rec(label=None, tier=t, reps=[_text_rep("p.txt", n_times=2)]))
        assert h["decision"] == "hold" and h["reason"] == f"unlabeled-tier-{t}" and h["send"] == []
    d = R.decide(_rec(label=None, tier="D"))
    assert d["decision"] == "reject" and d["reason"] == "auto:tier-D"


def test_decide_unlabeled_tier_a_with_no_usable_rep_rejects():
    d = R.decide(_rec(label=None, tier="A", reps=[]))
    assert d["decision"] == "reject" and "no-usable-rep" in d["reason"]


# ----------------------------- alternates (gate@6 representation override) -----------------------------
def test_alternates_excludes_winner_and_lists_other_usable():
    reps = [_text_rep("winner.txt", n_times=9), _text_rep("other.txt", n_times=2),
            _text_rep("garbled.txt", usable=0),  # unusable text excluded
            {"source": "capture:png", "filename": "page.png", "file_kind": "image"}]
    alts = R.alternates(reps, exclude={"winner.txt"})
    files = {a["file"] for a in alts}
    assert files == {"other.txt", "page.png"}          # winner + unusable excluded; image kept


def test_decide_target_carries_alternates_not_the_winner():
    reps = [_text_rep("winner.txt", n_times=9), _text_rep("alt.txt", n_times=3),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf"}]
    d = R.decide(_rec(label="school_bell_table", reps=reps))
    assert d["send"] == [{"file": "winner.txt", "kind": "text"}]
    alt_files = {a["file"] for a in d["alternates"]}
    assert alt_files == {"alt.txt", "page.pdf"}        # the swappable options, winner excluded


def test_decide_reject_has_no_alternates():
    d = R.decide(_rec(label="board_schedule", reps=[_text_rep("p.txt", n_times=4)]))
    assert d["alternates"] == []


def test_alternates_excludes_quarantined_chrome_segments():
    reps = [_text_rep("winner.txt", n_times=9),
            _text_rep("page.main.txt", n_times=4, source="segment:main"),    # de-chromed body: a candidate
            _text_rep("page.header.txt", n_times=1, source="segment:header"),  # chrome: excluded
            _text_rep("page.footer.txt", n_times=1, source="segment:footer"),  # chrome: excluded
            _text_rep("page.nav.txt", n_times=1, source="segment:nav")]        # chrome: excluded
    alts = {a["file"] for a in R.alternates(reps, exclude={"winner.txt"})}
    assert alts == {"page.main.txt"}


# ----------------------------- build_doc (traceable artifact) -----------------------------
def test_build_doc_is_traceable_with_completeness_and_header():
    district = {"district_id": "d", "district_dir": "d_dir", "labeled_topology": "per_school",
                "nces_denominator": {"total": 3, "by_level": {}}}
    records = [_rec(rec_key="d:1", label="school_bell_table", reps=[_text_rep("p1.txt", n_times=4)]),
               _rec(rec_key="d:2", label="board_schedule", reps=[_text_rep("p2.txt", n_times=4)]),
               _rec(rec_key="d:3", label="none")]
    doc = R.build_doc(district, records, {"config": "c", "labels": "l", "data": "x"})
    assert doc["completeness"] == {"n_canonical": 3, "n_send": 1, "n_reject": 2, "n_hold": 0}
    assert doc["topology"] == "per_school" and doc["label"] == "gross_bell_to_bell"
    assert doc["fingerprints"] == {"config": "c", "labels": "l", "data": "x"}
    # every canonical record present with a decision (traceable), only the target carries send[]
    by_key = {r["rec_key"]: r for r in doc["records"]}
    assert len(by_key) == 3
    assert by_key["d:1"]["decision"] == "send" and by_key["d:1"]["send"]
    assert by_key["d:2"]["decision"] == "reject" and by_key["d:2"]["reason"] == "non-target:board_schedule"
    assert by_key["d:3"]["decision"] == "reject"


# ----------------------------- generate (DB → filtered.json), rolled back -----------------------------
def _seed_district(sess, did, district_dir):
    sess.execute(text(
        "INSERT INTO district (district_id, name, district_dir, labeled_topology, nces_school_count, n_records) "
        "VALUES (:d, 'Test', :dir, 'per_school', 3, 1)"), {"d": did, "dir": district_dir})
    sess.execute(BS.INSERT_RECORD, {
        "rec_key": f"{did}:h1", "district_id": did, "district_dir": district_dir, "url": "http://x/a",
        "hash": "h1", "kind": "html", "final_url": None, "content_hash": "ch1", "duplicate_of": None,
        "tier": "A", "sort_score": 50.0, "category_hypothesis": "school_bell_table",
        "signals_json": json.dumps({"n_times": 4}), "intended_schools_json": json.dumps(["A Elem"]),
        "candidate_tools_json": "[]", "is_emergent": 0})
    sess.execute(text(
        "INSERT INTO label (rec_key, primary_label, facets_json, status) "
        "VALUES (:rk, 'school_bell_table', '{}', 'labeled')"), {"rk": f"{did}:h1"})
    sess.execute(BS.INSERT_REP, {"rec_key": f"{did}:h1", "source": "pdftotext", "filename": "page.txt",
                                 "file_kind": "text", "n_chars": 200, "n_times": 4, "usable": 1})


# #201: this test seeds the SIGNAL tables (district/record/representation) which gov_session does NOT
# bootstrap — it needs a pre-populated DB, so it's integration-only (run locally), NOT govdb (a fresh CI
# container lacks those tables). The other 16 tests in this file are pure release.decide logic (DB-free).
@pytest.mark.integration
def test_generate_writes_traceable_filtered_json(gov_session, tmp_path):
    did = "RELTEST"
    (tmp_path / "reltest_dir").mkdir()
    _seed_district(gov_session, did, "reltest_dir")

    summary = R.generate(gov_session, district_id=did, root=tmp_path)
    assert len(summary) == 1 and summary[0]["n_send"] == 1

    doc = json.loads((tmp_path / "reltest_dir" / "filtered.json").read_text())
    assert doc["district_id"] == did and doc["topology"] == "per_school"
    assert doc["completeness"] == {"n_canonical": 1, "n_send": 1, "n_reject": 0, "n_hold": 0}
    assert set(doc["fingerprints"]) == {"config", "labels", "data"}
    rec = doc["records"][0]
    assert rec["decision"] == "send" and rec["send"] == [{"file": "page.txt", "kind": "text"}]
    assert rec["intended_schools"] == ["A Elem"]
    gov_session.rollback()


def test_handbook_yield_rule_matches_rank_alternates_ordering():
    """#240 review: best_send's slice-vs-text yield comparison and the retry loop's rank_alternates
    are two encodings of ONE rule (yield-bearing text by n_times first). The two layers can't import
    each other (import-linter siblings), so THIS cross-layer test is the drift guard: if the
    ranking rule ever changes on one side, this fails and the other side gets re-aligned."""
    from infrastructure.acquisition.stage7_extract.requests import rank_alternates
    reps = [_text_rep("harvest_slice.txt", n_times=26, source="harvest_slice"),
            _text_rep("pdftotext.txt", n_times=90),
            _text_rep("page.txt", n_times=4)]
    sig = {"is_handbook": True, "harvest_pages": [12]}
    sent = R.best_send(reps, sig, {})[0]["file"]
    alts = [{"kind": "text", "n_times": r["n_times"], "file": r["filename"]} for r in reps]
    assert sent == rank_alternates(alts)[0]["file"], \
        "Stage 5's initial pick disagrees with the retry loop's yield ranking"
