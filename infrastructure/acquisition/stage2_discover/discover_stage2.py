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
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from infrastructure.acquisition.common import batch_guard as BG
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import config_loader as CFG
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import paths

from infrastructure.acquisition.common.discover import host_of, gate, is_scoping_domain, slugify
from infrastructure.acquisition.common import timeutil as TU

# Anchored to the repo (paths.RAW_CAPTURES), never a CWD-relative literal -- this script and the
# governance server (which reads the same discovery.json/candidates.json) must agree on the location
# regardless of launch directory. (The gate@1 create 500'd on exactly this CWD-relative class of bug.)
RAW_DIR = paths.RAW_CAPTURES
BANDS = ("elementary", "middle", "high")


def lea_dir(district_id: str, name: str) -> Path:
    return RAW_DIR / f"{district_id}_{slugify(name)}"


def query_for(school: str, state: str) -> str:
    return f"{school} {state} bell schedule start and end times"


def differentiated_queries(school: str, state: str) -> list:
    """The differentiated SERP query set for a 7->2 REDISCOVER follow-up (#160): materially different
    phrasings from the default `query_for` wave-1 query, rendered per school. A 7->2 round casts the
    WHOLE set at once (cheap SERP, max recall in one round). Config-as-data
    (`common/config/stage2_query_templates.json`) so it's tunable without code and the judge can later
    feed the same seam. Order preserved (config order); templates use only {school} + {state}.

    FOUNDATION ONLY (Chunk 2, epic #163): NOT yet consumed by discovery — the follow-up builder threads
    these in and Stage-2 discovery consumes them in Chunk 4."""
    return [tmpl.format(school=school, state=state)
            for tmpl in CFG.values("stage2_query_templates")]


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
    multiple bands appears once, with all its bands listed). Each row carries `query` (the default
    wave-1 query, kept for provenance + Wave 2) and `queries` (the list Wave 1 actually runs).

    #160: a follow-up band tagged `query_strategy=='widen_queries'` (its untried schools exhausted)
    casts the WIDER net — the school's `queries` gain the differentiated SERP set. `new_schools`
    (untried schools to try) and first-run batches keep the single default query."""
    by_school, widen = {}, set()
    for band in BANDS:
        bd = district.get("schools_by_band", {}).get(band, {})
        strat = bd.get("query_strategy")
        for s in bd.get("schools", []):
            row = by_school.setdefault(
                s["school_id"], {"school_id": s["school_id"], "school": s["name"], "bands": []}
            )
            if band not in row["bands"]:
                row["bands"].append(band)
            if strat == "widen_queries":
                widen.add(s["school_id"])
    roster = list(by_school.values())
    state = district["state"]
    for r in roster:
        r["query"] = query_for(r["school"], state)
        r["queries"] = [r["query"]]
        if r["school_id"] in widen:
            r["queries"] += differentiated_queries(r["school"], state)
    return roster


def reconcile(batch: dict, registry: dict) -> tuple[list, list]:
    """Filesystem is truth. For every district in the batch: if discovery.json already
    exists on disk, reconcile the registry up to match (skip -- already done, never redo
    automatically). If the registry claims furthest_stage>=2 but the file does NOT exist,
    that's a control failure, not routine drift -- halt the entire run rather than risk
    propagating whatever caused it to other districts. Returns (todo, skipped).

    FOLLOW-UP batches are the sanctioned exception (issue #174): a 7->2/7->3/7->1 follow-up
    exists precisely to REDO discovery for districts we already discovered, so 'discovery.json
    exists' must not skip them -- every included district is todo, and the redo merges with the
    prior round downstream (write_discovery merge mode) instead of replacing it. The
    registry-ahead-of-disk control failure still halts (a follow-up district missing its prior
    discovery.json is exactly as alarming as in a first run)."""
    todo, skipped = [], []
    followup = batch.get("batch_type") == "follow-up"
    for d in batch["districts"]:
        did = d["district_id"]
        done_on_disk = (lea_dir(did, d["name"]) / "discovery.json").exists()
        rec = registry["districts"].get(did)
        reg_says_done = rec is not None and rec.get("furthest_stage", 0) >= 2
        if not done_on_disk and reg_says_done:
            raise SystemExit(
                f"CONTROL FAILURE: registry says {did} ({d['name']}) reached Stage 2+ but "
                f"{lea_dir(did, d['name']) / 'discovery.json'} does not exist. Stopping the "
                f"entire run -- investigate before re-running anything in this batch."
            )
        if followup:
            todo.append(d)          # a follow-up IS a deliberate redo -- never skip on disk state
            continue
        if done_on_disk and not reg_says_done:
            DS.record_stage(
                registry, did, d["name"], d["state"], stage=2, stage_name="discover",
                outcome="reconciled_from_disk", batch_id=batch.get("batch_id"),
            )
            skipped.append(d)
        elif done_on_disk and reg_says_done:
            skipped.append(d)
        else:                       # not done_on_disk, not reg_says_done (the raise above covered
            todo.append(d)          # the registry-ahead-of-disk case for every batch type)
    return todo, skipped


def gate_urls(urls: list, domain: str) -> list:
    """The same on-domain/CMS-slug/news-aggregator gate as the legacy district-level
    discover.py, applied per-school. Returns [{"url", "kept", "reason"}, ...].

    #229 defense-in-depth (PR #242 review): Stage 2 FAILS CLOSED on a non-scoping domain instead
    of trusting Stage 1's admission guard. A blank domain used to flip gate() to its UNSCOPED
    branch (keep everything -> the Millard national-scope contamination, #227); now every URL is
    rejected with an explicit reason. This is the single gating chokepoint for all waves, so a
    blank/junk domain reaching Stage 2 through ANY path (manual DB edit, a future batch builder,
    a remediation script) can no longer contaminate — the run visibly yields nothing instead."""
    if not is_scoping_domain(domain):
        return [{"url": u, "kept": False, "reason": "no-scoping-domain — unscoped discovery refused (#229)"}
                for u in urls]
    slug = domain.split(".")[0]
    out = []
    for u in urls:
        ok, why = gate(u, domain, slug, True)
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
        # the agent-in-the-loop Wave 1 IS a Claude WebSearch subagent -- record the real provider
        r["wave1_provider"] = "claude_websearch"
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
    SERP provider -- brightdata_search primary via the headless failover cascade, serper_search the
    alternate), gate the URLs, init the Wave-2 fields empty. There is NO agent result to validate
    here (the provider returns URLs directly), so this replaces the merge_wave1/validate_wave1_result
    handoff of the retired agent-in-the-loop model. A billing/auth SystemExit propagates (halts the
    run, like a reconcile CONTROL FAILURE); any other per-school error degrades to zero URLs (logged).

    Provenance (issue #30): search_fn may return either a bare url list or a
    (provider_name, urls) tuple -- the failover cascade returns the tuple, because only IT knows
    which provider actually served the query. A bare list falls back to the fn's `provider_name`
    attribute. The name lands in `wave1_provider` and flows through flatten() into candidates.json."""
    default_provider = getattr(search_fn, "provider_name", "unknown_wave1")
    for r in roster:
        provider = default_provider   # NOTE: with multiple queries (#160), the LAST query's provider
        seen, urls = set(), []        # wins wave1_provider — per-school provenance, lossy on mid-set failover
        # run every query for the school (#160: a widen-strategy follow-up school has the default +
        # the differentiated set), UNIONing the URLs (order-preserving dedup).
        for q in r.get("queries") or [r["query"]]:
            try:
                res = search_fn(q, domain)
                provider, qurls = res if isinstance(res, tuple) else (default_provider, res)
            except SystemExit:
                raise
            except Exception as e:
                qurls = []
                print(f"   [w1/{r['school'][:24]}] ERR {str(e)[:60]}")
            for u in qurls:
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
        r["wave1_raw_urls"] = urls
        r["wave1_provider"] = provider
        r["wave1_gated"] = gate_urls(urls, domain)
        r["wave2_invoked"] = False
        r["wave2_raw_urls"] = []
        r["wave2_gated"] = []
    return roster


def run_wave2(residual: list, domain: str, search_fn) -> None:
    """Mutates each residual row in place. Script-driven, never a subagent -- a SERP/API call, not
    agent judgment. `search_fn` is the provider and is REQUIRED (issue #41: the old default was the
    retired openrouter_search, ~$27/1K -- a silent default must never be able to reach a retired
    paid provider). A billing/auth SystemExit propagates; other errors degrade to zero URLs for
    that school. The provider name is recorded per row (issue #30)."""
    provider = getattr(search_fn, "provider_name", "unknown_wave2")
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
        r["wave2_provider"] = provider
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
    classification itself was dropped -- see ACQUISITION_PIPELINE.md Stage 2).

    `tools[]` records the REAL provider that served each kept URL (issue #30): Wave 1 =
    "brightdata"/"serper" (whichever the failover cascade actually used), Wave 2 =
    "claude_websearch" -- read from the per-row `wave1_provider`/`wave2_provider` set by
    run_wave1/run_wave2/merge_wave1. The list flows into candidates.json -> the DB cache ->
    Stage-5 candidate_tools_json, so the names must be true provenance.

    BACKFILL NOTE (issue #30): batches discovered BEFORE this fix (<= batch_00007) carry the
    retired-architecture labels "claude" (really Bright Data/Serper Wave 1) and "openrouter"
    (really Claude WebSearch Wave 2) in candidates.json/the DB cache. Deliberately NOT
    backfilled by script -- the mislabels are documented in the issue; rows with the old
    labels are simply pre-fix vintage."""
    dedup = {}
    for r in roster:
        for tool, gated in ((r.get("wave1_provider") or "unknown_wave1", r["wave1_gated"]),
                            (r.get("wave2_provider") or "unknown_wave2", r["wave2_gated"])):
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


def write_discovery(district: dict, roster: list, batch_id: str, *, merge: bool = False) -> Path:
    """Single atomic write -- discovery.json (full per-school audit trail) + candidates.json
    (flattened, capture-ready). NEVER overwritten in place: an existing discovery.json (a
    deliberate redo -- a follow-up batch, or a manual one) is renamed aside with a timestamp
    suffix first, preserving the full attempt history -- data/raw/ is write-once in spirit
    (see ACQUISITION_PIPELINE.md Stage 2 and CLAUDE.md's "never modify data/raw/" rule).

    `merge=True` (a follow-up redo, issue #174): the new docs are the UNION of the prior round
    and this one, never just this round's slice -- Stage 5's ingest reads ONLY the current
    manifests (per-district delete + rebuild), so a slice-only manifest would ERASE the
    district's existing records (and orphan their gate@5 labels) at the next ingest.
      - discovery.json schools: this round's entry REPLACES the same school's old entry
        (latest attempt wins); schools not re-queried this round carry over verbatim -- so
        roster_norm (the signal layer's roster) stays complete.
      - candidates.json: prior candidates verbatim + this round's new URLs appended (deduped
        by normalized URL) -- the manifest stays the district's complete capture plan."""
    d = lea_dir(district["district_id"], district["name"])
    d.mkdir(parents=True, exist_ok=True)
    disc_path, cand_path = d / "discovery.json", d / "candidates.json"

    old_schools, old_candidates = [], []
    if merge and disc_path.exists():
        old_schools = (json.loads(disc_path.read_text()) or {}).get("schools", [])
        if cand_path.exists():
            old_candidates = (json.loads(cand_path.read_text()) or {}).get("candidates", [])

    if disc_path.exists():
        ts = TU.fs_stamp()
        disc_path.rename(d / f"discovery.{ts}.json")
        if cand_path.exists():
            cand_path.rename(d / f"candidates.{ts}.json")

    new_schools = [
        {
            "school_id": r["school_id"],
            "school": r["school"],
            "bands": r["bands"],
            "query": r["query"],
            "wave1_raw_urls": r["wave1_raw_urls"],
            "wave1_provider": r.get("wave1_provider"),
            "wave1_gated": r["wave1_gated"],
            "wave2_invoked": r["wave2_invoked"],
            "wave2_raw_urls": r["wave2_raw_urls"],
            "wave2_provider": r.get("wave2_provider"),
            "wave2_gated": r["wave2_gated"],
            "outcome": school_outcome(r),
        }
        for r in roster
    ]
    if old_schools:
        new_by_id = {e["school_id"]: e for e in new_schools}
        schools = [new_by_id.pop(s["school_id"], s) for s in old_schools]
        schools += [e for e in new_schools if e["school_id"] in new_by_id]
    else:
        schools = new_schools

    discovery_doc = {
        "district_id": district["district_id"],
        "name": district["name"],
        "state": district["state"],
        "domain": district.get("domain", ""),
        "batch_id": batch_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schools": schools,
    }
    disc_path.write_text(json.dumps(discovery_doc, indent=2))

    new_candidates = flatten(roster)
    if merge:
        for c in new_candidates:      # inline round provenance: which batch discovered this URL
            c["batch_id"] = batch_id  # (old candidates keep their entries verbatim, unstamped)
    if old_candidates:
        have_old = {_normalize_url(c["url"]) for c in old_candidates}
        candidates = old_candidates + [c for c in new_candidates
                                       if _normalize_url(c["url"]) not in have_old]
    else:
        candidates = new_candidates
    # #161: seed URLs (7->3 recapture directives carried on the follow-up batch) are pre-specified
    # capture targets — inject them into the candidate list (deduped by normalized URL, tool
    # 'seed_7to3') so Stage 3 captures them through the existing candidates.json pipe, no discovery and
    # no Stage-3 change. Dormant today (no producer of seed_urls), wired for when the judge feeds them.
    have = {_normalize_url(c["url"]) for c in candidates}
    for u in district.get("seed_urls") or []:
        if _normalize_url(u) not in have:
            candidates.append({"url": u, "schools": [], "tools": ["seed_7to3"]})
            have.add(_normalize_url(u))
    candidates_doc = {
        "district_id": district["district_id"],
        "name": district["name"],
        "domain": district.get("domain", ""),
        "candidates": candidates,
    }
    cand_path.write_text(json.dumps(candidates_doc, indent=2))
    return d


def finish_district(district: dict, roster: list, batch_id: str, registry: dict,
                    *, merge: bool = False) -> str:
    """Single registry write per district, at actual completion -- never from a subagent,
    never an interim 'started' marker (there's nothing meaningful to reconcile against a
    half-finished state, since the file write only happens once everything is assembled).
    `merge=True` = a follow-up redo (issue #174): write_discovery unions with the prior round."""
    ddir = write_discovery(district, roster, batch_id, merge=merge)
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
    # #168/#206 review: this legacy CLI writes real state (discovery.json + state_events via `finish`,
    # registry reconciles) — refuse a terminal abandoned batch exactly like headless.run_batch does,
    # else an abandoned batch's schools re-enter the funnel while excluded from the attempted-set (#162).
    with gdb.session_scope() as _con:
        BG.assert_runnable(_con, batch["batch_id"])

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
            # Issue #41: run_wave2's old default was the RETIRED openrouter_search (~$27/1K).
            # The decided Wave-2 provider (Claude WebSearch) needs the headless runner's
            # subprocess context, so this legacy CLI path refuses instead of silently paying.
            raise SystemExit(
                f"finish: {len(residual)}/{len(roster)} schools residual after Wave 1 + gating -- "
                f"the OpenRouter Wave-2 default is retired (issue #41) and the decided Wave-2 "
                f"provider (Claude WebSearch) runs only in the headless runner. Use the console "
                f"or: python3 -m infrastructure.acquisition.stage2_discover.headless run <batch>"
            )
        print(f"  wave 2: skipped, Wave 1 + gating satisfied all {len(roster)} schools")
        registry = DS.load()
        outcome = finish_district(district, roster, batch["batch_id"], registry,
                                  merge=batch.get("batch_type") == "follow-up")
        DS.save(registry)
        print(f"{district['district_id']} {district['name']}: {outcome}")


if __name__ == "__main__":
    main()
