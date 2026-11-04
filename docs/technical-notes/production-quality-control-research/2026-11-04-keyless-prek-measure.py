"""Pre-K teachers in districts whose CCD school files carry no Pre-K key (#1040; review #1097-#1106).

Read-only. Reads the LCT DB (Docker up): staff_counts (LEA file), districts, ccd_school_staffing
(school files, loaded by #1039), enrollment_by_grade. Findings and decisions: the plan note's
"Pre-K without a school key" section (2026-11-01-school-file-band-scopes-plan.md).

THE UNIVERSE, stated once, because the first Michigan sizing drifted on every one of these (#1097,
#1098, #1100):
  * LEA Pre-K FTE is REAL: `staff_counts.teachers_prek` is a number, not the 'NaN' placeholder the
    LEA importer writes for blank/Missing/Not reported cells (Postgres orders 'NaN' above every
    number, so `teachers_prek > 0` selects it: the #1098 bug).
  * LCT-eligible: `districts.is_shared_service_entity` is not true — the same column
    calculate_lct_variants filters on. Shared-service LEAs (ISDs, RESAs, CTCs) never publish (#1097).
  * KEY-LESS: the district's school rows carry no Pre-K membership (Σ memb_pk is NULL or 0), so D3's
    allocation by school Pre-K membership is 0/0. Any state, not only Michigan (#1102).
  * Placement test, inside FIRST (#1100), at tolerance TOL:
      inside   |Σ school / LEA total − 1| ≤ TOL
      outside  not inside, LEA total − Pre-K > 0, and |Σ school / (LEA total − Pre-K) − 1| ≤ TOL
      neither  otherwise. A district whose whole LEA total is Pre-K can only be inside or neither.

Sections (each prints NOTHING MEASURED on an empty input, never a green zero):
  U  universe counts                         C  calibration where Pre-K is inside by rule
  K  key-less districts by state             P  placement classes, both vintages
  N  permutation null for "outside"          A  two-year agreement and its null
  F  feasibility of the subtraction          B  bounds for the "neither" districts
  M  Michigan districts with Pre-K students and Pre-K FTE exactly 0 (the D3 flag)

Run: python3 docs/technical-notes/production-quality-control-research/2026-11-04-keyless-prek-measure.py
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict

from sqlalchemy import text

from infrastructure.database.connection import session_scope
from infrastructure.utilities.grade_bands import primary_bands_for

YEARS = ("2023-24", "2024-25")
TOL = 0.001
PERMUTATIONS = 2000
SEED = 1040


def _num(v):
    """A real number, or None for NULL and the 'NaN' placeholder."""
    if v is None:
        return None
    x = float(v)
    return None if math.isnan(x) else x


def load(session, year):
    leas = {}
    for did, state, shared, t, pk in session.execute(text(
            "SELECT s.district_id, d.state, coalesce(d.is_shared_service_entity, false), s.teachers_total, s.teachers_prek "
            "FROM staff_counts s JOIN districts d ON d.nces_id = s.district_id "
            "WHERE s.source_year = :y AND s.data_source = 'nces_ccd'"), {"y": year}):
        leas[did] = {"state": state, "shared": bool(shared), "t": _num(t), "pk_raw": pk, "pk": _num(pk)}
    schools = defaultdict(list)
    for leaid, fte, pkm, kg, level, gslo, gshi in session.execute(text(
            "SELECT leaid, teachers_fte, memb_pk, memb_kg, level, gslo, gshi FROM ccd_school_staffing "
            "WHERE source_year = :y"), {"y": year}):
        schools[leaid].append({"fte": _num(fte), "pkm": pkm, "kg": kg or 0, "level": level, "gslo": gslo, "gshi": gshi})
    lea_pk_students = dict(session.execute(text(
        "SELECT district_id, enrollment_prek FROM enrollment_by_grade WHERE source_year = :y"), {"y": year}).all())
    return leas, schools, lea_pk_students


def classify(s, t, pk, tol=TOL):
    if t and t > 0 and abs(s / t - 1) <= tol:
        return "inside"
    if t is not None and t - pk > 0 and abs(s / (t - pk) - 1) <= tol:
        return "outside"
    return "neither"


def rows_for(year, leas, schools):
    """One record per LEA with real Pre-K FTE > 0 and school rows: the frame every section reads."""
    out = []
    for did, lea in leas.items():
        if lea["pk"] is None or lea["pk"] <= 0 or lea["t"] is None or lea["t"] <= 0 or did not in schools:
            continue
        sch = schools[did]
        s = sum(x["fte"] for x in sch if x["fte"] is not None)
        keyless = not any((x["pkm"] or 0) > 0 for x in sch)
        out.append({"did": did, "state": lea["state"], "shared": lea["shared"], "t": lea["t"], "pk": lea["pk"],
                    "s": s, "keyless": keyless, "schools": sch})
    return out


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def main():
    rng = random.Random(SEED)
    with session_scope() as session:
        data = {y: load(session, y) for y in YEARS}
    frames = {y: rows_for(y, *data[y][:2]) for y in YEARS}
    if not any(frames.values()):
        print("NOTHING MEASURED — no LEA with real Pre-K FTE and school rows (is ccd_school_staffing loaded?)")
        return

    for y in YEARS:
        leas = data[y][0]
        nan = sum(1 for v in leas.values() if v["pk_raw"] is not None and v["pk"] is None)
        real = sum(1 for v in leas.values() if (v["pk"] or 0) > 0)
        print(f"\n== U [{y}] LEAs in staff_counts {len(leas):,}; Pre-K FTE 'NaN' {nan:,} (excluded); real Pre-K FTE > 0 {real:,}")
        f = frames[y]
        print(f"   with school rows {len(f):,}; LCT-eligible {sum(not r['shared'] for r in f):,}; "
              f"key-less {sum(r['keyless'] for r in f):,} (eligible {sum(r['keyless'] and not r['shared'] for r in f):,})")

    # C — calibration: districts WITH a school Pre-K key, where Pre-K is inside the school counts by rule.
    f = [r for r in frames["2024-25"] if not r["keyless"] and not r["shared"] and r["t"] >= 5]
    if not f:
        print("\n== C NOTHING MEASURED")
    else:
        e = [abs(r["s"] / r["t"] - 1) for r in f]
        short = [r for r in f if r["s"] < r["t"] * (1 - TOL)]
        chance = [r for r in short if classify(r["s"], r["t"], r["pk"]) == "outside"]
        print(f"\n== C [2024-25] keyed, eligible, ≥5 teachers: n={len(f):,}; |Σschool/LEA−1| p50 {100*pct(e,.5):.2f}% "
              f"p90 {100*pct(e,.9):.2f}% p95 {100*pct(e,.95):.2f}%; within {TOL:.1%}: {100*sum(x<=TOL for x in e)/len(e):.1f}%")
        print(f"   chance 'outside' match: {sum(classify(r['s'],r['t'],r['pk'])=='outside' for r in f)/len(f):.2%} of all; "
              f"{len(chance)} of {len(short):,} = {len(chance)/max(1,len(short)):.1%} of districts WITH a school shortfall")

    # K — key-less districts by state
    k = [r for r in frames["2024-25"] if r["keyless"] and not r["shared"]]
    by = Counter(r["state"] for r in k)
    fte = defaultdict(float)
    for r in k:
        fte[r["state"]] += r["pk"]
    print(f"\n== K [2024-25] key-less eligible LEAs: {len(k):,}, Pre-K FTE {sum(fte.values()):,.1f}; "
          f"MI {by.get('MI',0)} ({fte.get('MI',0):,.1f}); elsewhere {len(k)-by.get('MI',0)} ({sum(fte.values())-fte.get('MI',0):,.1f})")
    print("   top states:", ", ".join(f"{s} {n} ({fte[s]:,.0f})" for s, n in by.most_common(10)))

    # P / N / A — placement classes on key-less eligible LEAs, both years, plus the permutation null
    cls = {}
    for y in YEARS:
        k = [r for r in frames[y] if r["keyless"] and not r["shared"]]
        if not k:
            print(f"\n== P [{y}] NOTHING MEASURED")
            continue
        c = {r["did"]: classify(r["s"], r["t"], r["pk"]) for r in k}
        cls[y] = c
        tally, tfte = Counter(c.values()), defaultdict(float)
        for r in k:
            tfte[c[r["did"]]] += r["pk"]
        zero = sum(1 for r in k if r["t"] - r["pk"] <= 0)
        print(f"\n== P [{y}] key-less eligible {len(k)}: " + ", ".join(f"{n} {tally[n]} ({tfte[n]:,.1f} FTE)" for n in ("inside", "outside", "neither"))
              + f"; LEA total = Pre-K (outside undefined): {zero}")
        pks = [r["pk"] for r in k]
        null = []
        for _ in range(PERMUTATIONS):
            rng.shuffle(pks)
            null.append(sum(classify(r["s"], r["t"], p) == "outside" for r, p in zip(k, pks)))
        print(f"== N [{y}] outside observed {tally['outside']}; permutation null mean {sum(null)/len(null):.1f}, "
              f"p95 {pct(null,.95)}, max {max(null)}")
    if len(cls) == 2:
        both = set(cls[YEARS[0]]) & set(cls[YEARS[1]])
        agree = [d for d in both if cls[YEARS[0]][d] == cls[YEARS[1]][d] == "outside"]
        # null for two-year agreement: shuffle each year's Pre-K independently over the LEAs present in both
        ks = {y: {r["did"]: r for r in frames[y] if r["did"] in both} for y in YEARS}
        null2 = []
        for _ in range(PERMUTATIONS):
            hits = None
            for y in YEARS:
                ids = sorted(ks[y])
                pks = [ks[y][d]["pk"] for d in ids]
                rng.shuffle(pks)
                o = {d for d, p in zip(ids, pks) if classify(ks[y][d]["s"], ks[y][d]["t"], p) == "outside"}
                hits = o if hits is None else hits & o
            null2.append(len(hits))
        moved = Counter((cls[YEARS[0]][d], cls[YEARS[1]][d]) for d in both)
        print(f"\n== A key-less eligible in both years {len(both)}; outside in BOTH {len(agree)} "
              f"(null mean {sum(null2)/len(null2):.2f}, p95 {pct(null2,.95)}, max {max(null2)})")
        print("   transitions 2023-24 → 2024-25:", ", ".join(f"{a}→{b} {n}" for (a, b), n in moved.most_common()))

    # F — feasibility of subtracting Pre-K before the grade split, from the host schools
    k = [r for r in frames["2024-25"] if r["keyless"] and not r["shared"]]
    if k:
        infeasible, no_host_pk, hosts_kind = [], 0, Counter()
        for r in k:
            pk_hosts = [x for x in r["schools"] if x["gslo"] == "PK" and x["fte"]]
            el_hosts = [x for x in r["schools"] if x["fte"] and "elementary" in (primary_bands_for(x["level"], x["gslo"], x["gshi"]) or set())]
            hosts = pk_hosts or el_hosts
            hosts_kind["PK-offering" if pk_hosts else "elementary-band" if el_hosts else "none"] += 1
            host_fte = sum(x["fte"] for x in hosts)
            if r["pk"] > host_fte:
                infeasible.append((r["did"], r["state"], r["pk"], host_fte))
        print(f"\n== F [2024-25] key-less eligible {len(k)}; host schools: {dict(hosts_kind)}; "
              f"Pre-K FTE exceeds the hosts' whole FTE in {len(infeasible)} LEAs ({sum(x[2] for x in infeasible):,.1f} Pre-K FTE)")
        for did, st, pk, h in sorted(infeasible, key=lambda x: -x[2])[:8]:
            print(f"   {did} {st} Pre-K {pk:.2f} vs host FTE {h:.2f}")

    # B — bounds on the Pre-K inside the school counts for the neither districts
    k = [r for r in frames["2024-25"] if r["keyless"] and not r["shared"] and cls.get("2024-25", {}).get(r["did"]) == "neither"]
    if k:
        width = sum(min(r["pk"], max(0.0, r["t"] - r["s"])) for r in k)
        gap_ge = [r for r in k if r["t"] - r["s"] >= r["pk"]]
        print(f"\n== B [2024-25] neither {len(k)} LEAs, Pre-K FTE {sum(r['pk'] for r in k):,.1f}; bound width "
              f"Σ min(pk, gap) {width:,.1f}; shortfall ≥ Pre-K in {len(gap_ge)} ({sum(r['pk'] for r in gap_ge):,.1f} FTE)")

    # M — the D3 flag's students: Michigan LEAs with Pre-K students (LEA file) and Pre-K FTE exactly 0
    leas, _, pkst = data["2024-25"]
    m = [(d, pkst.get(d)) for d, v in leas.items() if v["state"] == "MI" and v["pk"] == 0 and (pkst.get(d) or 0) > 0]
    print(f"\n== M [2024-25] MI LEAs with LEA-file Pre-K students and Pre-K FTE = 0: {len(m)} "
          f"({sum(int(n) for _, n in m):,} students)" if m else "\n== M NOTHING MEASURED (no such LEA)")


if __name__ == "__main__":
    main()
