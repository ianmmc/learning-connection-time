"""Stage 9 CLI — incorporate approved districts into the LCT production DB.

    python -m infrastructure.acquisition.stage9_incorporate <district_id> [<district_id> ...]
    python -m infrastructure.acquisition.stage9_incorporate --batch ids.txt
    python -m infrastructure.acquisition.stage9_incorporate 3620580 --dry-run
    python -m infrastructure.acquisition.stage9_incorporate 3620580 --force

Stage 9 is ungated/mechanical: it acts only on districts already approved at gate@8 (and not stale),
so an ineligible district is reported and skipped, not an error (use --strict to fail on ineligibility).
"""
from __future__ import annotations

import argparse
import sys

from infrastructure.acquisition.stage9_incorporate.incorporate import (
    incorporate_batch,
    incorporate_district,
)


def _load_ids(path: str) -> list:
    with open(path) as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="stage9_incorporate", description=__doc__)
    ap.add_argument("district_ids", nargs="*", help="NCES district IDs to incorporate")
    ap.add_argument("--batch", metavar="FILE", help="file of district IDs (one per line, # comments)")
    ap.add_argument("--actor", default="auto:stage9", help="attribution actor (default auto:stage9)")
    ap.add_argument("--dry-run", action="store_true", help="plan the writes, write nothing")
    ap.add_argument("--force", action="store_true", help="re-write even if the fingerprint is unchanged")
    ap.add_argument("--strict", action="store_true", help="fail on an ineligible district (single-id)")
    args = ap.parse_args(argv)

    ids = list(args.district_ids)
    if args.batch:
        ids += _load_ids(args.batch)
    if not ids:
        ap.error("no district IDs given (positional or --batch)")

    if len(ids) == 1:
        res = incorporate_district(ids[0], actor=args.actor, dry_run=args.dry_run,
                                   force=args.force, strict=args.strict)
        results = [res]
    else:
        results = incorporate_batch(ids, actor=args.actor, dry_run=args.dry_run, force=args.force)

    for r in results:
        line = f"{r.district_id}: {r.status}"
        if r.reason:
            line += f" ({r.reason})"
        if r.written:
            line += " — " + ", ".join(
                f"{w['grade_level']}={w['minutes']}[{w['method']}/{w['minutes_basis']}]"
                for w in r.written)
        print(line)

    return 0 if all(r.status not in ("error",) for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
