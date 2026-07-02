"""Per-district, per-band school counts + statistical sampling envelope from NCES ccd_sch.

Bands: elementary / middle / high. A school can serve MULTIPLE bands (a K-8 covers
elementary AND middle), so band membership is GRADE-SPAN-aware (GSLO-GSHI via bands_for()),
not just the coarse LEVEL field -- but LEVEL is now the PRIMARY signal when it cleanly maps
to one band (Elementary/Middle/High), with grade-range as a per-band fallback (see
school_index() docstring; found 2026-06-22 via real CP-A review -- naive grade-range-only
classification duplicated real elementary/high schools into middle's candidate pool whenever
they merely clipped a boundary grade, e.g. a K-6 elementary diluting a district's real middle
school 5-to-1).
For each (district, band) we report the school count N and the finite-population sample size n
for 95% confidence / 5% margin (worst-case p=0.5). Small N censuses naturally.

Usage: school_sampling.py [--year 2024_25] [--ids id,id,...] [--summary]
"""
import csv, sys, math, json, argparse
from pathlib import Path
from collections import defaultdict

from infrastructure.acquisition.common import paths   # DATA_ROOT-anchored NCES reads (CWD-independent)

# NCES CCD raw data lives under DATA_ROOT (= <repo>/data by default), NOT the process CWD. Resolving it
# absolutely means the server/CLI find it regardless of where they're launched from — a CWD-relative
# version of these paths 500'd build_batch whenever the server ran from a non-repo-root directory.
_NCES_DIR = paths.DATA_ROOT / "raw" / "federal" / "nces-ccd"

GRADE_ORD = {g:i for i,g in enumerate(
    ["PK","KG","01","02","03","04","05","06","07","08","09","10","11","12","13"])}
# "13" is a real, sanctioned NCES grade code (some states use it for a continuation/
# extra-year high school program) -- without it, bands_for() silently returned an empty
# set for any school coded e.g. GSLO=09/GSHI=13, dropping real high schools from the
# high band entirely (found 2026-06-22: Jackson County MS's three comprehensive high
# schools all use 09-13 and were invisible to band selection; 222 open schools
# nationally use GSHI=13). Grade 13 is treated as part of the high band, not its own.
# normalize NCES grade tokens
def norm(g):
    g=(g or "").strip().upper()
    return {"PREKINDERGARTEN":"PK","K":"KG","KINDERGARTEN":"KG"}.get(g, g)

# band coverage by grade number: elementary K-5, middle 6-8, high 9-12/13 (PK counts as
# elementary; grade 13 counts as high, a continuation of high school, not its own band)
BANDS = {"elementary": range(GRADE_ORD["PK"], GRADE_ORD["05"]+1),
         "middle":     range(GRADE_ORD["06"], GRADE_ORD["08"]+1),
         "high":       range(GRADE_ORD["09"], GRADE_ORD["13"]+1)}

def bands_for(gslo, gshi):
    """Which bands a school's grade span overlaps. Returns set; {} if ungraded/unknown (M-M, etc.)."""
    lo, hi = GRADE_ORD.get(norm(gslo)), GRADE_ORD.get(norm(gshi))
    if lo is None or hi is None or hi < lo: return set()
    span = set(range(lo, hi+1))
    return {b for b, rng in BANDS.items() if span & set(rng)}

def bands_for_rescue(gslo, gshi):
    """Like bands_for(), but for the conservative any-overlap RESCUE only (districts whose
    grade spans don't form a clean partition): a school must reach grade 7 to count as
    touching middle -- topping out at grade 6 alone is treated as pure elementary, mirroring
    the same distinction recursive_band_groups() already makes for clean partitions via its
    top<=6 leading-prefix collapse. bands_for() itself is left as the literal grade-6-8
    definition for other callers (e.g. LEA-level claimed-band checks) -- this is specifically
    about per-school rescue-candidate selection, not the district's overall claimed span.
    Found 2026-06-22: West Bonner County ID's PRIEST RIVER ELEMENTARY and IDAHO HILL
    ELEMENTARY (both PK-06) were wrongly rescued into middle's candidate pool under plain
    bands_for() just because grade 6 sits in BANDS['middle']'s nominal range, while PRIEST
    LAKE ELEMENTARY (PK-07) and PRIEST RIVER LAMANNA HIGH (07-12) -- which actually reach
    grade 7 -- correctly do belong there."""
    lo, hi = GRADE_ORD.get(norm(gslo)), GRADE_ORD.get(norm(gshi))
    if lo is None or hi is None or hi < lo: return set()
    bands = set()
    if lo <= GRADE_ORD["05"]: bands.add("elementary")
    if lo <= GRADE_ORD["08"] and hi >= GRADE_ORD["07"]: bands.add("middle")
    if hi >= GRADE_ORD["09"]: bands.add("high")
    return bands

