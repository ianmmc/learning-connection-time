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
import csv, sys, math, json, argparse, functools, re
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
    grade spans don't form a clean partition). Two boundary disciplines:
      - A school topping at grade 6 that STARTS low is pure elementary (found 2026-06-22:
        West Bonner County ID's PRIEST RIVER/IDAHO HILL ELEMENTARY, both PK-06, were wrongly
        rescued into middle just because grade 6 sits in BANDS['middle']'s nominal range,
        while PRIEST LAKE ELEMENTARY PK-07 and LAMANNA HIGH 07-12 -- which reach grade 7 --
        correctly belong there).
      - A span STARTING at grade 5+ is a MIDDLE-FAMILY school, never elementary (#498 ruling,
        Ian 2026-07-15: 5-5, 5-6, and 6-6 are all middle -- Hammarskjold Upper Elementary NJ,
        LEVEL=Middle 05-06, is the pinned specimen -- and a 5-8 is middle only, not
        elementary+middle). Elementary attribution therefore requires starting at grade <=4.
    bands_for() itself is left as the literal grade-6-8 definition for other callers (e.g.
    LEA-level claimed-band checks) -- this is specifically about per-school rescue-candidate
    selection, not the district's overall claimed span."""
    lo, hi = GRADE_ORD.get(norm(gslo)), GRADE_ORD.get(norm(gshi))
    if lo is None or hi is None or hi < lo: return set()
    bands = set()
    if lo <= _IM_START_ORD: bands.add("elementary")
    if ((lo <= GRADE_ORD["08"] and hi >= GRADE_ORD["07"])
            or (lo > _IM_START_ORD and hi <= _IM_TOP_ORD)):
        bands.add("middle")
    if hi >= GRADE_ORD["09"]: bands.add("high")
    return bands

# NCES LEVEL maps cleanly to exactly one band for these three values -- trust it over
# grade-range when it applies (fixes dilution: a K-6 "Elementary" school no longer also
# counts toward middle just because grade 6 clips our band boundary). Everything else
# (Other, Secondary, Not reported, Not applicable, Ungraded, Adult Education, blank) is
# genuinely ambiguous/combined and falls back to grade-range overlap.
LEVEL_BAND = {"Elementary": "elementary", "Middle": "middle", "High": "high"}

# #258: name-token -> implied band(s). ORDER MATTERS: "junior high" must claim its words before the
# bare "high" pattern sees them. Tokens are whole-word phrases (padded match) so "Highland"/"Middleton"
# never trigger. K-8/K-12 imply multi-band service — a K-12-named school legitimately sits in ANY band,
# so it can never mismatch (the flag is for a SINGLE-level name in the wrong place). "Intermediate"
# implies elementary OR middle (#498, corpus-measured: real Intermediate schools sit on BOTH sides of
# the boundary — 04-06 upper-elementary AND 05-06 middle — so it gets the K-8 multi-band treatment).
_NAME_BAND_TOKENS = (
    (("junior high", "jr high"), {"middle"}),
    (("intermediate",), {"elementary", "middle"}),
    (("middle",), {"middle"}),
    (("high",), {"high"}),
    (("elementary", "primary", "grade school"), {"elementary"}),
    (("k 8", "k8"), {"elementary", "middle"}),
    (("k 12", "k12"), {"elementary", "middle", "high"}),
)


