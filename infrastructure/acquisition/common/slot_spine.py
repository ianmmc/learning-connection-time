"""#499 — the roster-template / school-slot spine (REQ-144).

The slot projection: each band's LIVE roster (band_rosters_for_district's slot_recs, derived from
ccd_sch — never frozen) crossed with the band's accepted facts, so coverage gaps are structurally
visible (unfilled slots), not post-hoc count arithmetic. PURE — no DB, no disk; the gate@8 approval
receipt snapshots the projection at sign-off, which is where reproducibility lives.

The join axis is `norm_school` on BOTH sides (facts are already keyed on it by the Stage-8 merge;
roster slots carry raw NCES SCH_NAME) — one home, school_match.py, same as every detector.

States (v1, read-only): a slot is `filled` (exactly one fact matches it), or `unfilled`. A fact
whose key collides with ≥2 roster slots attaches to each candidate as an `ambiguous` match WITHOUT
filling any of them (not individually observed — the ramp-up posture: confident matches auto-assign,
ambiguity waits for a human disposition, PR-B). A fact matching NO slot is an `unmatched-extra`,
a FIRST-CLASS state: the NCES roster can be wrong — the template is an overlay with an escape
hatch, never a cage (#237's lesson: detection is reliable, resolution isn't).
"""
from __future__ import annotations

from infrastructure.acquisition.common.school_match import norm_school


def project_slots(band_rosters, facts_by_band):
    """Cross each band's roster slots with its accepted fact names. PURE.

    Inputs:
      band_rosters  : SS.band_rosters_for_district(...) output — each band dict must carry
                      `slot_recs` ([{school_id, name, gslo, gshi, level, effective_band, source}]).
                      None/missing-band tolerated (returns {} / skips — the caller's clean-LEVEL
                      fallback story is unchanged).
      facts_by_band : {band: [school display name, ...]} — the band's INCLUDED facts (mode-voting
                      rows + human adds; excluded facts don't fill slots — the human struck them
                      from the band, and they are already surfaced via #257).

    Returns {band: {"slots": [...], "extras": [...], "stats": {...}}} for every band that has
    roster slots OR facts. Slot rows carry the roster identity (school_id — the NCESSCH key drift
    and receipts compare on) + the match; see the module docstring for the state vocabulary.
    """
    out = {}
    rosters = band_rosters or {}
    bands = [b for b in rosters if not b.startswith("_")]
    for b in (facts_by_band or {}):
        if b not in bands:
            bands.append(b)

    for band in bands:
        recs = (rosters.get(band) or {}).get("slot_recs") or []
        slots = []
        by_key = {}  # norm key -> [slot row, ...] (collisions are real: "Washington ES"/"Washington Academy")
        for rc in recs:
            row = {"school_id": rc.get("school_id"), "roster_school": rc.get("name", ""),
                   "norm_key": norm_school(rc.get("name", "")),
                   "gslo": rc.get("gslo"), "gshi": rc.get("gshi"),
                   "is_charter": rc.get("is_charter", ""),
                   "roster_source": rc.get("source"),
                   "slot_state": "unfilled", "match": None}
            slots.append(row)
            by_key.setdefault(row["norm_key"], []).append(row)

        extras, n_ambiguous = [], 0
        for name in (facts_by_band or {}).get(band, []):
            key = norm_school(name)
            hits = by_key.get(key, [])
            if len(hits) == 1:
                s = hits[0]
                if s["match"]:  # two facts on one slot can't happen post-merge; defensive
                    continue
                s["slot_state"] = "filled"
                s["match"] = {"norm_school_fact": key, "school_display": name,
                              "confidence": "matched", "basis": ["exact_name"]}
            elif len(hits) > 1:
                # A collision: the fact is not confidently any one slot — attach as ambiguous to
                # every candidate, fill NONE (PR-B's disposition/intent tie-break resolves it).
                n_ambiguous += 1
                cands = [s["norm_key"] for s in hits]
                for s in hits:
                    s["match"] = {"norm_school_fact": key, "school_display": name,
                                  "confidence": "ambiguous", "basis": ["exact_name"],
                                  "candidates": cands}
            else:
                extras.append({"norm_school_fact": key, "school_display": name,
                               "confidence": "unmatched_extra"})

        n_filled = sum(1 for s in slots if s["slot_state"] == "filled")
        out[band] = {
            "slots": slots,
            "extras": extras,
            "stats": {"n_slots": len(slots), "n_filled": n_filled,
                      "n_unfilled": len(slots) - n_filled,
                      "n_extras": len(extras), "n_ambiguous": n_ambiguous,
                      "slot_coverage": round(n_filled / len(slots), 3) if slots else None},
        }
    return out


def roster_drift(live_slots_by_band, receipt_slots_by_band):
    """Band-membership drift between the LIVE roster and the last APPROVED receipt's slot list —
    schools closing, opening, and reclassifying over the project's long horizon. PURE.

    The baseline is deliberately the last gate@8 receipt (the last roster a human signed), not the
    prior CCD vintage: the receipt chain is the longitudinal record (derive-from-receipts). Keyed
    on NCESSCH school_id — immune to renames. Returns None when the receipt carries no slots (a
    pre-#499 approval — nothing signed to diff against); {} when there is no drift.

    Shape: {"added": [{school_id, name, bands}], "removed": [...],
            "band_moved": [{school_id, name, from, to}]} — `bands`/`from`/`to` are sorted lists
    (a school legitimately serves several bands; drift is a change in that SET)."""
    def _index(slots_by_band):
        idx = {}
        for band, slots in (slots_by_band or {}).items():
            for s in slots or []:
                sid = s.get("school_id")
                if not sid:
                    continue
                e = idx.setdefault(sid, {"name": s.get("roster_school", ""), "bands": set()})
                e["bands"].add(band)
        return idx

    receipt = _index(receipt_slots_by_band)
    if not receipt:
        return None
    live = _index(live_slots_by_band)

    drift = {"added": [], "removed": [], "band_moved": []}
    for sid in sorted(live.keys() - receipt.keys()):
        drift["added"].append({"school_id": sid, "name": live[sid]["name"],
                               "bands": sorted(live[sid]["bands"])})
    for sid in sorted(receipt.keys() - live.keys()):
        drift["removed"].append({"school_id": sid, "name": receipt[sid]["name"],
                                 "bands": sorted(receipt[sid]["bands"])})
    for sid in sorted(live.keys() & receipt.keys()):
        if live[sid]["bands"] != receipt[sid]["bands"]:
            drift["band_moved"].append({"school_id": sid, "name": live[sid]["name"],
                                        "from": sorted(receipt[sid]["bands"]),
                                        "to": sorted(live[sid]["bands"])})
    return drift if any(drift.values()) else {}
