"""#672 — an escalation rung can perform STRICTLY WORSE than the rung before it. Measure it.

RERUNNABLE, READ-ONLY. Replays the on-disk Stage-2 discovery receipts and calls the LIVE routing
predicates (`Q1.usable_scoping_domains`, `BSTORE.followup_rounds`, `BSTORE.ladder_exhausted`).
Nothing is written.

    python3 docs/technical-notes/production-quality-control-research/2026-08-21-geo-ladder-regression-measure.py

Why this exists: #672 was filed 2026-07-27 and its headline mechanism — "`compose_zero_yield`
composes escalations as geo-scoped UNCONDITIONALLY, so a district with a confirmed domain of record
gets pushed into the scope designed for domain-less ones" — was CLOSED by #719 in the meantime.
Fixing the issue as written would re-fix something already fixed and miss what is still broken. The
repo's standing rule (measure the thing before fixing it; fourteen issues overturned so far) is the
only reason that is visible. Run this before touching the ladder.

C1  the re-route: where would each geo-laddered district go TODAY, through the live composer
    predicates? This is the part of #672 that #719 already closed, quantified rather than asserted.
C2  the rung-over-rung regression, corpus-wide: every consecutive pair of discovery receipts where
    the LATER rung kept FEWER candidates than the earlier one. #672's acceptance criterion 1.
C3  the residual exposure: districts that can still hit the dilution trap — no usable scoping
    domain, so a geo+widened rung really can multiply the denominator and fail closed. This is the
    population a fix must serve, and it is NOT the population the issue's Wyandanch example is in.
C4  criterion 3's question, asked of the DATA: can a `manual_flag` caused by DERIVATION FAILURE be
    told apart from one caused by NO RESULTS, using only what is persisted?

Every section prints an explicit NOTHING MEASURED verdict rather than a green zero.
"""
import collections
import json

from sqlalchemy import text

from infrastructure.acquisition.common import discovered_domain as DDOM
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common.db import session_scope
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage1_queue import queue_batch as Q1

DISTRICT_DIRS = paths.RAW_CAPTURES
NCES_YEAR = "2024_25"


def verdict(name, n_scanned, lines, unit="districts"):
    print(f"\n=== {name} ===")
    if not n_scanned:
        print(f"  NOTHING MEASURED — the sweep scanned 0 {unit}. This is NOT a pass; the corpus "
              "or the path assumption is wrong. Fix the script before reading anything below.")
        return
    print(f"  scanned: {n_scanned} {unit}")
    for ln in lines:
        print(f"  {ln}")


def kept_count(receipt):
    """Candidates the rung actually KEPT — the number that matters, not raw results found."""
    n = 0
    for sch in receipt.get("schools", []):
        n += sum(1 for g in sch.get("wave1_gated", []) if g.get("kept"))
        n += sum(1 for g in sch.get("wave2_gated", []) if g.get("kept"))
    return n


def raw_count(receipt):
    return sum(len(sch.get("wave1_raw_urls", [])) + len(sch.get("wave2_raw_urls", []))
               for sch in receipt.get("schools", []))


def outcome_of(receipt):
    outs = [s.get("outcome") for s in receipt.get("schools", [])]
    if not outs:
        return "no_schools"
    if all(o == "found" for o in outs):
        return "found_all"
    if all(o != "found" for o in outs):
        return "manual_flag_all"
    return "found_partial"


# ------------------------------------------------------------------ load every discovery receipt
receipts = collections.defaultdict(list)     # district_id -> [receipt, ...] oldest first
ddirs = sorted(DISTRICT_DIRS.glob("*/"))
if not ddirs:
    raise SystemExit(f"NOTHING MEASURED — no district dirs under {DISTRICT_DIRS}.")
for ddir in ddirs:
    for f in ddir.glob("discovery*.json"):
        try:
            r = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        did = r.get("district_id")
        if did:
            r["_file"] = f.name
            receipts[did].append(r)
for did in receipts:
    receipts[did].sort(key=lambda r: (r.get("generated_at") or "", r.get("batch_id") or ""))

