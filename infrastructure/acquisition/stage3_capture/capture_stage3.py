"""Stage 3 (Capture) of the bell-schedule acquisition pipeline -- the orchestration half.

Reads each district's candidates.json (Stage 2's deduped, capture-ready URL list) from
data/raw/lea-website-captures/<id>_<slug>/ -- never modifies it. The actual browser
automation (Playwright: fetch/render/modal-dismissal/page.pdf()/Drive handling/emergent-
candidate discovery) lives in infrastructure/scraper/capture_discovery.mjs; this module is
the Python control layer around it: reconciliation, outcome rollup, and the single
registry write-back, exactly mirroring discover_stage2.py's split (Python orchestrates and
owns the registry; a separate process does the risky/external work).

Filesystem is authoritative: a district's captures.json existing in
data/raw/lea-website-captures/<id>_<slug>/ IS "Stage 3 done" -- the registry is a cache of
that fact, reconciled FROM disk, never the reverse. See reconcile().

Usage:
  capture_stage3.py reconcile [--root data/raw/lea-website-captures]
  capture_stage3.py finish    <district_id> [--root data/raw/lea-website-captures]
"""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

from infrastructure.acquisition.common import batch_guard as BG
from infrastructure.acquisition.common import cache_ingest as CI
from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import district_status as DS

IMAGE_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff")


RAW_DIR = Path("data/raw/lea-website-captures")


def find_districts(root: Path) -> list:
    """Every directory under root with a discovery.json (Stage 2's header fields -- name,
    state, domain -- read from there, not candidates.json, which doesn't carry them) AND a
    candidates.json (what Stage 3 actually consumes). A district missing either is not
    Stage 3's concern yet."""
    out = []
    if not root.exists():
        return out
    for d in sorted(root.iterdir()):
        disc_path, cand_path = d / "discovery.json", d / "candidates.json"
        if not (d.is_dir() and disc_path.exists() and cand_path.exists()):
            continue
        disc = json.loads(disc_path.read_text())
        out.append({
            "district_id": disc["district_id"], "name": disc["name"],
            "state": disc["state"], "domain": disc.get("domain", ""), "dir": d,
        })
    return out


def reconcile(districts: list, registry: dict, *, redo: bool = False) -> tuple[list, list]:
    """Filesystem is truth. For every district with candidates.json ready: if captures.json
    already exists on disk, reconcile the registry up to match (skip -- already done, never
    redo automatically). If the registry claims furthest_stage>=3 but the file does NOT
    exist, that's a control failure, not routine drift -- halt the entire run rather than
    risk propagating whatever caused it to other districts. Returns (todo, skipped).

    `redo=True` (a follow-up batch, issue #174): 'captures.json exists' must not skip -- the
    follow-up exists precisely to redo these districts. The capture runner seeds from the
    prior manifest and captures only the DELTA (seedFromPriorCaptures in the mjs), so the
    redo never re-hits already-captured URLs. The control-failure halt is unchanged."""
    todo, skipped = [], []
    for d in districts:
        did = d["district_id"]
        done_on_disk = (d["dir"] / "captures.json").exists()
        rec = registry["districts"].get(did)
        reg_says_done = rec is not None and rec.get("furthest_stage", 0) >= 3
        if not done_on_disk and reg_says_done:
            raise SystemExit(
                f"CONTROL FAILURE: registry says {did} ({d['name']}) reached Stage 3+ but "
                f"{d['dir'] / 'captures.json'} does not exist. Stopping the entire run -- "
                f"investigate before re-running anything."
            )
        if redo:
            todo.append(d)          # a follow-up IS a deliberate redo -- never skip on disk state
            continue
        if done_on_disk and not reg_says_done:
            DS.record_stage(
                registry, did, d["name"], d["state"], stage=3, stage_name="capture",
                outcome="reconciled_from_disk",
            )
            skipped.append(d)
        elif done_on_disk and reg_says_done:
            skipped.append(d)
        else:                       # not done_on_disk, not reg_says_done (the raise above covered
            todo.append(d)          # the registry-ahead-of-disk case for every batch type)
    return todo, skipped


