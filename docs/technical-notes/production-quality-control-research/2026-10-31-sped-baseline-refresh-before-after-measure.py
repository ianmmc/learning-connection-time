#!/usr/bin/env python3
"""T4 (#1002): before/after measurement for the IDEA 618 / CRDC SPED baseline refresh. READ-ONLY.

The decision input for T5 (#1003). Writes nothing. Imports the production parse, ratio and estimate
functions (import_sped_baseline.build_state_baselines / aggregate_crdc_rows / build_crdc_lea_baselines
/ read_ccd_lea_totals; apply_sped_estimates.ratios_from_rows / estimate_district / select_year_totals;
calculate_lct_variants.calculate_lct) and never re-derives a ratio.

Needs the LCT DB at migration 029 (#999) — run with POSTGRES_DB pointed at a migrated copy until the
live DB is migrated.

Runs compared (all estimate the same 2024-25 districts — select_year_totals(NCES_PRIMARY_YEAR)):
  OLD          the stored 2017-18 baseline rows (what production applies today)
  NEW 6-21     the 2024-25 set, school-age band 6-21 (the 2017-18 definition; the child count still
               carries the column — personnel does not, so its School Age FTE serve 5-21)
  NEW 5-21     the 2024-25 set, IDEA 'School Age' (kindergarten 5-year-olds included)
  … /crdc-den  either NEW band with every LEA share divided by its CRDC total (same schools as the
               numerator) instead of CCD — the #960 pairwise rule applied to all LEAs, not only partial

Check-map:
  C0  harness control. The OLD in-memory run must REPRODUCE the stored core_sped / teachers_gened /
      instructional_sped lct_value for every district whose stored row came from the estimate (CA
      actual-enrollment overrides excluded), and the non-SPED `instructional` scope must recompute
      from its stored inputs. Any mismatch → HARNESS BROKEN, and no "after" number is reported.
  C1  per-state ratios OLD vs NEW (self-contained share; SPED teachers and teachers+paras per
      self-contained student) — national means + the largest movers.
  C2  the kindergarten-5-year-old share of school-age SPED, national and per state (definition shift).
  C3  in-memory apply on each run: Σ self-contained / SPED teachers / GenEd teachers, negative-GenEd
      count, and each SPED scope's n / mean / median / count capped at 360.
  C4  CRDC 2023-24 M+F vs CCD 2023-24 K-12 membership (the nonbinary-undercount check), and the LEA
      SPED share under the CCD vs CRDC-own denominator.
  C5  ESSER check: SPED teacher+para FTE growth 2017-18 → 2023-24 vs school-age SPED child-count growth
      2017-18 → 2024-25. 2023-24 personnel predates the ESSER cliff (~Sept 2024) and may overstate
      staffing paired with 2024-25 enrollment.

Verdicts: NOTHING MEASURED (empty input anywhere), HARNESS BROKEN (C0 failed), else MEASURED.
"""

from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import text  # noqa: E402

from infrastructure.database.connection import session_scope  # noqa: E402
from infrastructure.database.migrations import import_sped_baseline as isb  # noqa: E402
from infrastructure.database.migrations.apply_sped_estimates import (  # noqa: E402
    estimate_district, load_baseline_ratios, ratios_from_rows, select_year_totals,
)
from infrastructure.database.migrations.sped_baseline_profiles import PROFILE_2017_18, PROFILE_2024_25  # noqa: E402
from infrastructure.database.models import SpedLeaBaseline, SpedStateBaseline  # noqa: E402
from infrastructure.scripts.analyze.calculate_lct_variants import calculate_lct  # noqa: E402
from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR, SPED_BASELINE_YEAR  # noqa: E402

CAP = 360.0
# OLD is the stored 2017-18 rows, pinned (#1014) — SPED_BASELINE_YEAR moved to 2024-25 at adoption (#1003),
# and a harness that followed it would compare the refreshed baseline with itself. The C0 control is the
# APPLIED vintage (SPED_BASELINE_YEAR, whatever it is today): its stored rows through the production
# estimator must reproduce the stored SPED scopes — a verdict that is a function of the state, before
# or after adoption, not of when the script was written.
OLD_YEAR = PROFILE_2017_18.baseline_year
SCOPES = ("core_sped", "teachers_gened", "instructional_sped")


class NothingMeasured(SystemExit):
    def __init__(self, what):
        super().__init__(f"VERDICT: NOTHING MEASURED — {what}")


