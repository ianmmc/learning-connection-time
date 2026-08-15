"""gate@8 RE-REVIEW — a written district that gained new evidence (#713, epic #92).

The third gate@8 arrow, beside #682 (approve→write) and #689 (send-back→route). Fairbanks `0200600`
surfaced it: incorporated 2026-07-29 off a one-rep dispatch, re-dispatched on 2026-08-03 after #691
landed, **26 accepted facts for $0.004** — and then nothing happened. Its `stage8_approval` row was
still July's, its `district_grade_minutes` still July's write, and **no surface said so**. The
narrowed-dispatch audit tells you which districts to re-dispatch; the pipeline had nowhere to put the
answer when one came back richer. That is #662's shape one layer up: *written is not current*.

## The design questions, settled

* **New row or new disposition?** A **new `stage8_approval` row** — the table is precious and
  append-only, and `latest_decision` already means "the live decision". No schema change, and every
  prior decision stays readable. (Nothing here writes; the existing decide endpoint does it.)
* **What triggers a re-review?** NOT "any new fact" — measured, that is a false alarm generator:
  Fairbanks' 26 new facts moved **nothing** (identical modes, identical school sets), because
  `merge_fact_runs` is earliest-run-wins, so a re-extraction of the SAME schools cannot change the
  picture. The honest trigger is the one the codebase already owns: **REQ-147 staleness** — re-hash
  the frozen receipt under today's `fingerprint()` and compare to the live hash. `needs_rereview` is
  exactly `decided AND is_stale`.
* **Why then a cheap pre-filter?** Because the honest trigger costs a full closing-argument assembly
  per district (~28 ms × 53 decided districts = 1.5 s), and the gate@8 queue answers in ~27 ms.
  `CHANGED_SINCE_DECISION_SQL` is a SOUND SUPERSET, in one round trip (~3 ms warm): the fingerprint
  is derived from accepted facts + the four human-judgment tables, so nothing can move the picture
  without a row newer than the decision in one of them. Measured live 2026-08-14: 53 decided
  districts → **1** candidate (Fairbanks) → 0 actually stale. No false negatives by construction;
  the false positives cost one closing-argument load each.
* **What does Stage 9 do on the second pass?** Nothing new is needed: its idempotency key is
  (facts fingerprint, mapping version), so a re-approval on a moved picture re-writes, the orphan
  reconcile converges the band set, and #682 fires it from the approval. History is preserved by the
  append-only approval log + the Stage-9 ledger.
* **How is the delta presented?** `delta_against_decision` — PURE, per band: what the human approved
  vs what the facts say now, and which schools joined or left. A re-review is a review of WHAT
  CHANGED; a from-scratch re-adjudication is exactly what the standing falsifier forbids.
"""
from __future__ import annotations

from infrastructure.acquisition.stage8_aggregate import approval as APV
from infrastructure.acquisition.stage8_aggregate import closing_argument as CA

BANDS = ("elementary", "middle", "high")

# The SOUND SUPERSET pre-filter (see the module docstring): every district whose LATEST gate@8
# decision is older than some row that can move the fingerprint. Facts are scoped to accepted
# production facts (a vision-lab probe is a measurement, never part of the picture); the four
# human-judgment tables are append-only, EXCEPT the per-school override, which is an UPDATE onto
# school_fact.human_determination — so that one is dated by its own embedded `at` stamp rather than
# by the row's created_at, which would never move. `human_determination` may be '' rather than NULL,
# hence the NULLIF/btrim guard before the JSON cast (an unguarded cast raises on the empty string).
CHANGED_SINCE_DECISION_SQL = """
WITH latest AS (
  SELECT DISTINCT ON (district_id) district_id, approval_id, disposition, created_at
  FROM stage8_approval ORDER BY district_id, approval_id DESC)
SELECT l.district_id, l.approval_id, l.disposition, l.created_at,
       (SELECT COUNT(*) FROM school_fact f JOIN extraction e ON e.extraction_id = f.extraction_id
          WHERE f.district_id = l.district_id AND f.status = 'accepted'
            AND e.run_kind = 'production' AND f.created_at > l.created_at) AS n_new_facts,
       (SELECT COUNT(*) FROM band_exclusion x
          WHERE x.district_id = l.district_id AND x.created_at > l.created_at)
     + (SELECT COUNT(*) FROM human_added_fact h
          WHERE h.district_id = l.district_id AND h.created_at > l.created_at)
     + (SELECT COUNT(*) FROM slot_assignment a
          WHERE a.district_id = l.district_id AND a.created_at > l.created_at)
     + (SELECT COUNT(*) FROM school_fact o WHERE o.district_id = l.district_id
          AND (NULLIF(btrim(COALESCE(o.human_determination, '')), '')::json ->> 'at') > l.created_at)
       AS n_new_judgments
FROM latest l
"""


def candidates(session) -> list:
    """The cheap superset: [{district_id, approval_id, disposition, created_at, n_new_facts,
    n_new_judgments}] for every decided district that gained evidence AFTER its decision. One round
    trip. A district here MAY need re-review; `needs_rereview` decides."""
    from sqlalchemy import text
    return [dict(m) for m in session.execute(text(CHANGED_SINCE_DECISION_SQL)).mappings().all()
            if m["n_new_facts"] or m["n_new_judgments"]]


