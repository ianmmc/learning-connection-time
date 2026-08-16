"""Shared school-name normalization — the identity key for matching a school across sources (REQ-117).

A school's match key is its name with punctuation and level/type words stripped, so `Brick Mill
ES/ECC` and `brick mill esecc` collide. Stage 8 consensus uses it to group a school across models;
the Stage 7 GT validator uses it to match our extracted school to the hand-verified one; Stage 5's
topology denominator counts roster schools through it. They MUST use the SAME function or matching
silently drifts — hence one home in `common`. Pure.

IDEMPOTENT BY DESIGN: norm_school(norm_school(x)) == norm_school(x). Stage 7 persists this key into
school_fact.school, so consumers that compare persisted keys across code versions (merge_fact_runs,
the #237 detector) re-normalize through the CURRENT function at read time — idempotence is what makes
that self-healing instead of a double-strip corruption. (Review of PR #247: a stopword-list change
would otherwise fragment the cross-run merge key with no backfill path.)
"""
import re
import unicodedata

# LEVEL/TYPE words — safe to strip ANYWHERE in the name: they never carry the distinguishing part of
# a school's identity ("Marion High School" == "Marion"). Includes the ES/MS/HS abbreviations real
# district sites use interchangeably with the full words ("Lincoln HS" == "Lincoln High School" —
# PR #247 review: the unabbreviated-only list made the same school two keys, a false-positive
# contamination flag in the #237 detector).
_GENERIC = re.compile(
    r"\b(elementary|middle|high|intermediate|school|schools|jr|junior|senior|academy|the|of|at"
    r"|es|ms|hs|and|sr|jrsr)\b")
# 'and' added 2026-08-15 (#693): '&' was already punctuation-dropped by _base, so the SAME
# conjunction normalized two ways by typography — 'Science & Health' == 'science health' but
# 'Science and Health' != it, the exact Cleveland false-split. Measured safe: 0 collisions across
# all 83 corpus districts' rosters (findings report §9); persisted keys self-heal by re-normalizing
# through the CURRENT function (module docstring).
# 'sr'/'jrsr' added 2026-08-16 (#787, same asymmetry class): _base DELETES '/' (that deletion is
# load-bearing — the documented 'Brick Mill ES/ECC' == 'brick mill esecc' collision rides on it),
# so 'X Jr/Sr High' fuses to 'x jrsr' while 'X Jr Sr High' word-splits to 'x sr' ('jr' was a
# stopword, 'sr' was not) — one school, two keys. Both fused and split forms are now stopworded.
# Measured safe: 0 sr/jrsr collisions across the same 83 rosters.

# DISTRICT-TYPE qualifiers (#236) — stripped ONLY as a TRAILING run that ENDS IN A HARD DISTRICT
# MARKER (district / ISD / USD / … / SD), never mid-name and never bare. The #236 double-counts are a
# district qualifier APPENDED to a school's name ("Union Hill ISD", "Elmbrook District"); but
# 'unified'/'consolidated'/'independent' are also ordinary words inside real schools' proper names
# ("Meridian Consolidated School" is a different school than "Meridian School" — PR #247 review: the
# anywhere-strip merged them, so bare qualifiers now stay: "Lincoln Unified" keeps 'unified' unless a
# marker follows). community/county are allowed INSIDE a marker-terminated run ("Franklin Community
# School District") but never stripped bare (they distinguish schools: "Franklin County High" !=
# "Franklin High").
_DISTRICT_TAIL = re.compile(
    r"(?:^|\s)(?:(?:unified|consolidated|independent|community|county)\s+)*(?:schools?\s+)?"
    r"(?:district|isd|usd|cisd|cusd|ccsd|ufsd|csd|psd|sd)$")

# NCES SCH_NAME abbreviation TAILS (#499 PR-A, REQ-144) — the CCD directory abbreviates level/type
# words the full-word list above never sees ("Liberty Bell El Sch", "Southern Lehigh SHS"), so a
# roster slot and its extracted fact ("liberty bell") could never share a key. Stripped ONLY as a
# TRAILING run: "El" is also the Spanish article ("El Camino High" must keep it mid-name; a
# trailing "Roosevelt El" is safely the abbreviation). Fixed-point loop below handles cascades.
_NCES_TAIL = re.compile(r"(?:^|\s)(?:(?:el|elem|sch|schs|shs|jshs|jhs|ihs)\s*)+$")


