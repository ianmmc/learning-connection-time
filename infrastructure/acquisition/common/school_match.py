"""Shared school-name normalization — the identity key for matching a school across sources (REQ-117).

A school's match key is its name with punctuation and level/type words stripped, so `Brick Mill
ES/ECC` and `brick mill esecc` collide. Stage 8 consensus uses it to group a school across models;
the Stage 7 GT validator uses it to match our extracted school to the hand-verified one. They MUST
use the SAME function or matching silently drifts — hence one home in `common`. Pure.
"""
import re

# Level/type words + US district-type qualifiers. The district suffixes (#236) collapse a school and
# its district-suffixed variant to one key — "Union Hill" == "Union Hill ISD", "Elmbrook District" ==
# "Elmbrook Schools" — both real Stage-7 double-counts. Deliberately EXCLUDES county/community/public:
# those can be part of a school's distinguishing name, not just its type ("Franklin County High" vs
# "Franklin High" are different schools), so stripping them would over-merge.
_STOPWORDS = re.compile(
    r"\b(elementary|middle|high|school|schools|jr|junior|senior|academy|the|of|at"
    r"|isd|usd|cisd|cusd|ccsd|ufsd|csd|psd|sd|district|unified|consolidated|independent)\b")


def norm_school(name) -> str:
    """Lowercase → drop non-alphanumerics → strip level/type + district-type stopwords → collapse
    whitespace. Empty-key guard (#236): a name that is ALL stopwords (e.g. "The School District")
    would strip to "" and merge every all-type name into one bucket — fall back to the
    punctuation-normalized (un-stripped) form so those stay distinct."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9 ]", "", str(name).lower())
    stripped = re.sub(r"\s+", " ", _STOPWORDS.sub("", s)).strip()
    return stripped or re.sub(r"\s+", " ", s).strip()
