"""#118 (REQ-160) — Stage 2/4 effectiveness attribution: per-discovery-tool
candidate→record→target rates, per-processing-source winning representations, and the #164
per-district scope/ladder axes, all scoped by district_ids so synthetic rows never perturb the
corpus card (and per-batch views stay possible)."""
import json
from pathlib import Path

import pytest
from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.process_governance import attribution as ATTR
from infrastructure.acquisition.stage1_queue.models import Batch, BatchDistrict
from infrastructure.acquisition.stage7_extract import models as _M7  # noqa: F401

govdb = pytest.mark.govdb
STATIC = Path(__file__).parent.parent / "infrastructure/acquisition/process_governance/static"


def _seed(s):
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    gdb.init_precious_schema()
    BS.ensure_signal_schema(s)
    CI.ensure_cache_schema(s)
    did = "ZZAT1"
    # plan: two tools proposed the target URL; one tool proposed a dud
    s.execute(text("INSERT INTO candidate (district_id, url, tools_json) VALUES "
                   "(:d, 'https://zz.org/bells', '[\"brightdata\", \"serper\"]'), "
                   "(:d, 'https://zz.org/dud', '[\"serper\"]')"), {"d": did})
    # captures: the planned target + an EMERGENT hit with no plan row
    s.execute(text("INSERT INTO capture (district_id, hash, url, source) VALUES "
                   "(:d, 'aaaa111111', 'https://zz.org/bells', 'discovered'), "
                   "(:d, 'bbbb222222', 'https://zz.org/hidden-schedule', 'emergent')"), {"d": did})
    # canonical records + labels: planned->target, emergent->target
    for h, url, label in (("aaaa111111", "https://zz.org/bells", "school_bell_table"),
                          ("bbbb222222", "https://zz.org/hidden-schedule", "school_bell_table")):
        # `hash` set explicitly (#575 review): the real ingest path (build_signals.py's REC_COLS)
        # always populates it — attribution.py's capture join reads it directly (r.hash), not
        # derived from rec_key, so a synthetic row skipping it would falsely fail that join.
        s.execute(text("INSERT INTO record (rec_key, district_id, url, hash, tier, duplicate_of, "
                       "is_cluster_rep, cluster_id, sort_score) "
                       "VALUES (:k, :d, :u, :h, 'A', NULL, 1, NULL, 1.0)"),
                  {"k": f"{did}:{h}", "d": did, "u": url, "h": h})
        s.execute(text("INSERT INTO label (rec_key, primary_label, status) "
                       "VALUES (:k, :l, 'labeled')"), {"k": f"{did}:{h}", "l": label})
    # reps: the planned record wins with pdftotext (usable), a raster rides along unusable
    s.execute(text("INSERT INTO representation (rec_key, source, filename, file_kind, n_chars, "
                   "n_times, usable) VALUES "
                   "(:k, 'pdftotext', 'page.pdf.txt', 'text', 4000, 12, 1), "
                   "(:k, 'raster', 'p1.png', 'image', NULL, NULL, 0)"),
              {"k": f"{did}:aaaa111111"})
    return did


@govdb
def test_stage2_attribution_tools_and_emergent_fallback(gov_session):
    did = _seed(gov_session)
    out = ATTR.stage2_attribution(gov_session, district_ids=[did])
    pt = out["per_tool"]
    assert pt["brightdata"] == {"n_candidates": 1, "n_records": 1, "n_target": 1,
                                "n_labeled": 1, "target_rate_labeled": 1.0}
    assert pt["serper"]["n_candidates"] == 2 and pt["serper"]["n_records"] == 1
    # the emergent record has no plan row -> attributed to its capture source
    assert pt["capture:emergent"]["n_target"] == 1
    assert out["n_records"] == 2


@govdb
def test_stage4_attribution_winning_source(gov_session):
    did = _seed(gov_session)
    out = ATTR.stage4_attribution(gov_session, district_ids=[did])
    # the target record's release decision sends the usable text rep -> pdftotext wins
    assert out["winning_source"].get("pdftotext", 0) >= 1
    assert out["n_target_records"] == 2
    assert out["usable_by_source"]["pdftotext"]["n_usable"] == 1
    assert out["usable_by_source"]["raster"]["n_usable"] == 0