def need(rows, what):
    if not rows:
        raise NothingMeasured(what)
    return rows


def capped(v):
    return None if v is None else min(v, CAP)


def scope_values(est, minutes):
    """The three SPED scopes exactly as calculate_lct_variants forms them (cap at 360)."""
    if est is None or est.confidence == "low":
        return {}
    out = {}
    if est.sped_teachers > 0 and est.self_contained > 0:
        out["core_sped"] = capped(calculate_lct(minutes, est.sped_teachers, est.self_contained))
    if est.gened_teachers > 0 and est.gened_enrollment > 0:
        out["teachers_gened"] = capped(calculate_lct(minutes, est.gened_teachers, est.gened_enrollment))
    if est.sped_instructional and est.sped_instructional > 0 and est.self_contained > 0:
        out["instructional_sped"] = capped(calculate_lct(minutes, est.sped_instructional, est.self_contained))
    return out


def load_new_lea_rows():
    p = PROFILE_2024_25
    with open(p.crdc.path, encoding="utf-8-sig", newline="") as f:
        leas = isb.aggregate_crdc_rows(csv.DictReader(f))
    rows = isb.build_crdc_lea_baselines(p, leas)
    for lea_id, (n, _st, _nm) in isb.read_ccd_lea_totals(p.ccd.path).items():
        if lea_id in rows:
            rows[lea_id].ccd_total_enrollment = n
            rows[lea_id].calculate_ratio(prefer_crdc=False)    # the CCD-denominator variant, explicitly
    return rows


def crdc_denominator(lea_rows):
    """Variant: every LEA's share over its CRDC total (unsaved copies; the production rows are untouched)."""
    out = []
    for r in lea_rows.values():
        c = SpedLeaBaseline(lea_id=r.lea_id, state=r.state, crdc_sped_enrollment_total=r.crdc_sped_enrollment_total,
                            crdc_total_enrollment=r.crdc_total_enrollment, ccd_total_enrollment=r.ccd_total_enrollment,
                            crdc_schools_reserved=1)    # forces the same-schools denominator in calculate_ratio
        c.calculate_ratio()
        out.append(c)
    return out


def pct(a, b):
    return f"{(a / b - 1) * 100:+.1f}%" if b else "n/a"


