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
import json
from collections import Counter
from pathlib import Path

from infrastructure.acquisition.common import district_status as DS


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
    return outcome


def main():
    ap = argparse.ArgumentParser(description="Stage 3 (Capture), orchestration half")
    ap.add_argument("--root", default=str(RAW_DIR))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reconcile")

    p = sub.add_parser("finish")
    p.add_argument("district_id")

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


if __name__ == "__main__":
    main()
