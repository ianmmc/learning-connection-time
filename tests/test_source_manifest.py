"""#1037 (#1022 T3): the tracked NCES CCD source manifest, its verifier, and the guarded generator.

DB-free. The verifier is driven against synthetic files in a tmp tree, covering each verdict: match,
wrong size, wrong hash, absent, and the empty sweep (#1053: each file lands in exactly one bucket;
an empty manifest raises rather than reading green). The generator is driven against a tmp data/raw
tree carrying the catalogued file NAMES, covering each refusal (#1052). The tracked manifest is
checked for shape: canonical serialization, every entry's URL in the download catalog, sha256-shaped
hashes. Comparing the real data/raw files to it is the drift check's job (#1042).
"""
import json
import re

import pytest

from infrastructure.database.migrations.sped_baseline_profiles import _SOURCE_MD_ROW
from infrastructure.scripts.download import nces_ccd_manifest as GEN
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


class TestVerify:

    def test_reports_a_clean_match(self, tmp_path):
        m, _ = _manifest(tmp_path, {"a.csv": b"x" * 10, "b.zip": b"y" * 20})
        r = SM.verify(m, root=tmp_path)
        assert r == {"checked": ["2024-25/a.csv", "2024-25/b.zip"], "absent": [], "mismatched": []}

    def test_a_changed_byte_of_the_same_size_is_mismatched_and_NOT_checked(self, tmp_path):
        """#1053: the hash-mismatch branch used to fall through into `checked` as well."""
        m, folder = _manifest(tmp_path, {"a.csv": b"x" * 10})
        (folder / "a.csv").write_bytes(b"x" * 9 + b"z")
        r = SM.verify(m, root=tmp_path)
        assert [b[:2] for b in r["mismatched"]] == [("2024-25/a.csv", "sha256")]
        assert r["checked"] == [] and r["absent"] == []

    def test_a_size_change_is_mismatched_and_not_checked(self, tmp_path):
        m, folder = _manifest(tmp_path, {"a.csv": b"x" * 10})
        (folder / "a.csv").write_bytes(b"x" * 11)
        r = SM.verify(m, root=tmp_path)
        assert r["mismatched"] == [("2024-25/a.csv", "bytes", 10, 11)] and r["checked"] == []

    def test_an_absent_file_is_reported_never_matched(self, tmp_path):
        m, folder = _manifest(tmp_path, {"a.csv": b"x"})
        (folder / "a.csv").unlink()
        r = SM.verify(m, root=tmp_path)
        assert r == {"checked": [], "absent": ["2024-25/a.csv"], "mismatched": []}

    def test_every_file_lands_in_exactly_one_bucket(self, tmp_path):
        m, folder = _manifest(tmp_path, {"ok.csv": b"1", "hash.csv": b"22", "size.csv": b"333", "gone.csv": b"4"})
        (folder / "hash.csv").write_bytes(b"2x")
        (folder / "size.csv").write_bytes(b"3")
        (folder / "gone.csv").unlink()
        r = SM.verify(m, root=tmp_path)
        buckets = r["checked"] + r["absent"] + [b[0] for b in r["mismatched"]]
        assert sorted(buckets) == sorted(f"2024-25/{e['file']}" for e in m["years"]["2024-25"])
        assert len(buckets) == len(set(buckets))

    @pytest.mark.parametrize("years", [{}, {"2024-25": []}])
    def test_an_empty_sweep_is_not_a_verdict(self, tmp_path, years):
        with pytest.raises(SM.NothingMeasured):
            SM.verify({"source": "t", "base": "raw", "years": years}, root=tmp_path)


def test_entry_for(tmp_path):
    m, _ = _manifest(tmp_path, {"a.csv": b"x"})
    assert SM.entry_for(m, "2024-25", "a.csv")["bytes"] == 1
    with pytest.raises(KeyError, match="nope.csv"):
        SM.entry_for(m, "2024-25", "nope.csv")


# ------------------------------------------------------------------ the generator (#1052, #1065)

def _stems(year):
    return [CCD_CATALOG[year][t]["url"].rsplit("/", 1)[1].removesuffix(".zip") for t in GEN.TABLES]


