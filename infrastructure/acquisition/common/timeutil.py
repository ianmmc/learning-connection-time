"""One home for the acquisition pipeline's UTC timestamp strings (issue #147).

Two formats were each hand-rolled ~identically across the stages:
  * `utcnow()`   — the human/DB ISO form `YYYY-MM-DDTHH:MM:SSZ`, used as SQLAlchemy column defaults
    (`default=utcnow`, so the NAME is load-bearing — keep it importable/stable) and event timestamps;
  * `fs_stamp()` — the filesystem-safe compact form `YYYYMMDDTHHMMSSZ` for receipt/handoff filenames.

Both intentionally second-resolution and Zulu-suffixed. Importing from here keeps the format from
drifting between stages (a mixed format would break the ≤3-year temporal comparisons + filename sorts).
"""
import re as _re
from datetime import datetime, timezone
from typing import Optional


def hhmm_to_min(t) -> Optional[int]:
    """Canonical 'HH:MM' (24h) → minutes-since-midnight, or None if absent/unparseable (#638).
    ONE parser for the pipeline's canonical clock strings — previously duplicated as
    stage8_aggregate.aggregate._to_min and stage9_incorporate.provenance._hhmm_to_min (a third
    near-miss, build_signals.to_minutes, is a DIFFERENT function: pre-split ints + meridiem
    heuristics for raw-text extraction, deliberately not unified). Tolerant of surrounding
    whitespace/suffixes via prefix match, same as the original aggregate regex."""
    if not t:
        return None
    m = _re.match(r"\s*(\d{1,2}):(\d{2})", str(t))
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def utcnow() -> str:
    """UTC now as `YYYY-MM-DDTHH:MM:SSZ` — the pipeline's canonical timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fs_stamp() -> str:
    """UTC now as `YYYYMMDDTHHMMSSZ` — filesystem-safe (no colons) for receipt/handoff filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fs_stamp_from_iso(iso: str) -> str:
    """Convert a stored ISO timestamp (`utcnow()`'s `YYYY-MM-DDTHH:MM:SSZ`, tolerant of a `+00:00`
    offset or fractional seconds) to the `fs_stamp()` filename form `YYYYMMDDTHHMMSSZ`. Used by the
    receipt backfill to stamp a legacy file from its gov_db `state_event.created_at` rather than "now"
    (issue-#164 / REQ-164: NEVER the filesystem create-date). Raises ValueError on an unparseable value
    so the caller can fall through its source chain instead of writing a wrong stamp."""
    dt = datetime.fromisoformat(iso.strip().replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fs_stamp_from_epoch(epoch: float) -> str:
    """Convert a POSIX timestamp (e.g. a file's `st_mtime`) to the `fs_stamp()` filename form. The
    receipt backfill's last-resort source for an orphan with no gov_db event (logged when used)."""
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
