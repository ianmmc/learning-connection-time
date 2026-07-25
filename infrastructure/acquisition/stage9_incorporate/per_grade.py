"""Stage 9 — the LEA-level per-grade minutes projection (#605, epic #92). PURE.

Projects each approved band's modal minutes DOWN to the individual grade: `grade → owning band →
minutes`, using the band's LIVE grade span (`GSLO`/`GSHI`, from `raw_import.band_grade_span`) so
floating bands (a 7-9 middle) and merged shapes (K-8) resolve correctly. This is the artifact that
lets LCT consume the pipeline's 3-band minutes against 2-band staffing (the consumption is #606).

Grade → band, per district:
  - a band SERVES a grade when any of its serving schools' spans covers that grade (`GSLO..GSHI`);
    when a band has no live span (CCD files absent), it falls back to its canonical range (`BANDS`);
  - exactly one serving band → the grade takes that band's minutes;
  - ≥2 serving bands (overlap: e.g. a 7-9 middle and a 9-12 high both serving grade 9) → a
    deterministic LEA-level tie-rule: the grade's CANONICAL band wins when it is among the serving
    set; when it is NOT (a noisy-span shape where no serving band cleanly owns the grade), the
    fallback deterministically prefers the lowest band (elementary < middle < high) — an arbitrary
    but stable choice, honestly recorded as such in `overlap_flag` (never silent). No per-school
    headcount split — all LEA-grain.

No DB import. `writes` are the resolved `mapping.BandWrite`s (statutory minutes already filled in).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from infrastructure.acquisition.common.school_sampling import BANDS, GRADE_ORD, norm

# The LCT-relevant grade range: KG + grades 1-12 (PK is excluded from LCT; grade 13 rides with high
# for MINUTES but is not a distinct LCT weight — enrollment scopes stop at 12).
GRADE_TOKENS = ["KG"] + [f"{n:02d}" for n in range(1, 13)]
_BAND_ORDER = {"elementary": 0, "middle": 1, "high": 2}


@dataclass
class GradeMinute:
    grade: str
    minutes: Optional[int]
    source_band: str
    method: str
    minutes_basis: Optional[str]
    year: Optional[str]
    serving_bands: list
    overlap_flag: Optional[str]
    human_vouched: bool = False              # #626: inherited from the grade's owning band

    def summary(self) -> dict:
        return {"grade": self.grade, "minutes": self.minutes, "source_band": self.source_band,
                "method": self.method, "overlap_flag": self.overlap_flag}


def _canonical_grades(band: str) -> set:
    """The GRADE_TOKENS whose ordinal falls in a band's canonical range (elementary K-5 / middle 6-8
    / high 9-12) — the fallback coverage when a band carries no live roster span."""
    rng = BANDS.get(band)
    if rng is None:
        return set()
    return {g for g in GRADE_TOKENS if GRADE_ORD[g] in rng}


def _span_grades(slot_spans: list) -> set:
    """The GRADE_TOKENS a band's serving-school spans (`gslo..gshi`) actually cover."""
    covered = set()
    for s in slot_spans or []:
        lo, hi = GRADE_ORD.get(norm(s.get("gslo"))), GRADE_ORD.get(norm(s.get("gshi")))
        if lo is None or hi is None or hi < lo:
            continue
        covered |= {g for g in GRADE_TOKENS if lo <= GRADE_ORD[g] <= hi}
    return covered


def _canon_band(grade: str) -> Optional[str]:
    """Which canonical band OWNS a grade (elementary K-5 / middle 6-8 / high 9-12) — the tie-rule."""
    go = GRADE_ORD[grade]
    for band, rng in BANDS.items():
        if go in rng:
            return band
    return None


def _band_coverage(writes) -> dict:
    """{band: set(GRADE_TOKENS it serves)} — live span when present, else canonical range."""
    cov = {}
    for w in writes:
        spans = ((w.raw_import or {}).get("band_grade_span") or {}).get("slot_spans") or []
        grades = _span_grades(spans) or _canonical_grades(w.grade_level)
        cov[w.grade_level] = grades
    return cov


def project(writes, *, fingerprint: Optional[str] = None, approval_id: Optional[int] = None,
            actor: str = "auto:stage9") -> list:
    """Frozen-receipt BandWrites → per-grade GradeMinutes. Council + statutory bands both project
    (a statutory band contributes statutory minutes to its grades, label preserved)."""
    meta = {w.grade_level: w for w in writes}
    coverage = _band_coverage(writes)
    out = []
    for g in GRADE_TOKENS:
        serving = [b for b in meta if g in coverage.get(b, set())]
        if not serving:
            continue                         # no band serves g → LCT falls back to statutory (#606)
        if len(serving) == 1:
            band, flag = serving[0], None
        else:
            canon = _canon_band(g)
            if canon in serving:
                band = canon
            else:
                band = sorted(serving, key=lambda b: _BAND_ORDER.get(b, 9))[0]
            flag = f"overlap:{'+'.join(sorted(serving))}->{band}"
        w = meta[band]
        out.append(GradeMinute(
            grade=g, minutes=w.minutes, source_band=band, method=w.method,
            minutes_basis=w.minutes_basis, year=w.year, serving_bands=sorted(serving),
            overlap_flag=flag, human_vouched=bool(w.human_vouched)))   # #626
    return out


def provenance(gm: GradeMinute, *, fingerprint, approval_id, actor) -> dict:
    return {"facts_fingerprint": fingerprint, "approval_id": approval_id,
            "source_band": gm.source_band, "serving_bands": gm.serving_bands,
            "year_basis_band": gm.source_band, "actor": actor}