geo_districts = {did: rs for did, rs in receipts.items()
                 if any(r.get("geo_discovery") for r in rs)}

# ------------------------------------------------------------------ C1: the live re-route (#719)
with session_scope() as s:
    dd = DDOM.all_confirmed(s)
    dids = sorted(geo_districts)
    domains = Q1.usable_scoping_domains(NCES_YEAR, dids, dd) if dids else {}
    rounds = BSTORE.followup_rounds(s, dids) if dids else {}
    names = dict(s.execute(text(
        "SELECT district_id, name FROM district WHERE district_id = ANY(:d)"), {"d": dids}
    ).fetchall()) if dids else {}

route = {}
for did in dids:
    hd = bool(domains.get(did, ("", None))[0])
    rr = rounds.get(did, {"domain": 0, "geo": 0})
    if BSTORE.ladder_exhausted(rr, has_domain=hd):
        route[did] = "manual_flag (ladder exhausted)"
    elif hd:
        route[did] = "domain+widened"
    elif rr.get("geo", 0) == 0:
        route[did] = "geo+standard"
    else:
        route[did] = "geo+widened"

by_route = collections.Counter(route.values())
lines = [f"{v:>4}  {k}" for k, v in sorted(by_route.items())]
lines.append("")
lines.append("Reading: every district on `domain+widened` is one #719 already pulled OUT of geo.")
lines.append("#672's Wyandanch narrative — 'geo scope is forced onto districts that already have a")
lines.append("domain' — describes the composer as it was, not as it is.")
for did in dids:
    hd, src = domains.get(did, ("", None))
    lines.append(f"    {did} {str(names.get(did, ''))[:30]:<30} domain={hd or '(none)':<26} "
                 f"src={str(src):<6} rounds={rounds.get(did)} -> {route[did]}")
verdict("C1 — where each geo-laddered district routes TODAY (live predicates)",
        len(dids), lines)

# ------------------------------------------------------------------ C2: rung-over-rung regression
regressions, n_pairs = [], 0
for did, rs in sorted(receipts.items()):
    for prev, cur in zip(rs, rs[1:]):
        n_pairs += 1
        kp, kc = kept_count(prev), kept_count(cur)
        if kc < kp:
            g = cur.get("geo_discovery") or {}
            gp = (prev.get("geo_discovery") or {})
            # Classify by MECHANISM, not by symptom. Lumping these together would inflate #672 with
            # #719's own evidence set — the same "compare the dimension the rule is about" trap the
            # #841 audit hit when it read 3,532 deliberate differences as disagreements.
            # Order matters: test the MECHANISM before the routing. A district can be BOTH
            # (Wyandanch is), and #719's routing fix only stops domain-having districts from
            # entering geo — it does nothing about what happens once a domain-less one is in
            # there. Classifying by routing first would file the corpus's only instance of the
            # unfixed mechanism under "already fixed" and #672 would close on a false negative.
            if not g:
                kind = "non-geo"
            elif gp.get("outcome") == "derived" and g.get("outcome") == "below threshold":
                kind = "DILUTION (a working derivation destroyed by the widened rung — UNFIXED)"
            elif bool(domains.get(did, ("", None))[0]):
                # A geo rung on a district that HAS a usable scoping domain: exactly the #719
                # defect (merged 2026-08-14, `630f2a5`). No longer composable — the composer
                # routes these to domain+widened. Historical, not live exposure.
                kind = "#719 (geo rung on a domain-having district — no longer composable)"
            else:
                kind = "geo, other"
            regressions.append({
                "did": did, "name": names.get(did, ""), "kind": kind,
                "from": prev.get("batch_id"), "to": cur.get("batch_id"),
                "kept": (kp, kc), "raw": (raw_count(prev), raw_count(cur)),
                "outcome": (outcome_of(prev), outcome_of(cur)),
                "derivation": (gp.get("outcome"), g.get("outcome")),
                "share": (gp.get("share"), g.get("share")),
            })

