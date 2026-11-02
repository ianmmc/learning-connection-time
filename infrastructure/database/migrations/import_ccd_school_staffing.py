"""Load the CCD SCHOOL files (029 directory, 052 membership, 059 staff) verbatim into
ccd_school_staffing for one year (#1039, #1022 T5; #1017 phase 2, epic #724).

One row per school in the 029 directory for the year; the 052 and 059 values join on NCESSCH.
Missing or suppressed stays NULL with its DMS flag, never 0 (REQ-165). The three lea_* tables are
DERIVED from this one by T6 (#1040) and are not touched here.

Guards (infrastructure/utilities/data_guards.py; acceptance A2 of the plan note):
  * every source must be PINNED in config/source-manifests/nces-ccd.json and match it byte-for-byte
    (the T3 manifest is the only record of which bytes a gitignored raw file held; a drifted or
    undeclared file is refused, `nces_ccd_manifest.py --write [--repin]` is the logged way to pin it);
  * a zip member is read through utilities/zip_members.open_member, which verifies the CRC;
  * every TOTAL_INDICATOR / GRADE / DMS_FLAG / LEVEL value must be in the known vocabulary, and the
    vocabulary the parser filters on must be SEEN (a relabel is a parse error, never an empty column);
  * the stored per-grade membership (plus the 'Not Specified' grade-unknown residual) reconciles per
    school against the file's own 'Derived - Education Unit Total minus Adult Education Count' row
    (measured: 0 of 99,152 schools differ on 2024-25, 0 of 99,418 on 2023-24 — so the row-wise cap is
    0, not "small"; without the residual, 2 and 4 Wisconsin schools differ by one student);
  * the 052/059 schools must all be in the 029 directory with the same LEAID (measured 0 / 0 on both
    vintages — a non-zero count is a vintage mix-up);
  * a 0-school load is refused before anything is deleted;
  * the school-file teacher sum vs the LEA file's 'Teachers' total is REPORTED (receipt printed and
    stored in the lineage row) and loosely guarded: measured Σschool/ΣLEA = 0.9864 on both 2024-25
    and 2023-24, 94.1% / 93.7% of LEAs within ±5%, so an aggregate outside ±LEA_COVERAGE_TOLERANCE is
    the wrong pair of files, not a coverage finding.

Writes REPLACE the year's rows (delete + insert in one transaction), like import_sped_baseline.

Usage:
    python import_ccd_school_staffing.py [--year 2024-25] [--dry-run]

--dry-run parses, guards and reports without opening a database session.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import zipfile
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, insert

project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope  # noqa: E402
from infrastructure.database.models import CCDSchoolStaffing, DataLineage  # noqa: E402
from infrastructure.utilities import source_manifest  # noqa: E402
from infrastructure.utilities.common import EDUCATION_UNIT_TOTAL, EDUCATION_UNIT_TOTAL_MINUS_ADULT  # noqa: E402
from infrastructure.utilities.data_guards import (  # noqa: E402
    DataGuardError,
    TotalReconciliation,
    reconcile_total,
    require_labels_seen,
    require_nonempty_selection,
)
from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR  # noqa: E402
from infrastructure.utilities.zip_members import open_member  # noqa: E402

RAW_ROOT = project_root / "data" / "raw" / "federal" / "nces-ccd"
MANIFEST_SOURCE = "nces-ccd"
SCHOOL_FILE_IDS = ("029", "052", "059")

# ---------------------------------------------------------------------------------------- vocabularies
# Measured on both on-disk vintages (2023-24, 2024-25) on 2026-11-02; a value outside these sets is a
# relabel the parser must not guess at.
SUBTOTAL_BY_GRADE = "Subtotal 4 - By Grade"
MEMBERSHIP_INDICATORS = {
    "Category Set A - By Race/Ethnicity; Sex; Grade",
    "Derived - Subtotal by Race/Ethnicity and Sex minus Adult Education Count",
    SUBTOTAL_BY_GRADE,
    EDUCATION_UNIT_TOTAL_MINUS_ADULT,
    EDUCATION_UNIT_TOTAL,
}
STAFF_INDICATORS = {EDUCATION_UNIT_TOTAL}
GRADE_COLUMN = {
    "Pre-Kindergarten": "memb_pk",
    "Kindergarten": "memb_kg",
    **{f"Grade {n}": f"memb_{n:02d}" for n in range(1, 14)},
    "Ungraded": "memb_ug",
}
# Subtotal-4 grades the table has no column for. 'Not Specified' is the grade-unknown residual NCES
# derives per school (Education Unit Total − Σ graded rows; DMS_FLAG 'Derived', 0 at all but a handful
# of Wisconsin schools carrying 1 student each), so it is part of the reconciled sum. 'Adult Education'
# is not an LCT grade and is what separates the two Education-Unit totals, so the stored grades plus the
# residual reconcile against the minus-Adult-Education one.
GRADE_RESIDUAL = "Not Specified"
GRADES_NOT_STORED = {GRADE_RESIDUAL, "Adult Education"}
GRADE_VOCAB = set(GRADE_COLUMN) | GRADES_NOT_STORED
REPORTED = "Reported"
DMS_FLAGS = {REPORTED, "Derived", "Manual adjustment", "Missing", "Not reported", "Suppressed"}
LEVELS = {"Elementary", "Middle", "High", "Secondary", "Prekindergarten", "Other", "Ungraded",
          "Adult Education", "Not applicable", "Not reported"}
LEVELS_REQUIRED = {"Elementary", "Middle", "High"}       # the bands' own levels must occur
LEA_TEACHERS_STAFF = "Teachers"
LEA_TEACHERS_INDICATOR = "Derived - Major Staffing Category"

# Per-school Σ(stored grades) vs the file's own minus-Adult-Education total: EXACT on both vintages.
MAX_ROWWISE_DISAGREE = 0
# Σ school-file teachers / Σ LEA-file teachers, measured 0.9864 on both 2024-25 and 2023-24.
LEA_COVERAGE_TOLERANCE = 0.05
LEA_WITHIN_BAND = 0.05
INSERT_CHUNK = 5_000


# ---------------------------------------------------------------------------------------- sources
def year_dir(year: str, root: Path = RAW_ROOT) -> Path:
    return root / year.replace("-", "_")


def locate(year: str, root: Path = RAW_ROOT) -> dict[str, Path]:
    """The one source per file id for `year`: ccd_sch_<id>_*.csv when the CSV is on disk, else the
    release zip (ccd_sch_<id>_*.zip, read through open_member), plus the LEA 059 CSV under 'lea_059'.
    Refuses an absent or ambiguous id — the release suffix (_073025) is not derivable from the year."""
    d = year_dir(year, root)
    found: dict[str, Path] = {}
    for fid in SCHOOL_FILE_IDS:
        csvs = sorted(d.glob(f"ccd_sch_{fid}_*.csv"))
        zips = sorted(d.glob(f"ccd_sch_{fid}_*.zip"))
        matches = csvs or zips
        if len(matches) != 1:
            raise DataGuardError(
                f"CCD school file {fid} for {year}: expected exactly one ccd_sch_{fid}_*.csv (or .zip) "
                f"under {d}, found {[p.name for p in matches]}")
        found[fid] = matches[0]
    lea = sorted(d.glob("ccd_lea_059_*.csv"))
    if len(lea) != 1:
        raise DataGuardError(f"CCD LEA staff file for {year}: expected exactly one ccd_lea_059_*.csv "
                             f"under {d}, found {[p.name for p in lea]}")
    found["lea_059"] = lea[0]
    return found


def pinned_sha256(path: Path, year: str, manifest: dict) -> str:
    """The file's sha256, REQUIRED to equal its manifest pin. An undeclared file has no record of
    what bytes it should hold; a drifted one is not the file the manifest vouches for."""
    try:
        entry = source_manifest.entry_for(manifest, year, path.name)
    except KeyError as e:
        raise DataGuardError(f"{e}; pin it with nces_ccd_manifest.py --write before importing") from e
    actual = source_manifest.sha256_file(path)
    if actual != entry["sha256"]:
        raise DataGuardError(
            f"{path.name} on disk (sha256 {actual[:12]}…) is not the pinned {year} file "
            f"({entry['sha256'][:12]}…); re-download it or re-pin with --repin if the change is intended")
    return actual


@contextlib.contextmanager
def open_source(path: Path):
    """A binary stream of the CSV: the file itself, or the single .csv member of a release zip
    (CRC-verified by open_member as it is read)."""
    if path.suffix.lower() != ".zip":
        with open(path, "rb") as f:
            yield f
        return
    with zipfile.ZipFile(path) as z:
        members = [n for n in z.namelist() if n.lower().endswith(".csv")]
    if len(members) != 1:
        raise DataGuardError(f"{path.name}: expected exactly one .csv member, found {members}")
    with open_member(path, members[0]) as f:
        yield f


def _unknown(values: pd.Series, vocab: set[str], *, label: str) -> None:
    unknown = sorted(set(values.dropna().unique()) - vocab)
    if unknown:
        raise DataGuardError(f"{label}: {len(unknown)} value(s) outside the known vocabulary — "
                             f"{unknown[:10]}; the file's labels have drifted from the parser's")


def _unique(values: pd.Series, *, label: str) -> None:
    dupes = values[values.duplicated()].unique()
    if len(dupes):
        raise DataGuardError(f"{label}: {len(dupes)} NCESSCH value(s) occur more than once — "
                             f"{list(dupes[:5])}; a join on them would multiply rows")


def _number(x):
    """float(x) for a reported value; None for blank/NA (never 0 — REQ-165)."""
    if x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() in ("", "NA"):
        return None
    return float(x)


# ---------------------------------------------------------------------------------------- readers
def read_directory(stream) -> pd.DataFrame:
    """029: one row per school, indexed by NCESSCH."""
    cols = ["NCESSCH", "LEAID", "ST", "SCH_NAME", "SY_STATUS_TEXT", "SCH_TYPE_TEXT", "LEVEL", "GSLO", "GSHI"]
    df = pd.read_csv(stream, dtype=str, usecols=cols, encoding="utf-8")
    _unique(df["NCESSCH"], label="029 directory")
    _unknown(df["LEVEL"], LEVELS, label="029 LEVEL")
    require_labels_seen(LEVELS_REQUIRED, df["LEVEL"].dropna().unique(), label="029 LEVEL")
    return df.set_index("NCESSCH")


def read_staff(stream) -> pd.DataFrame:
    """059: one 'Education Unit Total' row per school → teachers_fte (None unless a value is present)
    and the DMS flag."""
    cols = ["NCESSCH", "LEAID", "TEACHERS", "TOTAL_INDICATOR", "DMS_FLAG"]
    df = pd.read_csv(stream, dtype=str, usecols=cols, encoding="utf-8")
    df["TOTAL_INDICATOR"] = df["TOTAL_INDICATOR"].str.strip()
    _unknown(df["TOTAL_INDICATOR"], STAFF_INDICATORS, label="059 TOTAL_INDICATOR")
    _unknown(df["DMS_FLAG"], DMS_FLAGS, label="059 DMS_FLAG")
    require_labels_seen(STAFF_INDICATORS, df["TOTAL_INDICATOR"].unique(), label="059 TOTAL_INDICATOR")
    require_labels_seen({REPORTED}, df["DMS_FLAG"].unique(), label="059 DMS_FLAG")
    df = df[df["TOTAL_INDICATOR"] == EDUCATION_UNIT_TOTAL]
    _unique(df["NCESSCH"], label="059 staff")
    # dtype=object: a float column would turn every None into NaN, which `is not None` lets through
    out = pd.DataFrame({
        "LEAID": df["LEAID"].values,
        "teachers_fte": [_number(v) for v in df["TEACHERS"]],
        "teachers_dms_flag": df["DMS_FLAG"].values,
    }, index=pd.Index(df["NCESSCH"].values, name="NCESSCH"), dtype=object)
    bad = [v for v in out["teachers_fte"] if v is not None and v < 0]
    if bad:
        raise DataGuardError(f"059 TEACHERS: {len(bad)} negative value(s)")
    return out


def read_membership(stream, *, chunksize: int = 2_000_000) -> tuple[pd.DataFrame, TotalReconciliation]:
    """052: the 'Subtotal 4 - By Grade' rows → one row per school with memb_* columns (None where the
    grade row is absent or carries no value), membership_flags {grade: flag} for every stored-grade row
    not 'Reported', and the per-school reconciliation receipt against the file's own
    minus-Adult-Education total."""
    cols = ["NCESSCH", "LEAID", "GRADE", "STUDENT_COUNT", "TOTAL_INDICATOR", "DMS_FLAG"]
    sub, ref = [], []
    seen_ti, seen_grade, seen_flag = set(), set(), set()
    for chunk in pd.read_csv(stream, dtype=str, usecols=cols, encoding="utf-8", chunksize=chunksize):
        chunk["TOTAL_INDICATOR"] = chunk["TOTAL_INDICATOR"].str.strip()
        _unknown(chunk["TOTAL_INDICATOR"], MEMBERSHIP_INDICATORS, label="052 TOTAL_INDICATOR")
        _unknown(chunk["DMS_FLAG"], DMS_FLAGS, label="052 DMS_FLAG")
        seen_ti.update(chunk["TOTAL_INDICATOR"].unique())
        seen_flag.update(chunk["DMS_FLAG"].dropna().unique())
        s = chunk[chunk["TOTAL_INDICATOR"] == SUBTOTAL_BY_GRADE]
        _unknown(s["GRADE"], GRADE_VOCAB, label="052 GRADE (Subtotal 4)")
        seen_grade.update(s["GRADE"].unique())
        sub.append(s[["NCESSCH", "LEAID", "GRADE", "STUDENT_COUNT", "DMS_FLAG"]])
        ref.append(chunk[chunk["TOTAL_INDICATOR"] == EDUCATION_UNIT_TOTAL_MINUS_ADULT][["NCESSCH", "STUDENT_COUNT"]])
    require_labels_seen({SUBTOTAL_BY_GRADE, EDUCATION_UNIT_TOTAL_MINUS_ADULT}, seen_ti, label="052 TOTAL_INDICATOR")
    require_labels_seen(set(GRADE_COLUMN), seen_grade, label="052 GRADE (Subtotal 4)")
    require_labels_seen({REPORTED}, seen_flag, label="052 DMS_FLAG")
    sub = pd.concat(sub, ignore_index=True) if sub else pd.DataFrame(columns=cols)
    ref = pd.concat(ref, ignore_index=True) if ref else pd.DataFrame(columns=["NCESSCH", "STUDENT_COUNT"])
    _unique(ref["NCESSCH"], label=f"052 '{EDUCATION_UNIT_TOTAL_MINUS_ADULT}'")
    dup = sub.duplicated(["NCESSCH", "GRADE"])
    if dup.any():
        raise DataGuardError(f"052 Subtotal 4: {int(dup.sum())} duplicate (NCESSCH, GRADE) row(s)")
    ref_total = {k: _number(v) for k, v in zip(ref["NCESSCH"], ref["STUDENT_COUNT"])}

    rows: dict[str, dict] = {}
    columns = (sub["NCESSCH"], sub["LEAID"], sub["GRADE"], sub["STUDENT_COUNT"], sub["DMS_FLAG"])
    for ncessch, leaid, grade, count, flag in zip(*columns):
        row = rows.setdefault(ncessch, {"LEAID": leaid, "membership_flags": {}, "_residual": None})
        value = _number(count)
        if grade == GRADE_RESIDUAL:
            row["_residual"] = value
            continue
        if grade not in GRADE_COLUMN:
            continue
        row[GRADE_COLUMN[grade]] = None if value is None else int(value)
        if flag != REPORTED:
            row["membership_flags"][grade] = flag

    # Per school: Σ(stored grades) + the grade-unknown residual must equal the file's own
    # minus-Adult-Education total. A school whose stored grades include a blank cannot be summed and is
    # not compared (its NULL is the record).
    n_compared = n_disagree = 0
    ours = theirs = 0.0
    residual_students = 0
    for ncessch, row in rows.items():
        values = [row.get(c) for c in GRADE_COLUMN.values() if c in row]
        residual = row["_residual"] or 0.0
        residual_students += int(residual)
        if any(v is None for v in values) or ref_total.get(ncessch) is None:
            continue
        n_compared += 1
        s = float(sum(values)) + residual
        ours += s
        theirs += ref_total[ncessch]
        if s != ref_total[ncessch]:
            n_disagree += 1
    receipt = reconcile_total(
        ours, theirs,
        label=f"052 Σ stored grades + '{GRADE_RESIDUAL}' vs '{EDUCATION_UNIT_TOTAL_MINUS_ADULT}' per school",
        n_compared=n_compared, n_disagree=n_disagree, max_disagree=MAX_ROWWISE_DISAGREE)
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "NCESSCH"
    for c in GRADE_COLUMN.values():
        if c not in df.columns:
            df[c] = None
    df.attrs["residual_students"] = residual_students
    return df, receipt


def read_lea_teachers(stream) -> pd.DataFrame:
    """ccd_lea_059: the 'Teachers' major-staffing-category total per LEA (value or None, flag)."""
    cols = ["LEAID", "STAFF", "STAFF_COUNT", "TOTAL_INDICATOR", "DMS_FLAG"]
    df = pd.read_csv(stream, dtype=str, usecols=cols, encoding="utf-8")
    df["STAFF"] = df["STAFF"].str.strip()
    df["TOTAL_INDICATOR"] = df["TOTAL_INDICATOR"].str.strip()
    require_labels_seen({LEA_TEACHERS_STAFF}, df["STAFF"].unique(), label="LEA 059 STAFF")
    require_labels_seen({LEA_TEACHERS_INDICATOR}, df["TOTAL_INDICATOR"].unique(), label="LEA 059 TOTAL_INDICATOR")
    df = df[(df["STAFF"] == LEA_TEACHERS_STAFF) & (df["TOTAL_INDICATOR"] == LEA_TEACHERS_INDICATOR)]
    dupes = df["LEAID"].duplicated()
    if dupes.any():
        raise DataGuardError(f"LEA 059 'Teachers': {int(dupes.sum())} duplicate LEAID row(s)")
    return pd.DataFrame({"lea_teachers_fte": [_number(v) for v in df["STAFF_COUNT"]],
                         "lea_teachers_dms_flag": df["DMS_FLAG"].values},
                        index=pd.Index(df["LEAID"].values, name="LEAID"), dtype=object)


# ---------------------------------------------------------------------------------------- assembly
def _subset_of_directory(directory: pd.DataFrame, other: pd.DataFrame, *, label: str) -> None:
    missing = other.index.difference(directory.index)
    if len(missing):
        raise DataGuardError(f"{label}: {len(missing)} school(s) are not in the 029 directory "
                             f"({list(missing[:5])}); the files are not the same vintage")
    joined = other[["LEAID"]].join(directory[["LEAID"]], rsuffix="_dir")
    mismatch = joined[joined["LEAID"] != joined["LEAID_dir"]]
    if len(mismatch):
        raise DataGuardError(f"{label}: {len(mismatch)} school(s) carry a different LEAID than the 029 "
                             f"directory ({list(mismatch.index[:5])})")


def assemble(year: str, directory: pd.DataFrame, staff: pd.DataFrame, membership: pd.DataFrame,
             shas: dict[str, str]) -> list[dict]:
    """One ccd_school_staffing row per 029 school, 052/059 values joined on NCESSCH."""
    _subset_of_directory(directory, staff, label="059 staff")
    _subset_of_directory(directory, membership, label="052 membership")
    require_nonempty_selection(directory, what=f"029 directory for {year}", available=sorted(shas))
    staff_fte = staff["teachers_fte"].to_dict()
    staff_flag = staff["teachers_dms_flag"].to_dict()
    memb = membership.to_dict(orient="index") if len(membership) else {}
    rows = []
    for ncessch, d in directory.iterrows():
        m = memb.get(ncessch, {})
        row = {
            "ncessch": ncessch,
            "source_year": year,
            "leaid": d["LEAID"],
            "state": d["ST"],
            "school_name": d["SCH_NAME"],
            "sy_status": d["SY_STATUS_TEXT"],
            "sch_type": d["SCH_TYPE_TEXT"],
            "level": d["LEVEL"],
            "gslo": d["GSLO"],
            "gshi": d["GSHI"],
            "teachers_fte": staff_fte.get(ncessch),
            "teachers_dms_flag": staff_flag.get(ncessch),
            "membership_flags": (m.get("membership_flags") or None) if m else None,
            "src_029_sha256": shas["029"],
            "src_052_sha256": shas["052"],
            "src_059_sha256": shas["059"],
        }
        for c in GRADE_COLUMN.values():
            v = m.get(c)
            row[c] = None if v is None or (isinstance(v, float) and pd.isna(v)) else int(v)
        rows.append(row)
    return rows


def lea_coverage(rows: list[dict], lea: pd.DataFrame) -> dict:
    """Σ school-file teachers vs Σ LEA-file 'Teachers', LEA by LEA. Reported (returned for the lineage
    row) and guarded only at the aggregate: outside ±LEA_COVERAGE_TOLERANCE is the wrong file pair."""
    school_sum: dict[str, float] = {}
    for r in rows:
        if r["teachers_fte"] is not None:
            school_sum[r["leaid"]] = school_sum.get(r["leaid"], 0.0) + float(r["teachers_fte"])
    ours = theirs = 0.0
    n = within = 0
    for leaid, lea_fte in lea["lea_teachers_fte"].items():
        if lea_fte is None or lea_fte <= 0:
            continue
        n += 1
        s = school_sum.get(leaid, 0.0)
        ours += s
        theirs += lea_fte
        if abs(s / lea_fte - 1.0) <= LEA_WITHIN_BAND:
            within += 1
    receipt = reconcile_total(ours, theirs, label="059 Σ school teachers vs LEA-file 'Teachers'",
                              tolerance=LEA_COVERAGE_TOLERANCE, n_compared=n)
    return {"school_teachers_fte": round(ours, 2), "lea_teachers_fte": round(theirs, 2),
            "ratio": round(receipt.ratio, 5), "leas_compared": n,
            "leas_within_5pct": within, "share_within_5pct": round(within / n, 5) if n else None,
            "leas_with_school_fte_only": len(set(school_sum) - set(lea.index))}


def load_year(year: str, root: Path = RAW_ROOT, manifest: dict | None = None) -> tuple[list[dict], dict]:
    """Locate, pin, parse and guard the year's files. Returns the rows and the lineage details."""
    manifest = source_manifest.load(MANIFEST_SOURCE) if manifest is None else manifest
    paths = locate(year, root)
    shas = {fid: pinned_sha256(paths[fid], year, manifest) for fid in SCHOOL_FILE_IDS}
    print(f"Sources for {year}:")
    for fid in SCHOOL_FILE_IDS:
        print(f"  {fid}: {paths[fid].name}  sha256 {shas[fid][:12]}…")
    print(f"  LEA 059: {paths['lea_059'].name}")
    with open_source(paths["029"]) as f:
        directory = read_directory(f)
    print(f"  029: {len(directory):,} schools")
    with open_source(paths["059"]) as f:
        staff = read_staff(f)
    print(f"  059: {len(staff):,} schools, {sum(v is not None for v in staff['teachers_fte']):,} with a teacher count")
    with open_source(paths["052"]) as f:
        membership, memb_receipt = read_membership(f)
    print(f"  052: {len(membership):,} schools; per-school reconciliation {memb_receipt.n_compared:,} compared, "
          f"{memb_receipt.n_disagree:,} differ, aggregate ratio {memb_receipt.ratio:.5f}")
    with open_source(paths["lea_059"]) as f:
        lea = read_lea_teachers(f)
    rows = assemble(year, directory, staff, membership, shas)
    coverage = lea_coverage(rows, lea)
    print(f"  Coverage: Σ school teachers {coverage['school_teachers_fte']:,.1f} / Σ LEA teachers "
          f"{coverage['lea_teachers_fte']:,.1f} = {coverage['ratio']:.4f}; "
          f"{coverage['leas_within_5pct']:,} of {coverage['leas_compared']:,} LEAs within ±5%")
    details = {
        "year": year,
        "sources": {fid: [paths[fid].name, shas[fid]] for fid in SCHOOL_FILE_IDS},
        "lea_source": paths["lea_059"].name,
        "schools": len(rows),
        "schools_with_teachers": sum(r["teachers_fte"] is not None for r in rows),
        "schools_with_membership": int(len(membership)),
        "grade_not_specified_students": membership.attrs.get("residual_students", 0),
        "membership_reconciliation": memb_receipt._asdict(),
        "lea_coverage": coverage,
    }
    return rows, details


