#!/usr/bin/env python3
"""T6 (#1004) step 1: per-LEA self-contained share vs the state share. READ-ONLY.

The decision input for #1004's methodology call. Writes nothing. Imports the production parser
(import_sped_baseline.read_lea_environments) and estimator (apply_sped_estimates.load_baseline_ratios /
estimate_district / select_year_totals; calculate_lct_variants.calculate_lct) — never re-derives them.

Compares, on the APPLIED baseline (SPED_BASELINE_YEAR) and the NCES_PRIMARY_YEAR districts:
  STATE   production today — every district gets its state's self-contained share
  LEA     a district whose IDEA LEA environments row publishes a share (total AND both self-contained
          cells real counts; -8/-9/blank suppression is missing, never 0) uses its own; others, state

Check-map:
  C0  harness control: the STATE run must reproduce every stored non-CA SPED scope value (0 differences)
      — no LEA number is reported off a harness that does not reproduce production.
  C1  coverage: LEAs with a share; districts estimated with one; SPED students (school age) they hold.
  C2  LEA share vs its state's share: distribution of the difference, by LEA school-age SPED size band
      (small-n LEAs are noisy: a 5-student LEA's share is 0, .2, .4 ...).
  C3  scope movement STATE → LEA: Σ self-contained, n / mean / median / capped for each SPED scope.

Verdicts: NOTHING MEASURED (empty input), HARNESS BROKEN (C0), else MEASURED.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import text  # noqa: E402

from infrastructure.database.connection import session_scope  # noqa: E402
from infrastructure.database.migrations.apply_sped_estimates import (  # noqa: E402
    estimate_district, load_baseline_ratios, select_year_totals,
)
from infrastructure.database.migrations.import_sped_baseline import read_lea_environments  # noqa: E402
from infrastructure.database.migrations.sped_baseline_profiles import FEDERAL_DIR  # noqa: E402
from infrastructure.scripts.analyze.calculate_lct_variants import calculate_lct  # noqa: E402
from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR, SPED_BASELINE_YEAR  # noqa: E402

LEA_ENV_FILE = FEDERAL_DIR / "idea-618/2024_25/beducationalenvironmentslea2024-25.csv"
CAP = 360.0
SCOPES = ("core_sped", "teachers_gened", "instructional_sped")


def nothing(what):
    raise SystemExit(f"VERDICT: NOTHING MEASURED — {what}")


def scopes(est, minutes):
    """The three SPED scopes as calculate_lct_variants forms them (360 cap, low confidence skipped)."""
    if est is None or est.confidence == "low":
        return {}
    out = {}
    if est.sped_teachers > 0 and est.self_contained > 0:
        out["core_sped"] = min(calculate_lct(minutes, est.sped_teachers, est.self_contained), CAP)
    if est.gened_teachers > 0 and est.gened_enrollment > 0:
        out["teachers_gened"] = min(calculate_lct(minutes, est.gened_teachers, est.gened_enrollment), CAP)
    if est.sped_instructional and est.sped_instructional > 0 and est.self_contained > 0:
        out["instructional_sped"] = min(calculate_lct(minutes, est.sped_instructional, est.self_contained), CAP)
    return out


def main():
    envs = read_lea_environments(LEA_ENV_FILE)
    shares = {k: v.share for k, v in envs.items() if v.share is not None}
    if not shares:
        nothing("no LEA publishes a self-contained share")
    with session_scope() as s:
        ratios = load_baseline_ratios(s, SPED_BASELINE_YEAR)
        districts = select_year_totals(s, NCES_PRIMARY_YEAR) or nothing(f"no districts for {NCES_PRIMARY_YEAR}")
        stored = s.execute(text(
            "SELECT district_id, staff_scope, lct_value, instructional_minutes, notes, year FROM lct_calculations "
            "WHERE grade_level IS NULL AND staff_scope IN ('core_sped','teachers_gened','instructional_sped','teachers_only')"
        )).all() or nothing("no lct_calculations rows")

    minutes = {d: int(m) for d, sc, _l, m, _n, y in stored if sc == "teachers_only" and y == NCES_PRIMARY_YEAR}
    runs = {"STATE": ratios, "LEA": ratios._replace(lea_self_contained=shares)}
    per = {name: {d.nces_id: (estimate_district(d, r), d) for d in districts if d.nces_id in minutes}
           for name, r in runs.items()}

    print("# T6 step 1 — per-LEA self-contained share (#1004)\n")
    print(f"Baseline {SPED_BASELINE_YEAR}; {len(per['STATE']):,} {NCES_PRIMARY_YEAR} districts with minutes\n")
    # ------------------------------------------------------------ C0
    compared = mism = 0
    for d, sc, lct, _m, notes, y in stored:
        if sc == "teachers_only" or y != NCES_PRIMARY_YEAR or "ca_actual" in (notes or "") or d not in per["STATE"]:
            continue
        mine = scopes(per["STATE"][d][0], minutes[d]).get(sc)
        compared += 1
        mism += mine is None or abs(mine - float(lct)) > 0.005
    print(f"## C0 harness control\n- STATE in-memory vs stored SPED scopes: {compared:,} compared, {mism} differ")
    if not compared:
        nothing("C0 compared nothing")
    if mism:
        print("\nVERDICT: HARNESS BROKEN — no LEA number is reported.")
        sys.exit(2)

    # ------------------------------------------------------------ C1
    sa_all = sum(v.total or 0 for v in envs.values())
    sa_cov = sum(envs[k].total for k in shares)
    used = sum(1 for e, _ in per["LEA"].values() if e and e.method == "lea_self_contained_ratio")
    print("\n## C1 coverage")
    print(f"- LEAs with a share: {len(shares):,} of {len(envs):,}; they hold {sa_cov:,} of {sa_all:,} school-age "
          f"SPED students (**{sa_cov / sa_all:.1%}**)")
    print(f"- {NCES_PRIMARY_YEAR} districts estimated on their own share: {used:,} of {len(per['LEA']):,} "
          f"(national-fallback states use the LEA share too when one exists)")

    # ------------------------------------------------------------ C2
    print("\n## C2 LEA share − state share, by LEA school-age SPED size")
    print("| SPED students | LEAs | median diff | p10 | p90 | share = 0 |")
    print("|---|---|---|---|---|---|")
    state_of = {d.nces_id: d.state for _, d in per["STATE"].values()}
    bands = [(0, 50), (50, 200), (200, 1000), (1000, 10**9)]
    for lo, hi in bands:
        diffs = sorted(shares[k] - ratios.self_contained.get(state_of[k], ratios.national["self_contained_ratio"])
                       for k in shares if k in state_of and lo <= envs[k].total < hi)
        if not diffs:
            continue
        q = lambda f: diffs[int(f * (len(diffs) - 1))]
        print(f"| {lo:,}–{hi if hi < 10**9 else '∞'} | {len(diffs):,} | {q(.5):+.3f} | {q(.1):+.3f} | {q(.9):+.3f} | "
              f"{sum(1 for k in shares if k in state_of and lo <= envs[k].total < hi and shares[k] == 0):,} |")

    # ------------------------------------------------------------ C3
    print("\n## C3 scope movement STATE → LEA")
    print("| run | Σ self-contained | Σ SPED teachers | scope | n | mean | median | capped at 360 |")
    print("|---|---|---|---|---|---|---|---|")
    for name, rows in per.items():
        ests = [e for e, _ in rows.values() if e]
        sc_sum, t_sum = sum(e.self_contained for e in ests), sum(e.sped_teachers for e in ests)
        for scope in SCOPES:
            v = [x[scope] for x in (scopes(e, minutes[d.nces_id]) for e, d in rows.values()) if scope in x]
            print(f"| {name} | {sc_sum:,} | {t_sum:,.0f} | {scope} | {len(v):,} | {statistics.mean(v):.2f} | "
                  f"{statistics.median(v):.2f} | {sum(1 for x in v if x >= CAP):,} |")
    print("\nVERDICT: MEASURED")


if __name__ == "__main__":
    main()
