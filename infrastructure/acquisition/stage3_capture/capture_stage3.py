"""Stage 3 (Capture) of the bell-schedule acquisition pipeline -- the orchestration half.

Reads each district's candidates.json (Stage 2's deduped, capture-ready URL list) from
data/raw/lea-website-captures/<id>_<slug>/ -- never modifies it. The actual browser
automation (Playwright: fetch/render/modal-dismissal/page.pdf()/Drive handling/emergent-
candidate discovery) lives in infrastructure/scraper/capture_discovery.mjs; this module is
the Python control layer around it: reconciliation, outcome rollup, and the single
registry write-back, exactly mirroring discover_stage2.py's split (Python orchestrates and
owns the registry; a separate process does the risky/external work).

Filesystem is authoritative: a district's captures.json existing in
data/raw/lea-website-captures/<id>_<slug>/ IS "Stage 3 done" -- the registry is a cache of
that fact, reconciled FROM disk, never the reverse. See reconcile().

Usage:
  capture_stage3.py reconcile [--root data/raw/lea-website-captures]
  capture_stage3.py finish    <district_id> [--root data/raw/lea-website-captures]
"""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import district_status as DS

IMAGE_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff")


RAW_DIR = Path("data/raw/lea-website-captures")


def find_districts(root: Path) -> list:
    """Every directory under root with a discovery.json (Stage 2's header fields -- name,
    state, domain -- read from there, not candidates.json, which doesn't carry them) AND a
    candidates.json (what Stage 3 actually consumes). A district missing either is not
    Stage 3's concern yet."""
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        disc_path, cand_path = d / "discovery.json", d / "candidates.json"
        if not (d.is_dir() and disc_path.exists() and cand_path.exists()):
            continue
        disc = json.loads(disc_path.read_text())
        out.append({
            "district_id": disc["district_id"], "name": disc["name"],
            "state": disc["state"], "domain": disc.get("domain", ""), "dir": d,
        })
    return out


def reconcile(districts: list, registry: dict) -> tuple[list, list]:
    """Filesystem is truth. For every district with candidates.json ready: if captures.json
    already exists on disk, reconcile the registry up to match (skip -- already done, never
    redo automatically). If the registry claims furthest_stage>=3 but the file does NOT
    exist, that's a control failure, not routine drift -- halt the entire run rather than
    risk propagating whatever caused it to other districts. Returns (todo, skipped)."""
    todo, skipped = [], []
    for d in districts:
        did = d["district_id"]
        done_on_disk = (d["dir"] / "captures.json").exists()
        rec = registry["districts"].get(did)
        reg_says_done = rec is not None and rec.get("furthest_stage", 0) >= 3
        if done_on_disk and not reg_says_done:
            DS.record_stage(
                registry, did, d["name"], d["state"], stage=3, stage_name="capture",
                outcome="reconciled_from_disk",
            )
            skipped.append(d)
        elif done_on_disk and reg_says_done:
            skipped.append(d)
        elif not done_on_disk and reg_says_done:
            raise SystemExit(
                f"CONTROL FAILURE: registry says {did} ({d['name']}) reached Stage 3+ but "
                f"{d['dir'] / 'captures.json'} does not exist. Stopping the entire run -- "
                f"investigate before re-running anything."
            )
        else:
            todo.append(d)
    return todo, skipped


def compute_outcome(captures: list) -> tuple[str, str]:
    """Roll up per-candidate ok/err into a district-level outcome plus a short notes
    summary. The registry holds this rollup only -- never a live array of open issues
    (a recipe for sync bugs); a human generates the actual triage list on demand by
    scanning captures.json files for a specific err value when ready to act on it."""
    oks = [c for c in captures if c.get("ok")]
    fails = [c for c in captures if not c.get("ok")]
    if not fails:
        outcome = "captured_all"
    elif not oks:
        outcome = "capture_failed_all"
    else:
        outcome = "captured_partial"
    reasons = Counter(c.get("err") or "unknown" for c in fails)
    notes = "; ".join(f"{n} {reason}" for reason, n in reasons.items())
    return outcome, notes


