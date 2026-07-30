"""#684 corpus measurement — the staff-day confusable, rerunnable (the #691/#694/#683 pattern).

Runs all three arms the design decision rests on, over every text-bearing capture record joined to the
human labels. Each arm answers one question, and two of the three answers are NEGATIVE — the point of
committing this script is that the rejections are reproducible, not just the accepted rule.

  --presence   Arm 1: "a staff-referent word within N chars of an in-window time" (the shape #684's
               issue proposed). Expected: a COIN FLIP. Grid of 3 vocabularies x 3 windows.
  --doc        Arm 2: a document-level /employee handbook/ match. Expected: net-NEGATIVE (most of its
               labeled hits are real targets).
  --clause     Arm 3 (the shipped rule): the live `build_signals.staff_duty_positional` +
               `detectors.staff_day_owned` — the employment-obligation CLAUSE scored relationally
               against student-referent language, per basis, ANY-basis. Expected: acc 1.000.
  --sensitivity  Arm 3's robustness: re-run the verdict across student windows 100/140/220/300/500 for
               every record carrying a duty clause, under both the ANY and ALL combinators. The
               shipped choice (ANY @ 140) must be stable and ALL must be the fragile one, or the
               "measurement could not fail".

No flags = all four. Text bases come from the LIVE `build_signals.text_bases` — the same selection
compute_signals stores signals from (PR #705 review [4]: the first version hand-copied that logic, and
a hand copy silently drifts, invalidating a re-run without anyone noticing). Offsets never cross texts.

Run:  python3 docs/technical-notes/production-quality-control-research/2026-07-29-issue684-staff-day-measure.py
"""
import bisect
import json
import re
import sys

from sqlalchemy import text as sqltext

from infrastructure.acquisition.common import db as gdb
from infrastructure.acquisition.stage5_filter import build_signals as BS
from infrastructure.acquisition.stage5_filter import detectors as D

# ---- Arm 1 vocabularies (NOT shipped — the measured rejection) ----
_OFFICE = [re.escape(k) for k in BS.OFFICE_HOURS_KW]
_OBLIG = [r"report to work", r"report to school by", r"report at\b", r"remain until", r"staff members?",
          r"staff are to", r"staff with a", r"duty day", r"contract(?:ed)? day", r"work ?day",
          r"faculty and staff", r"employee handbook", r"certified staff", r"classified staff"]
PRESENCE_VOCABS = {
    "V1_office_kw": re.compile("|".join(_OFFICE), re.I),
    "V2_obligation": re.compile("|".join([*_OFFICE, *_OBLIG]), re.I),
    "V3_bare_referent": re.compile("|".join([*_OFFICE, *_OBLIG, r"\bstaff\b", r"\bfaculty\b",
                                             r"\bemployees?\b"]), re.I),
}
PRESENCE_WINDOWS = [100, 140, 220]
DOC_EMPLOYEE_RE = re.compile(r"employee handbook|staff handbook|personnel handbook|"
                             r"certified (?:staff )?handbook|employee manual", re.I)
SENSITIVITY_WINDOWS = [100, 140, 220, 300, 500]


def _near(pattern, text, tpos, near):
    """In-window time offsets with a `pattern` match within `near` chars (the #537 bisect pattern)."""
    hits = set()
    for m in pattern.finditer(text):
        i = bisect.bisect_left(tpos, m.start() - near)
        while i < len(tpos) and tpos[i] <= m.end() + near:
            hits.add(tpos[i])
            i += 1
    return hits


def record_bases():
    """(rec_key, bases, full_all) per Stage-4-complete record — basis selection is the LIVE
    `build_signals.text_bases`, never a local copy (PR #705 review [4])."""
    for ddir in sorted(p for p in BS.RAW_DIR.glob("*") if p.is_dir()):
        if not all((ddir / f).exists() for f in ("captures.json", "processed.json", "discovery.json")):
            continue
        try:
            did = json.loads((ddir / "discovery.json").read_text())["district_id"]
            processed = json.loads((ddir / "processed.json").read_text())
        except Exception:  # noqa: BLE001 — one unreadable district never kills the scan
            continue
        for prec in processed:
            h = prec["hash"]
            rdir = ddir / "captures" / h
            mp = rdir / "page.main.txt"
            main_text = mp.read_text(errors="replace") if mp.exists() else None
            tb = BS.text_bases(rdir, prec.get("texts", []), main_text)
            yield f"{did}:{h}", [tb["best_text"], *tb["table_reps"]], tb["full_all"]