def compute_outcome(captures: list) -> tuple[str, str]:
    """Roll up per-candidate ok/err into a district-level outcome plus a short notes
    summary. The registry holds this rollup only -- never a live array of open issues
    (a recipe for sync bugs); a human generates the actual triage list on demand by
    scanning captures.json files for a specific err value when ready to act on it."""
    oks = [c for c in captures if c.get("ok")]
    fails = [c for c in captures if not c.get("ok")]
    if not fails:
        outcome = "captured_all"
    elif not oks:
        outcome = "capture_failed_all"
    else:
        outcome = "captured_partial"
    reasons = Counter(c.get("err") or "unknown" for c in fails)
    notes = "; ".join(f"{n} {reason}" for reason, n in reasons.items())
    return outcome, notes


# ---------------------------------------------------------------- manifest recovery (REQ-110 follow-up)
# A Node capture run that is SIGKILLed mid-run (e.g. a transient stall hitting the per-district timeout)
# leaves the per-URL folders on disk but NEVER writes captures.json (the manifest is end-of-run), so the
# completed work is orphaned (no manifest -> invisible to Stage 4 + the cache, the district reads as a
# total failure). These helpers REBUILD a manifest from disk. RECOVERY ONLY: they refuse to overwrite an
# existing captures.json, and the records are DEGRADED vs a live capture (fingerprint / final_url /
# text_times aren't recoverable from disk). The going-forward fix is Node-owns-shutdown (write a partial
# manifest on its own deadline); this is for the already-orphaned districts.

# WHATWG-parity helpers (#43): capture_discovery.mjs's stripFragment() round-trips through
# `new URL(url)` -- which NORMALIZES (lowercase scheme/host, default port dropped, '/' for an
# empty path, dot segments removed, space/unicode percent-encoded) -- so the folder name on
# disk is md5(<normalized url>). A raw '#'-split here hashed the UN-normalized URL and missed
# those folders during reconstruction.
_DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}
# WHATWG leaves these raw in a path (beyond quote()'s always-safe unreserved set).
_PATH_SAFE = "/%:@!$&'()*+,;=~[]-._"
# The query encode set is smaller still (only space, ", #, <, > get encoded).
_QUERY_SAFE = "%/:@!$&'()*+,;=?~[]^`{|}\\-._"


def _remove_dot_segments(path: str) -> str:
    """WHATWG path normalization: /a/../b -> /b, /a/./b -> /a/b, /a/.. -> / (trailing
    '.'/'..' keeps the trailing slash, like new URL())."""
    if not path:
        return path
    segs = path.split("/")
    out: list[str] = []
    for i, seg in enumerate(segs):
        if seg == ".":
            pass
        elif seg == "..":
            if len(out) > 1:
                out.pop()
        else:
            out.append(seg)
            continue
        if i == len(segs) - 1:  # trailing '.'/'..' -> keep a trailing '/'
            out.append("")
    return "/".join(out)


def _strip_fragment(url: str) -> str:
    """Replicate capture_discovery.mjs's stripFragment (new URL(url); u.hash=''; toString())
    for the common cases, so md5(_strip_fragment(url)) matches the per-URL folder Node named:
    lowercase scheme+host, punycode a unicode host, drop the scheme's default port, '/' for an
    empty path, remove dot segments, percent-encode space/unicode in path+query without
    double-encoding existing %XX. Residual (documented, accepted) divergences from Node: a
    bare trailing '?' (Node keeps it, we drop it), '\\' in a special-scheme path (Node
    rewrites it to '/'), malformed %-sequences (both mostly pass them through, but not
    byte-identically in every case), and full IDN/host-validation quirks. Unparseable input
    falls back to the raw '#'-split, matching Node's catch branch."""
    from urllib.parse import quote, urlsplit, urlunsplit
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.split("#", 1)[0]
    scheme = parts.scheme.lower()
    if not scheme or not parts.netloc:
        return url.split("#", 1)[0]
    host = parts.hostname or ""
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            pass
    userinfo = ""
    if parts.username is not None:
        userinfo = parts.username
        if parts.password is not None:
            userinfo += f":{parts.password}"
        userinfo += "@"
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = userinfo + host
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc += f":{port}"
    path = parts.path
    if scheme in _DEFAULT_PORTS:  # the WHATWG "special" schemes
        path = _remove_dot_segments(path) or "/"
        if not path.startswith("/"):
            path = "/" + path
    return urlunsplit((scheme, netloc, quote(path, safe=_PATH_SAFE),
                       quote(parts.query, safe=_QUERY_SAFE), ""))