@govdb
def test_district_axes_scope_ladder_and_domain_source(gov_session):
    s = gov_session
    did = _seed(s)
    now = _M7.utcnow()
    s.add(Batch(batch_id="batch_zzat_fr", batch_type="first-run", status="approved",
                discovery_scope="domain", nces_year="2024_25", created_at=now, created_by="zz",
                meta_json={}, first_approved_at=now))
    s.add(BatchDistrict(batch_id="batch_zzat_fr", district_id=did, ord=0, name="AT", state="ZZ",
                        domain="zz.org", domain_source="discovered", lea_claimed_bands=[],
                        nces_school_counts={}, band_processing_order=[], band_meta={}, included=True))
    s.add(Batch(batch_id="batch_zzat_geo", batch_type="follow-up", status="approved",
                discovery_scope="geo", nces_year="2024_25", created_at=now, created_by="zz",
                meta_json={}, first_approved_at=now))
    s.add(BatchDistrict(batch_id="batch_zzat_geo", district_id=did, ord=0, name="AT", state="ZZ",
                        domain="", lea_claimed_bands=[], nces_school_counts={},
                        band_processing_order=[], band_meta={}, included=True))
    s.flush()
    axes = ATTR.district_axes(s, district_ids=[did])
    a = axes[did]
    assert a["runs"] == {"first-run:domain": 1, "follow-up:geo": 1}
    assert a["ladder"] == {"domain": 0, "geo": 1}      # derived, follow-ups only
    assert a["domain_source"] == "discovered"


@govdb
def test_build_card_stamps_fingerprints(gov_session):
    did = _seed(gov_session)
    card = ATTR.build_card(gov_session, district_ids=[did])
    assert set(card["fingerprints"]) == {"label_set", "plan", "captures"}
    assert all(len(v) for v in card["fingerprints"].values())
    assert card["stage2"]["n_records"] == 2


def test_write_card_names_receipt_by_label_fingerprint(tmp_path):
    card = {"generated_at": "2026-07-20T00:00:00Z",
            "fingerprints": {"label_set": "abc123", "plan": "x", "captures": "y"},
            "stage2": {}, "stage4": {}, "district_axes": {}}
    out = ATTR.write_card(card, out_dir=tmp_path)
    assert out.name == "attribution_20260720T000000Z_abc123.json"
    assert json.loads(out.read_text())["fingerprints"]["label_set"] == "abc123"


@pytest.fixture
def client():
    try:
        gdb.get_engine().connect().close()
    except Exception as e:
        pytest.skip(f"governance Postgres unavailable: {type(e).__name__}: {e}")
    from fastapi.testclient import TestClient
    from infrastructure.acquisition.process_governance.server import app
    return TestClient(app)


@govdb
def test_attribution_endpoint_self_bootstraps_schema(client, monkeypatch):
    """#575 review: GET /api/attribution used to skip the schema-bootstrap its sibling
    GET /api/fidelity-triage already has (added by #581 for exactly this reason) —
    reintroducing the fresh-DB 500 that fix was written to prevent. Confirms both ensure-schema
    calls actually fire on this endpoint's path, and that the response is still a clean 200."""
    from infrastructure.acquisition.common import cache_ingest as CI
    from infrastructure.acquisition.stage5_filter import build_signals as BS
    calls = {"cache": False, "signal": False}
    orig_cache, orig_signal = CI.ensure_cache_schema, BS.ensure_signal_schema

    def _cache(con):
        calls["cache"] = True
        return orig_cache(con)

    def _signal(con):
        calls["signal"] = True
        return orig_signal(con)

    monkeypatch.setattr(CI, "ensure_cache_schema", _cache)
    monkeypatch.setattr(BS, "ensure_signal_schema", _signal)
    r = client.get("/api/attribution")
    assert r.status_code == 200
    assert calls == {"cache": True, "signal": True}


def test_console_panels_are_pinned():
    js = (STATIC / "outcomes.js").read_text()
    for marker in ("attributionPanel", "attr-panel-", "/api/attribution", "district_axes"):
        assert marker in js, f"outcomes.js lost the #118 panel marker {marker!r}"
    for stage in ("stage2.js", "stage4.js"):
        assert "attributionPanel" in (STATIC / stage).read_text(), f"{stage} lost the #118 panel mount"
