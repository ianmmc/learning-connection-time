"""Stage 2 (Discover) of the bell-schedule acquisition pipeline -- the deterministic half.

Reads Stage 1's batch JSON directly (schools_by_band, domain) -- NEVER recomputes band
membership from raw NCES CSV (see ACQUISITION_PIPELINE.md Stage 2; that's the exact bug
class Stage 1's CP-A review spent a full day fixing -- recomputing here would silently
discard every fix). Orchestration is agent-in-the-loop: Wave 1 needs a Haiku WebSearch
subagent, which this script cannot spawn. See .claude/skills/stage2-discover/SKILL.md for
the full procedure this module is driven by. None of this module ever runs inside a
subagent -- a subagent only ever returns its raw findings as a strict JSON result; this
script does all gating, Wave 2, flattening, writing, and registry bookkeeping.

Filesystem is authoritative: a district's discovery.json existing in
data/raw/lea-website-captures/<id>_<slug>/ IS "Stage 2 done" -- the registry is a cache of
that fact, reconciled FROM disk, never the reverse. See reconcile().

Usage:
  discover_stage2.py reconcile <batch.json>
  discover_stage2.py roster    <batch.json> <district_id>
  discover_stage2.py finish    <batch.json> <district_id> <wave1_result.json>
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths

from infrastructure.acquisition.common.discover import host_of, gate, openrouter_search

# Anchored to the repo (paths.RAW_CAPTURES), never a CWD-relative literal -- this script and the
# governance server (which reads the same discovery.json/candidates.json) must agree on the location
# regardless of launch directory. (The gate@1 create 500'd on exactly this CWD-relative class of bug.)
RAW_DIR = paths.RAW_CAPTURES
BANDS = ("elementary", "middle", "high")


def slugify(name: str, maxlen: int = 40) -> str:
    """lowercase, non-alphanumeric -> underscore, collapsed, truncated. district_id is the
    real disambiguator (see lea_dir()) -- this is for human readability only."""
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return s[:maxlen].rstrip("_")


def lea_dir(district_id: str, name: str) -> Path:
    return RAW_DIR / f"{district_id}_{slugify(name)}"


def query_for(school: str, state: str) -> str:
    return f"{school} {state} bell schedule start and end times"


def load_batch(path) -> dict:
    return json.loads(Path(path).read_text())


def find_district(batch: dict, district_id: str) -> dict:
    for d in batch["districts"]:
        if d["district_id"] == district_id:
            return d
    raise SystemExit(f"district {district_id} not found in batch {batch.get('batch_id')}")


def build_roster(district: dict) -> list:
    """Per-school targeting list from a Stage 1 batch district entry's schools_by_band --
    NEVER recomputed from NCES CSV. One row per distinct school_id (a school spanning
    multiple bands appears once, with all its bands listed)."""
    by_school = {}
    for band in BANDS:
        for s in district.get("schools_by_band", {}).get(band, {}).get("schools", []):
            row = by_school.setdefault(
                s["school_id"], {"school_id": s["school_id"], "school": s["name"], "bands": []}
            )
            if band not in row["bands"]:
                row["bands"].append(band)
    roster = list(by_school.values())
    for r in roster:
        r["query"] = query_for(r["school"], district["state"])
    return roster


def reconcile(batch: dict, registry: dict) -> tuple[list, list]:
    """Filesystem is truth. For every district in the batch: if discovery.json already
    exists on disk, reconcile the registry up to match (skip -- already done, never redo
    automatically). If the registry claims furthest_stage>=2 but the file does NOT exist,
    that's a control failure, not routine drift -- halt the entire run rather than risk
    propagating whatever caused it to other districts. Returns (todo, skipped)."""
    todo, skipped = [], []
    for d in batch["districts"]:
        did = d["district_id"]
        done_on_disk = (lea_dir(did, d["name"]) / "discovery.json").exists()
        rec = registry["districts"].get(did)
        reg_says_done = rec is not None and rec.get("furthest_stage", 0) >= 2
        if done_on_disk and not reg_says_done:
            DS.record_stage(
                registry, did, d["name"], d["state"], stage=2, stage_name="discover",
                outcome="reconciled_from_disk", batch_id=batch.get("batch_id"),
            )
            skipped.append(d)
        elif done_on_disk and reg_says_done:
            skipped.append(d)
        elif not done_on_disk and reg_says_done:
            raise SystemExit(
                f"CONTROL FAILURE: registry says {did} ({d['name']}) reached Stage 2+ but "
                f"{lea_dir(did, d['name']) / 'discovery.json'} does not exist. Stopping the "
                f"entire run -- investigate before re-running anything in this batch."
            )
        else:
            todo.append(d)
    return todo, skipped


def gate_urls(urls: list, domain: str) -> list:
    """The same on-domain/CMS-slug/news-aggregator gate as the legacy district-level
    discover.py, applied per-school. Returns [{"url", "kept", "reason"}, ...]."""
    scoped = bool(domain)
    slug = domain.split(".")[0] if domain else ""
    out = []
    for u in urls:
        ok, why = gate(u, domain, slug, scoped)
        out.append({"url": u, "kept": ok, "reason": why})
    return out


def validate_wave1_result(raw: dict, district: dict) -> dict:
    """Defends the subagent->orchestrator handoff contract: the subagent must echo
    district_id and domain (the NCES seed) alongside whatever it found, so the seed and
    the fruit travel together rather than requiring a cross-reference back to the batch.
    Fails loud on any mismatch -- a wrong-district result silently accepted would
    contaminate discovery.json with another district's URLs."""
    if raw.get("district_id") != district["district_id"]:
        raise SystemExit(
            f"Wave-1 result district_id mismatch: got {raw.get('district_id')!r}, "
            f"expected {district['district_id']!r}"
        )
    if raw.get("domain", "") != district.get("domain", ""):
        raise SystemExit(
            f"Wave-1 result domain mismatch for {district['district_id']}: got "
            f"{raw.get('domain')!r}, expected {district.get('domain', '')!r}"
        )
    return raw