# NCES LEVEL maps cleanly to exactly one band for these three values -- trust it over
# grade-range when it applies (fixes dilution: a K-6 "Elementary" school no longer also
# counts toward middle just because grade 6 clips our band boundary). Everything else
# (Other, Secondary, Not reported, Not applicable, Ungraded, Adult Education, blank) is
# genuinely ambiguous/combined and falls back to grade-range overlap.
LEVEL_BAND = {"Elementary": "elementary", "Middle": "middle", "High": "high"}

def primary_bands_for(level, gslo, gshi):
    """A school's PRIMARY band(s): LEVEL-mapped (single band) when clean, else grade-range
    overlap (bands_for(), possibly multiple bands) for combined/ambiguous LEVEL values."""
    b = LEVEL_BAND.get((level or "").strip())
    return {b} if b else bands_for(gslo, gshi)

def _grade_num(idx):
    """GRADE_ORD index -> integer grade number; PK/KG both -> 0 (pre-grade-1)."""
    for g, i in GRADE_ORD.items():
        if i == idx:
            return 0 if g in ("PK", "KG") else int(g)
    return None

def _clean_ascending_partition(spans):
    """spans: set of (lo_idx, hi_idx) GRADE_ORD-index tuples. Returns the sorted list if they
    form a clean, non-overlapping, contiguous ascending partition (no gaps, no overlap);
    else None (caller falls back to the conservative any-overlap rescue)."""
    ordered = sorted(spans, key=lambda s: s[0])
    for i in range(len(ordered) - 1):
        if ordered[i][1] + 1 != ordered[i + 1][0]:
            return None
    return ordered

def recursive_band_groups(spans):
    """Given a district's distinct (lo_idx, hi_idx) spans, if they form a clean ascending
    partition, recursively group them into elementary/middle/high segment-position lists
    (positions index into the spans sorted ascending by lo). Returns None if the spans don't
    form a clean partition.

    Rule (validated against the full 2024-25 NCES corpus, 2026-06-22 -- see
    ACQUISITION_PIPELINE.md Stage 1 / METHODOLOGY.md):
    1. Accumulate consecutive LEADING segments with top grade <=6 into "elementary" --
       handles 1, 2, or 3+ elementary sub-segments (lower/upper elementary, primary/
       intermediate splits). If even segment[0] already exceeds grade 6 at its top, it
       isn't part of this prefix at all (elementary is empty unless segment[0] itself
       starts within elementary's range -- see step 2).
    2. EVERY segment not claimed by the elementary prefix (which, when the prefix is
       empty, means every segment) is independently checked against its OWN span, not its
       position: it joins "middle" if it starts at grade <=8, and joins "high" if it ends
       at grade >=9. A segment can join both (the "middle+high merged" case -- Jasper
       Co./Jefferson-Morgan/Calhan/Martins Mill, no separate middle identity exists) or
       just one (Quitman County: a PK-08 elementary already fully covers middle, so the
       following 09-12 high school does NOT also need to claim middle; Sequoia Union
       Elementary: an 08-08 segment trailing an elem+middle-merged KG-07 segment is still
       middle, not high, regardless of coming last). A segment whose own span doesn't
       start within elementary's range (Bridge Academy CT: a lone 07-12 segment) never
       joins elementary just because it's first.
    This is a per-segment overlap check, not position-based guessing -- it supersedes the
    old exactly-2-school "largest overlap" tie-break entirely, and several earlier,
    narrower versions of this same function that got the boundary cases wrong (see
    docs/ACQUISITION_PIPELINE.md (the flow diagram) for the full trail).
    """
    ordered = _clean_ascending_partition(spans)
    if not ordered:  # None (not a clean partition) or [] (no parseable spans at all)
        return None
    los = [_grade_num(lo) for lo, _ in ordered]
    tops = [_grade_num(hi) for _, hi in ordered]
    n = len(ordered)

    elem_end = -1
    i = 0
    while i < n and tops[i] <= 6:
        elem_end = i
        i += 1

    if elem_end == -1:
        elem = [0] if los[0] <= 5 else []
        start = 0  # segment[0] itself still needs the middle/high check below
    else:
        elem = list(range(elem_end + 1))
        start = elem_end + 1

    middle, high = [], []
    for pos in range(start, n):
        if los[pos] <= 8:
            middle.append(pos)
        if tops[pos] >= 9:
            high.append(pos)

    return {"elementary": elem, "middle": middle, "high": high}

