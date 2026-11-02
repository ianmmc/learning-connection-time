"""#1022 decision measurements (D1/D2, D3, D8) on the 2023-24 vintage — CCD school files + CRDC 2023-24.

Read-only, DB-free except M4 (IDEA state baseline). Imports the LIVE band predicate
(`school_sampling.primary_bands_for`) rather than re-spelling it. Findings: the plan note's
"Decision measurements" section (2026-11-01-school-file-band-scopes-plan.md).

  M1 (D1/D2)  teacher FTE by the pipeline's own school band (primary_bands_for): how much sits in
              single-band schools, and what grade spans the elementary band holds.
  M2 (D3)     Pre-K teachers: the school file carries only a total; compare the pro-rata PK estimate
              (school teachers x PK share of membership) with the LEA-reported Pre-K teacher count.
  M3 (D8)     CRDC SCH_FTETEACH_SPEDCERT at school grain against CCD school teachers and CRDC IDEA
              enrollment; PTRs by band with and without the subtraction.
  M4 (D8)     CRDC SPEDCERT summed by state against IDEA 618 personnel (assigned SPED teachers), same year.

Each section prints NOTHING MEASURED when its inputs are absent or empty, never a green zero.
Run: python3 docs/technical-notes/production-quality-control-research/2026-11-01-band-scope-decisions-measure.py
"""
import csv
import io
import subprocess
from collections import defaultdict
from pathlib import Path

import pandas as pd

from infrastructure.acquisition.common.school_sampling import primary_bands_for

REPO = Path(__file__).resolve().parents[3]
CCD = REPO / "data/raw/federal/nces-ccd/2023_24"
CRDC = REPO / "data/raw/federal/crdc/2023_24"
SCH029 = CCD / "ccd_sch_029_2324_w_1a_073124.zip"
SCH052 = CCD / "ccd_sch_052_2324_l_1a_073124.zip"     # Deflate64: read through `unzip -p`
SCH059 = CCD / "ccd_sch_059_2324_l_1a_073124.zip"
LEA059 = CCD / "ccd_lea_059_2324_l_1a_073124.csv"
OPEN = {"Open", "New", "Reopened", "Changed Boundary/Agency", "Added"}
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 20)


def _unzip(z):
    return subprocess.Popen(["unzip", "-p", str(z), "*.csv"], stdout=subprocess.PIPE).stdout


def _num(df, cols):
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[df[c] < 0, c] = float("nan")     # CRDC reserve codes (-3, -5, -6, -9, -10 ...)
    return df


def schools():
    d029 = pd.read_csv(_unzip(SCH029), dtype=str, encoding="latin-1",
                       usecols=["NCESSCH", "LEAID", "SY_STATUS_TEXT", "SCH_TYPE_TEXT", "GSLO", "GSHI", "LEVEL"])
    d059 = _num(pd.read_csv(_unzip(SCH059), dtype=str, encoding="latin-1", usecols=["NCESSCH", "TEACHERS"]),
                ["TEACHERS"])
    memb = defaultdict(lambda: [0.0, 0.0])                # [PK, total] from "Subtotal 4 - By Grade"
    for row in csv.DictReader(io.TextIOWrapper(_unzip(SCH052), encoding="latin-1")):
        if row["TOTAL_INDICATOR"].startswith("Subtotal 4"):
            try:
                n = float(row["STUDENT_COUNT"])
            except ValueError:
                continue
            memb[row["NCESSCH"]][1] += n
            if row["GRADE"] == "Pre-Kindergarten":
                memb[row["NCESSCH"]][0] += n
    m = pd.DataFrame([(k, v[0], v[1]) for k, v in memb.items()], columns=["NCESSCH", "PK", "TOTAL"])
    s = d029.merge(d059, on="NCESSCH", how="left").merge(m, on="NCESSCH", how="left")
    s = s[s.SY_STATUS_TEXT.isin(OPEN)].copy()
    s["band"] = [",".join(sorted(primary_bands_for(lv, lo, hi))) for lv, lo, hi in zip(s.LEVEL, s.GSLO, s.GSHI)]
    s["single"] = s.band.isin(["elementary", "middle", "high"])
    return s


