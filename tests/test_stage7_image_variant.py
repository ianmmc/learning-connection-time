"""Stage 7 image_handoff_variant (REQ-117): the text->vision probe rewrite. No network/DB — a temp
capture tree + monkeypatched council/district-dir lookups. Covers the PNG-only picker (raster_p-1.png
preferred, else any *.png, never .webp/.jpg/.jpeg) and the distinct handoff_hash (the resume-collision
fix: sharing a hash with the source text handoff made run_council_streaming skip every image-pass
district, since resume keys off handoff_hash and the text run had already persisted all of them)."""
from infrastructure.acquisition.process_governance import stage7_run as R7


DOC = {
    "handoff_hash": "abc123",
    "councils": {"low-cost-text": {"voters": ["m1", "m2"], "judge": "j1"}},
    "districts": [
        {"district_id": "D1", "name": "Has Raster", "records": [
            {"rec_key": "D1:aa", "decision": "send",
             "reps": [{"file": "pdftotext.txt", "kind": "text", "councils": ["low-cost-text"]}]}]},
        {"district_id": "D2", "name": "Native PNG Only", "records": [
            {"rec_key": "D2:bb", "decision": "send",
             "reps": [{"file": "pdftotext.txt", "kind": "text", "councils": ["low-cost-text"]}]}]},
        {"district_id": "D3", "name": "Webp Only", "records": [
            {"rec_key": "D3:cc", "decision": "send",
             "reps": [{"file": "pdftotext.txt", "kind": "text", "councils": ["low-cost-text"]}]}]},
    ],
}


def _fake_councils():
    return {"image": {"id": "image", "voters": ["v1", "v2"], "judge": "j2"}}


def _make_tree(tmp_path):
    # D1: has raster_p-1.png (preferred) alongside another png
    (tmp_path / "D1" / "captures" / "aa").mkdir(parents=True)
    (tmp_path / "D1" / "captures" / "aa" / "raster_p-1.png").write_bytes(b"x")
    (tmp_path / "D1" / "captures" / "aa" / "other.png").write_bytes(b"x")
    # D2: no raster_p, but a native original.png
    (tmp_path / "D2" / "captures" / "bb").mkdir(parents=True)
    (tmp_path / "D2" / "captures" / "bb" / "original.png").write_bytes(b"x")
    # D3: only webp — must be excluded, never converted
    (tmp_path / "D3" / "captures" / "cc").mkdir(parents=True)
    (tmp_path / "D3" / "captures" / "cc" / "original.webp").write_bytes(b"x")
    return {"D1": "D1", "D2": "D2", "D3": "D3"}


def test_prefers_raster_p_falls_back_to_any_png_excludes_webp(tmp_path, monkeypatch):
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path)
    monkeypatch.setattr(R7, "district_dirs", lambda ids: _make_tree(tmp_path))
    monkeypatch.setattr(R7.C6, "load_configs", _fake_councils)

    v = R7.image_handoff_variant(DOC)
    kept = {d["district_id"]: d for d in v["districts"]}

    assert set(kept) == {"D1", "D2"}                       # D3 (webp-only) dropped entirely
    assert kept["D1"]["records"][0]["reps"][0]["file"] == "raster_p-1.png"   # preferred
    assert kept["D2"]["records"][0]["reps"][0]["file"] == "original.png"    # fallback
    for d in kept.values():
        rep = d["records"][0]["reps"][0]
        assert rep["kind"] == "image" and rep["councils"] == ["image"]


def test_variant_gets_a_distinct_handoff_hash(tmp_path, monkeypatch):
    """The resume-collision fix: sharing the source hash would make a text run's already-persisted
    extraction rows shadow the image pass and skip every district."""
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path)
    monkeypatch.setattr(R7, "district_dirs", lambda ids: _make_tree(tmp_path))
    monkeypatch.setattr(R7.C6, "load_configs", _fake_councils)

    v = R7.image_handoff_variant(DOC)
    assert v["handoff_hash"] == "abc123-image"
    assert v["handoff_hash"] != DOC["handoff_hash"]
    assert v["run_kind"] == "probe"          # #148: flagged a probe, keeping it out of the console
    assert "run_kind" not in DOC             # the source (production) doc is untouched


def test_custom_council_id_reflected_in_hash_and_routing(tmp_path, monkeypatch):
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path)
    monkeypatch.setattr(R7, "district_dirs", lambda ids: _make_tree(tmp_path))
    monkeypatch.setattr(R7.C6, "load_configs", lambda: {"vision-x": {"id": "vision-x"}})

    v = R7.image_handoff_variant(DOC, council_id="vision-x")
    assert v["handoff_hash"] == "abc123-vision-x"
    # #148: a NON-'-image' probe suffix — the exact case the old `NOT LIKE '%-image'` filter missed.
    # run_kind='probe' catches it regardless of the suffix, so it can't shadow production in the console.
    assert v["run_kind"] == "probe"
    d1 = next(d for d in v["districts"] if d["district_id"] == "D1")
    assert d1["records"][0]["reps"][0]["councils"] == ["vision-x"]
