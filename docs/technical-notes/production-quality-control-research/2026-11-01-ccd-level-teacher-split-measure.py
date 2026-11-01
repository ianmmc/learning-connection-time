"""#1017 — measure how each state's CCD 'elementary' / 'secondary' teacher split lines up with grade bands.

Read-only. Rerunnable. Backs docs/technical-notes/production-quality-control-research/
2026-11-01-ccd-level-teacher-split.md.

Check-map:
  M1  Unified K-12 districts (K/1, 6, 9 and 12 enrolled; secondary teachers > 0; K-12 >= 500): per state, the
      share of K-12 teacher FTE reported elementary (elem + kinder) vs the K-5 / K-6 / K-8 share of K-12
      enrollment. Nearest share = the grade cutoff that state's reported split behaves like; `dK8` = share of
      the state's districts that individually fit K-8 best.
  M2  K-8-only districts (grade 8 enrolled, no 9-12): per state, % reporting 0 secondary teachers and the
      secondary share of teacher FTE vs the grade 6-8 share of enrollment.
  M3  (--school-files) CCD school files: pupil/teacher ratio (K-12 students / school teacher FTE) for
      single-band schools and pro-rata by band (each school's teachers spread over its grades by enrollment).
      Independent of the LEA level split; the yardstick for the replacement scopes (phase 2).

Verdict: NOTHING MEASURED when the DB holds no unified districts for the year (never a green empty table).
Usage:  python3 <this file> [--year 2024-25] [--school-files]
"""
import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from infrastructure.database.connection import session_scope

REPO = Path(__file__).resolve().parents[3]
GRADES = ["k"] + [f"g{i}" for i in range(1, 13)]
SQL = """
SELECT d.state, s.district_id,
       s.teachers_elementary AS te, s.teachers_kindergarten AS tk, s.teachers_secondary AS ts,
       e.enrollment_kindergarten AS k,
       e.enrollment_grade_1 AS g1, e.enrollment_grade_2 AS g2, e.enrollment_grade_3 AS g3,
       e.enrollment_grade_4 AS g4, e.enrollment_grade_5 AS g5, e.enrollment_grade_6 AS g6,
       e.enrollment_grade_7 AS g7, e.enrollment_grade_8 AS g8, e.enrollment_grade_9 AS g9,
       e.enrollment_grade_10 AS g10, e.enrollment_grade_11 AS g11, e.enrollment_grade_12 AS g12
FROM staff_counts_effective s
JOIN enrollment_by_grade e ON e.district_id = s.district_id AND e.source_year = s.effective_year
JOIN districts d ON d.nces_id = s.district_id
WHERE s.effective_year = :year
"""


def cum_share(df, top):
    """K..grade `top` enrollment as a share of K-12 enrollment."""
    return df[GRADES[: top + 1]].sum(axis=1) / df["k12"]


def m1_unified(df):
    uni = df[(df.k + df.g1 > 0) & (df.g6 > 0) & (df.g9 > 0) & (df.g12 > 0) & (df.ts > 0) & (df.k12 >= 500)].copy()
    if uni.empty:
        return uni, None
    uni["el"] = uni.te + uni.tk
    uni["tt"] = uni.el + uni.ts
    for n in (5, 6, 8):
        uni[f"K{n}"] = cum_share(uni, n)
    uni["share"] = uni.el / uni.tt
    uni["dfit"] = uni[["K5", "K6", "K8"]].sub(uni.share, axis=0).abs().idxmin(axis=1)

    def agg(x):
        w = x.k12.sum()
        return pd.Series({
            "n": len(x),
            "elem_teacher_share": x.el.sum() / x.tt.sum(),
            "K5": (x.K5 * x.k12).sum() / w, "K6": (x.K6 * x.k12).sum() / w, "K8": (x.K8 * x.k12).sum() / w,
            "dK8": (x.dfit == "K8").mean(),
        })

    out = uni.groupby("state")[["el", "tt", "k12", "K5", "K6", "K8", "dfit"]].apply(agg)
    out["fit"] = out[["K5", "K6", "K8"]].sub(out.elem_teacher_share, axis=0).abs().idxmin(axis=1)
    return uni, out.sort_values("elem_teacher_share")


def m2_k8(df):
    k8 = df[(df[["g9", "g10", "g11", "g12"]].sum(axis=1) == 0) & (df.g8 > 0) & (df.k + df.g1 > 0)
            & (df.te + df.tk + df.ts > 0)].copy()
    if k8.empty:
        return None
    k8["m"] = k8[["g6", "g7", "g8"]].sum(axis=1)

    def agg(x):
        return pd.Series({
            "n": len(x),
            "zero_sec_pct": (x.ts == 0).mean(),
            "sec_share": x.ts.sum() / (x.te + x.tk + x.ts).sum(),
            "g68_enroll_share": x.m.sum() / x.k12.sum(),
        })

    out = k8.groupby("state")[["te", "tk", "ts", "m", "k12"]].apply(agg)
    return out[out.n >= 5].sort_values("sec_share")


