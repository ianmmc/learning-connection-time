"""Stage 1 (Queue) batch working-store operations (REQ-102).

The governance DB is the working store; `batch_NNNNN.json` is the receipt regenerated from rows. Every
function takes a Session and does NOT commit — the caller controls the transaction (the console wraps
in `gdb.session_scope`; tests use the rolling-back `gov_session` fixture). The gate@1 edit operations
(reject district / reject school / add school) are soft flips of `included` / row inserts, so nothing
is ever destroyed — the full proposed batch stays auditable.
"""
import json

from sqlalchemy import select

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict, BatchSchool, utcnow

BANDS = ("elementary", "middle", "high")
_META_KEYS = ("nces_school_counts_criteria", "stratification", "school_cap_per_band",
              "school_selection_when_over_cap")
_SCHOOL_FIELDS = ("school_id", "name", "is_charter", "level", "gslo", "gshi")


# ---------------------------------------------------------------- create (doc -> rows)
def create_batch(sess, batch_doc: dict, *, batch_type: str = "first-run", actor: str) -> None:
    """Write a freshly-built batch_doc into the working store (one Batch + BatchDistrict/BatchSchool
    rows). A multi-band school collapses to ONE BatchSchool row carrying all its bands. Flushes so the
    rows are visible to a same-transaction to_receipt_doc()."""
    bid = batch_doc["batch_id"]
    sess.add(Batch(
        batch_id=bid, batch_type=batch_type, status="draft",
        nces_year=batch_doc.get("nces_year", ""),
        created_at=batch_doc.get("created") or utcnow(), created_by=actor,
        meta_json={k: batch_doc[k] for k in _META_KEYS if k in batch_doc},
    ))
    for i, d in enumerate(batch_doc["districts"]):
        sbb = d.get("schools_by_band", {})
        order = d.get("band_processing_order") or list(sbb.keys())
        band_meta = {b: {k: sbb[b].get(k) for k in ("n_candidates", "n_unclaimed_at_selection", "n_selected")}
                     for b in sbb}
        sess.add(BatchDistrict(
            batch_id=bid, district_id=d["district_id"], ord=i, name=d["name"], state=d["state"],
            domain=d.get("domain", ""), enrollment_k12=d.get("enrollment_k12"),
            lea_claimed_bands=d.get("lea_claimed_bands", []),
            nces_school_counts=d.get("nces_school_counts", {}),
            band_processing_order=order, band_meta=band_meta, included=True,
        ))
        by_school: dict = {}
        for b in order:
            for s in sbb.get(b, {}).get("schools", []):
                row = by_school.setdefault(s["school_id"], {**s, "bands": []})
                if b not in row["bands"]:
                    row["bands"].append(b)
        for sid, s in by_school.items():
            sess.add(BatchSchool(
                batch_id=bid, district_id=d["district_id"], school_id=sid,
                name=s.get("name", ""), is_charter=s.get("is_charter"), level=s.get("level"),
                gslo=s.get("gslo"), gshi=s.get("gshi"), bands=s["bands"], included=True, source="stratified",
            ))
    sess.flush()


# ---------------------------------------------------------------- serialize (rows -> doc)
def _bands_for_district(d: BatchDistrict, schools: list) -> list:
    """band_processing_order, plus any extra band an added school introduced (kept stable)."""
    order = list(d.band_processing_order or [])
    for s in schools:
        for b in (s.bands or []):
            if b not in order:
                order.append(b)
    return order


