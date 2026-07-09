"""Council Lab (#80) — measured experiments over frozen extraction receipts.

First experiment: **JUDGE REPLAY**. Re-run a candidate judge on ONLY the reps where the two voters
disagreed and escalated (read straight from a persisted run's receipts), reusing the voters'
already-recorded facts so we pay for nothing but the judge calls. This is the cheapest possible signal
on a judge swap (#82: the image council's deepseek-v3.2 judge was text-only and 404'd on all 33
escalations, leaving 145 (band,school) disagreements unresolved). It answers two questions on the same
$0.03 run: how many disagreements the candidate judge RESOLVES, and — scored against GT — whether those
tie-breaks are CORRECT (a judge that resolves by hallucinating agreement would raise resolution but not
accuracy).

APP layer: reuses stage7_run's content resolver + paid-call path, Stage-8 consensus, and Stage-7 GT
scoring; the stage packages stay independent. Isolates the judge's effect by scoring the SAME
reconstruction twice — voters-only (baseline) vs voters+candidate-judge — so nothing but the judge
differs. Reads receipts + GT off disk; makes one paid judge call per escalated rep.
"""
from __future__ import annotations

import json
from pathlib import Path

from infrastructure.acquisition.common import model_families as MF
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.process_governance import stage7_run as R7
from infrastructure.acquisition.stage6_handoff import councils as C6
from infrastructure.acquisition.stage6_handoff import prompts as P
from infrastructure.acquisition.stage7_extract import parse as PARSE
from infrastructure.acquisition.stage7_extract import validate as VALID
from infrastructure.acquisition.stage8_aggregate import aggregate as AGG


def load_receipts(handoff_hash: str, root=None) -> list:
    """The latest per-district receipt for a persisted run — [{district...}], newest wins per district.
    The glob also matches AGGREGATE receipts (`write_receipt`'s `extraction_<hash>_<ts>.json`, whose
    top level has `districts`, not `district`) — skip those instead of crashing (#141; same defensive
    shape as `backfill_requests`)."""
    d = Path(root) if root else (paths.ACQUISITION / "extractions")
    by_district: dict = {}                              # district_id -> [(ts, path)]; ts sorts lexically
    for f in d.glob(f"extraction_{handoff_hash}_*.json"):
        parts = f.stem.split("_")                       # [extraction, <hash[-image]>, <district>, <ts>]
        if len(parts) != 4:                             # aggregate (extraction_<hash>_<ts>) — no district
            continue
        did, ts = parts[2], parts[3]
        by_district.setdefault(did, []).append((ts, f))
    out = []
    for cands in by_district.values():                  # #148: read newest-first, stop at the first
        for _ts, f in sorted(cands, reverse=True):      # valid receipt (a truncated newest must not
            pd = json.loads(f.read_text()).get("district")  # drop the district — older one still counts)
            if pd:
                out.append(pd)
                break
    return out


def _voter_rows(rep: dict) -> dict:
    """{model: facts} from a rep's recorded VOTER calls — the inputs consensus already saw (no re-call)."""
    return {c["model"]: (c.get("facts") or []) for c in rep["calls"] if c["role"] == "voter"}


def _tag(facts: list, rep: dict) -> list:
    """Attach the rep provenance consensus output needs for band aggregation + GT scoring."""
    for f in facts:
        f["rec_key"], f["source_file"] = rep["rec_key"], rep["file"]
    return facts


