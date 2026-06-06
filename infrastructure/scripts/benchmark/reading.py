#!/usr/bin/env python3
"""
reading.py - Document -> text / images for the extraction benchmark.

The "reading" step is deliberately separated from the "structuring" (LLM) step so the
benchmark can compare reading methods, not just models. Many captured bell-schedule PDFs
are image-based/scanned (pdftotext returns nothing), so the text path falls back to OCR.

Two outputs per district:
  - read_text(source_dir):  best-effort plain text via CLI tools
      PDF  -> `pdftotext -layout`; if empty -> pdftoppm + tesseract (OCR)
      HTML -> `html2text`
      DOCX -> `textutil` (macOS)
      image-> `tesseract`
  - read_images(source_dir): image paths for vision models
      existing image files + PDF pages rendered via `pdftoppm`

All external tools are wrapped defensively; failures degrade to empty output.
"""

from __future__ import annotations

import glob
import os
import subprocess
import tempfile
from pathlib import Path

PDF_MIN_TEXT_CHARS = 120  # below this, treat the PDF as image-based and OCR it
MAX_PDF_PAGES_OCR = 6      # cap OCR/vision pages per PDF (schedules are short)
MAX_IMAGES = 8             # cap images handed to a vision model per district


def _run(cmd: list[str], timeout: int = 90) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout or ""
    except Exception:
        return ""


def _active_files(source_dir: Path) -> list[Path]:
    """Files in active/ if present, else the district dir top level."""
    active = source_dir / "active"
    base = active if active.exists() else source_dir
    files = [Path(f) for f in glob.glob(str(base / "*")) if os.path.isfile(f)]
    # skip our own outputs / metadata
    skip = {"metadata.json", "extraction_result.json", "ground_truth.json",
            "enrichment_ready.json", "import_result.json", "verification_report.json"}
    return sorted(f for f in files if f.name not in skip)


def _ocr_pdf(pdf: Path) -> str:
    """Render PDF pages to PNG (pdftoppm) and OCR with tesseract."""
    text = ""
    with tempfile.TemporaryDirectory() as td:
        prefix = os.path.join(td, "page")
        _run(["pdftoppm", "-png", "-r", "200", "-l", str(MAX_PDF_PAGES_OCR), str(pdf), prefix], timeout=120)
        for png in sorted(glob.glob(prefix + "*.png")):
            text += _run(["tesseract", png, "stdout"], timeout=60) + "\n"
    return text


def read_text(source_dir: Path) -> tuple[str, list[str]]:
    """Best-effort text for the whole district. Returns (combined_text, source_filenames)."""
    parts: list[str] = []
    sources: list[str] = []
    for f in _active_files(source_dir):
        ext = f.suffix.lower()
        txt = ""
        if ext == ".pdf":
            txt = _run(["pdftotext", "-layout", str(f), "-"], timeout=60)
            if len(txt.strip()) < PDF_MIN_TEXT_CHARS:
                txt = _ocr_pdf(f)  # image-based PDF -> OCR
        elif ext in (".html", ".htm", ".mhtml"):
            txt = _run(["html2text", str(f)], timeout=60)
        elif ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif"):
            txt = _run(["tesseract", str(f), "stdout"], timeout=60)
        elif ext == ".docx":
            txt = _run(["textutil", "-convert", "txt", "-stdout", str(f)], timeout=60)
        elif ext == ".txt":
            try:
                txt = f.read_text(errors="replace")
            except Exception:
                txt = ""
        if txt and txt.strip():
            parts.append(f"\n--- From {f.name} ---\n{txt}")
            sources.append(f.name)
    return "\n".join(parts), sources


def read_images(source_dir: Path) -> tuple[list[str], list[str]]:
    """Image paths for a vision model: existing images + rendered PDF pages.
    Returns (image_paths, source_filenames). Caller is responsible for any cleanup of
    rendered pages (kept in a stable per-district render dir under the source)."""
    images: list[str] = []
    sources: list[str] = []
    render_root = source_dir / "_render"
    for f in _active_files(source_dir):
        ext = f.suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif"):
            images.append(str(f)); sources.append(f.name)
        elif ext == ".pdf":
            render_root.mkdir(exist_ok=True)
            prefix = str(render_root / f.stem)
            existing = sorted(glob.glob(prefix + "*.png"))
            if not existing:
                _run(["pdftoppm", "-png", "-r", "200", "-l", str(MAX_PDF_PAGES_OCR), str(f), prefix], timeout=120)
                existing = sorted(glob.glob(prefix + "*.png"))
            for png in existing:
                images.append(png); sources.append(os.path.basename(png))
        if len(images) >= MAX_IMAGES:
            break
    return images[:MAX_IMAGES], sources[:MAX_IMAGES]


if __name__ == "__main__":
    import sys
    d = Path(sys.argv[1])
    t, s = read_text(d)
    print(f"TEXT: {len(t)} chars from {s}")
    imgs, isrc = read_images(d)
    print(f"IMAGES: {len(imgs)} -> {[os.path.basename(i) for i in imgs]}")
    print(t[:800])
