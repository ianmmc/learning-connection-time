"""Council Lab judge-replay — the PURE reconstruction helpers (#80/#82). The paid replay itself is a
CLI experiment; here we lock the receipt-reading logic that feeds it: voter facts are reconstructed
from the recorded VOTER calls only (never the judge), so a replay reuses exactly what consensus saw."""
from infrastructure.acquisition.process_governance import council_lab as CL


def _rep(judged=False):
    return {
        "rec_key": "D1:abc", "file": "raster_p-1.png", "kind": "image", "judged": judged,
        "calls": [
            {"model": "google/gemini-2.5-flash", "role": "voter",
             "facts": [{"school_name": "A", "start_time": "08:00", "end_time": "14:00"}]},
            {"model": "mistralai/mistral-large-2512", "role": "voter",
             "facts": [{"school_name": "A", "start_time": "08:00", "end_time": "15:00"}]},
            # the dead judge call is present in the receipt but must NOT feed reconstruction
            {"model": "deepseek/deepseek-v3.2", "role": "judge", "ok": False, "facts": []},
        ],
    }


def test_voter_rows_excludes_the_judge():
    rows = CL._voter_rows(_rep())
    assert set(rows) == {"google/gemini-2.5-flash", "mistralai/mistral-large-2512"}
    assert "deepseek/deepseek-v3.2" not in rows          # the judge call is never a voter input
    assert len(rows["google/gemini-2.5-flash"]) == 1


def test_voter_rows_handles_missing_facts():
    rep = {"calls": [{"model": "m1", "role": "voter"}]}   # a voter call with no facts key
    assert CL._voter_rows(rep) == {"m1": []}


def test_tag_attaches_rep_provenance():
    facts = [{"band": "high", "school": "A", "gross": 400}]
    tagged = CL._tag(facts, _rep())
    assert tagged[0]["rec_key"] == "D1:abc" and tagged[0]["source_file"] == "raster_p-1.png"


def test_load_receipts_skips_aggregate_shape(tmp_path):
    """#141: the glob also matches write_receipt's AGGREGATE receipt (no 'district' key) — it must be
    skipped, not crash the replay with KeyError."""
    import json
    (tmp_path / "extraction_zzhash_0100270_20260703T000001Z.json").write_text(json.dumps(
        {"handoff_hash": "zzhash", "district": {"district_id": "0100270", "reps": []}}))
    (tmp_path / "extraction_zzhash_20260703T000002Z.json").write_text(json.dumps(
        {"handoff_hash": "zzhash", "districts": {}, "telemetry": {}}))     # aggregate — no 'district'
    docs = CL.load_receipts("zzhash", root=tmp_path)
    assert [d["district_id"] for d in docs] == ["0100270"]


def test_load_receipts_falls_back_when_newest_lacks_district(tmp_path):
    """#148 review: if the NEWEST receipt for a district is truncated (no 'district' payload), the
    older valid receipt must still represent the district — not silently drop it."""
    import json
    (tmp_path / "extraction_zzhash_0100270_20260703T000001Z.json").write_text(json.dumps(
        {"handoff_hash": "zzhash", "district": {"district_id": "0100270", "reps": []}}))
    (tmp_path / "extraction_zzhash_0100270_20260703T000002Z.json").write_text(json.dumps(
        {"handoff_hash": "zzhash"}))                                        # truncated newest
    docs = CL.load_receipts("zzhash", root=tmp_path)
    assert [d["district_id"] for d in docs] == ["0100270"]


def test_replay_refuses_text_only_judge_on_image_reps(tmp_path, monkeypatch):
    """#142 (the #82 shape): a CLI --judge candidate bypasses councils.validate() — the replay must
    refuse a non-vision-capable judge BEFORE any paid call when the receipts carry image reps."""
    import json
    import pytest
    from infrastructure.acquisition.process_governance import stage7_run as R7
    (tmp_path / "extraction_zzimg_0100270_20260703T000001Z.json").write_text(json.dumps(
        {"handoff_hash": "zzimg", "district": {"district_id": "0100270", "reps": [
            {"rec_key": "0100270:aa", "file": "raster_p-1.png", "kind": "image", "judged": True,
             "calls": []}]}}))
    monkeypatch.setattr(R7, "_require_key", lambda: None)
    monkeypatch.setattr(R7, "district_dirs", lambda ids: {})
    called = []
    monkeypatch.setattr(R7, "_call", lambda *a, **k: called.append(a) or None)
    with pytest.raises(ValueError, match="not vision-capable"):
        CL.replay_judge("zzimg", judge_model="deepseek/deepseek-v3.2", root=tmp_path)
    assert called == []      # refused BEFORE any paid call
