"""Stage 4 (Local processing) of the bell-schedule acquisition pipeline.

Reads each district's captures.json (Stage 3's output) from
data/raw/lea-website-captures/<id>_<slug>/ -- never modifies it. Unlike Stage 2/3, there is
no separate external/risky worker here (no browser, no subagent): the real work
(pdftotext/pdfplumber/camelot/tesseract, all fast local calls) lives in this same module
alongside the orchestration, since there is nothing risky/non-Python to delegate to.

Run every KEPT tool against every applicable input, always -- no waterfall, no gating on
prior success (resolved 2026-06-23 by a real spike against all 150 captured PDFs in
batch_00001 -- see docs/ACQUISITION_PIPELINE.md Stage 4):
  - pdftotext -layout, pdfplumber (lines strategy), camelot (stream + hybrid flavors) --
    table-tool output rendered as real Markdown-table syntax, not flattened pipe-text --
    run on every PDF, unconditionally.
  - Tesseract OCR -- run on every image: the existing page.png (browser screenshot),
    original.<img> (direct image download), AND a fresh pdftoppm rasterization of any PDF
    present. Persisted (not ephemeral, unlike reading.py's tempdir precedent) and kept as
    SEPARATE inputs (tesseract_screenshot / tesseract_image / tesseract_raster) since
    print-CSS can reflow differently than the on-screen render.
  - The existing .txt/.md/.csv (already written by Stage 3 / a Drive export) is evaluated
    against the same usable-text bar, with no special priority -- referenced, never
    rewritten.

Every attempted representation -- success, below-bar, OR errored -- gets an entry in
processed.json's texts[] list (completeness, not just success, is the audit bar, same as
discovery.json). Stage 4 does NOT rank/compare across representations -- that is Stage 5's
job; Stage 4 only decides per-representation usability.

Filesystem is authoritative: a district's processed.json existing IS "Stage 4 done" -- the
registry is a cache, reconciled FROM disk, never the reverse. See reconcile().

Usage:
  process_stage4.py reconcile [--root data/raw/lea-website-captures]
  process_stage4.py run <district_id> [--root data/raw/lea-website-captures]
  process_stage4.py run --all [--root data/raw/lea-website-captures]
"""
import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.acquisition.common import district_status as DS


RAW_DIR = Path("data/raw/lea-website-captures")

TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?")
USABLE_MIN_CHARS = 120  # reused from reading.py's PDF_MIN_TEXT_CHARS precedent, not a new number
USABLE_PRINTABLE_RATIO = 0.85
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff")


def metrics(text: str | None) -> tuple[int, int]:
    text = text or ""
    return len(text), len(TIME_RE.findall(text))


def is_usable(text: str | None) -> bool:
    """Recognizable text, not garbled binary -- non-trivial length + printable-character
    sanity check. Deliberately NOT a relevance/keyword check (that's Stage 5's job) --
    keeping "is this text" and "is this text about a schedule" separate is what keeps
    Stage 4 and Stage 5 from collapsing into one stage."""
    text = (text or "").strip()
    if len(text) < USABLE_MIN_CHARS:
        return False
    printable = sum(1 for c in text if c.isprintable() or c in "\n\t\r")
    return (printable / len(text)) >= USABLE_PRINTABLE_RATIO


# ---------------- find / reconcile (mirrors discover_stage2.py / capture_stage3.py) ----------------

def find_districts(root: Path) -> list[dict]:
    """Every directory under root with a captures.json (Stage 3's output) AND a
    discovery.json (district_id/name/state aren't in captures.json itself -- pulled from
    discovery.json, same as capture_stage3.py does for candidates.json)."""
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        cap_path, disc_path = d / "captures.json", d / "discovery.json"
        if not (d.is_dir() and cap_path.exists() and disc_path.exists()):
            continue
        disc = json.loads(disc_path.read_text())
        out.append({
            "district_id": disc["district_id"], "name": disc["name"], "state": disc["state"],
            "dir": d, "captures": json.loads(cap_path.read_text()),
        })
    return out