# ---------------------------------------------------------------- manifest recovery (REQ-110 follow-up)
# A Node capture run that is SIGKILLed mid-run (e.g. a transient stall hitting the per-district timeout)
# leaves the per-URL folders on disk but NEVER writes captures.json (the manifest is end-of-run), so the
# completed work is orphaned (no manifest -> invisible to Stage 4 + the cache, the district reads as a
# total failure). These helpers REBUILD a manifest from disk. RECOVERY ONLY: they refuse to overwrite an
# existing captures.json, and the records are DEGRADED vs a live capture (fingerprint / final_url /
# text_times aren't recoverable from disk). The going-forward fix is Node-owns-shutdown (write a partial
# manifest on its own deadline); this is for the already-orphaned districts.

def _strip_fragment(url: str) -> str:
    return url.split("#", 1)[0]


def _url_hash(url: str) -> str:
    """md5(stripFragment(url))[:10] — identical to capture_discovery.mjs's per-URL folder naming."""
    return hashlib.md5(_strip_fragment(url).encode()).hexdigest()[:10]


def _record_from_folder(folder: Path, url: str, *, tools, source, found_on) -> dict | None:
    """Build a capture record from the files present in a per-URL folder. Returns None for an empty
    (in-flight-at-kill) folder. Carries everything Stage 4 + the cache read (files/kind/ok/url/hash)."""
    if not folder.is_dir():
        return None
    files = sorted(f.name for f in folder.iterdir() if f.is_file())
    if not files:
        return None
    rec = {"url": url, "tools": list(tools or []), "source": source, "found_on": found_on,
           "hash": folder.name, "ok": True, "files": {}, "final_url": url,
           "fingerprint": None, "reconstructed": True}
    if "page.txt" in files:
        rec["kind"] = "html"
        rec["files"]["txt"] = "page.txt"
        if "page.png" in files:
            rec["files"]["png"] = "page.png"
        if "page.pdf" in files:
            rec["files"]["pdf"] = "page.pdf"
        rec["segmented"] = (folder / "page.main.txt").exists()
    elif (orig := next((f for f in files if f.startswith("original.")), None)):
        ext = orig.rsplit(".", 1)[-1].lower()
        rec["kind"] = "image" if ext in IMAGE_EXTS else ("pdf" if ext == "pdf" else "binary")
        rec["files"]["bin"] = orig
    else:   # a Drive export (file.pdf / pdf.pdf / csv.csv / markdown.md ...) — map by stem
        rec["kind"] = "drive_export"
        for f in files:
            rec["files"][f.split(".")[0]] = f
    return rec


def reconstruct_captures(district: dict) -> list:
    """RECOVERY ONLY: rebuild the captures.json record list from the on-disk per-URL folders. EVERY
    candidate appears (completeness is the audit bar): a recovered candidate is ok=True with its files;
    a candidate whose folder is empty/absent (capture interrupted before it finished) is ok=False with a
    `not_recovered` err -> the district honestly resolves `captured_partial`. Refuses if captures.json
    already exists. Emergent folders (a captured URL not in candidates.json) can't be reconstructed —
    md5 is one-way, so their URL is unrecoverable — and are left on disk, out of the manifest."""
    ddir = district["dir"]
    if (ddir / "captures.json").exists():
        raise SystemExit(f"{ddir / 'captures.json'} exists — refusing to overwrite "
                         f"(reconstruction is recovery-only)")
    cand = json.loads((ddir / "candidates.json").read_text()).get("candidates", [])
    capdir = ddir / "captures"
    records = []
    for c in cand:
        h = _url_hash(c["url"])
        rec = _record_from_folder(capdir / h, c["url"], tools=c.get("tools", []),
                                  source="discovered", found_on=None)
        if rec is None:
            rec = {"url": c["url"], "tools": list(c.get("tools", [])), "source": "discovered",
                   "found_on": None, "hash": h, "ok": False, "files": {},
                   "err": "not_recovered (capture interrupted before completion)"}
        records.append(rec)
    return records


def manual_capture_record(district: dict, *, url: str, src_file: Path, found_on: str | None = None) -> dict:
    """Drop a human-sourced file into the captures tree as a normal `source:"manual"` capture record
    (manual follow-up — no formal mechanism yet). Copies src_file to captures/<md5(url)>/original.<ext>;
    returns the record for the caller to fold into the manifest."""
    h = _url_hash(url)
    folder = district["dir"] / "captures" / h
    folder.mkdir(parents=True, exist_ok=True)
    ext = (src_file.suffix.lstrip(".") or "bin").lower()
    shutil.copy2(src_file, folder / f"original.{ext}")
    return {"url": url, "tools": [], "source": "manual", "found_on": found_on, "hash": h, "ok": True,
            "files": {"bin": f"original.{ext}"},
            "kind": "image" if ext in IMAGE_EXTS else ("pdf" if ext == "pdf" else "binary"),
            "final_url": url, "fingerprint": None, "reconstructed": True}