def needs_rereview(session, *, ca_loader=None) -> dict:
    """{district_id: {approval_id, disposition, n_new_facts, n_new_judgments}} for the districts whose
    decision is ACTUALLY stale — the pre-filter's survivors, each confirmed by the one authoritative
    staleness rule (`decision_status`, REQ-147: the frozen receipt re-hashed under today's code).

    Deliberately NOT the pre-filter's own output: Fairbanks proves the difference — 26 new facts, zero
    movement. A queue badge derived from "new facts" alone would have cried wolf on the only district
    the mechanism has ever seen.

    `ca_loader` is the closing-argument seam (tests inject; production uses the real assembler)."""
    load = ca_loader or (lambda s, d: CA.load_closing_argument(s, d, record_drift_event=False))
    out = {}
    for c in candidates(session):
        status = APV.decision_status(session, c["district_id"],
                                     current_fingerprint=CA.fingerprint(load(session,
                                                                             c["district_id"])))
        if status.get("is_stale"):
            out[c["district_id"]] = {"approval_id": c["approval_id"],
                                     "disposition": c["disposition"],
                                     "n_new_facts": c["n_new_facts"],
                                     "n_new_judgments": c["n_new_judgments"]}
    return out


def _schools(band_obj) -> dict:
    """{normalized school name: gross} for a band of a closing argument (either vintage)."""
    out = {}
    for s in (band_obj or {}).get("schools") or []:
        name = (s.get("school") or "").strip().lower()
        if name:
            out[name] = s.get("gross")
    return out


def delta_against_decision(frozen: dict, live: dict) -> dict:
    """PURE. What CHANGED between the picture a human approved and the picture now:

        {"moved": bool,
         "bands": {band: {approved_gross, live_gross, moved,
                          schools_added: [...], schools_removed: [...],
                          n_approved_schools, n_live_schools}}}

    A re-review must present a DELTA, not a from-scratch re-adjudication (the falsifier: a district
    that needs hand-re-adjudication means the mechanism is wrong). Band-grain because that is the
    decision's grain (§2e all-or-nothing at the district, determined per band).

    Bands are unioned across both vintages, so a band that APPEARED (the Fairbanks shape — a
    previously unheard band gaining facts) and one that VANISHED are both visible; anything outside
    the canonical three still shows, sorted after them, rather than being silently dropped."""
    fz_bands, lv_bands = (frozen or {}).get("bands") or {}, (live or {}).get("bands") or {}
    names = [b for b in BANDS if b in fz_bands or b in lv_bands]
    names += sorted(set(fz_bands) | set(lv_bands) - set(names) - set(BANDS))
    bands, moved_any = {}, False
    for b in names:
        fz, lv = fz_bands.get(b) or {}, lv_bands.get(b) or {}
        fz_s, lv_s = _schools(fz), _schools(lv)
        approved_gross, live_gross = fz.get("gross_minutes"), lv.get("gross_minutes")
        added = sorted(set(lv_s) - set(fz_s))
        removed = sorted(set(fz_s) - set(lv_s))
        # "moved" is about the DETERMINATION and its basis: a changed value, or a changed set of
        # schools under an unchanged value (the same number resting on different evidence is still a
        # thing the human signed off on and should see).
        moved = bool(approved_gross != live_gross or added or removed)
        moved_any = moved_any or moved
        bands[b] = {"approved_gross": approved_gross, "live_gross": live_gross, "moved": moved,
                    "schools_added": added, "schools_removed": removed,
                    "n_approved_schools": len(fz_s), "n_live_schools": len(lv_s)}
    return {"moved": moved_any, "bands": bands}


def main():
    """CLI: which written/decided districts actually need re-review, and what moved.

        python3 -m infrastructure.acquisition.stage8_aggregate.rereview [district_id ...]
    """
    import argparse
    import json

    from infrastructure.acquisition.common import db as gdb

    ap = argparse.ArgumentParser(description="gate@8 re-review audit (#713)")
    ap.add_argument("district_ids", nargs="*", help="show the delta for these (default: the flagged)")
    a = ap.parse_args()

    gdb.init_precious_schema()
    with gdb.session_scope() as s:
        cands = candidates(s)
        flagged = needs_rereview(s)
        print(f"{len(cands)} decided district(s) gained evidence since their decision; "
              f"{len(flagged)} actually need re-review.")
        for c in cands:
            mark = "NEEDS RE-REVIEW" if c["district_id"] in flagged else "no change to the picture"
            print(f"  {c['district_id']} ({c['disposition']}, approval {c['approval_id']}): "
                  f"+{c['n_new_facts']} fact(s), +{c['n_new_judgments']} judgment(s) — {mark}")
        for did in (a.district_ids or list(flagged)):
            latest = APV.latest_decision(s, did, with_receipt=True)
            if not latest:
                print(f"\n{did}: never decided")
                continue
            frozen = json.loads(latest["receipt_json"] or "{}")
            live = CA.load_closing_argument(s, did, record_drift_event=False)
            d = delta_against_decision(frozen, live)
            print(f"\n{did} — delta vs approval {latest['approval_id']} "
                  f"({'MOVED' if d['moved'] else 'unchanged'}):")
            for b, x in d["bands"].items():
                print(f"  {b:12} approved={x['approved_gross']} live={x['live_gross']} "
                      f"schools {x['n_approved_schools']}->{x['n_live_schools']}"
                      + (f" +{x['schools_added']}" if x["schools_added"] else "")
                      + (f" -{x['schools_removed']}" if x["schools_removed"] else ""))


if __name__ == "__main__":
    main()
