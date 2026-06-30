"""Stage 6 per-representation routing (REQ-101): a representation -> the council(s) it goes to.

PURE (dicts in, dict out; no DB, no other-stage imports). The default rule is deterministic and
keys on the representation's `kind` + the record's capture-fidelity signal:

  * image rep                      -> the vision council
  * text/pdf on a LOW-FIDELITY capture (visual_text_gap) -> the vision council, fidelity_suspect=True
    (STAGE6_HANDOFF_DESIGN §3B / the New Haven false-consensus lesson: cross-family agreement is
    trustworthy only on a clean input, so read the rendered picture and never auto-accept the text)
  * clean text/pdf                 -> the cheap text council

`councils` is always a LIST (the rep->council mapping is many-to-many; the default returns one).
`fidelity_suspect` rides along to the handoff so Stage 7 knows not to auto-accept on 2-voter
agreement. Content-typed / CMS / state councils (the speculative sketch dimensions) plug in here once
they exist in the registry — until then routing targets only the councils that are actually available.
"""
TEXT_COUNCIL = "low-cost-text"
IMAGE_COUNCIL = "image"


def is_low_fidelity(signals: dict) -> bool:
    """The capture-fidelity gate signal: a visual exists but the text capture is thin/unreliable, so
    cross-family text agreement would be false consensus on a shared bad input (New Haven)."""
    return bool((signals or {}).get("visual_text_gap"))


def route(send_entry: dict, signals: dict, available) -> dict:
    """Route ONE representation. Returns {councils:[id...], fidelity_suspect:bool, reason:str}.

    `send_entry`: the release `send` row ({file, kind, pages?}). `signals`: the record's signal dict.
    `available`: the set of configured council ids (so we never route to a council that isn't loaded).
    """
    kind = (send_entry or {}).get("kind")
    available = set(available or ())
    low_fi = is_low_fidelity(signals)

    # Image reps, and low-fidelity text/pdf, both want the vision council.
    if kind == "image" or low_fi:
        suspect = low_fi   # an image rep is the intended reader, not "suspect"; a redirected text rep is
        reason = "image-rep" if kind == "image" else "visual_text_gap->vision(fidelity)"
        if IMAGE_COUNCIL in available:
            return {"councils": [IMAGE_COUNCIL], "fidelity_suspect": suspect, "reason": reason}
        # No vision council configured: keep on the text council but STAY flagged (never silently
        # auto-accept a fidelity-suspect rep) — the judge/human is the backstop.
        return {"councils": [TEXT_COUNCIL], "fidelity_suspect": True,
                "reason": reason + ";no-image-council"}

    # Clean digital text/pdf -> the cheap text council.
    return {"councils": [TEXT_COUNCIL], "fidelity_suspect": False, "reason": "clean-text"}
