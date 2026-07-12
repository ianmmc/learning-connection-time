"""#227 Millard decontamination — a one-off, manifest-first remediation (DRY-RUN by default).

Millard Public Schools (NE, district 3173740) entered batch_00013 with a BLANK NCES `WEBSITE`, so Stage 2
ran its UNSCOPED, national-scope branch and pulled same-named schools nationwide into the candidate set —
102 distinct hosts over 147 captures, only 44 on the real `mpsomaha.org` (see #227). #229 now PREVENTS this
class going forward; Millard is the sole pre-guard casualty, so this cleans it up by hand.

What this does (all reversible prep — it does NOT re-spend on discovery):
  1. Reset the contaminated labels to `unlabeled`. A page that IS a valid schedule but for the WRONG
     district has no honest v2.1 label (target_absent/unusable both assert a false non-target GT), so
     unlabeled is the only truthful state — the exact rationale behind the #228 console button. Then
     re-export the tracked `labels.json` so the backup drops them (export keeps only status!='unlabeled').
  2. Purge the district's regenerable signal rows (representation/record/district/district_target, via the
     canonical `delete_district_signal_rows`) + the cross-stage cache rows
     (discovery_school/candidate/capture/processed_doc) — a clean slate the console shows honestly.
  3. Archive (not delete — distill) the on-disk capture dir so a re-discovery can't merge with stale
     off-domain capture binaries.
  4. Set `batch_district.domain = mpsomaha.org` + regenerate the batch receipt, so the operator's NEXT
     Stage-2 run for batch_00013 is SCOPED.
  5. Record a `state_event` documenting the remediation.

PRESERVED on purpose (auditability — the north-star commandment): the append-only `state_event` history and
the gate@5 `calibration_event` rows. The human decisions actually happened; a remediation does not rewrite
history. It also does NOT touch the PRECIOUS batch/batch_district/batch_school rows beyond the one domain
field, nor `cluster_split`/`followup_flag`.

NOT done here: the scoped RE-RUN. It spends money and belongs in the gated console flow (the batch is already
gate@1-approved → operator triggers Stage 2 → re-reviews at gate@5). This script only makes the reversible
prep + sets the domain, so that re-run comes out clean.

Usage:
  python3 -m infrastructure.acquisition.process_governance.remediate_millard_227            # DRY RUN (default)
  python3 -m infrastructure.acquisition.process_governance.remediate_millard_227 --execute  # apply

--execute first writes a restore point (a copy of the current labels.json + district_status.json + the
manifest) under data/acquisition/remediation/millard_227_<ts>/ before mutating anything.
"""
import argparse
import json
import shutil
from datetime import datetime, timezone

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage1_queue import batch_store as BSTORE
from infrastructure.acquisition.stage5_filter import build_signals as BS

BATCH_ID = "batch_00013"
DISTRICT_ID = "3173740"
REC_PREFIX = f"{DISTRICT_ID}:"
DEFAULT_DOMAIN = "mpsomaha.org"

# district_id-keyed regenerable tables to purge (the cross-stage cache — re-populated by a scoped re-run's
# ingest hooks). The derived signal tables (representation/record/district/district_target) go through
# BS.delete_district_signal_rows instead. PRECIOUS tables (batch*/label/cluster_split/followup_flag/
# state_event/calibration_event) are NOT in this list.
CACHE_TABLES = ("discovery_school", "candidate", "capture", "processed_doc")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count(con, sql: str, **p) -> int:
    return int(con.execute(text(sql), p).scalar() or 0)


def _disk_dir():
    """The on-disk capture dir for the district, or None if absent."""
    hits = sorted(paths.RAW_CAPTURES.glob(f"{DISTRICT_ID}_*"))
    return hits[0] if hits else None


