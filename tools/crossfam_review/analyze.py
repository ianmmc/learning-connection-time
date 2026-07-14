"""Rigorous per-model + per-judge effectiveness analysis over a completed run's receipts.

Answers the questions that decide roster tuning for a later sweep: which finder families pull their
weight (value per real dollar, not just raw counts), how much each UNIQUELY contributes (marginal
corroboration), which pairs agree, and whether the judge cascade shows family bias — with the
family-bias test done PROPERLY (controlled for finder quality; the naive version is confounded and
gives a backwards answer, see the 2026-07-13 analysis doc).

    python -m tools.crossfam_review.analyze 2026-07-13

Reads a run's receipts (`raw_findings.json`, `adjudications.json`, `raw_replies.jsonl` for real
`usage.cost`) — no network, no re-derivation. Requires scipy (Fisher exact) + is a dev/analysis tool,
not part of the review path; at extraction time it becomes an optional `[analysis]` extra.
"""
from __future__ import annotations

import itertools
import json
import sys
from collections import Counter, defaultdict

from tools.crossfam_review.roster import FINDERS, JUDGES
from tools.crossfam_review.shards import REPO_ROOT


def _load(stamp: str):
    d = REPO_ROOT / "data" / "review" / f"crossfam-{stamp}"
    raw = json.loads((d / "raw_findings.json").read_text())
    adj = json.loads((d / "adjudications.json").read_text())
    reps = [json.loads(l) for l in (d / "raw_replies.jsonl").read_text().splitlines()] \
        if (d / "raw_replies.jsonl").exists() else []
    return raw, adj, reps


def _key(file, line, category) -> tuple:
    try:
        lb = int(line) // 10
    except (TypeError, ValueError):
        lb = 0
    return (file, lb, (category or "").strip().lower())


def _family(model_id: str) -> str:
    return model_id.split("/", 1)[0] if "/" in model_id else model_id


def short(m: str) -> str:
    return m.split("/")[-1]


def analyze(stamp: str) -> dict:
    from scipy.stats import fisher_exact
    raw, adj, reps = _load(stamp)

    # candidate (dedup key) -> set of finder models; and the adjudicated / confirmed key sets
    cand_models: dict[tuple, set] = defaultdict(set)
    for f in raw:
        cand_models[_key(f["file"], f["line"], f["category"])].add(f["model"])
    adj_by_key = {_key(a["file"], a["line"], a.get("category")): a for a in adj}
    confirmed_keys = {k for k, a in adj_by_key.items() if a["confirmed"]}
    adj_keys = set(adj_by_key)

    # per-model cost + reliability from the raw-reply receipts
    cost, empty, err = defaultdict(float), defaultdict(int), defaultdict(int)
    for r in reps:
        cost[r["model"]] += (r.get("cost_usd") or 0.0)
        empty[r["model"]] += bool(r.get("empty"))
        err[r["model"]] += (not r.get("ok") and not r.get("skipped"))
    MODELS = [m.id for m in FINDERS]

    # per-model: adjudicated candidates it touched, confirmed of those, and sole-corroborator count
    found, conf_found, solo_dep = defaultdict(set), defaultdict(set), defaultdict(int)
    for k in adj_keys:
        ms = cand_models.get(k, set())
        for m in ms:
            found[m].add(k)
            if k in confirmed_keys:
                conf_found[m].add(k)
    for m in MODELS:
        for k in conf_found[m]:
            if len({_family(x) for x in cand_models[k] if x != m}) < 2:
                solo_dep[m] += 1     # removing m drops this confirmed candidate below min-agree 2

    models = {}
    for m in MODELS:
        nc, cf, c = len(found[m]), len(conf_found[m]), cost[m]
        models[m] = {"cost": round(c, 4), "candidates": nc, "confirmed": cf,
                     "precision": round(cf / nc, 3) if nc else 0.0,
                     "conf_per_usd": round(cf / c, 1) if c else 0.0,
                     "sole_corroborator": solo_dep[m], "empties": empty[m], "errors": err[m]}

    # pairwise co-occurrence (over adjudicated candidates) — raw + Jaccard
    pairs = []
    for a, b in itertools.combinations(MODELS, 2):
        fa, fb = found[a], found[b]
        inter, union = len(fa & fb), len(fa | fb)
        pairs.append({"a": short(a), "b": short(b), "shared": inter,
                      "jaccard": round(inter / union, 3) if union else 0.0})
    pairs.sort(key=lambda p: (-p["jaccard"], -p["shared"]))

    # cluster-size distribution (how many finders agreed) + the max
    sizes = Counter(len(cand_models[k]) for k in adj_keys)

    # per-finder category lens (finder-labeled)
    lens = {}
    mcat = defaultdict(Counter)
    for f in raw:
        mcat[f["model"]][(f["category"] or "?").strip().lower()] += 1
    for m in MODELS:
        lens[m] = mcat[m].most_common(3)

    # judge tallies
    jt = defaultdict(lambda: {"confirmed": 0, "refuted": 0, "error": 0})
    for a in adj:
        for v in a["verdicts"]:
            jt[v["judge"]][v["verdict"]] = jt[v["judge"]].get(v["verdict"], 0) + 1

    # CONTROLLED family bias: for each judge with a same-family finder, compare the family judge to the
    # OTHER judges on the SAME candidates where the family finder is present (holds candidate quality fixed).
    family_bias = []
    finder_by_family = defaultdict(list)
    for m in MODELS:
        finder_by_family[_family(m)].append(m)
    for jkey, jm in JUDGES.items():
        fam = _family(jm.id)
        for finder in finder_by_family.get(fam, []):
            jc = jt_ = oc = ot = 0
            for a in adj:
                k = _key(a["file"], a["line"], a.get("category"))
                if finder not in cand_models.get(k, set()):
                    continue
                jv = next((v for v in a["verdicts"]
                           if v["judge"] == jm.id and v["verdict"] in ("confirmed", "refuted")), None)
                others = [v for v in a["verdicts"]
                          if v["judge"] != jm.id and v["verdict"] in ("confirmed", "refuted")]
                if not jv or not others:
                    continue
                jc += jv["verdict"] == "confirmed"; jt_ += 1
                oc += sum(v["verdict"] == "confirmed" for v in others); ot += len(others)
            if jt_ and ot:
                odds, p = fisher_exact([[jc, jt_ - jc], [oc, ot - oc]])
                family_bias.append({
                    "judge": short(jm.id), "finder": short(finder), "n": jt_,
                    "judge_rate": round(jc / jt_, 3), "peers_rate": round(oc / ot, 3),
                    "delta": round(jc / jt_ - oc / ot, 3), "odds": round(float(odds), 2),
                    "p": round(float(p), 4)})

    return {"stamp": stamp, "totals": {"raw": len(raw), "adjudicated": len(adj),
                                       "confirmed": len(confirmed_keys)},
            "models": models, "pairs": pairs, "cluster_sizes": dict(sizes),
            "lenses": lens, "judges": dict(jt), "family_bias": family_bias}


