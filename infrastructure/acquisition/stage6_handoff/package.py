"""Stage 6 handoff-package assembly (REQ-101): release decision -> routed, priced handoff package.

Takes a per-district release decision — the Stage-5 canonical records, each carrying its `send` reps
(enriched with `kind` + `n_chars`/`n_times` for routing + cost) and the `signals` routing needs —
and produces the in-memory handoff package: every send rep routed to its council(s) (routing.py) and
priced (cost.py). Rejected records are recorded (decision + reason) with no reps, for traceability.

PURE (dicts in/out). Imports only sibling stage6 modules + nothing from other stages — the DB read of
the release decision and the app-layer wiring live in `process_governance` (the §12 contract: stage6
must not import stage5). `councils` = the loaded registry (id -> config); `cost_model` = the loaded rates.
"""

from infrastructure.acquisition.stage6_handoff import routing, cost, prompts as P6
from infrastructure.acquisition.common import model_families as MF
from infrastructure.acquisition.common.timeutil import utcnow as _now




def system_prompt_chars(council_cfg: dict) -> int:
    """The LARGEST system prompt any member of this council will send — the overhead the overflow
    estimate must carry (#846). Per-model prompt overrides exist (`prompts.<model>`), so take the
    max across members: the estimate is conservative by design (it errs toward "overflows"), and
    the weakest-member ceiling it feeds is a min, so the pessimistic prompt is the consistent
    choice. Stage 7 sends exactly one of these; `_est_prompt_tokens` measures the real one, and
    the two agree by construction for the member that carries the max."""
    ids = {P6.select_prompt_id(council_cfg, m) for m in MF.council_members(council_cfg)}
    return max((len(P6.SYSTEM_PROMPTS.get(i) or "") for i in ids), default=0)


def _overflow_for(council_cfg: dict, se: dict) -> "bool | None":
    """The dispatch-time overflow verdict for one send entry against its routed council. Feeds the
    shared estimator the SAME inputs the paid call will carry — content + system prompt, shaped by
    kind — not content chars alone (#846)."""
    return MF.rep_overflow(council_cfg, se.get("n_chars"), se.get("n_times"),
                           kind=se.get("kind") or "text",
                           system_chars=system_prompt_chars(council_cfg))


def assemble_record(rec: dict, councils: dict, cost_model: dict, overrides: dict = None) -> dict:
    """Route + price one release record's send reps. A non-send record returns with `reps: []`.
    `overrides` (gate@6 manual override): `{"<rec_key>::<file>": council_id}` — a rep whose key is
    overridden goes to the chosen council instead of the auto-routed one (fidelity flag recomputed)."""
    overrides = overrides or {}
    out = {"rec_key": rec.get("rec_key"), "url": rec.get("url"),
           "label": rec.get("label"),   # #691: the console's held rows name what a hold suppressed
           "decision": rec.get("decision"), "reason": rec.get("reason"), "reps": []}
    if rec.get("decision") != "send":
        return out
    signals = rec.get("signals") or {}
    for se in rec.get("send", []) or []:
        ov = overrides.get(f"{rec.get('rec_key')}::{se.get('file')}")
        if ov:
            # A stale/unknown override must REFUSE, not silently fall back to auto-routing — an
            # override is a human dispatch decision; misrouting a paid call quietly is worse than
            # failing the assembly (issue #54).
            if ov not in councils:
                raise ValueError(
                    f"unknown council override '{ov}' for rep "
                    f"{rec.get('rec_key')}::{se.get('file')} — not in the loaded council registry "
                    f"({sorted(councils)}); remove or correct the override")
            r = {"councils": [ov], "fidelity_suspect": routing.is_low_fidelity(signals),
                 "reason": f"override:{ov}"}
        else:
            r = routing.route(se, signals, councils)   # councils = id->config registry (carries input_kinds)
        est = sum(cost.estimate_council_cost(se, councils[cid], cost_model)
                  for cid in r["councils"] if cid in councils)
        rep = {
            "file": se.get("file"), "kind": se.get("kind"),
            "councils": r["councils"], "fidelity_suspect": r["fidelity_suspect"],
            "route_reason": r["reason"], "est_usd": est}
        # `pages` (the harvest-pages hint on a handbook PDF/slice send) must survive to the frozen
        # handoff + the Stage-7 request plan — it's what scopes the paid read (issue #38).
        if se.get("pages"):
            rep["pages"] = se["pages"]
        # `n_times`/`n_chars` are the cost model's output-token scaler inputs (cost.py `_n_schools` /
        # `estimate_call_cost`). They reach `se` via the bridge's `_enrich_send` but used to be dropped
        # here, so the measured scaler always fell to the floor (issue #192). Carry them when present —
        # they are size signals, kept OUT of the price-independent content identity (like est_usd).
        for _f in ("n_times", "n_chars"):
            if se.get(_f) is not None:
                rep[_f] = se[_f]
        # #822: can the council we just routed to actually EMIT this rep's estimated output? Known
        # here, pre-flight, from size + membership — before a cent is spent. TRI-STATE, and always
        # present: True overflows, False fits, None un-assessable (a binary/image rep carries no
        # n_times, or a member is uncatalogued). None must never be read as False downstream — the
        # vision tier has no countable times, so "fits" there would be a claim we cannot support.
        cid = r["councils"][0] if r["councils"] else None
        rep["overflow"] = (_overflow_for(councils[cid], se) if cid in councils else None)
        out["reps"].append(rep)
    return out


def assemble_district(district: dict, records: list, councils: dict, cost_model: dict, overrides: dict = None) -> dict:
    """One district block: every canonical record routed/priced, plus send-rep count + cost rollup."""
    recs = [assemble_record(r, councils, cost_model, overrides) for r in records]
    n_reps = sum(len(r["reps"]) for r in recs)
    est = sum(rep["est_usd"] for r in recs for rep in r["reps"])
    return {"district_id": district.get("district_id"), "name": district.get("name"),
            "state": district.get("state"), "topology": district.get("labeled_topology"),
            "records": recs, "n_send_reps": n_reps, "est_usd": est}


def assemble_package(districts: list, councils: dict, cost_model: dict, overrides: dict = None) -> dict:
    """The full in-memory handoff package over `districts` = [(district_meta, records), ...].
    Returns the district blocks + a total cost rollup carrying the cost model's provenance."""
    blocks = [assemble_district(d, recs, councils, cost_model, overrides) for d, recs in districts]
    total = sum(b["est_usd"] for b in blocks)
    n_reps = sum(b["n_send_reps"] for b in blocks)
    return {"generated_at": _now(), "districts": blocks,
            "cost": {"total_usd": total, "n_reps": n_reps,
                     "provenance": cost_model.get("provenance", "unknown")}}
