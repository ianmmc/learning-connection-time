"""Orchestrate the cross-family review: fan-out finders → dedup → judge cascade → file issues.

Safe by default. Without flags it PREFLIGHTS only (validates model ids against the live OpenRouter
catalog, prints the shard map + budget estimate, makes zero paid calls). A real review needs
`--run`; filing GitHub issues additionally needs `--live` (otherwise the issues it would create are
printed + written to the receipt). Every paid call is spend-guarded at `--cap` (default $10).

Usage:
  python -m tools.crossfam_review.run                 # preflight only (free)
  python -m tools.crossfam_review.run --run           # full paid review, print issues
  python -m tools.crossfam_review.run --run --live    # full review + file issues
  python -m tools.crossfam_review.run --run --max-shards 1 --only gemini-2.5-flash-lite
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

from tools.crossfam_review import client as OR
from tools.crossfam_review import council as C
from tools.crossfam_review import dedup as D
from tools.crossfam_review import finder as F
from tools.crossfam_review import github_sink as GH
from tools.crossfam_review import shards as S
from tools.crossfam_review.findings import Finding, dedup_key
from tools.crossfam_review.roster import FINDERS, JUDGES
from tools.crossfam_review.spend import BudgetExceeded, SpendGuard

_MISSING = object()   # sentinel: a legacy record whose category can't be resolved (see _completed_keys)

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
    # Render each shard's payload ONCE (it's byte-identical for all finders) instead of re-reading and
    # re-numbering every file once per (model, shard) — with 10 finders that was 10× the disk I/O.
    rendered = {s.shard_id: s.render() for s in shard_list}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(F.run_finder, m, s, guard, rendered[s.shard_id]): (m, s) for m, s in tasks}
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
        # Rotation index is derived from each candidate's OWN identity, not its list position, so the
        # voter/tiebreaker triple is stable whether judged in a full run or a --resume-council subset.
        futs = {pool.submit(C.adjudicate, c, C.stable_rotation_index(c), guard): c for c in candidates}
        done = 0
        for fut in as_completed(futs):
            try:
                adj = fut.result()
            except OR.BillingAuthError as e:
                # Dead key/balance: cancel every not-yet-started judge call so shutdown(wait=True)
                # doesn't run them all against the dead key. In-flight ones fail fast on the same 401/402.
                print(f"\n✗ billing/auth failure — halting council: {e}")
                for f in futs:
                    f.cancel()
                break
            adjs.append(adj)
            done += 1
            mark = "✓CONFIRMED" if adj.confirmed else "✗refuted"
            print(f"  [{done}/{len(candidates)}] {mark:11} {adj.candidate.severity:8} "
                  f"{adj.candidate.file}:{adj.candidate.line}  ${guard.settled():.3f}", flush=True)
    return adjs


def file_payloads(outdir, payloads, stamp: str, live: bool, pace: float = 2.0) -> list:
    """File a list of IssuePayload objects, paced + rate-limit aware. THE single filing path — used by
    both the main `--run --live` flow and `--file-only`, so neither can spray GitHub's secondary rate
    limit (~20-30/min) unpaced. Skips fingerprints already on the tracker (idempotent), spaces live
    creates `pace` apart, backs off 60s + retries once on a secondary-rate-limit rejection, and
    checkpoints issues.json after each create so a crash mid-batch loses nothing."""
    import time
    GH.ensure_label(stamp, live)
    already = GH.existing_fingerprints(stamp, live)
    todo = [p for p in payloads if p.fingerprint not in already]
    print(f"filing {len(todo)} of {len(payloads)} payloads (live={live}, {len(already)} already on "
          f"tracker) under '{GH.campaign_label(stamp)}'")
    filed = []
    for i, payload in enumerate(todo, 1):
        out = GH.create_issue(payload, live=live)
        if live and "error" in out and "rate limit" in (out.get("error", "").lower()):
            print("  ⏳ secondary rate limit — backing off 60s…", flush=True)
            time.sleep(60)
            out = GH.create_issue(payload, live=live)
        filed.append(out)
        tag = out.get("url") or out.get("error") or out.get("title", "")
        print(f"  [{i}/{len(todo)}] {'✓' if 'url' in out or not live else '✗'} {tag[:88]}", flush=True)
        (outdir / "issues.json").write_text(json.dumps(filed, indent=2))   # checkpoint each write
        if live and i < len(todo):
            time.sleep(pace)
    ok = sum(1 for o in filed if "url" in o or o.get("dry_run"))
    print(f"\n{'filed' if live else 'would file'} {ok}/{len(todo)} issues"
          + (f" ({len(filed) - ok} errored — re-run --file-only to retry)" if ok < len(filed) else ""))
    return filed


def _file_only(outdir, stamp: str, live: bool) -> int:
    """File issues from a prior run's persisted issue_payloads.json (no paid calls) via `file_payloads`."""
    src = outdir / "issue_payloads.json"
    if not src.exists():
        print(f"✗ no {src} — run the review first (dry) to produce it.")
        return 1
    saved = json.loads(src.read_text())
    payloads = [GH.IssuePayload(title=p["title"], body=p["body"], labels=p["labels"],
                                fingerprint=p["fingerprint"]) for p in saved]
    file_payloads(outdir, payloads, stamp, live)
    return 0