def check_file_consistency(district: dict) -> None:
    """Finer-grained than the registry check below: every ok:true record's files{} entries
    must actually exist on disk. A mismatch means something structurally broke (a partial
    write, a manual deletion, a Stage 3 bug) -- halt the entire run, same severity as
    registry-ahead-of-disk, not worked around or skipped. ok:false records (files: {} by
    design -- capture_failed, needs_oauth_reauth) are exempt, not an inconsistency."""
    for rec in district["captures"]:
        if not rec.get("ok"):
            continue
        record_dir = district["dir"] / "captures" / rec["hash"]
        for fname in (rec.get("files") or {}).values():
            if not (record_dir / fname).exists():
                raise SystemExit(
                    f"CONTROL FAILURE: {district['district_id']} ({district['name']}) "
                    f"captures.json claims '{fname}' exists in {record_dir} but it does "
                    f"not. Stopping the entire run -- investigate before re-running anything."
                )


def reconcile(districts: list[dict], registry: dict) -> tuple[list, list]:
    """Filesystem is truth, same shape as Stage 2/3 reconcile() -- plus the file-existence
    check above, run before any registry comparison so a structural problem is caught even
    on a district that would otherwise look 'todo'."""
    todo, skipped = [], []
    for d in districts:
        check_file_consistency(d)
        did = d["district_id"]
        done_on_disk = (d["dir"] / "processed.json").exists()
        rec = registry["districts"].get(did)
        reg_says_done = rec is not None and rec.get("furthest_stage", 0) >= 4
        if done_on_disk and not reg_says_done:
            DS.record_stage(registry, did, d["name"], d["state"], stage=4,
                             stage_name="process", outcome="reconciled_from_disk")
            skipped.append(d)
        elif done_on_disk and reg_says_done:
            skipped.append(d)
        elif not done_on_disk and reg_says_done:
            raise SystemExit(
                f"CONTROL FAILURE: registry says {did} ({d['name']}) reached Stage 4+ but "
                f"{d['dir'] / 'processed.json'} does not exist. Stopping the entire run -- "
                f"investigate before re-running anything."
            )
        else:
            todo.append(d)
    return todo, skipped


# ---------------- tool runners ----------------

def _run(cmd: list[str], timeout: int = 60) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.stdout or ""


def run_pdftotext(pdf_path: Path) -> str:
    return _run(["pdftotext", "-layout", str(pdf_path), "-"])


def _rows_to_markdown(rows: list) -> str:
    """Real Markdown-table syntax (header row + --- separator), not the ad hoc pipe-join
    the exploratory spike used -- preserves row/column structure unambiguously and reads
    natively to both a human reviewer and Stage 7's council. Kept as plain .txt (not .md)
    per the user's call -- the file extension is invisible to the model either way, since
    content is pasted into a prompt string, not uploaded as a file."""
    if not rows:
        return ""
    width = max(len(r) for r in rows)

    def cells(row):
        out = [("" if c is None else " ".join(str(c).split())) for c in row]
        return out + [""] * (width - len(out))

    lines = ["| " + " | ".join(cells(rows[0])) + " |", "|" + "|".join([" --- "] * width) + "|"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(cells(row)) + " |")
    return "\n".join(lines)


def run_pdfplumber_lines(pdf_path: Path) -> str:
    import pdfplumber
    blocks = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                md = _rows_to_markdown(table)
                if md:
                    blocks.append(md)
    return "\n\n".join(blocks)


def _camelot(pdf_path: Path, flavor: str) -> str:
    import camelot
    tables = camelot.read_pdf(str(pdf_path), flavor=flavor, pages="all")
    blocks = [_rows_to_markdown(t.data) for t in tables]
    return "\n\n".join(b for b in blocks if b)


def run_camelot_stream(pdf_path: Path) -> str:
    return _camelot(pdf_path, "stream")


def run_camelot_hybrid(pdf_path: Path) -> str:
    return _camelot(pdf_path, "hybrid")


