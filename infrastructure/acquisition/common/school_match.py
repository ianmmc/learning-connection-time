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
    r"|es|ms|hs)\b")

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
        t = re.sub(r"\s+", " ", _GENERIC.sub("", _DISTRICT_TAIL.sub("", s))).strip()
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