def sample_size(N, z=1.96, e=0.05, p=0.5):
    """95/5 finite-population-corrected sample size; censuses small N."""
    if N <= 0: return 0
    n0 = (z*z*p*(1-p)) / (e*e)          # ~384.16
    n = n0 / (1 + (n0-1)/N)
    return min(N, math.ceil(n))

OPEN = {"1","Open","open"}  # SY_STATUS 1 = open (filter closed/inactive)

def _sch_file(year):
    # year is 'YYYY_YY' (e.g. '2023_24'): the file's short year pair is year[2:4]+year[5:7]
    # -> '2324'. (Was year[7:9] -- '' for this format -- so the fast path never hit and the
    # glob fallback always ran; #40.)
    d = _NCES_DIR / year
    f = d / f"ccd_sch_029_{year[2:4]}{year[5:7]}_w_1a_073025.csv"
    if not f.exists():  # fall back to glob
        f = next(d.glob("ccd_sch_029_*_w_1a_*.csv"), None)
        if f is None:
            raise FileNotFoundError(f"no ccd_sch_029_*_w_1a_*.csv found in {d}")
    return f

def _lea_file(year):
    matches = sorted((_NCES_DIR / year).glob("ccd_lea_029_*.csv"))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one ccd_lea_029_*.csv in {_NCES_DIR / year}, found {matches}")
    return matches[0]

def _virtual_file(year):
    # Same 'YYYY_YY' slice + missing-file handling as _sch_file (#40).
    d = _NCES_DIR / year
    f = d / f"ccd_sch_129_{year[2:4]}{year[5:7]}_w_1a_073025.csv"
    if not f.exists():  # fall back to glob
        f = next(d.glob("ccd_sch_129_*_w_1a_*.csv"), None)
        if f is None:
            raise FileNotFoundError(f"no ccd_sch_129_*_w_1a_*.csv found in {d}")
    return f

# NCES VIRTUAL_TEXT enum: No virtual instruction / Supplemental Virtual / Primarily virtual /
# Exclusively virtual / Missing / Not reported. Only the majority/exclusively-virtual values
# are excluded -- a school with Supplemental Virtual is still a normal in-person school with a
# real bell schedule, just one that also offers a virtual option. Missing/Not reported are left
# alone (no positive evidence to exclude on, same principle as everywhere else in this file).
# Found 2026-06-22: Virginia Connections Academy (510348003096, Scott County VA) -- a
# Pearson-operated full-virtual school, LEVEL=Secondary so it was rescued into both middle and
# high via the ambiguous-LEVEL path -- confirmed VIRTUAL_TEXT="Exclusively virtual".
VIRTUAL_EXCLUDED = {"Exclusively virtual", "Primarily virtual"}

