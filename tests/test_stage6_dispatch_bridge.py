"""Stage 6 release->routing bridge (REQ-101, slice 4 — app layer).

Verifies the bridge reads the release decision (via the stage5 `release` readers), runs the real
`release.decide()`, enriches send reps with size signals, and assembles the package — with the
DB readers monkeypatched, so no Postgres/Docker is needed (the live DB path is exercised by the
govdb integration suite).
"""
import math

from infrastructure.acquisition.process_governance import stage6_dispatch as BR
from infrastructure.acquisition.stage5_filter import release as REL

CLEAN_TEXT = 0.00050 + 0.00022 + 0.5 * 0.00060   # low-cost-text bootstrap = 0.00102


def _fake_record(rec_key, label, reps):
    # the shape stage5 release.load_district_records yields
    return {"rec_key": rec_key, "url": f"http://x/{rec_key}", "tier": "A", "category": None,
            "signals": {"visual_text_gap": False}, "is_emergent": 0, "intended_schools": [],
            "label": label, "flags": [], "reps": reps}


def test_bridge_reads_decides_enriches_and_assembles(monkeypatch):
    reps = [{"source": "extracted", "filename": "extracted.txt", "file_kind": "text",
             "n_chars": 1500, "n_times": 6, "usable": 1}]
    records = [
        _fake_record("a", "school_bell_schedule", reps),     # a TARGET label -> send
        _fake_record("z", "board_calendar", reps),           # non-target -> reject
    ]
    monkeypatch.setattr(REL, "load_district",
                        lambda s, did: {"district_id": did, "name": "X", "district_dir": f"{did}_x",
                                        "labeled_topology": "per_school",
                                        "nces_denominator": {"total": 3, "by_level": {}}})
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: records)

    pkg = BR.build_handoff_package(session=None, district_ids=["0100810"])

    assert len(pkg["districts"]) == 1
    block = pkg["districts"][0]
    assert block["district_id"] == "0100810"
    assert block["n_send_reps"] == 1                       # only the target record routed
    sent = [r for r in block["records"] if r["decision"] == "send"][0]
    assert sent["reps"][0]["councils"] == ["low-cost-text"]
    assert math.isclose(sent["reps"][0]["est_usd"], CLEAN_TEXT, rel_tol=1e-9)
    # the reject is still recorded, with no reps
    rej = [r for r in block["records"] if r["decision"] == "reject"][0]
    assert rej["reps"] == []
    assert math.isclose(pkg["cost"]["total_usd"], CLEAN_TEXT, rel_tol=1e-9)
    assert pkg["cost"]["provenance"] == "bootstrap"


def test_missing_district_is_skipped(monkeypatch):
    monkeypatch.setattr(REL, "load_district", lambda s, did: None)
    monkeypatch.setattr(REL, "load_district_records", lambda s, did: [])
    pkg = BR.build_handoff_package(session=None, district_ids=["9999999"])
    assert pkg["districts"] == []
    assert pkg["cost"]["total_usd"] == 0
