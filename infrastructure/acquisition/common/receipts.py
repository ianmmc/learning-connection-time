"""Shared per-district receipt writer for the acquisition pipeline (REQ-164).

Every stage's per-district receipt is an ALWAYS-datetime-stamped, audit-only artifact written into the
district's ``lea-website-captures/<dir>/`` via this ONE crash-safe helper -- never a bespoke per-stage
``json.dump``. gov_db is the authoritative working store; these receipts are cross-checks + recovery
sources, NEVER read as input by an active-pipeline stage (governance §1; Decision-2, 2026-07-22).

Filename convention -- ``<basename>.<fs_stamp>.<writer>-<h8>.json``:
  * ``fs_stamp`` = ``timeutil.fs_stamp()`` (``YYYYMMDDTHHMMSSZ``) -- fixed-width, so a lexical filename
    sort IS chronological; the write is ALWAYS stamped, first run included (no fixed-'latest' name --
    humans sort by name/date, and receipts-are-audit-only removes any need for a stable latest name).
  * ``writer`` = ``"py"`` here / ``"node"`` in the Node capture writer. The tag makes per-writer hashes
    self-evidently per-writer, so an auditor never reads two different-writer hashes as "these differ"
    (the loose-with-writer-tag decision, 2026-07-22). The content hash is a WITHIN-writer same-second
    collision-breaker ONLY; cross-language hash agreement is neither required nor implied.
  * ``h8`` = first 8 hex of sha256 over the canonical payload MINUS ``VOLATILE_KEYS``, so a same-second
    re-run of identical content is idempotent (same filename) instead of a clobber.

Chronological order is carried by the timestamp; the finer ordering authority is ``state_event.event_id``
in gov_db, never the filename. Commit-before-receipt: callers write the receipt AFTER the gov_db commit,
so a crash may leave a LAGGING receipt (re-derivable) but never one AHEAD of the authoritative DB.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common.discover import slugify
from infrastructure.acquisition.common.timeutil import fs_stamp

WRITER = "py"

# Keys stripped before hashing so a wall-clock field a payload carries can't perturb same-content
# idempotency (mirrors the Stage-6 handoff hash's 'price-independent identity'). The Node writer strips
# the same set. Kept small + explicit -- this is a collision-breaker, not a semantic content fingerprint.
VOLATILE_KEYS = frozenset({"generated_at"})


def _capture_root() -> Path:
    """RAW_CAPTURES for receipt writes. Under pytest, a NON-overridden (still-default) RAW_CAPTURES is
    redirected to a per-process quarantine, so a test that drives a stage write never lands a receipt in
    the real ``data/raw`` tree (the issue-#178 guard_tracked_backup pattern, applied to captures). A
    test that EXPLICITLY monkeypatches ``paths.RAW_CAPTURES`` to its own tmp dir passes through untouched
    -- that is deliberate isolation (test_receipts, the Stage-9 integration env fixture)."""
    root = paths.RAW_CAPTURES
    if "PYTEST_CURRENT_TEST" in os.environ and root == (paths.DATA_ROOT / "raw" / "lea-website-captures"):
        q = Path(tempfile.gettempdir()) / "lct-test-quarantine" / "lea-website-captures"
        q.mkdir(parents=True, exist_ok=True)
        return q
    return root


def district_capture_dir(district_id: str, name: str = "") -> Path:
    """The district's ``lea-website-captures/`` dir. The dir is ``<district_id>_<slug>`` and
    ``district_id`` is the REAL disambiguator (the slug is human-readability only -- slugify's own
    contract), so an EXISTING dir is resolved by a ``<district_id>_*`` glob. That makes every stage
    land in the SAME dir regardless of which name source it holds (the gov batch name at Stage 2-8 vs.
    the LCT ``districts`` name at Stage 9 can differ in case/whitespace across the two DBs). Falls back
    to constructing ``<district_id>_<slug>`` from ``name`` when no dir exists yet (first write). Kept in
    ``common/`` so no stage module is imported (import-linter layering)."""
    root = _capture_root()
    if root.is_dir():
        existing = sorted(root.glob(f"{district_id}_*"))
        if existing:
            return existing[0]
    return root / f"{district_id}_{slugify(name)}"


def _hashable(payload):
    """The payload minus VOLATILE_KEYS (top-level only) -- what the content hash is taken over."""
    if isinstance(payload, dict):
        return {k: v for k, v in payload.items() if k not in VOLATILE_KEYS}
    return payload


def content_hash(payload) -> str:
    """First 8 hex of sha256 over the canonical (sorted-key, compact) payload minus VOLATILE_KEYS.
    Deterministic within THIS (Python) writer; deliberately NOT required to match the Node writer's
    hash (the loose decision) -- the writer tag in the filename keeps the two self-evidently distinct."""
    canon = json.dumps(_hashable(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:8]


def receipt_filename(basename: str, payload, *, ts: str, writer: str = WRITER) -> str:
    """``<basename>.<ts>.<writer>-<h8>.json`` -- the one place the convention is spelled out."""
    return f"{basename}.{ts}.{writer}-{content_hash(payload)}.json"


def write_receipt(district_id: str, name: str, basename: str, payload, *,
                  writer: str = WRITER) -> Path:
    """Write a per-district receipt (always-stamped, atomic) and return its path. A same-second write of
    byte-identical content is idempotent (identical filename -> no re-write), never a clobber. Payload is
    written AS GIVEN (dict or list) -- schema-agnostic; the timestamp authority is the filename + gov_db,
    so nothing is injected into the payload."""
    d = district_capture_dir(district_id, name)
    d.mkdir(parents=True, exist_ok=True)
    path = d / receipt_filename(basename, payload, ts=fs_stamp(), writer=writer)
    if not path.exists():
        paths.atomic_write_json(path, payload)
    return path


def iter_receipts(district_id: str, name: str, basename: str) -> List[Path]:
    """All stamped receipts for ``(district, basename)``, oldest -> newest. Sorted by full filename,
    which is chronological because the ``<fs_stamp>`` segment is fixed-width and lexically ordered; a
    same-second tie then breaks DETERMINISTICALLY on the trailing ``<writer>-<h8>`` (never on filesystem
    glob order). Excludes the legacy unstamped ``<basename>.json`` (handled by the backfill) and any
    different basename sharing a prefix (the ``.`` after basename anchors the glob)."""
    d = district_capture_dir(district_id, name)
    if not d.is_dir():
        return []
    return sorted(d.glob(f"{basename}.*.json"), key=lambda p: p.name)


def latest_receipt(district_id: str, name: str, basename: str) -> Optional[Path]:
    """The newest stamped receipt for ``(district, basename)``, or None -- THE resolver every reader
    uses instead of a fixed filename under always-stamp."""
    rs = iter_receipts(district_id, name, basename)
    return rs[-1] if rs else None