PDF_TOOLS = [
    ("pdftotext", run_pdftotext),
    ("pdfplumber_lines", run_pdfplumber_lines),
    ("camelot_stream", run_camelot_stream),
    ("camelot_hybrid", run_camelot_hybrid),
]


def rasterize(pdf_path: Path, out_dir: Path) -> list[Path]:
    """Persisted, not ephemeral -- a deliberate departure from reading.py's tempdir
    precedent, since Stage 4 keeps every representation inspectable in captures/<hash>/,
    same as page.txt/page.png/page.pdf. Named raster_p<N>.png so it never collides with
    Stage 3's page.png -- a genuinely different rendering path (print-CSS reflow can
    differ from the on-screen render), kept as a separate OCR input, not a substitute."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "raster_p"
    subprocess.run(["pdftoppm", "-png", "-r", "200", str(pdf_path), str(prefix)],
                    capture_output=True, timeout=120)
    return sorted(out_dir.glob("raster_p*.png"))


def run_tesseract(image_path: Path) -> str:
    return _run(["tesseract", str(image_path), "stdout"])


def run_tesseract_multi(image_paths: list[Path]) -> str:
    return "\n".join(run_tesseract(p) for p in image_paths)


# ---------------- per-record processing ----------------

def process_record(rec: dict, record_dir: Path) -> dict:
    """Build the texts[] list for one captures.json record -- every kept tool run against
    every applicable input it has, unconditionally; every attempt (success, below-bar, or
    errored) gets an entry, never silently omitted (completeness is the audit bar)."""
    files = rec.get("files") or {}
    texts: list[dict] = []

    def add(source: str, text: str | None, error: str | None, text_file: str | None, write: bool):
        n_chars, n_times = metrics(text)
        usable = is_usable(text) if error is None else False
        if write and error is None and text_file:
            (record_dir / text_file).write_text(text or "")
        entry = {"source": source, "text_file": text_file if error is None else None,
                  "n_chars": n_chars, "n_times": n_times, "usable": usable}
        if error:
            entry["error"] = error
        texts.append(entry)

    # 1. Pre-existing Stage-3 / Drive-export files -- referenced directly, never rewritten.
    for key, source in (("txt", "txt"), ("md", "md"), ("csv", "csv")):
        if key not in files:
            continue
        existing_path = record_dir / files[key]
        try:
            text = existing_path.read_text(errors="replace")
            add(source, text, None, files[key], write=False)
        except Exception as e:
            add(source, None, f"{type(e).__name__}: {e}", None, write=False)

    # 2. PDF -- all 4 kept tools, unconditionally. A 'bin' file that's actually a PDF
    # (direct-download case) counts too.
    pdf_file = files.get("pdf")
    if not pdf_file and files.get("bin", "").lower().endswith(".pdf"):
        pdf_file = files["bin"]
    pdf_path = (record_dir / pdf_file) if pdf_file else None
    has_pdf = pdf_path is not None and pdf_path.exists()
    if has_pdf:
        for tool_name, fn in PDF_TOOLS:
            try:
                add(tool_name, fn(pdf_path), None, f"{tool_name}.txt", write=True)
            except Exception as e:
                add(tool_name, None, f"{type(e).__name__}: {e}", None, write=False)

    # 3a. Existing browser screenshot (html-kind) -- OCR unconditionally.
    if "png" in files:
        png_path = record_dir / files["png"]
        try:
            add("tesseract_screenshot", run_tesseract(png_path), None,
                "tesseract_screenshot.txt", write=True)
        except Exception as e:
            add("tesseract_screenshot", None, f"{type(e).__name__}: {e}", None, write=False)

    # 3b. A direct image download ('bin' that isn't a PDF) -- OCR unconditionally.
    bin_file = files.get("bin")
    if bin_file and not bin_file.lower().endswith(".pdf"):
        if bin_file.lower().endswith(IMAGE_EXTS):
            img_path = record_dir / bin_file
            try:
                add("tesseract_image", run_tesseract(img_path), None,
                    "tesseract_image.txt", write=True)
            except Exception as e:
                add("tesseract_image", None, f"{type(e).__name__}: {e}", None, write=False)
        else:
            add("tesseract_image", None, f"unhandled bin format: {bin_file}", None, write=False)

    # 3c. A fresh rasterization of any PDF present -- OCR unconditionally, even when 3a
    # already ran (print-CSS reflow can make these genuinely different inputs).
    if has_pdf:
        try:
            pages = rasterize(pdf_path, record_dir)
            if pages:
                add("tesseract_raster", run_tesseract_multi(pages), None,
                    "tesseract_raster.txt", write=True)
            else:
                add("tesseract_raster", None, "pdftoppm produced no pages", None, write=False)
        except Exception as e:
            add("tesseract_raster", None, f"{type(e).__name__}: {e}", None, write=False)

    return {"url": rec["url"], "hash": rec["hash"],
            "usable": any(t["usable"] for t in texts), "texts": texts}


def process_district(district: dict) -> list[dict]:
    return [
        process_record(rec, district["dir"] / "captures" / rec["hash"])
        for rec in district["captures"] if rec.get("ok")
    ]


def compute_outcome(processed_records: list[dict]) -> str:
    """processed_all / processed_partial / no_usable_text_any -- same three-way shape as
    Stage 2/3's outcomes, rolled up from each record's usable flag."""
    if not processed_records:
        return "no_usable_text_any"
    usable_count = sum(1 for r in processed_records if r["usable"])
    if usable_count == len(processed_records):
        return "processed_all"
    if usable_count == 0:
        return "no_usable_text_any"
    return "processed_partial"


def write_processed(district: dict, records: list[dict]) -> Path:
    """Never overwritten in place -- an existing processed.json is renamed aside with a
    UTC timestamp suffix first, the same convention discover_stage2.py's write_discovery()
    already uses for discovery.json/candidates.json (and capture_discovery.mjs now matches
    too, after this same round of work)."""
    path = district["dir"] / "processed.json"
    if path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path.rename(district["dir"] / f"processed.{ts}.json")
    path.write_text(json.dumps(records, indent=2))
    return path


def finish_district(district: dict, registry: dict) -> str:
    """Single registry write per district, at actual completion -- same principle as
    Stage 2/3: there's nothing meaningful to reconcile against a half-finished state."""
    check_file_consistency(district)
    records = process_district(district)
    write_processed(district, records)
    outcome = compute_outcome(records)
    DS.record_stage(registry, district["district_id"], district["name"], district["state"],
                     stage=4, stage_name="process", outcome=outcome)
    return outcome


