#!/usr/bin/env python3
"""
Import ONE SPED baseline vintage from federal sources (profiles: sped_baseline_profiles.PROFILES).

This script imports:
1. IDEA 618 Personnel (state-level SPED teachers + paraprofessionals, school age)
2. IDEA 618 Child Count + Educational Environments (state-level school-age SPED students)
3. CRDC Enrollment (LEA-level SPED students)
4. CCD LEA Membership of the CRDC's own year (LEA-level total enrollment)

And calculates:
- State: SPED teachers (and teachers + paras) per self-contained SPED student; self-contained share
- LEA: SPED students / total students

Each vintage is keyed by baseline_year and replaces only its own rows (#999).

Usage:
    python import_sped_baseline.py [--baseline-year 2017-18] [--sample N]
"""

import argparse
import csv
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from infrastructure.database.connection import session_scope
from infrastructure.utilities.common import EDUCATION_UNIT_TOTAL_MINUS_ADULT, ccd_education_unit_totals
from infrastructure.utilities.school_year import SPED_BASELINE_YEAR
from infrastructure.database.models import SpedStateBaseline, SpedLeaBaseline, DataLineage
from infrastructure.utilities.data_guards import DataGuardError, reconcile_total, require_labels_seen
from infrastructure.database.migrations.sped_baseline_profiles import (
    BaselineProfile, ChildCountProfile, PersonnelProfile, PROFILES, get_profile, verify_source,
)

# File paths, sha256 pins and label vocabularies are per vintage: sped_baseline_profiles.PROFILES.

# State name to abbreviation mapping
STATE_ABBR = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA',
    'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'District of Columbia': 'DC',
    'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL',
    'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA',
    'Maine': 'ME', 'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
    'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
    'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR',
    'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
    'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA',
    'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY',
    'American Samoa': 'AS', 'Guam': 'GU', 'Northern Marianas': 'MP', 'Puerto Rico': 'PR',
    'Virgin Islands': 'VI',
    # Skip BIE - not a valid 2-letter state code
    # 'Bureau of Indian Education': 'BIE'
}


# CRDC reserve codes — negative values that are NOT counts (2017-18 Manual Table 2; 2023-24 Data File
# User's Manual Table 1, https://civilrightsdata.ed.gov/assets/downloads/2023-24%20User's%20Manual.pdf,
# sha256 85541dd2…f281330, modified 2026-08-17). Pinned for the record; the parser does not depend on
# the list being complete, because NO count or FTE in these federal files is ever legitimately
# negative — every negative is missing (#960). IDEA uses the same convention (-8 small-cell, -9 n/a
# in the LEA files, #1004).
CRDC_RESERVE_CODES = {
    -3: "Skip Logic Failure / Processing Error",
    -5: "Action Plan",
    -6: "Force Certified",
    -7: "Data are Indeterminable (2023-24)",
    -8: "EDFacts Missing Data (2017-18)",
    -9: "Not Applicable / Skipped",          # 2023-24: 1,835 schools carry it in all of TOT_ENR_M/F + SCH_ENR_IDEA_M/F
    -10: "Suppressed in Compliance with Executive Order 14168 (2023-24)",   # every school's nonbinary _X column
    -11: "Suppressed for Data Quality",
    -12: "Suppressed for privacy (2021-22)",
    -13: "Missing DIND Skip Logic (2023-24)",
}


def safe_float(value: str) -> float | None:
    """Parse a federal SPED count/FTE cell. Dashes, blanks, N/A, suppression marks ('x', '*') and any
    NEGATIVE value (a reserve code, never a count — #960) are missing: None, never a number."""
    if value is None or value.strip() in ['-', '', 'N/A', 'na', 'NA']:
        return None
    try:
        f = float(value.strip().replace(',', ''))
    except (ValueError, AttributeError):
        return None
    return f if f >= 0 else None


def safe_int(value: str) -> int | None:
    """safe_float, as an int."""
    f = safe_float(value)
    return int(f) if f is not None else None


HEADER_FIRST_CELL = 'Year'
MAX_PREAMBLE_ROWS = 20


def normalize_header(cell: str) -> str:
    """Collapse internal whitespace: the 2017-18 personnel header wraps one name over a newline
    ('…Certified/\\nParaprofessionals…'), so whitespace around '/' is dropped too."""
    return ' '.join(cell.split()).replace(' /', '/').replace('/ ', '/')