def _district_doc(sess, d: BatchDistrict, *, included_only: bool, with_flags: bool) -> dict:
    q = select(BatchSchool).where(BatchSchool.batch_id == d.batch_id,
                                  BatchSchool.district_id == d.district_id)
    if included_only:
        q = q.where(BatchSchool.included.is_(True))
    schools = list(sess.scalars(q))
    bmeta = d.band_meta or {}
    sbb = {}
    for b in _bands_for_district(d, schools):
        band_schools = sorted((s for s in schools if b in (s.bands or [])), key=lambda s: s.school_id)
        meta = bmeta.get(b, {})
        sbb[b] = {
            "n_candidates": meta.get("n_candidates"),
            "n_unclaimed_at_selection": meta.get("n_unclaimed_at_selection"),
            "n_selected": sum(1 for s in band_schools if s.included),   # LIVE
            "schools": [_school_dict(s, with_flags) for s in band_schools],
        }
    doc = {
        "district_id": d.district_id, "name": d.name, "state": d.state, "domain": d.domain,
        "enrollment_k12": d.enrollment_k12, "lea_claimed_bands": d.lea_claimed_bands,
        "nces_school_counts": d.nces_school_counts, "band_processing_order": d.band_processing_order,
        "schools_by_band": sbb,
    }
    if with_flags:
        doc["included"] = d.included
    return doc


def _school_dict(s: BatchSchool, with_flags: bool) -> dict:
    out = {"school_id": s.school_id, "name": s.name, "is_charter": s.is_charter,
           "level": s.level, "gslo": s.gslo, "gshi": s.gshi}
    if with_flags:
        out["included"] = s.included
        out["source"] = s.source
    return out


def _ordered_districts(sess, batch_id: str, *, included_only: bool) -> list:
    q = select(BatchDistrict).where(BatchDistrict.batch_id == batch_id)
    if included_only:
        q = q.where(BatchDistrict.included.is_(True))
    return list(sess.scalars(q.order_by(BatchDistrict.ord)))


def to_receipt_doc(sess, batch_id: str) -> dict:
    """The canonical batch_doc (INCLUDED rows only, original shape) — what the receipt file holds and
    what Stage 2 consumes. Raises KeyError if the batch is unknown."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    districts = [_district_doc(sess, d, included_only=True, with_flags=False)
                for d in _ordered_districts(sess, batch_id, included_only=True)]
    return {
        "batch_id": b.batch_id, "created": b.created_at, "n": len(districts),
        "nces_year": b.nces_year, **(b.meta_json or {}), "districts": districts,
    }


def to_view(sess, batch_id: str) -> dict:
    """The gate@1 review payload — lifecycle fields + ALL rows (included AND soft-rejected) with their
    flags, so the human sees what was proposed and what they've dropped."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    districts = [_district_doc(sess, d, included_only=False, with_flags=True)
                for d in _ordered_districts(sess, batch_id, included_only=False)]
    return {
        "batch_id": b.batch_id, "batch_type": b.batch_type, "status": b.status,
        "nces_year": b.nces_year, "created_at": b.created_at, "created_by": b.created_by,
        "approved_at": b.approved_at, "approved_by": b.approved_by,
        "n_included": sum(1 for d in districts if d["included"]),
        **(b.meta_json or {}), "districts": districts,
    }


def list_batches(sess) -> list:
    """Batch lifecycle rows for the queue list (n_districts = currently-included count)."""
    out = []
    for b in sess.scalars(select(Batch).order_by(Batch.batch_id)):
        n = len(list(sess.scalars(select(BatchDistrict.district_id).where(
            BatchDistrict.batch_id == b.batch_id, BatchDistrict.included.is_(True)))))
        out.append({"batch_id": b.batch_id, "batch_type": b.batch_type, "status": b.status,
                    "nces_year": b.nces_year, "n_districts": n, "created_at": b.created_at,
                    "created_by": b.created_by, "approved_at": b.approved_at, "approved_by": b.approved_by})
    return out


# ---------------------------------------------------------------- receipt (rows -> file)
def write_receipt(sess, batch_id: str):
    """Regenerate batch_NNNNN.json from the rows — the auditable receipt always reflects the working
    store. Overwrites in place during draft (the DB is authoritative; the receipt is the snapshot)."""
    doc = to_receipt_doc(sess, batch_id)
    paths.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = paths.QUEUE_DIR / f"{batch_id}.json"
    out_path.write_text(json.dumps(doc, indent=2))
    return out_path


