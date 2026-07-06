"""Regression: Stage 7's resolve_content must read a `harvest_slice.txt` rep through the shared
`build_signals.resolve_harvest_slice` resolver (new-location-first), NOT by joining the capture dir
itself. The #58 relocation moved slices OUT of the capture dir, so the old direct-join raised
FileNotFoundError on every relocated slice and aborted a whole batch run (found live on Marshall WI
5508790 during the #122 run). A plain text rep must still read straight from the capture dir."""
import pytest

from infrastructure.acquisition.process_governance import stage7_run as R7


REC = "5508790:6cc3deb70a"          # <district_id>:<capture-hash>
DDIR = "5508790_marshall_school_district"


def test_harvest_slice_rep_uses_resolver(tmp_path, monkeypatch):
    """A harvest_slice rep reads the relocated file the resolver points at — never the capture dir."""
    slice_fp = tmp_path / "5508790_6cc3deb70a.txt"
    slice_fp.write_text("REGULAR DAY 8:05 AM - 3:10 PM", encoding="utf-8")

    seen = {}

    def fake_resolve(district_id, district_dir, rec_key):
        seen.update(district_id=district_id, district_dir=district_dir, rec_key=rec_key)
        return slice_fp

    monkeypatch.setattr(R7.BS, "resolve_harvest_slice", fake_resolve)
    # Point the capture dir at an EMPTY tmp tree: if resolve_content joined it (the old bug), the
    # read would FileNotFoundError. The resolver path must win instead.
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path / "captures_root")

    out = R7.resolve_content(DDIR, REC, R7.BS.HARVEST_SLICE_FILE, "text")

    assert out == "REGULAR DAY 8:05 AM - 3:10 PM"
    # called with the district_id parsed off the rec_key prefix (not the hash)
    assert seen == {"district_id": "5508790", "district_dir": DDIR, "rec_key": REC}


def test_harvest_slice_missing_everywhere_still_raises(tmp_path, monkeypatch):
    """When neither location has the slice, fall through to the legacy path so the failure is a clear
    FileNotFoundError (not a silent empty read)."""
    monkeypatch.setattr(R7.BS, "resolve_harvest_slice", lambda *a: None)
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path / "captures_root")
    with pytest.raises(FileNotFoundError):
        R7.resolve_content(DDIR, REC, R7.BS.HARVEST_SLICE_FILE, "text")


def test_non_slice_text_rep_reads_capture_dir(tmp_path, monkeypatch):
    """A normal text rep is unaffected — it still reads straight from the capture dir, and never
    consults the harvest-slice resolver."""
    cap = tmp_path / DDIR / "captures" / "6cc3deb70a"
    cap.mkdir(parents=True)
    (cap / "page.txt").write_text("PAGE TEXT", encoding="utf-8")

    def boom(*a):  # the resolver must not be touched for a non-slice rep
        raise AssertionError("resolve_harvest_slice called for a non-slice rep")

    monkeypatch.setattr(R7.BS, "resolve_harvest_slice", boom)
    monkeypatch.setattr(R7.paths, "RAW_CAPTURES", tmp_path)

    assert R7.resolve_content(DDIR, REC, "page.txt", "text") == "PAGE TEXT"