def name_level_mismatch(school_name, nces_level, bands, gslo=None, gshi=None):
    """#258 detect-and-flag (never auto-reject): does this school's NAME carry a level token that
    contradicts its NCES LEVEL tag or an assigned band? The Coffee County signature: 'Zion Chapel
    High School' tagged Other PK-12, contaminating the elementary band — the name contradicted the
    placement, and nothing looked. A name token is a hint, not ground truth (legitimate exceptions
    exist), so the return is a flag for human review at a gate, never a drop. Handles the recurring
    temporal-reconfiguration class where the NCES tag lags reality (#257 is the correction half).

    #498 (PR #500 review round): the predicate is SPAN-AWARE when the caller can supply gslo/gshi
    (the roster surface can; the extracted-fact surface can't). Two false-positive classes died
    here: (a) the LEVEL side checks the EFFECTIVE band (carve-out applied), so a 'Middle'-tagged
    04-06 school placed in elementary no longer conflicts with its own correct placement; (b) a
    'middle'-named school on an intermediate span implies {elementary, middle} — its name is
    NCES's own over-assignment written on the building; flagging it against the ruled placement
    would re-litigate #498 on every review. Without a span, behavior is unchanged.

    Pure predicate: (...) -> None | {school, implied_bands, nces_level, conflicts}."""
    padded = " " + " ".join((school_name or "").lower().replace("-", " ").replace(".", " ").split()) + " "
    implied = None
    for tokens, bset in _NAME_BAND_TOKENS:
        if any(f" {t} " in padded for t in tokens):
            implied = bset
            break
    if not implied:
        return None
    if implied == {"middle"} and is_intermediate_span(gslo, gshi):
        implied = {"elementary", "middle"}
    conflicts = []
    level_band = effective_level_band(nces_level, gslo, gshi)
    if level_band and level_band not in implied:
        conflicts.append({"kind": "nces_level", "level": nces_level, "level_band": level_band})
    for b in sorted(set(bands or [])):
        if b in BANDS and b not in implied:
            conflicts.append({"kind": "band", "band": b})
    if not conflicts:
        return None
    return {"school": school_name, "implied_bands": sorted(implied),
            "nces_level": nces_level, "conflicts": conflicts}


# #498 boundary — ONE home for the intermediate/upper-elementary span definition (PR #500 review
# round: the same 4/6 pair was independently hardcoded in three functions). Expressed as plain
# grade numbers (PK/KG count as 0); span functions compare GRADE_ORD ordinals via the zero-padded
# keys below, recursive_band_groups compares _grade_num() integers directly.
INTERMEDIATE_MAX_START = 4   # a span starting at grade 5+ is middle-family, never elementary
INTERMEDIATE_MAX_TOP = 6     # a span topping above grade 6 is not an elementary-side span
_IM_START_ORD = GRADE_ORD[f"{INTERMEDIATE_MAX_START:02d}"]
_IM_TOP_ORD = GRADE_ORD[f"{INTERMEDIATE_MAX_TOP:02d}"]


def is_intermediate_span(gslo, gshi):
    """#498: the intermediate / upper-elementary span — starts at grade ≤4 AND tops at grade ≤6
    (Liberati: 04-06). Deliberately NOT 05-06 (5-6 is middle when it feeds a 7-8 — Ian's standard,
    and NCES's Middle tag agrees there); the 05-05/06-06 orphans were RULED middle (2026-07-15)."""
    lo, hi = GRADE_ORD.get(norm(gslo)), GRADE_ORD.get(norm(gshi))
    if lo is None or hi is None or hi < lo:
        return False
    return lo <= _IM_START_ORD and hi <= _IM_TOP_ORD


def effective_level_band(level, gslo, gshi):
    """#498 (DECIDED Ian 2026-07-15): the clean-LEVEL band with the ONE corpus-profiled override —
    LEVEL='Middle' on an intermediate span (starts ≤4, tops ≤6) is an upper-ELEMENTARY school
    (~330 schools nationally, 0.4%; NCES over-assigns Middle to intermediates — measured against
    the full 2024-25 corpus, where this is the ONLY hard LEVEL-vs-span disagreement class that
    exists; the reverse edge is zero). LEVEL stays primary everywhere else (the 2026-06-22
    anti-dilution decision) — this is a scalpel, not an inversion. Every caller that places or
    counts schools should use THIS, not LEVEL_BAND directly; overrides are surfaced
    detect-and-flag at gate@8 (the #257/#258 posture). Returns the band or None (ambiguous)."""
    b = LEVEL_BAND.get((level or "").strip())
    if b == "middle" and is_intermediate_span(gslo, gshi):
        return "elementary"
    return b


def primary_bands_for(level, gslo, gshi):
    """A school's PRIMARY band(s): LEVEL-mapped (single band) when clean — with the #498
    intermediate carve-out applied — else grade-range overlap (bands_for(), possibly multiple
    bands) for combined/ambiguous LEVEL values."""
    b = effective_level_band(level, gslo, gshi)
    return {b} if b else bands_for(gslo, gshi)