def seek_header_row(reader, *, label: str, first_cell: str = HEADER_FIRST_CELL) -> list[str]:
    """Advance `reader` to the column-header row and return it, found by CONTENT (first cell is
    `first_cell`), never by a fixed preamble length: the 2017-18 IDEA files carry 4 metadata rows,
    the 2024-25 ones 5 (a blank row 4), and `range(4)` would hand the blank row over as headers so
    every lookup misses and a hard-coded fallback index reads the wrong column (#975)."""
    for i, row in enumerate(reader):
        if row and row[0].strip() == first_cell:
            return [normalize_header(h) for h in row]
        if i >= MAX_PREAMBLE_ROWS:
            break
    raise DataGuardError(f"{label}: no header row (first cell {first_cell!r}) within the first "
                         f"{MAX_PREAMBLE_ROWS} rows — the file layout has changed")


# Known names of the aggregate rows outside STATE_ABBR (skipped silently; anything else warns)
NON_STATE_ROWS = {
    'Bureau of Indian Education', 'Federated States of Micronesia', 'Republic of Palau',
    'Republic of the Marshall Islands', 'US, Outlying Areas, and Freely Associated States',
    'US, Outlying Areas, And Freely Associated States',     # the 2023-24 personnel file's capitalization
}

# Personnel column names — identical in the 2017-18 and 2023-24 files (the wrapped
# '…Certified/\nParaprofessionals…' header is collapsed by normalize_header). A missing one is a layout
# change, never index 3/4/5 (#975).
P_YEAR, P_STATE, P_TYPE = 'Year', 'State', 'Personnel Type'
P_QUAL = 'Teachers Fully Certified/Paraprofessionals Qualified'
P_NOT_QUAL = 'Teachers Not Fully Certified/Paraprofessionals Not Qualified'
P_TOTAL = 'Teachers/Paraprofessionals Total'


def parse_personnel_rows(headers: list[str], rows, profile: PersonnelProfile) -> dict[str, dict[str, float | None]]:
    """Pure parse of the personnel rows (after the header row) into per-state teacher/para FTE.

    Returns {state_abbr: {'teachers_certified', 'teachers_not_certified', 'teachers_total',
    'paras_qualified', 'paras_not_qualified', 'paras_total'}} (absent keys = type not in file for
    that state). Only rows whose Year cell is the profile's are read.
    """
    year = profile.year_cell
    required = [P_YEAR, P_STATE, P_TYPE, P_QUAL, P_NOT_QUAL, P_TOTAL]
    headers = [normalize_header(h) for h in headers]
    require_labels_seen(required, headers, label=f"IDEA 618 personnel {year} header row")
    col = {name: headers.index(name) for name in required}
    width = max(col.values()) + 1

    state_data: dict[str, dict[str, float | None]] = {}
    personnel_types_seen: set[str] = set()
    for row in rows:
        if len(row) < width:
            continue
        if row[col[P_YEAR]].strip() != year:
            continue
        state_name = row[col[P_STATE]].strip()
        personnel_type = row[col[P_TYPE]].strip()
        personnel_types_seen.add(personnel_type)

        state_abbr = STATE_ABBR.get(state_name)
        if not state_abbr:
            if state_name not in NON_STATE_ROWS:
                print(f"  Warning: Unknown state '{state_name}'")
            continue
        record = state_data.setdefault(state_abbr, {})
        qualified = safe_float(row[col[P_QUAL]])
        not_qualified = safe_float(row[col[P_NOT_QUAL]])
        total = safe_float(row[col[P_TOTAL]])
        if personnel_type == profile.teacher_type:
            record.update(teachers_certified=qualified, teachers_not_certified=not_qualified,
                          teachers_total=total)
        elif personnel_type == profile.para_type:
            record.update(paras_qualified=qualified, paras_not_qualified=not_qualified, paras_total=total)

    # G2 (#970): the labels we filter on must occur in the file — a relabel ('Ages 6-21' → 'School Age'
    # in the 2023-24 vintage) must be a parse error, never a run that loads zero teachers.
    require_labels_seen({profile.teacher_type, profile.para_type}, personnel_types_seen,
                        label=f"IDEA 618 personnel {year} types")
    return state_data


def read_personnel_file(profile: PersonnelProfile, path: Path | None = None) -> dict[str, dict[str, float | None]]:
    """Open the personnel CSV (the profile's own file unless `path` overrides it, for fixtures)."""
    path = path or profile.source.path
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        headers = seek_header_row(reader, label=f"IDEA 618 personnel {path.name}")
        return parse_personnel_rows(headers, reader, profile)


