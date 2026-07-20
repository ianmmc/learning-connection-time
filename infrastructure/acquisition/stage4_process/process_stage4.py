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
from pathlib import Path
from urllib.parse import unquote

from infrastructure.acquisition.common import batch_guard as BG
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS
from infrastructure.acquisition.common import timeutil as TU


RAW_DIR = Path("data/raw/lea-website-captures")

TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(?:[AaPp]\.?[Mm]\.?)?")
# #518 time_blind: a URL that PROMISES a schedule (capture metadata, not text content -- the
# text-aboutness judgment stays Stage 5's, per is_usable's docstring) whose usable reps all
# recovered zero clock times. Sized by the 2026-07-19 corpus survey: 61 such records, incl.
# CMS document-viewer pages and soft-404s -- the class that otherwise lands as a silent
# target_absent at Stage 5. Matched against the UNQUOTED url (see sched_url_matches) -- a
# `[-_ %]?` character class can only ever consume a single literal `%`, never a real
# percent-encoded separator like `%20` (3 chars); the in-corpus survey found real captures
# named e.g. "Bell%20Schedule%20pdf.pdf" that a raw match on this pattern silently misses.
SCHED_URL_RE = re.compile(r"bell[-_ ]?schedule|daily[-_ ]?schedule|school[-_ ]?hours|class[-_ ]?times", re.I)


def sched_url_matches(url: str) -> bool:
    """SCHED_URL_RE over the percent-DECODED url -- see the pattern's own comment for why a
    raw match on encoded URLs (e.g. bell%20schedule) would silently miss real captures."""
    try:
        return bool(SCHED_URL_RE.search(unquote(url or "")))
    except Exception:
        return bool(SCHED_URL_RE.search(url or ""))
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


class InconsistentCapturesError(RuntimeError):
    """A district's captures.json claims files that aren't on disk (see check_file_consistency)."""


def check_file_consistency(district: dict) -> list[str]:
    """Finer-grained than the registry check below: every ok:true record's files{} entries
    must actually exist on disk. A mismatch means something structurally broke for THAT
    district (a partial write, a manual deletion, a Stage 3 bug). Returns the list of
    problems (empty = consistent). The blast radius is tiered (#78): an inconsistent
    district is QUARANTINED by reconcile() -- excluded from the run, reported loudly, and
    surfaced like `failed` -- rather than SystemExit-ing the whole run, because one
    district's broken captures say nothing about the rest of the batch.
    Registry-ahead-of-disk (reconcile's other check) KEEPS the hard stop: that one is a
    control-layer failure, not a per-district data problem. ok:false records (files: {} by
    design -- capture_failed, needs_oauth_reauth) are exempt, not an inconsistency."""
    problems = []
    for rec in district["captures"]:
        if not rec.get("ok"):
            continue
        record_dir = district["dir"] / "captures" / rec["hash"]
        for fname in (rec.get("files") or {}).values():
            if not isinstance(fname, str) or not fname:
                # #351: a non-string files{} value (hand-edited/corrupt manifest) must surface as
                # an inconsistency, not a TypeError that aborts the whole reconcile.
                problems.append(
                    f"captures.json has a non-string files entry {fname!r} in {record_dir}"
                )
            elif not (record_dir / fname).exists():
                problems.append(
                    f"captures.json claims '{fname}' exists in {record_dir} but it does not"
                )
    return problems


