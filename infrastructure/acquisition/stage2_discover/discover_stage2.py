"""Stage 2 (Discover) of the bell-schedule acquisition pipeline -- the deterministic half.

Reads Stage 1's batch JSON directly (schools_by_band, domain) -- NEVER recomputes band
membership from raw NCES CSV (see ACQUISITION_PIPELINE.md Stage 2; that's the exact bug
class Stage 1's gate@1 review spent a full day fixing -- recomputing here would silently
discard every fix). Orchestration is a fully deterministic SERP cascade (REQ-104,
`headless.py`): Wave 1 = Bright Data SERP with Serper failover, Wave 2 = Claude WebSearch
on the genuine residual only. No agent in the loop -- the retired agent-in-the-loop Wave 1
(and its stage2-discover skill) is documented in STAGE2_DISCOVER_DESIGN.md §5 history.
This module does all gating, Wave 2 scoping, flattening, writing, and registry bookkeeping.

Filesystem is authoritative: a district's discovery.json existing in
data/raw/lea-website-captures/<id>_<slug>/ IS "Stage 2 done" -- the registry is a cache of
that fact, reconciled FROM disk, never the reverse. See reconcile().

Usage:
  discover_stage2.py reconcile <batch.json>
  discover_stage2.py roster    <batch.json> <district_id>
  discover_stage2.py finish    <batch.json> <district_id> <wave1_result.json>
"""
import argparse
import collections
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from infrastructure.acquisition.common import batch_guard as BG
from infrastructure.acquisition.common import batch_types as BT
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import config_loader as CFG
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common.discover import (NEWS_AGG, _host_matches,
                                                            derive_domain)
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


def geo_queries(school: str, state: str, city: str, zipc: str, *, widened: bool = False) -> list:
    """The GEO-scoped rendering (#164): the SAME vocabulary as domain-scoped discovery — one
    vocabulary source, two scoping forms (the REQ-089 anti-drift rule) — with the district's
    NCES CCD geo tokens appended and NO site: composition downstream (the caller passes a blank
    dhost). `widened=False` = the standard wave-1 vocabulary (Path 1 first-runs, the first 5->1
    loop); `widened=True` adds the differentiated template set (the second 5->1 loop, the second
    7->1 loop). Geography disambiguates common school names nationally (the #227 class); the
    derive-and-re-gate in the geo run is the containment, not the query alone."""
    geo = " ".join(t for t in ((city or "").strip(), (zipc or "").strip()) if t)
    vocab = [query_for(school, state)]
    if widened:
        vocab += differentiated_queries(school, state)
    return [f"{q} {geo}".strip() for q in vocab]


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