lines = [f"consecutive rung pairs examined: {n_pairs}",
         f"pairs where the LATER rung kept FEWER candidates: {len(regressions)}",
         "",
         "acceptance criterion 1 ('an escalation rung never leaves a district with fewer kept "
         "candidates than the rung before it without that regression being visible and recorded'):",
         f"  {'FAIL — regressions exist and nothing in the data records them as such' if regressions else 'no regression found in this corpus'}",
         ""]
by_kind = collections.Counter(r["kind"] for r in regressions)
for k, v in sorted(by_kind.items()):
    lines.append(f"    {v:>3}  {k}")
lines.append("")
for r in sorted(regressions, key=lambda x: x["kind"]):
    lines.append(f"  [{r['kind'].split(' (')[0]}] {r['did']} {str(r['name'])[:26]:<26} "
                 f"{r['from']} -> {r['to']}")
    lines.append(f"      kept {r['kept'][0]:>3} -> {r['kept'][1]:<3}   raw {r['raw'][0]:>3} -> {r['raw'][1]:<3}"
                 f"   outcome {r['outcome'][0]} -> {r['outcome'][1]}")
    lines.append(f"      geo derivation {r['derivation'][0]} (share {r['share'][0]}) -> "
                 f"{r['derivation'][1]} (share {r['share'][1]})")
if regressions:
    lines.append("")
    lines.append("The dilution signature: raw results go UP while kept goes DOWN, because the share")
    lines.append("threshold has a DENOMINATOR the widened vocabulary inflates. Widening is assumed")
    lines.append("monotonic in recall; against a share-based gate it is not.")
    lines.append("")
    lines.append("BUT read the classification before quoting a total. The #719-tagged rows are that")
    lines.append("issue's own evidence (6 batches, 2026-08-14T17:16, merged the same day in 630f2a5)")
    lines.append("— they are history, not live exposure, and counting them as #672's would overstate")
    lines.append("this issue roughly fourfold. What #719 did NOT fix is the DILUTION row: a rung that")
    lines.append("derives a host, then a widened rung that dilutes the same host below threshold.")
    lines.append("That mechanism is untouched and applies to any district without a usable domain.")
    lines.append("The non-geo row is a third thing again — a domain-scoped rung that simply returned")
    lines.append("fewer keepers — and it is the plainest evidence for criterion 1: no derivation was")
    lines.append("involved at all, and still nothing recorded that the rung did worse.")
verdict("C2 — rung-over-rung kept-candidate regression (#672 criterion 1)", n_pairs, lines,
        unit="rung pairs")

# ------------------------------------------------------------------ C3: who is still exposed
exposed = [did for did in dids if route[did] in ("geo+standard", "geo+widened")]
lines = [f"districts that can still enter a geo rung: {len(exposed)}",
         f"of those, next rung is geo+widened (the dilution-capable one): "
         f"{sum(1 for d in exposed if route[d] == 'geo+widened')}"]
if exposed:
    for did in exposed:
        lines.append(f"    {did} {str(names.get(did, ''))[:30]:<30} -> {route[did]}")
lines.append("")
lines.append("This is the population a #672 fix must actually serve. Note what it is NOT: a")
lines.append("district with a confirmed domain of record. #719 routes those to domain+widened,")
lines.append("where the gate is on-domain and widening can only ADD. The residual criterion-2 case")
lines.append("is narrower than the issue states — a district whose PREVIOUS geo rung derived a host")
lines.append("that no human has confirmed yet: the next rung starts from a blank domain again and")
lines.append("can discard hits on the very host it just derived.")
verdict("C3 — residual exposure after #719", len(dids), lines)

# ------------------------------------------------------------------ C4: criterion 3, asked of the data
with session_scope() as s:
    rows = s.execute(text(
        "SELECT district_id, school, wave1_n_raw, wave1_n_kept, wave2_n_raw, wave2_n_kept, outcome "
        "FROM discovery_school")).fetchall()