def _url_hash(url: str) -> str:
    """md5(stripFragment(url))[:10] — identical to capture_discovery.mjs's per-URL folder naming."""
    return hashlib.md5(_strip_fragment(url).encode()).hexdigest()[:10]


def _record_from_folder(folder: Path, url: str, *, tools, source, found_on) -> dict | None:
    """Build a capture record from the files present in a per-URL folder. Returns None for an empty
    (in-flight-at-kill) folder. Carries everything Stage 4 + the cache read (files/kind/ok/url/hash)."""
    if not folder.is_dir():
        return None
    files = sorted(f.name for f in folder.iterdir() if f.is_file())
    if not files:
        return None
    rec = {"url": url, "tools": list(tools or []), "source": source, "found_on": found_on,
           "hash": folder.name, "ok": True, "files": {}, "final_url": url,
           "fingerprint": None, "reconstructed": True}
    if "page.txt" in files:
        rec["kind"] = "html"
        rec["files"]["txt"] = "page.txt"
        if "page.png" in files:
            rec["files"]["png"] = "page.png"
        if "page.pdf" in files:
            rec["files"]["pdf"] = "page.pdf"
        rec["segmented"] = (folder / "page.main.txt").exists()
    elif (orig := next((f for f in files if f.startswith("original.")), None)):
        ext = orig.rsplit(".", 1)[-1].lower()
        rec["kind"] = "image" if ext in IMAGE_EXTS else ("pdf" if ext == "pdf" else "binary")
        rec["files"]["bin"] = orig
    else:   # a Drive export — mirror capture_discovery.mjs's live-path keying (#42): a known
            # format stem (pdf.pdf / md.md / csv.csv) keys as itself, but the generic download
            # `file.<ext>` (format 'auto') is keyed 'bin' by the live path — and Stage 4 only
            # reads txt/md/csv/pdf/bin, so any unrecognized stem maps to 'bin' too (keying it
            # by raw stem made Stage 4 silently skip the recovered file).
        rec["kind"] = "drive_export"
        for f in files:
            stem = f.split(".", 1)[0]
            key = stem if stem in ("txt", "md", "csv", "pdf") else "bin"
            rec["files"].setdefault(key, f)
    return rec


def _journal_records(ddir: Path) -> dict:
    """hash -> record from the #117 per-task journal(s): the live `captures.journal.jsonl` plus any
    timestamp-suffixed crash leftovers a later run renamed aside, oldest first, so the LATEST line
    for a hash wins (a retried record supersedes its earlier attempt). Tolerates a torn final line
    (the SIGKILL landed mid-append) and non-dict lines. {} when no journal exists — reconstruction
    then degrades to the folder-scan path exactly as before #117."""
    out: dict = {}
    live = ddir / "captures.journal.jsonl"
    paths_ = sorted(ddir.glob("captures.journal.*.jsonl")) + ([live] if live.exists() else [])
    for jp in paths_:
        try:
            lines = jp.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue   # torn final line at the kill point, or stray garbage — skip
            if isinstance(rec, dict) and isinstance(rec.get("hash"), str):
                out[rec["hash"]] = rec
    return out