def main():
    ap = argparse.ArgumentParser(description="Stage 4 (Local processing)")
    ap.add_argument("--root", default=str(RAW_DIR))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reconcile")

    p = sub.add_parser("run")
    p.add_argument("district_id", nargs="?")
    p.add_argument("--all", action="store_true")

    a = ap.parse_args()
    root = Path(a.root)
    districts = find_districts(root)
    registry = DS.load()

    if a.cmd == "reconcile":
        todo, skipped = reconcile(districts, registry)
        DS.save(registry)
        print(f"{len(todo)} to process, {len(skipped)} already done (skipped)")
        for d in skipped:
            print(f"  skip [{d['state']}] {d['name']} ({d['district_id']})")
        for d in todo:
            print(f"  todo [{d['state']}] {d['name']} ({d['district_id']})")

    elif a.cmd == "run":
        if a.all:
            todo, _ = reconcile(districts, registry)
            for d in todo:
                outcome = finish_district(d, registry)
                print(f"{d['district_id']} {d['name']}: {outcome}")
        elif a.district_id:
            district = next((d for d in districts if d["district_id"] == a.district_id), None)
            if district is None:
                raise SystemExit(
                    f"district {a.district_id} not found under {root} "
                    f"(needs captures.json + discovery.json)"
                )
            outcome = finish_district(district, registry)
            print(f"{district['district_id']} {district['name']}: {outcome}")
        else:
            raise SystemExit("run requires a district_id or --all")
        DS.save(registry)


if __name__ == "__main__":
    main()