def replay_judge(handoff_hash: str, *, judge_model: str = None, council_id: str = "image",
                 root=None, gt_path: str = None, limit: int = None) -> dict:
    """Replay `judge_model` (default: the council's configured judge) on every escalated rep in
    `handoff_hash`'s receipts. Returns per-rep stats + an aggregate + baseline-vs-candidate GT
    scorecards. Makes one paid judge call per escalated rep (up to `limit`)."""
    cfg = C6.get(council_id)
    judge_model = judge_model or cfg["judge"]
    prompt_id = P.select_prompt_id(cfg, judge_model)
    R7._require_key()

    docs = load_receipts(handoff_hash, root)
    # #142 (the #82 shape, again): a CLI-passed --judge candidate never passes councils.validate()'s
    # vision guard — refuse a non-vision-capable judge BEFORE the first paid call if this run's reps
    # include images, instead of burning 33 escalations on 404s.
    if any(rep.get("kind") == "image" for pd in docs for rep in pd.get("reps", [])) \
            and not MF.is_vision_capable(judge_model):
        raise ValueError(
            f"judge candidate '{judge_model}' is not vision-capable (common.model_families."
            f"VISION_CAPABLE) but handoff {handoff_hash} contains image reps — every judge call "
            f"would 404 (#82). Pick a vision-capable candidate, or add the model to the allowlist "
            f"if it genuinely reads images.")
    ddirs = R7.district_dirs([pd["district_id"] for pd in docs])
    gt = VALID.load_gt(gt_path) if gt_path else None

    per_rep, base_districts, cand_districts = [], {}, {}
    replayed = 0
    for pd in docs:
        did = pd["district_id"]
        ddir = ddirs.get(did)
        base_acc, cand_acc = [], []
        for rep in pd["reps"]:
            voter_rows = _voter_rows(rep)
            b_acc, b_unres = AGG.consensus_school_facts(voter_rows)
            base_acc.extend(_tag([dict(f) for f in b_acc], rep))
            if not rep.get("judged") or (limit is not None and replayed >= limit):
                cand_acc.extend(_tag([dict(f) for f in b_acc], rep))   # not escalated → judge irrelevant
                continue
            # escalation: replay the candidate judge on the SAME on-disk rep the voters read
            content = R7.resolve_content(ddir, rep["rec_key"], rep["file"], rep["kind"])
            jres = R7._call(judge_model, prompt_id, rep["kind"], content)
            jfacts = PARSE.parse_schedules(jres.content) if jres.ok else []
            c_acc, c_unres = AGG.consensus_school_facts(voter_rows, {judge_model: jfacts})
            cand_acc.extend(_tag([dict(f) for f in c_acc], rep))
            replayed += 1
            resolved = len(b_unres) - len(c_unres)
            per_rep.append({
                "district": did, "rec_key": rep["rec_key"], "file": rep["file"],
                "judge_ok": jres.ok, "judge_error": jres.error,
                "cost_usd": jres.cost_usd or 0.0, "n_judge_facts": len(jfacts),
                "n_prior_unresolved": len(b_unres), "n_resolved": resolved,
                "n_still_unresolved": len(c_unres)})
            # Per-rep progress + incremental persistence (a big VL judge is ~25-40s/call; a buffered run
            # is invisible + unrecoverable if interrupted). Flush so it streams; dump partials to disk.
            print(f"  [rep {replayed}] {did} {rep['file'][:20]:20s} "
                  f"{'ok' if jres.ok else 'ERR'} ${jres.cost_usd or 0.0:.4f} "
                  f"resolved {resolved}/{len(b_unres)}  (facts={len(jfacts)})", flush=True)
            _dump_partial(handoff_hash, judge_model, per_rep)
        base_districts[did] = {"district_id": did, "name": pd.get("name", ""), "accepted": base_acc,
                               "unresolved": [], "bands": AGG.district_bands_from_facts(base_acc)}
        cand_districts[did] = {"district_id": did, "name": pd.get("name", ""), "accepted": cand_acc,
                               "unresolved": [], "bands": AGG.district_bands_from_facts(cand_acc)}

    ok = sum(1 for r in per_rep if r["judge_ok"])
    agg = {
        "reps_replayed": len(per_rep),
        "judge_calls_ok": ok, "judge_calls_err": len(per_rep) - ok,
        "prior_unresolved": sum(r["n_prior_unresolved"] for r in per_rep),
        "resolved": sum(r["n_resolved"] for r in per_rep),
        "still_unresolved": sum(r["n_still_unresolved"] for r in per_rep),
        "cost_usd": round(sum(r["cost_usd"] for r in per_rep), 5),
    }
    out = {"handoff_hash": handoff_hash, "judge_model": judge_model, "aggregate": agg, "per_rep": per_rep}
    if gt:
        out["gt_baseline"] = VALID.score_run({"districts": base_districts}, gt)
        out["gt_candidate"] = VALID.score_run({"districts": cand_districts}, gt)
    return out


