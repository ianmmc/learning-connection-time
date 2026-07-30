"""#683 corpus measurement — `instructional_time` old-vs-new, rerunnable (the #691/#694 pattern).

Scans every text-bearing capture record and reports, per record, whether the PRE-#683 regex
(embedded below as a frozen literal — it no longer exists in code) and the CURRENT
`instructional_declaration()` predicate fire. The strictly-narrowing claim ("0 records gained")
in the companion report is exactly `GAINED == []` here; rerun after any edit to the regex or
guard to re-check it.

`--guard-audit` additionally splits the CURRENT predicate into its two halves (regex alone vs
regex + antecedent guard) and prints the records where the guard CHANGED the outcome — the #704
review's question. As of 2026-07-29 the answer is 0: every measured FP already fails the
number+instruction+day-scope regex itself, which is why threshold hedges were removed from the
guard (they rejected genuine "at least N minutes of instruction per day" statutory declarations
while doing no corpus work).

Run:  python3 docs/technical-notes/production-quality-control-research/2026-07-29-issue683-instructional-declaration-measure.py [--guard-audit]
"""
import re
import sys

from infrastructure.acquisition.common import paths
from infrastructure.acquisition.stage5_filter.build_signals import (
    INSTRUCTIONAL_RE, instructional_declaration)

# The pre-#683 form, frozen verbatim (main @ 01d7614) — the measurement baseline.
OLD_RE = re.compile(
    r"(\d{2,4})\s*(?:minutes|mins)\s+(?:of|per)\s+(?:instruction|instructional|class|learning)"
    r"|(?:instructional\s+minutes|minutes\s+per\s+day|minutes\s+of\s+instruction)", re.I)


def record_texts():
    for ddir in sorted(p for p in paths.RAW_CAPTURES.glob("*") if p.is_dir()):
        cdir = ddir / "captures"
        if not cdir.is_dir():
            continue
        for rdir in sorted(cdir.glob("*")):
            if not rdir.is_dir():
                continue
            txt = ""
            for f in sorted(rdir.glob("*.txt")):
                try:
                    txt += f.read_text(errors="replace")
                except Exception:  # noqa: BLE001 — a single unreadable rep never kills the scan
                    pass
            if txt:
                yield f"{ddir.name.split('_')[0]}:{rdir.name[:10]}", txt


def main():
    guard_audit = "--guard-audit" in sys.argv
    old_set, new_set, regex_only = set(), set(), set()
    n = 0
    for key, txt in record_texts():
        n += 1
        if OLD_RE.search(txt):
            old_set.add(key)
        if INSTRUCTIONAL_RE.search(txt):
            regex_only.add(key)
        if instructional_declaration(txt):
            new_set.add(key)
    print(f"records scanned: {n}")
    print(f"OLD (pre-#683) fires on {len(old_set)}: {sorted(old_set)}")
    print(f"NEW predicate fires on {len(new_set)}: {sorted(new_set)}")
    print(f"GAINED (must be [] — strictly narrowing): {sorted(new_set - old_set)}")
    print(f"REMOVED ({len(old_set - new_set)}): {sorted(old_set - new_set)}")
    if guard_audit:
        print(f"\n--guard-audit: regex alone fires on {len(regex_only)}: {sorted(regex_only)}")
        print(f"records where the antecedent guard changed the outcome: "
              f"{sorted(regex_only - new_set)}")


if __name__ == "__main__":
    main()
