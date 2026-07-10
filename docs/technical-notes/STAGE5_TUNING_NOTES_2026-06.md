# Stage 5 — tuning & learning-loop methods (reference)

> **Distilled methods + citations** for the Stage-5 learning loop. The built design lives in
> `STAGE5_FILTER_DESIGN_2026-06.md` (§2 detectors/combiner, §5 the loop); this note is the *method
> reference* behind it — what to reach for as label coverage grows. Rewritten 2026-07-01; the raw
> research transcripts (two Perplexity passes, June 2025) are in git history and the primary-source
> citations survive below. V2 adds the weak-supervision / labeling-function layer (Part C), sourced from
> `docs/technical-notes/filtering-research/`.

The loop has **three regimes**, each with its own correct machinery. Do NOT build a later regime early —
at n≈440 labels the small-n methods (Part A) are correct and the scale machinery (Part B) is high-variance noise.

---

## Part A — small-n regime (BUILD NOW; n≈150–1000, ≤~60 groups)

**Threshold optimization under a hard recall floor.**
- **≤5 knobs → exact frontier / coarse grid + coordinate descent** — cheap objective (just re-score the
  stored labels), produces a fully-inspectable precision–recall surface. Built: `frontier.py`.
- **6–12 knobs → constrained Bayesian opt** (Optuna `TPESampler(constraints_func=…)` / c-TPE, IJCAI'23),
  recall floor as an inequality constraint, precision the objective. Not yet needed.
- **Recall floor is a POLICY number, not a round one** — set it at/below the *measured* baseline of the
  metric it defends. **The canonical floor (#208, `harness.RECALL_FLOOR = 0.98`) defends A+B recall**
  (reaches-review — no target suppressed to tier D), whose measured baseline is 0.9961, so 0.98 sits below
  it as required. The earlier tier-A guidance here (baseline 0.9688/0.9756, "not a naive 0.98") described
  the pre-#208 floor that targeted tier-A recall — tier-A recall is precision-shaped by design (~0.89 with
  borderline targets routed to review) and is no longer the floored metric.

**Overfit guards (small n, correlated groups).**
- **Leave-One-Group-Out CV by district** (`sklearn.LeaveOneGroupOut`) — records within a district share
  CMS chrome/templates, so plain k-fold leaks. Report recall/precision variance across folds; high variance
  = thresholds over-indexed on particular districts. Built (`frontier.logo_cv`); **reported, never a gate**
  (CV detects overfit, doesn't prevent it; directional at n≈12–60).
- **Bootstrap threshold-stability** (`scipy.stats.bootstrap`) — resample labels, re-optimize, report each
  knob's coefficient of variation; CV>0.3 = poorly determined → widen range / regularize / collect more.
- **Minimum group support** — refuse a per-group threshold below k≈10 labels; fall back to the global default.

**Drift detection (does a new labeled batch degrade the live config enough to retune?).**
- **Bernoulli CUSUM** on recall and precision *separately* vs. the floor — accumulates evidence, so a
  single batch with 2–3 extra misses won't trip it (~10-line NumPy fn). **Two-gate** with the **lower
  Wilson-score CI bound** (`statsmodels.stats.proportion.proportion_confint(method='wilson')`) to kill
  small-n false alarms (the 95% Wilson half-width at n≈150 is ±3–4pp — that width *is* why one batch can't
  be trusted). **McNemar** (`mlxtend`) / Fisher's exact as the "bother retuning?" gate comparing old vs new
  thresholds on the same examples. **Avoid** Page-Hinkley (assumes Gaussian) and KS/chi-squared/Evidently/
  Alibi-Detect (those detect *input-distribution* drift — the wrong layer; we need *labeled-performance* drift).
- **Config-induced vs. world drift:** a Stage-5 config change moves the `data` fingerprint too (tier/category
  are config-derived), so the ledger flags `pure_config_move=False`; the drift detector must feed on
  *new-district* data change only, not the tuning move's own effect.

---

## Part B — scale endgame (DEFERRED; ~17k districts nested in ~50 states + a handful of CMS vendors)

Documented so the small-n foundations are built compatibly; **none of it runs until coverage warrants.**
Most groups will have few/zero labels *permanently* — so:

1. **Estimation — hierarchical partial-pooling shrinkage** `global → CMS-vendor → state → district`, each
   level shrinking toward its parent ∝ how little local data it has; a zero-label district inherits its
   state posterior mean (itself shrunk toward CMS-cluster). Empirical Bayes (closed-form Beta-Binomial /
   `statsmodels MixedLM`) over full MCMC for cost; `bambi`/`pymc` for the 3-level nest. Zero-support
   thresholds are **inherited, not exposed to the optimizer** (separates estimation from optimization).
2. **Detection — ADDIS online-FDR** (`online-fdr`) across per-district CUSUM streams (sequential, discards
   in-control streams early → power where most streams are fine), rolled up via batch **BH** at the state/CMS
   level; only **state/CMS-level alerts reach the human** — district signals trigger automated re-estimation.
   `p-filter` (Barber & Ramdas) for provable multi-level group-FDR.
3. **Scope — VPC/ICC variance-components** (`pingouin.intraclass_corr` / `bambi` nested random effects)
   decides *which level a knob lives at*: VPC>0.3 → free parameter at that level; 0.1–0.3 → covariate/offset;
   <0.1 → pool fully. **Strong prior from our own data: CMS-vendor explains more variance than state**
   (chrome/template behavior is vendor-driven, not geographic) — which is why V2 promotes `cms_hint` to a
   first-class **grouping** signal now (STAGE5_FILTER §3), even though it's not a *score* input.

Library gate: `scikit-learn`/`scikit-optimize` now; `pingouin`/`online-fdr`/`bambi`/`pymc` only when coverage grows.

---

## Part C — the weak-supervision / labeling-function layer (V2, the combiner's endgame)

Source: `docs/technical-notes/filtering-research/` (Snorkel; FrugalGPT; SUPG; K-12 hours markup). The V2
detectors ARE labeling functions; this is how they compose and how far to push the combiner.

- **Start with a transparent weighted vote** (config-as-data weights), NOT a learned model. Snorkel's own
  finding: a hand-weighted vote is competitive, and the learned generative `LabelModel` beats majority vote
  **only** when LF accuracies are *heterogeneous* at *medium* label density — it converges to majority vote
  at low/high density. So the learned combiner is deferred until per-detector diagnostics (below) justify it.
- **Per-LF diagnostics are the live dashboard** (Snorkel `LFAnalysis`, reimplemented in `harness.py`):
  **polarity** (which decision it votes), **coverage** (fraction of records it fires on), **accuracy**
  (precision when it fires, vs the matching human facet), **overlap/conflict** (≥2 LFs fire / disagree).
  These turn "adjust the weights" into a data-grounded conversation and name the next detector to fix.
- **Learned `LabelModel`** (Snorkel) — the deferred graduation: infers each LF's accuracy from the
  agreement/disagreement structure *without* gold labels for every point, down-weighting noisy LFs. Adopt
  only when diagnostics show heterogeneous accuracy at medium density; **model LF dependencies** (two LFs
  encoding the same heuristic double-count) to avoid bias — pairs naturally with the CMS-vendor pooling of Part B.
- **Two-stage cascade calibration** (FrugalGPT: 50–98% cost cut at GPT-4 quality; SUPG: statistically
  guaranteed recall). Stage 5 is the cheap deterministic stage; only the `review`/`send` band incurs Stage-7
  cost. **Calibrate the `suppress` (auto-NO) boundary to a fixed recall floor** with SUPG-style
  importance-sampled validation against hand labels — and **instrument the suppressed tier**: periodically
  hand-label a sample of auto-suppressed records to measure the false-negative rate *directly* (the only way
  to catch silent recall loss). Report recall + pass-through + a ±sensitivity sweep at the operating point.
- **Threshold that changes the plan:** if the `review`+`send` (LLM-bound) band exceeds ~30–40% of records,
  the detectors are too timid — tighten `send`/`suppress` using the conflict analysis, don't widen review.

---

## Key citations (primary sources)

- **Snorkel** — Ratner et al., *Rapid Training Data Creation with Weak Supervision*, VLDB J. 2017; **DryBell**
  (Bach et al., SIGMOD 2019) — weak supervision at Google, LF diagnostics (polarity/coverage/overlap/conflict).
- **FrugalGPT** — Chen, Zaharia & Zou, arXiv:2305.05176 / TMLR 2024 (cheap→expensive cascade, 50–98% cost cut).
- **SUPG** — Kang et al., *Approximate Selection with Guarantees using Proxies*, PVLDB 13(12) 2020 (recall-target cutoff).
- **Boilerplate** — Kohlschütter et al., WSDM'10 (shallow text features); trafilatura `favor_recall`/`include_tables`
  (footers are dropped by main-content extractors — the inverse of what hours extraction needs).
- **K-12 hours markup** — `filtering-research/`: schema.org `OpeningHoursSpecification` near-absent on K-12 CMS
  (<5%); heading-proximity + footer-scoping is the tractable signal; office-vs-school-hours & bell-fragment
  are the dangerous confusables.
- **Small-n / scale stats** — Bernoulli CUSUM + Wilson CI; `sklearn.LeaveOneGroupOut`; Optuna c-TPE (IJCAI'23);
  hierarchical partial pooling (Stan/PyMC/bambi); ADDIS/LORD/SAFFRON online-FDR; p-filter (Barber & Ramdas,
  JRSS-B 2017); VPC/ICC (`pingouin`).

*(Full URLs for the June-2025 Perplexity passes are preserved in git history of this file.)*
