"""The ONE home for the grade -> band map and the school -> band classifier (#1035, #1022 T1).

Elementary / middle / high, by grade: PK-5, 6-8, 9-13. PK counts as elementary for SERVICE (a PK-5
school serves the elementary band). Grade 13 counts as high: a continuation of high school, not its
own band. Both the acquisition pipeline (Stage 1 placement, Stage 9 grade ownership) and the LCT
layer (per-grade minutes, the school-file band scopes) read this module. That is why it lives in
`utilities/`: the import-linter contracts forbid the LCT layer from importing `acquisition`.
Before #1035 the map was spelled four times, and a test held two of the copies in agreement
(#638).

Two relations live here, and they are different questions:
  - `canon_band(grade)`: which band OWNS a grade. Exactly one; the fixed map.
  - `primary_bands_for(level, gslo, gshi)`: which band(s) a SCHOOL belongs to. NCES LEVEL when it
    is clean, with the #498 carve-out, else the grade-span overlap. The school-file band scopes band
    schools by this rule (#1022 D1/D2), the same rule that bands the bell minutes.
"""
from __future__ import annotations

GRADE_ORD = {g: i for i, g in enumerate(
    ["PK", "KG", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13"])}
# "13" is a real, sanctioned NCES grade code (some states use it for a continuation/extra-year high
# school program). Without it, bands_for() returned an empty set for any school coded GSLO=09/GSHI=13,
# dropping real high schools from the high band (found 2026-06-22: Jackson County MS's three
# comprehensive high schools all use 09-13; 222 open schools nationally use GSHI=13).

# The LCT grade range: KG + grades 1-12. PK is excluded from LCT; grade 13 rides with high for
# minutes but carries no LCT enrollment weight.
K12_GRADE_TOKENS = ["KG"] + [f"{n:02d}" for n in range(1, 13)]


def norm(g):
    """Normalize an NCES grade token ("Kindergarten" -> "KG", "PreKindergarten" -> "PK")."""
    g = (g or "").strip().upper()
    return {"PREKINDERGARTEN": "PK", "K": "KG", "KINDERGARTEN": "KG"}.get(g, g)


BANDS = {"elementary": range(GRADE_ORD["PK"], GRADE_ORD["05"] + 1),
         "middle":     range(GRADE_ORD["06"], GRADE_ORD["08"] + 1),
         "high":       range(GRADE_ORD["09"], GRADE_ORD["13"] + 1)}


def canon_band(grade: str) -> str | None:
    """The band that OWNS a grade token under the fixed map; None for an unknown token."""
    go = GRADE_ORD.get(grade)
    for band, rng in BANDS.items():
        if go is not None and go in rng:
            return band
    return None


def band_grade_tokens(band: str, tokens=K12_GRADE_TOKENS) -> list:
    """The `tokens` (default the LCT K-12 range, in order) that `band` owns."""
    return [g for g in tokens if canon_band(g) == band]


def grade_int(grade: str) -> int | None:
    """A grade token as an integer: PK -1, KG 0, "01".."13" -> 1..13; None if unknown."""
    go = GRADE_ORD.get(grade)
    return None if go is None else go - GRADE_ORD["KG"]


def enrollment_column(grade: str) -> str:
    """The LCT DB enrollment column for a K-12 grade token (`enrollment_by_grade`)."""
    return "enrollment_kindergarten" if grade == "KG" else f"enrollment_grade_{grade_int(grade)}"


def bands_for(gslo, gshi):
    """Which bands a school's grade span overlaps. Returns a set; empty if ungraded/unknown (M-M, etc.)."""
    lo, hi = GRADE_ORD.get(norm(gslo)), GRADE_ORD.get(norm(gshi))
    if lo is None or hi is None or hi < lo:
        return set()
    span = set(range(lo, hi + 1))
    return {b for b, rng in BANDS.items() if span & set(rng)}


# NCES LEVEL maps cleanly to exactly one band for these three values. Trust it over the grade range
# when it applies; this fixes dilution, so a K-6 "Elementary" school no longer also counts toward
# middle just because grade 6 clips the band boundary. Everything else (Other, Secondary, Not
# reported, Not applicable, Ungraded, Adult Education, blank) is genuinely ambiguous or combined and
# falls back to grade-range overlap.
LEVEL_BAND = {"Elementary": "elementary", "Middle": "middle", "High": "high"}

# #498 boundary: the intermediate / upper-elementary span definition. Plain grade numbers (PK/KG = 0).
INTERMEDIATE_MAX_START = 4   # a span starting at grade 5+ is middle-family, never elementary
INTERMEDIATE_MAX_TOP = 6     # a span topping above grade 6 is not an elementary-side span
INTERMEDIATE_START_ORD = GRADE_ORD[f"{INTERMEDIATE_MAX_START:02d}"]
INTERMEDIATE_TOP_ORD = GRADE_ORD[f"{INTERMEDIATE_MAX_TOP:02d}"]


def is_intermediate_span(gslo, gshi):
    """#498: the intermediate / upper-elementary span: starts at grade ≤4 AND tops at grade ≤6
    (Liberati: 04-06). Deliberately NOT 05-06 (5-6 is middle when it feeds a 7-8 — Ian's standard,
    and NCES's Middle tag agrees there); the 05-05/06-06 orphans were RULED middle (2026-07-15)."""
    lo, hi = GRADE_ORD.get(norm(gslo)), GRADE_ORD.get(norm(gshi))
    if lo is None or hi is None or hi < lo:
        return False
    return lo <= INTERMEDIATE_START_ORD and hi <= INTERMEDIATE_TOP_ORD


def effective_level_band(level, gslo, gshi):
    """#498 (DECIDED Ian 2026-07-15): the clean-LEVEL band with the ONE corpus-profiled override.
    LEVEL='Middle' on an intermediate span (starts ≤4, tops ≤6) is an upper-ELEMENTARY school
    (~330 schools nationally, 0.4%). NCES over-assigns Middle to intermediates; measured against
    the full 2024-25 corpus, this is the ONLY hard LEVEL-vs-span disagreement class that exists, and
    the reverse edge is zero. LEVEL stays primary everywhere else (the 2026-06-22 anti-dilution
    decision): this is a scalpel, not an inversion. Every caller that places or counts schools
    should use THIS, not LEVEL_BAND directly. Returns the band, or None (ambiguous)."""
    b = LEVEL_BAND.get((level or "").strip())
    if b == "middle" and is_intermediate_span(gslo, gshi):
        return "elementary"
    return b


def primary_bands_for(level, gslo, gshi):
    """A school's PRIMARY band(s): LEVEL-mapped (single band) when clean, with the #498
    intermediate carve-out applied; else grade-range overlap (bands_for(), possibly multiple
    bands) for combined/ambiguous LEVEL values."""
    b = effective_level_band(level, gslo, gshi)
    return {b} if b else bands_for(gslo, gshi)
