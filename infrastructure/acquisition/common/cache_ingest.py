"""Cross-stage DB cache — the live, queryable projection of each district's on-disk DATA artifacts.

The governance DB is the **working store** the console reads (governance §7a-A); the district-dir JSON
(`discovery.json`/`candidates.json`/`captures.json`/`processed.json`) is the authoritative, regenerable
**source** those rows are projected from. This module is the single source of truth for that projection's
schema + the per-district UPSERTs, living in `common/` so every stage can keep its own slice fresh —
the layering contract makes stages independent siblings, so the ingest cannot live in `stage5_filter`
(REQ-103c originally put it there; it moved here when stages 2/3/4 started maintaining the cache live).

**Lifecycle: a live working store, not a drop-each-ingest cache.** The four tables are created
`IF NOT EXISTS` and refreshed per district (DELETE that district's rows, then UPSERT — issue #33, so a
row that vanished from the source JSON can't linger as a ghost) — whole tables are never dropped
mid-flight, so the console reads fresh rows for a batch that is only partway down the pipeline
(Stage 2 done, Stage 3 pending). They remain fully
regenerable from disk (`stage5_filter.build_signals.ingest()` re-upserts every district on a full pass);
they are simply never destroyed under in-flight data. Contrast the *derived* signal tables
(`record`/`representation`/…), which stay drop+rebuild because they are an all-or-nothing recomputation.

Each stage's `finish` calls the best-effort `cache_*` helper after its disk write: a cache hiccup logs a
warning and is swallowed (the precious record is the disk JSON + the state_event log), exactly like the
`filtered.json` refresh — it must never fail the stage.
"""
import json
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb

# The four cross-stage cache tables — created IF NOT EXISTS (idempotent; never dropped under in-flight
# data). Columns are identical to the originals in build_signals' REBUILD_DDL (REQ-103c).
CACHE_DDL = [
    # Stage 2 discovery funnel — one row per (district, school).
    """CREATE TABLE IF NOT EXISTS discovery_school (
        district_id text, school_id text, school text, bands_json text, query text,
        wave1_n_raw integer, wave1_n_kept integer, wave2_invoked integer,
        wave2_n_raw integer, wave2_n_kept integer, outcome text,
        wave1_raw_urls_json text, wave1_gated_json text, wave2_raw_urls_json text, wave2_gated_json text,
        PRIMARY KEY (district_id, school_id))""",
    # Stage 2 capture plan — one row per (district, candidate URL).
    """CREATE TABLE IF NOT EXISTS candidate (
        district_id text, url text, schools_json text, tools_json text, n_schools integer,
        PRIMARY KEY (district_id, url))""",
    # Stage 3 capture receipt — one row per (district, capture hash). `err` carries the per-candidate
    # failure reason (e.g. needs_oauth_reauth / a WAF block) so the console's failure breakdown is
    # queryable from the DB, not only from captures.json.
    """CREATE TABLE IF NOT EXISTS capture (
        district_id text, hash text, url text, final_url text, ok integer, kind text, source text,
        found_on text, tools_json text, files_json text, modals_dismissed integer, segmented integer,
        text_times integer, final_host text, fingerprint_json text, err text,
        PRIMARY KEY (district_id, hash))""",
    # Stage 4 processed doc — one row per (district, processed hash); texts live in `representation`.
    """CREATE TABLE IF NOT EXISTS processed_doc (
        district_id text, hash text, url text, usable integer, n_texts integer,
        PRIMARY KEY (district_id, hash))""",
]

# UPSERTs — re-running a stage refreshes that district's rows in place (the live working-store contract).
UPSERT_DISCOVERY_SCHOOL = text(
    """INSERT INTO discovery_school (district_id, school_id, school, bands_json, query,
         wave1_n_raw, wave1_n_kept, wave2_invoked, wave2_n_raw, wave2_n_kept, outcome,
         wave1_raw_urls_json, wave1_gated_json, wave2_raw_urls_json, wave2_gated_json)
       VALUES (:district_id, :school_id, :school, :bands_json, :query,
         :wave1_n_raw, :wave1_n_kept, :wave2_invoked, :wave2_n_raw, :wave2_n_kept, :outcome,
         :wave1_raw_urls_json, :wave1_gated_json, :wave2_raw_urls_json, :wave2_gated_json)
       ON CONFLICT (district_id, school_id) DO UPDATE SET
         school=excluded.school, bands_json=excluded.bands_json, query=excluded.query,
         wave1_n_raw=excluded.wave1_n_raw, wave1_n_kept=excluded.wave1_n_kept,
         wave2_invoked=excluded.wave2_invoked, wave2_n_raw=excluded.wave2_n_raw,
         wave2_n_kept=excluded.wave2_n_kept, outcome=excluded.outcome,
         wave1_raw_urls_json=excluded.wave1_raw_urls_json, wave1_gated_json=excluded.wave1_gated_json,
         wave2_raw_urls_json=excluded.wave2_raw_urls_json, wave2_gated_json=excluded.wave2_gated_json""")