def main():
    with session_scope() as s:
        old_states = need(s.query(SpedStateBaseline).filter(SpedStateBaseline.baseline_year == OLD_YEAR).all(),
                          f"no sped_state_baseline rows for {OLD_YEAR}")
        old_leas = need(s.query(SpedLeaBaseline).filter(SpedLeaBaseline.baseline_year == OLD_YEAR).all(),
                        f"no sped_lea_baseline rows for {OLD_YEAR}")
        districts = need(select_year_totals(s, NCES_PRIMARY_YEAR), f"no districts for {NCES_PRIMARY_YEAR}")
        stored = s.execute(text(
            "SELECT district_id, staff_scope, lct_value, instructional_minutes, instructional_staff, enrollment, "
            "notes, year FROM lct_calculations WHERE grade_level IS NULL AND staff_scope IN "
            "('core_sped','teachers_gened','instructional_sped','instructional','teachers_only')")).all()
        need(stored, "no lct_calculations rows")
        applied_ratios = load_baseline_ratios(s, SPED_BASELINE_YEAR)
        for r in old_states + old_leas:
            s.expunge(r)

    minutes, stored_sped, control = {}, {}, []
    for did, scope, lct, mins, staff, enr, notes, year in stored:
        if scope == "teachers_only":
            minutes[did] = (int(mins), year)
        elif scope == "instructional":
            control.append((float(lct), calculate_lct(mins, staff, enr)))
        elif "ca_actual" not in (notes or ""):   # the CA override is recorded in notes (enrollment_source is NULL)
            stored_sped[(did, scope)] = (float(lct), year)
    need(minutes, "no teachers_only minutes")
    need(control, "no instructional control rows")

    new_leas = load_new_lea_rows()
    runs = {"OLD": (old_states, old_leas)}
    for band in ("6-21", "5-21"):
        states = list(isb.build_state_baselines(PROFILE_2024_25, band=band).values())
        runs[f"NEW {band}"] = (states, list(new_leas.values()))
        runs[f"NEW {band}/crdc-den"] = (states, crdc_denominator(new_leas))

    results = {}
    for name, (st_rows, lea_rows) in runs.items():
        year = OLD_YEAR if name == "OLD" else PROFILE_2024_25.baseline_year
        ratios = ratios_from_rows(year, st_rows, lea_rows)
        per = {}
        for d in districts:
            if d.nces_id not in minutes:
                continue
            est = estimate_district(d, ratios)
            per[d.nces_id] = (est, scope_values(est, minutes[d.nces_id][0]))
        results[name] = (ratios, per)

    # ---------------------------------------------------------------- C0 harness control
    print("# T4 before/after — SPED baseline refresh (#1002)\n")
    print(f"Districts estimated: {len(districts):,} ({NCES_PRIMARY_YEAR}); with minutes: "
          f"{sum(1 for d in districts if d.nces_id in minutes):,}\n")
    print("## C0 harness control")
    ctrl_bad = sum(1 for a, b in control if b is None or abs(a - b) > 1e-4)
    applied_per = {d.nces_id: scope_values(estimate_district(d, applied_ratios), minutes[d.nces_id][0])
                   for d in districts if d.nces_id in minutes}
    compared = mism = 0
    for (did, scope), (lct, year) in stored_sped.items():
        if year != NCES_PRIMARY_YEAR or did not in applied_per:
            continue
        mine = applied_per[did].get(scope)
        compared += 1
        if mine is None or abs(mine - lct) > 0.005:
            mism += 1
    print(f"- `instructional` control: {len(control):,} rows recomputed, {ctrl_bad} differ")
    print(f"- APPLIED baseline {SPED_BASELINE_YEAR} (stored rows, production estimator) vs stored SPED scopes "
          f"({NCES_PRIMARY_YEAR} rows, non-CA-actual): {compared:,} compared, {mism} differ (> 0.005 min)")
    if not compared:
        raise NothingMeasured("C0 compared 0 stored SPED rows")
    if ctrl_bad or mism:
        print("\nVERDICT: HARNESS BROKEN — the applied baseline does not reproduce production; "
              "no OLD/NEW number is reported.")
        sys.exit(2)

    # ---------------------------------------------------------------- C1 per-state ratios
    print("\n## C1 state ratios (unweighted mean across states; national fallback values)")
    print("| run | self-contained share | SPED teachers / SC student | teachers+paras / SC student |")
    print("|---|---|---|---|")
    for name in ("OLD", "NEW 6-21", "NEW 5-21"):
        n = results[name][0].national
        print(f"| {name} | {n['self_contained_ratio']:.4f} | {n['teacher_ratio']:.4f} | {n['instructional_ratio']:.4f} |")
    o, nw = results["OLD"][0], results["NEW 5-21"][0]
    movers = sorted(((abs(nw.teacher[s] / o.teacher[s] - 1), s) for s in o.teacher.keys() & nw.teacher.keys()), reverse=True)[:8]
    print("\nLargest teacher-ratio movers (OLD → NEW 5-21): " +
          ", ".join(f"{s} {o.teacher[s]:.3f}→{nw.teacher[s]:.3f}" for _, s in movers))
    gone = sorted(o.teacher.keys() - nw.teacher.keys())
    added = sorted(nw.teacher.keys() - o.teacher.keys())
    print(f"States with a teacher ratio only in OLD: {gone or 'none'}; only in NEW: {added or 'none'}")

    # ---------------------------------------------------------------- C2 kindergarten 5-year-olds
    cc = isb.read_child_count_file(PROFILE_2024_25.child_count)
    k5 = sum(t["age_5_school_age"] or 0 for t in cc.values())
    sa = sum(t["school_age"]["5-21"] for t in cc.values())
    need(sa, "no 2024-25 school-age count")
    shares = sorted(((t["age_5_school_age"] or 0) / t["school_age"]["5-21"], st) for st, t in cc.items() if t["school_age"]["5-21"])
    sc5 = sum(t["self_contained"]["5-21"] for t in cc.values())
    sc6 = sum(t["self_contained"]["6-21"] for t in cc.values())
    print("\n## C2 kindergarten 5-year-olds in 'School Age' (2024-25)")
    print(f"- national: {k5:,} of {sa:,} = **{k5 / sa:.2%}**; per state min {shares[0][0]:.2%} ({shares[0][1]}), "
          f"median {shares[len(shares) // 2][0]:.2%}, max {shares[-1][0]:.2%} ({shares[-1][1]})")
    print(f"- self-contained 5-21 {sc5:,} vs 6-21 {sc6:,} (5K self-contained {sc5 - sc6:,})")

    # ---------------------------------------------------------------- C3 in-memory apply
    print(f"\n## C3 in-memory apply to {NCES_PRIMARY_YEAR} districts")
    print("| run | estimated | Σ self-contained | Σ SPED teachers | Σ GenEd teachers | negative GenEd |")
    print("|---|---|---|---|---|---|")
    for name, (_r, per) in results.items():
        ests = [e for e, _ in per.values() if e]
        print(f"| {name} | {len(ests):,} | {sum(e.self_contained for e in ests):,} | "
              f"{sum(e.sped_teachers for e in ests):,.0f} | {sum(e.gened_teachers for e in ests):,.0f} | "
              f"{sum(1 for e in ests if e.gened_teachers < 0)} |")
    print("\n| run | scope | n | mean | median | capped at 360 |")
    print("|---|---|---|---|---|---|")
    for name, (_r, per) in results.items():
        for scope in SCOPES:
            v = [sv[scope] for _, sv in per.values() if scope in sv]
            if not v:
                print(f"| {name} | {scope} | 0 | — | — | — |")
                continue
            print(f"| {name} | {scope} | {len(v):,} | {statistics.mean(v):.2f} | {statistics.median(v):.2f} | "
                  f"{sum(1 for x in v if x >= CAP):,} |")
    print("\n(`instructional`, the non-SPED control, is unchanged by construction in every run — verified "
          "against its stored inputs in C0.)")

    # ---------------------------------------------------------------- C4 CRDC vs CCD
    print("\n## C4 CRDC 2023-24 vs CCD 2023-24")
    rec = isb.reconcile_crdc_with_ccd(PROFILE_2024_25, new_leas)
    print(f"- full-coverage Σ CRDC M+F / Σ CCD K-12: **{rec.ratio:.4f}** over {rec.n_compared:,} LEAs; "
          f"{rec.n_disagree:,} off by > 20%")
    for name in ("NEW 5-21", "NEW 5-21/crdc-den"):
        props = list(results[name][0].lea_proportion.values())
        print(f"- {name}: LEA SPED share mean {statistics.mean(props):.4f}, median {statistics.median(props):.4f} "
              f"over {len(props):,} LEAs")
    props_old = list(results["OLD"][0].lea_proportion.values())
    print(f"- OLD: LEA SPED share mean {statistics.mean(props_old):.4f}, median {statistics.median(props_old):.4f} "
          f"over {len(props_old):,} LEAs")

    # ---------------------------------------------------------------- C5 ESSER
    print("\n## C5 ESSER check (state totals, states present in both vintages)")
    old_by = {r.state: r for r in old_states}
    new_by = {r.state: r for r in runs["NEW 5-21"][0]}
    both = [st for st in old_by.keys() & new_by.keys()
            if old_by[st].sped_instructional_total and new_by[st].sped_instructional_total
            and old_by[st].sped_students_school_age and new_by[st].sped_students_school_age]
    need(both, "no state in both vintages")
    new621 = {r.state: r for r in runs["NEW 6-21"][0]}
    fte_o = sum(float(old_by[s].sped_instructional_total) for s in both)
    fte_n = sum(float(new_by[s].sped_instructional_total) for s in both)
    t_o = sum(float(old_by[s].sped_teachers_total or 0) for s in both)
    t_n = sum(float(new_by[s].sped_teachers_total or 0) for s in both)
    kids_o = sum(old_by[s].sped_students_school_age for s in both)
    kids_n621 = sum(new621[s].sped_students_school_age for s in both)
    kids_n521 = sum(new_by[s].sped_students_school_age for s in both)
    sc_o = sum(old_by[s].sped_students_self_contained or 0 for s in both)
    sc_n = sum(new_by[s].sped_students_self_contained or 0 for s in both)
    print(f"- {len(both)} states. SPED teacher FTE 2017-18 → 2023-24: {t_o:,.0f} → {t_n:,.0f} ({pct(t_n, t_o)}); "
          f"teachers + paras: {fte_o:,.0f} → {fte_n:,.0f} ({pct(fte_n, fte_o)})")
    print(f"- school-age SPED 2017-18 (6-21) → 2024-25: 6-21 {kids_o:,} → {kids_n621:,} ({pct(kids_n621, kids_o)}); "
          f"5-21 → {kids_n521:,} ({pct(kids_n521, kids_o)}); self-contained (5-21) {sc_o:,} → {sc_n:,} ({pct(sc_n, sc_o)})")
    print("\nVERDICT: MEASURED")


if __name__ == "__main__":
    main()
