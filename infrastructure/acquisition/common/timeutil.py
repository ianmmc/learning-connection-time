"""One home for the acquisition pipeline's UTC timestamp strings (issue #147).

Two formats were each hand-rolled ~identically across the stages:
  * `utcnow()`   — the human/DB ISO form `YYYY-MM-DDTHH:MM:SSZ`, used as SQLAlchemy column defaults
    (`default=utcnow`, so the NAME is load-bearing — keep it importable/stable) and event timestamps;
  * `fs_stamp()` — the filesystem-safe compact form `YYYYMMDDTHHMMSSZ` for receipt/handoff filenames.

Both intentionally second-resolution and Zulu-suffixed. Importing from here keeps the format from
drifting between stages (a mixed format would break the ≤3-year temporal comparisons + filename sorts).
"""
from datetime import datetime, timezone


def utcnow() -> str:
    """UTC now as `YYYY-MM-DDTHH:MM:SSZ` — the pipeline's canonical timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fs_stamp() -> str:
    """UTC now as `YYYYMMDDTHHMMSSZ` — filesystem-safe (no colons) for receipt/handoff filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