def write_manifest(district: dict, records: list) -> None:
    """Atomic write of a reconstructed captures.json (recovery path; refuses to clobber)."""
    path = district["dir"] / "captures.json"
    if path.exists():
        raise SystemExit(f"{path} exists — refusing to overwrite (reconstruction is recovery-only)")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(records, indent=2))
    tmp.replace(path)


def finish_district(district: dict, registry: dict) -> str:
    """Single registry write per district, at actual completion -- never an interim
    'started' marker, same principle as Stage 2: there's nothing meaningful to reconcile
    against a half-finished state, since captures.json only exists once the Node capture
    script has fully finished that district."""
    captures_path = district["dir"] / "captures.json"
    captures = json.loads(captures_path.read_text())
    outcome, notes = compute_outcome(captures)
    DS.record_stage(
        registry, district["district_id"], district["name"], district["state"],
        stage=3, stage_name="capture", outcome=outcome, notes=notes,
    )
    # Project this district's capture receipts into the live DB cache (the console's Stage-3 surface
    # reads them). Best-effort: captures.json on disk + the state_event are the durable record.
    CI.cache_capture(district["dir"], district["district_id"])
    return outcome


def main():
    ap = argparse.ArgumentParser(description="Stage 3 (Capture), orchestration half")
    ap.add_argument("--root", default=str(RAW_DIR))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reconcile")

    p = sub.add_parser("finish")
    p.add_argument("district_id")

    # Recovery: rebuild captures.json from disk for a district orphaned by a mid-run SIGKILL.
    pr = sub.add_parser("reconstruct", help="rebuild captures.json from on-disk capture folders (recovery)")
    pr.add_argument("district_id")
    pr.add_argument("--manual-file", help="a human-sourced file to add as a source:manual capture record")
    pr.add_argument("--manual-url", help="the origin URL/page for --manual-file (hashed to the folder name)")

    a = ap.parse_args()
    root = Path(a.root)
    districts = find_districts(root)

    if a.cmd == "reconcile":
        registry = DS.load()
        todo, skipped = reconcile(districts, registry)
        DS.save(registry)
        print(f"{len(todo)} to capture, {len(skipped)} already done (skipped)")
        for d in skipped:
            print(f"  skip [{d['state']}] {d['name']} ({d['district_id']})")
        for d in todo:
            print(f"  todo [{d['state']}] {d['name']} ({d['district_id']})")

    elif a.cmd == "finish":
        district = next((d for d in districts if d["district_id"] == a.district_id), None)
        if district is None:
            raise SystemExit(f"district {a.district_id} not found under {root} (needs discovery.json + candidates.json)")
        registry = DS.load()
        outcome = finish_district(district, registry)
        DS.save(registry)
        print(f"{district['district_id']} {district['name']}: {outcome}")

    elif a.cmd == "reconstruct":
        district = next((d for d in districts if d["district_id"] == a.district_id), None)
        if district is None:
            raise SystemExit(f"district {a.district_id} not found under {root} (needs discovery.json + candidates.json)")
        records = reconstruct_captures(district)
        if a.manual_file:
            if not a.manual_url:
                raise SystemExit("--manual-file requires --manual-url (the origin page, hashed to the folder)")
            records.append(manual_capture_record(district, url=a.manual_url, src_file=Path(a.manual_file),
                                                 found_on=a.manual_url))
            print(f"  + manual capture: {a.manual_file} -> {a.manual_url}")
        n_ok = sum(1 for r in records if r.get("ok"))
        write_manifest(district, records)
        registry = DS.load()
        outcome = finish_district(district, registry)   # records state_event + upserts the DB cache
        DS.save(registry)
        print(f"{district['district_id']} {district['name']}: reconstructed "
              f"{n_ok}/{len(records)} ok -> {outcome}")


if __name__ == "__main__":
    main()
