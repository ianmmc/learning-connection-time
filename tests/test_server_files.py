"""serve_file containment + harvest-slice resolution (issues #48/#58) — DB-free.

The /files/ handler must (1) refuse any resolved path outside the record's capture dir
(Path.is_relative_to on resolved paths, not the old startswith idiom) and (2) resolve a
harvest_slice.txt that moved to the new derived-artifact location (wave 1D's
build_signals.resolve_harvest_slice), falling back gracefully.

Containment is asserted by calling the handler directly: the routing layer happens to also reject
percent-encoded slashes, but the handler must be safe on its own (defense in depth — a different
front end or a future route change must not re-open the hole).
"""
import contextlib

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from infrastructure.acquisition.process_governance import server as SRV

client = TestClient(SRV.app)


def _capture_dir(tmp_path, dd="lea_x", h="abc123"):
    d = tmp_path / dd / "captures" / h
    d.mkdir(parents=True)
    return d


def test_serves_a_file_inside_the_capture_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(SRV, "RAW_DIR", tmp_path)
    (_capture_dir(tmp_path) / "page.txt").write_text("bell times")
    r = client.get("/files/lea_x/abc123/page.txt")
    assert r.status_code == 200 and r.text == "bell times"


def test_dotdot_escape_in_filename_is_rejected(tmp_path, monkeypatch):
    """A ../ in the filename must not escape the capture dir (issue #48) — even though the file
    it points at EXISTS."""
    monkeypatch.setattr(SRV, "RAW_DIR", tmp_path)
    _capture_dir(tmp_path)
    (tmp_path / "lea_x" / "captures" / "secret.txt").write_text("outside the record dir")
    with pytest.raises(HTTPException) as e:
        SRV.serve_file("lea_x", "abc123", "../secret.txt")
    assert e.value.status_code == 404


def test_dotdot_escape_in_district_dir_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(SRV, "RAW_DIR", tmp_path / "raw")
    (tmp_path / "raw").mkdir()
    outside = tmp_path / "elsewhere" / "captures" / "abc123"
    outside.mkdir(parents=True)
    (outside / "page.txt").write_text("outside RAW_DIR")
    with pytest.raises(HTTPException) as e:
        SRV.serve_file("../elsewhere", "abc123", "page.txt")
    assert e.value.status_code == 404


def test_sibling_prefix_dir_is_rejected(tmp_path, monkeypatch):
    """The regression class the startswith idiom allowed: /a/captures/h1x passes
    startswith('/a/captures/h1')."""
    monkeypatch.setattr(SRV, "RAW_DIR", tmp_path)
    _capture_dir(tmp_path, h="h1")
    sibling = tmp_path / "lea_x" / "captures" / "h1x"
    sibling.mkdir(parents=True)
    (sibling / "page.txt").write_text("wrong record")
    with pytest.raises(HTTPException) as e:
        SRV.serve_file("lea_x", "h1", "../h1x/page.txt")
    assert e.value.status_code == 404


def test_harvest_slice_resolves_via_new_location(tmp_path, monkeypatch):
    """A harvest_slice.txt absent from the legacy capture dir resolves through
    build_signals.resolve_harvest_slice (new-location-first — issue #58 seam)."""
    monkeypatch.setattr(SRV, "RAW_DIR", tmp_path)
    _capture_dir(tmp_path)                                        # no harvest_slice.txt inside
    new_home = tmp_path / "harvest_slices" / "0100810"
    new_home.mkdir(parents=True)
    slice_path = new_home / "0100810_abc123.txt"
    slice_path.write_text("pages 4-6 of the handbook")

    class _FakeCon:
        def execute(self, *a, **k):
            class R:
                @staticmethod
                def first():
                    return ("0100810", "0100810:abc123")
            return R()

    @contextlib.contextmanager
    def fake_scope():
        yield _FakeCon()

    monkeypatch.setattr(SRV.gdb, "session_scope", fake_scope)
    calls = {}

    def fake_resolve(district_id, district_dir, rec_key, filename):
        calls["args"] = (district_id, district_dir, rec_key, filename)
        return slice_path

    monkeypatch.setattr(SRV.BS, "resolve_slice", fake_resolve)
    r = client.get("/files/lea_x/abc123/harvest_slice.txt")
    assert r.status_code == 200 and r.text == "pages 4-6 of the handbook"
    assert calls["args"] == ("0100810", "lea_x", "0100810:abc123", "harvest_slice.txt")


def test_missing_harvest_slice_is_a_plain_404_even_with_db_down(tmp_path, monkeypatch):
    monkeypatch.setattr(SRV, "RAW_DIR", tmp_path)
    _capture_dir(tmp_path)

    @contextlib.contextmanager
    def fake_scope():
        raise RuntimeError("db down")
        yield

    monkeypatch.setattr(SRV.gdb, "session_scope", fake_scope)
    r = client.get("/files/lea_x/abc123/harvest_slice.txt")
    assert r.status_code == 404