def _adj_record(a) -> dict:
    """One adjudication -> receipt dict. Carries `category` so `_completed_keys` can key on the full
    dedup identity (older receipts without it are backfilled by summary-match in `_resume_council`)."""
    return {"file": a.candidate.file, "line": a.candidate.line, "category": a.candidate.category,
            "confirmed": a.confirmed, "escalated": a.escalated, "summary": a.candidate.summary,
            "verdicts": [{"judge": v.judge, "role": v.role, "verdict": v.verdict, "reason": v.reason}
                         for v in a.verdicts]}


def _real_votes(adj: dict) -> int:
    return sum(1 for v in adj.get("verdicts", []) if v["verdict"] in ("confirmed", "refuted"))


def _record_category(a: dict, sig_to_cat: dict):
    """A record's category, or a backfill from `sig_to_cat` for legacy receipts that predate the field,
    or `_MISSING` if it can't be resolved. Returning `_MISSING` (rather than defaulting to "") is what
    prevents two different-category legacy records in the same line-bucket from BOTH keying to
    (file, bucket, "") and colliding — a collision would silently mark one 'done' and never re-judge it."""
    cat = a.get("category")
    if cat is not None:
        return cat
    return sig_to_cat.get((a["file"], a["line"], a.get("summary", "")), _MISSING)


def _completed_keys(records: list, sig_to_cat: dict) -> set:
    """Full dedup keys `(file, line-bucket, category)` that were GENUINELY judged (>=2 real votes). A
    candidate whose judge calls were refused at the cap (force-refuted on errors) is NOT complete and
    must be re-judged. A legacy record whose category can't be resolved is SKIPPED (left out of `done`)
    so it gets re-judged — the conservative choice: better to re-judge (and pay) than to silently drop
    a real un-judged candidate via an ambiguous "" key collision."""
    done = set()
    for a in records:
        if _real_votes(a) < 2:
            continue
        cat = _record_category(a, sig_to_cat)
        if cat is _MISSING:
            continue
        done.add(dedup_key(a["file"], a["line"], cat))
    return done


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
    # (file,line,summary)->category, to backfill category onto older receipts that predate the field.
    sig_to_cat = {(c.file, c.line, c.summary): c.category for c in corroborated}
    prior = json.loads((outdir / "adjudications.json").read_text()) if (outdir / "adjudications.json").exists() else []
    done = _completed_keys(prior, sig_to_cat)
    remaining = [c for c in corroborated if dedup_key(c.file, c.line, c.category) not in done]
    print(f"resume: {len(corroborated)} corroborated (≥{args.min_agree}); "
          f"{len(done)} genuinely judged already; re-/newly judging {len(remaining)} "
          f"(incl. budget-starved) under cap ${args.cap:.2f}")
    if not remaining:
        print("nothing left to adjudicate.")
        return 0

    new_adjs = run_council(remaining, guard, args.workers)
    new_conf = [a for a in new_adjs if a.confirmed]

    # Merge adjudications by full dedup key: a re-judged candidate OVERWRITES its prior budget-starved
    # record rather than duplicating it (the receipt stays one row per candidate). Backfill category on
    # prior records so their keys align with the new ones.
    by_key = {}
    for a in prior:
        cat = _record_category(a, sig_to_cat)
        if cat is _MISSING:
            # Can't resolve this legacy record's category; keep it verbatim under a summary-disambiguated
            # key so it never collides with (or overwrites) a real (file, bucket, category) entry.
            by_key[("~unkeyed", a["file"], a.get("line"), a.get("summary", ""))] = a
            continue
        a = a if a.get("category") is not None else {**a, "category": cat}
        by_key[dedup_key(a["file"], a["line"], cat)] = a
    for a in new_adjs:
        by_key[dedup_key(a.candidate.file, a.candidate.line, a.candidate.category)] = _adj_record(a)
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
    outdir = RECEIPTS / f"crossfam-{args.stamp}"

    # Non-preflight modes that operate on a PRIOR run's receipts — dispatched before the preflight gate
    # (they don't need --run; the paid full review does). file-only makes no paid calls; resume-council
    # does, so it still needs a key + guard.
    if args.file_only:
        return _file_only(outdir, args.stamp, args.live)
    if args.resume_council:
        if not OR.has_key():
            print("✗ no OPENROUTER_API_KEY — cannot resume the paid council.")
            return 1
        outdir.mkdir(parents=True, exist_ok=True)
        return _resume_council(outdir, shard_area, args, SpendGuard(args.cap))

    if not args.run:
        return preflight(shard_list, args.cap)

    if not OR.has_key():
        print("✗ no OPENROUTER_API_KEY — cannot run. (Set it or use preflight.)")
        return 1

    guard = SpendGuard(args.cap)
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    outdir.mkdir(parents=True, exist_ok=True)

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
    (outdir / "adjudications.json").write_text(json.dumps([_adj_record(a) for a in adjs], indent=2))
    print(f"\nconfirmed: {len(confirmed)}/{len(adjs)} · total spend ${guard.settled():.3f}")

    # 4. File issues — build every payload FIRST and persist it, so a filing failure (rate limit,
    # network, a gh hiccup) after a ~$10+ paid review can be replayed from disk without re-paying.
    payloads = [GH.build_payload(a, args.stamp)
                for a in sorted(confirmed, key=lambda a: (a.candidate.severity, a.candidate.file))]
    (outdir / "issue_payloads.json").write_text(json.dumps(
        [{"title": p.title, "body": p.body, "labels": p.labels, "fingerprint": p.fingerprint}
         for p in payloads], indent=2))
    filed = file_payloads(outdir, payloads, args.stamp, args.live)
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
