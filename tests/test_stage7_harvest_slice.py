"""Regression: Stage 7's resolve_content must read a page-SLICE rep (`harvest_slice.txt`,
`timebearing_slice.txt`) through the shared `build_signals.resolve_slice` resolver
(new-location-first), NOT by joining the capture dir itself. The #58 relocation moved slices OUT of
the capture dir, so the old direct-join raised FileNotFoundError on every relocated slice and
aborted a whole batch run (found live on Marshall WI 5508790 during the #122 run). A plain text rep
must still read straight from the capture dir.

#821 note: the call site no longer spells a filename test of its own — `resolve_slice` returns None
for a non-slice, so ONE function decides which files are slices and where they live. These tests
therefore patch `resolve_slice`, which IS the real seam."""
import pytest

from infrastructure.acquisition.process_governance import stage7_run as R7


REC = "5508790:6cc3deb70a"          # <district_id>:<capture-hash>
DDIR = "5508790_marshall_school_district"


@pytest.mark.parametrize("slice_file", ["harvest_slice.txt", "timebearing_slice.txt"])
def test_slice_rep_uses_resolver(tmp_path, monkeypatch, slice_file):
    """A slice rep reads the relocated file the resolver points at — never the capture dir.
    Both slice kinds resolve through the same path."""
    slice_fp = tmp_path / "relocated.txt"
    slice_fp.write_text("REGULAR DAY 8:05 AM - 3:10 PM", encoding="utf-8")

    seen = {}

    def fake_resolve(district_id, district_dir, rec_key, filename):
        seen.update(district_id=district_id, district_dir=district_dir,
                    rec_key=rec_key, filename=filename)
        return slice_fp

    monkeypatch.setattr(R7.BS, "resolve_slice", fake_resolve)
    # Point the capture dir at an EMPTY tmp tree: if resolve_content joined it (the old bug), the
    # read would FileNotFoundError. The resolver path must win instead.
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path / "captures_root")

    out = R7.resolve_content(DDIR, REC, slice_file, "text")

    assert out == "REGULAR DAY 8:05 AM - 3:10 PM"
    # called with the district_id parsed off the rec_key prefix (not the hash), and the filename
    # forwarded so the resolver can tell WHICH slice kind it is
    assert seen == {"district_id": "5508790", "district_dir": DDIR,
                    "rec_key": REC, "filename": slice_file}


def test_slice_missing_everywhere_still_raises(tmp_path, monkeypatch):
    """When neither location has the slice, fall through to the legacy path so the failure is a clear
    FileNotFoundError (not a silent empty read)."""
    monkeypatch.setattr(R7.BS, "resolve_slice", lambda *a: None)
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path / "captures_root")
    with pytest.raises(FileNotFoundError):
        R7.resolve_content(DDIR, REC, R7.BS.HARVEST_SLICE_FILE, "text")


def test_non_slice_text_rep_reads_capture_dir(tmp_path, monkeypatch):
    """A normal text rep is unaffected — it still reads straight from the capture dir. The resolver
    IS consulted now (there is no filename test at the call site any more), but it must decline a
    non-slice filename without touching the filesystem, so the capture-dir read still wins."""
    cap = tmp_path / DDIR / "captures" / "6cc3deb70a"
    cap.mkdir(parents=True)
    (cap / "page.txt").write_text("PAGE TEXT", encoding="utf-8")
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path)

    assert R7.resolve_content(DDIR, REC, "page.txt", "text") == "PAGE TEXT"


def test_resolver_declines_a_non_slice_filename_outright():
    """The contract the call site now depends on: resolve_slice returns None for anything that is
    not a known slice file, so callers need no membership test. Pure — no filesystem, no DB."""
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    assert BS.resolve_slice("5508790", DDIR, REC, "page.txt") is None
    assert BS.resolve_slice("5508790", DDIR, REC, "pdftotext.txt") is None
