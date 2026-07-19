"""Stage 4 tool-runner hardening: #32 (exit-code policy in _run -- nonzero+empty stdout is an
error surfaced on the representation entry; nonzero+substantial stdout is success, the text is
the product) and #45 (raster page cap, per-page OCR tolerance, pdftoppm returncode check +
stale-raster clearing). Every subprocess call is monkeypatched -- no poppler/tesseract needed
(except TestPdftotextPageSeparators, which runs the REAL toolchain and skips where absent)."""
import shutil
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


@pytest.mark.skipif(
    not (shutil.which("gs") and shutil.which("pdftotext")),
    reason="needs ghostscript + poppler (the Stage-4 toolchain)")
class TestPdftotextPageSeparators:
    """The #522 console's bookmark→PDF-page map splits Stage-4's pdftotext output on \\f — pin that
    real `pdftotext -layout` emits ONE form-feed per page with page content BEFORE its \\f, so the
    client-side rule `page = (form-feeds strictly before offset) + 1` stays deterministic. If a
    poppler upgrade ever changes \\f emission, this fails instead of bookmarks silently mislabeling
    pages (the map is otherwise tied to the server by nothing)."""

    def test_layout_output_carries_one_formfeed_per_page(self, tmp_path):
        pdf = tmp_path / "three.pdf"
        subprocess.run(
            ["gs", "-q", "-o", str(pdf), "-sDEVICE=pdfwrite", "-c",
             "/Helvetica findfont 12 scalefont setfont "
             "72 720 moveto (page one 8:00 am) show showpage "
             "72 720 moveto (page two dismissal 3:15 pm) show showpage "
             "72 720 moveto (page three) show showpage"],
            check=True, capture_output=True)
        text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                              check=True, capture_output=True, text=True).stdout
        assert text.count("\f") == 3, "one \\f per page (including a trailing one)"
        # The client rule: page N's content precedes the Nth \f — "dismissal" (page 2) has exactly 1 \f before it.
        assert text[:text.index("\f")].count("page one") == 1
        assert text[:text.index("dismissal")].count("\f") == 1


class TestMalformedManifestTolerance:
    """#351 — a non-string files{} value (hand-edited/corrupt captures.json; Stage 3 never
    writes one) degrades to representation-absent / a reported inconsistency, never a crash."""

    def test_process_record_drops_non_string_files_values(self, tmp_path):
        out = C4.process_record({"url": "u", "hash": "h", "ok": True,
                                 "files": {"bin": None, "pdf": 123, "txt": ""}}, tmp_path)
        assert out["texts"] == []   # nothing crashed; nothing claimed

    def test_check_file_consistency_reports_non_string_entry_instead_of_crashing(self, tmp_path):
        district = {"dir": tmp_path,
                    "captures": [{"url": "u", "hash": "h", "ok": True, "files": {"bin": None}}]}
        problems = C4.check_file_consistency(district)
        assert len(problems) == 1 and "non-string files entry" in problems[0]


class TestTimeBlindFidelity:
    """#518 — the SILENT capture-fidelity shape: a schedule-promising URL whose usable reps
    all recovered zero clock times gets fidelity=['time_blind']. Assertion is on the URL
    (capture metadata), never the text — text-aboutness stays Stage 5's (is_usable docstring)."""

    FILLER = "Our district is committed to student success and community engagement. " * 4

    def _rec(self, tmp_path, url, text, final_url=None):
        (tmp_path / "page.txt").write_text(text)
        rec = {"url": url, "hash": "h", "ok": True, "files": {"txt": "page.txt"}}
        if final_url:
            rec["final_url"] = final_url
        return C4.process_record(rec, tmp_path)

    def test_schedule_url_with_zero_times_is_flagged(self, tmp_path):
        out = self._rec(tmp_path, "https://x.org/about-us/bell-schedule", self.FILLER)
        assert out["usable"] is True and out["fidelity"] == ["time_blind"]

    def test_times_present_means_no_flag(self, tmp_path):
        out = self._rec(tmp_path, "https://x.org/bell-schedule",
                        self.FILLER + " Breakfast 8:55 AM, dismissal 3:43 PM.")
        assert "fidelity" not in out

    def test_non_schedule_url_with_zero_times_is_not_flagged(self, tmp_path):
        out = self._rec(tmp_path, "https://x.org/news/article-42", self.FILLER)
        assert "fidelity" not in out

    def test_unusable_record_is_not_flagged_its_failure_is_already_visible(self, tmp_path):
        out = self._rec(tmp_path, "https://x.org/bell-schedule", "tiny")
        assert out["usable"] is False and "fidelity" not in out

    def test_post_redirect_final_url_asserting_a_schedule_counts(self, tmp_path):
        out = self._rec(tmp_path, "https://x.org/documents/716886", self.FILLER,
                        final_url="https://x.org/documents/bus-%26-bell-schedules/716886")
        assert out["fidelity"] == ["time_blind"]