@pytest.fixture
def raw_tree(tmp_path):
    """A tmp repo root whose data/raw carries every catalogued file (as .zip) for every catalogued year."""
    for year in GEN.catalogued_years():
        folder = tmp_path / GEN.BASE / year.replace("-", "_")
        folder.mkdir(parents=True)
        for i, stem in enumerate(_stems(year)):
            (folder / f"{stem}.zip").write_bytes(f"{year}{stem}".encode() * (i + 1))
    return tmp_path


def _run(root, *flags):
    mdir = root / "config" / "source-manifests"
    return GEN.main(list(flags), root=root, manifest_dir=mdir), mdir / f"{GEN.SOURCE}.json"


def test_write_on_a_complete_tree_succeeds_and_verifies(raw_tree):
    rc, path = _run(raw_tree, "--write")
    assert rc == 0 and path.exists()
    m = json.loads(path.read_text())
    assert {len(v) for v in m["years"].values()} == {len(GEN.TABLES)}
    r = SM.verify(m, root=raw_tree)
    assert r["absent"] == [] and r["mismatched"] == [] and len(r["checked"]) == len(GEN.TABLES) * len(m["years"])
    assert path.read_text() == SM.dump(m)


def test_write_refuses_when_a_catalogued_file_is_absent(raw_tree, capsys):
    """#1052: a fresh clone (partial data/raw) must not shrink the tracked manifest."""
    rc, path = _run(raw_tree, "--write")
    before = path.read_text()
    year = GEN.catalogued_years()[0]
    (raw_tree / GEN.BASE / year.replace("-", "_") / f"{_stems(year)[0]}.zip").unlink()
    rc, _ = _run(raw_tree, "--write")
    assert rc == 1 and path.read_text() == before
    assert "REFUSED" in capsys.readouterr().out


def test_write_refuses_changed_bytes_without_repin_and_accepts_with(raw_tree, capsys):
    rc, path = _run(raw_tree, "--write")
    before = path.read_text()
    year = GEN.catalogued_years()[0]
    target = raw_tree / GEN.BASE / year.replace("-", "_") / f"{_stems(year)[0]}.zip"
    target.write_bytes(target.read_bytes() + b"!")
    rc, _ = _run(raw_tree, "--write")
    out = capsys.readouterr().out
    assert rc == 1 and path.read_text() == before and "pinned bytes changed" in out and "--repin" in out
    rc, _ = _run(raw_tree, "--write", "--repin")
    assert rc == 0 and "REPIN" in capsys.readouterr().out
    assert SM.entry_for(json.loads(path.read_text()), year, target.name)["sha256"] == SM.sha256_file(target)


def test_report_only_never_writes(raw_tree):
    rc, path = _run(raw_tree)
    assert rc == 0 and not path.exists()


def test_nothing_measured_on_an_empty_tree(tmp_path, capsys):
    rc, path = _run(tmp_path, "--write")
    assert rc == 1 and not path.exists() and "NOTHING MEASURED" in capsys.readouterr().out


def test_source_md_uses_the_repo_layout_the_parser_reads(raw_tree):
    """#1065: `_SOURCE_MD_ROW` (sped_baseline_profiles) must parse every row, and the file is UTF-8."""
    rc, _ = _run(raw_tree, "--source-md")
    assert rc == 0
    for year in GEN.catalogued_years():
        md = (raw_tree / GEN.BASE / year.replace("-", "_") / "SOURCE.md").read_text(encoding="utf-8")
        rows = {m["name"]: m["sha"] for m in _SOURCE_MD_ROW.finditer(md)}
        assert len(rows) == len(GEN.TABLES)
        for stem in _stems(year):
            assert rows[f"{stem}.zip"] == SM.sha256_file(raw_tree / GEN.BASE / year.replace("-", "_") / f"{stem}.zip")


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
                assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"])
                assert e["bytes"] > 0
                stem = e["url"].rsplit("/", 1)[1].removesuffix(".zip")
                # on disk as the zip itself, or as the CSV member extracted from it
                assert e["file"] == f"{stem}.zip" or (e["file"] == e["member"] == f"{stem}.csv"), e