def reconstruct_captures(district: dict) -> list:
    """RECOVERY ONLY: rebuild the captures.json record list after a hard kill. EVERY candidate appears
    (completeness is the audit bar). Two evidence tiers, best first:
      1. the #117 per-task journal (captures.journal.jsonl + renamed-aside leftovers) — FULL-fidelity
         records exactly as the live run built them, including EMERGENT captures whose URL is
         otherwise unrecoverable (md5 is one-way);
      2. the on-disk per-URL folder scan — DEGRADED records (no fingerprint/final_url/text_times),
         for work journaled runs predate or whose journal line was lost.
    A candidate covered by neither is ok=False `not_recovered` -> the district honestly resolves
    `captured_partial`. Refuses if captures.json already exists. Pre-#117 limitation (emergent
    folders left out of the manifest) now applies only when no journal exists."""
    ddir = district["dir"]
    if (ddir / "captures.json").exists():
        raise SystemExit(f"{ddir / 'captures.json'} exists — refusing to overwrite "
                         f"(reconstruction is recovery-only)")
    cand = json.loads((ddir / "candidates.json").read_text()).get("candidates", [])
    capdir = ddir / "captures"
    journal = _journal_records(ddir)
    records = []
    covered = set()
    for c in cand:
        h = _url_hash(c["url"])
        covered.add(h)
        rec = journal.get(h) or _record_from_folder(capdir / h, c["url"], tools=c.get("tools", []),
                                                    source="discovered", found_on=None)
        if rec is None:
            rec = {"url": c["url"], "tools": list(c.get("tools", [])), "source": "discovered",
                   "found_on": None, "hash": h, "ok": False, "files": {},
                   "err": "not_recovered (capture interrupted before completion)"}
        records.append(rec)
    # Journal records beyond the capture plan — emergent (and manual) captures the pre-#117
    # reconstruction had to abandon. Full-fidelity, carried verbatim.
    records.extend(rec for h, rec in journal.items() if h not in covered)
    return records


def manual_capture_record(district: dict, *, url: str, src_file: Path, found_on: str | None = None) -> dict:
    """Drop a human-sourced file into the captures tree as a normal `source:"manual"` capture record
    (manual follow-up — no formal mechanism yet). Copies src_file to captures/<md5(url)>/original.<ext>;
    returns the record for the caller to fold into the manifest."""
    h = _url_hash(url)
    folder = district["dir"] / "captures" / h
    folder.mkdir(parents=True, exist_ok=True)
    ext = (src_file.suffix.lstrip(".") or "bin").lower()
    shutil.copy2(src_file, folder / f"original.{ext}")
    return {"url": url, "tools": [], "source": "manual", "found_on": found_on, "hash": h, "ok": True,
            "files": {"bin": f"original.{ext}"},
            "kind": "image" if ext in IMAGE_EXTS else ("pdf" if ext == "pdf" else "binary"),
            "final_url": url, "fingerprint": None, "reconstructed": True}


def write_manifest(district: dict, records: list) -> None:
    """Atomic write of a reconstructed captures.json (recovery path; refuses to clobber). A LANDED
    manifest supersedes every #117 journal for the district — they are consumed (deleted) here so a
    future reconstruct (after e.g. a re-discovery deletes the manifest) can never resurrect records
    from a defunct round (review finding on #563)."""
    path = district["dir"] / "captures.json"
    if path.exists():
        raise SystemExit(f"{path} exists — refusing to overwrite (reconstruction is recovery-only)")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(records, indent=2))
    tmp.replace(path)
    for jp in list(district["dir"].glob("captures.journal.*.jsonl")) + \
            [district["dir"] / "captures.journal.jsonl"]:
        try:
            jp.unlink()
        except OSError:
            pass   # absent / already swept — the manifest is what matters