def build_roster(district: dict, *, geo: bool = False) -> list:
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
    geo_fields = district.get("geo") if geo else None
    for r in roster:
        r["query"] = query_for(r["school"], state)
        if geo:
            # #164 geo mode: the SAME vocabulary, geo-rendered (city/zip tokens, no site: at the
            # provider — the caller passes a blank dhost). Widen-strategy schools get the widened
            # vocabulary geo-rendered too.
            r["queries"] = geo_queries(r["school"], state, (geo_fields or {}).get("city", ""),
                                       (geo_fields or {}).get("zip", ""),
                                       widened=r["school_id"] in widen)
        else:
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
    prior round downstream (write_discovery merge mode) instead of replacing it.

    The registry-ahead-of-disk control failure halts UNLESS the district has an on-disk
    decontamination restore point (#572): remediate_contamination deliberately removes a
    contaminated district's artifacts while PRESERVING its state history (auditability), so
    registry-ahead-of-disk is that path's expected, receipted end state — the district simply
    rediscovers fresh (write_discovery merge mode finds no prior file and writes anew). A
    missing discovery.json with NO remediation receipt still halts the entire run."""
    todo, skipped = [], []
    followup = BT.redoes_attempted(batch)
    for d in batch["districts"]:
        did = d["district_id"]
        done_on_disk = (lea_dir(did, d["name"]) / "discovery.json").exists()
        rec = registry["districts"].get(did)
        reg_says_done = rec is not None and rec.get("furthest_stage", 0) >= 2
        if not done_on_disk and reg_says_done:
            receipt = DS.remediation_receipt(did)
            if receipt is not None:
                print(f"  [reconcile] {did} ({d['name']}): registry ahead of disk, EXPLAINED by "
                      f"the decontamination restore point {receipt.name} — rediscovering fresh")
                todo.append(d)
                continue
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

    Provenance (issue #30, #341): search_fn may return either a bare url list or a
    (provider_name, urls) tuple -- the failover cascade returns the tuple, because only IT knows
    which provider actually served the query. A bare list falls back to the fn's `provider_name`
    attribute. Each URL keeps the provider that FIRST surfaced it (a `provider` key on its
    wave1_gated entry, preferred by flatten()); `wave1_provider` is the last SUCCESSFULLY-
    answering query's provider (a scalar summary -- a failed final query does not overwrite
    it, and cannot masquerade as having served) and `wave1_providers` lists every provider
    that successfully answered a query for the school, INCLUDING legitimate zero-URL answers
    (a "found nothing" search is service, not failure) -- so a mid-set failover (#160
    multi-query) no longer loses per-URL attribution or undercounts the audit trail."""
    default_provider = getattr(search_fn, "provider_name", "unknown_wave1")
    for r in roster:
        provider = default_provider
        seen, urls, providers, provider_by_url = set(), [], [], {}
        # run every query for the school (#160: a widen-strategy follow-up school has the default +
        # the differentiated set), UNIONing the URLs (order-preserving dedup).
        for q in r.get("queries") or [r["query"]]:
            try:
                res = search_fn(q, domain)
                provider, qurls = res if isinstance(res, tuple) else (default_provider, res)
            except SystemExit:
                raise
            except Exception as e:
                qurls = None   # None = the query FAILED; [] = it ran and found nothing
                print(f"   [w1/{r['school'][:24]}] ERR {str(e)[:60]}")
            if qurls is not None and provider not in providers:
                providers.append(provider)   # an empty-but-successful answer still counts as serving
            for u in qurls or []:
                if u not in seen:
                    seen.add(u)
                    urls.append(u)
                    provider_by_url[u] = provider
        r["wave1_raw_urls"] = urls
        r["wave1_provider"] = provider
        r["wave1_providers"] = providers
        r["wave1_gated"] = gate_urls(urls, domain)
        for g in r["wave1_gated"]:
            g["provider"] = provider_by_url.get(g["url"], provider)
        r["wave2_invoked"] = False
        r["wave2_raw_urls"] = []
        r["wave2_gated"] = []
    return roster


def apply_geo_derivation(roster: list) -> tuple:
    """#164 geo mode, between wave 1 and wave 2: an un-scoped wave 1 leaves every school's
    wave1_gated FAIL-CLOSED (gate_urls refuses everything on a blank domain — the correct
    no-derivation outcome). This tallies the RAW result hosts across all schools (news/aggregators
    excluded — they never scope), derives the majority host (discover.derive_domain: family-merged,
    >=40% share AND >=3 distinct schools), and on success RE-GATES every school's raw URLs against
    the derived host through the normal scoped gate, preserving per-URL provider attribution.
    Returns (derived_host | None, receipt) — the receipt lands in discovery.json as the
    `geo_discovery` block, and the derived host is the `discovered_domain` PROPOSAL a human
    confirms (never an automatic write; NCES data is never touched)."""
    tally: dict = {}
    for r in roster:
        for u in r.get("wave1_raw_urls", []):
            h = host_of(u)
            if not h or any(_host_matches(h, n) for n in NEWS_AGG):
                continue
            slot = tally.setdefault(h, {"n": 0, "schools": set()})
            slot["n"] += 1
            slot["schools"].add(r["school_id"])
    derived, receipt = derive_domain(tally)
    if derived:
        for r in roster:
            provider_by_url = {g["url"]: g.get("provider") for g in r.get("wave1_gated", [])}
            r["wave1_gated"] = gate_urls(r.get("wave1_raw_urls", []), derived)
            for g in r["wave1_gated"]:
                if provider_by_url.get(g["url"]):
                    g["provider"] = provider_by_url[g["url"]]
    return derived, receipt


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
    "claude_websearch" -- read from each gated entry's own `provider` (#341, first provider
    to surface the URL), falling back to the per-row `wave1_provider`/`wave2_provider` for
    pre-#341 rows and the legacy merge_wave1 path. The list flows into candidates.json ->
    the DB cache -> Stage-5 candidate_tools_json, so the names must be true provenance.

    BACKFILL NOTE (issue #30): batches discovered BEFORE this fix (<= batch_00007) carry the
    retired-architecture labels "claude" (really Bright Data/Serper Wave 1) and "openrouter"
    (really Claude WebSearch Wave 2) in candidates.json/the DB cache. Deliberately NOT
    backfilled by script -- the mislabels are documented in the issue; rows with the old
    labels are simply pre-fix vintage."""
    dedup = {}
    for r in roster:
        for fallback_tool, gated in ((r.get("wave1_provider") or "unknown_wave1", r["wave1_gated"]),
                                     (r.get("wave2_provider") or "unknown_wave2", r["wave2_gated"])):
            for g in gated:
                if not g["kept"]:
                    continue
                tool = g.get("provider") or fallback_tool
                k = _normalize_url(g["url"])
                entry = dedup.setdefault(k, {"url": g["url"], "schools": [], "tools": []})
                if r["school"] not in entry["schools"]:
                    entry["schools"].append(r["school"])
                if tool not in entry["tools"]:
                    entry["tools"].append(tool)
    return list(dedup.values())


# Crash-safe JSON write (#265) -- the shared common/paths helper (review: this was the third
# hand-rolled copy of the tmp+os.replace pattern; district_status.export_status and
# batch_store.write_receipt consolidate onto the same helper post-merge). Kept as a module
# global so tests can monkeypatch the write for order-spying.
_atomic_write_json = paths.atomic_write_json


def _prior_doc(d: Path, live: Path, stem: str) -> dict:
    """The most recent prior version of a manifest: the live file if present, else the newest
    timestamped aside (`<stem>.<ts>.json`). The aside fallback is crash-orphan tolerance
    (review finding on #265): a prior attempt may have renamed the old files aside and then
    died between the two writes, leaving e.g. candidates.json present (already the union)
    but discovery.json absent -- the prior schools then live only in the newest aside."""
    if live.exists():
        return json.loads(live.read_text()) or {}
    asides = sorted(d.glob(f"{stem}.*.json"))   # fs_stamp is lexicographically sortable
    if asides:
        return json.loads(asides[-1].read_text()) or {}
    return {}


def kept_in(school_entry: dict) -> int:
    """Candidates one school entry actually KEPT this round (both waves). The number that matters
    downstream -- raw results found are not a capture plan, gated keeps are."""
    return (sum(1 for g in school_entry.get("wave1_gated", []) or [] if g.get("kept"))
            + sum(1 for g in school_entry.get("wave2_gated", []) or [] if g.get("kept")))


def rung_regression(prior_schools: list, new_schools: list) -> dict | None:
    """#672 criterion 1: did THIS escalation rung keep FEWER candidates than the rung before it?

    Returns a receipt block when it did, else None. Escalation is assumed monotonic in recall and
    is not: the widened vocabulary multiplies total results, which is a DENOMINATOR increase for
    the share-based geo derivation, so a rung meant as a second chance can dilute a host the prior
    rung successfully derived and fail closed with nothing (Wyandanch `3631800`, batch_00034 ->
    batch_00035: 10 kept -> 0, raw 36 -> 109, share 0.400 -> 0.179 -- measured in
    production-quality-control-research/2026-08-21-geo-ladder-regression-measure.py).

    Scoped to the schools this rung actually RE-QUERIED. A follow-up merge unions the prior round
    into the doc, so comparing whole documents could never regress -- the union is >= the prior by
    construction, which is exactly the kind of comparison-with-itself that cannot fail (the repo's
    Pass-B lesson). Comparing the re-queried subset is the question the criterion is about.

    Detection ONLY -- this records that the rung did worse, it does not change what the rung kept.
    Whether a diluted rung should fall back to the previous rung's derived host is a scoping-policy
    decision (it would gate on an UNCONFIRMED discovered_domain proposal) and is deliberately not
    made here."""
    if not prior_schools or not new_schools:
        return None
    # #878: a dict comprehension keyed on school_id would silently keep only the LAST entry if the
    # prior doc carried the same school twice (a stale aside, a roster correction that reused an
    # ID), producing a wrong kept_before and an unauditable verdict. AGGREGATE instead of
    # overwriting — the honest answer to "what did the prior rung keep for this school" is the sum
    # across its entries — and SURFACE the anomaly in the receipt. Deliberately not a raise: this
    # is a reporting function called mid-batch, and halting a live capture run over a duplicate in
    # a historical manifest would trade a cosmetic problem for a real one. Auditability is served
    # by recording it (commandment #1), not by crashing.
    prior_kept, dupes = {}, collections.Counter()
    for s in prior_schools:
        sid = s.get("school_id")
        if not sid:
            continue
        dupes[sid] += 1
        prior_kept[sid] = prior_kept.get(sid, 0) + kept_in(s)
    requeried = [s for s in new_schools if s.get("school_id") in prior_kept]
    if not requeried:
        return None
    before = sum(prior_kept[s["school_id"]] for s in requeried)
    after = sum(kept_in(s) for s in requeried)
    if after >= before:
        return None
    out = {
        "kept_before": before,
        "kept_after": after,
        "n_schools_compared": len(requeried),
        # The schools this rung took from "had candidates" to "has none" -- the ones that flip to
        # manual_flag purely because the escalation ran.
        "schools_zeroed": sorted(s["school_id"] for s in requeried
                                 if prior_kept[s["school_id"]] > 0 and kept_in(s) == 0),
    }
    duplicated = sorted(sid for sid, n in dupes.items() if n > 1)
    if duplicated:
        out["duplicate_prior_school_ids"] = duplicated
    return out


def write_discovery(district: dict, roster: list, batch_id: str, *, merge: bool = False,
                    geo_receipt: dict | None = None, docs_out: dict | None = None) -> Path:
    """Write discovery.json (full per-school audit trail) + candidates.json (flattened,
    capture-ready). Both writes are atomic (temp + os.replace, #265), and candidates.json is
    written FIRST: reconcile() keys "Stage 2 done" on discovery.json existing, so a crash
    between the two writes must leave the district looking not-done (re-runnable) rather than
    done-with-no-capture-plan. NEVER overwritten in place: an existing discovery.json (a
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

    # #672 criterion 1: the prior rung's schools, read UNCONDITIONALLY (not only on a merge) and
    # BEFORE the rename-aside below, so a regression is detectable on every re-run of a district --
    # a domain-scoped rung can lose keepers too (measured: `0101920` batch_00013 -> batch_00026,
    # 322 -> 309, no geo derivation involved at all).
    # #877: ONE read. This used to parse the same discovery.json twice on every merge — once here
    # and once inside the `if merge:` block — which on a large district means re-parsing the full
    # per-school audit trail (every school's raw URL list) for nothing.
    prior_disc = _prior_doc(d, disc_path, "discovery")
    prior_schools_for_compare = prior_disc.get("schools", [])

    old_schools, old_candidates, old_geo = [], [], None
    if merge:
        # The candidates doc is still read independently (live file, else newest aside) -- gating
        # BOTH on disc_path.exists() lost the union when a crashed attempt left an orphaned
        # candidates.json with no discovery.json (review finding on #265; see _prior_doc).
        old_schools = prior_schools_for_compare
        old_geo = prior_disc.get("geo_discovery")   # #164 review: carry the derivation receipt forward
        old_candidates = _prior_doc(d, cand_path, "candidates").get("candidates", [])

    if disc_path.exists() or cand_path.exists():
        # Rename aside whichever exists -- independent gates, so a crash-orphaned
        # candidates.json is preserved with a timestamp instead of silently clobbered.
        ts = TU.fs_stamp()
        if disc_path.exists():
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
            "wave1_providers": r.get("wave1_providers"),
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
    # #672 criterion 1: an escalation that performed WORSE than the rung before it must not be
    # silently indistinguishable from one that simply found nothing. Compared against THIS rung's
    # own new entries (not the merged union) for the reason rung_regression documents.
    regression = rung_regression(prior_schools_for_compare, new_schools)
    if regression is not None:
        discovery_doc["rung_regression"] = regression
    if geo_receipt is not None:
        # #164: the geo run's derivation receipt — the full host tally + thresholds + outcome,
        # and (when derived) the discovered_domain PROPOSAL awaiting human confirmation.
        discovery_doc["geo_discovery"] = geo_receipt
    elif old_geo is not None:
        # #164 review: a domain-scoped follow-up merge (geo_receipt=None) must not silently drop
        # the district's earlier derivation receipt from the LIVE manifest — the aside file is
        # attempt history, not where auditors look.
        discovery_doc["geo_discovery"] = old_geo

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
    # candidates first, discovery last (#265): discovery.json existing is the "done" marker.
    _atomic_write_json(cand_path, candidates_doc)
    _atomic_write_json(disc_path, discovery_doc)
    if docs_out is not None:
        # #616: hand the just-built docs back so the same-process caller can project them into the DB
        # cache WITHOUT re-reading them off disk. cand_map mirrors cache_ingest.load_candidates' shape.
        docs_out["discovery"] = discovery_doc
        docs_out["candidates_map"] = {c["url"]: {"schools": c.get("schools", []),
                                                 "tools": c.get("tools", [])}
                                      for c in candidates if c.get("url")}
    return d


def finish_district(district: dict, roster: list, batch_id: str, registry: dict,
                    *, merge: bool = False, geo_receipt: dict | None = None) -> str:
    """Single registry write per district, at actual completion -- never from a subagent,
    never an interim 'started' marker (there's nothing meaningful to reconcile against a
    half-finished state, since the file write only happens once everything is assembled).
    `merge=True` = a follow-up redo (issue #174): write_discovery unions with the prior round."""
    docs: dict = {}
    write_discovery(district, roster, batch_id, merge=merge, geo_receipt=geo_receipt, docs_out=docs)
    outcome = district_outcome(roster)
    # #734 (#719 review): a geo run whose derivation failed with provider hits in hand must leave a
    # DURABLE trace — the runner's loud job-log block and event feed die with the process, and the
    # outcome string alone reads as an ordinary manual_flag_all ("total failure wearing a normal
    # outcome's clothes"). The state_event note + the discovery.json geo_discovery receipt (outcome
    # + full tally, written above) together let any later reader distinguish "providers found N
    # hits, all #229-refused" from a genuine zero-hit flag.
    notes = ""
    if district.get("_geo_refused"):
        notes = (f"geo_derivation_failed: {district['_geo_refused']} provider result(s) refused "
                 "no-scoping-domain (#229/#719) — see discovery.json geo_discovery")
    # #672 criterion 1: the regression must be DURABLE and visible, for the same reason #734 made
    # the derivation failure durable — the job log dies with the process and the outcome string
    # alone cannot say "this rung did worse than the last one". Note that most of these do NOT
    # reach manual_flag_all: the measured corpus lost keepers on found_all -> found_partial
    # transitions, which read as ordinary progress. Appended, never substituted: a rung can be
    # both geo-refused and a regression (Wyandanch was).
    reg = (docs.get("discovery") or {}).get("rung_regression")
    if reg:
        note = (f"rung_regression: kept {reg['kept_before']} -> {reg['kept_after']} over "
                f"{reg['n_schools_compared']} re-queried school(s) (#672)")
        if reg["schools_zeroed"]:
            note += f"; {len(reg['schools_zeroed'])} school(s) lost every candidate"
        notes = f"{notes}; {note}" if notes else note
    DS.record_stage(
        registry, district["district_id"], district["name"], district["state"],
        stage=2, stage_name="discover", outcome=outcome, batch_id=batch_id, notes=notes,
    )
    # Project this district's funnel into the live DB cache so the console reads fresh rows without
    # waiting for a Stage-5 ingest, from the just-built docs — no write-then-reread round-trip off disk
    # (#616; gov_db is the working store, disk is an audit receipt). Best-effort.
    CI.cache_discovery_docs(docs["discovery"], docs["candidates_map"])
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
                                  merge=BT.redoes_attempted(batch))
        DS.save(registry)
        print(f"{district['district_id']} {district['name']}: {outcome}")


if __name__ == "__main__":
    main()