# ---------------------------------------------------------------- gate@1 edits (soft) + lifecycle
class BatchLocked(Exception):
    """Raised when an edit is attempted on an already-approved batch (re-open to draft first)."""


def _require_draft(b: Batch) -> None:
    if b is None:
        raise KeyError("batch")
    if b.status != "draft":
        raise BatchLocked(f"{b.batch_id} is {b.status}; re-open to draft before editing")


def reject_district(sess, batch_id: str, district_id: str) -> None:
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    d = sess.get(BatchDistrict, (batch_id, district_id))
    if d is None:
        raise KeyError(district_id)
    d.included = False
    sess.flush()


def reject_school(sess, batch_id: str, district_id: str, school_id: str) -> None:
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    s = sess.get(BatchSchool, (batch_id, district_id, school_id))
    if s is None:
        raise KeyError(school_id)
    s.included = False
    sess.flush()


def restore_district(sess, batch_id: str, district_id: str) -> None:
    """Reverse a reject_district (set included back to True) — keeps gate@1 editing reversible during
    draft so a mis-reject isn't a dead end."""
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    d = sess.get(BatchDistrict, (batch_id, district_id))
    if d is None:
        raise KeyError(district_id)
    d.included = True
    sess.flush()


def restore_school(sess, batch_id: str, district_id: str, school_id: str) -> None:
    """Reverse a reject_school. (A genuinely NEW school is added via add_school instead.)"""
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    s = sess.get(BatchSchool, (batch_id, district_id, school_id))
    if s is None:
        raise KeyError(school_id)
    s.included = True
    sess.flush()


def add_school(sess, batch_id: str, district_id: str, school: dict, bands: list) -> None:
    """Add a school to a district's targeting (story 31). `school` carries the NCES fields
    (school_id/name/level/gslo/gshi/is_charter) the caller pulled from the eligible pool; `bands` is
    which band(s) to target it in. Re-including a previously-rejected row is also an add."""
    b = sess.get(Batch, batch_id)
    _require_draft(b)
    sid = school["school_id"]
    existing = sess.get(BatchSchool, (batch_id, district_id, sid))
    if existing is not None:
        existing.included = True
        existing.bands = sorted(set((existing.bands or []) + bands))
    else:
        sess.add(BatchSchool(
            batch_id=batch_id, district_id=district_id, school_id=sid, name=school.get("name", ""),
            is_charter=school.get("is_charter"), level=school.get("level"), gslo=school.get("gslo"),
            gshi=school.get("gshi"), bands=list(bands), included=True, source="manual_add"))
    sess.flush()


def approve_batch(sess, batch_id: str, actor: str) -> None:
    """gate@1 approval — the batch-level transition (the unit that advances to discovery)."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    if b.status != "draft":
        raise BatchLocked(f"{batch_id} is already {b.status}")
    b.status = "approved"
    b.approved_at = utcnow()
    b.approved_by = actor
    sess.flush()


def reopen_batch(sess, batch_id: str, actor: str) -> None:
    """Re-open an approved batch back to draft for further editing (clears the approval stamp)."""
    b = sess.get(Batch, batch_id)
    if b is None:
        raise KeyError(batch_id)
    b.status = "draft"
    b.approved_at = None
    b.approved_by = None
    sess.flush()


# ---------------------------------------------------------------- next id (DB rows + on-disk receipts)
def next_batch_number(sess) -> int:
    """The next free batch number, considering BOTH the DB batch rows and any batch_*.json receipts on
    disk (a hand-run CLI batch may exist as a file before it's a row)."""
    nums = []
    for (bid,) in sess.execute(select(Batch.batch_id)):
        if bid.startswith("batch_") and bid[6:].isdigit():
            nums.append(int(bid[6:]))
    if paths.QUEUE_DIR.exists():
        for p in paths.QUEUE_DIR.glob("batch_*.json"):
            stem = p.stem[6:]
            if stem.isdigit():
                nums.append(int(stem))
    return (max(nums) + 1) if nums else 1
