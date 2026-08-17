"""#809 — MODEL_WINDOWS drift detector (network; integration-marked, excluded from the default
suite and per-commit CI).

The checked-in-not-fetched decision for MODEL_WINDOWS is right (determinism, test visibility,
commandment #1) — but it accepts staleness, and REQ-174 exists because the LAST hand-refreshed
window assumption (MAX_TOKENS_CEILING's premise) went stale silently until two districts zeroed
in a paid run. The key-set parity test cannot observe drift: if a provider changes a catalogued
model's windows tomorrow, every DB-free test stays green and the first symptom is a provider 400.
This test IS the detector — a failure here means "refresh the catalog" (the command is in
model_families.py next to MODEL_WINDOWS), never "the build is broken".
"""
import json
import urllib.request

import pytest

from infrastructure.acquisition.common.model_families import MODEL_WINDOWS

pytestmark = pytest.mark.integration   # network — nightly/local, never the default suite


def _fetch_models() -> dict:
    req = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                 headers={"User-Agent": "lct-window-drift-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    return {m["id"]: m for m in body.get("data", [])}


def test_catalogued_windows_match_provider():
    try:
        live = _fetch_models()
    except OSError as e:   # offline/unreachable — skip, never a false "refresh the catalog"
        pytest.skip(f"OpenRouter unreachable: {e}")
    drifted = []
    for model_id, w in MODEL_WINDOWS.items():
        m = live.get(model_id)
        if m is None:
            drifted.append(f"{model_id}: NOT LISTED by the provider anymore")
            continue
        ctx = m.get("context_length")
        max_out = (m.get("top_provider") or {}).get("max_completion_tokens")
        if ctx != w["context"]:
            drifted.append(f"{model_id}: context {w['context']} (catalog) != {ctx} (live)")
        if max_out != w["max_out"]:
            drifted.append(f"{model_id}: max_out {w['max_out']} (catalog) != {max_out} (live)")
    assert not drifted, (
        "MODEL_WINDOWS has drifted from the provider — refresh the catalog "
        "(see the fetch command in model_families.py) and re-run:\n  " + "\n  ".join(drifted))
