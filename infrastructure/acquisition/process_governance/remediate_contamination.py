"""Unscoped-discovery decontamination — manifest-first remediation tooling (DRY-RUN by default).

Born as the #227 Millard cleanup (the CLI defaults still point there), generalized per the PR #242
review: the NEXT contaminated district runs `--batch-id X --district-id Y --domain Z` instead of a
copy-pasted script. The failure class: a district entered a batch with a blank/junk domain, Stage 2
ran its UNSCOPED national-scope branch, and same-named schools nationwide polluted the candidate set
(Millard: 102 distinct hosts over 147 captures, only 44 on the real `mpsomaha.org`). #229 now blocks
the class at Stage-1 admission AND Stage 2 fails closed (`gate_urls`); this tool cleans up a district
that got through before those guards existed.

What --execute does (it does NOT re-spend on discovery):
  1. Resets the contaminated labels to `unlabeled` — via the ONE shared definition of a reset,
     `build_signals.reset_labels_bulk` (same SQL the #228 console button uses), applied to the EXACT
     rec_keys enumerated in the manifest the operator reviewed (never a re-derived predicate, so what
     was signed off is what happens even if labeling continued in between).
  2. Purges the district's regenerable signal rows (via the canonical `delete_district_signal_rows`)
     + the cross-stage cache rows (discovery_school/candidate/capture/processed_doc).
  3. Sets `batch_district.domain` to the (validated) scoping domain.
  4. Records a `state_event` documenting the remediation.
  Then, ONLY AFTER that transaction commits, it re-exports `labels.json` and regenerates the batch
  receipt from the committed rows — the commit-before-export discipline `server.py`'s label writes
  follow (PR #242 review: exporting mid-transaction left disk ahead of a rolled-back DB).

PRESERVED on purpose (auditability — the north-star commandment): the append-only `state_event`
history and the gate@5 `calibration_event` rows. The human decisions actually happened; a remediation
does not rewrite history. The PRECIOUS batch/batch_district/batch_school rows survive untouched except
the one domain field; `cluster_split`/`followup_flag` are never touched.

The on-disk capture dir (under data/raw/ — CLAUDE.md Critical Rule 5: never modify data/raw/) is NOT
touched by default. Pass `--archive-capture-dir` to move it into the restore dir — an explicit,
per-run human decision to make the rule exception, recommended here because a re-ingest could
otherwise merge stale off-domain capture receipts back in.

NOT done here: the scoped RE-RUN. It spends money and belongs in the gated console flow (gate@1
approval → Stage 2 → re-review at gate@5).

Usage:
  python3 -m infrastructure.acquisition.process_governance.remediate_contamination            # DRY RUN
  python3 -m infrastructure.acquisition.process_governance.remediate_contamination --execute [--archive-capture-dir]

--execute first writes a VERIFIED restore point (current labels.json + district_status.json + the
manifest) under data/acquisition/remediation/<district>_<ts>/ before mutating anything, and refuses
to run twice (domain already non-blank) without --force.
"""
import argparse
import json
import shutil
from datetime import datetime, timezone

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.common.discover import domain_of, is_scoping_domain
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage5_filter import build_signals as BS

# The #227 case these defaults point at; any other contamination passes explicit CLI args.
DEFAULT_BATCH_ID = "batch_00013"
DEFAULT_DISTRICT_ID = "3173740"
DEFAULT_DOMAIN = "mpsomaha.org"

# district_id-keyed regenerable tables to purge (the cross-stage cache — re-populated by a scoped
# re-run's ingest hooks). The derived signal tables (representation/record/district/district_target)
# go through BS.delete_district_signal_rows instead. PRECIOUS tables (batch*/label/cluster_split/
# followup_flag/state_event/calibration_event) are NOT in this list.
CACHE_TABLES = ("discovery_school", "candidate", "capture", "processed_doc")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count(con, sql: str, **p) -> int:
    return int(con.execute(text(sql), p).scalar() or 0)


def _disk_dir(district_id: str):
    """The on-disk capture dir for the district, or None if absent."""
    hits = sorted(paths.RAW_CAPTURES.glob(f"{district_id}_*"))
    return hits[0] if hits else None


