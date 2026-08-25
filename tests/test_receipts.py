"""Unit tests for the shared per-district receipt writer (REQ-164; common/receipts.py).

Covers the convention contract: always-stamped filenames, the writer tag, the volatile-excluded content
hash, same-second idempotency (no clobber), re-run history preservation, latest/iter resolution, and
schema-agnostic (dict OR list) payloads. Pure filesystem -- no DB, no network.
"""
import re

import pytest

from infrastructure.acquisition.common import paths, receipts

DID = "3501110"
NAME = "GALLUP"
FN_RE = re.compile(r"^incorporate\.\d{8}T\d{6}Z\.py-[0-9a-f]{8}\.json$")


@pytest.fixture
def cap_root(tmp_path, monkeypatch):
    """Redirect RAW_CAPTURES to a tmp dir so receipts never touch the real tree."""
    monkeypatch.setattr(paths, "RAW_CAPTURES", tmp_path)
    return tmp_path


def _fixed_stamp(monkeypatch, stamp):
    monkeypatch.setattr(receipts, "fs_stamp", lambda: stamp)


def test_filename_convention(cap_root, monkeypatch):
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    p = receipts.write_receipt(DID, NAME, "incorporate", {"bands": {"high": 425}})
    assert FN_RE.match(p.name), p.name
    assert p.parent.name == f"{DID}_gallup"          # district_id + slug
    assert p.exists()


def test_always_stamped_first_run(cap_root, monkeypatch):
    """No fixed-'latest' name -- the very first write is already stamped."""
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    p = receipts.write_receipt(DID, NAME, "incorporate", {"x": 1})
    assert ".20260722T155540Z." in p.name
    assert not (p.parent / "incorporate.json").exists()   # never an unstamped latest


def test_writer_tag_present_and_overridable(cap_root, monkeypatch):
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    p_py = receipts.write_receipt(DID, NAME, "incorporate", {"x": 1})
    assert ".py-" in p_py.name
    p_node = receipts.write_receipt(DID, NAME, "capture", [{"h": 1}], writer="node")
    assert ".node-" in p_node.name


def test_content_hash_excludes_volatile(cap_root):
    """generated_at must not perturb the hash -- else same-content re-runs stop being idempotent."""
    a = {"bands": {"high": 425}, "generated_at": "2026-07-22T15:55:40Z"}
    b = {"bands": {"high": 425}, "generated_at": "2026-07-22T16:00:00Z"}
    assert receipts.content_hash(a) == receipts.content_hash(b)


def test_content_hash_changes_with_substance(cap_root):
    assert receipts.content_hash({"m": 425}) != receipts.content_hash({"m": 430})


def test_content_hash_is_8_hex(cap_root):
    h = receipts.content_hash({"x": 1})
    assert len(h) == 8 and re.fullmatch(r"[0-9a-f]{8}", h)


def test_same_second_same_content_is_idempotent(cap_root, monkeypatch):
    """Two identical-content writes in the same second -> same filename, no clobber, no error."""
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    p1 = receipts.write_receipt(DID, NAME, "incorporate", {"x": 1})
    p2 = receipts.write_receipt(DID, NAME, "incorporate", {"x": 1})
    assert p1 == p2
    assert len(list(p1.parent.glob("incorporate.*.json"))) == 1


def test_same_second_different_content_both_preserved(cap_root, monkeypatch):
    """Same second, different content -> different h8 -> both files preserved (no clobber)."""
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    p1 = receipts.write_receipt(DID, NAME, "incorporate", {"x": 1})
    p2 = receipts.write_receipt(DID, NAME, "incorporate", {"x": 2})
    assert p1 != p2
    assert len(list(p1.parent.glob("incorporate.*.json"))) == 2


def test_rerun_preserves_history(cap_root, monkeypatch):
    """A later-second re-run writes a NEW file; the prior receipt is never clobbered."""
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    p1 = receipts.write_receipt(DID, NAME, "incorporate", {"run": 1})
    _fixed_stamp(monkeypatch, "20260722T155600Z")
    p2 = receipts.write_receipt(DID, NAME, "incorporate", {"run": 2})
    assert p1.exists() and p2.exists() and p1 != p2


