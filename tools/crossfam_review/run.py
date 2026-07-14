"""Orchestrate the cross-family review: fan-out finders → dedup → judge cascade → file issues.

Safe by default. Without flags it PREFLIGHTS only (validates model ids against the live OpenRouter
catalog, prints the shard map + budget estimate, makes zero paid calls). A real review needs
`--run`; filing GitHub issues additionally needs `--live` (otherwise the issues it would create are
printed + written to the receipt). Every paid call is spend-guarded at `--cap` (default $10).

Usage:
  python -m tools.crossfam_review.run                 # preflight only (free)
  python -m tools.crossfam_review.run --run           # full paid review, print issues
  python -m tools.crossfam_review.run --run --live    # full review + file issues
  python -m tools.crossfam_review.run --run --max-shards 1 --only glm-4.7-flash
                                                                        # cheap smoke test

Receipts (every stage's raw output) land under data/review/crossfam-<stamp>/ — the audit trail.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from infrastructure.acquisition.stage7_extract import openrouter as OR
from tools.crossfam_review import council as C
from tools.crossfam_review import dedup as D
from tools.crossfam_review import finder as F
from tools.crossfam_review import github_sink as GH
from tools.crossfam_review import shards as S
from tools.crossfam_review.findings import Finding
from tools.crossfam_review.roster import FINDERS, JUDGES
from tools.crossfam_review.spend import BudgetExceeded, SpendGuard

RECEIPTS = S.REPO_ROOT / "data" / "review"


def _live_model_ids() -> set[str] | None:
    """The OpenRouter catalog's model ids, or None if the catalog can't be fetched (offline)."""
    import urllib.request
    try:
        with urllib.request.urlopen("https://openrouter.ai/api/v1/models", timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        return {m["id"] for m in data.get("data", [])}
    except Exception:
        return None


def _estimate(shard_list) -> float:
    """Rough pre-run cost: every finder over every shard (in≈shard tokens, out≈4k) + a council pass
    (~3 judge calls × ~5k in each over an assumed ~1 candidate/shard). Over-estimates on purpose."""
    tok = sum(s.est_tokens for s in shard_list)
    finders = sum(m.cost(tok + 600 * len(shard_list), 4000 * len(shard_list)) for m in FINDERS)
    n_cand = max(1, len(shard_list))
    council = sum(J.cost(5000, 400) for J in JUDGES.values()) * n_cand
    return finders + council


def preflight(shard_list, cap: float) -> int:
    summary = S.surface_summary(shard_list)
    print("── cross-family review · preflight ──")
    print(f"surface: {summary['files']} files · {summary['shards']} shards · "
          f"~{summary['est_tokens']:,} tokens")
    print(f"finders: {len(FINDERS)} · judges: {len(JUDGES)} (rotating cascade)")
    est = _estimate(shard_list)
    print(f"estimated spend: ~${est:.2f}  (hard cap ${cap:.2f})")

    ids = _live_model_ids()
    if ids is None:
        print("model validation: SKIPPED (couldn't reach OpenRouter catalog)")
    else:
        missing = [m.id for m in FINDERS if m.id not in ids] + \
                  [j.id for j in JUDGES.values() if j.id not in ids]
        if missing:
            print(f"model validation: ✗ NOT FOUND on OpenRouter: {missing}")
            return 1
        print(f"model validation: ✓ all {len(FINDERS) + len(JUDGES)} model ids exist")
    print(f"OpenRouter key present: {OR.has_key()}")
    if est > cap:
        print(f"⚠ estimate ${est:.2f} exceeds cap ${cap:.2f} — raise --cap or reduce scope")
    return 0


def run_finders(shard_list, only: set[str] | None, guard: SpendGuard, workers: int) -> list:
    models = [m for m in FINDERS if (only is None or m.id.split("/")[-1] in only or m.id in only)]
    tasks = [(m, s) for m in models for s in shard_list]
    results: list[F.FinderResult] = []
    print(f"finder pass: {len(models)} models × {len(shard_list)} shards = {len(tasks)} calls")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(F.run_finder, m, s, guard): (m, s) for m, s in tasks}
        done = 0
        for fut in as_completed(futs):
            try:
                r = fut.result()
            except OR.BillingAuthError as e:
                print(f"\n✗ billing/auth failure — halting: {e}")
                for f in futs:
                    f.cancel()
                break
            results.append(r)
            done += 1
            n = len(r.findings)
            flag = "∅" if r.empty else ("·" if r.ok else ("skip" if r.skipped else "ERR"))
            print(f"  [{done}/{len(tasks)}] {flag} {r.model:34} {r.shard_id:30} "
                  f"{n:>3} findings  ${guard.settled():.3f}", flush=True)
    return results


def run_council(candidates, guard: SpendGuard, workers: int) -> list:
    print(f"judge cascade: {len(candidates)} candidates")
    adjs: list[C.Adjudication] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(C.adjudicate, c, i, guard): i for i, c in enumerate(candidates)}
        done = 0
        for fut in as_completed(futs):
            try:
                adj = fut.result()
            except OR.BillingAuthError as e:
                print(f"\n✗ billing/auth failure — halting council: {e}")
                break
            adjs.append(adj)
            done += 1
            mark = "✓CONFIRMED" if adj.confirmed else "✗refuted"
            print(f"  [{done}/{len(candidates)}] {mark:11} {adj.candidate.severity:8} "
                  f"{adj.candidate.file}:{adj.candidate.line}  ${guard.settled():.3f}", flush=True)
    return adjs


def _file_only(outdir, stamp: str, live: bool) -> int:
    """File issues from a prior run's persisted issue_payloads.json (no paid calls)."""
    src = outdir / "issue_payloads.json"
    if not src.exists():
        print(f"✗ no {src} — run the review first (dry) to produce it.")
        return 1
    saved = json.loads(src.read_text())
    print(f"filing {len(saved)} saved payloads (live={live}) under '{GH.campaign_label(stamp)}'")
    GH.ensure_label(stamp, live)
    already = GH.existing_fingerprints(stamp, live)
    filed = []
    for p in saved:
        if p["fingerprint"] in already:
            continue
        payload = GH.IssuePayload(title=p["title"], body=p["body"], labels=p["labels"],
                                  fingerprint=p["fingerprint"])
        out = GH.create_issue(payload, live=live)
        filed.append(out)
        print(f"  {'✓ ' + out.get('url','') if live else '(dry) ' + out['title'][:80]}", flush=True)
    (outdir / "issues.json").write_text(json.dumps(filed, indent=2))
    print(f"\n{'filed' if live else 'would file'} {len(filed)} issues.")
    return 0