def build_manifest(con, batch_id: str, district_id: str, domain: str) -> dict:
    """Read-only: exactly what --execute would change. Mutates nothing. The manifest is the ONLY
    input execute() takes — the rec_keys enumerated here are exactly the rows a later --execute
    resets, so the reviewed artifact and the applied change can never diverge (PR #242 review)."""
    bd = con.execute(
        text("SELECT name, state, domain FROM batch_district WHERE batch_id=:b AND district_id=:d"),
        {"b": batch_id, "d": district_id}).mappings().first()
    label_rows = con.execute(
        text("SELECT rec_key, primary_label, status FROM label "
             "WHERE rec_key LIKE :p AND status != 'unlabeled' ORDER BY rec_key"),
        {"p": f"{district_id}:%"}).mappings().all()
    cap_total = _count(con, "SELECT COUNT(*) FROM capture WHERE district_id=:d", d=district_id)
    # dot-boundary host match (the _host_matches rule, issue #34): a bare LIKE '%domain' would
    # count evilmpsomaha.org as on-domain and understate the contamination (PR #242 review).
    cap_on = _count(con, "SELECT COUNT(*) FROM capture WHERE district_id=:d "
                         "AND (final_host = :dom OR final_host LIKE :sub)",
                    d=district_id, dom=domain, sub=f"%.{domain}")
    disk = _disk_dir(district_id)
    return {
        "batch_id": batch_id, "district_id": district_id, "generated_at": _now(),
        "district_name": bd["name"] if bd else None, "district_state": bd["state"] if bd else None,
        "domain": {"current": bd["domain"] if bd else None, "new": domain},
        "labels_to_reset": [dict(r) for r in label_rows],
        "captures": {"total": cap_total, "on_real_domain": cap_on, "off_domain": cap_total - cap_on},
        "purge_counts": {
            "representation": _count(con, "SELECT COUNT(*) FROM representation WHERE rec_key IN "
                                          "(SELECT rec_key FROM record WHERE district_id=:d)", d=district_id),
            "record": _count(con, "SELECT COUNT(*) FROM record WHERE district_id=:d", d=district_id),
            "district": _count(con, "SELECT COUNT(*) FROM district WHERE district_id=:d", d=district_id),
            "district_target": _count(con, "SELECT COUNT(*) FROM district_target WHERE district_id=:d", d=district_id),
            **{t: _count(con, f"SELECT COUNT(*) FROM {t} WHERE district_id=:d", d=district_id) for t in CACHE_TABLES},
        },
        "preserved": {
            "batch_school": _count(con, "SELECT COUNT(*) FROM batch_school WHERE batch_id=:b AND district_id=:d",
                                   b=batch_id, d=district_id),
            "state_event": _count(con, "SELECT COUNT(*) FROM state_event WHERE district_id=:d", d=district_id),
            "calibration_event": _count(con, "SELECT COUNT(*) FROM calibration_event WHERE district_id=:d", d=district_id),
        },
        "disk_dir": str(disk) if disk else None,
    }


