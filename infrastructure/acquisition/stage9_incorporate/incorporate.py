"""Stage 9 — Incorporate: the I/O orchestrator (the sanctioned cross-DB write).

This is the ONE acquisition module that imports `infrastructure.database` (the second import-linter
exception after Stage 1's read — pyproject.toml). It reads the approved gate@8 closing argument from
the **governance** DB and writes the per-band minutes into the **LCT production** DB's `bell_schedules`
landing zone, then stamps an 'incorporated' state_event back on the governance side.

Fail-loud (Rule #6 verify-in-DB, for BOTH written tables). Idempotent + re-approval-safe: an UPSERT
per band, a Stage-9 orphan reconcile for the year-change case, and a governance idempotency ledger
that short-circuits an unchanged fingerprint. Two-DB safety is ORDERING (LCT commit before the
governance stamp), not a distributed transaction — the two DBs are deliberately decoupled.

Standing walls (PR #607 review):
  - batch_00000 (benchmark) districts are REFUSED — "Stage 9 (non-benchmark only) is the sole
    promoter to bell_schedules" (stage7_extract/models.py; CLAUDE.md's permanent wall).
  - A Stage-9 write whose (year, grade_level) key is already held by a NON-Stage-9 method
    (human_provided, tier_*, …) FAILS LOUD — human/legacy work is never silently overwritten; a
    person resolves the conflict (remove the manual row, or exclude the band at gate@8) and re-runs.
    (`--dry-run` surfaces the conflict instead of raising, so the preview shows it before a real run.)
  - The receipt actually written is re-checked against the decision the eligibility gate validated
    (same approval_id, still approved) — a gate@8 action landing between the two governance reads
    must not smuggle a different determination into production (the PR #252 TOCTOU class).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import receipts as RCPT
from infrastructure.acquisition.stage8_aggregate import approval as APV
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA
from infrastructure.acquisition.stage9_incorporate import ledger as LEDGER
from infrastructure.acquisition.stage9_incorporate import mapping as MAP
from infrastructure.acquisition.stage9_incorporate import per_grade as PG

# The sanctioned cross-DB imports (import-linter ignore_imports #2, pyproject.toml):
from infrastructure.database import queries as Q
from infrastructure.database.connection import session_scope as lct_session_scope
from infrastructure.database.models import BellSchedule, DistrictGradeMinutes

# Methods that mark a `bell_schedules` row as Stage-9-authored (there is no created_by column) — the
# orphan-reconcile scope AND the overwrite boundary: any other method is a protected legacy row.
STAGE9_METHODS = ("council_extraction", "statutory_fallback")

STATUTORY_DEFAULT_MINUTES = 360

_schemas_ensured = False


@dataclass
class IncorporationResult:
    district_id: str
    status: str                      # incorporated | already_incorporated | dry_run | not_eligible | no_bands
    written: list = field(default_factory=list)
    fingerprint: Optional[str] = None
    reason: Optional[str] = None
    grades: int = 0                  # #605: per-grade projection rows written
    overlaps: int = 0                # grades resolved by the overlap tie-rule (flagged)
    conflicts: list = field(default_factory=list)   # dry-run only: bands blocked by a non-Stage-9 row


def _norm_did(did) -> str:
    return str(did).strip().zfill(7)   # pad, never strip digits (migration 015 / issue #20)


def _ensure_schemas() -> None:
    """Create the governance precious tables if absent (idempotent, once per process) — every other
    stage entry point does this; a standalone/cron Stage-9 run against a fresh governance DB must
    not crash on the first state_event write (PR #607 review)."""
    global _schemas_ensured
    if not _schemas_ensured:
        gdb.init_precious_schema()
        _schemas_ensured = True


def _is_benchmark_district(gs, district_id: str) -> bool:
    """True when the district belongs to any batch_type='benchmark' batch (batch_00000) — the
    permanent Stage-9 wall (mirrors stage7_execute._benchmark_district_ids, which Stage 9 cannot
    import: process_governance sits ABOVE this layer). Only a MISSING batch table (a fresh
    governance DB) is treated as not-benchmark; any other query error FAILS LOUD — a wall that can
    never fail-open, so a transient DB error can't let a benchmark district through (PR #607 R2)."""
    try:
        return bool(gs.execute(text(
            "SELECT 1 FROM batch_district bd JOIN batch b ON b.batch_id = bd.batch_id "
            "WHERE b.batch_type = 'benchmark' AND bd.district_id = :d LIMIT 1"),
            {"d": district_id}).first())
    except ProgrammingError:
        gs.rollback()   # relation "batch"/"batch_district" does not exist — fresh DB, no members
        return False


def _statutory_minutes(session, state: Optional[str], band: str) -> int:
    """State statutory minimum for a band (elementary/middle/high), or the 360 last-resort default.
    Uses the canonical get_state_requirement lookup (case-normalized) and treats only NULL — not a
    literal 0 — as absent, so a zero-valued seed row fails loud at the 100-600 DB CHECK instead of
    being papered over with a fabricated 360 (PR #607 review)."""
    if state:
        req = Q.get_state_requirement(session, state)
        if req:
            minutes = req.get_minutes(band)
            if minutes is not None:
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
    dropped out (a band removed at re-approval). One current row per (district, grade). One bulk
    fetch serves both the upsert decision and the orphan diff (PR #607 review: was N+1)."""
    existing = {r.grade: r for r in
                (session.query(DistrictGradeMinutes)
                 .filter(DistrictGradeMinutes.district_id == stored_did).all())}
    keep = set()
    for gm in grade_minutes:
        keep.add(gm.grade)
        prov = PG.provenance(gm, fingerprint=fingerprint, approval_id=approval_id, actor=actor)
        row = existing.get(gm.grade)
        if row:
            row.instructional_minutes = gm.minutes
            row.source_band = gm.source_band
            row.method = gm.method
            row.minutes_basis = gm.minutes_basis
            row.year = gm.year
            row.overlap_flag = gm.overlap_flag
            row.human_vouched = gm.human_vouched   # #626
            row.provenance = prov
        else:
            session.add(DistrictGradeMinutes(
                district_id=stored_did, grade=gm.grade, instructional_minutes=gm.minutes,
                source_band=gm.source_band, method=gm.method, minutes_basis=gm.minutes_basis,
                year=gm.year, overlap_flag=gm.overlap_flag, human_vouched=gm.human_vouched,
                provenance=prov))
    for grade, row in existing.items():
        if grade not in keep:
            session.delete(row)
    session.flush()


def _foreign_collisions(session, stored_did: str, writes: list) -> list:
    """The (year, grade_level) keys a Stage-9 write would land on that are already held by a
    NON-Stage-9 method (human_provided / tier_* / legacy) — human/legacy rows Stage 9 must never
    silently overwrite. Returns [{grade_level, year, existing_method}] (empty = clear to write)."""
    existing = {(r.year, r.grade_level): r for r in
                (session.query(BellSchedule)
                 .filter(BellSchedule.district_id == stored_did).all())}
    out = []
    for w in writes:
        row = existing.get((w.year, w.grade_level))
        if row is not None and row.method not in STAGE9_METHODS:
            out.append({"grade_level": w.grade_level, "year": w.year,
                        "existing_method": row.method})
    return out


def _verify_written(session, stored_did: str, writes: list) -> None:
    """Rule #6 — re-query each intended row IN THE SAME session and assert minutes/method/basis
    (and, for statutory rows, that no council-era clock times survived) before commit. Raises on
    any absence or mismatch (rolls the whole write back)."""
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
        if row.method == "statutory_fallback" and (row.start_time or row.end_time):
            raise RuntimeError(
                f"Stage 9 verify: statutory row {stored_did}/{w.year}/{w.grade_level} carries "
                f"clock times ({row.start_time!r}, {row.end_time!r}) — must be cleared")


def _verify_grade_minutes(session, stored_did: str, grade_minutes: list) -> None:
    """Rule #6 for the projection table too — district_grade_minutes is what the LCT calc actually
    reads, one hop closer to the consumed metric than bell_schedules (PR #607 review)."""
    rows = {r.grade: r for r in
            (session.query(DistrictGradeMinutes)
             .filter(DistrictGradeMinutes.district_id == stored_did).all())}
    expected = {gm.grade for gm in grade_minutes}
    if set(rows) != expected:
        raise RuntimeError(
            f"Stage 9 grade-minutes verify failed for {stored_did}: "
            f"db grades {sorted(rows)} != expected {sorted(expected)}")
    for gm in grade_minutes:
        r = rows[gm.grade]
        if (r.instructional_minutes != gm.minutes or r.method != gm.method
                or r.minutes_basis != gm.minutes_basis or r.source_band != gm.source_band
                or r.year != gm.year or r.overlap_flag != gm.overlap_flag):
            raise RuntimeError(
                f"Stage 9 grade-minutes verify mismatch for {stored_did}/{gm.grade}: "
                f"db=({r.instructional_minutes},{r.method},{r.minutes_basis},{r.source_band},"
                f"{r.year},{r.overlap_flag}) expected=({gm.minutes},{gm.method},{gm.minutes_basis},"
                f"{gm.source_band},{gm.year},{gm.overlap_flag})")
        # #95 provenance must round-trip as a dict (catches a JSONB serialization drop)
        if not isinstance(r.provenance, dict) or r.provenance.get("facts_fingerprint") is None:
            raise RuntimeError(
                f"Stage 9 grade-minutes verify: {stored_did}/{gm.grade} provenance not persisted "
                f"as a fingerprinted dict (got {type(r.provenance).__name__})")


def incorporate_district(district_id, *, actor="auto:stage9", dry_run=False, force=False,
                         strict=False, refresh_twin=True) -> IncorporationResult:
    """Incorporate one approved district. Returns an IncorporationResult; raises only on a genuine
    fault (missing LCT district, verify mismatch) or, with strict=True, on ineligibility.

    `refresh_twin=True` regenerates district_status.json in-path (the #615 fix). incorporate_batch
    passes False and exports ONCE at the end (issue #49 O(N^2) avoidance)."""
    district_id = _norm_did(district_id)   # governance + LCT ids share the zero-padded convention
    _ensure_schemas()

    def _ineligible(reason: str, fp=None) -> IncorporationResult:
        if strict:
            raise ValueError(f"District {district_id} not eligible for Stage 9: {reason}")
        return IncorporationResult(district_id, "not_eligible", fingerprint=fp, reason=reason)

    # ---- Phase A: governance read + eligibility ----
    with gdb.session_scope() as gs:
        if _is_benchmark_district(gs, district_id):
            return _ineligible("benchmark district (batch_00000) — walled off from Stage-9 writes")
        ca_live = CA.load_closing_argument(gs, district_id, record_drift_event=False)
        fp_live = CA.fingerprint(ca_live)
        status = APV.decision_status(gs, district_id, current_fingerprint=fp_live)
        if not status["is_approved"]:
            reason = ("never_decided" if not status["decided"]
                      else "sent_back" if status["disposition"] != "approved"
                      else "stale")
            return _ineligible(reason, fp_live)
        latest = APV.latest_decision(gs, district_id, with_receipt=True)
        # TOCTOU re-check (PR #252 class): the receipt row we WRITE from must be the exact decision
        # the eligibility gate validated — a concurrent gate@8 action between the two reads
        # (send-back, re-approval) must not smuggle a different determination into production.
        validated_id = (status.get("latest") or {}).get("approval_id")
        if (latest is None or latest["disposition"] != "approved"
                or (validated_id is not None and latest["approval_id"] != validated_id)):
            return _ineligible("decision_changed_during_read", fp_live)
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
    if dry_run:
        # Read-only preview: resolve statutory minutes (so the number a real run would write shows,
        # not "None"), surface any foreign-row conflict a real run would fail on, and flag a
        # retraction (an empty re-approval of a previously-incorporated district deletes its rows).
        with lct_session_scope() as ls:
            district = Q.get_district_by_id(ls, district_id)
            conflicts = _foreign_collisions(ls, district.nces_id, writes) if district else []
            if district:
                for w in writes:
                    if w.needs_statutory_minutes and w.minutes is None:
                        w.minutes = _statutory_minutes(ls, district.state, w.grade_level)
        reason = None
        if conflicts:
            reason = "conflict: " + ", ".join(f"{c['grade_level']}@{c['year']}[{c['existing_method']}]"
                                              for c in conflicts)
        elif not writes:
            reason = (f"would RETRACT {len(inc.get('bands') or {})} incorporated band(s)"
                      if inc else "no_bands")
        return IncorporationResult(district_id, "dry_run",
                                   written=[w.summary() for w in writes], fingerprint=fp_live,
                                   reason=reason, conflicts=conflicts)
    if not writes and inc is None:
        return IncorporationResult(district_id, "no_bands", fingerprint=fp_live,
                                   reason="approved receipt carried no bands")
    # An EMPTY writes list with a prior incorporation falls through: Phase C reconciles the prior
    # rows away (an empty re-approval RETRACTS, it doesn't linger — PR #607 review).

    # ---- Phase C: LCT write (single txn, verify before commit) ----
    with lct_session_scope() as ls:
        district = Q.get_district_by_id(ls, district_id)
        if not district:
            raise ValueError(f"District {district_id} not found in LCT production DB")
        stored_did = district.nces_id
        state = district.state
        district_name = district.name   # captured in-session for the receipt slug (ORM detaches on exit)
        # FAIL LOUD on a foreign-row collision: a (year, grade_level) key held by a NON-Stage-9
        # method (human_provided / tier_* / legacy) is a human-vs-pipeline conflict Stage 9 must
        # never silently resolve. Raise BEFORE any write so nothing is committed; a person removes
        # the manual row or excludes the band at gate@8, then re-runs (PR #607 R2 — this replaces
        # the earlier "silently skip protected bands", which orphaned the band's per-grade rows).
        conflicts = _foreign_collisions(ls, stored_did, writes)
        if conflicts:
            raise RuntimeError(
                f"Stage 9 refuses to overwrite non-Stage-9 bell rows for {district_id}: "
                f"{conflicts}. Resolve the conflict (remove the manual row, or exclude the band at "
                f"gate@8) then re-incorporate.")
        for w in writes:
            if w.needs_statutory_minutes:
                w.minutes = _statutory_minutes(ls, state, w.grade_level)
            schedule = Q.add_bell_schedule(
                ls, stored_did, w.year, w.grade_level, w.minutes,
                start_time=w.start_time, end_time=w.end_time,
                schools_sampled=w.schools_sampled, source_urls=w.source_urls,
                confidence=w.confidence, method=w.method, minutes_basis=w.minutes_basis,
                source_description=w.source_description, notes=w.notes,
                raw_import=w.raw_import, created_by=actor)
            if w.method == "statutory_fallback":
                # A council→statutory flip over the SAME key (council's consensus year == current
                # year) hits add_bell_schedule's UPDATE path, which preserves the old None-args
                # times — the retracted council times must not survive on a statutory row.
                schedule.start_time = None
                schedule.end_time = None
        ls.flush()
        _reconcile_stage9_orphans(ls, stored_did, keep={(w.year, w.grade_level) for w in writes})
        _verify_written(ls, stored_did, writes)
        # #605: project the written bands DOWN to per-grade minutes (the LCT-consumable artifact).
        grade_minutes = PG.project(writes, fingerprint=fp_live, approval_id=approval_id, actor=actor)
        _write_grade_minutes(ls, stored_did, grade_minutes, fp_live, approval_id, actor)
        _verify_grade_minutes(ls, stored_did, grade_minutes)
        n_grades = len(grade_minutes)
        n_overlaps = sum(1 for gm in grade_minutes if gm.overlap_flag)
        # commit on context-manager exit

    # ---- Phase D: governance stamp + audit receipt (after the LCT commit) ----
    bands = {w.grade_level: w.method for w in writes}
    receipt_payload = {
        "stage": 9, "stage_name": "incorporate", "district_id": district_id, "state": state,
        "approval_id": approval_id, "facts_fingerprint": fp_live, "actor": actor,
        # gov_db + the LCT rows are authoritative; this receipt is a faithful audit projection, never
        # a transmission vehicle read back by the pipeline (REQ-164 / Decision-2 / governance §1).
        "authoritative": "gov_db:state_event + lct:bell_schedules/district_grade_minutes",
        "bands": [w.summary() for w in writes],
        "grade_minutes": [gm.summary() for gm in grade_minutes],
        "n_grades": n_grades, "n_overlaps": n_overlaps}
    with gdb.session_scope() as gs:
        LEDGER.record_incorporation(gs, district_id, fingerprint=fp_live, approval_id=approval_id,
                                    bands=bands, actor=actor)
        gs.commit()                          # commit-before-derive: persist the stamp before the twin
        if refresh_twin:
            _refresh_status_twin(gs)         # #615: standalone exports here; batch exports once at end
    _stamp_receipt(district_id, district_name, receipt_payload)   # AFTER both commits (commit-before-receipt)

    return IncorporationResult(district_id, "incorporated",
                               written=[w.summary() for w in writes], fingerprint=fp_live,
                               grades=n_grades, overlaps=n_overlaps)


def _refresh_status_twin(gs) -> None:
    """Best-effort district_status.json regeneration from the COMMITTED gov log (#615: the twin lagged
    gate@8/Stage 9 until an incidental later export). gov_db is authoritative and the twin is
    regenerable, so a hiccup is logged, never a failed incorporation (matches cache_ingest's stance)."""
    try:
        DS.export_status(gs)
    except Exception as e:  # noqa: BLE001 — the twin is regenerable; never fail a committed write
        print(f"[warn] Stage 9 district_status.json refresh failed ({type(e).__name__}: {e}); "
              f"the twin reconciles on the next export")


def _stamp_receipt(district_id, district_name, receipt_payload) -> None:
    """Best-effort per-district Stage-9 audit receipt into the capture dir (REQ-164). Written AFTER the
    gov_db + LCT commits (commit-before-receipt); regenerable from gov_db + the LCT rows, so a disk
    hiccup is logged, never a failed incorporation."""
    try:
        RCPT.write_receipt(district_id, district_name, "stage9_incorporate", receipt_payload)
    except Exception as e:  # noqa: BLE001 — the receipt is regenerable; never fail a committed write
        print(f"[warn] Stage 9 receipt write failed for {district_id} "
              f"({type(e).__name__}: {e}); regenerable from gov_db + the LCT rows")


def incorporate_batch(district_ids: Iterable, *, actor="auto:stage9", dry_run=False,
                      force=False, strict=False, continue_on_error=True) -> list:
    """Incorporate many districts. On a per-district fault, records an error result and continues
    (unless continue_on_error=False, which re-raises). With strict=True an ineligible district is
    a fault — captured as an error result so a batch run surfaces it (nonzero CLI exit) instead of
    silently succeeding (PR #607 review: --strict used to be dropped in batch mode)."""
    results = []
    for did in district_ids:
        try:
            # refresh_twin=False: the twin is regenerated ONCE after the loop, not per district
            # (issue #49 O(N^2) avoidance — a full district_status.json rebuild per incorporation).
            results.append(incorporate_district(did, actor=actor, dry_run=dry_run, force=force,
                                                strict=strict, refresh_twin=False))
        except Exception as exc:  # noqa: BLE001 — batch resilience; the fault is captured per district
            if not continue_on_error:
                raise
            results.append(IncorporationResult(str(did), "error", reason=f"{type(exc).__name__}: {exc}"))
    if not dry_run and any(r.status == "incorporated" for r in results):
        _refresh_status_twin_run_end()   # one twin refresh for the whole batch (#615 + issue #49)
    return results


def _refresh_status_twin_run_end() -> None:
    """Best-effort ONE-shot twin refresh after a batch (issue #49). Fresh session (DS.export), so it
    reflects every district's committed stamp; a hiccup is logged, never a failed batch."""
    try:
        DS.export()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Stage 9 batch twin refresh failed ({type(e).__name__}: {e}); "
              f"reconciles on the next export")
