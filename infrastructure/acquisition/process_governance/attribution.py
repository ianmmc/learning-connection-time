#!/usr/bin/env python3
"""Stage 2/4 effectiveness ATTRIBUTION (#118, REQ-160) — the measurement harness extended upstream.

The Stage-5 harness (harness.py) answers "does the SCORER separate targets from junk?". This module
answers the two questions upstream of it, over the same human-labeled corpus:

  * STAGE 2 — which DISCOVERY tool earns its keep? Every canonical record joins back to the
    `candidate` plan row for its (district, url) and that row's `tools_json` (which SERP
    provider(s) proposed the URL); a record with no plan row attributes to its capture `source`
    (emergent one-hop, manual, benchmark_gt). Per tool: how many candidates it proposed, how many
    became records, how many a human labeled TARGET — the tool-level hit rate the Wave-1/Wave-2
    architecture was chosen on (governance §11f; STAGE2 §3).
  * STAGE 4 — which PROCESSING tool produces the representation the release actually sends?
    For every human-labeled TARGET record, `release.decide()` picks the winning send files; each
    maps back to its representation row's `source` (pdftotext, camelot_*, tesseract_*, raster,
    txt, …). Corpus-wide usable-rate per source rides along for context.
  * THE #164 AXES — per district: every ever-approved batch's (batch_type × discovery_scope),
    the derived ladder position (`batch_store.followup_rounds` — never a stored counter), and
    the scoping-domain source (nces | discovered). Recorded from day one so the geo-vs-domain
    comparison has attribution data the moment geo composition is exercised.

SCORECARD DISCIPLINE (REQ-090): a measurement is only meaningful as a fingerprinted tuple, so the
card stamps the label-set, the discovery plan (`candidate`), and the capture rows it was computed
over — re-derivable, auditable, comparable across time. Read-only over the governance Postgres.
Run on demand (the console panels + CLI); never per-label-write.

KNOWN LIMIT (v1, documented not hidden): `candidate` holds each district's LATEST plan (per-run
upsert), so a district that ran under BOTH scopes attributes its records to the latest plan's
tools. Fine at today's volume (one geo district); revisit if plans start cycling per district.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.stage5_filter import release as REL
from infrastructure.acquisition.stage5_filter.harness import _h

TARGET = BS.TARGET_LABELS


def _did_filter(district_ids) -> tuple[str, dict]:
    """(SQL clause, params) restricting to `district_ids` when given — corpus-wide otherwise.
    The filter exists for tests (synthetic districts must not perturb corpus aggregates) and
    for future per-batch views."""
    if not district_ids:
        return "", {}
    return " AND r.district_id = ANY(:dids)", {"dids": list(district_ids)}


def stage2_attribution(con, district_ids=None) -> dict:
    """Per discovery TOOL: candidates proposed → canonical records → human-labeled targets.
    Attribution = the candidate plan row's tools_json for the record's (district, url); a record
    with no plan row falls back to its capture source (emergent/manual/benchmark_gt)."""
    clause, params = _did_filter(district_ids)
    # plan-side totals (candidates proposed per tool), independent of what became a record
    plan_counts: dict = defaultdict(int)
    pc, pp = ("WHERE district_id = ANY(:dids)", {"dids": list(district_ids)}) if district_ids else ("", {})
    for (tools_j,) in con.execute(text(f"SELECT tools_json FROM candidate {pc}"), pp):
        for t in (json.loads(tools_j or "[]") or ["unknown"]):
            plan_counts[t] += 1

    rows = con.execute(text(f"""
        SELECT r.district_id, r.url, l.primary_label, r.tier, c.tools_json, cap.source
        FROM record r
        LEFT JOIN label l ON l.rec_key = r.rec_key
        LEFT JOIN candidate c ON c.district_id = r.district_id AND c.url = r.url
        LEFT JOIN capture cap ON cap.district_id = r.district_id AND cap.hash = r.hash
        WHERE {REL.CANONICAL_RECORD_WHERE}{clause}"""), params).all()
    per_tool: dict = defaultdict(lambda: {"n_candidates": 0, "n_records": 0, "n_target": 0,
                                          "n_labeled": 0})
    for _did, _url, plabel, _tier, tools_j, cap_source in rows:
        tools = json.loads(tools_j or "null") or [f"capture:{cap_source or 'unknown'}"]
        for t in tools:
            b = per_tool[t]
            b["n_records"] += 1
            if plabel:
                b["n_labeled"] += 1
            if plabel in TARGET:
                b["n_target"] += 1
    for t, n in plan_counts.items():
        per_tool[t]["n_candidates"] = n
    out = {}
    for t, b in sorted(per_tool.items()):
        out[t] = {**b, "target_rate_labeled": round(b["n_target"] / b["n_labeled"], 3)
                  if b["n_labeled"] else None}
    return {"per_tool": out, "n_records": len(rows)}


def stage4_attribution(con, district_ids=None) -> dict:
    """Per processing SOURCE: which representation the release WINS with on human-labeled TARGET
    records (`release.decide()`'s send files mapped back to representation.source), plus the
    corpus-wide usable-rate per source for context."""
    clause, params = _did_filter(district_ids)
    target_dids = [r[0] for r in con.execute(text(f"""
        SELECT DISTINCT r.district_id FROM record r JOIN label l ON l.rec_key = r.rec_key
        WHERE l.primary_label = ANY(:t){clause}"""), {"t": list(TARGET), **params})]
    winning: dict = defaultdict(int)
    n_target_records = 0
    # #637: ONE bulk load for all target districts (was a per-district load_district_records loop —
    # an N+1 over the labeled TARGET corpus, growing with every labeled district).
    records_by_did = REL.load_districts_records(con, sorted(target_dids))
    for did in sorted(target_dids):
        for rec in records_by_did.get(did, []):
            if rec.get("label") not in TARGET:
                continue
            n_target_records += 1
            reps_by_file = {rp.get("filename"): rp for rp in rec.get("reps") or []}
            for send in REL.decide(rec)["send"]:
                src = (reps_by_file.get(send.get("file")) or {}).get("source") or "unknown"
                winning[src] += 1
    usable: dict = {}
    uc, up = ((" WHERE r.district_id = ANY(:dids)", {"dids": list(district_ids)})
              if district_ids else ("", {}))
    for src, n, n_use in con.execute(text(f"""
        SELECT rep.source, COUNT(*), COUNT(*) FILTER (WHERE rep.usable = 1)
        FROM representation rep JOIN record r ON r.rec_key = rep.rec_key{uc}
        GROUP BY rep.source"""), up):
        usable[src] = {"n_reps": n, "n_usable": n_use,
                       "usable_rate": round(n_use / n, 3) if n else None}
    return {"winning_source": dict(sorted(winning.items(), key=lambda kv: -kv[1])),
            "n_target_records": n_target_records, "usable_by_source": usable}


def district_axes(con, district_ids=None) -> dict:
    """The #164 attribution axes per district: every ever-approved batch's (batch_type ×
    discovery_scope), the derived ladder position, and the scoping-domain source."""
    clause, params = (("WHERE bd.district_id = ANY(:dids)", {"dids": list(district_ids)})
                      if district_ids else ("", {}))
    runs: dict = defaultdict(lambda: defaultdict(int))
    dids = set()
    for did, btype, scope in con.execute(text(f"""
        SELECT bd.district_id, b.batch_type, COALESCE(b.discovery_scope, 'domain')
        FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id
        {clause}{' AND' if clause else 'WHERE'} b.first_approved_at IS NOT NULL AND bd.included"""),
            params):
        runs[did][f"{btype}:{scope}"] += 1
        dids.add(did)
    # #575 review: must filter on the SAME approved+included predicate as `runs` above — otherwise
    # a draft/abandoned/never-approved batch with a higher batch_id can win DISTINCT ON and
    # misattribute the axis to a run that never actually happened.
    dsource = dict(con.execute(text(f"""
        SELECT DISTINCT ON (bd.district_id) bd.district_id, bd.domain_source
        FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id
        {clause}{' AND' if clause else 'WHERE'} bd.domain_source IS NOT NULL
        AND b.first_approved_at IS NOT NULL AND bd.included
        ORDER BY bd.district_id, b.batch_id DESC"""), params).all())
    ladder = BSTORE.followup_rounds(con, sorted(dids)) if dids else {}
    return {did: {"runs": dict(runs[did]), "ladder": ladder.get(did),
                  "domain_source": dsource.get(did, "nces")} for did in sorted(dids)}


def fingerprints(con) -> dict:
    """The tuple this card is re-derivable from: the label set, the discovery plan, the captures."""
    labels = con.execute(text(
        "SELECT rec_key, primary_label, status FROM label WHERE status != 'unlabeled' "
        "ORDER BY rec_key")).fetchall()
    plan = con.execute(text(
        "SELECT district_id, url, tools_json FROM candidate ORDER BY district_id, url")).fetchall()
    caps = con.execute(text(
        "SELECT district_id, hash, source, err FROM capture ORDER BY district_id, hash")).fetchall()
    return {"label_set": _h("|".join("·".join(map(str, r)) for r in labels)),
            "plan": _h("|".join("·".join(map(str, r)) for r in plan)),
            "captures": _h("|".join("·".join(map(str, r)) for r in caps))}


def build_card(con=None, district_ids=None) -> dict:
    def _work(c):
        return {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fingerprints": fingerprints(c),
                "stage2": stage2_attribution(c, district_ids),
                "stage4": stage4_attribution(c, district_ids),
                "district_axes": district_axes(c, district_ids)}
    if con is not None:
        return _work(con)
    with gdb.session_scope() as c:
        return _work(c)


def write_card(card, out_dir=None):
    """Persist the receipt beside the harness scorecards (same discipline, distinct prefix)."""
    from pathlib import Path
    out_dir = Path(out_dir or paths.SCORECARDS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = card["generated_at"].replace(":", "").replace("-", "")
    out = out_dir / f"attribution_{ts}_{card['fingerprints']['label_set']}.json"
    out.write_text(json.dumps(card, indent=2))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Stage 2/4 effectiveness attribution (#118)")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    card = build_card()
    s2 = card["stage2"]["per_tool"]
    print(f"stage2 ({card['stage2']['n_records']} canonical records):")
    for t, b in s2.items():
        print(f"  {t:24} cand={b['n_candidates']:5} rec={b['n_records']:5} "
              f"labeled={b['n_labeled']:4} target={b['n_target']:4} "
              f"rate={b['target_rate_labeled']}")
    s4 = card["stage4"]
    print(f"stage4 winning sources over {s4['n_target_records']} target records: "
          f"{s4['winning_source']}")
    if not a.no_write:
        print("wrote", write_card(card))


if __name__ == "__main__":
    main()
