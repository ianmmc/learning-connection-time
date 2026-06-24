#!/usr/bin/env python3
"""Stage 4 PDF-tool spike: run every candidate fast/deterministic extraction tool
against the real captured PDFs in data/raw/lea-website-captures/, save raw outputs +
cheap comparison metrics. Exploratory only -- not part of the production pipeline.

Fast tools only: pdftotext, pdfplumber (lines + text strategies), PyMuPDF, Camelot
(stream/network/hybrid/lattice), img2table (bordered/borderless), Tesseract OCR.
Docling/EasyOCR/PaddleOCR deliberately excluded (2026-06-23) -- each costs 13-56s
PER PAGE for heavy-model inference; any case that actually needs that level of
understanding goes to the paid vision council (Stage 7), not a slow local model,
the same tradeoff that already retired local Ollama for this project.

Usage:
    python3 run_spike.py
"""
import json
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

RAW_DIR = Path("data/raw/lea-website-captures")
OUT_DIR = Path("data/benchmark_results/stage4_pdf_tool_spike")
SUMMARY = OUT_DIR / "summary.jsonl"

TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?")
KW_RE = re.compile(r"\b(bell|schedule|dismissal|start time|end time|school hours|arrival|first bell|period \d)\b", re.I)


def metrics(text: str) -> dict:
    text = text or ""
    printable = sum(1 for c in text if c.isprintable() or c in "\n\t")
    return {
        "n_chars": len(text),
        "printable_ratio": round(printable / len(text), 3) if text else 0.0,
        "n_times": len(TIME_RE.findall(text)),
        "has_keyword": bool(KW_RE.search(text)),
    }


def discover_pdfs() -> list[dict]:
    """Every PDF under data/raw/lea-website-captures, with district/hash/kind/text_times context."""
    out = []
    for district_dir in sorted(RAW_DIR.iterdir()):
        if not district_dir.is_dir():
            continue
        cap_json = district_dir / "captures.json"
        if not cap_json.exists():
            continue
        records = json.loads(cap_json.read_text())
        by_hash = {r["hash"]: r for r in records}
        captures_dir = district_dir / "captures"
        if not captures_dir.exists():
            continue
        for hash_dir in sorted(captures_dir.iterdir()):
            if not hash_dir.is_dir():
                continue
            rec = by_hash.get(hash_dir.name, {})
            for pdf in sorted(hash_dir.glob("*.pdf")):
                out.append({
                    "district": district_dir.name,
                    "hash": hash_dir.name,
                    "pdf_path": pdf,
                    "out_dir": OUT_DIR / district_dir.name / hash_dir.name,
                    "kind": rec.get("kind"),
                    "text_times": rec.get("text_times"),
                    "url": rec.get("url"),
                })
    return out


def write_result(out_dir: Path, name: str, text: str, append_summary: dict):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.txt").write_text(text or "")
    with SUMMARY.open("a") as f:
        f.write(json.dumps(append_summary) + "\n")


def run_tool(tool_name: str, fn, pdf_info: dict):
    t0 = time.time()
    row = {"district": pdf_info["district"], "hash": pdf_info["hash"], "tool": tool_name,
           "kind": pdf_info["kind"], "text_times_existing": pdf_info["text_times"]}
    try:
        text, extra = fn(pdf_info["pdf_path"])
        row.update(metrics(text))
        row.update(extra or {})
        row["error"] = None
    except Exception as e:
        text = ""
        row["error"] = f"{type(e).__name__}: {e}"
        row.update(metrics(""))
    row["elapsed_s"] = round(time.time() - t0, 2)
    write_result(pdf_info["out_dir"], tool_name, text, row)
    status = "OK" if not row["error"] else f"ERR: {row['error'][:60]}"
    print(f"  [{tool_name:18s}] {pdf_info['district'][:30]:30s}/{pdf_info['hash']}  "
          f"{row['elapsed_s']:6.2f}s  chars={row['n_chars']:6d} times={row['n_times']:3d}  {status}")


# ---------- fast tools ----------

def t_pdftotext(pdf_path):
    out = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                          capture_output=True, text=True, timeout=60)
    return out.stdout, {}


def t_pdfplumber_lines(pdf_path):
    import pdfplumber
    parts, n_tables = [], 0
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            tabs = page.extract_tables()
            n_tables += len(tabs)
            for t in tabs:
                parts.append("\n".join(" | ".join(c or "" for c in row) for row in t))
    return "\n\n".join(parts), {"n_tables": n_tables}