def merge_wave1(roster: list, raw: dict, domain: str) -> list:
    """Attach each school's raw Wave-1 URLs (keyed by school_id) onto the roster built from
    the batch, then gate them. A school in the roster with no matching entry in the
    subagent's result is treated as zero URLs found, not silently dropped."""
    by_id = {s["school_id"]: s.get("urls", []) for s in raw.get("schools", [])}
    for r in roster:
        urls = by_id.get(r["school_id"], [])
        r["wave1_raw_urls"] = urls
        r["wave1_gated"] = gate_urls(urls, domain)
        r["wave2_invoked"] = False
        r["wave2_raw_urls"] = []
        r["wave2_gated"] = []
    return roster


def residual_schools(roster: list) -> list:
    """Schools with zero KEPT candidates after gating Wave 1 -- the only schools Wave 2 is
    allowed to touch. A district where Wave 1 + gating satisfied every school must skip
    Wave 2 entirely (no OpenRouter call at all), not just narrow its scope to nothing."""
    return [r for r in roster if not any(g["kept"] for g in r["wave1_gated"])]


def run_wave1(roster: list, domain: str, search_fn) -> list:
    """Deterministic Wave 1 for the SERP architecture: call search_fn(query, domain) per school (a
    SERP provider -- brightdata_search primary, serper_search/openrouter_search alternates), gate the
    URLs, init the Wave-2 fields empty. There is NO agent result to validate here (the provider
    returns URLs directly), so this replaces the merge_wave1/validate_wave1_result handoff of the
    retired agent-in-the-loop model. A billing/auth SystemExit propagates (halts the run, like a
    reconcile CONTROL FAILURE); any other per-school error degrades to zero URLs (logged)."""
    for r in roster:
        try:
            urls = search_fn(r["query"], domain)
        except SystemExit:
            raise
        except Exception as e:
            urls = []
            print(f"   [w1/{r['school'][:24]}] ERR {str(e)[:60]}")
        r["wave1_raw_urls"] = urls
        r["wave1_gated"] = gate_urls(urls, domain)
        r["wave2_invoked"] = False
        r["wave2_raw_urls"] = []
        r["wave2_gated"] = []
    return roster


def run_wave2(residual: list, domain: str, search_fn=openrouter_search) -> None:
    """Mutates each residual row in place. Script-driven, never a subagent -- a SERP/API call, not
    agent judgment. `search_fn` is the provider (default openrouter_search for back-compat; the SERP
    runner passes serper_search). A billing/auth SystemExit propagates; other errors degrade to zero
    URLs for that school."""
    for r in residual:
        r["wave2_invoked"] = True
        try:
            urls = search_fn(r["query"], domain)
        except SystemExit:
            raise
        except Exception as e:
            urls = []
            print(f"   [w2/{r['school'][:24]}] ERR {str(e)[:60]}")
        r["wave2_raw_urls"] = urls
        r["wave2_gated"] = gate_urls(urls, domain)


def school_outcome(row: dict) -> str:
    kept_w1 = any(g["kept"] for g in row["wave1_gated"])
    kept_w2 = any(g["kept"] for g in row["wave2_gated"])
    return "found" if (kept_w1 or kept_w2) else "manual_flag"


def district_outcome(roster: list) -> str:
    outcomes = {school_outcome(r) for r in roster}
    if outcomes == {"found"}:
        return "found_all"
    if outcomes == {"manual_flag"}:
        return "manual_flag_all"
    return "found_partial"


def _normalize_url(u: str) -> str:
    return host_of(u) + urlparse(u).path.rstrip("/")


def flatten(roster: list) -> list:
    """Dedup kept candidates across schools by normalized URL -- collapses a hub page into
    one shared capture target automatically, independent of any topology label (topology
    classification itself was dropped -- see ACQUISITION_PIPELINE.md Stage 2)."""
    dedup = {}
    for r in roster:
        for tool, gated in (("claude", r["wave1_gated"]), ("openrouter", r["wave2_gated"])):
            for g in gated:
                if not g["kept"]:
                    continue
                k = _normalize_url(g["url"])
                entry = dedup.setdefault(k, {"url": g["url"], "schools": [], "tools": []})
                if r["school"] not in entry["schools"]:
                    entry["schools"].append(r["school"])
                if tool not in entry["tools"]:
                    entry["tools"].append(tool)
    return list(dedup.values())