def _real_votes(adj: dict) -> int:
    return sum(1 for v in adj.get("verdicts", []) if v["verdict"] in ("confirmed", "refuted"))


def _completed_keys(outdir) -> set:
    """(file, line-bucket) that were GENUINELY judged by a prior pass — i.e. got >=2 real (non-error)
    votes. A candidate whose judge calls were REFUSED at the spend cap (force-refuted on errors) is NOT
    complete and must be re-judged by a resume, not skipped. This is the difference between "459
    adjudicated" and "296 actually evaluated" (the rest were budget-starved)."""
    f = outdir / "adjudications.json"
    if not f.exists():
        return set()
    return {(a["file"], a["line"] // 10) for a in json.loads(f.read_text()) if _real_votes(a) >= 2}


def _resume_council(outdir, shard_area, args, guard: SpendGuard) -> int:
    """Judge the corroborated candidates a prior run left un-adjudicated (it hit its cap), reusing that
    run's saved raw_findings.json. Pays ONLY for the new judging; appends to the run's receipts +
    issue_payloads so a subsequent --file-only files the whole set."""
    raw_f = outdir / "raw_findings.json"
    if not raw_f.exists():
        print(f"✗ no {raw_f} — resume needs a prior run's finder output.")
        return 1
    raw = [Finding(**d) for d in json.loads(raw_f.read_text())]
    all_cands = D.cluster(raw, shard_area)
    corroborated = [c for c in all_cands if c.agree_count >= args.min_agree]
    done = _completed_keys(outdir)
    remaining = [c for c in corroborated if (c.file, c.line // 10) not in done]
    print(f"resume: {len(corroborated)} corroborated (≥{args.min_agree}); "
          f"{len(done)} genuinely judged already; re-/newly judging {len(remaining)} "
          f"(incl. budget-starved) under cap ${args.cap:.2f}")
    if not remaining:
        print("nothing left to adjudicate.")
        return 0

    new_adjs = run_council(remaining, guard, args.workers)
    new_conf = [a for a in new_adjs if a.confirmed]

    # Merge adjudications by (file, line-bucket): a re-judged candidate OVERWRITES its prior
    # budget-starved record rather than duplicating it (the receipt stays one row per candidate).
    def _rec(a):
        return {"file": a.candidate.file, "line": a.candidate.line, "confirmed": a.confirmed,
                "escalated": a.escalated, "summary": a.candidate.summary,
                "verdicts": [{"judge": v.judge, "role": v.role, "verdict": v.verdict, "reason": v.reason}
                             for v in a.verdicts]}
    prior = json.loads((outdir / "adjudications.json").read_text()) if (outdir / "adjudications.json").exists() else []
    by_key = {(a["file"], a["line"] // 10): a for a in prior}
    for a in new_adjs:
        by_key[(a.candidate.file, a.candidate.line // 10)] = _rec(a)
    (outdir / "adjudications.json").write_text(json.dumps(list(by_key.values()), indent=2))

    # Append newly-confirmed issue payloads to the saved set (dedup by fingerprint).
    payloads = json.loads((outdir / "issue_payloads.json").read_text()) if (outdir / "issue_payloads.json").exists() else []
    seen = {p["fingerprint"] for p in payloads}
    for a in sorted(new_conf, key=lambda a: (a.candidate.severity, a.candidate.file)):
        p = GH.build_payload(a, args.stamp)
        if p.fingerprint in seen:
            continue
        payloads.append({"title": p.title, "body": p.body, "labels": p.labels, "fingerprint": p.fingerprint})
        seen.add(p.fingerprint)
    (outdir / "issue_payloads.json").write_text(json.dumps(payloads, indent=2))

    print(f"\nresume added {len(new_conf)} confirmed (of {len(new_adjs)} judged) · "
          f"spend this pass ${guard.settled():.3f} · {len(payloads)} total payloads saved")
    print(f"file them with:  python -m tools.crossfam_review.run --file-only --live --stamp {args.stamp}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cross-family external code review")
    ap.add_argument("--run", action="store_true", help="make paid calls (default: preflight only)")
    ap.add_argument("--live", action="store_true", help="file GitHub issues (default: print them)")
    ap.add_argument("--file-only", action="store_true",
                    help="skip the paid review; (re)file from a prior run's saved issue_payloads.json")
    ap.add_argument("--resume-council", action="store_true",
                    help="adjudicate the corroborated candidates a prior run left un-judged (e.g. it hit "
                         "its cap), reusing that run's saved raw_findings.json — pays ONLY for new judging")
    ap.add_argument("--cap", type=float, default=10.0, help="hard USD spend cap (default 10)")
    ap.add_argument("--workers", type=int, default=8, help="concurrent API calls")
    ap.add_argument("--max-shards", type=int, default=0, help="review only the first N shards (smoke test)")
    ap.add_argument("--only", default="", help="comma-separated finder model ids/short-names to run")
    ap.add_argument("--min-agree", type=int, default=1,
                    help="only adjudicate candidates flagged by >= this many finder families "
                         "(2+ focuses the council on cross-family-corroborated findings; default 1 = all)")
    ap.add_argument("--stamp", default=date.today().isoformat(), help="campaign stamp (default today)")
    args = ap.parse_args(argv)

    shard_list = S.build_shards()
    if args.max_shards > 0:
        shard_list = shard_list[:args.max_shards]
    shard_area = {s.shard_id: s.area_label for s in shard_list}

    if not args.run:
        return preflight(shard_list, args.cap)

    if not OR.has_key():
        print("✗ no OPENROUTER_API_KEY — cannot run. (Set it or use preflight.)")
        return 1

    guard = SpendGuard(args.cap)
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    outdir = RECEIPTS / f"crossfam-{args.stamp}"
    outdir.mkdir(parents=True, exist_ok=True)

    # File-only: skip the paid finder+council pass entirely and (re)file from a prior run's saved
    # issue_payloads.json — used to review a dry run's output, then file it without re-paying, or to
    # replay a filing that failed partway. Idempotent via fingerprints.
    if args.file_only:
        return _file_only(outdir, args.stamp, args.live)

    if args.resume_council:
        return _resume_council(outdir, shard_area, args, guard)

    # 1. Finders
    finder_results = run_finders(shard_list, only, guard, args.workers)
    raw = [f for r in finder_results for f in r.findings]
    (outdir / "raw_findings.json").write_text(json.dumps([f.to_dict() for f in raw], indent=2))
    # Raw-reply audit trail: every finder call's verbatim output (auditability, commandment #1) — so a
    # parse-miss or a reasoning-drowned finder can be inspected after the fact, not guessed at.
    with (outdir / "raw_replies.jsonl").open("w") as fh:
        for r in finder_results:
            fh.write(json.dumps({
                "model": r.model, "shard": r.shard_id, "ok": r.ok, "empty": r.empty,
                "skipped": r.skipped, "finish_reason": r.finish_reason, "n_findings": len(r.findings),
                "cost_usd": r.cost_usd, "error": r.error, "content": r.raw_content}) + "\n")
    empties = [r for r in finder_results if r.empty]
    errs = [r for r in finder_results if not r.ok and not r.skipped]
    print(f"\nraw findings: {len(raw)} · spend so far ${guard.settled():.3f}")
    if empties:
        print(f"⚠ {len(empties)} finder calls returned empty content (reasoning-drowned?): "
              f"{sorted({r.model for r in empties})}")
    if errs:
        print(f"⚠ {len(errs)} finder calls errored: {sorted({r.model for r in errs})}")

    # 2. Dedup
    all_candidates = D.cluster(raw, shard_area)
    (outdir / "candidates.json").write_text(json.dumps(
        [{"file": c.file, "line": c.line, "severity": c.severity, "category": c.category,
          "summary": c.summary, "agree_count": c.agree_count,
          "families": sorted(c.families)} for c in all_candidates], indent=2))
    # Corroboration filter: with many finders, a real bug tends to be flagged by SEVERAL families,
    # while singletons are mostly one model's noise. Adjudicating only candidates ≥ min_agree focuses
    # the expensive judge council on the cross-family-corroborated set — higher signal AND far cheaper
    # (the whole REQ-056 thesis). Singletons stay in candidates.json for optional later review.
    candidates = [c for c in all_candidates if c.agree_count >= args.min_agree]
    dropped = len(all_candidates) - len(candidates)
    print(f"unique candidates: {len(all_candidates)}  "
          f"(adjudicating {len(candidates)} with ≥{args.min_agree} families; "
          f"{dropped} singletons held back in candidates.json)")

    # 3. Judge cascade
    try:
        adjs = run_council(candidates, guard, args.workers)
    except BudgetExceeded as e:
        print(f"⚠ spend cap hit during council: {e}")
        adjs = []
    confirmed = [a for a in adjs if a.confirmed]
    (outdir / "adjudications.json").write_text(json.dumps(
        [{"file": a.candidate.file, "line": a.candidate.line, "confirmed": a.confirmed,
          "escalated": a.escalated, "summary": a.candidate.summary,
          "verdicts": [{"judge": v.judge, "role": v.role, "verdict": v.verdict, "reason": v.reason}
                       for v in a.verdicts]} for a in adjs], indent=2))
    print(f"\nconfirmed: {len(confirmed)}/{len(adjs)} · total spend ${guard.settled():.3f}")

    # 4. File issues — build every payload FIRST and persist it, so a filing failure (rate limit,
    # network, a gh hiccup) after a ~$10+ paid review can be replayed from disk without re-paying.
    payloads = [GH.build_payload(a, args.stamp)
                for a in sorted(confirmed, key=lambda a: (a.candidate.severity, a.candidate.file))]
    (outdir / "issue_payloads.json").write_text(json.dumps(
        [{"title": p.title, "body": p.body, "labels": p.labels, "fingerprint": p.fingerprint}
         for p in payloads], indent=2))
    GH.ensure_label(args.stamp, args.live)
    already = GH.existing_fingerprints(args.stamp, args.live)
    filed = []
    for payload in payloads:
        if payload.fingerprint in already:
            continue
        filed.append(GH.create_issue(payload, live=args.live))
    (outdir / "issues.json").write_text(json.dumps(filed, indent=2))
    (outdir / "run_meta.json").write_text(json.dumps({
        "stamp": args.stamp, "live": args.live, "cap": args.cap,
        "spend": guard.snapshot(), "finders": len(FINDERS),
        "shards": len(shard_list), "raw_findings": len(raw),
        "empty_finder_calls": len(empties), "errored_finder_calls": len(errs),
        "candidates": len(candidates), "confirmed": len(confirmed),
        "filed": len(filed)}, indent=2))

    verb = "filed" if args.live else "would file (dry-run)"
    print(f"\n{verb} {len(filed)} issues under label '{GH.campaign_label(args.stamp)}'")
    print(f"receipts: {outdir}")
    print(f"FINAL SPEND: ${guard.settled():.4f} / cap ${args.cap:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
