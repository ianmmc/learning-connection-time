#!/usr/bin/env python3
"""#517 schedule_link_only ROUTING receipt — the one-hop-away retry list.

The detection half (build_signals.schedule_link_only + the attention chip) marks pages that NAME a
bell schedule they don't contain (measured 2026-07-18: 78/78 such census-labeled records are
target_absent — pure link-hubs, zero collateral). This module is the routing half: emit the
per-district list of flagged pages as a regenerable receipt + stdout table, so the operator can feed
the flagged PAGES back through Stage-3 capture (the existing one-hop emergent scan captures the
linked schedule on the revisit — the stored captures keep no raw HTML, so the href itself is only
recoverable by revisiting). The browser-side revisit executor is epic #111's territory (with #518);
this receipt is the hand-off. Read-only against the governance DB; never dispatches anything."""
import argparse
import json

from sqlalchemy import text

from infrastructure.acquisition.common import db as gdb  # noqa: E402
from infrastructure.acquisition.common import paths  # noqa: E402

RECEIPT = paths.STAGE5_DIR / "schedule_link_retry.json"


def flagged(session) -> list:
    """[{district_id, rec_key, url, tier, label}] for every schedule_link_only record, district-grouped.
    Labeled target_absent records are INCLUDED deliberately: the label says 'no target HERE', and the
    flag says 'the target is one hop away' — both true, and the retry is about the hop."""
    rows = session.execute(text(
        """SELECT r.district_id, r.rec_key, r.url, r.tier, l.primary_label
           FROM record r LEFT JOIN label l ON l.rec_key = r.rec_key
           WHERE r.signals_json LIKE '%"schedule_link_only": true%'
           ORDER BY r.district_id, r.rec_key""")).fetchall()
    return [{"district_id": d, "rec_key": rk, "url": u, "tier": t, "label": lab}
            for d, rk, u, t, lab in rows]


def write_receipt(items: list) -> dict:
    by_district = {}
    for it in items:
        by_district.setdefault(it["district_id"], []).append(
            {k: it[k] for k in ("rec_key", "url", "tier", "label")})
    doc = {"purpose": "schedule_link_only capture-retry candidates (#517) — revisit each page with the "
                      "Stage-3 emergent scan; the linked schedule is one hop away",
           "n_districts": len(by_district), "n_records": len(items), "districts": by_district}
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(doc, indent=1))
    return doc


def main():
    argparse.ArgumentParser(description="#517 schedule_link_only retry receipt").parse_args()
    with gdb.session_scope() as s:
        items = flagged(s)
    doc = write_receipt(items)
    print(f"{doc['n_records']} flagged records across {doc['n_districts']} districts -> {RECEIPT}")
    for did, recs in sorted(doc["districts"].items()):
        print(f"  {did}: {len(recs)}")
        for r in recs[:3]:
            print(f"     {r['rec_key']}  {r['url'][:70]}")


if __name__ == "__main__":
    main()