def write_discovery(district: dict, roster: list, batch_id: str) -> Path:
    """Single atomic write -- discovery.json (full per-school audit trail) + candidates.json
    (flattened, capture-ready). NEVER overwritten in place: an existing discovery.json (a
    deliberate, manual redo -- Stage 2 never triggers this on its own) is renamed aside
    with a timestamp suffix first, preserving the full attempt history -- data/raw/ is
    write-once in spirit (see ACQUISITION_PIPELINE.md Stage 2 and CLAUDE.md's "never
    modify data/raw/" rule)."""
    d = lea_dir(district["district_id"], district["name"])
    d.mkdir(parents=True, exist_ok=True)
    disc_path, cand_path = d / "discovery.json", d / "candidates.json"
    if disc_path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        disc_path.rename(d / f"discovery.{ts}.json")
        if cand_path.exists():
            cand_path.rename(d / f"candidates.{ts}.json")

    discovery_doc = {
        "district_id": district["district_id"],
        "name": district["name"],
        "state": district["state"],
        "domain": district.get("domain", ""),
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schools": [
            {
                "school_id": r["school_id"],
                "school": r["school"],
                "bands": r["bands"],
                "query": r["query"],
                "wave1_raw_urls": r["wave1_raw_urls"],
                "wave1_gated": r["wave1_gated"],
                "wave2_invoked": r["wave2_invoked"],
                "wave2_raw_urls": r["wave2_raw_urls"],
                "wave2_gated": r["wave2_gated"],
                "outcome": school_outcome(r),
            }
            for r in roster
        ],
    }
    disc_path.write_text(json.dumps(discovery_doc, indent=2))

    candidates_doc = {
        "district_id": district["district_id"],
        "name": district["name"],
        "domain": district.get("domain", ""),
        "candidates": flatten(roster),
    }
    cand_path.write_text(json.dumps(candidates_doc, indent=2))
    return d


def finish_district(district: dict, roster: list, batch_id: str, registry: dict) -> str:
    """Single registry write per district, at actual completion -- never from a subagent,
    never an interim 'started' marker (there's nothing meaningful to reconcile against a
    half-finished state, since the file write only happens once everything is assembled)."""
    ddir = write_discovery(district, roster, batch_id)
    outcome = district_outcome(roster)
    DS.record_stage(
        registry, district["district_id"], district["name"], district["state"],
        stage=2, stage_name="discover", outcome=outcome, batch_id=batch_id,
    )
    # Project this district's funnel into the live DB cache so the console reads fresh rows without
    # waiting for a Stage-5 ingest. Best-effort: the disk JSON + state_event are the durable record.
    CI.cache_discovery(ddir)
    return outcome


def main():
    ap = argparse.ArgumentParser(description="Stage 2 (Discover), deterministic half")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("reconcile")
    p.add_argument("batch")

    p = sub.add_parser("roster")
    p.add_argument("batch")
    p.add_argument("district_id")

    p = sub.add_parser("finish")
    p.add_argument("batch")
    p.add_argument("district_id")
    p.add_argument("wave1_result")

    a = ap.parse_args()
    batch = load_batch(a.batch)

    if a.cmd == "reconcile":
        registry = DS.load()
        todo, skipped = reconcile(batch, registry)
        DS.save(registry)
        print(f"{batch['batch_id']}: {len(todo)} to discover, {len(skipped)} already done (skipped)")
        for d in skipped:
            print(f"  skip [{d['state']}] {d['name']} ({d['district_id']})")
        for d in todo:
            print(f"  todo [{d['state']}] {d['name']} ({d['district_id']})")

    elif a.cmd == "roster":
        district = find_district(batch, a.district_id)
        roster = build_roster(district)
        print(json.dumps({"district_id": district["district_id"], "name": district["name"],
                           "domain": district.get("domain", ""), "schools": roster}, indent=2))

    elif a.cmd == "finish":
        district = find_district(batch, a.district_id)
        roster = build_roster(district)
        raw = json.loads(Path(a.wave1_result).read_text())
        validate_wave1_result(raw, district)
        roster = merge_wave1(roster, raw, district.get("domain", ""))
        residual = residual_schools(roster)
        if residual:
            print(f"  wave 2: {len(residual)}/{len(roster)} schools residual after Wave 1 + gating")
            run_wave2(residual, district.get("domain", ""))
        else:
            print(f"  wave 2: skipped, Wave 1 + gating satisfied all {len(roster)} schools")
        registry = DS.load()
        outcome = finish_district(district, roster, batch["batch_id"], registry)
        DS.save(registry)
        print(f"{district['district_id']} {district['name']}: {outcome}")


if __name__ == "__main__":
    main()