# Child-count column names shared by every vintage; the age-band columns come from the profile.
COL_YEAR, COL_STATE, COL_ENV, COL_DISABILITY = 'Year', 'State Name', 'SEA Education Environment', 'SEA Disability Category'


def parse_child_count_rows(headers: list[str], rows, profile: ChildCountProfile) -> dict[str, dict]:
    """Pure parse of the child-count rows (after the header row) into per-state totals.

    Returns {state_abbr: {'early_childhood': int, 'school_age': {band: int}, 'self_contained':
    {band: int}, 'mainstreamed': {band: int}, 'age_5_school_age': int | None}} with one entry per
    band in profile.school_age_cols. Only the profile's year cell and the 'All Disabilities' rows are
    read; states outside STATE_ABBR (BIE, the US aggregate, freely associated states) are skipped.

    The file carries its own per-age-band total rows — those ARE the totals; summing the environment
    rows and the total row together double-counts (#970).
    """
    year = profile.year_cell
    bands = dict(profile.school_age_cols)
    headers = [normalize_header(h) for h in headers]
    required = [COL_YEAR, COL_STATE, COL_ENV, COL_DISABILITY, profile.early_childhood_col, *bands.values()]
    if profile.age_5_school_age_col:
        required.append(profile.age_5_school_age_col)
    require_labels_seen(required, headers, label=f"IDEA 618 child count {year} header row")
    col = {name: headers.index(name) for name in required}
    width = max(col.values()) + 1

    def fresh():
        return {'early_childhood': 0, 'school_age': dict.fromkeys(bands, 0),
                'self_contained': dict.fromkeys(bands, 0), 'mainstreamed': dict.fromkeys(bands, 0),
                'age_5_school_age': None}

    state_totals: dict[str, dict] = {}
    env_sum: dict[str, dict[str, int]] = {}     # Σ environment rows (NOT the total row) per state+band, for G1
    environments_seen: set[str] = set()
    for row in rows:
        if len(row) < width:
            continue
        if row[col[COL_YEAR]].strip() != year or row[col[COL_DISABILITY]].strip() != 'All Disabilities':
            continue
        state_abbr = STATE_ABBR.get(row[col[COL_STATE]].strip())
        if not state_abbr:
            continue
        environment = row[col[COL_ENV]].strip()
        environments_seen.add(environment)
        totals = state_totals.setdefault(state_abbr, fresh())
        counts = {band: safe_int(row[col[c]]) or 0 for band, c in bands.items()}

        if environment == profile.early_childhood_total_row:
            totals['early_childhood'] = safe_int(row[col[profile.early_childhood_col]]) or 0
        elif environment == profile.school_age_total_row:
            totals['school_age'] = counts
            if profile.age_5_school_age_col:
                totals['age_5_school_age'] = safe_int(row[col[profile.age_5_school_age_col]])
        else:
            sums = env_sum.setdefault(state_abbr, dict.fromkeys(bands, 0))
            for band, n in counts.items():
                sums[band] += n
                if environment in profile.self_contained:
                    totals['self_contained'][band] += n
                elif environment in profile.mainstreamed:
                    totals['mainstreamed'][band] += n

    # G2 both ways: every label the parser keys on must occur in the file (#970's 'Separate School'
    # never did), and every label the file carries must be one the parser classifies (#982).
    require_labels_seen(
        profile.self_contained | profile.mainstreamed
        | {profile.school_age_total_row, profile.early_childhood_total_row},
        environments_seen, label=f"IDEA 618 child count {year} environments",
    )
    unknown = sorted(environments_seen - profile.known_environments)
    if unknown:
        raise DataGuardError(
            f"IDEA 618 child count {year}: {len(unknown)} environment label(s) the parser does not "
            f"classify — {unknown}. Add each to the profile's self_contained/mainstreamed/other; an "
            f"unclassified school-age setting silently leaves a category short."
        )
    # G1, per band: the environment rows must add up to the file's own total row (per state; exact
    # 2× = the total row was summed in). A state whose Total row is missing/suppressed while its
    # environment rows are numeric reaches reconcile_total with reference 0 and fails there (#982) —
    # it is never stored as a school-age count of 0.
    for state_abbr, totals in state_totals.items():
        for band in bands:
            env_n = env_sum.get(state_abbr, {}).get(band, 0)
            if totals['school_age'][band] or env_n:
                reconcile_total(env_n, totals['school_age'][band],
                                label=f"IDEA 618 child count {year} {state_abbr} ({band}): Σ environments vs Total row")
    return state_totals


