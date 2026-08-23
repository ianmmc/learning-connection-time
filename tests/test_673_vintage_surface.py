"""#673 — the gate@5 vintage surface: DB-free source pins for the render path.

The end-to-end render proof is `infrastructure/scraper/verify_673_console.mjs` (live server + the
real TAOS records; not CI-runnable). These pins hold the properties whose loss the first run of
that script caught, so they cannot silently return between console verifications.

The bug being pinned (found 2026-08-23, the render check #673 was left open for): PR #850's client
read a top-level vintage field off the /api/record payload, but that endpoint has never projected
one — the vintage's one home is the SIGNALS dict (`build_signals` writes it into `signals_json`;
the #241 floor SQL reads it there). The phantom read was always undefined, so every record —
the 2014-15 TAOS handbook included — rendered "unknown" with no floor warning and no facet hint.
The #846 shape: a payload contract and its consumer drifting apart with nothing connecting them.

#895 tightened the countermeasure from "read the right dict" to "spell the path ONCE": renderPanel
binds `const vintage = s.content_school_year` a single time, and every consumer uses the binding.
A second spelling anywhere in the file is the drift vector re-opening.

Uses the shared `app_js` conftest fixture (#897) — the one construction of the client's source
path, derived from the package location so a repo-layout move cannot silently break it.
"""


def test_client_reads_vintage_from_the_signals_dict_not_a_phantom_payload_field(app_js):
    assert "d.content_school_year" not in app_js, (
        "/api/record has NO top-level content_school_year — the value lives inside the signals "
        "dict, and reading it off the payload root renders every record's vintage as 'unknown' "
        "(the exact bug verify_673_console.mjs caught on its first run)")
    # #895: ONE spelling of the field path, bound once in renderPanel; consumers use the binding.
    assert app_js.count("s.content_school_year") == 1, (
        "the field path must be spelled exactly once (the `vintage` binding) — a second spelling "
        "is the #850/#895 drift vector re-opening")
    assert "const vintage = s.content_school_year" in app_js
    assert "belowFloor(vintage)" in app_js, "the facet hint must consume the binding"


def test_vintage_surface_dom_hooks_present(app_js):
    """UI-visibility requirement (the standing rule for console rework): the verifier and any
    future Playwright pass key on these hooks; losing one silently blinds the render check."""
    assert 'data-feat="vintage-readout"' in app_js
    assert 'data-feat="vintage-facets"' in app_js
    assert "BELOW the ${VALIDITY_FLOOR} validity floor" in app_js, (
        "the held-reason must be stated at the point of review (acceptance box 2)")
    assert "#642" in app_js, "the unknown case must explain the URL-only derivation limit"


def test_vintage_hint_is_a_flag_never_an_auto_tick(app_js):
    """#241 measured the automatic recency veto actively harmful (1 false-send removed, 17 real
    targets vetoed): the below-floor hint must flow into `check(...)`'s FLAGGED argument (an
    <em class="det-hint">), never into the checkbox's checked state."""
    assert "check(id, t, belowFloor(vintage))" in app_js
    # the only paths to a pre-checked facet box are the human's own saved facets
    assert app_js.count('savedFacets[id] === "yes" ? "checked"') == 1