def m3_school_files(year):
    d = REPO / "data/raw/federal/nces-ccd" / year.replace("-", "_")
    files = {p.name.split("_")[2]: p for p in d.glob("ccd_sch_*")}
    need = {"029", "052", "059"}
    if not need <= files.keys():
        print(f"M3: NOTHING MEASURED — school files {sorted(need - files.keys())} absent under {d}")
        return
    staff = pd.read_csv(files["059"], dtype={"NCESSCH": str}, usecols=["NCESSCH", "TEACHERS", "DMS_FLAG"])
    staff = staff[staff.DMS_FLAG == "Reported"]
    level = pd.read_csv(files["029"], dtype={"NCESSCH": str}, usecols=["NCESSCH", "LEVEL"])
    parts = []
    # The zip also carries a .sas7bdat twin, and NCES compresses it with Deflate64, which Python's zipfile
    # cannot read; stream the CSV member through `unzip -p`.
    with zipfile.ZipFile(files["052"]) as z:
        (member,) = [n for n in z.namelist() if n.endswith(".csv")]
    proc = subprocess.Popen(["unzip", "-p", str(files["052"]), member], stdout=subprocess.PIPE)
    for chunk in pd.read_csv(proc.stdout, dtype={"NCESSCH": str}, chunksize=2_000_000,
                             usecols=["NCESSCH", "GRADE", "STUDENT_COUNT", "TOTAL_INDICATOR"]):
        parts.append(chunk[chunk.TOTAL_INDICATOR == "Subtotal 4 - By Grade"])
    if proc.wait() != 0:
        raise RuntimeError(f"unzip -p {files['052'].name} exited {proc.returncode}")
    g = pd.concat(parts)
    gmap = {"Kindergarten": 0, **{f"Grade {i}": i for i in range(1, 13)}}
    g = g[g.GRADE.isin(gmap)].assign(gr=lambda x: x.GRADE.map(gmap))
    band = pd.cut(g.gr, [-1, 5, 8, 12], labels=["K-5", "6-8", "9-12"])
    wide = g.assign(band=band).pivot_table(index="NCESSCH", columns="band", values="STUDENT_COUNT",
                                           aggfunc="sum", fill_value=0, observed=False)
    wide["k12"] = wide.sum(axis=1)
    m = wide[wide.k12 > 0].join(staff.set_index("NCESSCH"), how="inner").join(level.set_index("NCESSCH"))
    m = m[m.TEACHERS > 0]
    if m.empty:
        print("M3: NOTHING MEASURED — no school with both teachers and K-12 students")
        return
    bands = ["K-5", "6-8", "9-12"]
    single = m[(m[bands] > 0).sum(axis=1) == 1]
    print(f"\nM3 school files ({year}): {len(m):,} schools, {m.TEACHERS.sum():,.0f} teacher FTE, "
          f"{m.k12.sum():,.0f} K-12 students")
    for b in bands:
        s = single[single[b] > 0]
        share = m[b] / m.k12
        print(f"  {b:5} single-band PTR {s[b].sum() / s.TEACHERS.sum():5.1f} ({len(s):,} schools) | "
              f"pro-rata PTR {m[b].sum() / (m.TEACHERS * share).sum():5.1f}")
    for lv in ("Elementary", "Middle", "High"):
        s = m[m.LEVEL == lv]
        print(f"  LEVEL={lv:10} PTR {s.k12.sum() / s.TEACHERS.sum():5.1f} ({len(s):,} schools)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--year", default="2024-25")
    ap.add_argument("--school-files", action="store_true", help="also run M3 over the raw CCD school files (slow)")
    args = ap.parse_args(argv)
    with session_scope() as s:
        df = pd.read_sql(text(SQL), s.connection(), params={"year": args.year})
    df[["te", "tk", "ts"] + GRADES] = df[["te", "tk", "ts"] + GRADES].astype(float).fillna(0)
    df["k12"] = df[GRADES].sum(axis=1)

    uni, m1 = m1_unified(df)
    if m1 is None:
        print(f"VERDICT: NOTHING MEASURED — no unified districts for {args.year}")
        return 1
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)
    print(f"M1 unified K-12 districts ({args.year}): {len(uni):,}")
    print(m1.round(3).to_string())
    print("\nState fit counts:", m1.fit.value_counts().to_dict())
    t = uni.el.sum() / uni.tt.sum()
    print(f"National: elem teacher share {t:.3f} | K-5 {(uni.K5 * uni.k12).sum() / uni.k12.sum():.3f} "
          f"| K-8 {(uni.K8 * uni.k12).sum() / uni.k12.sum():.3f}")

    m2 = m2_k8(df)
    print("\nM2 K-8-only districts (states with >= 5):")
    print("NOTHING MEASURED" if m2 is None or m2.empty else m2.round(2).to_string())

    if args.school_files:
        m3_school_files(args.year)
    k8_states = sorted(m1.index[m1.fit == "K8"])
    print(f"\nVERDICT: {len(k8_states)} jurisdictions' reported elementary share fits K-8 enrollment: "
          f"{', '.join(k8_states)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
