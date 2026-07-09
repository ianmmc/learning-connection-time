"""batch_00000 benchmark injection (stage1_queue/benchmark_batch.py) — the special-case batch.

Pure parts tested against a synthetic gt_root; the real-GT loader test reads the LOCAL (not
git-tracked — large per-district raw captures) curation workspace, so it's marked `integration`
like the other local-external-resource tests (file reads only, no DB, no writes)."""
import json
import hashlib
from pathlib import Path

import pytest

from infrastructure.acquisition.stage1_queue import benchmark_batch as BB


def test_gt_url_is_stable_and_hash_deterministic():
    u = BB.gt_url("1200180_BROWARD", "bells.pdf")
    assert u == "gt://gt_curation_20260621T060008Z/1200180_BROWARD/bells.pdf"
    rec = BB.capture_record("1200180_BROWARD", "bells.pdf")
    assert rec["hash"] == hashlib.md5(u.encode()).hexdigest()[:10]


def test_capture_record_shape_matches_stage4_readers():
    """process_stage4 reads files.bin: *.pdf -> the 4 PDF tools + raster OCR; image ext ->
    tesseract_image. kind mirrors the direct-fetch path in capture_discovery.mjs."""
    pdf = BB.capture_record("D", "Bell Schedule 25-26.pdf")
    assert pdf["kind"] == "pdf" and pdf["files"]["bin"] == "original.pdf" and pdf["ok"]
    png = BB.capture_record("D", "2023 Start and end times.png")
    assert png["kind"] == "image" and png["files"]["bin"] == "original.png"
    webp = BB.capture_record("D", "flier.WEBP")
    assert webp["files"]["bin"] == "original.webp"     # lowercased ext
    assert pdf["source"] == "benchmark_gt" and pdf["err"] is None


@pytest.mark.integration
def test_load_curated_finds_all_27_real_dirs():
    """Needs the local (not git-tracked) gt_curation_20260621T060008Z/{hub,per_school}/ raw
    capture directories — CI has only the tracked manifest/proposals JSON, not the binaries."""
    curated = BB.load_curated()
    assert len(curated) == 27
    missing = [c["district_id"] for c in curated if c["gt_dir"] is None]
    assert missing == [], f"curation dirs missing on disk: {missing}"
    topos = {c["gt_topology"] for c in curated}
    assert topos == {"hub", "per_school"}


def _fake_gt(tmp_path: Path) -> Path:
    root = tmp_path / "gt"
    d = root / "hub" / "9999999_Testville"
    d.mkdir(parents=True)
    (d / "bells.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "times.png").write_bytes(b"\x89PNG fake")
    (d / "notes.txt").write_text("dropped ext — must be ignored")
    (root / "gt_proposals.json").write_text(json.dumps(
        [{"district_id": "9999999", "dir": "9999999_Testville", "topology": "hub"}]))
    return root


def test_inject_district_lays_standard_pipeline_layout(tmp_path):
    gt = _fake_gt(tmp_path)
    raw = tmp_path / "captures_root"
    d = {"district_id": "9999999", "name": "Testville", "state": "ZZ",
         "domain": "", "gt_dirname": "9999999_Testville"}
    out = BB.inject_district(d, gt_root=gt, raw_root=raw)
    ddir = Path(out["dir"])
    assert out["n_files"] == 2                                    # .txt dropped
    disc = json.loads((ddir / "discovery.json").read_text())
    assert disc["district_id"] == "9999999" and disc["benchmark"] is True
    cands = json.loads((ddir / "candidates.json").read_text())["candidates"]
    assert len(cands) == 2 and all(c["tools"] == ["benchmark_gt"] for c in cands)
    caps = json.loads((ddir / "captures.json").read_text())
    assert len(caps) == 2
    for rec in caps:
        f = ddir / "captures" / rec["hash"] / rec["files"]["bin"]
        assert f.exists() and f.stat().st_size > 0                # bytes actually copied
    kinds = sorted(r["kind"] for r in caps)
    assert kinds == ["image", "pdf"]


def test_inject_refuses_to_overwrite(tmp_path):
    gt = _fake_gt(tmp_path)
    raw = tmp_path / "captures_root"
    d = {"district_id": "9999999", "name": "Testville", "state": "ZZ",
         "domain": "", "gt_dirname": "9999999_Testville"}
    BB.inject_district(d, gt_root=gt, raw_root=raw)
    with pytest.raises(FileExistsError):
        BB.inject_district(d, gt_root=gt, raw_root=raw)


def test_load_curated_resolves_buckets_from_proposals(tmp_path):
    """#148: a FIXTURE-based unit check of load_curated's LOGIC (proposals -> entries, hub/per_school
    dir resolution) that runs in CI — the real-27-dirs test above is integration-only (needs the local
    binaries), so a regression in this parsing/resolution shipped green through CI. Synthetic gt_root:
    no binaries, just a proposals manifest + a couple of stub dirs."""
    import json
    from infrastructure.acquisition.stage1_queue import benchmark_batch as BB
    (tmp_path / "hub").mkdir()
    (tmp_path / "per_school").mkdir()
    (tmp_path / "hub" / "alpha_dir").mkdir()             # resolves under hub/
    (tmp_path / "per_school" / "beta_dir").mkdir()       # resolves under per_school/
    # gamma_dir is intentionally absent on disk -> gt_dir must be None (the missing-dir signal)
    (tmp_path / "gt_proposals.json").write_text(json.dumps([
        {"district_id": "0100001", "dir": "alpha_dir", "topology": "hub"},
        {"district_id": "0200002", "dir": "beta_dir", "topology": "per_school"},
        {"district_id": "0300003", "dir": "gamma_dir", "topology": "hub"},
    ]))
    out = BB.load_curated(gt_root=tmp_path)
    assert [c["district_id"] for c in out] == ["0100001", "0200002", "0300003"]   # every proposal → entry
    by_id = {c["district_id"]: c for c in out}
    assert by_id["0100001"]["gt_dir"] == tmp_path / "hub" / "alpha_dir"           # resolved under hub/
    assert by_id["0200002"]["gt_dir"] == tmp_path / "per_school" / "beta_dir"     # resolved under per_school/
    assert by_id["0300003"]["gt_dir"] is None                                     # absent → None, not crash
    assert by_id["0100001"]["gt_topology"] == "hub" and by_id["0100001"]["gt_dirname"] == "alpha_dir"


def test_tracked_gt_proposals_manifest_has_27_valid_entries():
    """#148: the 27-count + topology validity of the TRACKED gt_proposals.json (no binaries needed) —
    catches a manifest regression in CI, complementing the integration on-disk-dirs test."""
    import json
    from infrastructure.acquisition.stage1_queue import benchmark_batch as BB
    mf = BB.GT_ROOT / "gt_proposals.json"
    if not mf.exists():
        import pytest as _pt
        _pt.skip("tracked gt_proposals.json not present in this checkout")
    props = json.loads(mf.read_text())
    assert len(props) == 27
    assert {p["topology"] for p in props} == {"hub", "per_school"}
    assert all(p.get("district_id") and p.get("dir") for p in props)