def build_manifest(con, domain: str = DEFAULT_DOMAIN) -> dict:
    """Read-only: exactly what --execute would change. Mutates nothing. `domain` is the target scoping
    domain (used to split captures into on-/off-domain in the report)."""
    domain_now = con.execute(
        text("SELECT domain FROM batch_district WHERE batch_id=:b AND district_id=:d"),
        {"b": BATCH_ID, "d": DISTRICT_ID}).scalar()
    label_rows = con.execute(
        text("SELECT rec_key, primary_label, status FROM label "
             "WHERE rec_key LIKE :p AND status != 'unlabeled' ORDER BY rec_key"),
        {"p": f"{REC_PREFIX}%"}).mappings().all()
    cap_total = _count(con, "SELECT COUNT(*) FROM capture WHERE district_id=:d", d=DISTRICT_ID)
    cap_on = _count(con, "SELECT COUNT(*) FROM capture WHERE district_id=:d AND final_host LIKE :h",
                    d=DISTRICT_ID, h=f"%{domain}")
    disk = _disk_dir()
    return {
        "batch_id": BATCH_ID, "district_id": DISTRICT_ID, "generated_at": _now(),
        "domain": {"current": domain_now, "new": None},   # filled by main() with the chosen domain
        "labels_to_reset": [dict(r) for r in label_rows],
        "captures": {"total": cap_total, "on_real_domain": cap_on, "off_domain": cap_total - cap_on},
        "purge_counts": {
            "representation": _count(con, "SELECT COUNT(*) FROM representation WHERE rec_key IN "
                                          "(SELECT rec_key FROM record WHERE district_id=:d)", d=DISTRICT_ID),
            "record": _count(con, "SELECT COUNT(*) FROM record WHERE district_id=:d", d=DISTRICT_ID),
            "district": _count(con, "SELECT COUNT(*) FROM district WHERE district_id=:d", d=DISTRICT_ID),
            "district_target": _count(con, "SELECT COUNT(*) FROM district_target WHERE district_id=:d", d=DISTRICT_ID),
            **{t: _count(con, f"SELECT COUNT(*) FROM {t} WHERE district_id=:d", d=DISTRICT_ID) for t in CACHE_TABLES},
        },
        "preserved": {
            "batch_school": _count(con, "SELECT COUNT(*) FROM batch_school WHERE batch_id=:b AND district_id=:d",
                                   b=BATCH_ID, d=DISTRICT_ID),
            "state_event": _count(con, "SELECT COUNT(*) FROM state_event WHERE district_id=:d", d=DISTRICT_ID),
            "calibration_event": _count(con, "SELECT COUNT(*) FROM calibration_event WHERE district_id=:d", d=DISTRICT_ID),
        },
        "disk_dir": str(disk) if disk else None,
    }


# reset-to-unlabeled: identical semantics to the #228 console button (server.RESET_LABEL) — nulls
# primary/facets/note, status='unlabeled', leaves the legacy flags_json untouched.
_RESET_LABEL = text(
    """UPDATE label SET primary_label=NULL, facets_json=NULL, note=NULL, status='unlabeled', updated_at=:ts
       WHERE rec_key LIKE :p AND status != 'unlabeled'""")


