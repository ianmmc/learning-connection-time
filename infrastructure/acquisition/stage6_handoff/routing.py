"""Stage 6 per-representation routing (REQ-101): a representation -> the council(s) it goes to.

PURE (dicts in, dict out; no DB, no other-stage imports). The default rule is deterministic and
keys on the representation's `kind` + the record's capture-fidelity signal, then picks the council
whose declared `input_kinds` covers the wanted kind — DATA-DRIVEN off the council configs, so a new
content-typed council plugs in by adding a config entry, not by editing this code:

  * image rep                      -> a council that reads images (the vision council)
  * text/pdf on a LOW-FIDELITY capture (visual_text_gap) -> the vision council, fidelity_suspect=True
    (STAGE6_HANDOFF_DESIGN §3B / the New Haven false-consensus lesson: cross-family agreement is
    trustworthy only on a clean input, so read the rendered picture and never auto-accept the text)
  * clean text/pdf                 -> a council that reads text

`councils` is the id->config registry. `councils` is always a LIST in the result (the rep->council
mapping is many-to-many; the default returns one). `fidelity_suspect` rides along to the handoff so
Stage 7 knows not to auto-accept on 2-voter agreement.
"""

# Rep file_kind -> the council input_kind it needs read. (image reps + low-fidelity text both want vision.)
_IMAGE_KIND = "image"
_TEXT_KIND = "text"


def is_low_fidelity(signals: dict) -> bool:
    """The capture-fidelity gate signal: a visual exists but the text capture is thin/unreliable, so
    cross-family text agreement would be false consensus on a shared bad input (New Haven)."""
    return bool((signals or {}).get("visual_text_gap"))


def _councils_for_kind(councils: dict, kind: str) -> list:
    """The configured council ids whose `input_kinds` covers `kind` (sorted, deterministic)."""
    return sorted(cid for cid, c in (councils or {}).items() if kind in (c.get("input_kinds") or []))


def route(send_entry: dict, signals: dict, councils: dict) -> dict:
    """Route ONE representation. Returns {councils:[id...], fidelity_suspect:bool, reason:str}.

    `send_entry`: the release `send` row ({file, kind, pages?}). `signals`: the record's signal dict.
    `councils`: the id->config registry (configs carry `input_kinds`), so we route by what each
    council declares it reads — and never to a council that isn't loaded.
    """
    kind = (send_entry or {}).get("kind")
    low_fi = is_low_fidelity(signals)
    want = _IMAGE_KIND if (kind == _IMAGE_KIND or low_fi) else _TEXT_KIND
    redirected = low_fi and kind != _IMAGE_KIND   # a low-fidelity text/pdf rep redirected to vision

    matches = _councils_for_kind(councils, want)
    if matches:
        reason = ("image-rep" if kind == _IMAGE_KIND
                  else "visual_text_gap->vision(fidelity)" if redirected else f"{want}-council")
        return {"councils": [matches[0]], "fidelity_suspect": redirected, "reason": reason}

    # No council reads the wanted kind. Fall back to a text council if one exists, but STAY flagged
    # whenever the rep wanted vision (image rep, or a fidelity-suspect text rep) — never silently
    # auto-accept it; the judge/human is the backstop.
    suspect = (kind == _IMAGE_KIND) or low_fi
    text_matches = _councils_for_kind(councils, _TEXT_KIND)
    if text_matches:
        return {"councils": [text_matches[0]], "fidelity_suspect": suspect,
                "reason": f"{want}-council-unavailable->text"}
    return {"councils": [], "fidelity_suspect": suspect, "reason": f"no-council-for-{want}"}