def _base(name) -> str:
    """Lowercase, transliterate accents (NFKD: José -> jose, not the mangled 'jos'), turn hyphens/
    dashes into SPACES (so 'Lincoln-Unified' word-splits like 'Lincoln Unified' — deleting the hyphen
    fused the tokens and hid the suffix from the word-boundary strip), drop other punctuation,
    collapse whitespace."""
    s = unicodedata.normalize("NFKD", str(name).lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[-‐-―]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_school_strict(name) -> str:
    """The stripped key, with NO empty-key fallback: a name that is ALL type/qualifier words returns
    "" (falsy). This is the JUNK FILTER form — the #237 detector drops roster entries that strict-
    normalize to nothing (a scraped 'School District' header is not a school), which the fallback in
    norm_school would smuggle through as a matchable key. Strips to a FIXED POINT (a generic word's
    removal can expose a new marker tail, e.g. "Lincoln ISD Academy" → "lincoln isd" → "lincoln") —
    the loop is what makes the key idempotent."""
    if not name:
        return ""
    s = _base(name)
    while True:
        t = re.sub(r"\s+", " ", _GENERIC.sub("", _DISTRICT_TAIL.sub("", _NCES_TAIL.sub("", s)))).strip()
        if t == s:
            return t
        s = t


def norm_school(name) -> str:
    """The match key. Empty-key guard (#236): a name that is ALL stopwords (e.g. "The School
    District") would strip to "" and merge every all-type name into one bucket — fall back to the
    punctuation-normalized (un-stripped) form so those stay distinct. Use norm_school_strict when
    you want the falsy "" to FILTER such names instead."""
    if not name:
        return ""
    stripped = norm_school_strict(name)
    return stripped or _base(name)


# ---------------------------------------------------------------------------------------------
# Roster-anchored identity resolution (#693/#721) — measured design in
# docs/technical-notes/learning-loop-reports/2026-08-15-693-721-roster-anchored-identity.md.
#
# norm_school above is deliberately UNTOUCHED: it is the persisted key (REQ-117) and the 2026-08-15
# measurement showed stopword widening reaches 4 pairs corpus-wide while the roster reaches 323+.
# Resolution layers ON TOP, at the consensus boundary, and is band-scoped — the band in the
# grouping key is the only thing separating the 35 level-collapse districts (APOPKA ELEMENTARY /
# MIDDLE / HIGH all norm to 'apopka'), so every rule below matches within the claimed band FIRST
# and falls to cross-band only when the claimed band has no candidate (that fall-through is what
# detects #721's multiband campuses and wrong-band claims).
# ---------------------------------------------------------------------------------------------

# Grade-span tokens glued onto extracted names ('kinston k12') — these never distinguish two
# schools within one band, unlike bare numbers ("PS 121" vs "PS 122"), so ONLY these exact shapes
# are stripped, never digit tokens generally. DIGITS ARE REQUIRED on the k-forms: bare 'prek'/'pk'
# is an excluded-GRADE marker, not a span — 'bucks hill prek' is plausibly a preschool program
# whose schedule must NOT fuse into Bucks Hill Elementary; it stays unmatched so the rung-4
# exclusion screen adjudicates it (2026-08-15 corpus validation). jr/sr moved to _GENERIC (#787):
# norm_school strips them before the resolver ever sees a key, so a span-alternative here was dead.
_GRADE_SPAN = re.compile(r"\b(?:pre|p)?k\s*\d{1,2}\b"
                         r"|\b\d{1,2}\s*(?:th)?\s+grades?\b")


def _strip_grade_span(nkey: str) -> str:
    return re.sub(r"\s+", " ", _GRADE_SPAN.sub(" ", nkey)).strip()


def _acronyms(raw_name: str) -> set:
    """Acronym forms of a roster school's FULL name — computed on the un-stripped base because the
    level words carry the acronym's tail ('Essex Middle School' -> 'ems'; the stripped form loses
    it, a 5x undercount in the 2026-08-15 measurement). Two variants: the whole name, and the name
    minus trailing 'school(s)' ('Albert D. Lawton School' -> 'adls' AND 'adl')."""
    toks = _base(raw_name).split()
    out = set()
    for cut in (toks, toks[:-1] if toks and toks[-1] in ("school", "schools") else None):
        if cut and len(cut) > 1:
            out.add("".join(t[0] for t in cut))
    return out


def resolve_school_identity(name, band, roster_recs):
    """Resolve an extracted school name to a roster identity. Pure.

    roster_recs: {band: [{"name": raw roster name, "school_id": NCESSCH}, ...]} — the Stage-1 slot
    spine with ids (a superset of #707's names-only roster_by_band; both ride the same context).

    Returns (key, info):
      key  — the normalized identity to group on: the ROSTER school's norm key when uniquely
             resolved (so variant spellings collide), else norm_school(name) unchanged.
      info — None when the roster offers nothing (unmatched: caller applies the #693 rung-4/5
             screen + name-in-lieu policy), else a dict:
               {"rule": exact|grade_span|leading_initial|acronym|token_set|token_subset,
                "school_id": ..., "roster_school": raw name,
                "rostered_bands": [bands this school_id appears in]}         — resolved, or
               {"rule": "ambiguous", "candidates": [raw names]}              — 2+ roster schools
                match: the split MUST be kept (#681's false-agreement defect otherwise; §7 of the
                findings report), the info only makes the ambiguity gate@8-visible.

    The judge cannot mint an identity (the #707 rule): this changes GROUPING only — consensus
    thresholds are untouched by the caller's contract."""
    nkey = norm_school(name)
    if not nkey or not roster_recs:
        return nkey, None
    # #777: a strict-DEGENERATE key ('hs', 'the schools' — all type/referent words) must never
    # resolve: 'HS' is a band label, not a name, and an acronym coincidence ('Hill School' -> hs)
    # would mint a specific school_id from an unspecific extraction, bypassing the #245 guard and
    # #707's roster_unique/band_referent machinery, which own exactly this class.
    if not norm_school_strict(name):
        return nkey, None

    # Index the roster once per call: per-band and cross-band views, each key -> {school_id}.
    # #786: an id-LESS roster entry (blank NCESSCH — newly-opened/closing CCD rows) indexes under
    # a name-based sentinel: it still COUNTS as a candidate for "is this name unique" (dropping it
    # turned a real 2-candidate ambiguity into a false-confident match), but a sentinel can never
    # be the resolved winner — no identity without an id.
    def _sid_of(r):
        return r.get("school_id") or f"_noid:{norm_school(r.get('name'))}"

    def _index(recs):
        by_norm, by_acr, toks = {}, {}, []
        for r in recs:
            rk = norm_school(r.get("name"))
            if not rk:
                continue
            sid = _sid_of(r)
            by_norm.setdefault(rk, set()).add(sid)
            by_norm.setdefault(_strip_grade_span(rk), set()).add(sid)
            for a in _acronyms(r.get("name")):
                by_acr.setdefault(a, set()).add(sid)
            toks.append((frozenset(rk.split()), sid))
        return by_norm, by_acr, toks

    id_meta = {}                     # sid (real or sentinel) -> (raw name, [bands])
    for b, recs in roster_recs.items():
        for r in recs or []:
            raw = r.get("name")
            if not norm_school(raw):
                continue
            meta = id_meta.setdefault(_sid_of(r), (raw, []))
            if b not in meta[1]:
                meta[1].append(b)

    def _try(recs):
        """Run the FORMS x RULES ladder against one roster view; return (rule, {school_id}) or
        None. Forms are cheap artifact-corrections of the extracted key (grade-span token,
        leading single-letter); each form gets the full rule ladder — 'x hannah gibbons' needs
        leading-initial THEN token-subset to reach 'Hannah Gibbons-Nottingham' (2026-08-15
        corpus validation). A form is only safe because a REAL distinguishing token exact-matches
        at the unmodified form first and never falls through."""
        by_norm, by_acr, toks = _index(recs)
        stripped = _strip_grade_span(nkey)
        words = nkey.split()
        no_initial = " ".join(words[1:]) if len(words) > 1 and len(words[0]) == 1 else None
        forms = [("", nkey)]
        if stripped != nkey:
            forms.append(("grade_span", stripped))
        if no_initial:
            forms.append(("leading_initial", no_initial))
        for form_name, form in forms:
            ktoks = frozenset(form.split())
            for rule, hits in (
                    ("exact", by_norm.get(form)),
                    ("acronym", by_acr.get(form.replace(" ", ""))),
                    ("token_set", {sid for rt, sid in toks if rt == ktoks} or None),
                    # key ⊂ roster tokens ('lincoln west science health' ⊂ roster). The REVERSE
                    # direction (roster ⊂ key) is deliberately absent: measured value-negative —
                    # it minted 'regular day bell schedule' -> Bell Middle (findings report §3).
                    ("token_subset", {sid for rt, sid in toks if ktoks and ktoks < rt} or None)):
                # #790: the leading_initial form composes with NEAR-EXACT rules only (exact /
                # token_set). Initial-strip + subset was one guess stacked on another: against a
                # stale roster missing the true 'J Edgar Hoover', 'j edgar hoover' confidently
                # bound to an unrelated 'Edgar Hoover Annex'. Costs the one corpus case that
                # needed the composite (x-hannah, Cleveland) — it now lands roster_unmatched,
                # which is safe, visible, and still counted (findings report §9 review round).
                if form_name == "leading_initial" and rule not in ("exact", "token_set"):
                    continue
                if hits:
                    return (f"{form_name}+{rule}" if form_name and rule != "exact"
                            else form_name or rule), hits
        return None

    # Claimed band first (level-collapse safety), then cross-band (multiband/wrong-band detection).
    for view in ((roster_recs.get(band) or []),
                 [r for b, recs in roster_recs.items() for r in (recs or [])]):
        hit = _try(view)
        if not hit:
            continue
        rule, sids = hit
        if len(sids) > 1:
            return nkey, {"rule": "ambiguous",
                          "candidates": sorted(id_meta[s][0] for s in sids if s in id_meta)}
        sid = next(iter(sids))
        if str(sid).startswith("_noid:"):
            # #786: the unique candidate has no NCESSCH — it disambiguated the field (no false
            # confidence in a sibling), but an identity cannot be minted without an id.
            return nkey, None
        raw, bands = id_meta.get(sid, (None, []))
        return norm_school(raw), {"rule": rule, "school_id": sid, "roster_school": raw,
                                  "rostered_bands": sorted(bands), "resolved_from": nkey}
    return nkey, None