def main():
    argv = sys.argv[1:]
    arms = {a for a in ("--presence", "--doc", "--clause", "--sensitivity") if a in argv} or \
        {"--presence", "--doc", "--clause", "--sensitivity"}

    with gdb.get_engine().connect() as con:
        labels = dict(con.execute(sqltext(
            "SELECT rec_key, primary_label FROM label "
            "WHERE status != 'unlabeled' AND primary_label IS NOT NULL")).fetchall())
        tiers = dict(con.execute(sqltext("SELECT rec_key, tier FROM record")).fetchall())

    rows = []
    for rec_key, bases, full_all in record_bases():
        pres, duty_bases = {}, []
        for t in bases:
            tpos = sorted(o for o, _ in BS.in_window_positions(t))
            if not tpos:
                continue
            for vname, pat in PRESENCE_VOCABS.items():
                for w in PRESENCE_WINDOWS:
                    pres[(vname, w)] = max(pres.get((vname, w), 0), len(_near(pat, t, tpos, w)))
            d, _ = BS.staff_duty_positional(t, tpos)
            stu = {w: len(_near(BS.STUDENT_REF_RE, t, tpos, w)) for w in SENSITIVITY_WINDOWS}
            duty_bases.append({"n_iw": len(tpos), "duty": d, "stu": stu})
        rows.append({"rec_key": rec_key, "label": labels.get(rec_key), "tier": tiers.get(rec_key),
                     "presence": pres, "bases": duty_bases,
                     "doc_employee": bool(DOC_EMPLOYEE_RE.search(full_all))})

    lab = [r for r in rows if r["label"]]
    tgt = [r for r in lab if r["label"] in BS.TARGET_LABELS]
    non = [r for r in lab if r["label"] not in BS.TARGET_LABELS]
    print(f"records scanned: {len(rows)}   labeled: {len(lab)} "
          f"({len(tgt)} target / {len(non)} non-target)   "
          f"tier-A labeled: {sum(1 for r in lab if r['tier'] == 'A')} "
          f"({sum(1 for r in lab if r['tier'] == 'A' and r['label'] in BS.TARGET_LABELS)} target / "
          f"{sum(1 for r in lab if r['tier'] == 'A' and r['label'] not in BS.TARGET_LABELS)} non-target)")

    def score(name, pred):
        ft, fn = [r for r in tgt if pred(r)], [r for r in non if pred(r)]
        fu = [r for r in rows if not r["label"] and pred(r)]
        acc = len(fn) / (len(ft) + len(fn)) if (ft or fn) else 0
        print(f"{name:<40}{len(ft):>6}{len(fn):>6}{acc:>8.3f}"
              f"{sum(1 for r in ft if r['tier'] == 'A'):>7}"
              f"{sum(1 for r in fn if r['tier'] == 'A'):>7}{len(fu):>7}")

    hdr = f"\n{'candidate':<40}{'tgt':>6}{'non':>6}{'acc':>8}{'A_tgt':>7}{'A_non':>7}{'unlab':>7}"
    if "--presence" in arms:
        print("\n=== ARM 1 (REJECTED): a staff word NEAR a time — the issue's proposed shape ===" + hdr)
        for vname in PRESENCE_VOCABS:
            for w in PRESENCE_WINDOWS:
                score(f"{vname} @ {w}", lambda r, v=vname, x=w: r["presence"].get((v, x), 0) >= 1)
        print("  `acc` = share of firings on labeled NON-targets (a negative detector is right there).")
        print("  ~0.5 is a coin flip: A_tgt is what a hard-undermining rule would have DEMOTED.")

    if "--doc" in arms:
        print("\n=== ARM 2 (REJECTED): a document-level /employee handbook/ match ===" + hdr)
        score("doc_employee_handbook", lambda r: r["doc_employee"])
        print("  the labeled hits, by label — districts publish bell tables inside/beside staff handbooks:")
        for r in [r for r in lab if r["doc_employee"]]:
            print(f"    {r['rec_key']:<24} tier={r['tier']} {r['label']}")

    def verdict(r, window, combinator):
        with_times = [b for b in r["bases"] if b["n_iw"]]
        if not with_times or not any(b["duty"] for b in with_times):
            return False
        return combinator(b["duty"] > b["stu"][window] for b in with_times)

    if "--clause" in arms:
        print("\n=== ARM 3 (SHIPPED): the duty CLAUSE, relational, per basis, ANY @ 140 ===" + hdr)
        score("staff_day_owned (live predicate)",
              lambda r: verdict(r, BS.STUDENT_REF_NEAR_CHARS, any))
        # cross-check the arithmetic against the live detector, so the report can't drift from the code
        for r in rows:
            sd = sr = 0
            for b in r["bases"]:
                if b["duty"] - b["stu"][BS.STUDENT_REF_NEAR_CHARS] > sd - sr:
                    sd, sr = b["duty"], b["stu"][BS.STUDENT_REF_NEAR_CHARS]
            live = D.staff_day_owned({"staff_duty_times": sd, "student_ref_times": sr})
            assert live == verdict(r, BS.STUDENT_REF_NEAR_CHARS, any), r["rec_key"]
        print("  (each record's verdict re-checked against detectors.staff_day_owned — no drift)")
        print("\n  every record carrying a duty clause at all:")
        dc = [r for r in rows if any(b["duty"] for b in r["bases"])]
        for r in sorted(dc, key=lambda r: not verdict(r, 140, any)):
            print(f"    {r['rec_key']:<24} tier={r['tier']} owned={verdict(r, 140, any):d} "
                  f"label={r['label']} "
                  f"bases={[(b['n_iw'], b['duty'], b['stu'][140]) for b in r['bases'] if b['n_iw']]}")

    if "--sensitivity" in arms:
        print("\n=== ARM 3 SENSITIVITY: student window x combinator (must be stable at the shipped point) ===")
        dc = [r for r in rows if any(b["duty"] for b in r["bases"])]
        print(f"{'student window':>16}{'ANY fires':>12}{'ALL fires':>12}   which (ANY)")
        for w in SENSITIVITY_WINDOWS:
            a = [r for r in dc if verdict(r, w, any)]
            b = [r for r in dc if verdict(r, w, all)]
            print(f"{w:>16}{len(a):>12}{len(b):>12}   {', '.join(r['rec_key'] for r in a)}")
        print("  SHIPPED = ANY @ 140. ANY holds the verdict across every window; ALL loses it at 500,")
        print("  which is why the combinator is ANY and the window is not load-bearing at 140-300.")


if __name__ == "__main__":
    main()