def t_pdfplumber_text(pdf_path):
    import pdfplumber
    parts, n_tables = [], 0
    settings = {"vertical_strategy": "text", "horizontal_strategy": "text"}
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            tabs = page.extract_tables(settings)
            n_tables += len(tabs)
            for t in tabs:
                parts.append("\n".join(" | ".join(c or "" for c in row) for row in t))
    return "\n\n".join(parts), {"n_tables": n_tables}


def t_pymupdf(pdf_path):
    import fitz
    parts, n_tables = [], 0
    doc = fitz.open(str(pdf_path))
    for page in doc:
        tf = page.find_tables()
        n_tables += len(tf.tables)
        for t in tf.tables:
            parts.append("\n".join(" | ".join(str(c) if c is not None else "" for c in row)
                                    for row in t.extract()))
    return "\n\n".join(parts), {"n_tables": n_tables}


def _camelot(pdf_path, flavor):
    import camelot
    tables = camelot.read_pdf(str(pdf_path), flavor=flavor, pages="all")
    parts = ["\n".join(" | ".join(row) for row in t.data) for t in tables]
    return "\n\n".join(parts), {"n_tables": len(tables)}


def t_camelot_stream(pdf_path):
    return _camelot(pdf_path, "stream")


def t_camelot_network(pdf_path):
    return _camelot(pdf_path, "network")


def t_camelot_hybrid(pdf_path):
    return _camelot(pdf_path, "hybrid")


def t_camelot_lattice(pdf_path):
    return _camelot(pdf_path, "lattice")


_TESSERACT_OCR = None


def _img2table_ocr():
    global _TESSERACT_OCR
    if _TESSERACT_OCR is None:
        from img2table.ocr import TesseractOCR
        _TESSERACT_OCR = TesseractOCR(lang="eng")
    return _TESSERACT_OCR


def _img2table(pdf_path, borderless):
    from img2table.document import PDF
    pdf = PDF(str(pdf_path))
    result = pdf.extract_tables(ocr=_img2table_ocr(), borderless_tables=borderless)
    parts, n_tables = [], 0
    for page_tables in result.values():
        n_tables += len(page_tables)
        for t in page_tables:
            df = t.df
            parts.append(df.to_string())
    return "\n\n".join(parts), {"n_tables": n_tables}


def t_img2table_bordered(pdf_path):
    return _img2table(pdf_path, borderless=False)


def t_img2table_borderless(pdf_path):
    return _img2table(pdf_path, borderless=True)


def _rasterize(pdf_path: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "_raster"
    subprocess.run(["pdftoppm", "-png", "-r", "200", str(pdf_path), str(prefix)],
                    capture_output=True, timeout=120)
    return sorted(out_dir.glob("_raster*.png"))


def t_tesseract(pdf_path, out_dir):
    pages = _rasterize(pdf_path, out_dir)
    text = "\n".join(
        subprocess.run(["tesseract", str(p), "stdout"], capture_output=True, text=True, timeout=60).stdout
        for p in pages
    )
    return text, {"n_pages": len(pages)}


FAST_TOOLS = [
    ("pdftotext", t_pdftotext),
    ("pdfplumber_lines", t_pdfplumber_lines),
    ("pdfplumber_text", t_pdfplumber_text),
    ("pymupdf", t_pymupdf),
    ("camelot_stream", t_camelot_stream),
    ("camelot_network", t_camelot_network),
    ("camelot_hybrid", t_camelot_hybrid),
    ("camelot_lattice", t_camelot_lattice),
    ("img2table_bordered", t_img2table_bordered),
    ("img2table_borderless", t_img2table_borderless),
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = discover_pdfs()
    print(f"Found {len(pdfs)} PDFs across {len(set(p['district'] for p in pdfs))} districts.\n")

    for i, pdf_info in enumerate(pdfs, 1):
        print(f"-- [{i}/{len(pdfs)}] {pdf_info['district']}/{pdf_info['hash']} ({pdf_info['kind']}, "
              f"existing text_times={pdf_info['text_times']}) --")
        for name, fn in FAST_TOOLS:
            run_tool(name, fn, pdf_info)
        run_tool("tesseract", lambda p, d=pdf_info["out_dir"]: t_tesseract(p, d), pdf_info)

    print("\nDone. Summary at", SUMMARY)


if __name__ == "__main__":
    main()
