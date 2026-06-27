"""REQ-094 — the Stage 5→6 release generator: the deterministic record→representation descent that
emits one traceable `filtered.json` per district.

The descent (best_send / decide / build_doc) is PURE — unit-tested with synthetic records, no DB.
The DB read→build→write path (generate) is exercised against the real governance Postgres via the
gov_session fixture: a synthetic district/record/label/representation is inserted on the session
(test-specific ids), generate() writes filtered.json to a tmp dir, and the session is ROLLED BACK
at teardown so the live data is untouched.
"""
import json

from sqlalchemy import text

from infrastructure.acquisition.stage5_filter import release as R
from infrastructure.acquisition.stage5_filter import build_signals as BS


def _rec(label=None, tier="A", reps=None, signals=None, flags=None, **over):
    base = {"rec_key": "d:1", "url": "http://x/a", "tier": tier, "category": "x",
            "label": label, "signals": signals or {}, "flags": flags or [],
            "is_emergent": 0, "intended_schools": [], "reps": reps or []}
    base.update(over)
    return base


def _text_rep(filename, n_times=0, n_chars=100, usable=1, source="pdftotext"):
    return {"source": source, "filename": filename, "file_kind": "text",
            "n_chars": n_chars, "n_times": n_times, "usable": usable}


# ----------------------------- best_send (one best representation) -----------------------------
def test_best_send_picks_densest_usable_text():
    reps = [_text_rep("a.txt", n_times=1), _text_rep("b.txt", n_times=5), _text_rep("c.txt", n_times=2)]
    assert R.best_send(reps, {}, []) == [{"file": "b.txt", "kind": "text"}]


def test_best_send_image_when_visual_text_gap():
    reps = [_text_rep("a.txt", n_times=3),
            {"source": "capture:png", "filename": "page.png", "file_kind": "image"}]
    assert R.best_send(reps, {"visual_text_gap": True}, []) == [{"file": "page.png", "kind": "image"}]


def test_best_send_image_when_human_flags_target_image_only():
    reps = [_text_rep("a.txt", n_times=9),
            {"source": "raster", "filename": "raster_p1.png", "file_kind": "image"}]
    assert R.best_send(reps, {}, ["target_image_only"]) == [{"file": "raster_p1.png", "kind": "image"}]


def test_best_send_handbook_sends_pdf_with_harvest_pages():
    reps = [_text_rep("a.txt", n_times=4),
            {"source": "capture:pdf", "filename": "page.pdf", "file_kind": "pdf"}]
    sig = {"is_handbook": True, "harvest_pages": [2, 3]}
    assert R.best_send(reps, sig, []) == [{"file": "page.pdf", "kind": "pdf", "pages": [2, 3]}]


def test_best_send_empty_when_no_reps():
    assert R.best_send([], {}, []) == []


# ----------------------------- decide (the release rule) -----------------------------
def test_decide_target_label_sends():
    rec = _rec(label="school_bell_schedule", reps=[_text_rep("page.txt", n_times=4)])
    d = R.decide(rec)
    assert d["decision"] == "send"
    assert d["reason"] == "target-label:school_bell_schedule"
    assert d["send"] == [{"file": "page.txt", "kind": "text"}]


def test_decide_labeled_non_target_rejects():
    d = R.decide(_rec(label="board_schedule", reps=[_text_rep("page.txt", n_times=4)]))
    assert d["decision"] == "reject" and d["reason"] == "non-target:board_schedule" and d["send"] == []


def test_decide_target_with_no_usable_rep_flags_it():
    d = R.decide(_rec(label="school_bell_schedule", reps=[]))
    assert d["decision"] == "send" and d["reason"].endswith(";no-usable-rep") and d["send"] == []


def test_decide_unlabeled_tier_d_rejects_unlabeled_recall_bias_sends():
    assert R.decide(_rec(label=None, tier="D"))["reason"] == "auto:tier-D"
    keep = R.decide(_rec(label=None, tier="A", reps=[_text_rep("p.txt", n_times=2)]))
    assert keep["decision"] == "send" and keep["reason"] == "auto:recall-bias"


# ----------------------------- build_doc (traceable artifact) -----------------------------
def test_build_doc_is_traceable_with_completeness_and_header():
    district = {"district_id": "d", "district_dir": "d_dir", "labeled_topology": "per_school",
                "nces_denominator": {"total": 3, "by_level": {}}}
    records = [_rec(rec_key="d:1", label="school_bell_schedule", reps=[_text_rep("p1.txt", n_times=4)]),
               _rec(rec_key="d:2", label="board_schedule", reps=[_text_rep("p2.txt", n_times=4)]),
               _rec(rec_key="d:3", label="none")]
    doc = R.build_doc(district, records, {"config": "c", "labels": "l", "data": "x"})
    assert doc["completeness"] == {"n_canonical": 3, "n_send": 1, "n_reject": 2}
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
        "tier": "A", "sort_score": 50.0, "category_hypothesis": "school_bell_schedule",
        "signals_json": json.dumps({"n_times": 4}), "intended_schools_json": json.dumps(["A Elem"]),
        "candidate_tools_json": "[]", "is_emergent": 0})
    sess.execute(text(
        "INSERT INTO label (rec_key, primary_label, flags_json, status) "
        "VALUES (:rk, 'school_bell_schedule', '[]', 'labeled')"), {"rk": f"{did}:h1"})
    sess.execute(BS.INSERT_REP, {"rec_key": f"{did}:h1", "source": "pdftotext", "filename": "page.txt",
                                 "file_kind": "text", "n_chars": 200, "n_times": 4, "usable": 1})


def test_generate_writes_traceable_filtered_json(gov_session, tmp_path):
    did = "RELTEST"
    (tmp_path / "reltest_dir").mkdir()
    _seed_district(gov_session, did, "reltest_dir")

    summary = R.generate(gov_session, district_id=did, root=tmp_path)
    assert len(summary) == 1 and summary[0]["n_send"] == 1

    doc = json.loads((tmp_path / "reltest_dir" / "filtered.json").read_text())
    assert doc["district_id"] == did and doc["topology"] == "per_school"
    assert doc["completeness"] == {"n_canonical": 1, "n_send": 1, "n_reject": 0}
    assert set(doc["fingerprints"]) == {"config", "labels", "data"}
    rec = doc["records"][0]
    assert rec["decision"] == "send" and rec["send"] == [{"file": "page.txt", "kind": "text"}]
    assert rec["intended_schools"] == ["A Elem"]
    gov_session.rollback()
