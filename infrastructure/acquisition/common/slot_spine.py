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

Band-grain facts (REQ-146): a blanket statement ("All Elementary Schools", council
applies_to=="multiple") attaches to the BAND NODE, votes ONCE in the mode (never per projected
slot — the Santa Fe inflation #253 fixed), and PROJECTS onto the band's unfilled slots
(slot_state "projected": covered by the statement, not individually observed). A conjunction
("Milagro and Ortiz Schools") whose campuses resolve to roster slots FILLS those named slots
(basis "conjunction"). Slot conflicts (a direct fact disagreeing with the blanket) resolve by the
fixed ladder sufficiency → hub-exception → vintage — rendered ADVICE only; both facts keep their
votes until a human disposes (ramp-up posture).
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


def project_slots(band_rosters, facts_by_band, *, assignments=None, intent_by_reckey=None,
                  band_facts=None):
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
      band_facts     : REQ-146 — {band: {"norm_school_fact", "school_display", "kind",
                       "campuses": [...]}} for the band's band-grain fact (group_descriptor /
                       council scope / conjunction). The band-fact's own name is NOT an extra
                       (it is band-grain, not an unmatched school); a conjunction's resolved
                       campuses FILL their slots (basis "conjunction"); a blanket kind projects
                       onto every remaining unfilled slot (slot_state "projected").
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
    bfacts = band_facts or {}
    bands = [b for b in rosters if not b.startswith("_")]
    for b in list(facts_by_band or {}) + [a.get("band") for a in asg]:
        if b and b not in bands:
            bands.append(b)
    # Every school_id anywhere in the district's roster, cross-band — lets orphan surfacing say
    # "reclassified to another band" vs "gone from the district entirely" (review round 2).
    all_district_ids = {rc.get("school_id")
                        for b in bands for rc in (rosters.get(b) or {}).get("slot_recs") or []
                        if rc.get("school_id")}

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

        bf = bfacts.get(band)
        extras, n_ambiguous, fact_keys_seen = [], 0, set()
        # Human ASSIGNs are processed FIRST (epic-#499 review round): "human disposition wins
        # outright" must not depend on fact iteration order — without this, a fact that
        # exact-name-fills a slot earlier in the loop silently shadows a later fact's assign
        # to that same slot. Stable sort: assigned facts keep their relative order, then the rest.
        # ONE fk→sid index serves both the sort key and the loop's bind lookup (review round 2:
        # the earlier shape scanned assign_of per fact twice — once for the key, once for bound).
        band_fact_rows = (facts_by_band or {}).get(band, [])
        assign_slot_by_key = {}
        for (sid_, fk_) in assign_of:
            if fk_ not in assign_slot_by_key and sid_ in by_id:
                assign_slot_by_key[fk_] = sid_
        if assign_slot_by_key:
            band_fact_rows = sorted(
                band_fact_rows,
                key=lambda f: 0 if norm_school(_fact_entry(f)[0]) in assign_slot_by_key else 1)
        for f in band_fact_rows:
            name, rk = _fact_entry(f)
            key = norm_school(name)
            fact_keys_seen.add(key)

            # REQ-146: the band-grain fact is not a school — it never fills a slot by its own
            # name and never lands in extras; its campuses/projection are handled below.
            if bf and key == bf.get("norm_school_fact"):
                continue

            # 1) a human ASSIGN wins outright — bind the fact to the named slot wherever the name
            #    match would have landed (ambiguous, extra, or a different exact match).
            _sid = assign_slot_by_key.get(key)
            bound = by_id.get(_sid) if _sid else None
            if bound is not None and not bound["match"]:
                _fill(bound, key, name, ["disposition"], assign_of[(bound["school_id"], key)])
                continue

            # 2) confirm_extra: the human said this fact is a REAL school NCES missed — it becomes
            #    a human-confirmed slot (denominator +1), not an extra and not a roster fill.
            if key in confirm_of:
                # Review round 2: the SAME key twice (a council fact + a #474 hand-add for the
                # one confirmed school) must not mint a SECOND human-confirmed slot — that
                # double-counts the denominator. First fact creates it; siblings are duplicates.
                if any(r["roster_source"] == "human_confirmed" and r["norm_key"] == key
                       for r in by_key.get(key, [])):
                    continue
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
                if s["match"]:
                    if s["match"].get("norm_school_fact") != key:
                        # A DIFFERENT key already holds the slot (a human assign displaced this
                        # name match) — the displaced fact stays VISIBLE as an extra, never
                        # silently dropped (epic-#499 review round).
                        extras.append({"norm_school_fact": key, "school_display": name,
                                       "confidence": "unmatched_extra",
                                       "intent_schools": intent.get(rk, []),
                                       "displaced_by": s["match"].get("norm_school_fact")})
                    else:
                        # The SAME key twice CAN happen despite the merge: merge_fact_runs
                        # dedupes council rows only — a #474 hand-add duplicating a still-
                        # accepted council fact arrives as a second row (review round 2; the
                        # endpoint now 409s new ones, but standing rows must surface, not
                        # vanish — the projection is an audit view, never a cage).
                        extras.append({"norm_school_fact": key, "school_display": name,
                                       "confidence": "duplicate_vote",
                                       "intent_schools": intent.get(rk, []),
                                       "duplicate_of_slot": s["school_id"]})
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
                # Same defensive guard as the single-hit branch (epic-#499 review round): a
                # caller whose facts aren't norm-key-deduped could send two facts colliding on
                # this key — never overwrite a slot's existing match or double-count the band.
                open_hits = [s for s in hits if not s["match"]]
                if not open_hits:
                    continue
                n_ambiguous += 1
                cands = [{"school_id": s["school_id"], "roster_school": s["roster_school"]}
                         for s in hits]
                for s in open_hits:
                    s["match"] = {"norm_school_fact": key, "school_display": name,
                                  "confidence": "ambiguous", "basis": ["exact_name"],
                                  "candidates": cands}
            else:
                extras.append({"norm_school_fact": key, "school_display": name,
                               "confidence": "unmatched_extra",
                               "intent_schools": intent.get(rk, [])})

        # REQ-146/148: a band fact's campuses fill their named slots — one page stating times
        # for N schools genuinely is N schools' schedules (the fact still votes ONCE in the mode;
        # slot fill is coverage truth, not a vote). Matching is on the NORM key: detector campuses
        # are roster-verbatim, but v4 council campus_names are page-verbatim SHORTHAND ("Milagro"
        # for "Milagro Middle School" — the live Santa Fe reading, 2026-07-15), which only the
        # level-word-stripping key can join. A campus key colliding with >1 slot fills NOTHING
        # (the same no-guess rule as ambiguous facts).
        if bf and bf.get("campuses"):
            for c in bf["campuses"]:
                ck = norm_school(c)
                hits_c = [s_ for s_ in by_key.get(ck, [])
                          if s_["slot_state"] == "unfilled" and not s_["match"]]
                if len(hits_c) == 1 and len(by_key.get(ck, [])) == 1:
                    s_ = hits_c[0]
                    s_["slot_state"] = "filled"
                    s_["match"] = {"norm_school_fact": bf["norm_school_fact"],
                                   "school_display": bf.get("school_display", ""),
                                   "confidence": "matched", "basis": ["conjunction"]}

        # REQ-146: a BLANKET band fact (group descriptor / council scope) projects onto every slot
        # still unheard — a visible third state between filled and unfilled: covered by the
        # statement, not individually observed. Ambiguous slots stay ambiguous (they have a
        # direct fact waiting on a human, which is stronger information than a blanket).
        n_projected = 0
        if bf and bf.get("kind") in ("group_descriptor", "council_scope") :
            for s_ in slots:
                if s_["slot_state"] == "unfilled" and not s_["match"]:
                    s_["slot_state"] = "projected"
                    s_["projected_by"] = bf["norm_school_fact"]
                    n_projected += 1

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
                # Review round 2: say WHICH gone. Still elsewhere in the district roster ⇒
                # reclassified to another band; absent everywhere ⇒ closed — or an id that was
                # never valid (pre-validation rows, restored backups: the live view can't tell
                # those apart from a closure, so the copy must state both hypotheses).
                orphaned.append({**base, "kind": "slot_gone_from_roster",
                                 "still_in_district_roster": sid in all_district_ids})
            # An ASSIGN whose slot ended up carrying a DIFFERENT fact (two standing assigns on
            # one slot — the unique index permits it, norm_school_fact is in the key): the
            # shadowed disposition must be VISIBLE for human retirement, never silently inert
            # (epic-#499 review round).
            if a["disposition"] == "assign" and sid in by_id:
                m = by_id[sid].get("match")
                if m and m.get("norm_school_fact") != a.get("norm_school_fact"):
                    orphaned.append({**base, "kind": "assign_shadowed",
                                     "slot_carries": m.get("norm_school_fact")})
                # Review round 2: an assign whose target fact never appeared in this band's
                # included facts (excluded via #257, rejected, superseded) binds NOTHING — the
                # slot sits open and the disposition is inert. Without this flag the human has
                # no signal their standing answer stopped doing anything.
                elif a.get("norm_school_fact") not in fact_keys_seen:
                    orphaned.append({**base, "kind": "assign_fact_absent"})
            if a["disposition"] == "confirm_extra" and a.get("norm_school_fact") in {
                    s["norm_key"] for s in slots if s["roster_source"] != "human_confirmed"}:
                orphaned.append({**base, "kind": "extra_now_in_roster"})

        n_filled = sum(1 for s in slots if s["slot_state"] == "filled")
        band_out = {
            "slots": slots,
            "extras": extras,
            "stats": {"n_slots": len(slots), "n_filled": n_filled,
                      "n_projected": n_projected,
                      "n_unfilled": len(slots) - n_filled - n_projected,
                      "n_extras": len(extras), "n_ambiguous": n_ambiguous,
                      "slot_coverage": round(n_filled / len(slots), 3) if slots else None},
        }
        if orphaned:
            band_out["orphaned_dispositions"] = orphaned
        out[band] = band_out
    return out


