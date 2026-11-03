#!/usr/bin/env python3
"""Write the tracked NCES CCD source manifest and, on request, each year folder's SOURCE.md (#1037).

Hashes the CCD files the school-file band scopes read (#1022). That is ccd_sch_029/052/059 and
ccd_lea_059, for each catalogued year, as they sit on disk under data/raw/federal/nces-ccd/<year>/.
The output is config/source-manifests/nces-ccd.json, tracked in git. A file on disk as an extracted
CSV is recorded with the release zip it came from (`member`); a file on disk as the zip is recorded
as the zip.

Usage:
    python3 -m infrastructure.scripts.download.nces_ccd_manifest             # report only
    python3 -m infrastructure.scripts.download.nces_ccd_manifest --write     # write the tracked manifest
    python3 -m infrastructure.scripts.download.nces_ccd_manifest --write --repin   # accept changed bytes
    python3 -m infrastructure.scripts.download.nces_ccd_manifest --source-md # + SOURCE.md in data/raw (opt-in)

`--write` is guarded (#1052). It refuses, exit 1 and the tracked manifest untouched, when any
catalogued file is absent from disk (a fresh clone must not shrink the manifest), and when any file
the tracked manifest already pins is absent or carries different bytes (that is drift, the thing the
manifest exists to detect, not a reason to re-pin). `--repin` is the explicit, logged override for the
second case: the operator is saying the new bytes are the intended source.

No retrieval date is recorded, because none is known, and nothing machine-dependent is either: the
file mtime that used to be recorded made `--write` rewrite the tracked JSON after any re-copy with no
byte change (#1089). The sha256 and size are the record.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from infrastructure.scripts.download.fetch_nces_ccd import CCD_CATALOG
from infrastructure.utilities import source_manifest as SM

SOURCE = "nces-ccd"
BASE = "data/raw/federal/nces-ccd"
TABLES = ("school_directory", "school_membership", "school_staff", "district_staff")


def _entry(year: str, table: str, root: Path) -> dict | None:
    url = CCD_CATALOG[year][table]["url"]
    stem = url.rsplit("/", 1)[1].removesuffix(".zip")
    folder = SM.year_folder(BASE, year, root)
    zip_path, csv_path = folder / f"{stem}.zip", folder / f"{stem}.csv"
    path = zip_path if zip_path.exists() else csv_path if csv_path.exists() else None
    if path is None:
        return None
    e = {"file": path.name, "bytes": path.stat().st_size, "sha256": SM.sha256_file(path), "url": url}
    if path.suffix == ".csv":
        e["member"] = f"{stem}.csv"
    return e


def catalogued_years() -> list:
    return sorted(y for y in CCD_CATALOG if all(t in CCD_CATALOG[y] for t in TABLES))


def build(root: Path | None = None) -> tuple[dict, list]:
    """The manifest as disk would have it, plus the catalogued files disk lacks."""
    manifest, missing = {"source": SOURCE, "base": BASE, "years": {}}, []
    for year in catalogued_years():
        entries = []
        for table in TABLES:
            e = _entry(year, table, root)
            if e is None:
                missing.append(f"{year} {table}")
            else:
                entries.append(e)
        manifest["years"][year] = entries
    return manifest, missing


def source_md(year: str, entries: list) -> str:
    """The repo's SOURCE.md layout (`| file | sha256 | source |`), the one
    `sped_baseline_profiles._SOURCE_MD_ROW` parses, so verify_source's cross-check sees these rows."""
    lines = [f"# Provenance (NCES CCD {year}; hashes also tracked in config/source-manifests/{SOURCE}.json)",
             "", "| file | sha256 | source |", "|---|---|---|"]
    for e in entries:
        src = e["url"] + (f" (member {e['member']})" if "member" in e else "")
        lines.append(f"| {e['file']} | {e['sha256']} | {src} |")
    return "\n".join(lines) + "\n"


def refusals(tracked: dict | None, missing: list, root: Path, repin: bool) -> list:
    """Why `--write` must not proceed. Empty means it may."""
    why = [f"absent on disk: {m}" for m in missing]
    if tracked is not None:
        try:
            v = SM.verify(tracked, root=root)
        except SM.NothingMeasured:
            v = {"absent": [], "mismatched": []}
        drift = [f"pinned file absent: {a}" for a in v["absent"]]
        drift += [f"pinned bytes changed: {f} ({field}: {old} -> {new})" for f, field, old, new in v["mismatched"]]
        if drift and not repin:
            why += drift + ["(pass --repin to accept the changed bytes as the intended source)"]
    return why


def main(argv=None, root: Path | None = None, manifest_dir: Path = SM.MANIFEST_DIR) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write the tracked manifest (config/source-manifests/)")
    ap.add_argument("--repin", action="store_true",
                    help="with --write: accept files whose bytes differ from the tracked manifest (logged override)")
    ap.add_argument("--source-md", action="store_true",
                    help="also write SOURCE.md into each data/raw year folder (adds a file to data/raw: opt-in)")
    args = ap.parse_args(argv)
    manifest, missing = build(root)
    n = sum(len(v) for v in manifest["years"].values())
    if n == 0:
        print("NOTHING MEASURED — no catalogued CCD file found on disk")
        return 1
    print(json.dumps(manifest, indent=2))
    tracked_path = manifest_dir / f"{SOURCE}.json"
    tracked = json.loads(tracked_path.read_text(encoding="utf-8")) if tracked_path.exists() else None
    why = refusals(tracked, missing, root, args.repin)
    if args.write or args.source_md:
        if why:
            print("REFUSED — the tracked manifest is untouched:\n  " + "\n  ".join(why))
            return 1
        if args.repin:
            print("REPIN: accepting changed bytes as the intended source (operator override)")
    elif why:
        print("would refuse --write:\n  " + "\n  ".join(why))
    if args.write:
        manifest_dir.mkdir(parents=True, exist_ok=True)
        tracked_path.write_text(SM.dump(manifest), encoding="utf-8")
        print(f"wrote {tracked_path}")
    if args.source_md:
        for year, entries in manifest["years"].items():
            (SM.year_folder(BASE, year, root) / "SOURCE.md").write_text(source_md(year, entries), encoding="utf-8")
        print(f"wrote {len(manifest['years'])} SOURCE.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
