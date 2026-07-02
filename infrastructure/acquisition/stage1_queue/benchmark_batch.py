"""batch_00000 — the BENCHMARK batch: the 27 curated-GT districts injected at the Stage-3 seam.

THE SPECIAL CASE, by design (Ian, approved 2026-07-02). The 27 districts of the hand-verified
ground truth (`data/benchmark/gt_curation_20260621T060008Z/` — 940/943 per-school start/end
times human-confirmed) enter the pipeline with their FROZEN capture artifacts — the exact
files the GT was verified against — so Stage 7's council and Stage 8's aggregation can be
scored against known answers with zero site-drift confounding. No discovery, no fetching.

What this module does:
  1. builds a batch_00000 doc from the curated district list (NCES school selection runs
     normally — bands/topology denominators are real; exclusion filters are NOT applied,
     a benchmark district is in by fiat) and persists it approved, batch_type="benchmark";
  2. injects each district's curated files into the standard pipeline layout
     (`data/raw/lea-website-captures/<id>_<slug>/` with discovery.json / candidates.json /
     captures/<hash>/original.<ext> / captures.json), each file a direct-fetch-shaped capture
     (`files.bin`, kind pdf|image) under a stable `gt://` URI (the originals were
     hand-collected; no source URLs survive — see the archive sidecars);
  3. writes the cross-stage cache rows + stage-2/3 state_events so the console and Stage 4's
     reconcile see a coherent, already-captured batch.

Stage 4 then runs NORMALLY (console or headless), and the Stage 4→5 handoff ingests as usual.

THE WALL (enforce at Stage 7-9 build): batch_type == "benchmark" marks this batch. Benchmark
districts' extracted values must NEVER be Stage-9-written to the LCT DB or counted in
funnel/enrichment statistics — they are a measuring stick, and several source docs are
deliberately of older school years. See STAGE6_DISPATCH_DESIGN §3C C.6.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common.discover import host_of
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue.queue_batch import eligible_pool, select_schools
from infrastructure.acquisition.stage2_discover.discover_stage2 import slugify

import infrastructure.acquisition.common.school_sampling as S

BATCH_ID = "batch_00000"
GT_ROOT = paths.DATA_ROOT / "benchmark" / "gt_curation_20260621T060008Z"
KEPT_EXT = {".gif", ".jpeg", ".jpg", ".pdf", ".png", ".webp"}
DEFAULT_YEAR = "2024_25"


def load_curated(gt_root: Path = GT_ROOT) -> list[dict]:
    """The 27 curated districts: id, curation dir (under hub/ or per_school/), GT topology."""
    proposals = json.loads((gt_root / "gt_proposals.json").read_text())
    out = []
    for p in proposals:
        d = None
        for bucket in ("hub", "per_school"):
            cand = gt_root / bucket / p["dir"]
            if cand.is_dir():
                d = cand
                break
        out.append({"district_id": p["district_id"], "gt_dir": d,
                    "gt_dirname": p["dir"], "gt_topology": p["topology"]})
    return out


def gt_url(gt_dirname: str, filename: str) -> str:
    """Stable benchmark URI — the artifact's identity. The originals were hand-collected
    (no source URLs survive; archive sidecars carry migration provenance only)."""
    return f"gt://gt_curation_20260621T060008Z/{gt_dirname}/{filename}"


def capture_record(gt_dirname: str, filename: str) -> dict:
    """One curated file as a direct-fetch-shaped Stage-3 capture record (files.bin +
    kind pdf|image — exactly what process_stage4 reads for PDF tools / tesseract_image)."""
    url = gt_url(gt_dirname, filename)
    ext = Path(filename).suffix.lower().lstrip(".")
    return {
        "url": url,
        "hash": hashlib.md5(url.encode()).hexdigest()[:10],
        "source": "benchmark_gt",
        "found_on": None,
        "ok": True,
        "kind": "pdf" if ext == "pdf" else "image",
        "files": {"bin": f"original.{ext}"},
        "err": None,
        "fingerprint": {},
    }


def build_batch_doc(year: str = DEFAULT_YEAR) -> tuple[dict, list]:
    """The batch_00000 doc in build_batch()'s exact shape, over the FIXED curated list.
    NCES school selection runs normally (real band scaffolding + topology denominators);
    the pre-queue exclusion filters are bypassed on purpose (empty registry; a curated
    district that fell out of the eligible pool is reported, not silently dropped)."""
    curated = load_curated()
    pool, sch_idx, _ = eligible_pool(year, {"districts": {}})   # no already-attempted filter
    level_counts = S.school_level_counts(year)
    districts_out, skipped = [], []
    for c in curated:
        did = c["district_id"]
        if c["gt_dir"] is None:
            skipped.append((did, "curation dir not found on disk"))
            continue
        info = pool.get(did)
        if info is None:
            skipped.append((did, "not in the NCES eligible pool (closed/CTC/gap?)"))
            continue
        web = info["website"] or ""
        domain = host_of(web if "//" in web else "http://" + web) if web else ""
        order, schools_by_band = select_schools(BATCH_ID, did, sch_idx.get(did, {}))
        districts_out.append({
            "district_id": did,
            "name": info["name"],
            "state": info["state"],
            "domain": domain,
            "enrollment_k12": info["enrollment_k12"],
            "lea_claimed_bands": sorted(info["claimed_bands"]),
            "nces_school_counts": level_counts.get(did, {"total": 0, "by_level": {}}),
            "band_processing_order": order,
            "schools_by_band": schools_by_band,
            "gt_dirname": c["gt_dirname"],
            "gt_topology": c["gt_topology"],
        })
    doc = {
        "batch_id": BATCH_ID,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n": len(districts_out),
        "nces_year": year,
        "benchmark": {
            "purpose": ("the 27 curated-GT districts, injected at the Stage-3 seam from the "
                        "FROZEN gt_curation artifacts — the accuracy yardstick for Stage 7/8"),
            "gt_source": str(GT_ROOT.relative_to(paths.DATA_ROOT.parent)
                             if GT_ROOT.is_relative_to(paths.DATA_ROOT.parent) else GT_ROOT),
            "approved": "Ian, in-chat, 2026-07-02",
            "wall": ("NEVER Stage-9 written, NEVER counted in funnel/enrichment stats; "
                     "several source docs are deliberately older school years"),
        },
        "school_cap_per_band": 12,
        "districts": districts_out,
    }
    return doc, skipped


def inject_district(d: dict, gt_root: Path = GT_ROOT, raw_root: Path | None = None) -> dict:
    """Lay one district's curated files into the standard pipeline capture layout.
    Returns the summary {district_id, dir, n_files}. Refuses to overwrite an existing
    discovery.json (same write-once posture as Stage 2)."""
    raw_root = raw_root or paths.RAW_CAPTURES
    ddir = raw_root / f"{d['district_id']}_{slugify(d['name'])}"
    if (ddir / "discovery.json").exists():
        raise FileExistsError(f"{ddir}/discovery.json exists — refusing to overwrite "
                              "(benchmark injection is one-shot; remove manually to redo)")
    src_dir = None
    for bucket in ("hub", "per_school"):
        cand = gt_root / bucket / d["gt_dirname"]
        if cand.is_dir():
            src_dir = cand
            break
    files = sorted(f.name for f in src_dir.iterdir()
                   if f.is_file() and f.suffix.lower() in KEPT_EXT)
    caps, cands = [], []
    (ddir / "captures").mkdir(parents=True, exist_ok=True)
    for fname in files:
        rec = capture_record(d["gt_dirname"], fname)
        rec_dir = ddir / "captures" / rec["hash"]
        rec_dir.mkdir(exist_ok=True)
        shutil.copy2(src_dir / fname, rec_dir / rec["files"]["bin"])
        caps.append(rec)
        cands.append({"url": rec["url"], "schools": [], "tools": ["benchmark_gt"]})
    discovery_doc = {
        "district_id": d["district_id"],
        "name": d["name"],
        "state": d["state"],
        "domain": d.get("domain", ""),
        "batch_id": BATCH_ID,
        "benchmark": True,
        "note": ("BENCHMARK INJECTION — no discovery ran; candidates are the frozen "
                 "gt_curation artifacts under gt:// URIs (hand-collected originals; "
                 "no source URLs survive)"),
        "schools": [],
    }
    (ddir / "discovery.json").write_text(json.dumps(discovery_doc, indent=2))
    (ddir / "candidates.json").write_text(json.dumps({"candidates": cands}, indent=2))
    (ddir / "captures.json").write_text(json.dumps(caps, indent=2))
    return {"district_id": d["district_id"], "dir": str(ddir), "n_files": len(files)}


def create_and_inject(year: str = DEFAULT_YEAR, actor: str = "benchmark_injector") -> dict:
    """The whole one-shot: batch rows (created + APPROVED — Ian's in-chat approval
    2026-07-02) + receipt, file injection, cache rows, stage-2/3 state_events.
    Stage 4 is deliberately NOT run here — run it via the console/headless as usual."""
    doc, skipped = build_batch_doc(year)
    gdb.init_precious_schema()
    with gdb.session_scope() as sess:
        BSTORE.create_batch(sess, doc, batch_type="benchmark", actor=actor)
        BSTORE.approve_batch(sess, BATCH_ID, actor="ian:chat-approval-2026-07-02")
        BSTORE.write_receipt(sess, BATCH_ID)
    injected = [inject_district(d) for d in doc["districts"]]
    with gdb.session_scope() as sess:
        for d in doc["districts"]:
            ddir = Path(paths.RAW_CAPTURES) / f"{d['district_id']}_{slugify(d['name'])}"
            CI.ingest_discovery(sess, ddir)
            CI.ingest_capture(sess, ddir, d["district_id"])
        sess.commit()
    registry = DS.load()
    for d in doc["districts"]:
        DS.record_stage(registry, d["district_id"], d["name"], d["state"], stage=1,
                        stage_name="queue", outcome="queued", batch_id=BATCH_ID)
        DS.record_stage(registry, d["district_id"], d["name"], d["state"], stage=2,
                        stage_name="discover", outcome="found_all", batch_id=BATCH_ID,
                        notes="benchmark injection: frozen gt_curation artifacts, no discovery ran")
        DS.record_stage(registry, d["district_id"], d["name"], d["state"], stage=3,
                        stage_name="capture", outcome="captured_all", batch_id=BATCH_ID,
                        notes="benchmark injection: files copied from gt_curation, no fetching")
        DS.save(registry, export=False)
    DS.export()
    return {"batch": BATCH_ID, "districts": len(doc["districts"]),
            "skipped": skipped, "injected": injected}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Create + inject the batch_00000 benchmark batch")
    ap.add_argument("--year", default=DEFAULT_YEAR)
    ap.add_argument("--dry-run", action="store_true", help="build + report only, write nothing")
    args = ap.parse_args()
    if args.dry_run:
        doc, skipped = build_batch_doc(args.year)
        print(f"{BATCH_ID}: {doc['n']} districts ready; skipped: {skipped or 'none'}")
        for d in doc["districts"]:
            print(f"  {d['district_id']} {d['name'][:40]:<40} gt_topology={d['gt_topology']}")
        return
    out = create_and_inject(args.year)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
