"""Stage 6 immutable handoff artifact (REQ-101, slice 5).

freeze() turns an in-memory handoff package into the frozen `handoff_<hash>_<ts>.json` doc (governance
§5): it embeds the council configs actually used + per-district fingerprints, and a content-identity
hash. The hash is **price-independent** — over what we SENT (reps + routing + council configs +
fingerprints), NOT the dollar estimates — so a later reprice/retune can't rewrite a past dispatch's
identity. write() is immutable: it refuses to overwrite. Pure + filesystem; no DB.
"""
import json

import pytest

from infrastructure.acquisition.stage6_handoff import handoff

COUNCILS = {
    "low-cost-text": {"id": "low-cost-text", "voters": ["a/1", "b/1"], "judge": "c/1"},
    "image": {"id": "image", "voters": ["d/1", "e/1"], "judge": "f/1"},
}
FPR = {"0100810": {"config": "cfg1", "labels": "lab1", "data": "dat1"}}


def _pkg(est=0.001, councils=("low-cost-text",)):
    return {
        "generated_at": "2026-06-30T00:00:00Z",
        "districts": [{
            "district_id": "0100810", "n_send_reps": 1, "est_usd": est,
            "records": [{"rec_key": "a", "url": "u", "decision": "send", "reason": "t",
                         "reps": [{"file": "t.txt", "kind": "text", "councils": list(councils),
                                   "fidelity_suspect": False, "route_reason": "clean-text",
                                   "est_usd": est}]}],
        }],
        "cost": {"total_usd": est, "n_reps": 1, "provenance": "bootstrap"},
    }


def test_freeze_embeds_used_councils_fingerprints_and_cost():
    doc = handoff.freeze(_pkg(), COUNCILS, FPR, created_by="ian")
    assert "handoff_hash" in doc and len(doc["handoff_hash"]) >= 8
    assert doc["created_by"] == "ian"
    assert set(doc["councils"]) == {"low-cost-text"}      # only the council actually used is frozen in
    assert "image" not in doc["councils"]
    assert doc["fingerprints"] == FPR
    assert doc["cost"]["provenance"] == "bootstrap"
    assert doc["districts"][0]["district_id"] == "0100810"


def test_hash_is_stable_across_timestamps():
    a = handoff.freeze(_pkg(), COUNCILS, FPR)
    b = handoff.freeze(_pkg(), COUNCILS, FPR)
    assert a["handoff_hash"] == b["handoff_hash"]         # same content, different created_at -> same hash
    assert a["created_at"] is not None


def test_hash_is_price_independent():
    # identical reps/routing/configs, different dollar estimates (a reprice) -> SAME identity hash
    cheap = handoff.freeze(_pkg(est=0.001), COUNCILS, FPR)
    pricey = handoff.freeze(_pkg(est=0.999), COUNCILS, FPR)
    assert cheap["handoff_hash"] == pricey["handoff_hash"]


def test_hash_changes_when_what_we_send_changes():
    base = handoff.freeze(_pkg(councils=("low-cost-text",)), COUNCILS, FPR)
    rerouted = handoff.freeze(_pkg(councils=("image",)), COUNCILS, FPR)
    assert base["handoff_hash"] != rerouted["handoff_hash"]
    # and a fingerprint change (new data/labels) also changes identity
    fp2 = {"0100810": {"config": "cfg1", "labels": "lab2", "data": "dat1"}}
    assert handoff.freeze(_pkg(), COUNCILS, fp2)["handoff_hash"] != base["handoff_hash"]


def test_verified_only_is_carried_and_part_of_identity():
    # the frozen doc records the mode, and a verified-only dispatch is a DISTINCT artifact from a
    # default one over the same reps (no hash collision / no FileExistsError conflation)
    default = handoff.freeze(_pkg(), COUNCILS, FPR)
    assert default["verified_only"] is False
    vpkg = _pkg(); vpkg["verified_only"] = True
    verified = handoff.freeze(vpkg, COUNCILS, FPR)
    assert verified["verified_only"] is True
    assert verified["handoff_hash"] != default["handoff_hash"]


def test_filename_format():
    doc = handoff.freeze(_pkg(), COUNCILS, FPR)
    fn = handoff.handoff_filename(doc)
    assert fn.startswith("handoff_") and fn.endswith(".json")
    assert doc["handoff_hash"] in fn


def test_write_is_immutable(tmp_path):
    doc = handoff.freeze(_pkg(), COUNCILS, FPR)
    out = handoff.write(doc, root=tmp_path)
    assert out.exists()
    assert json.loads(out.read_text())["handoff_hash"] == doc["handoff_hash"]
    with pytest.raises(FileExistsError):
        handoff.write(doc, root=tmp_path)           # a frozen dispatch is never overwritten
