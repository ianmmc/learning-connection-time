"""Roster-anchored school identity resolution (#693/#721) — the resolver's pinned cases.

Every case here is a REAL district from the 2026-08-15 corpus measurement
(docs/technical-notes/learning-loop-reports/2026-08-15-693-721-roster-anchored-identity.md);
the property numbers (P1..P9) are that report's acceptance list. The level-collapse pin (P5) is
the one a future "just merge on name" change would break — it is the reason grade_level stays in
the consensus grouping key.
"""
import pytest

from infrastructure.acquisition.common.school_match import (
    norm_school, resolve_school_identity)


def recs(*pairs):
    return [{"name": n, "school_id": s} for n, s in pairs]


# --- Cleveland 3904378 (P1, P2) --------------------------------------------------------------

# Real roster names, verified against ccd_sch 2026-08-15 — the '&' and the '-Nottingham' are the
# details that made the naive fixture pass while production failed (see findings report §9).
CLEVELAND = {
    "high": recs(("Lincoln West School of Science & Health", "390437800001"),
                 ("Lincoln West School Of Global Studies", "390437800006"),
                 ("Rhodes College and Career Academy", "390437800002"),
                 ("Rhodes School of Environmental Studies", "390437800003")),
    "elementary": recs(("Hannah Gibbons-Nottingham Elementary School", "390437800004"),
                       ("Daniel E Morgan School", "390437800005")),
    "middle": recs(("Daniel E Morgan School", "390437800005")),
}


def test_p1_lincoln_west_variants_share_one_identity():
    """The filed #693 case. The root cause was a normalizer ASYMMETRY: '&' is punctuation-dropped
    but 'and' was a kept token — the same conjunction normalized two ways by typography. With
    'and' in _GENERIC (measured: 0 roster collisions across all 83 corpus districts) both
    variants exact-match the roster; the Global Studies sibling proves the merge is not a
    prefix-grab."""
    assert norm_school("Lincoln West Science and Health") == "lincoln west science health"
    k1, i1 = resolve_school_identity("lincoln west science health", "high", CLEVELAND)
    k2, i2 = resolve_school_identity("lincoln west science and health", "high", CLEVELAND)
    assert k1 == k2
    assert i1["school_id"] == i2["school_id"] == "390437800001"
    # bare 'lincoln west' spans BOTH real schools -> must be ambiguous, never a guess
    _, amb = resolve_school_identity("lincoln west", "high", CLEVELAND)
    assert amb["rule"] == "ambiguous"


def test_p2_leading_initial_artifact_resolves():
    """'x hannah gibbons' (roster/extraction artifact) joins 'hannah gibbons' — and BOTH need a
    second rung after the initial-strip because the roster name carries '-Nottingham'. The
    resolver only merges the GROUP; the 30-min start disagreement inside it stays the council's
    to adjudicate."""
    k1, i1 = resolve_school_identity("x hannah gibbons", "elementary", CLEVELAND)
    k2, _ = resolve_school_identity("hannah gibbons", "elementary", CLEVELAND)
    assert k1 == k2 == "hannah gibbons nottingham"
    assert i1["rule"] == "leading_initial+token_subset"


def test_p6_ambiguity_keeps_the_split():
    """'rhodes' matches TWO real roster schools — resolving would be #681 (false agreement).
    The key must stay unchanged; the info only makes the ambiguity gate@8-visible."""
    key, info = resolve_school_identity("rhodes", "high", CLEVELAND)
    assert key == "rhodes"
    assert info["rule"] == "ambiguous"
    assert len(info["candidates"]) == 2


# --- Essex Westford 5000395 (P3) -------------------------------------------------------------

ESSEX = {
    "elementary": recs(("Founders Memorial School", "500039500001"),
                       ("Albert D. Lawton School", "500039500002"),
                       ("Westford Elementary School", "500039500003")),
    "middle": recs(("Essex Middle School", "500039500004"),),
}


def test_p3_acronym_meets_spelled_out():
    """The systematic Essex form: models pick different naming conventions off the same site.
    Acronyms are computed on the FULL name — level words carry the tail (the 5x-undercount
    instrument lesson, findings report §3)."""
    k_acr, i_acr = resolve_school_identity("fms", "elementary", ESSEX)
    k_full, _ = resolve_school_identity("founders memorial", "elementary", ESSEX)
    assert k_acr == k_full == "founders memorial"
    assert i_acr["rule"] == "acronym"
    # the minus-'school' variant: 'Albert D. Lawton School' -> 'adl' as well as 'adls'
    k_adl, _ = resolve_school_identity("adl", "elementary", ESSEX)
    assert k_adl == "albert d lawton"
    # cross-band fall-through: 'ems' claimed under elementary still finds Essex Middle School
    k_ems, i_ems = resolve_school_identity("ems", "elementary", ESSEX)
    assert k_ems == "essex" and i_ems["rostered_bands"] == ["middle"]


# --- Washoe 3200480 / Coffee County 0100810 (P4 inputs, grade-span) --------------------------

WASHOE = {
    "elementary": recs(("GERLACH K-12 SCHOOL", "320048000001"), ("Smithridge Elementary", "320048000002")),
    "middle": recs(("GERLACH K-12 SCHOOL", "320048000001"),),
    "high": recs(("GERLACH K-12 SCHOOL", "320048000001"),),
}