# REQ-149 (#90 pull-in, REQ-109 anchor): the per-band SATISFIED signal, in slot vocabulary.
# Thresholds approved as starting values (Ian, 2026-07-15, plan review) and carried in every
# receipt so they are auditable and tunable without staleness.
SATISFIED_MIN_COVERAGE = 0.60
SATISFIED_MIN_PLURALITY = 0.60
SATISFIED_MIN_SAMPLED = 3


def band_satisfied(stats, band_fact, conflicts, *, min_coverage=SATISFIED_MIN_COVERAGE,
                   min_plurality=SATISFIED_MIN_PLURALITY, min_sampled=SATISFIED_MIN_SAMPLED):
    """Is this band's determination CONFIDENT enough to stop pursuing? PURE. Satisfied ⇔
      (a) slot coverage — (n_filled + n_projected) / n_slots >= min_coverage ("we heard from, or
          a blanket covers, most of the roster"); OR
      (b) mode concentration — n_sampled >= min_sampled AND plurality_share >= min_plurality
          ("the mode is reliable regardless of roster reach"); OR
      (c) a clean blanket — a band fact present with NO unresolved slot conflicts.
    Governing principle (Ian, #253/#499): confident band-level declarations, not per-school
    accuracy. Consumed as an ADDITIONAL follow-up suppressor beside the covered_bands hard gate
    (never a replacement — Ian, 2026-07-15). Returns {satisfied, basis, thresholds}.

    stats: {n_slots, n_filled, n_projected, n_sampled, plurality_share} — slot stats merged with
    the band's sampling context (n_slots may be 0/absent when the CCD roster is unavailable —
    arm (a) simply cannot fire; the honest degradation).
    conflicts: the band's slot_conflicts rows (rung/leans) — any with rung 'unresolved' blocks (c)."""
    st = stats or {}
    thresholds = {"min_coverage": min_coverage, "min_plurality": min_plurality,
                  "min_sampled": min_sampled}
    n_slots = st.get("n_slots") or 0
    if n_slots:
        cov = ((st.get("n_filled") or 0) + (st.get("n_projected") or 0)) / n_slots
        if cov >= min_coverage:
            return {"satisfied": True, "basis": "coverage", "thresholds": thresholds}
    n, plu = st.get("n_sampled") or 0, st.get("plurality_share")
    if n >= min_sampled and plu is not None and plu >= min_plurality:
        return {"satisfied": True, "basis": "plurality", "thresholds": thresholds}
    if band_fact and not any(c.get("rung") == "unresolved" for c in (conflicts or [])):
        return {"satisfied": True, "basis": "band_fact", "thresholds": thresholds}
    return {"satisfied": False, "basis": None, "thresholds": thresholds}


