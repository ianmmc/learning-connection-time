"""Already-extracted delta (#717, REQ-186) — which reps a prior PRODUCTION run already bought.

THE ONE HOME FOR THIS RULE (REQ-182). gate@6 composition, the cost preview, and any future
auto-dispatch policy all ask the same question — "has this rep already been extracted for this
district?" — and they must ask it of THIS function. The project's most-repeated failure class is
the same rule implemented twice and drifting (eleven instances across five sessions); a second
spelling of the delta would silently diverge from the one the spend decision uses.

Stage 3 has had this discipline for capture since REQ-172 (`seedFromPriorCaptures` — an
already-captured URL is never re-fetched). This is its dispatch-layer sibling.

GRAIN: `(rec_key, file)`. District grain cannot answer the question — a 7->6 alternate-rep
re-dispatch (REQ-118) re-dispatches the district ON PURPOSE with a DIFFERENT rep, and the #473
recover-band path re-sends a NAMED rep deliberately. Both are legitimate; only a repeated
(rec_key, file) is duplicate work. Scoring at district grain would book that deliberate design as
waste — the #841 lesson: before calling a divergence a bug, check whether it is INTENTIONAL.

THE PREDICATE (measured 2026-08-23; see
`docs/technical-notes/production-quality-control-research/2026-08-23-already-extracted-delta-measure.py`):

    a rep is ALREADY EXTRACTED  <=>  it was sent in a prior production handoff that actually ran,
                                     UNLESS that run errored AND the rep left no fact behind.

A `school_fact` row is per-rep PROOF that THAT rep was read successfully, so it outranks the
run-level error flag. The measurement rejected the simpler "subtract reps from runs with no
errors": `extraction.n_errors` is recorded per (district, handoff), NOT per rep, so a single
errored rep re-admits its whole run — district 3904378 went 7 reps -> 0. That rule needlessly
re-buys 32 reps across 11 districts that demonstrably succeeded. This one re-admits exactly the 8
reps corpus-wide that both errored and yielded nothing: the true retry population.

PRODUCTION ONLY, BOTH SIDES. Only `run_kind='production'` runs count as having bought a rep, and
callers apply this only to a production dispatch. A benchmark/Council-Lab dispatch exists precisely
to re-extract the same reps under different councils (#679 walls those two worlds apart already),
so subtracting there would defeat its purpose.

DEGRADES, NEVER FAILS OPEN-ENDED. The sent-set lives in the immutable receipts on disk; the fact
evidence lives in the DB. If a receipt cannot be read, that handoff still contributes its
fact-proven reps rather than dropping out entirely — so an unreadable receipt costs a little
duplicate spend, never a stranded district. Stranding real work is the worse failure: over-spend is
observable and reversible, a district that silently sends nothing is neither.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from infrastructure.acquisition.common import paths

# Production runs for one district, with the per-run error count folded in. A handoff appears here
# ONLY if it actually ran — a composed-but-never-run draft bought nothing and must not suppress.
#
# The handoff side is DEDUPED to one row per hash BEFORE the join (#908): `handoff_hash` is not
# unique in the `handoff` table (the PK is handoff_id = hash+timestamp — the same content dispatched
# twice legitimately shares a hash), and `extraction` links by hash only, so a bare join would fan
# out and multiply SUM(n_errors) by the number of same-hash dispatches. Same-hash rows are identical
# CONTENT by construction of the identity hash, so any one receipt answers the sent-set question;
# MAX(path) picks the latest — the same latest-wins rule closing_argument's resolver uses.
_RUNS_SQL = text("""
    SELECT e.handoff_hash, SUM(COALESCE(e.n_errors, 0)) AS n_errors, h.path
      FROM extraction e
      LEFT JOIN (SELECT handoff_hash, MAX(path) AS path
                   FROM handoff GROUP BY handoff_hash) h
        ON h.handoff_hash = e.handoff_hash
     WHERE e.district_id = :d AND e.run_kind = 'production'
     GROUP BY e.handoff_hash, h.path