def _write_restore_point(manifest: dict) -> "paths.Path":
    """Copy the tracked precious backups + the manifest into a timestamped restore dir BEFORE mutating."""
    ts = manifest["generated_at"].replace(":", "").replace("-", "")
    rdir = paths.ACQUISITION / "remediation" / f"millard_227_{ts}"
    rdir.mkdir(parents=True, exist_ok=True)
    (rdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    for src in (paths.LABELS_JSON, paths.STATUS_FILE):
        if src.exists():
            shutil.copy2(src, rdir / src.name)
    return rdir


def execute(con, manifest: dict, new_domain: str) -> dict:
    """Apply the remediation on an open transaction (caller commits)."""
    ts = _now()
    done = {}
    # 1. reset contaminated labels + re-export the tracked backup (drops them)
    done["labels_reset"] = con.execute(_RESET_LABEL, {"ts": ts, "p": f"{REC_PREFIX}%"}).rowcount
    BS.export_labels(con)
    # 2. purge regenerable signal + cache rows
    BS.delete_district_signal_rows(con, DISTRICT_ID)   # representation/record/district/district_target
    done["cache_purged"] = {t: con.execute(text(f"DELETE FROM {t} WHERE district_id=:d"),
                                           {"d": DISTRICT_ID}).rowcount for t in CACHE_TABLES}
    # 3. set the real domain + regenerate the receipt so the next Stage-2 run is scoped
    con.execute(text("UPDATE batch_district SET domain=:dom WHERE batch_id=:b AND district_id=:d"),
                {"dom": new_domain, "b": BATCH_ID, "d": DISTRICT_ID})
    BSTORE.write_receipt(con, BATCH_ID)
    done["domain_set"] = new_domain
    # 4. audit event (preserving the prior history, not rewriting it)
    from infrastructure.acquisition.common.district_status import INSERT_STATE_EVENT
    con.execute(INSERT_STATE_EVENT, {
        "district_id": DISTRICT_ID, "name": "MILLARD PUBLIC SCHOOLS", "state": "NE",
        "stage": 5, "stage_name": "filter", "checkpoint": None,
        "event_type": "remediated", "outcome": "decontaminated",
        "topology": None, "batch_id": BATCH_ID, "fingerprints_json": None, "actor": "remediate_millard_227",
        "note": f"#227 unscoped-discovery contamination purged; domain set to {new_domain}; "
                f"{done['labels_reset']} labels reset to unlabeled; awaiting scoped re-run at the console.",
        "created_at": ts})
    return done


def main():
    ap = argparse.ArgumentParser(description="#227 Millard decontamination (dry-run by default)")
    ap.add_argument("--execute", action="store_true", help="apply the remediation (default: dry-run)")
    ap.add_argument("--domain", default=DEFAULT_DOMAIN, help=f"scoping domain to set (default {DEFAULT_DOMAIN})")
    ap.add_argument("--force", action="store_true",
                    help="override the already-remediated guard (domain already non-blank) — dangerous")
    a = ap.parse_args()

    gdb.init_precious_schema()
    with gdb.session_scope() as con:
        manifest = build_manifest(con, a.domain)
    manifest["domain"]["new"] = a.domain

    print(json.dumps(manifest, indent=2))

    if not a.execute:
        print("\nDRY RUN — nothing changed. Re-run with --execute to apply (a restore point is written first).")
        print("After --execute: re-run Stage 2 discovery for batch_00013 at the console (now SCOPED), "
              "then re-review Millard at gate@5.")
        return

    # Enforcing single-shot guard (not just a warning): once the domain is set, a scoped re-run
    # repopulates records/captures and applies fresh gate@5 labels — a SECOND --execute would purge that
    # good re-acquired data and null those labels. Refuse when the domain is already non-blank.
    already = manifest["domain"]["current"] not in ("", None)
    if already and not a.force:
        print(f"\n⛔ REFUSING --execute: batch_district.domain is already {manifest['domain']['current']!r} "
              f"(not blank) — this district looks ALREADY remediated. A second run would purge re-acquired "
              f"records/captures and null freshly-applied labels. Re-run with --force only if you are certain.")
        return

    rdir = _write_restore_point(manifest)
    print(f"\nRestore point written: {rdir}")
    with gdb.session_scope() as con:
        done = execute(con, manifest, a.domain)
    # archive the disk dir AFTER the DB commit (irreversible-ish move; do it last)
    disk = _disk_dir()
    if disk:
        dest = rdir / "archived_capture_dir" / disk.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(disk), str(dest))
        done["disk_archived_to"] = str(dest)
    print("\nAPPLIED:\n" + json.dumps(done, indent=2))
    print("\nNext (gated, spends money): re-run Stage 2 discovery for batch_00013 at the console — it is "
          "now scoped to mpsomaha.org — then Stage 3/4/5 and re-review Millard at gate@5.")


if __name__ == "__main__":
    main()