def real_bands_for_district(by_level, schools_by_band, band_rosters=None) -> set:
    """The bands a district can ACTUALLY satisfy — each SERVED by ≥1 real NCES school. This is
    FILLABILITY, not primary-label classification, so it must agree with `school_index`'s own
    placement — including the gap-fill: Jasper Co.'s 'High'-LEVEL 07-12 school also fills middle
    (grades 7-8 attend it), and Roy's 07-12 school produced ACCEPTED middle-band facts. A
    `primary_bands_for`-based version shipped first and wrongly called all 24 such gap-filled
    middles "phantom" (PR #191 review). Three signals, unioned:
      1. clean Elementary/Middle/High LEVEL counts (`by_level` — ALL criteria-meeting schools,
         not just the selected subset);
      2. any band Stage 1 itself placed ≥1 school into (`schools_by_band` — the sbb dict,
         carrying the school_index gap-fill verbatim);
      3. each placed school's clean LEVEL band + its `bands_for_rescue` grade span (the same
         conservative overlap school_index rescues with — a K-6 does NOT reach middle).
    The single definition of "real bands" for the Stage-7 request loop's coverage gates
    (`stage7_extract/requests.py` holds the gate policy).

    #498 (PR #500 review round — the signal-1 phantom): signal 1's AGGREGATE LEVEL counts carry no
    per-school spans, so they cannot apply the intermediate carve-out — 56 corpus districts (e.g.
    0604650, whose only 'Middle'-tagged school is a 04-06 intermediate) would claim a middle band
    NO real school serves, and Stage 7's phantom-suppression gate (`target_bands = claimed ∩ real`)
    would keep SPENDING against it. So when the caller supplies the LIVE serving roster
    (`band_rosters_for_district`, span-aware by construction), the roster REPLACES signal 1 — same
    all-criteria-schools coverage, carve-out applied. Signal 1's raw form survives only as the
    fallback when the CCD files aren't on disk. Signals 2/3 are unchanged; a STALE Stage-1
    placement (a pre-#498 batch) can still claim a band via signal 2 — that class is surfaced as a
    stale-roster note at gate@8, not silently dropped (fill-gaps-not-overwrite applies to receipts
    too)."""
    if band_rosters:
        bands = {b for b in BANDS if (band_rosters.get(b) or {}).get("total", 0) > 0}
    else:
        bands = {LEVEL_BAND[lvl] for lvl in (by_level or {}) if lvl in LEVEL_BAND}
    for band, meta in (schools_by_band or {}).items():
        schools = (meta or {}).get("schools") or []
        if band in BANDS and schools:
            bands.add(band)
        for sc in schools:
            b = effective_level_band(sc.get("level"), sc.get("gslo"), sc.get("gshi"))
            if b:
                bands.add(b)
            bands |= bands_for_rescue(sc.get("gslo"), sc.get("gshi"))
    return bands

# #253 A1: joiners + collective generics for combined-scope detection. A "combined-scope" extracted
# name describes a GROUP of campuses, not one school — either a grade-band collective ("K-8 Schools",
# "All Elementary Schools") or a conjunction listing several campuses ("Milagro and Ortiz Schools").
_SCOPE_JOINERS = re.compile(r"\s+(?:and|&|\+)\s+|\s*/\s*|\s*,\s*")
_SCOPE_GENERICS = ("schools", "campuses", "sites", "buildings")
_SCOPE_QUANTIFIERS = ("all", "both")


