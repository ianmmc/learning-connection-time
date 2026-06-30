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
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.acquisition.common import paths

DEFAULT_ROOT = paths.ACQUISITION / "handoffs"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    """The price-INDEPENDENT content that defines this dispatch's identity (drops all dollar fields)."""
    dist = []
    for d in package.get("districts", []):
        recs = []
        for r in d.get("records", []):
            reps = [{"file": rep.get("file"), "kind": rep.get("kind"),
                     "councils": rep.get("councils"), "fidelity_suspect": rep.get("fidelity_suspect")}
                    for rep in r.get("reps", [])]
            recs.append({"rec_key": r.get("rec_key"), "decision": r.get("decision"), "reps": reps})
        dist.append({"district_id": d.get("district_id"), "records": recs})
    return {"districts": dist, "councils": used_councils, "fingerprints": fingerprints}


def freeze(package: dict, councils: dict, fingerprints: dict, created_by: str = "human") -> dict:
    """Build the immutable handoff doc from a package + the council registry + per-district fingerprints."""
    used = _councils_used(package, councils)
    identity = _identity(package, used, fingerprints)
    h = hashlib.md5(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    return {
        "handoff_hash": h, "created_at": _now(), "created_by": created_by,
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
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2))
    tmp.replace(out)
    return out
