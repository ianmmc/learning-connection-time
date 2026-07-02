"""Stage 4 tool-runner hardening: #32 (exit-code policy in _run -- nonzero+empty stdout is an
error surfaced on the representation entry; nonzero+substantial stdout is success, the text is
the product) and #45 (raster page cap, per-page OCR tolerance, pdftoppm returncode check +
stale-raster clearing). Every subprocess call is monkeypatched -- no poppler/tesseract needed."""
import subprocess

import pytest

from infrastructure.acquisition.stage4_process import process_stage4 as C4


def _cp(rc, stdout="", stderr=""):
    return subprocess.CompletedProcess(["x"], rc, stdout=stdout, stderr=stderr)


class TestRunExitCodes:
    def test_nonzero_exit_empty_stdout_raises_tool_error(self, monkeypatch):
        monkeypatch.setattr(C4.subprocess, "run", lambda *a, **k: _cp(2, "", "boom went the tool"))
        with pytest.raises(C4.ToolError, match=r"exit 2: boom"):
            C4._run(["pdftotext", "x"])

    def test_nonzero_exit_with_substantial_stdout_is_success_with_text(self, monkeypatch):
        # pdftotext-style: warns on stderr and exits 1, but still emits usable text
        monkeypatch.setattr(C4.subprocess, "run",
                            lambda *a, **k: _cp(1, "School starts at 8:00", "Syntax Warning"))
        assert C4._run(["pdftotext", "x"]) == "School starts at 8:00"

    def test_zero_exit_empty_stdout_is_plain_empty(self, monkeypatch):
        monkeypatch.setattr(C4.subprocess, "run", lambda *a, **k: _cp(0, "", ""))
        assert C4._run(["tesseract", "x"]) == ""

    def test_crashed_tool_records_error_entry_in_process_record(self, monkeypatch, tmp_path):
        """The old _run returned '' on a crash, so the representation entry read as a
        non-errored empty text (#32) -- it must carry `error` instead."""
        (tmp_path / "page.pdf").write_bytes(b"%PDF")
        monkeypatch.setattr(C4.subprocess, "run", lambda *a, **k: _cp(127, "", "not found"))
        monkeypatch.setattr(C4, "PDF_TOOLS", [("pdftotext", C4.run_pdftotext)])
        out = C4.process_record({"url": "u", "hash": "h", "ok": True,
                                 "files": {"pdf": "page.pdf"}}, tmp_path)
        entry = {t["source"]: t for t in out["texts"]}["pdftotext"]
        assert entry["error"].startswith("ToolError: exit 127")
        assert entry["usable"] is False and entry["text_file"] is None


class TestRasterize:
    def test_stale_rasters_cleared_and_returncode_checked(self, monkeypatch, tmp_path):
        (tmp_path / "raster_p1.png").write_bytes(b"stale from a prior failed run")
        monkeypatch.setattr(C4.subprocess, "run", lambda *a, **k: _cp(1, "", "pdftoppm blew up"))
        with pytest.raises(C4.ToolError, match="pdftoppm exit 1"):
            C4.rasterize(tmp_path / "x.pdf", tmp_path)
        assert not (tmp_path / "raster_p1.png").exists()   # stale raster not resurrected

    def test_partial_pages_on_nonzero_exit_are_kept(self, monkeypatch, tmp_path):
        def fake(cmd, **k):
            (tmp_path / "raster_p1.png").write_bytes(b"new")
            return _cp(3, "", "died on page 2")
        monkeypatch.setattr(C4.subprocess, "run", fake)
        assert [p.name for p in C4.rasterize(tmp_path / "x.pdf", tmp_path)] == ["raster_p1.png"]

    def test_page_cap_passed_to_pdftoppm(self, monkeypatch, tmp_path):
        seen = {}

        def fake(cmd, **k):
            seen["cmd"] = cmd
            return _cp(0)
        monkeypatch.setattr(C4.subprocess, "run", fake)
        C4.rasterize(tmp_path / "x.pdf", tmp_path)
        i = seen["cmd"].index("-l")
        assert seen["cmd"][i + 1] == str(C4.OCR_RASTER_PAGE_CAP)


class TestTesseractMulti:
    def test_per_page_error_tolerance(self, monkeypatch, tmp_path):
        """One page's timeout must not discard the other pages' text (#45)."""
        pages = [tmp_path / f"raster_p{i}.png" for i in (1, 2, 3)]

        def ocr(p):
            if p.name == "raster_p2.png":
                raise subprocess.TimeoutExpired("tesseract", 60)
            return f"text {p.name}"
        monkeypatch.setattr(C4, "run_tesseract", ocr)
        out = C4.run_tesseract_multi(pages)
        assert "text raster_p1.png" in out and "text raster_p3.png" in out
        assert "[ocr failed: raster_p2.png: TimeoutExpired" in out

    def test_page_cap_bounds_the_ocr_and_records_a_note(self, monkeypatch, tmp_path):
        monkeypatch.setattr(C4, "OCR_RASTER_PAGE_CAP", 2)
        calls = []
        monkeypatch.setattr(C4, "run_tesseract",
                            lambda p: calls.append(p.name) or f"t {p.name}")
        pages = [tmp_path / f"raster_p{i}.png" for i in range(1, 6)]
        out = C4.run_tesseract_multi(pages)
        assert calls == ["raster_p1.png", "raster_p2.png"]
        assert "3 page(s) beyond 2 not OCR'd" in out
