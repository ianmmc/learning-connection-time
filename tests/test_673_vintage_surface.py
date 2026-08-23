"""#673 — the gate@5 vintage surface: DB-free source pins for the render path.

The end-to-end render proof is `infrastructure/scraper/verify_673_console.mjs` (live server + the
real TAOS records; not CI-runnable). These pins hold the two properties whose loss the first run of
that script caught, so they cannot silently return between console verifications.

The bug being pinned (found 2026-08-23, the render check #673 was left open for): PR #850's client
read a top-level `d.content_school_year`, but `/api/record` has never projected that field — the
vintage's one home is the SIGNALS dict (`build_signals` writes it into `signals_json`; the #241
floor SQL reads it there). `d.content_school_year` was therefore always undefined, and every record
— the 2014-15 TAOS handbook included — rendered "unknown" with no floor warning and no facet hint.
The phantom field is exactly the #846 shape: the payload contract and its consumer drifting apart
with nothing connecting them.
"""
from pathlib import Path

APP_JS = (Path(__file__).resolve().parent.parent
          / "infrastructure/acquisition/process_governance/static/app.js")


def test_client_reads_vintage_from_the_signals_dict_not_a_phantom_payload_field():
    js = APP_JS.read_text()
    assert "d.content_school_year" not in js, (
        "/api/record has NO top-level content_school_year — the value lives inside the signals "
        "dict, and reading d.content_school_year renders every record's vintage as 'unknown' "
        "(the exact bug verify_673_console.mjs caught on its first run)")
    assert js.count("s.content_school_year") >= 2, (
        "both consumers — the readout and the facet hint — must read the signals dict")


def test_vintage_surface_dom_hooks_present():
    """UI-visibility requirement (the standing rule for console rework): the verifier and any
    future Playwright pass key on these hooks; losing one silently blinds the render check."""
    js = APP_JS.read_text()
    assert 'data-feat="vintage-readout"' in js
    assert 'data-feat="vintage-facets"' in js
    assert "BELOW the ${VALIDITY_FLOOR} validity floor" in js, (
        "the held-reason must be stated at the point of review (acceptance box 2)")
    assert "#642" in js, "the unknown case must explain the URL-only derivation limit"


def test_vintage_hint_is_a_flag_never_an_auto_tick():
    """#241 measured the automatic recency veto actively harmful (1 false-send removed, 17 real
    targets vetoed): the below-floor hint must flow into `check(...)`'s FLAGGED argument (an
    <em class="det-hint">), never into the checkbox's checked state."""
    js = APP_JS.read_text()
    assert "check(id, t, belowFloor(s.content_school_year))" in js
    # the only paths to a pre-checked facet box are the human's own saved facets
    assert js.count('savedFacets[id] === "yes" ? "checked"') == 1