def write_year(session, year: str, rows: list[dict], details: dict) -> int:
    """REPLACE the year's rows, then log the lineage row, all in the caller's transaction."""
    require_nonempty_selection(rows, what=f"ccd_school_staffing rows for {year}", available=[year])
    session.execute(delete(CCDSchoolStaffing).where(CCDSchoolStaffing.source_year == year))
    for i in range(0, len(rows), INSERT_CHUNK):
        session.execute(insert(CCDSchoolStaffing), rows[i:i + INSERT_CHUNK])
    DataLineage.log(
        session,
        entity_type="ccd_school_staffing",
        entity_id=year,
        operation="import",
        source_file=", ".join(v[0] for v in details["sources"].values()),
        details=details,
        created_by="import_ccd_school_staffing.py",
    )
    return len(rows)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Load the CCD school files verbatim into ccd_school_staffing")
    parser.add_argument(
        "--year", default=NCES_PRIMARY_YEAR,
        help=f"School year to load (default: NCES_PRIMARY_YEAR = {NCES_PRIMARY_YEAR}; "
             f"bump that constant on a new CCD, never this default)")
    parser.add_argument("--dry-run", action="store_true", help="parse, guard and report; write nothing")
    args = parser.parse_args(argv)

    print("=" * 60)
    print("NCES CCD school staffing import (ccd_school_staffing)")
    print("=" * 60)
    rows, details = load_year(args.year, RAW_ROOT)
    if args.dry_run:
        print(f"\nDRY RUN: {len(rows):,} rows for {args.year} parsed and guarded; nothing written")
        return
    with session_scope() as session:
        n = write_year(session, args.year, rows, details)
    print(f"\nIMPORT COMPLETE: {n:,} ccd_school_staffing rows for {args.year} (replaced the year's prior rows)")


if __name__ == "__main__":
    main()
