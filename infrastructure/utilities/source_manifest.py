"""Tracked provenance for raw source files (#1037, #1022 T3).

`data/raw/` is gitignored, so nothing in git says which bytes a raw file held. A source manifest is
a TRACKED JSON (`config/source-manifests/<source>.json`) recording, per year, each file's name, size,
sha256 and origin URL. When a file on disk was extracted from a release zip, it also records the zip
member it came from. The importer (#1039) stores these sha256s with every row it loads. The drift check
(#1042) compares disk to manifest, and stored rows to manifest.

Shape: {"source": str, "base": "<path under the repo>", "years": {"<year>": [entry, ...]}} where an
entry is {"file", "bytes", "sha256", "url", "member"?}. Nothing machine-dependent is recorded (#1089:
a file mtime made `--write` rewrite the tracked JSON on every machine with no byte change).

Where the files live is decided ONCE, by `base_dir` / `year_folder` (#1089): `base` is repo-relative,
and when the acquisition layer's LCT_DATA_ROOT relocates the data tree the `data/` prefix follows it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST_DIR = REPO / "config" / "source-manifests"


def base_dir(manifest_or_base: dict | str, root: Path | None = None) -> Path:
    """The folder a manifest's `base` names. An explicit `root` wins (tests, scratch trees); otherwise
    LCT_DATA_ROOT, when set, replaces the repo's `data/` (the same override acquisition/common/paths.py
    honours); otherwise the repo."""
    base = manifest_or_base["base"] if isinstance(manifest_or_base, dict) else manifest_or_base
    if root is not None:
        return Path(root) / base
    relocated = os.environ.get("LCT_DATA_ROOT")
    if relocated and (base == "data" or base.startswith("data/")):
        return Path(relocated).expanduser() / base[len("data/"):]
    return REPO / base


def year_folder(manifest_or_base: dict | str, year: str, root: Path | None = None) -> Path:
    """`<base>/<year with '-' as '_'>`: the one spelling of the per-year folder rule."""
    return base_dir(manifest_or_base, root) / year.replace("-", "_")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def load(source: str) -> dict:
    return json.loads((MANIFEST_DIR / f"{source}.json").read_text(encoding="utf-8"))


def dump(manifest: dict) -> str:
    """The canonical serialization (indent 2, literal punctuation, trailing newline)."""
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def entry_for(manifest: dict, year: str, file: str) -> dict:
    """The manifest entry for one file. KeyError when it is not declared."""
    for e in manifest["years"][year]:
        if e["file"] == file:
            return e
    raise KeyError(f"{file} is not declared for {year} in the {manifest['source']} manifest")


class NothingMeasured(Exception):
    """verify() was given no entries to check: an empty sweep is not a verdict."""


def verify(manifest: dict, root: Path | None = None) -> dict:
    """Compare every declared file on disk with its manifest entry. Each file lands in exactly ONE of
    {"checked": [...]            # present, size AND sha256 match: verified clean
     "absent": [...]             # declared but not on disk (reported, never a match)
     "mismatched": [(file, field, declared, actual), ...]}   # present, size or sha256 differs
    Raises NothingMeasured when the manifest declares no file at all (#1053)."""
    out = {"checked": [], "absent": [], "mismatched": []}
    entries = [(y, e) for y, es in sorted(manifest["years"].items()) for e in es]
    if not entries:
        raise NothingMeasured(f"the {manifest.get('source')} manifest declares no file")
    for year, e in entries:
        label = f"{year}/{e['file']}"
        path = year_folder(manifest, year, root) / e["file"]
        if not path.exists():
            out["absent"].append(label)
        elif (size := path.stat().st_size) != e["bytes"]:
            out["mismatched"].append((label, "bytes", e["bytes"], size))
        elif (actual := sha256_file(path)) != e["sha256"]:
            out["mismatched"].append((label, "sha256", e["sha256"], actual))
        else:
            out["checked"].append(label)
    return out