flagged = [r for r in rows if r[6] != "found"]
deriv_fail = [r for r in flagged if (r[2] or 0) + (r[4] or 0) > 0 and (r[3] or 0) + (r[5] or 0) == 0]
no_results = [r for r in flagged if (r[2] or 0) + (r[4] or 0) == 0]
lines = [f"school rows with a non-'found' outcome: {len(flagged)}",
         f"  raw results found but NONE kept (derivation/gate refusal): {len(deriv_fail)}",
         f"  no raw results at all (the search genuinely found nothing): {len(no_results)}",
         f"  neither (partial keeps): {len(flagged) - len(deriv_fail) - len(no_results)}",
         "",
         "acceptance criterion 3 ('manual_flag from DERIVATION FAILURE is distinguishable in the",
         "data from manual_flag arising from NO RESULTS'):",
         "  PARTIAL — the two are separable by INFERENCE (n_raw > 0 AND n_kept == 0), but the",
         "  `outcome` column says 'manual_flag' for both and no column records the CAUSE. Every",
         "  consumer that reads `outcome` alone still cannot tell them apart, which is what the",
         "  criterion is about. #719 added a loud batch-level `_geo_refused` count on the district",
         "  dict, but that is a run-time console surface, not a persisted per-school fact.",
         "",
         "Note the inference is not free: n_raw>0/n_kept==0 also covers an honest off-domain",
         "refusal on a normal domain-scoped run. Distinguishing THOSE needs the gate reason, which",
         "IS carried per-URL in wave1_gated_json and is the cheap place to lift a cause from."]
verdict("C4 — is the cause of a manual_flag recoverable from persisted data?", len(rows), lines,
        unit="discovery_school rows")

# ------------------------------------------- C5: what a regressed rung actually COST, end to end
# The issue's headline harm is "109 raw URLs found then thrown away, on-domain hits among them".
# That counts what the RUNG discarded, which is not what the DISTRICT lost: candidates.json unions
# across rungs, so earlier rungs' on-domain URLs survive a later rung's total refusal. The number
# that matters is the on-domain URLs a regressed rung found that are in NO capture plan.
lines, n_examined = [], 0
for r in regressions:
    did = r["did"]
    ddir = next((d for d in ddirs if d.name.startswith(f"{did}_")), None)
    if ddir is None:
        continue
    later = next((x for x in receipts[did] if x.get("batch_id") == r["to"]), None)
    try:
        plan = json.loads((ddir / "candidates.json").read_text()).get("candidates", [])
    except (OSError, ValueError):
        continue
    if later is None:
        continue
    n_examined += 1
    dom = (domains.get(did, ("", None))[0] or "").lower()
    planned = {(c.get("url") or "").rstrip("/").lower() for c in plan}
    raw = [u for sch in later.get("schools", []) for u in sch.get("wave1_raw_urls", [])]
    on_dom = {u for u in raw if dom and (u.split("/")[2].lower().endswith(dom)
                                         if len(u.split("/")) > 2 else False)}
    lost = sorted(u for u in on_dom if u.rstrip("/").lower() not in planned)
    lines.append(f"  {did} {str(r['name'])[:26]:<26} {r['to']}: raw {len(raw)} "
                 f"({len(set(raw))} distinct) | on-domain {len(on_dom)} | "
                 f"NOT in any capture plan: {len(lost)}")
    for u in lost[:5]:
        lines.append(f"        lost: {u}")
lines.append("")
lines.append("Reading: the capture plan is a UNION across rungs (write_discovery merges), so a")
lines.append("refusing rung cannot un-plan what an earlier rung already found. Quote the")
lines.append("NOT-in-any-capture-plan column as the harm, never the raw count — for Wyandanch the")
lines.append("raw count is 109 and the real figure is 3. The rest of the damage is to the STATUS")
lines.append("layer: the district's last stage-2 event reads manual_flag_all, and candidates.json's")
lines.append("top-level `domain` is blanked, on a district whose records were captured and labeled.")
verdict("C5 — what a regressed rung actually cost (plan-aware, not raw-count)", n_examined, lines,
        unit="regressed rungs with a readable plan")

print("\ndone — read-only, nothing written.")