def test_p4_multiband_campus_resolves_to_one_school_id_from_any_band():
    """#721's Gerlach: both voters' claims (middle, high) resolve to the SAME school_id, and the
    info carries the roster's own multiband placement — the adjudication signal the consensus
    layer merges on."""
    k_m, i_m = resolve_school_identity("gerlach k 12", "middle", WASHOE)
    k_h, i_h = resolve_school_identity("gerlach k 12", "high", WASHOE)
    assert k_m == k_h and i_m["school_id"] == i_h["school_id"] == "320048000001"
    assert i_m["rostered_bands"] == ["elementary", "high", "middle"]


def test_grade_span_strip_recovers_kinston():
    """The Kinston lesson (findings report §4): a glued-on grade-span token is not identity."""
    coffee = {"elementary": recs(("Kinston School", "010081000001"),),
              "high": recs(("Zion Chapel High School", "010081000002"),)}
    k, i = resolve_school_identity("kinston k12", "elementary", coffee)
    assert k == "kinston" and i["rule"] == "grade_span"
    k, i = resolve_school_identity("zion chapel k12", "high", coffee)
    assert k == "zion chapel" and i["rule"] == "grade_span"


# --- Orange 1201440 (P5 — THE PIN) -----------------------------------------------------------

ORANGE = {
    "elementary": recs(("APOPKA ELEMENTARY", "120144000001"),),
    "middle": recs(("APOPKA MIDDLE", "120144000002"),),
    "high": recs(("APOPKA HIGH", "120144000003"),),
}


def test_p5_level_collapse_pin():
    """THE regression pin: 'apopka' norms identically for three REAL schools; the claimed band
    must select the right one, and the three resolutions must be three distinct school_ids.
    35 groups / 12 districts in the 2026-08-15 corpus have this shape — a name-only grouping
    key (or a cross-band-first resolver) mass-fuses them. Must never pass ambiguous either:
    in-band each key is unique."""
    ids = {}
    for band in ("elementary", "middle", "high"):
        key, info = resolve_school_identity("apopka", band, ORANGE)
        assert key == "apopka"
        assert info and info["rule"] == "exact", f"{band}: {info}"
        ids[band] = info["school_id"]
    assert len(set(ids.values())) == 3


def test_p5_cross_band_on_level_collapse_is_ambiguous_not_a_guess():
    """A level-collapse name claimed in a band with NO candidate (Apopka has no K-12 campus)
    falls through to cross-band, finds three distinct schools, and must refuse to pick."""
    no_middle = {b: v for b, v in ORANGE.items() if b != "middle"}
    key, info = resolve_school_identity("apopka", "middle", no_middle)
    assert key == "apopka" and info["rule"] == "ambiguous"


# --- the value-negative rule stays absent (P9-adjacent) --------------------------------------

def test_reverse_subset_rule_is_absent():
    """roster ⊂ key measured value-negative ('regular day bell schedule' -> Bell Middle,
    'appoquinimink preschool full' -> Appoquinimink High). Unmatched is the correct outcome."""
    sd = {"middle": recs(("Bell Middle", "063432000001"),)}
    key, info = resolve_school_identity("regular day bell schedule", "middle", sd)
    assert key == norm_school("regular day bell schedule") and info is None


def test_bare_prek_is_not_a_grade_span():
    """'bucks hill prek' must NOT fuse into Bucks Hill Elementary: bare 'prek' marks an
    excluded-grade PROGRAM, not a span — the fact stays unmatched so the rung-4 exclusion screen
    adjudicates it (Waterbury 0904830, corpus validation §9). Digit-carrying spans still strip:
    'hanscom k8' and 'annabel c perry pk 8' resolve."""
    waterbury = {"elementary": recs(("Bucks Hill School", "090483000001"),)}
    key, info = resolve_school_identity("bucks hill prek", "elementary", waterbury)
    assert key == "bucks hill prek" and info is None
    hanscom = {"elementary": recs(("Hanscom School", "250690000001"),)}
    assert resolve_school_identity("hanscom k8", "elementary", hanscom)[0] == "hanscom"
    broward = {"elementary": recs(("ANNABEL C. PERRY PK-8", "120018000001"),)}
    # the returned key is the ROSTER school's canonical norm (span and all) — variant extractions
    # 'annabel c perry' and 'annabel c perry pk 8' both land on it, which is what grouping needs
    k, i = resolve_school_identity("annabel c perry", "elementary", broward)
    assert k == "annabel c perry pk 8" and i is not None


def test_unmatched_and_empty_inputs():
    assert resolve_school_identity("totally novel academy x", "high", ORANGE)[1] is None
    assert resolve_school_identity("", "high", ORANGE) == ("", None)
    assert resolve_school_identity("apopka", "high", {}) == ("apopka", None)
    # roster rows without school_id contribute nothing (defensive against sparse slot_recs)
    assert resolve_school_identity("apopka", "high",
                                   {"high": [{"name": "APOPKA HIGH"}]})[1] is None


def test_resolution_is_stable_under_its_own_output():
    """Resolving the resolved key again is a no-op with the same identity — the idempotence
    contract norm_school already carries, extended through the resolver (a re-aggregation replay
    (#716) must not drift on its second pass)."""
    k1, i1 = resolve_school_identity("lincoln west science health", "high", CLEVELAND)
    k2, i2 = resolve_school_identity(k1, "high", CLEVELAND)
    assert (k1, i1["school_id"]) == (k2, i2["school_id"])
