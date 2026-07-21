"""Stage 9 — Incorporate: the I/O orchestrator (the sanctioned cross-DB write).

This is the ONE acquisition module that imports `infrastructure.database` (the second import-linter
exception after Stage 1's read — pyproject.toml). It reads the approved gate@8 closing argument from
the **governance** DB and writes the per-band minutes into the **LCT production** DB's `bell_schedules`
landing zone, then stamps an 'incorporated' state_event back on the governance side.

Fail-loud (Rule #6 verify-in-DB). Idempotent + re-approval-safe: an UPSERT per band, a Stage-9 orphan
reconcile for the year-change case, and a governance idempotency ledger that short-circuits an
unchanged fingerprint. Two-DB safety is ORDERING (LCT commit before the governance stamp), not a
distributed transaction — the two DBs are deliberately decoupled.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Optional

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage8_aggregate import approval as APV
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA
from infrastructure.acquisition.stage9_incorporate import ledger as LEDGER
from infrastructure.acquisition.stage9_incorporate import mapping as MAP
from infrastructure.acquisition.stage9_incorporate import per_grade as PG

# The sanctioned cross-DB imports (import-linter ignore_imports #2, pyproject.toml):
from infrastructure.database import queries as Q
from infrastructure.database.connection import session_scope as lct_session_scope
from infrastructure.database.models import BellSchedule, DistrictGradeMinutes, StateRequirement

# Methods that mark a `bell_schedules` row as Stage-9-authored (there is no created_by column) — the
# orphan-reconcile scope. Legacy rows (human_provided / tier_*) are never touched.
STAGE9_METHODS = ("council_extraction", "statutory_fallback")

STATUTORY_DEFAULT_MINUTES = 360


@dataclass
class IncorporationResult:
    district_id: str
    status: str                      # incorporated | already_incorporated | dry_run | not_eligible | no_bands
    written: list = field(default_factory=list)
    fingerprint: Optional[str] = None
    reason: Optional[str] = None
    grades: int = 0                  # #605: per-grade projection rows written
    overlaps: int = 0                # grades resolved by the overlap tie-rule (flagged)


def _norm_did(did: str) -> str:
    return str(did).zfill(7)   # pad, never strip (migration 015 / issue #20)


def _statutory_minutes(session, state: Optional[str], band: str) -> int:
    """State statutory minimum for a band (elementary/middle/high), or the 360 last-resort default."""
    if state:
        req = session.query(StateRequirement).filter(StateRequirement.state == state).first()
        if req:
            minutes = req.get_minutes(band)
            if minutes:
                return int(minutes)
    return STATUTORY_DEFAULT_MINUTES


def _reconcile_stage9_orphans(session, stored_did: str, keep: set) -> None:
    """Delete this district's Stage-9-authored rows whose (year, grade_level) is not in the just-
    written set — converges each incorporation to exactly its current band set (the year-change case).
    Scoped to STAGE9_METHODS so legacy rows are never touched."""
    rows = (session.query(BellSchedule)
            .filter(BellSchedule.district_id == stored_did,
                    BellSchedule.method.in_(STAGE9_METHODS))
            .all())
    for r in rows:
        if (r.year, r.grade_level) not in keep:
            session.delete(r)
    session.flush()


def _write_grade_minutes(session, stored_did: str, grade_minutes: list, fingerprint, approval_id,
                         actor: str) -> None:
    """UPSERT the per-grade projection (#605) on (district_id, grade), then reconcile grades that
    dropped out (a band removed at re-approval). One current row per (district, grade)."""
    keep = set()
    for gm in grade_minutes:
        keep.add(gm.grade)
        prov = PG.provenance(gm, fingerprint=fingerprint, approval_id=approval_id, actor=actor)
        row = (session.query(DistrictGradeMinutes)
               .filter(DistrictGradeMinutes.district_id == stored_did,
                       DistrictGradeMinutes.grade == gm.grade).first())
        if row:
            row.instructional_minutes = gm.minutes
            row.source_band = gm.source_band
            row.method = gm.method
            row.minutes_basis = gm.minutes_basis
            row.year = gm.year
            row.overlap_flag = gm.overlap_flag
            row.provenance = prov
        else:
            session.add(DistrictGradeMinutes(
                district_id=stored_did, grade=gm.grade, instructional_minutes=gm.minutes,
                source_band=gm.source_band, method=gm.method, minutes_basis=gm.minutes_basis,
                year=gm.year, overlap_flag=gm.overlap_flag, provenance=prov))
    for row in (session.query(DistrictGradeMinutes)
                .filter(DistrictGradeMinutes.district_id == stored_did).all()):
        if row.grade not in keep:
            session.delete(row)
    session.flush()


def _verify_written(session, stored_did: str, writes: list) -> None:
    """Rule #6 — re-query each intended row IN THE SAME session and assert minutes/method/basis
    before commit. Raises on any absence or mismatch (rolls the whole write back)."""
    for w in writes:
        row = (session.query(BellSchedule)
               .filter(BellSchedule.district_id == stored_did,
                       BellSchedule.year == w.year,
                       BellSchedule.grade_level == w.grade_level)
               .first())
        if row is None:
            raise RuntimeError(
                f"Stage 9 verify failed: {stored_did}/{w.year}/{w.grade_level} not found in DB")
        if (row.instructional_minutes != w.minutes or row.method != w.method
                or row.minutes_basis != w.minutes_basis):
            raise RuntimeError(
                f"Stage 9 verify mismatch for {stored_did}/{w.year}/{w.grade_level}: "
                f"db=({row.instructional_minutes},{row.method},{row.minutes_basis}) "
                f"expected=({w.minutes},{w.method},{w.minutes_basis})")


def incorporate_district(district_id, *, actor="auto:stage9", dry_run=False, force=False,
                         strict=False) -> IncorporationResult:
    """Incorporate one approved district. Returns an IncorporationResult; raises only on a genuine
    fault (missing LCT district, verify mismatch) or, with strict=True, on ineligibility."""
    # ---- Phase A: governance read + eligibility ----
    with gdb.session_scope() as gs:
        ca_live = CA.load_closing_argument(gs, district_id, record_drift_event=False)
        fp_live = CA.fingerprint(ca_live)
        status = APV.decision_status(gs, district_id, current_fingerprint=fp_live)
        if not status["is_approved"]:
            reason = ("never_decided" if not status["decided"]
                      else "sent_back" if status["disposition"] != "approved"
                      else "stale")
            if strict:
                raise ValueError(f"District {district_id} not eligible for Stage 9: {reason}")
            return IncorporationResult(district_id, "not_eligible",
                                       fingerprint=fp_live, reason=reason)
        latest = APV.latest_decision(gs, district_id, with_receipt=True)
        receipt = json.loads(latest["receipt_json"])
        approval_id = latest["approval_id"]
        # The LIVE roster (unsigned) sources band_grade_span — pre-#499 frozen receipts carry no
        # slot_projection, and roster coverage is derived-live-never-frozen by design.
        grade_span_source = ca_live
        inc = LEDGER.latest_incorporation(gs, district_id)
        already = bool(inc and inc.get("fingerprint") == fp_live)

    if already and not force:
        return IncorporationResult(district_id, "already_incorporated", fingerprint=fp_live)

    # ---- Phase B: pure map ----
    writes = MAP.plan_writes(receipt, fingerprint=fp_live, approval_id=approval_id, actor=actor,
                             grade_span_source=grade_span_source)
    if not writes:
        return IncorporationResult(district_id, "no_bands", fingerprint=fp_live,
                                   reason="approved receipt carried no bands")
    if dry_run:
        return IncorporationResult(district_id, "dry_run",
                                   written=[w.summary() for w in writes], fingerprint=fp_live)

    # ---- Phase C: LCT write (single txn, verify before commit) ----
    ndid = _norm_did(district_id)
    with lct_session_scope() as ls:
        district = Q.get_district_by_id(ls, ndid)
        if not district:
            raise ValueError(f"District {district_id} not found in LCT production DB")
        stored_did = district.nces_id
        state = district.state
        for w in writes:
            if w.needs_statutory_minutes:
                w.minutes = _statutory_minutes(ls, state, w.grade_level)
            Q.add_bell_schedule(
                ls, district_id, w.year, w.grade_level, w.minutes,
                start_time=w.start_time, end_time=w.end_time,
                schools_sampled=w.schools_sampled, source_urls=w.source_urls,
                confidence=w.confidence, method=w.method, minutes_basis=w.minutes_basis,
                source_description=w.source_description, notes=w.notes,
                raw_import=w.raw_import, created_by=actor)
        ls.flush()
        _reconcile_stage9_orphans(ls, stored_did, keep={(w.year, w.grade_level) for w in writes})
        _verify_written(ls, stored_did, writes)
        # #605: project the approved bands DOWN to per-grade minutes (the LCT-consumable artifact)
        grade_minutes = PG.project(writes, fingerprint=fp_live, approval_id=approval_id, actor=actor)
        _write_grade_minutes(ls, stored_did, grade_minutes, fp_live, approval_id, actor)
        n_grades = len(grade_minutes)
        n_overlaps = sum(1 for gm in grade_minutes if gm.overlap_flag)
        # commit on context-manager exit

    # ---- Phase D: governance stamp (after the LCT commit) ----
    bands = {w.grade_level: w.method for w in writes}
    with gdb.session_scope() as gs:
        LEDGER.record_incorporation(gs, district_id, fingerprint=fp_live, approval_id=approval_id,
                                    bands=bands, actor=actor)

    return IncorporationResult(district_id, "incorporated",
                               written=[w.summary() for w in writes], fingerprint=fp_live,
                               grades=n_grades, overlaps=n_overlaps)


def incorporate_batch(district_ids: Iterable, *, actor="auto:stage9", dry_run=False,
                      force=False, continue_on_error=True) -> list:
    """Incorporate many districts. On a per-district fault, records a not_eligible-style error result
    and continues (unless continue_on_error=False, which re-raises)."""
    results = []
    for did in district_ids:
        try:
            results.append(incorporate_district(did, actor=actor, dry_run=dry_run, force=force))
        except Exception as exc:  # noqa: BLE001 — batch resilience; the fault is captured per district
            if not continue_on_error:
                raise
            results.append(IncorporationResult(str(did), "error", reason=f"{type(exc).__name__}: {exc}"))
    return results