def test_latest_and_iter_are_chronological(cap_root, monkeypatch):
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    receipts.write_receipt(DID, NAME, "incorporate", {"run": 1})
    _fixed_stamp(monkeypatch, "20260722T160000Z")
    newest = receipts.write_receipt(DID, NAME, "incorporate", {"run": 2})
    _fixed_stamp(monkeypatch, "20260722T155900Z")
    receipts.write_receipt(DID, NAME, "incorporate", {"run": 3})
    order = [p.name for p in receipts.iter_receipts(DID, NAME, "incorporate")]
    assert order == sorted(order)                                   # oldest -> newest by stamp
    assert receipts.latest_receipt(DID, NAME, "incorporate") == newest   # the 16:00 write


def test_latest_receipt_none_when_absent(cap_root):
    assert receipts.latest_receipt(DID, NAME, "incorporate") is None


def test_iter_excludes_legacy_unstamped(cap_root, monkeypatch):
    """A legacy bare <basename>.json (pre-always-stamp) is NOT matched -- the backfill handles it."""
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    p = receipts.write_receipt(DID, NAME, "discovery", {"x": 1})
    (p.parent / "discovery.json").write_text("{}")                  # simulate a legacy file
    names = [q.name for q in receipts.iter_receipts(DID, NAME, "discovery")]
    assert "discovery.json" not in names and p.name in names


def test_iter_does_not_bleed_across_prefix_basenames(cap_root, monkeypatch):
    """basename 'stage7' must not match 'stage7_extract...' (the '.' after basename anchors the glob)."""
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    receipts.write_receipt(DID, NAME, "stage7", {"a": 1})
    receipts.write_receipt(DID, NAME, "stage7_extract", {"b": 2})
    assert len(receipts.iter_receipts(DID, NAME, "stage7")) == 1


def test_list_payload_supported(cap_root, monkeypatch):
    """captures.json / processed.json are LISTS -- the helper must write them unchanged."""
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    payload = [{"hash": "abc", "usable": True}, {"hash": "def", "usable": False}]
    p = receipts.write_receipt(DID, NAME, "captures", payload)
    import json
    assert json.loads(p.read_text()) == payload


def test_atomic_no_tmp_left_behind(cap_root, monkeypatch):
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    p = receipts.write_receipt(DID, NAME, "incorporate", {"x": 1})
    assert not list(p.parent.glob("*.tmp"))


def test_ddir_override_writes_to_the_given_dir(tmp_path, monkeypatch):
    """An in-pipeline caller that already holds the district's capture dir (Stage 4 district['dir'],
    Stage 5 root/district_dir) passes ddir= to bypass the RAW_CAPTURES glob — the receipt lands there,
    NOT under district_capture_dir (which the default resolution would pick)."""
    _fixed_stamp(monkeypatch, "20260722T155540Z")
    monkeypatch.setattr(paths, "RAW_CAPTURES", tmp_path / "raw")   # a DIFFERENT tree
    explicit = tmp_path / "reltest_dir"
    p = receipts.write_receipt(DID, NAME, "filtered", {"x": 1}, ddir=explicit)
    assert p.parent == explicit
    assert not (tmp_path / "raw").exists()                         # the glob dir was never touched
    assert p.name.startswith("filtered.") and ".py-" in p.name


def test_670_receipts_are_write_only_in_production_code():
    """REQ-164: receipts are audit cross-checks + recovery sources, NEVER data-transmission vehicles
    read as input by an active-pipeline stage. Pin (#670): no module under infrastructure/ outside
    common/receipts.py CALLS the resolvers (latest_receipt / iter_receipts) — true today, kept true.
    #670's completeness datum deliberately travels over the capture subprocess's stdout channel and
    lives in gov_db (the stage-3 outcome event's fingerprints_json) precisely so no pipeline stage
    ever needs to resolve a receipt. AST-scanned, so docstring mentions don't false-positive."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "infrastructure"
    offenders = []
    for p in sorted(root.rglob("*.py")):
        if p.name == "receipts.py" and p.parent.name == "common":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else (
                    f.id if isinstance(f, ast.Name) else None)
                if name in {"latest_receipt", "iter_receipts"}:
                    offenders.append(f"{p.relative_to(root.parent)}:{node.lineno}")
    assert not offenders, (
        "receipt resolvers called from production code (receipts are write-only for the "
        f"pipeline; source the datum from gov_db instead): {offenders}")
