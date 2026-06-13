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
MAX_IMAGES = 3             # cap images to a vision model (each ~2-4k tokens; context-limited)
RENDER_DPI = 150           # render resolution for PDF->image (balance legibility vs tokens)


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
        _run(["pdftoppm", "-png", "-r", str(RENDER_DPI), "-l", str(MAX_PDF_PAGES_OCR), str(pdf), prefix], timeout=120)
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


MAX_IMAGE_DIM = 1024  # bound the longest side; VLM image tokens scale with resolution


def _bounded(path: str, render_root: Path) -> str:
    """Return a copy of the image with longest side <= MAX_IMAGE_DIM (sips). Cached."""
    render_root.mkdir(exist_ok=True)
    dst = render_root / ("small_" + Path(path).stem + ".png")
    if not dst.exists():
        _run(["sips", "-Z", str(MAX_IMAGE_DIM), "-s", "format", "png",
              str(path), "--out", str(dst)], timeout=60)
    return str(dst) if dst.exists() else path


def _render_table(rows: list) -> str:
    """Render a pdfplumber/pandas table (list of cell-rows) as a pipe-delimited block."""
    out = []
    for row in rows:
        cells = ["" if c is None else " ".join(str(c).split()) for c in row]
        if any(cells):
            out.append(" | ".join(cells))
    return "\n".join(out)


def read_tables(source_dir: Path) -> tuple[str, list[str]]:
    """Table-aware reading: preserve cell/column structure that pdftotext flattens.

    PDF  -> pdfplumber.extract_tables(); fall back to `pdftotext -layout`, then OCR.
    HTML -> pandas.read_html() (real DOM tables); fall back to html2text.
    image/docx/txt -> same as read_text (OCR/textutil).
    Returns (combined_text, source_filenames).
    """
    parts: list[str] = []
    sources: list[str] = []
    for f in _active_files(source_dir):
        ext = f.suffix.lower()
        txt = ""
        if ext == ".pdf":
            try:
                import pdfplumber
                tabs = []
                with pdfplumber.open(str(f)) as pdf:
                    for page in pdf.pages[:MAX_PDF_PAGES_OCR]:
                        for t in page.extract_tables():
                            r = _render_table(t)
                            if r:
                                tabs.append(r)
                txt = "\n\n".join(tabs)
            except Exception:
                txt = ""
            if len(txt.strip()) < PDF_MIN_TEXT_CHARS:  # no tables -> layout text -> OCR
                txt = _run(["pdftotext", "-layout", str(f), "-"], timeout=60)
                if len(txt.strip()) < PDF_MIN_TEXT_CHARS:
                    txt = _ocr_pdf(f)
        elif ext in (".html", ".htm", ".mhtml"):
            try:
                import pandas as pd
                dfs = pd.read_html(str(f))
                txt = "\n\n".join(_render_table([list(df.columns)] + df.values.tolist()) for df in dfs)
            except Exception:
                txt = ""
            if len(txt.strip()) < PDF_MIN_TEXT_CHARS:
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
    """Bounded image paths for a vision model: existing images + rendered PDF pages,
    each downscaled so a few fit in the context window. Returns (image_paths, source_names)."""
    raw: list[tuple[str, str]] = []
    render_root = source_dir / "_render"
    for f in _active_files(source_dir):
        ext = f.suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".gif"):
            raw.append((str(f), f.name))
        elif ext == ".pdf":
            render_root.mkdir(exist_ok=True)
            prefix = str(render_root / f.stem)
            existing = sorted(glob.glob(prefix + "*.png"))
            if not existing:
                _run(["pdftoppm", "-png", "-r", str(RENDER_DPI), "-l", str(MAX_PDF_PAGES_OCR), str(f), prefix], timeout=120)
                existing = sorted(glob.glob(prefix + "*.png"))
            for png in existing:
                raw.append((png, os.path.basename(png)))
        if len(raw) >= MAX_IMAGES:
            break
    raw = raw[:MAX_IMAGES]
    images = [_bounded(p, render_root) for p, _ in raw]
    sources = [n for _, n in raw]
    return images, sources


if __name__ == "__main__":
    import sys
    d = Path(sys.argv[1])
    t, s = read_text(d)
    print(f"TEXT: {len(t)} chars from {s}")
    imgs, isrc = read_images(d)
    print(f"IMAGES: {len(imgs)} -> {[os.path.basename(i) for i in imgs]}")
    print(t[:800])
