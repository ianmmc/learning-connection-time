"""#1037 (#1022 T3): the tracked NCES CCD source manifest and its verifier.

DB-free. The verifier is driven against synthetic files in a tmp tree, covering each verdict: match,
wrong size, wrong hash, absent. The tracked manifest is checked for shape: canonical serialization,
every entry's URL in the download catalog, sha256-shaped hashes. Comparing the real data/raw files
to it is the drift check's job (#1042), and absence there must never pass as a match.
"""
import json

from infrastructure.scripts.download.fetch_nces_ccd import CCD_CATALOG
from infrastructure.utilities import source_manifest as SM


def _manifest(tmp_path, files):
    folder = tmp_path / "raw" / "2024_25"
    folder.mkdir(parents=True)
    entries = []
    for name, body in files.items():
        (folder / name).write_bytes(body)
        entries.append({"file": name, "bytes": len(body), "sha256": SM.sha256_file(folder / name),
                        "url": f"https://example/{name}", "file_mtime": "2026-11-01"})
    return {"source": "t", "base": "raw", "years": {"2024-25": entries}}, folder


def test_verify_reports_a_clean_match(tmp_path):
    m, _ = _manifest(tmp_path, {"a.csv": b"x" * 10, "b.zip": b"y" * 20})
    r = SM.verify(m, root=tmp_path)
    assert r == {"checked": ["2024-25/a.csv", "2024-25/b.zip"], "absent": [], "mismatched": []}


def test_verify_catches_a_changed_byte_of_the_same_size(tmp_path):
    m, folder = _manifest(tmp_path, {"a.csv": b"x" * 10})
    (folder / "a.csv").write_bytes(b"x" * 9 + b"z")
    (bad,) = SM.verify(m, root=tmp_path)["mismatched"]
    assert bad[:2] == ("2024-25/a.csv", "sha256")


def test_verify_catches_a_size_change(tmp_path):
    m, folder = _manifest(tmp_path, {"a.csv": b"x" * 10})
    (folder / "a.csv").write_bytes(b"x" * 11)
    assert SM.verify(m, root=tmp_path)["mismatched"] == [("2024-25/a.csv", "bytes", 10, 11)]


def test_an_absent_file_is_reported_never_matched(tmp_path):
    m, folder = _manifest(tmp_path, {"a.csv": b"x"})
    (folder / "a.csv").unlink()
    r = SM.verify(m, root=tmp_path)
    assert r["absent"] == ["2024-25/a.csv"] and r["checked"] == [] and r["mismatched"] == []


def test_entry_for(tmp_path):
    m, _ = _manifest(tmp_path, {"a.csv": b"x"})
    assert SM.entry_for(m, "2024-25", "a.csv")["bytes"] == 1
    try:
        SM.entry_for(m, "2024-25", "nope.csv")
    except KeyError as e:
        assert "nope.csv" in str(e)
    else:
        raise AssertionError("an undeclared file must raise")


class TestTrackedManifest:

    def test_canonical_serialization(self):
        raw = (SM.MANIFEST_DIR / "nces-ccd.json").read_text(encoding="utf-8")
        assert raw == SM.dump(json.loads(raw))

    def test_declares_the_band_scope_inputs_for_both_years(self):
        m = SM.load("nces-ccd")
        for year in ("2023-24", "2024-25"):
            prefixes = sorted(e["file"][:11] for e in m["years"][year])
            assert prefixes == ["ccd_lea_059", "ccd_sch_029", "ccd_sch_052", "ccd_sch_059"], year

    def test_every_entry_is_well_formed_and_catalogued(self):
        m = SM.load("nces-ccd")
        urls = {v["url"] for y in CCD_CATALOG.values() for v in y.values()}
        for year, entries in m["years"].items():
            for e in entries:
                assert e["url"] in urls, e
                assert len(e["sha256"]) == 64 and int(e["sha256"], 16) >= 0
                assert e["bytes"] > 0
                stem = e["url"].rsplit("/", 1)[1].removesuffix(".zip")
                # on disk as the zip itself, or as the CSV member extracted from it
                assert e["file"] == f"{stem}.zip" or (e["file"] == e["member"] == f"{stem}.csv"), e
