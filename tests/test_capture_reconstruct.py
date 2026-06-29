"""Stage 3 manifest RECOVERY (REQ-110 follow-up): rebuild captures.json from on-disk per-URL folders
for a district orphaned by a mid-run SIGKILL (folders on disk, no manifest). Pure-filesystem — no DB."""
import json

import pytest

from infrastructure.acquisition.stage3_capture import capture_stage3 as C3


def _district(tmp_path, candidates):
    d = tmp_path / "1716950_x"
    (d / "captures").mkdir(parents=True)
    (d / "candidates.json").write_text(json.dumps({"candidates": candidates}))
    return {"district_id": "1716950", "name": "X", "state": "IL", "dir": d}


def _folder(district, url, files: dict):
    fdir = district["dir"] / "captures" / C3._url_hash(url)
    fdir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (fdir / name).write_text(content)
    return fdir


def test_reconstruct_marks_recovered_ok_and_missing_not_recovered(tmp_path):
    cands = [
        {"url": "https://x.org/html-page/", "tools": ["bd"]},   # full HTML capture
        {"url": "https://x.org/doc.pdf", "tools": []},           # direct PDF
        {"url": "https://x.org/empty/", "tools": []},            # folder mkdir'd but in-flight at kill
        {"url": "https://x.org/never-started/", "tools": []},    # no folder at all
    ]
    dist = _district(tmp_path, cands)
    _folder(dist, "https://x.org/html-page/", {"page.txt": "8:00", "page.png": "x", "page.pdf": "x", "page.main.txt": "8:00"})
    _folder(dist, "https://x.org/doc.pdf", {"original.pdf": "%PDF"})
    _folder(dist, "https://x.org/empty/", {})   # empty shell

    recs = C3.reconstruct_captures(dist)
    by_url = {r["url"]: r for r in recs}
    assert len(recs) == 4                                          # completeness: every candidate appears
    assert by_url["https://x.org/html-page/"]["ok"] and by_url["https://x.org/html-page/"]["kind"] == "html"
    assert by_url["https://x.org/html-page/"]["files"] == {"txt": "page.txt", "png": "page.png", "pdf": "page.pdf"}
    assert by_url["https://x.org/html-page/"]["segmented"] is True
    assert by_url["https://x.org/doc.pdf"]["ok"] and by_url["https://x.org/doc.pdf"]["files"] == {"bin": "original.pdf"}
    assert by_url["https://x.org/empty/"]["ok"] is False and "not_recovered" in by_url["https://x.org/empty/"]["err"]
    assert by_url["https://x.org/never-started/"]["ok"] is False
    # outcome over the rebuilt manifest = captured_partial (2 ok, 2 not)
    assert C3.compute_outcome(recs)[0] == "captured_partial"


def test_reconstruct_refuses_to_overwrite_existing_manifest(tmp_path):
    dist = _district(tmp_path, [{"url": "https://x.org/a", "tools": []}])
    (dist["dir"] / "captures.json").write_text("[]")
    with pytest.raises(SystemExit):
        C3.reconstruct_captures(dist)


def test_manual_capture_record_copies_file_and_builds_record(tmp_path):
    dist = _district(tmp_path, [])
    src = tmp_path / "handbook.pdf"
    src.write_text("%PDF-1.7 ...")
    url = "https://x.org/district-parent-student-information-handbook/"
    rec = C3.manual_capture_record(dist, url=url, src_file=src, found_on=url)
    assert rec["source"] == "manual" and rec["kind"] == "pdf" and rec["ok"]
    assert rec["files"] == {"bin": "original.pdf"}
    dest = dist["dir"] / "captures" / C3._url_hash(url) / "original.pdf"
    assert dest.exists() and dest.read_text().startswith("%PDF")