def read_child_count_file(profile: ChildCountProfile, path: Path | None = None) -> dict[str, dict]:
    """Open the child-count CSV, seek its header row by content, and parse it."""
    path = path or profile.source.path
    with open(path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        headers = seek_header_row(reader, label=f"IDEA 618 child count {path.name}")
        return parse_child_count_rows(headers, reader, profile)


def build_state_baselines(profile: BaselineProfile, band: str | None = None) -> dict[str, SpedStateBaseline]:
    """The per-state baseline rows a vintage produces, unsaved — the one construction both the import
    and the T4 before/after measurement use (#1002 imports this; it never re-derives a ratio).

    `band` overrides the profile's school_age_band (the measurement compares both); with neither set,
    this refuses — the band is a methodology decision, not a default (#1003).
    """
    band = band or profile.school_age_band
    if band not in profile.child_count.school_age_cols:
        raise DataGuardError(f"SPED baseline {profile.baseline_year}: school-age band {band!r} is not "
                             f"decided or not in the file ({sorted(profile.child_count.school_age_cols)})")
    personnel = read_personnel_file(profile.personnel)
    children = read_child_count_file(profile.child_count)

    out: dict[str, SpedStateBaseline] = {}
    for state_abbr in sorted(set(personnel) | set(children)):
        fte = personnel.get(state_abbr, {})
        teachers, paras = fte.get('teachers_total'), fte.get('paras_total')
        rec = SpedStateBaseline(
            state=state_abbr,
            baseline_year=profile.baseline_year,
            personnel_year=profile.personnel.source.data_year,
            child_count_year=profile.child_count.source.data_year,
            school_age_band=band,
            personnel_source_file=profile.personnel.source.path.name,
            child_count_source_file=profile.child_count.source.path.name,
            sped_teachers_certified=fte.get('teachers_certified'),
            sped_teachers_not_certified=fte.get('teachers_not_certified'),
            sped_teachers_total=teachers,
            sped_paras_qualified=fte.get('paras_qualified'),
            sped_paras_not_qualified=fte.get('paras_not_qualified'),
            sped_paras_total=paras,
        )
        if (teachers or 0) > 0 or (paras or 0) > 0:
            rec.sped_instructional_total = (teachers or 0) + (paras or 0)
        if state_abbr in children:
            t = children[state_abbr]
            rec.sped_students_early_childhood = t['early_childhood'] or None
            rec.sped_students_school_age = t['school_age'][band] or None
            rec.sped_students_age_5_school_age = t['age_5_school_age']
            rec.sped_students_total = (t['early_childhood'] or 0) + (t['school_age'][band] or 0) or None
            rec.sped_students_self_contained = t['self_contained'][band] or None
            rec.sped_students_mainstreamed = t['mainstreamed'][band] or None
            rec.calculate_ratios()
        out[state_abbr] = rec
    return out


def import_idea_state_baseline(profile: BaselineProfile) -> dict[str, SpedStateBaseline]:
    """IDEA 618 personnel + child count → per-state baseline rows for one vintage."""
    print(f"\n=== Importing IDEA 618 state baseline {profile.baseline_year} "
          f"(personnel {profile.personnel.source.data_year}, child count {profile.child_count.source.data_year}) ===")
    state_data = build_state_baselines(profile)

    teachers_count = sum(1 for s in state_data.values() if s.sped_teachers_total)
    paras_count = sum(1 for s in state_data.values() if s.sped_paras_total)
    total_sc = sum(s.sped_students_self_contained or 0 for s in state_data.values())
    total_sa = sum(s.sped_students_school_age or 0 for s in state_data.values())
    print(f"  SPED teacher data for {teachers_count} states, paraprofessional data for {paras_count}")
    print(f"  School age ({profile.school_age_band}): {total_sa:,}; self-contained {total_sc:,} "
          f"({(total_sc / total_sa * 100) if total_sa else 0:.1f}%)")
    return state_data


# IDEA 618 LEA educational environments (#1004, T6): per-LEA school-age environment counts, wide
# format, NCES LEA ID carried. `-8` = small-cell suppression, `-9` = questionable data quality, blank =
# not reported — all missing (safe_int). The school-age environment columns partition the
# 'All Educational Environments' total, which G1 checks per row where every cell is numeric.
LEA_ENV_TOTAL = 'School Age All Educational Environments'
LEA_ENV_SELF_CONTAINED = ('School Age Inside regular class less than 40% of the day', 'School Age Separate School')
LEA_ENV_PARTS = (
    'School Age Inside regular class 80% or more of the day',
    'School Age Inside regular class 40% through 79% of the day',
    *LEA_ENV_SELF_CONTAINED,
    'School Age Residential Facility', 'School Age Homebound/Hospital',
    'School Age Correctional Facilities', 'School Age Parentally placed in private schools',
)


# Measured 2026-10-31 on the 2024-25 file: 6 of 7,021 fully-numeric rows miss their own total, all
# Wisconsin, each 1-3 students UNDER it (unassigned students, not a dropped category). A relabel or a
# dropped column moves thousands of rows, so the cap sits just above the measured six.
LEA_ENV_MAX_ROW_DISAGREE = 10


@dataclass
class LeaEnvironments:
    total: int | None             # school-age, all environments
    self_contained: int | None    # <40% + separate school; None when either cell is missing

    @property
    def share(self) -> float | None:
        if self.total and self.self_contained is not None:
            return self.self_contained / self.total
        return None


def parse_lea_environment_rows(headers: list[str], rows) -> dict[str, LeaEnvironments]:
    """Pure: the IDEA LEA environments file → {nces_leaid: LeaEnvironments}. A share is published only
    when the total AND both self-contained cells are real counts — a suppressed cell is never read as
    0 (#1004). G1: where every school-age cell is numeric, the parts must sum to the row's own total."""
    headers = [normalize_header(h) for h in headers]
    required = ['NCES LEA ID', LEA_ENV_TOTAL, *LEA_ENV_PARTS]
    require_labels_seen(required, headers, label="IDEA 618 LEA environments header row")
    col = {name: headers.index(name) for name in required}
    out: dict[str, LeaEnvironments] = {}
    compared = disagree = 0
    for row in rows:
        if len(row) <= max(col.values()):
            continue
        lea_id = row[col['NCES LEA ID']].strip()
        if len(lea_id) != 7:
            continue
        total = safe_int(row[col[LEA_ENV_TOTAL]])
        parts = [safe_int(row[col[c]]) for c in LEA_ENV_PARTS]
        if total is not None and all(v is not None for v in parts):
            compared += 1
            disagree += sum(parts) != total
        lt40, sep = (safe_int(row[col[c]]) for c in LEA_ENV_SELF_CONTAINED)
        out[lea_id] = LeaEnvironments(total, lt40 + sep if lt40 is not None and sep is not None else None)
    reconcile_total(compared - disagree, compared, label="IDEA 618 LEA environments: rows whose parts sum to their total",
                    n_compared=compared, n_disagree=disagree, max_disagree=LEA_ENV_MAX_ROW_DISAGREE)
    return out


def read_lea_environments(path: Path) -> dict[str, LeaEnvironments]:
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        headers = seek_header_row(reader, label=f"IDEA 618 LEA environments {path.name}", first_cell='School Year')
        return parse_lea_environment_rows(headers, reader)


CRDC_COUNT_COLS = ('SCH_ENR_IDEA_M', 'SCH_ENR_IDEA_F', 'TOT_ENR_M', 'TOT_ENR_F')


@dataclass
class CrdcLea:
    lea_name: str
    state: str
    sped_m: int = 0
    sped_f: int = 0
    tot_m: int = 0
    tot_f: int = 0
    schools: int = 0
    schools_reserved: int = 0


def aggregate_crdc_rows(rows) -> dict[str, CrdcLea]:
    """Pure: CRDC school rows → per-LEA SPED (IDEA) and total enrollment, M+F.

    PAIRWISE exclusion (#960, Ian 2026-10-31): a school contributes to an LEA's SPED AND total sums only
    when all four of its counts are valid (non-negative, present). The baseline is a ratio, so dropping
    a school from numerator and denominator together keeps it unbiased; CRDC's own convention (reserve
    = 0 inside a calculated total) would not. Excluded schools are COUNTED, so the LEA can be flagged.
    Nonbinary `_X` columns are not read: 2023-24 blanks every one to -10 (EO 14168), so M+F is the
    whole of what the file can say — its undercount vs CCD is measured, not assumed (#1001).
    """
    leas: dict[str, CrdcLea] = {}
    for row in rows:
        lea_id = (row.get('LEAID') or '').strip()
        if len(lea_id) != 7:
            continue
        lea = leas.setdefault(lea_id, CrdcLea((row.get('LEA_NAME') or '').strip(),
                                              (row.get('LEA_STATE') or '').strip()))
        lea.schools += 1
        counts = [safe_int(row.get(c) or '') for c in CRDC_COUNT_COLS]
        if any(n is None for n in counts):
            lea.schools_reserved += 1
            continue
        sped_m, sped_f, tot_m, tot_f = counts
        lea.sped_m += sped_m
        lea.sped_f += sped_f
        lea.tot_m += tot_m
        lea.tot_f += tot_f
    return leas


def build_crdc_lea_baselines(profile: BaselineProfile, leas: dict[str, CrdcLea]) -> dict[str, SpedLeaBaseline]:
    """Per-LEA baseline rows from the CRDC aggregate. An LEA every one of whose schools was excluded
    stores NULL CRDC totals (ratio NULL → the estimator's state-average fallback)."""
    out: dict[str, SpedLeaBaseline] = {}
    for lea_id, a in leas.items():
        valid = a.schools - a.schools_reserved
        notes = None
        if a.schools_reserved:
            notes = (f"CRDC {profile.crdc.data_year}: {a.schools_reserved} of {a.schools} schools carry reserve "
                     f"codes and were excluded pairwise (#960)"
                     + ("; no valid school — CRDC totals NULL" if not valid else ""))
        sped = a.sped_m + a.sped_f
        tot = a.tot_m + a.tot_f
        out[lea_id] = SpedLeaBaseline(
            lea_id=lea_id, lea_name=a.lea_name, state=a.state,
            baseline_year=profile.baseline_year,
            crdc_year=profile.crdc.data_year, ccd_year=profile.ccd.data_year,
            crdc_sped_enrollment_m=a.sped_m if valid else None,
            crdc_sped_enrollment_f=a.sped_f if valid else None,
            crdc_sped_enrollment_total=(sped or None) if valid else None,
            crdc_total_enrollment_m=a.tot_m if valid else None,
            crdc_total_enrollment_f=a.tot_f if valid else None,
            crdc_total_enrollment=(tot or None) if valid else None,
            crdc_schools_reserved=a.schools_reserved,
            crdc_source_file=profile.crdc.path.name,
            data_quality_notes=notes,
        )
    return out


def import_crdc_enrollment(profile: BaselineProfile, sample_limit: int | None = None) -> dict[str, SpedLeaBaseline]:
    """CRDC Enrollment (school rows) → per-LEA baseline rows for one vintage."""
    print(f"\n=== Importing CRDC {profile.crdc.data_year} Enrollment (LEA SPED Students) ===")
    with open(profile.crdc.path, 'r', encoding='utf-8-sig', newline='') as f:
        rows = csv.DictReader(f)
        if sample_limit:
            rows = itertools.islice(rows, sample_limit)
        leas = aggregate_crdc_rows(rows)
    lea_data = build_crdc_lea_baselines(profile, leas)
    flagged = sum(1 for a in leas.values() if a.schools_reserved)
    emptied = sum(1 for a in leas.values() if a.schools_reserved == a.schools)
    print(f"  {len(lea_data):,} LEAs from {sum(a.schools for a in leas.values()):,} school records; "
          f"{flagged:,} with reserve-coded schools excluded pairwise, {emptied:,} with none valid")
    return lea_data


def read_ccd_lea_totals(path: Path) -> dict[str, tuple[int | None, str, str]]:
    """CCD LEA membership: {leaid: (student_count, state, lea_name)} from the 'Derived - Education Unit
    Total minus Adult Education Count' rows — K-12, the population CRDC enrolls — through the one shared
    reader that carries the #308 strip and #427 dedupe (#996/#1001)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    totals = ccd_education_unit_totals(df, indicator=EDUCATION_UNIT_TOTAL_MINUS_ADULT,
                                       columns=('LEAID', 'STUDENT_COUNT', 'ST', 'LEA_NAME'))
    return {r.LEAID.strip(): (safe_int(r.STUDENT_COUNT), r.ST.strip(), r.LEA_NAME.strip())
            for r in totals.itertuples(index=False) if len(r.LEAID.strip()) == 7}


def import_ccd_enrollment(profile: BaselineProfile, lea_data: dict[str, SpedLeaBaseline],
                          sample_limit: int | None = None) -> dict[str, SpedLeaBaseline]:
    """CCD LEA membership of the CRDC's own year → each LEA's denominator (#1001: never another year)."""
    print(f"\n=== Importing CCD {profile.ccd.data_year} LEA Membership (denominator) ===")
    matched = new_leas = 0
    for lea_id, (enrollment, state, lea_name) in read_ccd_lea_totals(profile.ccd.path).items():
        if lea_id in lea_data:
            lea_data[lea_id].ccd_total_enrollment = enrollment
            lea_data[lea_id].ccd_source_file = profile.ccd.path.name
            lea_data[lea_id].calculate_ratio()
            matched += 1
        else:
            lea_data[lea_id] = SpedLeaBaseline(
                lea_id=lea_id, lea_name=lea_name, state=state,
                baseline_year=profile.baseline_year,
                crdc_year=profile.crdc.data_year, ccd_year=profile.ccd.data_year,
                ccd_total_enrollment=enrollment, ccd_source_file=profile.ccd.path.name,
            )
            new_leas += 1
        if sample_limit and (matched + new_leas) >= sample_limit:
            break
    if profile.lea_denominator == 'crdc':
        # #1003: every LEA divides by CRDC's own total (same schools as the numerator), including the
        # CRDC LEAs CCD does not list; CCD-only rows carry no CRDC total and stay ratio-less.
        for r in lea_data.values():
            r.calculate_ratio(prefer_crdc=True)
    print(f"  Matched {matched:,} LEAs with CRDC data; added {new_leas:,} CCD-only LEAs "
          f"(denominator: {profile.lea_denominator})")
    return lea_data


# CRDC M+F vs CCD K-12 membership, full-coverage LEAs only (partial LEAs are short by construction).
# Measured 2026-10-31 (#1001): aggregate 0.9923 (2017-18) / 0.9786 (2023-24 — the extra ~1.4 points is
# consistent with the EO 14168 nonbinary suppression); LEAs off by > 20%: 4.3% / 4.9%. The bounds sit
# just outside the worst measured vintage, so a file that drifts further fails loud.
CRDC_CCD_AGGREGATE_TOLERANCE = 0.035
CRDC_CCD_LEA_BAND = 0.20
CRDC_CCD_MAX_LEA_SHARE_OUTSIDE_BAND = 0.06


def reconcile_crdc_with_ccd(profile: BaselineProfile, lea_data: dict[str, SpedLeaBaseline]):
    """Guard the CRDC totals against the CCD membership of the same year (#1001): the aggregate within
    the measured tolerance, and the share of LEAs off by more than CRDC_CCD_LEA_BAND capped."""
    pairs = [(r.crdc_total_enrollment, r.ccd_total_enrollment) for r in lea_data.values()
             if r.crdc_schools_reserved == 0 and r.crdc_total_enrollment and r.ccd_total_enrollment]
    outside = sum(1 for c, d in pairs if abs(c / d - 1) > CRDC_CCD_LEA_BAND)
    receipt = reconcile_total(
        sum(c for c, _ in pairs), sum(d for _, d in pairs),
        label=f"CRDC {profile.crdc.data_year} M+F vs CCD {profile.ccd.data_year} K-12 membership (full-coverage LEAs)",
        tolerance=CRDC_CCD_AGGREGATE_TOLERANCE, n_compared=len(pairs), n_disagree=outside,
        max_disagree=int(CRDC_CCD_MAX_LEA_SHARE_OUTSIDE_BAND * len(pairs)),
    )
    print(f"  CRDC vs CCD: ratio {receipt.ratio:.4f} over {receipt.n_compared:,} LEAs; "
          f"{receipt.n_disagree:,} off by > {CRDC_CCD_LEA_BAND:.0%}")
    return receipt


def save_to_database(session, profile: BaselineProfile, state_data: dict, lea_data: dict) -> None:
    """Replace ONE vintage's baseline rows, atomically. Rows of every other vintage are never touched
    (#999): the 2017-18 baseline stays side by side with a refresh until T5 retires it."""
    print(f"\n=== Saving baseline {profile.baseline_year} to Database ===")
    v = profile.baseline_year
    gone_states = session.query(SpedStateBaseline).filter(SpedStateBaseline.baseline_year == v).delete()
    gone_leas = session.query(SpedLeaBaseline).filter(SpedLeaBaseline.baseline_year == v).delete()
    session.add_all(state_data.values())
    session.add_all(lea_data.values())
    print(f"  Replaced {gone_states} → {len(state_data)} state rows, {gone_leas:,} → {len(lea_data):,} LEA rows")

    DataLineage.log(
        session,
        entity_type="sped_state_baseline",
        entity_id=v,
        operation="import",
        source_file="import_sped_baseline.py",
        details={
            "baseline_year": v,
            "states_imported": len(state_data),
            "school_age_band": profile.school_age_band,
            "sources": {"personnel": [profile.personnel.source.relpath, profile.personnel.source.sha256],
                        "child_count": [profile.child_count.source.relpath, profile.child_count.source.sha256]},
        },
        created_by="import_sped_baseline"
    )
    DataLineage.log(
        session,
        entity_type="sped_lea_baseline",
        entity_id=v,
        operation="import",
        source_file="import_sped_baseline.py",
        details={
            "baseline_year": v,
            "leas_imported": len(lea_data),
            "leas_with_reserved_schools": sum(1 for r in lea_data.values() if r.crdc_schools_reserved),
            "sources": {"crdc": [profile.crdc.relpath, profile.crdc.sha256],
                        "ccd": [profile.ccd.relpath, profile.ccd.sha256]},
        },
        created_by="import_sped_baseline"
    )
    session.commit()
    print("  Committed to database")


def print_summary(state_data: dict, lea_data: dict):
    """Print summary statistics."""
    print("\n=== Summary ===")
    states_with_teachers = sum(1 for s in state_data.values() if s.sped_teachers_total)
    states_with_students = sum(1 for s in state_data.values() if s.sped_students_school_age)
    states_with_ratio = sum(1 for s in state_data.values() if s.ratio_sped_teachers_per_student)
    print(f"\nState-Level (SPED Teachers / Self-Contained SPED Students):")
    print(f"  States with teacher data: {states_with_teachers}")
    print(f"  States with student data: {states_with_students}")
    print(f"  States with calculated ratio: {states_with_ratio}")

    leas_with_sped = sum(1 for l in lea_data.values() if l.crdc_sped_enrollment_total)
    leas_with_total = sum(1 for l in lea_data.values() if l.ccd_total_enrollment)
    proportions = [float(l.ratio_sped_proportion) for l in lea_data.values() if l.ratio_sped_proportion]
    print(f"\nLEA-Level (SPED Students / Total Students):")
    print(f"  LEAs with SPED enrollment: {leas_with_sped:,}")
    print(f"  LEAs with total enrollment: {leas_with_total:,}")
    print(f"  LEAs with calculated ratio: {len(proportions):,}")
    if proportions:
        print(f"  SPED proportion: mean {sum(proportions) / len(proportions):.2%}, "
              f"min {min(proportions):.2%}, max {max(proportions):.2%}")


def main():
    parser = argparse.ArgumentParser(description="Import one SPED baseline vintage (IDEA 618 + CRDC + CCD)")
    parser.add_argument("--baseline-year", default=SPED_BASELINE_YEAR, choices=sorted(PROFILES),
                        help=f"Baseline vintage to import (default: SPED_BASELINE_YEAR = {SPED_BASELINE_YEAR})")
    parser.add_argument("--sample", type=int, help="Limit CRDC school rows / CCD LEAs, for testing")
    args = parser.parse_args()
    profile = get_profile(args.baseline_year)

    print("=" * 60)
    print(f"SPED Baseline Data Import ({profile.baseline_year})")
    print("=" * 60)
    if profile.school_age_band is None:
        raise DataGuardError(f"baseline {profile.baseline_year}: school_age_band is undecided (a T5 call, #1003) "
                             f"— it can be parsed and measured, not written")
    for src in (profile.personnel.source, profile.child_count.source, profile.crdc, profile.ccd):
        verify_source(src)
        print(f"  verified {src.relpath} ({src.data_year})")

    state_data = import_idea_state_baseline(profile)
    lea_data = import_crdc_enrollment(profile, sample_limit=args.sample)
    lea_data = import_ccd_enrollment(profile, lea_data, sample_limit=args.sample)
    if not args.sample:
        reconcile_crdc_with_ccd(profile, lea_data)
    with session_scope() as session:
        save_to_database(session, profile, state_data, lea_data)
    print_summary(state_data, lea_data)

    print("\n" + "=" * 60)
    print("Import complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
