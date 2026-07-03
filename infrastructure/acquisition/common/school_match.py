"""Shared school-name normalization — the identity key for matching a school across sources (REQ-117).

A school's match key is its name with punctuation and level/type words stripped, so `Brick Mill
ES/ECC` and `brick mill esecc` collide. Stage 8 consensus uses it to group a school across models;
the Stage 7 GT validator uses it to match our extracted school to the hand-verified one. They MUST
use the SAME function or matching silently drifts — hence one home in `common`. Pure.
"""
import re

_STOPWORDS = re.compile(r"\b(elementary|middle|high|school|jr|junior|senior|academy|the|of|at)\b")


def norm_school(name) -> str:
    """Lowercase → drop non-alphanumerics → strip level/type stopwords → collapse whitespace."""
    if not name:
        return ""
    s = re.sub(r"[^a-z0-9 ]", "", str(name).lower())
    s = _STOPWORDS.sub("", s)
    return re.sub(r"\s+", " ", s).strip()