""")

_FACTS_SQL = text("""
    SELECT DISTINCT rec_key, source_file FROM school_fact WHERE district_id = :d
""")


def _receipt_path(handoff_hash: str, stored_path: str | None, root: Path) -> Path | None:
    """Resolve a receipt by BASENAME under the canonical handoffs dir, falling back to the stored
    path. `handoff.path` is absolute and machine-specific — it does not survive a fresh clone or
    CI, where the same receipt is present at the same basename."""
    if stored_path:
        name = Path(stored_path).name
        local = root / name
        if local.exists():
            return local
        p = Path(stored_path)
        if p.exists():
            return p
    hits = sorted(root.glob(f"handoff_{handoff_hash}_*.json"))
    return hits[-1] if hits else None


def _sent_reps(path: Path, district_id: str) -> set[tuple[str, str]] | None:
    """The (rec_key, file) pairs SENT for one district in one receipt.

    None means UNREADABLE — distinct from an empty set, which means "read fine, sent nothing".
    The caller must not conflate them: an empty set is authoritative (subtract nothing), while
    None means the sent-set is unknown and only the DB's fact evidence can be trusted.

    The WALK is inside the try too (#907): a syntactically-valid receipt of the wrong shape
    (hand-corrupted, legacy schema — nothing freeze() writes today, but nothing here should trust
    that) must degrade this one handoff to the fact-evidence fallback, never 500 the whole
    multi-district gate@6 preview it happens to be part of. That is the module's "degrades, never
    fails open-ended" promise applied to the parse as well as the I/O."""
    try:
        doc = json.loads(path.read_text())
        out = set()
        for d in doc.get("districts") or []:
            if d.get("district_id") != district_id:
                continue
            for rec in d.get("records") or []:
                if rec.get("decision") != "send":
                    continue
                for rp in rec.get("reps") or []:
                    out.add((rec.get("rec_key"), rp.get("file")))
        return out
    except Exception:
        return None


def already_extracted_reps(session, district_id: str, *, root=None) -> set[tuple[str, str]]:
    """The (rec_key, file) pairs a prior PRODUCTION run already bought for this district.

    THE one predicate behind #717's delta — see the module docstring for the rule and why the
    simpler run-level version was measured and rejected. Returns an empty set for a district with
    no prior production run, so a first dispatch is never narrowed.

    `session=None` is the codebase's DB-free sentinel (the convention every stage6 composition test
    uses, with the DB readers monkeypatched): no session, no history, subtract nothing. It cannot
    mask a production bug — `release.load_district` dereferences the session first and would raise
    long before this.
    """
    if session is None:
        return set()
    runs = list(session.execute(_RUNS_SQL, {"d": district_id}))
    if not runs:
        return set()
    root = Path(root) if root else paths.HANDOFFS_DIR

    # Fact evidence is fetched LAZILY (#910): only the errored-run and unreadable-receipt branches
    # read it, and the common all-clean district would otherwise pay a school_fact query per
    # preview render whose result is fetched and discarded.
    facts: set[tuple[str, str]] | None = None

    def _fact_evidence() -> set[tuple[str, str]]:
        nonlocal facts
        if facts is None:
            facts = {(rk, sf) for rk, sf in session.execute(_FACTS_SQL, {"d": district_id})}
        return facts

    out: set[tuple[str, str]] = set()
    for handoff_hash, n_errors, stored_path in runs:
        path = _receipt_path(handoff_hash, stored_path, root)
        sent = _sent_reps(path, district_id) if path else None
        if sent is None:
            # Receipt missing or unreadable: the sent-set is unknown, so fall back to the DB's own
            # per-rep evidence. Costs a little duplicate spend, never strands a district.
            out |= _fact_evidence()
        elif not n_errors:
            out |= sent                      # clean run: everything it sent was read
        else:
            out |= (sent & _fact_evidence())  # errored run: only what provably produced a fact
    return out