def reconcile(districts: list[dict], registry: dict, *, redo: bool = False) -> tuple[list, list, list]:
    """Filesystem is truth, same shape as Stage 2/3 reconcile() -- plus the file-existence
    check above, run ONLY on districts about to be processed (an already-done district is
    not gated retroactively). Returns (todo, skipped, quarantined): a quarantined district
    is inconsistent on disk (#78) -- excluded from the run with a loud per-district report
    line and its problems attached as d['inconsistency']; the caller surfaces it like a
    `failed` district. Registry-ahead-of-disk stays a run-halting SystemExit.

    `redo=True` (a follow-up batch, issue #174): 'processed.json exists' must not skip -- the
    district's captures.json is now the prior+delta UNION, and process_district rebuilds
    processed.json from it in full (local CPU only; the old file is renamed aside), so the
    processed manifest stays complete. Consistency check + control-failure halt unchanged."""
    todo, skipped, quarantined = [], [], []
    for d in districts:
        did = d["district_id"]
        done_on_disk = (d["dir"] / "processed.json").exists()
        rec = registry["districts"].get(did)
        reg_says_done = rec is not None and rec.get("furthest_stage", 0) >= 4
        if not done_on_disk and reg_says_done:
            # #572: same receipted exception as the Stage 2/3 reconciles — a decontaminated
            # district processes fresh instead of halting (see DS.remediation_receipt).
            receipt = DS.remediation_receipt(did)
            if receipt is not None:
                print(f"  [reconcile] {did} ({d['name']}): registry ahead of disk, EXPLAINED by "
                      f"the decontamination restore point {receipt.name} — processing fresh")
            else:
                raise SystemExit(
                    f"CONTROL FAILURE: registry says {did} ({d['name']}) reached Stage 4+ but "
                    f"{d['dir'] / 'processed.json'} does not exist. Stopping the entire run -- "
                    f"investigate before re-running anything."
                )
        if done_on_disk and not redo:
            if not reg_says_done:
                DS.record_stage(registry, did, d["name"], d["state"], stage=4,
                                 stage_name="process", outcome="reconciled_from_disk")
            skipped.append(d)
            continue
        problems = check_file_consistency(d)
        if problems:
            for p in problems:
                print(f"QUARANTINED (inconsistent captures) {did} ({d['name']}): {p}")
            d["inconsistency"] = problems
            quarantined.append(d)
        else:
            todo.append(d)
    return todo, skipped, quarantined


# ---------------- tool runners ----------------

class ToolError(RuntimeError):
    """A tool subprocess failed in a way that left no usable output."""


def _run(cmd: list[str], timeout: int = 60) -> str:
    """Run a local tool and return its stdout.

    Exit-code policy (#32): a nonzero exit with EMPTY stdout is an error -- raised, so the
    caller's add() records an `error` entry instead of a silent, non-errored empty
    representation. A nonzero exit WITH non-empty stdout is treated as success: pdftotext/
    tesseract commonly warn on stderr and exit nonzero while still emitting perfectly usable
    text, and the text itself is the product Stage 4 is after (the usable-text bar then
    judges it like any other output)."""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = p.stdout or ""
    if p.returncode != 0 and not out.strip():
        raise ToolError(f"exit {p.returncode}: {(p.stderr or '').strip()[:120]}")
    return out


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


# OCR page budget (#45): a 100-page handbook must not queue 100 sequential 60s-budget
# tesseract calls. pdftoppm rasterizes at most this many pages (-l) and run_tesseract_multi
# OCRs at most this many images. Module-level so a config change / test override is one line.
OCR_RASTER_PAGE_CAP = 40