# REQ-146: the conflict-resolution ladder (Ian, 2026-07-14, recorded on #253/#499) — FIXED rung
# order, deterministic, and ADVICE only: `leans` is rendered for the reviewer; both facts keep
# their votes until a human disposes (nothing auto-rejects, ramp-up posture).
CONFLICT_MIN_SAMPLED = 3
CONFLICT_MIN_PLURALITY = 0.6


def resolve_slot_conflict(direct, band_fact, band_stats, *, exceptions=None,
                          min_sampled=CONFLICT_MIN_SAMPLED,
                          min_plurality=CONFLICT_MIN_PLURALITY):
    """One slot's direct fact vs the band's blanket statement, gross disagreeing. PURE.

    Rungs, in order (the first that can decide, decides):
      (a) sample_sufficiency — the band already holds a reliable mode (n_sampled >= min_sampled
          AND plurality >= min_plurality): the conflict resolves as exception-vs-outlier against
          a trustworthy mode; lean toward whichever side SITS ON the mode. Populous bands live
          here; bands with <= 3 schools are where the real determination problem lives.
      (b) hub_exception — the blanket's own source names this school as an exception (a K-8/K-12
          with different hours). `exceptions` is that list (v4 campus/exception readings feed it;
          empty until then — the rung passes through, never guesses).
      (c) vintage — #254's machinery: a KNOWN school year on one side only, or a newer year,
          leans that side; unknown-vs-unknown decides nothing.
    Undecided everywhere -> rung "unresolved", leans None (the honest null: collect more data).

    direct     : {"gross", "school", "school_year"} — the slot's directly-observed fact.
    band_fact  : {"gross", "school_year", ...} — the blanket.
    band_stats : {"n_sampled", "plurality_share", "gross_minutes"} — the band's mode context.
    Returns {"rung", "leans": "direct"|"band_fact"|None, "note"}."""
    st = band_stats or {}
    n, plu, mode = st.get("n_sampled") or 0, st.get("plurality_share"), st.get("gross_minutes")
    if n >= min_sampled and plu is not None and plu >= min_plurality and mode is not None:
        if direct.get("gross") == mode and band_fact.get("gross") != mode:
            return {"rung": "sample_sufficiency", "leans": "direct",
                    "note": f"band mode {mode} is reliable (n={n}, plurality {plu:.0%}) and the "
                            f"direct reading sits on it"}
        if band_fact.get("gross") == mode and direct.get("gross") != mode:
            return {"rung": "sample_sufficiency", "leans": "band_fact",
                    "note": f"band mode {mode} is reliable (n={n}, plurality {plu:.0%}) and the "
                            f"blanket sits on it — the direct reading is the outlier"}
    exc = { _base(e) for e in (exceptions or []) }
    if exc and _base(direct.get("school", "")) in exc:
        return {"rung": "hub_exception", "leans": "direct",
                "note": "the blanket's own source names this school as an exception"}
    dy, by = direct.get("school_year"), band_fact.get("school_year")
    if dy and by and dy != by:
        newer = "direct" if dy > by else "band_fact"
        return {"rung": "vintage", "leans": newer,
                "note": f"school years differ ({dy} vs {by}) — the newer reading leans"}
    if bool(dy) != bool(by):
        return {"rung": "vintage", "leans": "direct" if dy else "band_fact",
                "note": "only one side states a school year — the dated reading leans"}
    return {"rung": "unresolved", "leans": None,
            "note": "no rung decides — collect more data (small band, no exception list, no "
                    "year signal)"}


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