def m1(s):
    print("\n== M1 (D1/D2): teacher FTE by the pipeline's school band ==")
    if s.TEACHERS.sum() <= 0:
        return print("M1: NOTHING MEASURED")
    t = s.groupby("band").agg(schools=("NCESSCH", "size"), teachers=("TEACHERS", "sum"), students=("TOTAL", "sum"))
    t["teacher_%"] = (100 * t.teachers / t.teachers.sum()).round(2)
    print(t.sort_values("teachers", ascending=False).round(2).to_string())
    print("teacher FTE in single-band schools: %.1f%%" % (100 * s[s.single].TEACHERS.sum() / s.TEACHERS.sum()))
    el = s[s.band == "elementary"]
    print("elementary band, teacher % by top grade:",
          (100 * el.groupby("GSHI").TEACHERS.sum() / el.TEACHERS.sum()).round(1).nlargest(6).to_dict())


def m2(s):
    print("\n== M2 (D3): Pre-K teachers, pro-rata vs LEA-reported ==")
    if not LEA059.exists():
        return print(f"M2: NOTHING MEASURED — {LEA059.name} absent")
    lea = _num(pd.read_csv(LEA059, dtype=str, encoding="latin-1", usecols=["LEAID", "STAFF", "STAFF_COUNT"]),
               ["STAFF_COUNT"])
    pk = lea[lea.STAFF == "Pre-kindergarten Teachers"].set_index("LEAID").STAFF_COUNT.rename("pk_lea")
    s = s.assign(pk_prorata=s.TEACHERS * s.PK / s.TOTAL.where(s.TOTAL > 0))
    d = s.groupby("LEAID").agg(pk_prorata=("pk_prorata", "sum"), pk_memb=("PK", "sum")).join(pk)
    both = d[(d.pk_memb > 0) & d.pk_lea.notna()]
    if both.empty:
        return print("M2: NOTHING MEASURED — no LEA with PK membership and a reported PK teacher count")
    print("LEAs with PK students: %d; PK teacher count reported: %d; reported 0 despite PK students: %d" % (
        (d.pk_memb > 0).sum(), len(both), (both.pk_lea == 0).sum()))
    print("PK teachers: LEA-reported %.0f vs pro-rata %.0f; PK PTR reported %.1f vs pro-rata %.1f" % (
        both.pk_lea.sum(), both.pk_prorata.sum(),
        both.pk_memb.sum() / both.pk_lea.sum(), both.pk_memb.sum() / both.pk_prorata.sum()))
    r = (both.pk_lea / both.pk_prorata.where(both.pk_prorata > 0)).dropna()
    print("per-LEA reported/pro-rata quantiles:", r.quantile([.1, .25, .5, .75, .9]).round(2).to_dict())


def crdc():
    sup = _num(pd.read_csv(CRDC / "School Support.csv", dtype=str, encoding="latin-1",
                           usecols=["COMBOKEY", "LEA_STATE", "SCH_FTETEACH_TOT", "SCH_FTETEACH_SPEDCERT"]),
               ["SCH_FTETEACH_TOT", "SCH_FTETEACH_SPEDCERT"])
    idea_cols = ["SCH_ENR_IDEA_M", "SCH_ENR_IDEA_F", "SCH_ENR_IDEA_X"]
    tot_cols = ["TOT_ENR_M", "TOT_ENR_F", "TOT_ENR_X"]
    en = _num(pd.read_csv(CRDC / "Enrollment.csv", dtype=str, encoding="latin-1",
                          usecols=["COMBOKEY", *tot_cols, *idea_cols]), tot_cols + idea_cols)
    en["enr"] = en[tot_cols].sum(axis=1)
    en["idea"] = en[idea_cols].sum(axis=1)
    return sup.merge(en[["COMBOKEY", "enr", "idea"]], on="COMBOKEY", how="left")