def _print(r: dict) -> None:
    t = r["totals"]
    print(f"\n── cross-family review effectiveness · {r['stamp']} ──")
    print(f"raw {t['raw']} · adjudicated {t['adjudicated']} · confirmed {t['confirmed']}")
    print("  NB: only the corroborated (>=2 family) set was judged — 'precision' is over that set, "
          "not solo accuracy.\n")

    print("VALUE — confirmed found vs real cost (sorted by conf/$):")
    print(f"  {'model':24}{'conf':>5}{'cand':>6}{'cost$':>8}{'conf/$':>8}{'prec':>7}{'sole':>6}{'err':>5}")
    for m, s in sorted(r["models"].items(), key=lambda kv: -kv[1]["conf_per_usd"]):
        print(f"  {short(m):24}{s['confirmed']:>5}{s['candidates']:>6}{s['cost']:>8.3f}"
              f"{s['conf_per_usd']:>8.0f}{s['precision']:>7.2f}{s['sole_corroborator']:>6}"
              f"{s['errors']+s['empties']:>5}")

    print("\nMODEL PAIRS most likely to find the same issue (by Jaccard):")
    for p in r["pairs"][:5]:
        print(f"  {p['a']:22} + {p['b']:22} jaccard={p['jaccard']:.2f} shared={p['shared']}")

    print("\nAGREEMENT — how many finders found each candidate:")
    for sz in sorted(r["cluster_sizes"], reverse=True):
        mx = "  <-- MAX" if sz == max(r["cluster_sizes"]) else ""
        print(f"  {sz:2} finders: {r['cluster_sizes'][sz]:3} candidates{mx}")

    print("\nFINDER LENSES (top finder-labeled categories):")
    for m, top in r["lenses"].items():
        print(f"  {short(m):24} " + ", ".join(f"{c}:{n}" for c, n in top))

    print("\nJUDGES (confirm/refute/error):")
    for j, s in r["judges"].items():
        print(f"  {short(j):22} conf {s.get('confirmed',0):>4}  refute {s.get('refuted',0):>4}  "
              f"err {s.get('error',0):>3}")

    print("\nFAMILY BIAS (controlled — family judge vs peers on the SAME candidates):")
    for fb in r["family_bias"]:
        sig = "  <-- significant" if fb["p"] < 0.05 else "  (n.s.)"
        print(f"  {fb['judge']:16} ↔ {fb['finder']:22} n={fb['n']:3}  "
              f"judge={fb['judge_rate']:.2f} peers={fb['peers_rate']:.2f} "
              f"Δ={fb['delta']:+.2f}  p={fb['p']:.3f}{sig}")


if __name__ == "__main__":
    _print(analyze(sys.argv[1] if len(sys.argv) > 1 else "2026-07-13"))
