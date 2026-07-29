"""#691 measurement (READ-ONLY): replay district_release_input over every hub-labeled district and
simulate the two candidate rules against the baseline composer.

Rule A (issue option 2): hub-priority holds only UNLABELED survivors — labeled targets always send
  (the hub winner among them). Narrowing keeps suppressing speculative tier-A auto-sends only.
Rule B (yield floor): today's narrowing stands, but a LABELED sibling whose n_times_in_window is
  >= k * max(1, winner's n_times_in_window) also sends (grid over k).

Method: wrap _hub_priority_holds to capture the exact survivor set the live pass sees, run the real
district_release_input (production, verified_only=False — the issue's own methodology), then compute
each rule's send set offline from the captured survivors + each record's signals.
"""
import json
import sys

from sqlalchemy import text

import infrastructure.acquisition.process_governance.stage6_dispatch as S6
from infrastructure.acquisition.common.db import session_scope

K_GRID = [2, 3, 5]

captured = {}
_orig_hub = S6._hub_priority_holds


def _wrapper(sendables):
    captured["survivors"] = [dict(s) for s in sendables]
    return _orig_hub(sendables)


S6._hub_priority_holds = _wrapper


def nitw(sig):
    v = (sig or {}).get("n_times_in_window")
    return int(v) if isinstance(v, (int, float)) else 0


def main():
    out = {"districts": [], "k_grid": K_GRID}
    with session_scope() as session:
        dids = [r[0] for r in session.execute(text(
            """SELECT DISTINCT r.district_id
               FROM record r JOIN label l ON l.rec_key = r.rec_key
               WHERE l.primary_label IN ('district_hub_by_school', 'district_hub_by_band')
               ORDER BY r.district_id"""))]
        print(f"hub-labeled districts: {len(dids)}", file=sys.stderr)
        for did in dids:
            captured.clear()
            di = S6.district_release_input(session, did)
            if di is None:
                continue
            district, records = di
            by_key = {r["rec_key"]: r for r in records}
            survivors = captured.get("survivors") or []
            sig_of = {rk: (by_key[rk]["signals"] or {}) for rk in by_key}

            baseline_sends = [r["rec_key"] for r in records if r["decision"] == "send"]
            hub_holds = [r["rec_key"] for r in records
                         if r["decision"] == "hold" and str(r["reason"]).startswith("hub-priority:")]
            winner = None
            if hub_holds:
                winner = str(by_key[hub_holds[0]]["reason"]).split("narrowed-to:", 1)[1]
            elif len(baseline_sends) >= 1 and survivors:
                w, _ = _orig_hub(survivors)
                winner = w  # hub present but nothing to hold (solo survivor)

            surv_rows = []
            for s in survivors:
                surv_rows.append({
                    "rec_key": s["rec_key"], "label": s.get("label"), "url": s.get("url"),
                    "year": s.get("year"), "n_times": s.get("n_times"),
                    "nitw": nitw(sig_of.get(s["rec_key"]))})
            row_of = {r["rec_key"]: r for r in surv_rows}

            hub_narrowed = bool(hub_holds)
            winner_nitw = row_of[winner]["nitw"] if winner in row_of else None

            # Rule A: labeled survivors always send; unlabeled survivors (auto:tier-A) hold when a hub exists.
            rule_a_sends = None
            if winner is not None:
                rule_a_sends = sorted({r["rec_key"] for r in surv_rows if r["label"]} | {winner})

            # Rule B: winner + labeled siblings clearing the yield floor, per k.
            rule_b = {}
            if winner is not None and winner_nitw is not None:
                for k in K_GRID:
                    floor = k * max(1, winner_nitw)
                    extra = [r["rec_key"] for r in surv_rows
                             if r["label"] and r["rec_key"] != winner and r["nitw"] >= floor]
                    rule_b[str(k)] = sorted(set(extra) | {winner})

            out["districts"].append({
                "district_id": did, "name": district.get("name"), "state": district.get("state"),
                "n_canonical": len(records),
                "n_baseline_sends": len(baseline_sends), "baseline_sends": baseline_sends,
                "n_hub_holds": len(hub_holds), "hub_narrowed": hub_narrowed,
                "winner": winner, "winner_row": row_of.get(winner),
                "survivors": surv_rows,
                "rule_a_sends": rule_a_sends,
                "rule_a_added": (sorted(set(rule_a_sends) - set(baseline_sends))
                                 if rule_a_sends is not None else None),
                "rule_b_sends": rule_b,
            })

    # corpus rollup
    ds = out["districts"]
    narrowed = [d for d in ds if d["hub_narrowed"]]
    out["summary"] = {
        "hub_labeled_districts": len(ds),
        "narrowed_districts": len(narrowed),
        "baseline_total_sends": sum(d["n_baseline_sends"] for d in ds),
        "rule_a": {
            "districts_changed": sum(1 for d in ds if d["rule_a_added"]),
            "sends_added": sum(len(d["rule_a_added"] or []) for d in ds)},
        "rule_b": {str(k): {
            "districts_changed": sum(1 for d in ds if (d["rule_b_sends"].get(str(k)) or [])
                                     and set(d["rule_b_sends"][str(k)]) - set(d["baseline_sends"])),
            "sends_added": sum(len(set(d["rule_b_sends"].get(str(k)) or []) - set(d["baseline_sends"]))
                               for d in ds)} for k in K_GRID},
    }
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