def m3(s, cr):
    print("\n== M3 (D8): CRDC SPEDCERT at school grain ==")
    j = s.merge(cr, left_on="NCESSCH", right_on="COMBOKEY", how="inner")
    j = j[j.TEACHERS.notna() & j.SCH_FTETEACH_TOT.notna() & j.SCH_FTETEACH_SPEDCERT.notna()]
    if j.empty:
        return print("M3: NOTHING MEASURED — no CCD school matched to CRDC with both teacher counts")
    print("matched schools %d of %d open; sums CCD teachers %.0f, CRDC total %.0f, SPEDCERT %.0f" % (
        len(j), len(s), j.TEACHERS.sum(), j.SCH_FTETEACH_TOT.sum(), j.SCH_FTETEACH_SPEDCERT.sum()))
    off = (j.SCH_FTETEACH_TOT - j.TEACHERS).abs() / j.TEACHERS.where(j.TEACHERS > 0)
    print("|CRDC total - CCD teachers| / CCD: median %.3f; >25%% off in %.1f%% of schools" % (
        off.median(), 100 * (off > .25).mean()))
    print("SPEDCERT > CCD teachers: %d schools; >=20 IDEA students but SPEDCERT 0: %d schools (%.0f students)" % (
        (j.SCH_FTETEACH_SPEDCERT > j.TEACHERS).sum(),
        ((j.idea >= 20) & (j.SCH_FTETEACH_SPEDCERT == 0)).sum(),
        j[(j.idea >= 20) & (j.SCH_FTETEACH_SPEDCERT == 0)].idea.sum()))
    g = j.groupby("SCH_TYPE_TEXT").agg(teach=("TEACHERS", "sum"), spedcert=("SCH_FTETEACH_SPEDCERT", "sum"),
                                       idea=("idea", "sum"), enr=("enr", "sum"))
    g["spedcert_share"] = (g.spedcert / g.teach).round(3)
    g["idea_share"] = (g.idea / g.enr).round(3)
    print(g.round(3).to_string())
    b = j[(j.SCH_TYPE_TEXT == "Regular School") & j.single].groupby("band").agg(
        teach=("TEACHERS", "sum"), spedcert=("SCH_FTETEACH_SPEDCERT", "sum"), idea=("idea", "sum"), enr=("enr", "sum"))
    b["spedcert_share"] = (b.spedcert / b.teach).round(3)
    b["idea_share"] = (b.idea / b.enr).round(3)
    b["ptr_all"] = (b.enr / b.teach).round(1)
    b["ptr_minus_both"] = ((b.enr - b.idea) / (b.teach - b.spedcert)).round(1)
    b["ptr_minus_teachers_only"] = (b.enr / (b.teach - b.spedcert)).round(1)
    print("regular single-band schools:\n" + b.round(3).to_string())


def m4(cr):
    print("\n== M4 (D8): CRDC SPEDCERT vs IDEA 618 assigned SPED teachers, by state ==")
    from sqlalchemy import text
    from infrastructure.database.connection import session_scope
    try:
        with session_scope() as ses:
            b = pd.DataFrame(ses.execute(text(
                "SELECT state, sped_teachers_certified::float AS cert, sped_teachers_total::float AS total, "
                "personnel_year FROM sped_state_baseline WHERE baseline_year = '2024-25'")).mappings().all())
    except Exception as exc:                                     # DB down is not a verdict
        return print(f"M4: NOTHING MEASURED — {type(exc).__name__}")
    if b.empty:
        return print("M4: NOTHING MEASURED — no 2024-25 sped_state_baseline rows")
    j = b.set_index("state").join(cr.groupby("LEA_STATE").SCH_FTETEACH_SPEDCERT.sum().rename("crdc"), how="inner")
    j = j[j.total > 0]
    j["crdc_over_idea"] = j.crdc / j.total
    print("personnel year %s; national CRDC %.0f / IDEA total %.0f (certified %.0f) = %.2f" % (
        ",".join(b.personnel_year.unique()), j.crdc.sum(), j.total.sum(), j.cert.sum(), j.crdc.sum() / j.total.sum()))
    print("state ratio quantiles:", j.crdc_over_idea.quantile([0, .1, .25, .5, .75, .9, 1]).round(2).to_dict())
    print(j.sort_values("crdc_over_idea").crdc_over_idea.round(2).iloc[list(range(3)) + list(range(-6, 0))].to_dict())


if __name__ == "__main__":
    if not all(p.exists() for p in (SCH029, SCH052, SCH059)):
        raise SystemExit(f"VERDICT: NOTHING MEASURED — 2023-24 school files absent under {CCD}")
    s = schools()
    m1(s)
    m2(s)
    cr = crdc() if (CRDC / "School Support.csv").exists() else None
    if cr is None:
        print("\nM3/M4: NOTHING MEASURED — CRDC 2023-24 absent")
    else:
        m3(s, cr)
        m4(cr)
