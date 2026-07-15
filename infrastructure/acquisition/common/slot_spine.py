"""#499 — the roster-template / school-slot spine (REQ-144 projection, REQ-145 attribution).

The slot projection: each band's LIVE roster (band_rosters_for_district's slot_recs, derived from
ccd_sch — never frozen) crossed with the band's accepted facts, so coverage gaps are structurally
visible (unfilled slots), not post-hoc count arithmetic. PURE — no DB, no disk; the gate@8 approval
receipt snapshots the projection at sign-off, which is where reproducibility lives.

The join axis is `norm_school` on BOTH sides (facts are already keyed on it by the Stage-8 merge;
roster slots carry raw NCES SCH_NAME) — one home, school_match.py, same as every detector.

States: a slot is `filled` (exactly one fact confidently matches) or `unfilled`. A fact whose key
collides with ≥2 roster slots attaches to each candidate as `ambiguous` and fills NONE — unless the
Stage-2 discovery-intent prior (REQ-145: the fact's URL was discovered by querying for exactly one
of the candidates) or a human disposition resolves it. A fact matching NO slot is an
`unmatched-extra`, a FIRST-CLASS state: the NCES roster can be wrong — the template is an overlay
with an escape hatch (`confirm_extra`), never a cage (#237's lesson: detection is reliable,
resolution isn't).

Resolution precedence (weight, never override): human disposition > exact 1:1 name match >
intent-tie-broken ambiguity > ambiguous (waits for the human). Intent alone NEVER creates a
match — a district-wide page discovered via one school's query legitimately covers many schools.
"""
from __future__ import annotations

from infrastructure.acquisition.common.school_match import _base, norm_school

# disposition verbs (REQ-145) — the console posts these; validation lives at the endpoint
DISPOSITIONS = ("assign", "reject", "confirm_extra")


def _fact_entry(f):
    """A facts_by_band entry is {'school': name, 'rec_key': rk} (or a bare name, tolerated)."""
    if isinstance(f, dict):
        return f.get("school", ""), f.get("rec_key")
    return f, None