def _virtual_ids(year):
    """NCESSCH set of schools too virtual to represent a normal in-person bell-to-bell day."""
    ids = set()
    with open(_virtual_file(year), encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if row.get("VIRTUAL_TEXT", "") in VIRTUAL_EXCLUDED:
                ids.add(row.get("NCESSCH", ""))
    return ids

REGULAR_SCH_TYPE = "Regular School"  # NCES SCH_TYPE_TEXT enum: Regular / Special Education /
# Career and Technical / Alternative. Only "Regular School" is reliably representative of a
# normal academic day for bell-schedule sampling purposes (decided 2026-06-22, after Olympic
# Peninsula HomeConnection [Alternative School -- a homeschool-umbrella program] and Jackson
# County Vocational Center [Career and Technical School -- a school-level CTC inside an
# otherwise-normal district, invisible to the LEA-level Rule 6 exclusion] both surfaced in a
# real batch). Special Education School is excluded too for now -- a separate, deferred body
# of work, not because it's structurally like the other two.

def _eligible(row, virtual_ids):
    """Shared school-level eligibility predicate: open, regular, non-virtual, not a standalone
    preschool. Used by BOTH school_index() (band assignment) and school_level_counts() (raw-LEVEL
    denominator) so the two can never disagree on which schools count -- school_level_counts()'s
    'total' is therefore exactly school_index()'s distinct-school count."""
    return (row.get("SY_STATUS", "") in OPEN
            and row.get("SCH_TYPE_TEXT", "") == REGULAR_SCH_TYPE
            and row.get("NCESSCH", "") not in virtual_ids
            and row.get("GSHI", "") not in ("PK", "KG"))


def school_level_counts(year):
    """did(7-digit) -> {'total': n, 'by_level': {LEVEL: count}} for schools meeting OUR criteria
    (open, regular, non-virtual, non-preschool -- see _eligible), grouped by the RAW ccd_sch
    LEVEL field (Elementary/Middle/High/Secondary/Other/Not reported/...). This is the transparent
    topology denominator -- the count of schools we'd actually try to schedule -- NOT ccd_lea's
    self-reported figure and NOT the derived 3-band assignment. 'total' == school_index() distinct
    count (same eligibility). A blank/missing LEVEL is bucketed as 'Not reported'."""
    virtual_ids = _virtual_ids(year)
    out = defaultdict(lambda: {"total": 0, "by_level": defaultdict(int)})
    with open(_sch_file(year), encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if not _eligible(row, virtual_ids):
                continue
            did = row.get("LEAID", "").zfill(7)
            lvl = (row.get("LEVEL", "") or "").strip() or "Not reported"
            out[did]["total"] += 1
            out[did]["by_level"][lvl] += 1
    return {did: {"total": v["total"], "by_level": dict(v["by_level"])} for did, v in out.items()}


def school_index(year):
    """district_id -> band -> [{school_id, name, is_charter, level, gslo, gshi}, ...] for open,
    regular, non-preschool-only graded schools. gslo/gshi are included for human inspection
    (e.g. spot-checking why a school landed in a given band) -- not used by any selection
    logic above this function. The full per-school roster, not just counts -- the
    source of truth for queue-time per-band school SELECTION (Stage 1), as opposed to
    load()'s counts (corpus-wide envelope).

    Band assignment, in priority order (decided 2026-06-22, after CP-A review of real batches):
    1. LEVEL-CLEAN pass: a school whose NCES LEVEL is a clean Elementary/Middle/High is
       assigned to exactly that one band, full stop -- "our primary tool is to rely on LEVEL
       before any of this" (a K-6 "Elementary" school is ONLY in elementary, even though
       grade 6 would otherwise also overlap middle; fixes dilution, where a real middle
       school's candidate pool got padded with unrelated elementary/high schools that merely
       clipped the boundary grade).
    2. RECURSIVE GROUPING for whatever LEVEL leaves unresolved (a band with zero LEVEL-clean
       candidates, or a school whose own LEVEL is ambiguous -- Other/Secondary/Not
       reported/Ungraded/blank): recursive_band_groups() groups the district's full set of
       distinct grade spans by structural position (see its docstring) when they form a
       clean ascending partition. This is a strict generalization of the old "exactly 2
       schools, largest overlap wins" tie-break -- same idea, but it now also handles 3, 4,
       5, and 6-segment real district shapes (elementary split into 2-3 sub-tiers, high
       split into lower/upper) without needing a school-count carve-out.
    3. ANY-OVERLAP FALLBACK: if the spans don't form a clean partition (e.g. Breathitt County
       KY, Chama Valley NM -- multiple elementary schools with genuinely different,
       overlapping/redundant spans, not just multiple buildings sharing one span), fall back
       to the original conservative rule: any school whose grade range overlaps a still-empty
       band counts as a candidate for it. Not yet validated for these messier shapes -- kept
       deliberately permissive rather than guessing.

    Schools that are majority/exclusively virtual (NCES ccd_sch_129 VIRTUAL_TEXT, see
    VIRTUAL_EXCLUDED) are dropped before any of the above -- a virtual school has no real
    in-person bell-to-bell day to sample (found 2026-06-22: Virginia Connections Academy,
    Scott County VA).
    """
    idx = defaultdict(lambda: defaultdict(list))
    by_district = defaultdict(list)  # did -> [school, ...] (every eligible school, LEVEL-clean or not)
    virtual_ids = _virtual_ids(year)
    with open(_sch_file(year), encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            # Eligibility (open, regular, non-virtual, not standalone preschool) is the shared
            # _eligible() predicate -- excludes e.g. Lake Preschool (PK-PK) / Clinton County Early
            # Childhood Center (PK-KG) via GSHI in (PK,KG), narrower than excluding any PK-serving
            # school (a K-5 with GSLO=PK, GSHI=05 still counts). Kept in lockstep with
            # school_level_counts() so the band index and the LEVEL denominator agree.
            if not _eligible(row, virtual_ids): continue
            did = row.get("LEAID","").zfill(7)
            school = {
                "school_id": row.get("NCESSCH",""),
                "name": row.get("SCH_NAME",""),
                "is_charter": row.get("CHARTER_TEXT",""),
                "level": row.get("LEVEL",""),
                "gslo": row.get("GSLO",""),
                "gshi": row.get("GSHI",""),
            }
            by_district[did].append(school)

    for did, schools in by_district.items():
        ambiguous = []
        for school in schools:
            b = LEVEL_BAND.get(school["level"].strip())
            if b:
                idx[did][b].append(school)
            else:
                ambiguous.append(school)

        if not ambiguous and all(idx[did][b] for b in BANDS):
            continue  # every band already has a clean LEVEL match; nothing left to resolve

        span_schools = defaultdict(list)
        for school in schools:
            lo, hi = GRADE_ORD.get(norm(school["gslo"])), GRADE_ORD.get(norm(school["gshi"]))
            if lo is None or hi is None or hi < lo: continue
            span_schools[(lo, hi)].append(school)

        groups = recursive_band_groups(set(span_schools.keys()))
        if groups is not None:
            ordered_spans = sorted(span_schools.keys(), key=lambda s: s[0])
            ambiguous_ids = {s["school_id"] for s in ambiguous}
            for band, positions in groups.items():
                band_was_empty = not idx[did][band]
                for pos in positions:
                    for school in span_schools[ordered_spans[pos]]:
                        is_ambiguous = school["school_id"] in ambiguous_ids
                        # A LEVEL-clean school may ONLY be added here if this band was a
                        # genuine gap (no LEVEL-clean coverage at all) -- e.g. Jasper Co.'s
                        # "High"-LEVEL school must ALSO fill middle, since middle has no
                        # LEVEL-clean school of its own (the merged-middle+high case). It must
                        # NOT be added to a band that already has separate LEVEL-clean
                        # coverage -- that's the original dilution bug. An ambiguous school,
                        # by contrast, can join a band regardless of whether it was already
                        # non-empty (Aledo ISD TX: the "Secondary"-LEVEL 9th-grade campus must
                        # join the "High"-LEVEL main campus in high, not be dropped just
                        # because high already had a school -- found 2026-06-22).
                        if not is_ambiguous and not band_was_empty:
                            continue
                        if school not in idx[did][band]:
                            idx[did][band].append(school)
        else:
            # Not a clean partition -- conservative any-overlap fallback (unvalidated shape).
            # bands_for_rescue(), not bands_for() -- see its docstring (West Bonner County ID).
            for school in ambiguous:
                for b in bands_for_rescue(school["gslo"], school["gshi"]):
                    if school not in idx[did][b]:
                        idx[did][b].append(school)
            for band in BANDS:
                if idx[did][band]: continue
                for school in schools:
                    if band in bands_for_rescue(school["gslo"], school["gshi"]):
                        idx[did][band].append(school)
    return idx

def load(year):
    # (district_id) -> band -> count of schools serving that band
    idx = school_index(year)
    counts = defaultdict(lambda: defaultdict(int))
    for did, bands in idx.items():
        for b, schools in bands.items():
            counts[did][b] = len(schools)
    return counts

def lea_info(year):
    """district_id -> {name, state, website, status, lea_type, claimed_bands}, from the LEA
    directory file. claimed_bands = bands_for() applied to the LEA-level (overall) GSLO/GSHI --
    the district's CLAIMED grade range, not a substitute for school-level enumeration (school_index()
    above) -- see Rule 7 / ACQUISITION_PIPELINE.md Stage 1 grade-span-integrity exclusion."""
    out = {}
    with open(_lea_file(year), encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            did = row.get("LEAID","").zfill(7)
            out[did] = {
                "name": row.get("LEA_NAME",""),
                "state": row.get("ST",""),
                "website": row.get("WEBSITE",""),
                "status": row.get("SY_STATUS_TEXT",""),
                "lea_type": row.get("LEA_TYPE_TEXT",""),
                "claimed_bands": bands_for(row.get("GSLO"), row.get("GSHI")),
            }
    return out

def charter_lookup(did, year="2024_25"):
    """{normalized_school_name: 'Yes'|'No'} for one LEA's open schools (NCES CHARTER_TEXT).
    We TAG charters (NCES flag), never exclude (REQ-060); a name not found -> 'unknown'."""
    import re
    def norm(n):
        n = re.sub(r"[^a-z0-9 ]", "", (n or "").lower())
        n = re.sub(r"\b(elementary|middle|high|school|jr|junior|senior|academy|the|of|at)\b", "", n)
        return re.sub(r"\s+", " ", n).strip()
    out = {}
    with open(_sch_file(year), encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if row.get("LEAID","").zfill(7) != str(did).zfill(7): continue
            if row.get("SY_STATUS","") not in OPEN: continue
            out[norm(row.get("SCH_NAME",""))] = "Yes" if row.get("CHARTER_TEXT") == "Yes" else "No"
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="2024_25")
    ap.add_argument("--ids", default="")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    counts = load(a.year)

    if a.ids:
        _gt = paths.DATA_ROOT / "benchmark" / "ground_truth_manifest.json"
        man = {d["district_id"]: d for d in json.load(open(_gt))["districts"]} if _gt.exists() else {}
        for did in a.ids.split(","):
            did = did.zfill(7); c = counts.get(did, {})
            name = man.get(did,{}).get("district_name","?")
            row = " ".join(f"{b[:4]}={c.get(b,0)}(n{sample_size(c.get(b,0))})" for b in ("elementary","middle","high"))
            tot_n = sum(sample_size(c.get(b,0)) for b in BANDS)
            print(f"{did} {name[:28]:28} {row}  | calls/district(census-sample)={tot_n}")
        return

    # corpus-wide envelope
    nd = len(counts)
    band_school_calls = defaultdict(int); districts_with = defaultdict(int)
    census_total = 0; sample_total = 0
    dist_sample_calls = []
    for did, c in counts.items():
        dcalls = 0
        for b in BANDS:
            N = c.get(b, 0)
            if N: districts_with[b]+=1
            census_total += N
            s = sample_size(N); sample_total += s; band_school_calls[b]+=s; dcalls += s
        dist_sample_calls.append(dcalls)
    dist_sample_calls.sort()
    med = dist_sample_calls[len(dist_sample_calls)//2] if dist_sample_calls else 0
    p95 = dist_sample_calls[int(len(dist_sample_calls)*0.95)] if dist_sample_calls else 0
    print(f"districts with >=1 graded school: {nd}")
    print(f"total open graded-school band-memberships (census): {census_total:,}")
    print(f"total band-extractions if 95/5 sampled:             {sample_total:,}  ({100*sample_total/census_total:.0f}% of census)")
    print(f"per-band sampled calls: " + ", ".join(f"{b}={band_school_calls[b]:,} (in {districts_with[b]:,} dists)" for b in BANDS))
    print(f"per-district sampled calls (3 bands): median={med}  p95={p95}  max={max(dist_sample_calls) if dist_sample_calls else 0}")

if __name__ == "__main__":
    main()
