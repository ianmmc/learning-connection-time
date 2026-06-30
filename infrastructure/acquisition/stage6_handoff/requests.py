"""Stage 6 OpenRouter request assembly (REQ-101) — the dispatch plumbing UP TO the seam.

`plan_requests()` turns a frozen handoff into the deterministic FIRST-PASS plan: one planned call per
(sent rep × routed council × VOTER model). The judge is NOT in the first pass — it's materialized only
on a voter disagreement, at escalation time in Stage 7. `build_request()` materializes the actual
OpenRouter chat request given the representation's content (text string, or an image data/URL).

This is the seam: everything needed to POST is assembled here; the paid call itself is Stage 7.
Pure — no network, no DB, no disk reads (content is supplied by the caller). Imports only `prompts`.
"""
from infrastructure.acquisition.stage6_handoff import prompts as P


def plan_requests(handoff_doc: dict) -> list:
    """The first-pass voter-call plan over a frozen handoff. Each entry:
    {district_id, rec_key, file, kind, council_id, model, role, prompt_id}."""
    councils = handoff_doc.get("councils") or {}
    plan = []
    for d in handoff_doc.get("districts", []):
        did = d.get("district_id")
        for rec in d.get("records", []):
            if rec.get("decision") != "send":
                continue
            for rep in rec.get("reps", []):
                for cid in rep.get("councils", []):
                    cfg = councils.get(cid)
                    if not cfg:
                        continue
                    for model in cfg.get("voters", []):
                        plan.append({
                            "district_id": did, "rec_key": rec.get("rec_key"),
                            "file": rep.get("file"), "kind": rep.get("kind"),
                            "council_id": cid, "model": model, "role": "voter",
                            "prompt_id": P.select_prompt_id(cfg, model)})
    return plan


def build_request(planned: dict, content) -> dict:
    """Materialize the OpenRouter chat request for a planned call given the rep's CONTENT
    (text string, or an image data/URL). The last step before the paid POST — the seam."""
    system = P.SYSTEM_PROMPTS[planned["prompt_id"]]
    return {"model": planned["model"],
            "messages": [{"role": "system", "content": system},
                         P.user_message(content, planned.get("kind"))]}