def project_slots(band_rosters, facts_by_band, *, assignments=None, intent_by_reckey=None):
    """Cross each band's roster slots with its accepted fact names. PURE.

    Inputs:
      band_rosters   : SS.band_rosters_for_district(...) output — each band dict must carry
                       `slot_recs` ([{school_id, name, is_charter, gslo, gshi, level,
                       effective_band, source}]). None/missing-band tolerated (the caller's
                       clean-LEVEL fallback story is unchanged).
      facts_by_band  : {band: [{"school": display_name, "rec_key": rk} | display_name, ...]} — the
                       band's INCLUDED facts (mode-voting rows + human adds; #257-excluded facts
                       don't fill slots).
      assignments    : REQ-145 — the district's standing SlotAssignment rows, list of
                       {band, roster_school_id, norm_school_fact, disposition, school, reason,
                       actor, created_at}. assign binds fact→slot; reject removes a candidate
                       (a collapse to one survivor fills it); confirm_extra turns an extra into a
                       human-confirmed slot (denominator +1, roster_source "human_confirmed").
      intent_by_reckey : REQ-145 — {rec_key: [intended school name, ...]} from Stage-2 discovery
                       (record.intended_schools_json): which roster school(s) each URL was
                       discovered FOR. Tie-breaker ONLY. Intent names are Stage-1 roster verbatim,
                       so RAW-name equality (_base) distinguishes colliding candidates — the shared
                       norm key, being the very thing that collided, cannot.

    Returns {band: {"slots": [...], "extras": [...], ["orphaned_dispositions": [...]],
                    "stats": {...}}} for every band with roster slots, facts, or dispositions.
    """
    out = {}
    rosters = band_rosters or {}
    asg = list(assignments or [])
    intent = intent_by_reckey or {}
    bands = [b for b in rosters if not b.startswith("_")]
    for b in list(facts_by_band or {}) + [a.get("band") for a in asg]:
        if b and b not in bands:
            bands.append(b)

    for band in bands:
        recs = (rosters.get(band) or {}).get("slot_recs") or []
        band_asg = [a for a in asg if a.get("band") == band]
        assign_of = {(a.get("roster_school_id") or "", a["norm_school_fact"]): a
                     for a in band_asg if a.get("disposition") == "assign"}
        reject_of = {(a.get("roster_school_id") or "", a["norm_school_fact"]): a
                     for a in band_asg if a.get("disposition") == "reject"}
        confirm_of = {a["norm_school_fact"]: a
                      for a in band_asg if a.get("disposition") == "confirm_extra"}

        slots, by_key, by_id = [], {}, {}
        for rc in recs:
            row = {"school_id": rc.get("school_id"), "roster_school": rc.get("name", ""),
                   "norm_key": norm_school(rc.get("name", "")),
                   "gslo": rc.get("gslo"), "gshi": rc.get("gshi"),
                   "is_charter": rc.get("is_charter", ""),
                   "roster_source": rc.get("source"),
                   "slot_state": "unfilled", "match": None}
            slots.append(row)
            by_key.setdefault(row["norm_key"], []).append(row)
            by_id[row["school_id"]] = row

        def _fill(slot, key, name, basis, disposition=None):
            slot["slot_state"] = "filled"
            slot["match"] = {"norm_school_fact": key, "school_display": name,
                             "confidence": "matched", "basis": basis}
            if disposition:
                slot["match"]["disposition"] = {
                    "kind": disposition["disposition"], "reason": disposition.get("reason"),
                    "actor": disposition.get("actor"), "at": disposition.get("created_at")}

        extras, n_ambiguous = [], 0
        for f in (facts_by_band or {}).get(band, []):
            name, rk = _fact_entry(f)
            key = norm_school(name)

            # 1) a human ASSIGN wins outright — bind the fact to the named slot wherever the name
            #    match would have landed (ambiguous, extra, or a different exact match).
            bound = next((by_id[sid] for (sid, fk) in assign_of
                          if fk == key and sid in by_id), None)
            if bound is not None and not bound["match"]:
                _fill(bound, key, name, ["disposition"], assign_of[(bound["school_id"], key)])
                continue

            # 2) confirm_extra: the human said this fact is a REAL school NCES missed — it becomes
            #    a human-confirmed slot (denominator +1), not an extra and not a roster fill.
            if key in confirm_of:
                a = confirm_of[key]
                row = {"school_id": "", "roster_school": a.get("school") or name,
                       "norm_key": key, "gslo": None, "gshi": None, "is_charter": "",
                       "roster_source": "human_confirmed",
                       "slot_state": "unfilled", "match": None}
                _fill(row, key, name, ["disposition"], a)
                slots.append(row)
                by_key.setdefault(key, []).append(row)
                continue

            # 3) a human REJECT removes that candidate before the count decides anything
            hits = [s for s in by_key.get(key, [])
                    if (s["school_id"] or "", key) not in reject_of]
            if len(hits) == 1:
                s = hits[0]
                if s["match"]:      # two facts on one slot can't happen post-merge; defensive
                    continue
                basis = ["exact_name"]
                if len(by_key.get(key, [])) > 1:
                    basis.append("disposition")                     # a reject broke the tie
                _fill(s, key, name, basis)
            elif len(hits) > 1:
                # 4) Stage-2 discovery-intent tie-break: exactly-one rule — zero or several intent
                #    hits keep the ambiguity (weight, never override).
                intent_base = {_base(n) for n in intent.get(rk, [])}
                by_intent = [s for s in hits if _base(s["roster_school"]) in intent_base]
                if len(by_intent) == 1 and not by_intent[0]["match"]:
                    _fill(by_intent[0], key, name, ["exact_name", "discovery_intent"])
                    continue
                n_ambiguous += 1
                cands = [{"school_id": s["school_id"], "roster_school": s["roster_school"]}
                         for s in hits]
                for s in hits:
                    s["match"] = {"norm_school_fact": key, "school_display": name,
                                  "confidence": "ambiguous", "basis": ["exact_name"],
                                  "candidates": cands}
            else:
                extras.append({"norm_school_fact": key, "school_display": name,
                               "confidence": "unmatched_extra",
                               "intent_schools": intent.get(rk, [])})

        # Orphan surfacing (REQ-145, never auto-deleted): an assign/reject whose slot vanished
        # from the live roster (school closed / reclassified out), and a confirm_extra whose
        # school NOW matches a real roster slot (NCES caught up — retiring it avoids a
        # double-counted denominator). Human retirement is the disposition; this only surfaces.
        orphaned = []
        for a in band_asg:
            sid = a.get("roster_school_id") or ""
            base = {k: a.get(k) for k in ("roster_school_id", "norm_school_fact",
                                          "school", "disposition", "reason")}
            if a["disposition"] in ("assign", "reject") and sid and sid not in by_id:
                orphaned.append({**base, "kind": "slot_gone_from_roster"})
            if a["disposition"] == "confirm_extra" and a.get("norm_school_fact") in {
                    s["norm_key"] for s in slots if s["roster_source"] != "human_confirmed"}:
                orphaned.append({**base, "kind": "extra_now_in_roster"})

        n_filled = sum(1 for s in slots if s["slot_state"] == "filled")
        band_out = {
            "slots": slots,
            "extras": extras,
            "stats": {"n_slots": len(slots), "n_filled": n_filled,
                      "n_unfilled": len(slots) - n_filled,
                      "n_extras": len(extras), "n_ambiguous": n_ambiguous,
                      "slot_coverage": round(n_filled / len(slots), 3) if slots else None},
        }
        if orphaned:
            band_out["orphaned_dispositions"] = orphaned
        out[band] = band_out
    return out


def roster_drift(live_slots_by_band, receipt_slots_by_band):
    """Band-membership drift between the LIVE roster and the last APPROVED receipt's slot list —
    schools closing, opening, and reclassifying over the project's long horizon. PURE.

    The baseline is deliberately the last gate@8 receipt (the last roster a human signed), not the
    prior CCD vintage: the receipt chain is the longitudinal record (derive-from-receipts). Keyed
    on NCESSCH school_id — immune to renames; human-confirmed slots (school_id "") are excluded
    (they are dispositions, not NCES membership). Returns None when the receipt carries no slots
    (a pre-#499 approval — nothing signed to diff against); {} when there is no drift.

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