def combined_scope_name(school_name, roster_names=None):
    """#253 detect-and-flag (never auto-reject): does this EXTRACTED school name denote MULTIPLE
    campuses or a grade-band group rather than a single school? The Santa Fe signature: 'k8 schools'
    (one page stating times for the district's K-8 schools collectively) and 'milagro and ortiz
    schools' (one table listing both middle schools) each landed as its own row in the middle band —
    pseudo-schools inflating n_schools and injecting extra modal votes off one combined table.

    Two kinds, mirroring #258's pure-predicate shape:
      - `group_descriptor`: a band token (K-8, elementary, middle, …) or an all/both quantifier
        beside a collective plural ("schools"/"campuses"/…) — a description of a CLASS of campuses,
        never a campus. `implied_bands` rides along from the band token when one is present.
      - `conjunction`: joiner-split segments (and/&/,//) that RESOLVE to ≥2 distinct roster schools
        via norm_school_strict (the trustworthy hint, same posture as #237's roster_matched). An
        UNRESOLVED conjunction only flags when a collective plural is also present — 'Lewis and
        Clark Elementary' is one school and must not flag on its 'and' alone.

    Pure predicate: (school_name, roster_names) -> None | {school, kind, campuses, implied_bands}.
    A flag is a hint for gate@8 review — the fact keeps its vote until the reviewer disposes
    (exclude via #257, or the roster-template slot-projection once built)."""
    from infrastructure.acquisition.common.school_match import norm_school_strict
    raw = (school_name or "").strip()
    if not raw:
        return None
    padded = " " + " ".join(raw.lower().replace("-", " ").replace(".", " ").split()) + " "
    has_generic = any(f" {g} " in padded for g in _SCOPE_GENERICS)

    band_tokens = None
    for tokens, bset in _NAME_BAND_TOKENS:
        if any(f" {t} " in padded for t in tokens):
            band_tokens = bset
            break
    quantified = any(padded.startswith(f" {q} ") for q in _SCOPE_QUANTIFIERS)
    # A band token + collective plural, or a bare quantified collective ("all schools"), with NO
    # other identifying tokens left once the class words are gone — 'Kearny Elementary Schools'
    # (a typo'd real campus) keeps its proper-name token and does not flag.
    if has_generic and (band_tokens or quantified):
        residue = norm_school_strict(raw)
        # strip the band/quantifier class words themselves from the residue check
        residue_words = [w for w in residue.split()
                         if w not in ("k", "8", "k8", "12", "k12", "primary", "grade", "intermediate")
                         and w not in _SCOPE_QUANTIFIERS]
        if not residue_words:
            return {"school": school_name, "kind": "group_descriptor", "campuses": [],
                    "implied_bands": sorted(band_tokens or [])}

    segments = [s for s in (_SCOPE_JOINERS.split(raw)) if s and s.strip()]
    if len(segments) >= 2:
        strict_roster = {}
        for rn in (roster_names or []):
            k = norm_school_strict(rn)
            if k:
                strict_roster.setdefault(k, rn)
        campuses, seen = [], set()
        for seg in segments:
            k = norm_school_strict(seg)
            if k and k in strict_roster and k not in seen:
                seen.add(k)
                campuses.append(strict_roster[k])
        if len(campuses) >= 2:
            return {"school": school_name, "kind": "conjunction", "campuses": campuses,
                    "implied_bands": []}
        if has_generic:
            return {"school": school_name, "kind": "conjunction", "campuses": [],
                    "implied_bands": []}
    return None


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
    # #498 ruling (Ian 2026-07-15): a segment STARTING at grade 5+ is middle-family (5-6 beside a
    # 7-8 is a middle school, not an upper-elementary tier), so the elementary prefix additionally
    # requires the segment to START at grade <=4 — a K-3 / 4-6 / 7-8 / 9-12 four-band district
    # folds both leading tiers into elementary, but K-4 / 5-6 / 7-8 / 9-12 folds only K-4.
    # Boundary numbers are the shared #498 constants (one home), as plain grade ints here.
    while i < n and tops[i] <= INTERMEDIATE_MAX_TOP and los[i] <= INTERMEDIATE_MAX_START:
        elem_end = i
        i += 1

    if elem_end == -1:
        elem = [0] if los[0] <= INTERMEDIATE_MAX_START else []
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
        # FileNotFoundError like the _sch_file/_virtual_file siblings — a missing/ambiguous data
        # file is an ordinary exception callers can catch, never a process exit (the old
        # SystemExit slipped past every `except Exception` best-effort guard; epic-#499 review).
        raise FileNotFoundError(
            f"expected exactly one ccd_lea_029_*.csv in {_NCES_DIR / year}, found {matches}")
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

