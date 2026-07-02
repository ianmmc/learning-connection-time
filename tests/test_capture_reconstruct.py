"""Stage 3 manifest RECOVERY (REQ-110 follow-up): rebuild captures.json from on-disk per-URL folders
for a district orphaned by a mid-run SIGKILL (folders on disk, no manifest). Pure-filesystem — no DB.

Also covers the two recovery-fidelity fixes: #43 (_strip_fragment must normalize like Node's
new URL() so md5 hashes find the folders Node named) and #42 (Drive-export stems map to the
live path's files{} keys, which Stage 4 actually reads)."""
import hashlib
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


# ---------------------------------------------------------------- #43: URL-hash parity with Node
# Expected values are new URL(raw).toString() with hash='' -- verified against Node 20 directly.
@pytest.mark.parametrize("raw,normalized", [
    ("HTTPS://X.Org:443/a#f", "https://x.org/a"),        # uppercase scheme+host, default port, fragment
    ("http://x.org:80/p?q=1#z", "http://x.org/p?q=1"),   # http default port dropped
    ("https://x.org", "https://x.org/"),                 # empty path -> '/'
    ("https://x.org:8080/a", "https://x.org:8080/a"),    # non-default port kept
    ("https://x.org/A/B?Q=x#frag", "https://x.org/A/B?Q=x"),  # path/query case preserved
    ("https://x.org/a b", "https://x.org/a%20b"),        # space percent-encoded
    ("https://x.org/a%20b", "https://x.org/a%20b"),      # existing %XX not double-encoded
    ("https://x.org/a/../b", "https://x.org/b"),         # dot segments removed
    ("https://x.org/café", "https://x.org/caf%C3%A9"),  # unicode path utf-8 encoded
    ("not a url#frag", "not a url"),                     # unparseable -> raw '#' split (Node catch branch)
])
def test_strip_fragment_matches_node_normalization(raw, normalized):
    assert C3._strip_fragment(raw) == normalized
    # hash parity is what actually matters for folder lookup:
    assert C3._url_hash(raw) == hashlib.md5(normalized.encode()).hexdigest()[:10]


def test_reconstruct_finds_folder_named_by_nodes_normalized_url(tmp_path):
    """Node captured 'HTTPS://X.Org:443/page#top' under md5('https://x.org/page')[:10]; the old
    raw '#'-split hashed the unnormalized URL and missed the folder (#43)."""
    cand_url = "HTTPS://X.Org:443/page#top"
    dist = _district(tmp_path, [{"url": cand_url, "tools": []}])
    node_folder = dist["dir"] / "captures" / hashlib.md5(b"https://x.org/page").hexdigest()[:10]
    node_folder.mkdir(parents=True)
    (node_folder / "page.txt").write_text("8:00")
    recs = C3.reconstruct_captures(dist)
    assert recs[0]["ok"] is True and recs[0]["files"] == {"txt": "page.txt"}


# ---------------------------------------------------------------- #42: Drive-export key mapping
def test_reconstruct_drive_auto_download_keys_bin_not_stem(tmp_path):
    """The live path writes the generic Drive download as file.<ext> keyed 'bin'; keying the
    recovered file by its raw stem ('file') made Stage 4 silently skip it (#42)."""
    url = "https://drive.google.com/file/d/abc123/view"
    dist = _district(tmp_path, [{"url": url, "tools": []}])
    _folder(dist, url, {"file.pdf": "%PDF"})
    recs = C3.reconstruct_captures(dist)
    assert recs[0]["kind"] == "drive_export"
    assert recs[0]["files"] == {"bin": "file.pdf"}


def test_reconstruct_drive_format_stems_keep_their_live_keys(tmp_path):
    url = "https://docs.google.com/document/d/abc/edit"
    dist = _district(tmp_path, [{"url": url, "tools": []}])
    _folder(dist, url, {"pdf.pdf": "%PDF", "md.md": "# schedule"})
    recs = C3.reconstruct_captures(dist)
    assert recs[0]["files"] == {"pdf": "pdf.pdf", "md": "md.md"}


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