UPSERT_CANDIDATE = text(
    """INSERT INTO candidate (district_id, url, schools_json, tools_json, n_schools)
       VALUES (:district_id, :url, :schools_json, :tools_json, :n_schools)
       ON CONFLICT (district_id, url) DO UPDATE SET
         schools_json=excluded.schools_json, tools_json=excluded.tools_json,
         n_schools=excluded.n_schools""")
UPSERT_CAPTURE = text(
    """INSERT INTO capture (district_id, hash, url, final_url, ok, kind, source, found_on,
         tools_json, files_json, modals_dismissed, segmented, text_times, final_host, fingerprint_json, err)
       VALUES (:district_id, :hash, :url, :final_url, :ok, :kind, :source, :found_on,
         :tools_json, :files_json, :modals_dismissed, :segmented, :text_times, :final_host, :fingerprint_json, :err)
       ON CONFLICT (district_id, hash) DO UPDATE SET
         url=excluded.url, final_url=excluded.final_url, ok=excluded.ok, kind=excluded.kind,
         source=excluded.source, found_on=excluded.found_on, tools_json=excluded.tools_json,
         files_json=excluded.files_json, modals_dismissed=excluded.modals_dismissed,
         segmented=excluded.segmented, text_times=excluded.text_times,
         final_host=excluded.final_host, fingerprint_json=excluded.fingerprint_json, err=excluded.err""")
UPSERT_PROCESSED_DOC = text(
    """INSERT INTO processed_doc (district_id, hash, url, usable, n_texts)
       VALUES (:district_id, :hash, :url, :usable, :n_texts)
       ON CONFLICT (district_id, hash) DO UPDATE SET
         url=excluded.url, usable=excluded.usable, n_texts=excluded.n_texts""")


# Columns added after a table's first creation. Because the cache is now never dropped, a table that
# predates a column (e.g. `capture.err`, added when the Stage-3 console needed a queryable failure
# reason) won't pick it up from CREATE TABLE IF NOT EXISTS — so apply idempotent ALTERs too.
CACHE_ALTERS = [
    "ALTER TABLE capture ADD COLUMN IF NOT EXISTS err text",
]


def ensure_cache_schema(con) -> None:
    """Create the four cross-stage cache tables if absent + apply additive column migrations
    (idempotent). Caller owns the session."""
    for ddl in CACHE_DDL:
        con.execute(text(ddl))
    for alter in CACHE_ALTERS:
        con.execute(text(alter))


def load_candidates(ddir: Path) -> dict:
    """url -> {'schools': [...], 'tools': [...]} from a district's candidates.json (the Stage 2
    D_FLATTEN capture plan, carrying the URL->school map). {} if absent/unreadable. Records whose
    URL is NOT a key here were captured but never planned -> emergent (discovered mid-capture)."""
    cf = ddir / "candidates.json"
    if not cf.exists():
        return {}
    try:
        doc = json.loads(cf.read_text())
    except Exception as e:
        # #326: a MALFORMED file (partial write) is not "no candidates" -- without this line the
        # ingest would silently rebuild the district's candidate rows as empty and every captured
        # URL would misclassify as emergent. Same [warn] convention as _best_effort.
        print(f"[warn] cache_ingest: unreadable candidates.json in {ddir} "
              f"({type(e).__name__}: {e}) -- ingesting as empty; fix the file and re-ingest")
        return {}
    return {c["url"]: {"schools": c.get("schools", []), "tools": c.get("tools", [])}
            for c in doc.get("candidates", []) if c.get("url")}


# ---------------------------------------------------------------- dict-based upserts (build_signals reuse)
# Each per-district ingest DELETEs that district's rows from the table(s) it owns before re-UPSERTing
# (issue #33): the source JSON is a whole-district snapshot, so a school/URL/hash that vanished from
# disk must also vanish from the cache — UPSERT alone leaves ghost rows behind. Scoped per district +
# per stage-table pair, inside the caller's transaction, so an in-flight OTHER district is untouched.
# None of the four tables accumulates across batches by design: a district belongs to one batch, and
# discovery.json/candidates.json/captures.json/processed.json are each rewritten wholesale per run.
def upsert_discovery_rows(con, disc: dict, cand_map: dict) -> None:
    """Replace one district's Stage-2 funnel: discovery_school (per school, rolled-up wave counts +
    raw JSON for audit) + candidate (per planned URL, the URL->school map). DELETE-then-UPSERT so
    rows for schools/URLs no longer on disk don't linger (#33)."""
    did = disc["district_id"]
    con.execute(text("DELETE FROM discovery_school WHERE district_id=:d"), {"d": did})
    con.execute(text("DELETE FROM candidate WHERE district_id=:d"), {"d": did})
    for sc in disc.get("schools", []):
        w1g, w2g = sc.get("wave1_gated", []), sc.get("wave2_gated", [])
        con.execute(UPSERT_DISCOVERY_SCHOOL, {
            "district_id": did, "school_id": sc.get("school_id"), "school": sc.get("school"),
            "bands_json": json.dumps(sc.get("bands", [])), "query": sc.get("query"),
            "wave1_n_raw": len(sc.get("wave1_raw_urls", [])),
            "wave1_n_kept": sum(1 for g in w1g if g.get("kept")),
            "wave2_invoked": int(bool(sc.get("wave2_invoked"))),
            "wave2_n_raw": len(sc.get("wave2_raw_urls", [])),
            "wave2_n_kept": sum(1 for g in w2g if g.get("kept")),
            "outcome": sc.get("outcome"),
            "wave1_raw_urls_json": json.dumps(sc.get("wave1_raw_urls", [])),
            "wave1_gated_json": json.dumps(w1g),
            "wave2_raw_urls_json": json.dumps(sc.get("wave2_raw_urls", [])),
            "wave2_gated_json": json.dumps(w2g)})
    for url, c in cand_map.items():
        con.execute(UPSERT_CANDIDATE, {
            "district_id": did, "url": url, "schools_json": json.dumps(c.get("schools", [])),
            "tools_json": json.dumps(c.get("tools", [])), "n_schools": len(c.get("schools", []))})


