"""Load the CCD SCHOOL files (029 directory, 052 membership, 059 staff) verbatim into
ccd_school_staffing for one year (#1039, #1022 T5; #1017 phase 2, epic #724).

One row per school in the 029 directory for the year; the 052 and 059 values join on NCESSCH.
A count is stored only when NCES REPORTS it (DMS_FLAG 'Reported'); any other flag stores NULL with
the flag kept in teachers_dms_flag / membership_flags, never 0 (REQ-165). Measured on both on-disk
vintages (2026-11-03): every stored-grade cell with another flag is either blank ('Missing',
'Not reported', 'Suppressed') or a 'Manual adjustment' ZERO (1,234 / 1,113 cells, 1,110 of them
Michigan Pre-K each year, while the LEA file carries 53,882 Michigan Pre-K students — a zero-fill,
not a count; #1070). The three lea_* tables are DERIVED from this one by T6 (#1040), not touched here.

Guards (infrastructure/utilities/data_guards.py; acceptance A2 of the plan note):
  * --year must parse and must not be a COVID year (REQ-007), and every file's own SCHOOL_YEAR column
    must spell that year ('2024-2025'), so a mis-stamped folder is refused (#1079);
  * every source — the three school files AND the LEA 059 file the coverage guard reads — is located
    FROM the manifest (config/source-manifests/nces-ccd.json; one precedence, #1073) and must match
    its pin byte-for-byte (#1072). An undeclared, absent or drifted file is refused;
    `nces_ccd_manifest.py --write [--repin]` is the logged way to pin it;
  * a zip member is read through utilities/zip_members.open_member, which verifies the CRC;
  * NCESSCH / LEAID must be 12 / 7 digits (the #611 leading-zero class, #1085), and at write time the
    file's LEAIDs must match ≥ MATCH_COVERAGE_FLOOR of our districts (the LEA importer's guard, one home);
  * a blank text cell is NULL at the row boundary, never the text 'NaN' (#934, #1071); a blank where a
    closed vocabulary is expected (TOTAL_INDICATOR / GRADE / DMS_FLAG / LEVEL) is outside it; every
    value must be in the known vocabulary and the vocabulary the parser filters on must be SEEN;
  * a numeric cell is a non-negative finite number (an integer for a membership count) or blank; any
    other token (a suppression mark, a reserve code) is refused naming the column and the school (#1084);
  * the stored per-grade membership (plus the 'Not Specified' grade-unknown residual) reconciles per
    school against the file's own 'Derived - Education Unit Total minus Adult Education Count' row
    (row-wise cap 0: measured 0 of 98,014 / 98,306 compared schools differ on 2024-25 / 2023-24),
    and the compared share must be ≥ MIN_COMPARED_SHARE so a silent skip of most schools cannot
    pass (#1078). The 059 file has no unreported non-blank teacher value on either vintage;
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
import math
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, func, insert, select

project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from infrastructure.database.connection import session_scope  # noqa: E402
from infrastructure.database.models import CCDSchoolStaffing, DataLineage, District  # noqa: E402
from infrastructure.utilities import source_manifest  # noqa: E402
from infrastructure.utilities.common import EDUCATION_UNIT_TOTAL, EDUCATION_UNIT_TOTAL_MINUS_ADULT  # noqa: E402
from infrastructure.utilities.data_guards import (  # noqa: E402
    DataGuardError,
    TotalReconciliation,
    reconcile_total,
    require_labels_seen,
    require_match_coverage,
    require_nonempty_selection,
)
from infrastructure.utilities.grade_bands import LEVEL_BAND  # noqa: E402
from infrastructure.utilities.school_year import NCES_PRIMARY_YEAR, is_covid_year, start_year  # noqa: E402
from infrastructure.utilities.zip_members import open_member  # noqa: E402

# Where the files live is the MANIFEST's `base` (data/raw/federal/nces-ccd), resolved by
# source_manifest.year_folder — the one folder rule, which honours LCT_DATA_ROOT (#1089). RAW_ROOT is
# only an override of the tree that `base` is joined to (tests point it at a scratch tree); None = the repo.
RAW_ROOT: Path | None = None
MANIFEST_SOURCE = "nces-ccd"
SCHOOL_FILE_IDS = ("029", "052", "059")
LEA_FILE_ID = "lea_059"
# The manifest entry for each source id: the one whose file name starts with the id's stem.
FILE_STEM = {"029": "ccd_sch_029_", "052": "ccd_sch_052_", "059": "ccd_sch_059_", LEA_FILE_ID: "ccd_lea_059_"}
NCESSCH_RE = re.compile(r"\d{12}")
LEAID_RE = re.compile(r"\d{7}")
BLANK = "<blank>"      # how a blank cell is named where a vocabulary is expected

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
# The 16 stored grades, keyed by the CCD GRADE label. The LEA importer's GRADE_MAPPING spells the same
# labels for its enrollment_* columns; tests/test_import_ccd_school_staffing.py pins the two key sets to
# each other (#1086).
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
LEVELS_REQUIRED = frozenset(LEVEL_BAND)      # the bands' own levels must occur (one home: grade_bands)
LEA_TEACHERS_STAFF = "Teachers"
LEA_TEACHERS_INDICATOR = "Derived - Major Staffing Category"

# Per-school Σ(stored grades) vs the file's own minus-Adult-Education total: EXACT on both vintages.
MAX_ROWWISE_DISAGREE = 0
# Share of schools with membership rows that the per-school reconciliation could compare (every stored
# grade Reported and a reference total present): measured 98,014 of 99,420 = 0.986 (2024-25) and
# 98,306 of 99,678 = 0.986 (2023-24).
MIN_COMPARED_SHARE = 0.95
# Σ school-file teachers / Σ LEA-file teachers, measured 0.9864 on both 2024-25 and 2023-24.
LEA_COVERAGE_TOLERANCE = 0.05
LEA_WITHIN_BAND = 0.05
INSERT_CHUNK = 5_000


# ---------------------------------------------------------------------------------------- the year
def require_year(year: str) -> None:
    """A parseable, non-COVID school year (Critical Rule 2; #1079). The manifest pin is not a
    substitute: a COVID vintage could be pinned deliberately for another purpose."""
    try:
        start_year(year)
    except ValueError as e:
        raise DataGuardError(f"--year {year!r}: {e}") from e
    if is_covid_year(year):
        raise DataGuardError(f"--year {year}: a COVID-excluded year is never loaded (REQ-007)")


def school_year_label(year: str) -> str:
    """'2024-25' as the CCD files spell SCHOOL_YEAR: '2024-2025'."""
    s = start_year(year)
    return f"{s}-{s + 1}"


# ---------------------------------------------------------------------------------------- sources
def locate(year: str, manifest: dict, root: Path | None = None) -> dict[str, tuple[Path, dict]]:
    """The one source per file id, AS THE MANIFEST DECLARES IT (one precedence between the release
    zip and an extracted CSV: the manifest's, #1073). A year or id the manifest does not declare,
    two entries for one id, or a declared file absent on disk is refused."""
    entries = manifest.get("years", {}).get(year)
    if entries is None:
        raise DataGuardError(
            f"{year} is not declared in the {manifest.get('source')} manifest (years: "
            f"{sorted(manifest.get('years', {}))}); pin its files with nces_ccd_manifest.py --write before importing")
    d = source_manifest.year_folder(manifest, year, root)
    found: dict[str, tuple[Path, dict]] = {}
    for fid, stem in FILE_STEM.items():
        hits = [e for e in entries if e["file"].startswith(stem)]
        if len(hits) != 1:
            raise DataGuardError(
                f"CCD file {fid} for {year}: the manifest declares {len(hits)} {stem}* file(s) "
                f"({[e['file'] for e in hits]}); expected exactly one — pin it with nces_ccd_manifest.py --write")
        path = d / hits[0]["file"]
        if not path.is_file():
            raise DataGuardError(f"{path.name} is pinned for {year} but is not on disk under {d}; "
                                 f"download it (fetch_nces_ccd) or re-pin what is there")
        found[fid] = (path, hits[0])
    return found


def pinned_sha256(path: Path, entry: dict, year: str) -> str:
    """The file's sha256, REQUIRED to equal its manifest pin: a drifted file is not the file the
    manifest vouches for (the only record of which bytes a gitignored raw file held)."""
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


# ---------------------------------------------------------------------------------------- cells
def _read(stream, cols: list[str], **kw) -> pd.DataFrame:
    """Every cell as text; ONLY an empty cell is NA (pandas' default also swallows 'NA', 'None',
    'null', 'nan' — a school literally named 'None' must survive, #1071)."""
    return pd.read_csv(stream, dtype=str, usecols=cols, encoding="utf-8",
                       keep_default_na=False, na_values=[""], **kw)


def _text(v):
    """A string cell, or None for a blank — the ONE boundary where pandas' NaN becomes SQL NULL, so
    the text 'NaN' can never be stored (#934, #1071)."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)


def _unknown(values: pd.Series, vocab: set[str], *, label: str) -> None:
    """Every value is in the closed vocabulary; a blank is outside every vocabulary."""
    unknown = sorted({_text(v) or BLANK for v in values.unique()} - vocab)
    if unknown:
        raise DataGuardError(f"{label}: {len(unknown)} value(s) outside the known vocabulary — "
                             f"{unknown[:10]}; the file's labels have drifted from the parser's")


def _seen(values: pd.Series) -> set[str]:
    return {t for t in (_text(v) for v in values.unique()) if t is not None}


def _unique(values: pd.Series, *, label: str) -> None:
    dupes = values[values.duplicated()].unique()
    if len(dupes):
        raise DataGuardError(f"{label}: {len(dupes)} NCESSCH value(s) occur more than once — "
                             f"{list(dupes[:5])}; a join on them would multiply rows")


def _require_shape(values: pd.Series, pattern: re.Pattern, *, label: str) -> None:
    """Every id is exactly the digits NCES publishes (a stripped leading zero is one digit short:
    the #611 class, #1085; a blank or shifted column is caught the same way)."""
    bad = [v for v in values if not (isinstance(v, str) and pattern.fullmatch(v))]
    if bad:
        raise DataGuardError(f"{label}: {len(bad)} id(s) are not {pattern.pattern} — e.g. {bad[:5]}; "
                             f"a leading zero was stripped or a column shifted (#611)")


def _check_year(values: pd.Series, year: str, *, label: str) -> None:
    """The file's own SCHOOL_YEAR column spells the year being loaded (#1079)."""
    expected = school_year_label(year)
    seen = sorted({_text(v) or BLANK for v in values.unique()})
    if seen != [expected]:
        raise DataGuardError(f"{label}: SCHOOL_YEAR is {seen}, not {expected!r}; "
                             f"the file is not the {year} vintage (or is mis-stamped)")


def _numbers(values: pd.Series, *, label: str, ids=None, integral: bool = False) -> list:
    """Each cell as a non-negative finite number (an int when `integral`), or None for a blank — never
    0 for a blank (REQ-165). Any other token is refused naming the column and the first offenders
    (#1084): a suppression mark or a reserve code must be handled explicitly, never guessed at."""
    out, bad = [], []
    ids = list(ids) if ids is not None else [None] * len(values)
    for i, v in zip(ids, values):
        t = _text(v)
        if t is None or not t.strip():
            out.append(None)
            continue
        try:
            x = float(t)
        except ValueError:
            bad.append((i, t))
            continue
        if not (math.isfinite(x) and x >= 0) or (integral and x != int(x)):
            bad.append((i, t))
            continue
        out.append(int(x) if integral else x)
    if bad:
        kind = "non-negative integer" if integral else "non-negative number"
        raise DataGuardError(f"{label}: {len(bad)} cell(s) are not a {kind} or blank — e.g. {bad[:5]}")
    return out


# ---------------------------------------------------------------------------------------- readers
def read_directory(stream, year: str) -> pd.DataFrame:
    """029: one row per school, indexed by NCESSCH."""
    cols = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "ST", "SCH_NAME", "SY_STATUS_TEXT", "SCH_TYPE_TEXT",
            "LEVEL", "GSLO", "GSHI"]
    df = _read(stream, cols)
    _check_year(df["SCHOOL_YEAR"], year, label="029")
    _require_shape(df["NCESSCH"], NCESSCH_RE, label="029 NCESSCH")
    _require_shape(df["LEAID"], LEAID_RE, label="029 LEAID")
    _unique(df["NCESSCH"], label="029 directory")
    _unknown(df["LEVEL"], LEVELS, label="029 LEVEL")
    require_labels_seen(LEVELS_REQUIRED, _seen(df["LEVEL"]), label="029 LEVEL")
    return df.drop(columns="SCHOOL_YEAR").set_index("NCESSCH")


def read_staff(stream, year: str) -> dict[str, dict]:
    """059: one 'Education Unit Total' row per school → {NCESSCH: {LEAID, teachers_fte, teachers_dms_flag}}.
    teachers_fte is the reported value, or None with the flag when NCES did not report one."""
    cols = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "TEACHERS", "TOTAL_INDICATOR", "DMS_FLAG"]
    df = _read(stream, cols)
    _check_year(df["SCHOOL_YEAR"], year, label="059")
    df["TOTAL_INDICATOR"] = df["TOTAL_INDICATOR"].str.strip()
    _unknown(df["TOTAL_INDICATOR"], STAFF_INDICATORS, label="059 TOTAL_INDICATOR")
    _unknown(df["DMS_FLAG"], DMS_FLAGS, label="059 DMS_FLAG")
    require_labels_seen(STAFF_INDICATORS, _seen(df["TOTAL_INDICATOR"]), label="059 TOTAL_INDICATOR")
    require_labels_seen({REPORTED}, _seen(df["DMS_FLAG"]), label="059 DMS_FLAG")
    df = df[df["TOTAL_INDICATOR"] == EDUCATION_UNIT_TOTAL]
    _unique(df["NCESSCH"], label="059 staff")
    _require_shape(df["NCESSCH"], NCESSCH_RE, label="059 NCESSCH")
    fte = _numbers(df["TEACHERS"], label="059 TEACHERS", ids=df["NCESSCH"])
    out = {}
    for ncessch, leaid, value, flag in zip(df["NCESSCH"], df["LEAID"], fte, df["DMS_FLAG"]):
        out[ncessch] = {"LEAID": leaid, "teachers_fte": value if flag == REPORTED else None,
                        "teachers_dms_flag": flag, "unreported_value": value is not None and flag != REPORTED}
    return out


def read_membership(stream, year: str, *, chunksize: int = 2_000_000) -> tuple[dict[str, dict], TotalReconciliation, dict]:
    """052: the 'Subtotal 4 - By Grade' rows → {NCESSCH: {LEAID, membership_flags, memb_*...}} with a
    memb_* value only where the grade row is present AND Reported (else None, the flag in
    membership_flags), the per-school reconciliation receipt against the file's own
    minus-Adult-Education total, and the counts the lineage row records."""
    cols = ["SCHOOL_YEAR", "NCESSCH", "LEAID", "GRADE", "STUDENT_COUNT", "TOTAL_INDICATOR", "DMS_FLAG"]
    sub, ref = [], []
    seen_ti, seen_grade, seen_flag = set(), set(), set()
    for chunk in _read(stream, cols, chunksize=chunksize):
        _check_year(chunk["SCHOOL_YEAR"], year, label="052")
        chunk["TOTAL_INDICATOR"] = chunk["TOTAL_INDICATOR"].str.strip()
        _unknown(chunk["TOTAL_INDICATOR"], MEMBERSHIP_INDICATORS, label="052 TOTAL_INDICATOR")
        _unknown(chunk["DMS_FLAG"], DMS_FLAGS, label="052 DMS_FLAG")
        seen_ti |= _seen(chunk["TOTAL_INDICATOR"])
        seen_flag |= _seen(chunk["DMS_FLAG"])
        s = chunk[chunk["TOTAL_INDICATOR"] == SUBTOTAL_BY_GRADE]
        _unknown(s["GRADE"], GRADE_VOCAB, label="052 GRADE (Subtotal 4)")
        seen_grade |= _seen(s["GRADE"])
        sub.append(s[["NCESSCH", "LEAID", "GRADE", "STUDENT_COUNT", "DMS_FLAG"]])
        ref.append(chunk[chunk["TOTAL_INDICATOR"] == EDUCATION_UNIT_TOTAL_MINUS_ADULT][["NCESSCH", "STUDENT_COUNT"]])
    require_labels_seen({SUBTOTAL_BY_GRADE, EDUCATION_UNIT_TOTAL_MINUS_ADULT}, seen_ti, label="052 TOTAL_INDICATOR")
    require_labels_seen(set(GRADE_COLUMN), seen_grade, label="052 GRADE (Subtotal 4)")
    require_labels_seen({REPORTED}, seen_flag, label="052 DMS_FLAG")
    sub = pd.concat(sub, ignore_index=True)
    ref = pd.concat(ref, ignore_index=True)
    _require_shape(sub["NCESSCH"], NCESSCH_RE, label="052 NCESSCH")
    _unique(ref["NCESSCH"], label=f"052 '{EDUCATION_UNIT_TOTAL_MINUS_ADULT}'")
    dup = sub.duplicated(["NCESSCH", "GRADE"])
    if dup.any():
        raise DataGuardError(f"052 Subtotal 4: {int(dup.sum())} duplicate (NCESSCH, GRADE) row(s)")
    counts = _numbers(sub["STUDENT_COUNT"], label="052 STUDENT_COUNT (Subtotal 4)", ids=sub["NCESSCH"], integral=True)
    ref_total = dict(zip(ref["NCESSCH"], _numbers(
        ref["STUDENT_COUNT"], label=f"052 STUDENT_COUNT ('{EDUCATION_UNIT_TOTAL_MINUS_ADULT}')",
        ids=ref["NCESSCH"], integral=True)))

    rows: dict[str, dict] = {}
    residual: dict[str, int] = {}
    unreported, unreported_by_fips = Counter(), Counter()
    for ncessch, leaid, grade, value, flag in zip(sub["NCESSCH"], sub["LEAID"], sub["GRADE"], counts, sub["DMS_FLAG"]):
        row = rows.setdefault(ncessch, {"LEAID": leaid, "membership_flags": {}})
        if grade == GRADE_RESIDUAL:
            residual[ncessch] = value or 0
            continue
        if grade not in GRADE_COLUMN:
            continue
        if flag != REPORTED:
            # Not a count NCES reports: NULL with the flag kept (#1070). 'Missing' / 'Not reported' /
            # 'Suppressed' cells are blank anyway; 'Manual adjustment' ones are all exactly 0.
            row["membership_flags"][grade] = flag
            unreported[flag] += 1
            unreported_by_fips[leaid[:2]] += 1
            value = None
        row[GRADE_COLUMN[grade]] = value

    # Per school: Σ(stored grades) + the grade-unknown residual must equal the file's own
    # minus-Adult-Education total. A school with an unreported stored grade cannot be summed and is
    # not compared (its NULL is the record) — but most schools MUST compare (#1078).
    n_compared = n_disagree = 0
    ours = theirs = 0.0
    for ncessch, row in rows.items():
        values = [row.get(c) for c in GRADE_COLUMN.values() if c in row]
        if any(v is None for v in values) or ref_total.get(ncessch) is None:
            continue
        n_compared += 1
        s = sum(values) + residual.get(ncessch, 0)
        ours += s
        theirs += ref_total[ncessch]
        if s != ref_total[ncessch]:
            n_disagree += 1
    if rows and n_compared < MIN_COMPARED_SHARE * len(rows):
        raise DataGuardError(
            f"052 per-school reconciliation compared only {n_compared:,} of {len(rows):,} schools "
            f"({n_compared / len(rows):.1%}, floor {MIN_COMPARED_SHARE:.0%}); a reconciliation that skips "
            f"most schools is not a verdict (#1078)")
    receipt = reconcile_total(
        ours, theirs,
        label=f"052 Σ stored grades + '{GRADE_RESIDUAL}' vs '{EDUCATION_UNIT_TOTAL_MINUS_ADULT}' per school",
        n_compared=n_compared, n_disagree=n_disagree, max_disagree=MAX_ROWWISE_DISAGREE)
    extras = {
        "schools": len(rows),
        "compared_share": round(n_compared / len(rows), 5) if rows else None,
        "grade_not_specified_students": sum(residual.values()),
        "unreported_cells": dict(sorted(unreported.items())),
        "unreported_cells_by_fips": dict(sorted(unreported_by_fips.items())),
    }
    return rows, receipt, extras


def read_lea_teachers(stream, year: str) -> dict[str, float | None]:
    """ccd_lea_059: the 'Teachers' major-staffing-category total per LEA (value or None)."""
    cols = ["SCHOOL_YEAR", "LEAID", "STAFF", "STAFF_COUNT", "TOTAL_INDICATOR"]
    df = _read(stream, cols)
    _check_year(df["SCHOOL_YEAR"], year, label="LEA 059")
    df["STAFF"] = df["STAFF"].str.strip()
    df["TOTAL_INDICATOR"] = df["TOTAL_INDICATOR"].str.strip()
    require_labels_seen({LEA_TEACHERS_STAFF}, _seen(df["STAFF"]), label="LEA 059 STAFF")
    require_labels_seen({LEA_TEACHERS_INDICATOR}, _seen(df["TOTAL_INDICATOR"]), label="LEA 059 TOTAL_INDICATOR")
    df = df[(df["STAFF"] == LEA_TEACHERS_STAFF) & (df["TOTAL_INDICATOR"] == LEA_TEACHERS_INDICATOR)]
    dupes = df["LEAID"].duplicated()
    if dupes.any():
        raise DataGuardError(f"LEA 059 'Teachers': {int(dupes.sum())} duplicate LEAID row(s)")
    _require_shape(df["LEAID"], LEAID_RE, label="LEA 059 LEAID")
    return dict(zip(df["LEAID"], _numbers(df["STAFF_COUNT"], label="LEA 059 STAFF_COUNT ('Teachers')", ids=df["LEAID"])))


# ---------------------------------------------------------------------------------------- assembly
def _subset_of_directory(directory: pd.DataFrame, other: dict[str, dict], *, label: str) -> None:
    dir_leaid = directory["LEAID"].to_dict()
    missing = [n for n in other if n not in dir_leaid]
    if missing:
        raise DataGuardError(f"{label}: {len(missing)} school(s) are not in the 029 directory "
                             f"({missing[:5]}); the files are not the same vintage")
    mismatch = [n for n, r in other.items() if r["LEAID"] != dir_leaid[n]]
    if mismatch:
        raise DataGuardError(f"{label}: {len(mismatch)} school(s) carry a different LEAID than the 029 "
                             f"directory ({mismatch[:5]})")


def assemble(year: str, directory: pd.DataFrame, staff: dict[str, dict], membership: dict[str, dict],
             shas: dict[str, str]) -> list[dict]:
    """One ccd_school_staffing row per 029 school, 052/059 values joined on NCESSCH. Every text cell
    passes through _text, so a blank is NULL (#1071)."""
    _subset_of_directory(directory, staff, label="059 staff")
    _subset_of_directory(directory, membership, label="052 membership")
    rows = []
    for ncessch, d in directory.to_dict(orient="index").items():
        s = staff.get(ncessch, {})
        m = membership.get(ncessch, {})
        row = {
            "ncessch": ncessch,
            "source_year": year,
            "leaid": d["LEAID"],
            "state": _text(d["ST"]),
            "school_name": _text(d["SCH_NAME"]),
            "sy_status": _text(d["SY_STATUS_TEXT"]),
            "sch_type": _text(d["SCH_TYPE_TEXT"]),
            "level": _text(d["LEVEL"]),
            "gslo": _text(d["GSLO"]),
            "gshi": _text(d["GSHI"]),
            "teachers_fte": s.get("teachers_fte"),
            "teachers_dms_flag": s.get("teachers_dms_flag"),
            "membership_flags": m.get("membership_flags") or None,
            "src_029_sha256": shas["029"],
            "src_052_sha256": shas["052"],
            "src_059_sha256": shas["059"],
        }
        for c in GRADE_COLUMN.values():
            row[c] = m.get(c)
        rows.append(row)
    return rows


def lea_coverage(rows: list[dict], lea: dict[str, float | None]) -> dict:
    """Σ school-file teachers vs Σ LEA-file 'Teachers', LEA by LEA. Reported (returned for the lineage
    row) and guarded only at the aggregate: outside ±LEA_COVERAGE_TOLERANCE is the wrong file pair."""
    school_sum: dict[str, float] = {}
    for r in rows:
        if r["teachers_fte"] is not None:
            school_sum[r["leaid"]] = school_sum.get(r["leaid"], 0.0) + float(r["teachers_fte"])
    ours = theirs = 0.0
    n = within = 0
    for leaid, lea_fte in lea.items():
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
            "leas_with_school_fte_only": len(set(school_sum) - set(lea))}


def load_year(year: str, root: Path | None = None, manifest: dict | None = None) -> tuple[list[dict], dict]:
    """Locate, pin, parse and guard the year's files. Returns the rows and the lineage details."""
    require_year(year)
    manifest = source_manifest.load(MANIFEST_SOURCE) if manifest is None else manifest
    sources = locate(year, manifest, root)
    paths = {fid: p for fid, (p, _) in sources.items()}
    shas = {fid: pinned_sha256(p, entry, year) for fid, (p, entry) in sources.items()}
    print(f"Sources for {year}:")
    for fid in FILE_STEM:
        print(f"  {fid}: {paths[fid].name}  sha256 {shas[fid][:12]}…")
    with open_source(paths["029"]) as f:
        directory = read_directory(f, year)
    print(f"  029: {len(directory):,} schools")
    with open_source(paths["059"]) as f:
        staff = read_staff(f, year)
    n_unreported_fte = sum(s["unreported_value"] for s in staff.values())
    print(f"  059: {len(staff):,} schools, {sum(s['teachers_fte'] is not None for s in staff.values()):,} "
          f"with a reported teacher count ({n_unreported_fte:,} unreported values stored NULL)")
    with open_source(paths["052"]) as f:
        membership, memb_receipt, memb = read_membership(f, year)
    print(f"  052: {memb['schools']:,} schools; per-school reconciliation {memb_receipt.n_compared:,} compared "
          f"({memb['compared_share']:.1%}), {memb_receipt.n_disagree:,} differ, aggregate ratio {memb_receipt.ratio:.5f}; "
          f"unreported cells {memb['unreported_cells']}")
    with open_source(paths[LEA_FILE_ID]) as f:
        lea = read_lea_teachers(f, year)
    rows = assemble(year, directory, staff, membership, shas)
    require_nonempty_selection(rows, what=f"ccd_school_staffing rows for {year}", available=[year])
    coverage = lea_coverage(rows, lea)
    print(f"  Coverage: Σ school teachers {coverage['school_teachers_fte']:,.1f} / Σ LEA teachers "
          f"{coverage['lea_teachers_fte']:,.1f} = {coverage['ratio']:.4f}; "
          f"{coverage['leas_within_5pct']:,} of {coverage['leas_compared']:,} LEAs within ±5%")
    details = {
        "year": year,
        "sources": {fid: [paths[fid].name, shas[fid]] for fid in FILE_STEM},
        "schools": len(rows),
        "schools_with_teachers": sum(r["teachers_fte"] is not None for r in rows),
        "teachers_unreported_values": n_unreported_fte,
        "schools_with_membership": memb["schools"],
        "membership_compared_share": memb["compared_share"],
        "grade_not_specified_students": memb["grade_not_specified_students"],
        "membership_unreported_cells": memb["unreported_cells"],
        "membership_unreported_cells_by_fips": memb["unreported_cells_by_fips"],
        "membership_reconciliation": memb_receipt._asdict(),
        "lea_coverage": coverage,
    }
    return rows, details


# ---------------------------------------------------------------------------------------- write
def require_district_match(session, rows: list[dict]) -> dict:
    """The file's LEAIDs must match ≥ MATCH_COVERAGE_FLOOR of min(file LEAs, our districts): a stripped
    leading zero would otherwise load cleanly and silently lose every FIPS<10 state at the T6/T7 join
    (#611, #1085). Measured 2024-25: 17,644 of min(18,587, 17,842) = 98.9%."""
    leaids = sorted({r["leaid"] for r in rows})
    n_ours = session.execute(select(func.count()).select_from(District)).scalar()
    n_matched = session.execute(
        select(func.count()).select_from(District).where(District.nces_id.in_(leaids))).scalar()
    require_match_coverage(len(leaids), n_matched, n_ours, label="ccd_school_staffing LEAIDs vs districts")
    return {"file_leas": len(leaids), "districts": n_ours, "matched": n_matched}


def write_year(session, year: str, rows: list[dict], details: dict) -> int:
    """REPLACE the year's rows, then log the lineage row, all in the caller's transaction."""
    require_nonempty_selection(rows, what=f"ccd_school_staffing rows for {year}", available=[year])
    details["district_match"] = require_district_match(session, rows)
    session.execute(delete(CCDSchoolStaffing).where(CCDSchoolStaffing.source_year == year))
    # A Core insert on the Table: one executemany per chunk. The ORM bulk path (insert(Model)) drops
    # None-valued keys row by row and fragments a chunk into a statement per run of identical key
    # sets — measured ~79,000 statements per vintage (#1074).
    table = CCDSchoolStaffing.__table__
    for i in range(0, len(rows), INSERT_CHUNK):
        session.execute(insert(table), rows[i:i + INSERT_CHUNK])
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