def rasterize(pdf_path: Path, out_dir: Path) -> list[Path]:
    """Persisted, not ephemeral -- a deliberate departure from reading.py's tempdir
    precedent, since Stage 4 keeps every representation inspectable in captures/<hash>/,
    same as page.txt/page.png/page.pdf. Named raster_p<N>.png so it never collides with
    Stage 3's page.png -- a genuinely different rendering path (print-CSS reflow can
    differ from the on-screen render), kept as a separate OCR input, not a substitute.

    #45 hardening: stale raster_p*.png from a prior failed/partial run are cleared first
    (they'd otherwise be globbed up as if this rasterization produced them); pages are
    capped at OCR_RASTER_PAGE_CAP via -l; and pdftoppm's exit code is checked -- a nonzero
    exit that produced NO pages raises (a nonzero exit with some pages proceeds with the
    partial set, same spirit as _run's stdout policy)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("raster_p*.png"):
        stale.unlink()
    prefix = out_dir / "raster_p"
    p = subprocess.run(["pdftoppm", "-png", "-r", "200",
                        "-l", str(OCR_RASTER_PAGE_CAP), str(pdf_path), str(prefix)],
                       capture_output=True, text=True, timeout=120)
    pages = sorted(out_dir.glob("raster_p*.png"))
    if p.returncode != 0 and not pages:
        raise ToolError(f"pdftoppm exit {p.returncode}: {(p.stderr or '').strip()[:120]}")
    return pages


def run_tesseract(image_path: Path) -> str:
    return _run(["tesseract", str(image_path), "stdout"])


def run_tesseract_multi(image_paths: list[Path]) -> str:
    """OCR up to OCR_RASTER_PAGE_CAP pages with per-page error tolerance (#45): one page's
    timeout/crash records an inline note and keeps every other page's text, instead of
    discarding the whole document; pages beyond the cap record a note, not silence."""
    parts = []
    capped = list(image_paths)[:OCR_RASTER_PAGE_CAP]
    for p in capped:
        try:
            parts.append(run_tesseract(p))
        except Exception as e:  # noqa: BLE001 -- per-page tolerance is the point
            parts.append(f"[ocr failed: {p.name}: {type(e).__name__}: {str(e)[:80]}]")
    skipped = len(image_paths) - len(capped)
    if skipped > 0:
        parts.append(f"[ocr page cap: {skipped} page(s) beyond {OCR_RASTER_PAGE_CAP} not OCR'd]")
    return "\n".join(parts)


# ---------------- per-record processing ----------------

def process_record(rec: dict, record_dir: Path) -> dict:
    """Build the texts[] list for one captures.json record -- every kept tool run against
    every applicable input it has, unconditionally; every attempt (success, below-bar, or
    errored) gets an entry, never silently omitted (completeness is the audit bar)."""
    # #351: drop non-string files{} values up front -- Stage 3 never writes them, but a
    # hand-edited/corrupt manifest must degrade to "that representation is absent", not an
    # AttributeError on .lower() mid-district.
    files = {k: v for k, v in (rec.get("files") or {}).items() if isinstance(v, str) and v}
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

    out = {"url": rec["url"], "hash": rec["hash"],
           "usable": any(t["usable"] for t in texts), "texts": texts}
    # #518 time_blind: only the SILENT failure shape gets the flag -- usable text came back
    # (so nothing else marks the record suspect) from a schedule-promising URL, yet no USABLE
    # rep holds a single clock time (a spurious time in a garbled below-bar OCR rep must not
    # suppress the flag -- Stage 5 reads the usable reps). Unusable/errored records are already
    # visible via `usable`.
    if out["usable"] and all(t["n_times"] == 0 for t in texts if t["usable"]) \
            and (sched_url_matches(rec["url"]) or sched_url_matches(rec.get("final_url"))):
        out["fidelity"] = ["time_blind"]
    return out


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
        ts = TU.fs_stamp()
        path.rename(district["dir"] / f"processed.{ts}.json")
    path.write_text(json.dumps(records, indent=2))
    return path


def finish_district(district: dict, registry: dict) -> str:
    """Single registry write per district, at actual completion -- same principle as
    Stage 2/3: there's nothing meaningful to reconcile against a half-finished state.
    Belt-and-braces re-check of file consistency (#78): reconcile() already quarantines,
    but the direct `run <district_id>` path reaches here without it -- raise a district-
    scoped error, never a run-halting SystemExit."""
    problems = check_file_consistency(district)
    if problems:
        raise InconsistentCapturesError("; ".join(problems))
    records = process_district(district)
    write_processed(district, records)
    outcome = compute_outcome(records)
    DS.record_stage(registry, district["district_id"], district["name"], district["state"],
                     stage=4, stage_name="process", outcome=outcome)
    # Project this district's processed-doc rows into the live DB cache. Best-effort: processed.json
    # on disk + the state_event are the durable record.
    CI.cache_processed(district["dir"], district["district_id"])
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
        todo, skipped, quarantined = reconcile(districts, registry)
        DS.save(registry)
        print(f"{len(todo)} to process, {len(skipped)} already done (skipped), "
              f"{len(quarantined)} quarantined (inconsistent)")
        for d in skipped:
            print(f"  skip [{d['state']}] {d['name']} ({d['district_id']})")
        for d in quarantined:
            print(f"  inconsistent [{d['state']}] {d['name']} ({d['district_id']})")
        for d in todo:
            print(f"  todo [{d['state']}] {d['name']} ({d['district_id']})")

    elif a.cmd == "run":
        if a.all:
            todo, _, quarantined = reconcile(districts, registry)
            # #168/#206 review: run writes processed.json + state_events — refuse any district whose
            # artifacts belong to a terminal abandoned batch (halts the sweep, matching the reconcile
            # checks' fail-loud convention; the dir's discovery.json records the producing batch).
            with gdb.session_scope() as _con:
                for d in todo:
                    BG.assert_district_runnable(_con, d["dir"])
            for d in quarantined:
                DS.record_stage(registry, d["district_id"], d["name"], d["state"],
                                 stage_name="process", event_type="failed",
                                 notes="inconsistent: " + "; ".join(d["inconsistency"])[:200])
                print(f"{d['district_id']} {d['name']}: inconsistent (quarantined)")
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
            with gdb.session_scope() as _con:   # #168/#206 review: same guard, single-district form
                BG.assert_district_runnable(_con, district["dir"])
            outcome = finish_district(district, registry)
            print(f"{district['district_id']} {district['name']}: {outcome}")
        else:
            raise SystemExit("run requires a district_id or --all")
        DS.save(registry)


if __name__ == "__main__":
    main()