def upsert_capture_rows(con, district_id: str, caps: dict) -> None:
    """Replace one district's Stage-3 capture receipts (one row per hash, incl. captures that never
    processed). `caps`: hash -> capture record dict (from captures.json). DELETE-then-UPSERT (#33)."""
    con.execute(text("DELETE FROM capture WHERE district_id=:d"), {"d": district_id})
    for h, cap in caps.items():
        fp = cap.get("fingerprint") or {}
        con.execute(UPSERT_CAPTURE, {
            "district_id": district_id, "hash": h, "url": cap.get("url"),
            "final_url": cap.get("final_url"), "ok": int(bool(cap.get("ok"))), "kind": cap.get("kind"),
            "source": cap.get("source"), "found_on": cap.get("found_on"),
            "tools_json": json.dumps(cap.get("tools", [])),
            "files_json": json.dumps(cap.get("files") or {}),
            "modals_dismissed": int(bool(cap.get("modals_dismissed"))),
            "segmented": int(bool(cap.get("segmented"))), "text_times": cap.get("text_times"),
            "final_host": fp.get("final_host"), "fingerprint_json": json.dumps(fp),
            "err": cap.get("err")})


def upsert_processed_rows(con, district_id: str, processed: dict) -> None:
    """Replace one district's Stage-4 processed-doc rows (texts themselves live in `representation`).
    DELETE-then-UPSERT (#33)."""
    con.execute(text("DELETE FROM processed_doc WHERE district_id=:d"), {"d": district_id})
    for h, prec in processed.items():
        con.execute(UPSERT_PROCESSED_DOC, {
            "district_id": district_id, "hash": h, "url": prec.get("url"),
            "usable": int(bool(prec.get("usable"))), "n_texts": len(prec.get("texts", []))})


# ---------------------------------------------------------------- dir-based ingest (one district)
def ingest_discovery(con, ddir: Path) -> None:
    disc = json.loads((ddir / "discovery.json").read_text())
    upsert_discovery_rows(con, disc, load_candidates(ddir))


def ingest_capture(con, ddir: Path, district_id: str) -> None:
    caps = {r["hash"]: r for r in json.loads((ddir / "captures.json").read_text())}
    upsert_capture_rows(con, district_id, caps)


def ingest_processed(con, ddir: Path, district_id: str) -> None:
    processed = {r["hash"]: r for r in json.loads((ddir / "processed.json").read_text())}
    upsert_processed_rows(con, district_id, processed)


# ---------------------------------------------------------------- best-effort stage hooks (own session)
def _best_effort(label: str, fn) -> None:
    """Open a session, ensure schema, run `fn(con)`, commit. A cache failure is logged + swallowed:
    the precious record is the on-disk JSON + the state_event log, and a full re-ingest rebuilds the
    cache, so a hiccup here must never fail the stage (same stance as the filtered.json refresh)."""
    try:
        with gdb.session_scope() as con:
            ensure_cache_schema(con)
            fn(con)
    except Exception as e:
        print(f"[warn] cross-stage cache {label} ingest failed ({type(e).__name__}: {e}); "
              f"the DB cache will refresh on the next full ingest")


def cache_discovery(ddir: Path) -> None:
    """Stage 2 finish hook: project discovery.json + candidates.json into the DB cache."""
    _best_effort("discovery", lambda con: ingest_discovery(con, ddir))


def cache_capture(ddir: Path, district_id: str) -> None:
    """Stage 3 finish hook: project captures.json into the DB cache."""
    _best_effort("capture", lambda con: ingest_capture(con, ddir, district_id))


def cache_processed(ddir: Path, district_id: str) -> None:
    """Stage 4 finish hook: project processed.json into the DB cache."""
    _best_effort("processed", lambda con: ingest_processed(con, ddir, district_id))
