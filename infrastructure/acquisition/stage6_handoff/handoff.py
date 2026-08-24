"""Stage 6 immutable handoff artifact (REQ-101): freeze "what we sent" to the council.

`freeze()` turns an in-memory handoff package (from `package.assemble_package`) into the frozen
`handoff_<hash>_<ts>.json` doc (governance §5): it embeds the council configs actually used + the
per-district `(config,labels,data)` fingerprints, and stamps a **content-identity hash**.

The hash is deliberately **price-independent** — computed over *what we sent* (the reps, their routing,
the council configs, the fingerprints), NOT the dollar estimates — so a later reprice (live OpenRouter
pricing, §3C C.0) or a cost-model retune cannot rewrite a past dispatch's identity. `write()` is
immutable: a frozen dispatch file is never overwritten (a new dispatch is a new file).

Pure + filesystem; no DB. The DB index row + the `dispatched` state_event are recorded by the app-layer
bridge (which has the gov session), the next slice.
"""
import hashlib
import json
from pathlib import Path

from infrastructure.acquisition.common.benchmark import effective_dispatch_type
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common.timeutil import utcnow as _now

DEFAULT_ROOT = paths.HANDOFFS_DIR   # ONE spelling — base-layer readers (#717) use paths directly




def _councils_used(package: dict, councils: dict) -> dict:
    """The subset of the registry actually referenced by the package's reps — frozen into the doc so
    'what config we sent' is recoverable even if the registry later changes."""
    used = set()
    for d in package.get("districts", []):
        for r in d.get("records", []):
            for rep in r.get("reps", []):
                used.update(rep.get("councils", []))
    return {cid: councils[cid] for cid in sorted(used) if cid in councils}


def _identity(package: dict, used_councils: dict, fingerprints: dict) -> dict:
    """The price-INDEPENDENT content that defines this dispatch's identity (drops all dollar fields).

    ORDER-INSENSITIVE (issue #52): districts / records / reps are sorted here so the same selection
    hashes identically regardless of the order it was assembled in (e.g. the console sending district
    ids in click order). NOTE: adding this sort (and the `pages` field, issue #38) CHANGES the identity
    hash future dispatches compute for content that would previously have hashed differently — that's
    fine: no stored hash is ever compared against a recomputed one (the 409 dedup only compares two
    freshly computed hashes), so past frozen artifacts stand untouched."""
    dist = []
    for d in package.get("districts", []):
        recs = []
        for r in d.get("records", []):
            reps = sorted(
                ({"file": rep.get("file"), "kind": rep.get("kind"), "pages": rep.get("pages"),
                  "councils": rep.get("councils"), "fidelity_suspect": rep.get("fidelity_suspect")}
                 for rep in r.get("reps", [])),
                key=lambda x: (x["file"] or "", x["kind"] or ""))
            recs.append({"rec_key": r.get("rec_key"), "decision": r.get("decision"), "reps": reps})
        recs.sort(key=lambda x: x["rec_key"] or "")
        dist.append({"district_id": d.get("district_id"), "records": recs})
    dist.sort(key=lambda x: x["district_id"] or "")
    # `verified_only` is part of identity: a training-grade dispatch (labeled targets only) is a
    # distinct artifact from a default one even when the reps happen to coincide (no hash collision).
    # `dispatch_type` (#618) rides for exactly the same reason: a BENCHMARK dispatch of the same reps
    # is a different artifact from a production one — it terminates at gate@7 and never reaches the
    # LCT write. Because package_identity() reuses this function, the gate@6 preview->freeze staleness
    # check (issue #37) covers a type flip for free: a draft previewed as production and frozen as
    # benchmark computes a different identity and 409s instead of silently substituting.
    # `redo` (#717/#905) rides for the same reason again: it changes WHICH reps compose (the
    # already-extracted delta is skipped), so a declared redo is a different artifact from a default
    # dispatch — and the frozen receipt must record that the redo was DECLARED, so a later audit of
    # "why was this district re-bought?" is answerable from the artifact alone
    # (derive-provenance-from-receipts). Including it here also makes the #37 preview→freeze
    # staleness gate cover a redo flip for free, exactly as it covers a dispatch_type flip.
    return {"districts": dist, "councils": used_councils, "fingerprints": fingerprints,
            "verified_only": bool(package.get("verified_only", False)),
            "dispatch_type": effective_dispatch_type(package),
            "redo": bool(package.get("redo", False))}


def package_identity(package: dict) -> str:
    """Public identity hash of an UNFROZEN package — the gate@6 preview→freeze staleness token
    (issue #37). Covers exactly what the human reviewed: the sorted districts/records/reps (incl.
    each rep's routed councils + overrides, via rep['councils']), the verified_only mode, and the
    dispatch_type (#618 — a preview-as-production / freeze-as-benchmark flip must 409, not slip); NO
    fingerprints and NO council configs (a preview has neither), and price-independent like the
    frozen hash. Preview and dispatch both compute it from a freshly built package: equal hashes ⇒
    the release content the human approved is what dispatch is about to freeze."""
    identity = _identity(package, {}, {})
    return hashlib.md5(json.dumps(identity, sort_keys=True, ensure_ascii=False)
                       .encode("utf-8")).hexdigest()[:12]


def freeze(package: dict, councils: dict, fingerprints: dict, created_by: str = "human") -> dict:
    """Build the immutable handoff doc from a package + the council registry + per-district fingerprints."""
    used = _councils_used(package, councils)
    identity = _identity(package, used, fingerprints)
    h = hashlib.md5(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    return {
        "handoff_hash": h, "created_at": _now(), "created_by": created_by,
        "verified_only": bool(package.get("verified_only", False)),
        # #618: the frozen doc RECORDS its own type, so the artifact on disk is self-describing —
        # "was this dispatch benchmark?" must be answerable from the receipt alone, never only from a
        # DB row that could be lost or disagree (the derive-provenance-from-receipts convention).
        "dispatch_type": effective_dispatch_type(package),
        # #717/#905: whether this dispatch was a DECLARED redo (already-extracted delta skipped) —
        # self-describing for the same reason dispatch_type is: the artifact alone must answer it.
        "redo": bool(package.get("redo", False)),
        "fingerprints": fingerprints, "councils": used,
        "cost": package.get("cost"), "districts": package.get("districts", []),
    }


def handoff_filename(doc: dict) -> str:
    ts = doc["created_at"].replace(":", "").replace("-", "")
    return f"handoff_{doc['handoff_hash']}_{ts}.json"


def write(doc: dict, root=None) -> Path:
    """Write the frozen doc immutably (refuses to overwrite an existing handoff file)."""
    root = Path(root or DEFAULT_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    out = root / handoff_filename(doc)
    if out.exists():
        raise FileExistsError(f"immutable handoff already exists: {out}")
    paths.atomic_write_json(out, doc)
    return out
