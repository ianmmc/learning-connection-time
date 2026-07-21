"""Stage 9 mapping — PURE: a frozen gate@8 closing-argument receipt -> a list of BandWrite plans.

No DB import. One BandWrite per band the receipt determined (method='council_extraction') plus one
per claimed-but-unsatisfied band (method='statutory_fallback', minutes resolved in the I/O layer from
StateRequirement so this stays DB-free — #94/REQ-049). All three bands are written faithfully; no
blending (the LEA-level per-grade projection is a separate follow-up). Unit-tested against real
receipts minted by closing_argument.build_closing_argument.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from infrastructure.acquisition.stage9_incorporate import provenance as P


@dataclass
class BandWrite:
    """One planned `bell_schedules` UPSERT (district_id supplied by the orchestrator)."""
    grade_level: str
    method: str
    minutes_basis: str
    year: str
    year_basis: str
    minutes: Optional[int] = None            # None for statutory until resolved in the I/O layer
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    confidence: str = "high"
    schools_sampled: list = field(default_factory=list)
    source_urls: list = field(default_factory=list)
    source_description: Optional[str] = None
    notes: Optional[str] = None
    raw_import: Optional[dict] = None
    needs_statutory_minutes: bool = False
    statutory_reason: Optional[str] = None

    def summary(self) -> dict:
        return {"grade_level": self.grade_level, "method": self.method,
                "minutes_basis": self.minutes_basis, "minutes": self.minutes,
                "year": self.year, "year_basis": self.year_basis, "confidence": self.confidence,
                "needs_statutory_minutes": self.needs_statutory_minutes,
                "statutory_reason": self.statutory_reason}


def plan_writes(receipt: dict, *, fingerprint: Optional[str] = None,
                approval_id: Optional[int] = None, actor: str = "auto:stage9",
                grade_span_source: Optional[dict] = None) -> list:
    """Deterministic map: frozen receipt -> BandWrites. Council bands first, then statutory-fallback
    for each claimed-but-unsatisfied band. Signed fields come from `receipt`; the (unsigned)
    band_grade_span reads `grade_span_source` (the LIVE closing argument) when provided."""
    writes = []

    for band, b in (receipt.get("bands") or {}).items():
        urls = P.collect_source_urls(b)
        year, basis = P.resolve_schedule_year(b, urls)
        agg = b.get("method")
        sampling = b.get("sampling") or {}
        writes.append(BandWrite(
            grade_level=band,
            method="council_extraction",
            minutes_basis="gross_bell_to_bell",
            year=year, year_basis=basis,
            minutes=b.get("gross_minutes"),
            start_time=b.get("start_time"), end_time=b.get("end_time"),
            confidence=P.band_confidence(sampling),
            schools_sampled=P.collect_schools_sampled(b),
            source_urls=urls,
            source_description=P.council_source_description(band, sampling, agg),
            notes=P.council_notes(band, sampling, agg, basis),
            raw_import=P.council_raw_import(receipt, band, b, fingerprint=fingerprint,
                                            approval_id=approval_id, year_basis=basis, actor=actor,
                                            grade_span_source=grade_span_source),
        ))

    unsatisfied = (receipt.get("negative_space") or {}).get("unsatisfied_bands") or []
    for band in unsatisfied:
        reason = P.statutory_reason(receipt, band)
        year, basis = P.resolve_schedule_year({}, None)   # no schedule -> current-year KEY only
        writes.append(BandWrite(
            grade_level=band,
            method="statutory_fallback",
            minutes_basis="statutory",
            year=year, year_basis=basis,
            minutes=None, needs_statutory_minutes=True, statutory_reason=reason,
            confidence="low",
            source_description=P.statutory_source_description(band, reason),
            notes=P.statutory_notes(band, reason),
            raw_import=P.statutory_raw_import(receipt, band, fingerprint=fingerprint,
                                              approval_id=approval_id, reason=reason, actor=actor,
                                              grade_span_source=grade_span_source),
        ))

    return writes