# #253/#229: the ONE human-readable statement of what the school-level eligibility criteria count —
# shown wherever a denominator or exclusion figure appears (gate@8 sampling stats, the Settings
# Exclusions view), so an auditor never has to guess what's absent from a count.
SCHOOL_CRITERIA_TEXT = ("Open, regular NCES schools only (virtual, alternative, special-ed and "
                        "adult-ed campuses excluded; standalone preschools excluded). A school "
                        "counts toward every band its NCES LEVEL or its own grade span serves — "
                        "a K-8 counts toward elementary AND middle.")

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
    count (same eligibility). A blank/missing LEVEL is bucketed as 'Not reported'.

    #498 note (PR #500 review round): DELIBERATELY raw -- the #498 intermediate carve-out is NOT
    applied here, by design: this is the receipt of what NCES says, and it feeds the gate@8
    'n_total_level_only' continuity figure. Expect it to DISAGREE with band_rosters_for_district's
    carve-out-aware totals for Liberati-class districts (a 'Middle'-tagged 04-06 counts under
    Middle here, under elementary there); the gate@8 override note is the reconciliation."""
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


def latest_nces_year():
    """The newest NCES CCD vintage on disk ('YYYY_YY' dir containing a ccd_sch file), or None.
    Self-rolling like utilities/school_year: a new CCD drop is picked up without a code change."""
    if not _NCES_DIR.is_dir():
        return None
    years = sorted((d.name for d in _NCES_DIR.iterdir()
                    if re.fullmatch(r"\d{4}_\d{2}", d.name)
                    and next(d.glob("ccd_sch_029_*_w_1a_*.csv"), None)), reverse=True)
    return years[0] if years else None


@functools.lru_cache(maxsize=2)
def _district_schools(year):
    """did(7-digit) -> [school dict, ...] for EVERY _eligible school — the shared CSV read behind
    school_index() and band_rosters_for_district(). Cached (one ~full-corpus scan per year per
    process; the gate@8 console calls this per district view). Callers must NOT mutate the result.

    #498 (PR #500 review round): each record is STAMPED with `effective_band` (the carve-out
    answer) and `level_overridden` at load time — the override travels with the school, so a
    future consumer of this loader cannot silently reach for LEVEL_BAND.get(...) and reintroduce
    the pre-#498 behavior; the drift the review found in real_bands_for_district's signal 1 was
    exactly that class. Raw `level`/`gslo`/`gshi` stay verbatim (the receipt of what NCES says)."""
    by_district = defaultdict(list)
    virtual_ids = _virtual_ids(year)
    with open(_sch_file(year), encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if not _eligible(row, virtual_ids):
                continue
            level, gslo, gshi = row.get("LEVEL", ""), row.get("GSLO", ""), row.get("GSHI", "")
            eff = effective_level_band(level, gslo, gshi)
            by_district[row.get("LEAID", "").zfill(7)].append({
                "school_id": row.get("NCESSCH", ""),
                "name": row.get("SCH_NAME", ""),
                "is_charter": row.get("CHARTER_TEXT", ""),
                "level": level,
                "gslo": gslo,
                "gshi": gshi,
                "effective_band": eff,
                "level_overridden": eff != LEVEL_BAND.get(level.strip()),
            })
    return dict(by_district)


def band_rosters_for_district(district_id, year=None):
    """#253: the band-SERVING denominator roster, LIVE from ccd_sch (Ian, 2026-07-14: derive live,
    never freeze — school counts change over the project's long horizon; the gate@8 approval receipt
    snapshots the value at sign-off, which is where reproducibility lives).

    A school SERVES a band when its clean LEVEL maps there OR its own grade span reaches it under
    bands_for_rescue's conservative overlap — a KG-08 'Elementary'-tagged K-8 serves middle (Santa
    Fe: 4 such schools, NCES tags them Elementary); a K-6 'Elementary' does NOT (the same grade-7
    discrimination rescue exists for); a 'High' 07-12 serves middle too (the Jasper Co. gap-fill
    class). This is FILLABILITY vocabulary — real_bands_for_district's signals 1+3 applied
    per-school — deliberately NOT school_index()'s anti-dilution selection placement: selection asks
    'which pool do we sample from', the denominator asks 'how many schools would full band coverage
    require'. (school_index would put Santa Fe's K-8s in elementary only, reading middle as 2-of-2
    covered — the exact 200%-coverage lie #253 exists to fix.)

    Returns {band: {"total": n, "by_source": {"level_clean": n, "grade_span": n,
                    "level_override": n}, "schools": [name, ...],
                    "slot_recs": [{school_id, name, is_charter, gslo, gshi, level, effective_band,
                    source}, ...]}} — slot_recs is the #499 slot-spine identity surface (REQ-144):
    the same placements as `schools`, with the NCESSCH key (what receipts and drift compare on),
    the span (so the console can explain a placement), the charter tag (REQ-060: tag, never
    exclude), and per-placement `source`. Plus "_unattributed": [name, ...]
    for schools serving no band (unparseable span + ambiguous LEVEL) — surfaced, never silently
    dropped — and "_level_overrides": the #498 intermediate carve-outs applied (detect-and-flag:
    every override is visible at gate@8, never silent). Returns None when the CCD files aren't on
    disk (caller falls back to the clean-LEVEL denominator)."""
    year = year or latest_nces_year()
    if not year:
        return None
    try:
        schools = _district_schools(year).get(str(district_id).zfill(7), [])
    except FileNotFoundError:
        return None
    out = {b: {"total": 0, "by_source": {"level_clean": 0, "grade_span": 0, "level_override": 0},
               "schools": [], "slot_recs": []} for b in BANDS}
    unattributed, overrides = [], []
    for sc in schools:
        # lb/is_override come from the loader's per-school stamp (one derivation, one home);
        # is_override is a school-level invariant, computed once, not re-derived per band.
        lb, is_override = sc.get("effective_band"), bool(sc.get("level_overridden"))
        if is_override:   # the #498 carve-out fired — record it for the flag surface
            overrides.append({"school": sc.get("name", ""), "nces_level": sc.get("level"),
                              "gslo": sc.get("gslo"), "gshi": sc.get("gshi"),
                              "band": lb, "instead_of": LEVEL_BAND.get((sc.get("level") or "").strip())})
        serves = ({lb} if lb else set()) | bands_for_rescue(sc.get("gslo"), sc.get("gshi"))
        if not serves:
            unattributed.append(sc.get("name", ""))
            continue
        for b in serves:
            out[b]["total"] += 1
            src = ("level_override" if (b == lb and is_override)
                   else "level_clean" if b == lb else "grade_span")
            out[b]["by_source"][src] += 1
            out[b]["schools"].append(sc.get("name", ""))
            # #499 (REQ-144): the slot-spine identity row — same placement, with the NCESSCH key
            # (drift/receipts compare on it), the span, and the charter tag (REQ-060: tag, never
            # exclude; the slot view badges it — the Structure-C surface #243/#244 can read).
            out[b]["slot_recs"].append({
                "school_id": sc.get("school_id", ""), "name": sc.get("name", ""),
                "is_charter": sc.get("is_charter", ""),
                "gslo": sc.get("gslo"), "gshi": sc.get("gshi"), "level": sc.get("level"),
                "effective_band": lb, "source": src})
    return {**out, "_unattributed": unattributed, "_level_overrides": overrides, "_year": year}


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
    # Eligibility (open, regular, non-virtual, not standalone preschool) is the shared _eligible()
    # predicate inside _district_schools() -- excludes e.g. Lake Preschool (PK-PK) / Clinton County
    # Early Childhood Center (PK-KG) via GSHI in (PK,KG), narrower than excluding any PK-serving
    # school (a K-5 with GSLO=PK, GSHI=05 still counts). Kept in lockstep with
    # school_level_counts() so the band index and the LEVEL denominator agree.
    by_district = _district_schools(year)  # did -> [school, ...] (every eligible school)

    for did, schools in by_district.items():
        ambiguous = []
        for school in schools:
            # #498: the LEVEL-clean pass uses the loader's carve-out stamp — a 'Middle'-tagged
            # 04-06 is a clean ELEMENTARY placement here (Liberati class), not ambiguous.
            b = school.get("effective_band")
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
    We TAG charters (NCES flag), never exclude (REQ-060); a name not found -> 'unknown'.
    Keys are `norm_school` — the ONE shared match axis (school_match.py); this had a private,
    divergent re-implementation until #499 PR-A consolidated it (REQ-144)."""
    from infrastructure.acquisition.common.school_match import norm_school as norm
    out = {}
    with open(_sch_file(year), encoding="utf-8-sig", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if row.get("LEAID","").zfill(7) != str(did).zfill(7): continue
            if row.get("SY_STATUS","") not in OPEN: continue
            key = norm(row.get("SCH_NAME",""))
            # norm_school strips NCES abbreviation tails (El/Sch/SHS...), so two sibling schools
            # CAN collide on one key ('Roosevelt El' / 'Roosevelt Sch') — never let a 'No'
            # overwrite a 'Yes': dropping a charter tag on collision would quietly violate
            # REQ-060 (tag charters, never exclude) for the losing school (epic-#499 review).
            if out.get(key) != "Yes":
                out[key] = "Yes" if row.get("CHARTER_TEXT") == "Yes" else "No"
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