def _dump_partial(handoff_hash: str, judge_model: str, per_rep: list) -> None:
    """Write the running per-rep results to disk after each judge call — so a long VL run is
    inspectable mid-flight and recoverable if interrupted (the buffered-run lesson, 2026-07-04)."""
    d = paths.ACQUISITION / "council_lab"
    d.mkdir(parents=True, exist_ok=True)
    ok = sum(1 for r in per_rep if r["judge_ok"])
    pu = sum(r["n_prior_unresolved"] for r in per_rep)
    rs = sum(r["n_resolved"] for r in per_rep)
    safe = handoff_hash.replace("/", "_")
    (d / f"judge_replay_{safe}_partial.json").write_text(json.dumps({
        "handoff_hash": handoff_hash, "judge_model": judge_model,
        "reps_done": len(per_rep), "judge_ok": ok, "resolved": rs, "prior_unresolved": pu,
        "cost_usd": round(sum(r["cost_usd"] for r in per_rep), 5), "per_rep": per_rep}, indent=2))


def _print(out: dict) -> None:
    a = out["aggregate"]
    print(f"\nJudge replay — {out['judge_model']} on {out['handoff_hash']}")
    print(f"  escalated reps replayed: {a['reps_replayed']}  (judge OK {a['judge_calls_ok']} / "
          f"err {a['judge_calls_err']})   cost ${a['cost_usd']:.4f}")
    pu, rs = a["prior_unresolved"], a["resolved"]
    print(f"  disagreements: {pu} prior-unresolved → {rs} RESOLVED "
          f"({round(100*rs/pu, 1) if pu else 0}%), {a['still_unresolved']} still unresolved")
    if "gt_candidate" in out:
        b, c = out["gt_baseline"], out["gt_candidate"]
        print(f"  GT bands   : baseline {b['bands']['pct']}% ({b['bands']['hit']}/{b['bands']['compared']}, "
              f"{b['bands']['gap']} gap)  →  candidate {c['bands']['pct']}% "
              f"({c['bands']['hit']}/{c['bands']['compared']}, {c['bands']['gap']} gap)")
        print(f"  GT schools : baseline {b['schools']['pct']}% ({b['schools']['hit']}/{b['schools']['matched']})"
              f"  →  candidate {c['schools']['pct']}% ({c['schools']['hit']}/{c['schools']['matched']})")
    errs = [r for r in out["per_rep"] if not r["judge_ok"]]
    if errs:
        print(f"  {len(errs)} judge call(s) errored, e.g.: {errs[0]['district']} — {(errs[0]['judge_error'] or '')[:80]}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Council Lab — judge-replay experiment (#80/#82)")
    ap.add_argument("handoff_hash", help="e.g. a2bc80c004ca-image")
    ap.add_argument("--judge", help="candidate judge model id (default: the council's configured judge)")
    ap.add_argument("--council", default="image")
    ap.add_argument("--gt", help="path to gt_proposals.json (default: newest gt_curation)")
    ap.add_argument("--limit", type=int, help="cap the number of judge calls (cheap sanity run)")
    a = ap.parse_args()
    gt_path = a.gt
    if gt_path is None:
        from infrastructure.acquisition.process_governance.stage7_run import default_gt_path
        try:
            gt_path = default_gt_path()
        except Exception:
            gt_path = None
    out = replay_judge(a.handoff_hash, judge_model=a.judge, council_id=a.council,
                       gt_path=gt_path, limit=a.limit)
    _print(out)


if __name__ == "__main__":
    main()