def finish_district(district: dict, registry: dict) -> str:
    """Single registry write per district, at actual completion -- never an interim
    'started' marker, same principle as Stage 2: there's nothing meaningful to reconcile
    against a half-finished state, since captures.json only exists once the Node capture
    script has fully finished that district."""
    captures_path = district["dir"] / "captures.json"
    try:
        captures = json.loads(captures_path.read_text())
    except json.JSONDecodeError as e:
        # #267: a truncated/corrupt manifest (crash mid-write) must fail with the recovery path
        # spelled out -- without this, reconcile() skips the district forever (file exists = done)
        # while reconstruct refuses to run (file exists), a silent wedge.
        # The command must match the reconstruct subparser's REAL signature (a single
        # district_id positional; --root optional) -- the review caught the first draft
        # citing a nonexistent <batch.json> argument, the opposite of a recovery aid.
        raise RuntimeError(
            f"corrupt captures.json for {district['district_id']} at {captures_path}: {e}. "
            f"Recovery: move the corrupt file aside, then rebuild it from the captures/ tree with "
            f"`python3 -m infrastructure.acquisition.stage3_capture.capture_stage3 reconstruct "
            f"{district['district_id']}`"
        ) from e
    outcome, notes = compute_outcome(captures)
    DS.record_stage(
        registry, district["district_id"], district["name"], district["state"],
        stage=3, stage_name="capture", outcome=outcome, notes=notes,
    )
    # Project this district's capture receipts into the live DB cache (the console's Stage-3 surface
    # reads them). Best-effort: captures.json on disk + the state_event are the durable record.
    CI.cache_capture(district["dir"], district["district_id"])
    return outcome


def main():
    ap = argparse.ArgumentParser(description="Stage 3 (Capture), orchestration half")
    ap.add_argument("--root", default=str(RAW_DIR))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("reconcile")

    p = sub.add_parser("finish")
    p.add_argument("district_id")

    # Recovery: rebuild captures.json from disk for a district orphaned by a mid-run SIGKILL.
    pr = sub.add_parser("reconstruct", help="rebuild captures.json from on-disk capture folders (recovery)")
    pr.add_argument("district_id")
    pr.add_argument("--manual-file", help="a human-sourced file to add as a source:manual capture record")
    pr.add_argument("--manual-url", help="the origin URL/page for --manual-file (hashed to the folder name)")

    a = ap.parse_args()
    root = Path(a.root)
    districts = find_districts(root)

    if a.cmd == "reconcile":
        registry = DS.load()
        todo, skipped = reconcile(districts, registry)
        DS.save(registry)
        print(f"{len(todo)} to capture, {len(skipped)} already done (skipped)")
        for d in skipped:
            print(f"  skip [{d['state']}] {d['name']} ({d['district_id']})")
        for d in todo:
            print(f"  todo [{d['state']}] {d['name']} ({d['district_id']})")

    elif a.cmd == "finish":
        district = next((d for d in districts if d["district_id"] == a.district_id), None)
        if district is None:
            raise SystemExit(f"district {a.district_id} not found under {root} (needs discovery.json + candidates.json)")
        # #168/#206 review: finish writes captures.json state + a state_event — refuse if this district's
        # artifacts belong to a terminal abandoned batch (the dir's discovery.json records which).
        with gdb.session_scope() as _con:
            BG.assert_district_runnable(_con, district["dir"])
        registry = DS.load()
        outcome = finish_district(district, registry)
        DS.save(registry)
        print(f"{district['district_id']} {district['name']}: {outcome}")

    elif a.cmd == "reconstruct":
        district = next((d for d in districts if d["district_id"] == a.district_id), None)
        if district is None:
            raise SystemExit(f"district {a.district_id} not found under {root} (needs discovery.json + candidates.json)")
        # #168/#206 review: the recovery path also writes captures.json + a state_event — same guard.
        with gdb.session_scope() as _con:
            BG.assert_district_runnable(_con, district["dir"])
        records = reconstruct_captures(district)
        if a.manual_file:
            if not a.manual_url:
                raise SystemExit("--manual-file requires --manual-url (the origin page, hashed to the folder)")
            records.append(manual_capture_record(district, url=a.manual_url, src_file=Path(a.manual_file),
                                                 found_on=a.manual_url))
            print(f"  + manual capture: {a.manual_file} -> {a.manual_url}")
        n_ok = sum(1 for r in records if r.get("ok"))
        write_manifest(district, records)
        registry = DS.load()
        outcome = finish_district(district, registry)   # records state_event + upserts the DB cache
        DS.save(registry)
        print(f"{district['district_id']} {district['name']}: reconstructed "
              f"{n_ok}/{len(records)} ok -> {outcome}")


if __name__ == "__main__":
    main()
