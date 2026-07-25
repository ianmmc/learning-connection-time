"""Stage 9 provenance — PURE helpers that turn a frozen gate@8 closing-argument band into the
`bell_schedules` write's provenance fields (#95 / REQ-050) and resolve its year coordinate.

No DB import (the cross-DB hole stays in incorporate.py). Import-safe from the pure mapping layer
and the unit tests. Every value here is derived deterministically from the frozen receipt.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Optional

from infrastructure.acquisition.common.timeutil import utcnow
from infrastructure.utilities.school_year import (
    content_school_year,
    current_school_year,
    is_acceptable_data_year,
)


# ----------------------------- year resolution -----------------------------
def band_school_years(band: dict) -> list:
    """The per-school stated school_year readings (#254) present in a band, non-null."""
    return [s.get("school_year") for s in band.get("schools", []) if s.get("school_year")]


def band_human_vouched(band: dict) -> bool:
    """#626: did a human vouch for this band's value at gate@8? True when any INCLUDED school carries a
    human determination — a `human_override` (incl. a note-only approval like Dickinson's "I'm
    approving"), an applied times-override, or a hand-added cited fact (`human_added`, #474). Such a
    determination is durable + auditable (a named actor took responsibility) and renders the band's
    value acceptable past the REQ-026 temporal window (Ian, 2026-07-24). Excluded (struck-through)
    schools never count — they were removed from the value, so an override on one isn't a vouch for it."""
    for s in band.get("schools", []):
        if s.get("excluded"):
            continue
        if s.get("human_override") or s.get("override_applied") or s.get("human_added"):
            return True
    return False


def _representative_urls(band: dict) -> list:
    """#626 part 2: the evidence URL(s) of the INCLUDED school(s) whose gross is CLOSEST to the band's
    winning value — the source of the value, not a losing/out-of-roster sample. A band's stored vintage
    must track its actual value's provenance: Dickinson's middle (426 — the mean of Dickinson MS's 426
    and the since-CLOSED Hagen JH's 425) must not inherit Hagen's `.../2016-17-HJH...` URL year just
    because that URL happens to parse a year. Empty when the band carries no per-school gross/URL signal
    (→ the caller falls through to current-year, never a stale non-representative URL)."""
    val = band.get("gross_minutes")
    schools = [s for s in band.get("schools", [])
               if s.get("gross") is not None and not s.get("excluded")]
    if val is None or not schools:
        return []
    best = min(abs(s["gross"] - val) for s in schools)
    urls, seen = [], set()
    for s in schools:
        if abs(s["gross"] - val) != best:
            continue
        ev = s.get("evidence")
        u = ev.get("url") if isinstance(ev, dict) else None
        if u and u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def resolve_schedule_year(band: dict, urls: Optional[list] = None) -> tuple:
    """(year, basis) for a band's `bell_schedules` KEY coordinate. Precedence (REQ-054 — never
    inferred from today's date):
      1. band-consensus school_year — the modal acceptable per-school reading;
      2. deterministic content year off the REPRESENTATIVE source URL (the value's source — #626 part 2);
      3. current_school_year() — the last-resort key coordinate (a page that stated no year is not
         evidence of staleness; the reader returns year=None for statutory rows regardless).
    COVID/malformed candidates are skipped at (1)/(2), never written."""
    years = [y for y in band_school_years(band) if is_acceptable_data_year(y)]
    if years:
        return Counter(years).most_common(1)[0][0], "band_consensus"
    # #626 part 2: derive the content year from the value's OWN source (the school whose gross is closest
    # to the band value), NOT every band URL — a non-winning/closed-school sample's stale URL must not
    # set the band's vintage. Fall back to the caller-passed `urls` only when the band has no gross
    # signal at all (e.g. the statutory-fallback call passes band={}).
    src_urls = _representative_urls(band) or [u for u in (urls or []) if u]
    if src_urls:
        cy = content_school_year(*src_urls)
        if cy and is_acceptable_data_year(cy):
            return cy, "content_url"
    return current_school_year(), "default_current"


# ----------------------------- band-times consistency (#627) -----------------------------
def _hhmm_to_min(t: Optional[str]) -> Optional[int]:
    """HH:MM -> minutes-since-midnight, or None if absent/unparseable."""
    if not t or ":" not in str(t):
        return None
    try:
        h, m = str(t).split(":")[:2]
        return int(h) * 60 + int(m)
    except (ValueError, TypeError):
        return None


def times_consistent(start: Optional[str], end: Optional[str], gross: Optional[int]) -> bool:
    """#627: are a band's representative (start,end) internally consistent with its gross?
    True when a time is absent/unparseable or gross is None (nothing to contradict), else span
    end−start must equal gross. A mean_tiebreak band stores a SYNTHETIC gross (average of two
    distinct-span schools) with one school's real times, so span != gross — writing those times
    fails Stage 9's bell_schedules cross-check (minutes ≤ end−start). plan_writes drops the times
    when this returns False, healing receipts frozen before the aggregate.py fix (new receipts
    already omit them). The original synthetic band stays intact in raw_import.receipt_band."""
    sm, em = _hhmm_to_min(start), _hhmm_to_min(end)
    if sm is None or em is None or gross is None:
        return True
    return (em - sm) == gross


# ----------------------------- provenance field builders -----------------------------
def collect_source_urls(band: dict) -> list:
    """Dedup of each included school's winning-evidence URL (order-stable)."""
    seen, out = set(), []
    for s in band.get("schools", []):
        ev = s.get("evidence")
        u = ev.get("url") if isinstance(ev, dict) else None
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def collect_schools_sampled(band: dict) -> list:
    """The fact-side per-school evidence list (names + council times + models + stated year) — the
    re-verify roster. Grade coverage rides in raw_import.band_grade_span, not here."""
    return [{"school": s.get("school"),
             "start_time": s.get("start_time"), "end_time": s.get("end_time"),
             "gross": s.get("gross"), "models": s.get("models"),
             "school_year": s.get("school_year")}
            for s in band.get("schools", [])]


def band_confidence(sampling: dict) -> str:
    """Bucket a band's confidence from its sampling sufficiency (coverage + plurality)."""
    cov = sampling.get("coverage")
    plur = sampling.get("plurality_share")
    if cov is not None and cov >= 0.5 and (plur is None or plur >= 0.6):
        return "high"
    if cov is not None and cov >= 0.25:
        return "medium"
    return "low"


def band_grade_span(source: dict, band: str) -> dict:
    """LEA-level grade coverage of the band's SERVING roster schools — the grade->band substrate the
    follow-up per-grade projection reads. Read from `source`'s slot_projection (span-aware,
    merged-shape-correct: a K-8 correctly appears in both elementary and middle).

    `source` is the LIVE closing argument at incorporation time, NOT the frozen receipt: the roster is
    explicitly UNSIGNED (excluded from the gate@8 fingerprint — roster drift must never stale an
    approval; the rule is "derive from ccd_sch live, never freeze", Ian 2026-07-14), and pre-#499
    frozen receipts carry no slot_projection at all, so freezing it would leave every existing
    approval's span empty. Recorded via `basis` so the projection and any auditor know it is
    live-at-incorporation, not what was signed."""
    slots = (((source.get("slot_projection") or {}).get(band) or {}).get("slots")) or []
    spans = [{"school_id": s.get("school_id"), "gslo": s.get("gslo"), "gshi": s.get("gshi"),
              "roster_source": s.get("roster_source")}
             for s in slots if s.get("gslo") or s.get("gshi")]
    return {"slot_spans": spans, "source": "slot_projection",
            "basis": "unhashed (live roster at incorporation)"}


def council_source_description(band: str, sampling: dict, agg: Optional[str]) -> str:
    s = sampling or {}
    return (f"Stage-9 council extraction; band={band}; "
            f"{s.get('n_sampled')}/{s.get('n_total')} schools (coverage={s.get('coverage')}); "
            f"agg={agg}")


def council_notes(band: str, sampling: dict, agg: Optional[str], year_basis: str) -> str:
    s = sampling or {}
    return json.dumps({"stage": 9, "consensus_outcome": agg, "year_basis": year_basis,
                       "plurality_share": s.get("plurality_share"), "coverage": s.get("coverage")},
                      sort_keys=True)


def council_raw_import(receipt: dict, band: str, band_dict: dict, *, fingerprint, approval_id,
                       year_basis: str, actor: str, grade_span_source: dict = None) -> dict:
    """The #95 re-verify bundle: enough to re-verify months later without re-crawling. The signed
    fields come from the frozen `receipt`; `band_grade_span` reads the LIVE roster (`grade_span_source`
    if given, else the receipt as a fallback)."""
    return {"stage": 9, "facts_fingerprint": fingerprint, "approval_id": approval_id,
            "receipt_band": band_dict, "provenance": receipt.get("provenance"),
            "sampling": band_dict.get("sampling"), "year_basis": year_basis,
            "band_grade_span": band_grade_span(grade_span_source or receipt, band),
            "incorporated_at": utcnow(), "actor": actor}


# ----------------------------- statutory fallback (#94 / REQ-049) -----------------------------
def statutory_reason(receipt: dict, band: str) -> str:
    """Why a claimed band landed as statutory_fallback, derived from the frozen negative space."""
    ns = receipt.get("negative_space", {}) or {}
    rec_bands = {r.get("band") for r in (ns.get("recoverable_bands") or [])
                 if isinstance(r, dict)}
    if band in rec_bands:
        return "recoverable_sibling_facts"
    return "no_accepted_facts"


def statutory_source_description(band: str, reason: str) -> str:
    return (f"Stage-9 statutory fallback; band={band}; reason={reason}; "
            f"NOT an enriched measurement")


def statutory_notes(band: str, reason: str) -> str:
    return json.dumps({"stage": 9, "fallback": True, "reason": reason}, sort_keys=True)


def statutory_raw_import(receipt: dict, band: str, *, fingerprint, approval_id, reason: str,
                         actor: str, grade_span_source: dict = None) -> dict:
    ns = receipt.get("negative_space", {}) or {}
    slice_ = {k: ns.get(k) for k in
              ("unsatisfied_bands", "unheard_slots", "recoverable_bands", "coverage_gaps")
              if ns.get(k)}
    return {"stage": 9, "facts_fingerprint": fingerprint, "approval_id": approval_id,
            "fallback": True, "reason": reason,
            "band_grade_span": band_grade_span(grade_span_source or receipt, band),
            "negative_space": slice_, "incorporated_at": utcnow(), "actor": actor}