def _write_restore_point(manifest: dict) -> "paths.Path":
    """Copy the tracked precious backups + the manifest into a timestamped restore dir BEFORE
    mutating — and VERIFY each copy landed (PR #242 review: a silently-incomplete restore point is
    discovered exactly when it's needed). Raises on any failed copy; a source file that legitimately
    doesn't exist yet is recorded in the manifest copy, not silently skipped."""
    ts = manifest["generated_at"].replace(":", "").replace("-", "")
    rdir = paths.ACQUISITION / "remediation" / f"{manifest['district_id']}_{ts}"
    rdir.mkdir(parents=True, exist_ok=True)
    backed_up, absent = [], []
    for src in (paths.LABELS_JSON, paths.STATUS_FILE):
        if not src.exists():
            absent.append(str(src))
            continue
        dest = rdir / src.name
        shutil.copy2(src, dest)
        if not dest.exists() or dest.stat().st_size != src.stat().st_size:
            raise RuntimeError(f"restore-point copy failed verification: {src} -> {dest} — "
                               f"REFUSING to proceed to --execute with an incomplete restore point")
        backed_up.append(str(dest))
    manifest["restore_point"] = {"dir": str(rdir), "backed_up": backed_up, "absent_sources": absent}
    (rdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return rdir


def execute(con, manifest: dict) -> dict:
    """Apply the DB remediation on an open transaction (caller commits; caller then re-exports the
    JSON receipts AFTER the commit — no disk write happens in here, so a failed statement rolls
    back cleanly with disk untouched; PR #242 review). Driven entirely by the manifest: the exact
    reviewed rec_keys, batch/district ids, and target domain."""
    batch_id, district_id = manifest["batch_id"], manifest["district_id"]
    new_domain = manifest["domain"]["new"]
    ts = _now()
    done = {}
    # 1. reset the REVIEWED contaminated labels — the shared #228 definition of a reset
    keys = [r["rec_key"] for r in manifest["labels_to_reset"]]
    done["labels_reset"] = BS.reset_labels_bulk(con, keys, ts)
    # 2. purge regenerable signal + cache rows
    BS.delete_district_signal_rows(con, district_id)   # representation/record/district/district_target
    done["cache_purged"] = {t: con.execute(text(f"DELETE FROM {t} WHERE district_id=:d"),
                                           {"d": district_id}).rowcount for t in CACHE_TABLES}
    # 3. set the real domain so the next Stage-2 run is scoped
    con.execute(text("UPDATE batch_district SET domain=:dom WHERE batch_id=:b AND district_id=:d"),
                {"dom": new_domain, "b": batch_id, "d": district_id})
    done["domain_set"] = new_domain
    # 4. audit event (preserving the prior history, not rewriting it)
    from infrastructure.acquisition.common.district_status import INSERT_STATE_EVENT
    con.execute(INSERT_STATE_EVENT, {
        "district_id": district_id, "name": manifest.get("district_name") or district_id,
        "state": manifest.get("district_state") or "", "stage": 5, "stage_name": "filter",
        "checkpoint": None, "event_type": "remediated", "outcome": "decontaminated",
        "topology": None, "batch_id": batch_id, "fingerprints_json": None,
        "actor": "remediate_contamination",
        "note": f"unscoped-discovery contamination purged (#227 class); domain set to {new_domain}; "
                f"{done['labels_reset']} labels reset to unlabeled; awaiting scoped re-run at the console.",
        "created_at": ts})
    return done


def main():
    ap = argparse.ArgumentParser(description="Unscoped-discovery decontamination (dry-run by default)")
    ap.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    ap.add_argument("--district-id", default=DEFAULT_DISTRICT_ID)
    ap.add_argument("--domain", default=DEFAULT_DOMAIN, help=f"scoping domain to set (default {DEFAULT_DOMAIN})")
    ap.add_argument("--execute", action="store_true", help="apply the remediation (default: dry-run)")
    ap.add_argument("--archive-capture-dir", action="store_true",
                    help="ALSO move the district's on-disk capture dir (under data/raw/) into the "
                         "restore dir — an explicit exception to CLAUDE.md Critical Rule 5, "
                         "recommended so a re-ingest can't merge stale off-domain receipts back in")
    ap.add_argument("--force", action="store_true",
                    help="override the already-remediated guard (domain already non-blank) — dangerous")
    a = ap.parse_args()

    # #229 applies to this side door too: the domain about to be written into batch_district must
    # itself be a usable scoping domain, or we'd recreate the exact broken state being remediated.
    domain = domain_of(a.domain)
    if not is_scoping_domain(domain):
        raise SystemExit(f"--domain {a.domain!r} is not a usable scoping domain "
                         f"(normalized: {domain!r}) — refusing (#229).")

    gdb.init_precious_schema()
    with gdb.session_scope() as con:
        manifest = build_manifest(con, a.batch_id, a.district_id, domain)

    print(json.dumps(manifest, indent=2))

    if not a.execute:
        print("\nDRY RUN — nothing changed. Re-run with --execute to apply (a verified restore point "
              "is written first).")
        print(f"After --execute: re-run Stage 2 discovery for {a.batch_id} at the console (now SCOPED), "
              f"then re-review the district at gate@5.")
        return

    # Enforcing single-shot guard (not just a warning): once the domain is set, a scoped re-run
    # repopulates records/captures and applies fresh gate@5 labels — a SECOND --execute would purge
    # that good re-acquired data and null those labels. Refuse when the domain is already non-blank.
    already = manifest["domain"]["current"] not in ("", None)
    if already and not a.force:
        print(f"\n⛔ REFUSING --execute: batch_district.domain is already {manifest['domain']['current']!r} "
              f"(not blank) — this district looks ALREADY remediated. A second run would purge re-acquired "
              f"records/captures and null freshly-applied labels. Re-run with --force only if you are certain.")
        return

    rdir = _write_restore_point(manifest)
    print(f"\nRestore point written + verified: {rdir}")
    with gdb.session_scope() as con:
        done = execute(con, manifest)
    # Disk writes ONLY after the transaction above committed (commit-before-export, same as the
    # console's label writes): re-export labels.json from the committed rows + regenerate the batch
    # receipt so Stage 2 reads the corrected domain.
    with gdb.session_scope() as con:
        BS.export_labels(con)
        BSTORE.write_receipt(con, a.batch_id)
    # The capture dir under data/raw/ moves ONLY on explicit operator opt-in (CLAUDE.md Critical
    # Rule 5: never modify data/raw/ — this flag is the human decision to make the one exception).
    disk = _disk_dir(a.district_id)
    if disk and a.archive_capture_dir:
        dest = rdir / "archived_capture_dir" / disk.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(disk), str(dest))
        done["disk_archived_to"] = str(dest)
    elif disk:
        done["disk_dir_left_in_place"] = str(disk)
        print(f"\n⚠  {disk} left in place (data/raw/ untouched — Critical Rule 5). Before the scoped "
              f"re-run, consider `--archive-capture-dir` (an explicit, logged exception) so a "
              f"re-ingest can't merge stale off-domain receipts back in.")
    print("\nAPPLIED:\n" + json.dumps(done, indent=2))
    print(f"\nNext (gated, spends money): re-run Stage 2 discovery for {a.batch_id} at the console — "
          f"now scoped to {domain} — then Stage 3/4/5 and re-review the district at gate@5.")


if __name__ == "__main__":
    main()
