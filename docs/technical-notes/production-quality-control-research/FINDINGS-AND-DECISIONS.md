# Production quality-control research — findings & decisions (2026-07-10)

> **What this is.** The ~1,660 lines of deep-research in this directory, distilled to the decisions that
> drive epics **#200** (dev-time defect prevention) and **#209** (runtime guardrails for autonomous
> operation). Read this first; the raw reports are the depth/citations behind each decision.
> **Why it exists.** Commandment 4 (best use of the one human's time) + commandment 1 (auditability): a
> future collaborator — or an outside skeptic challenging our approach — reads *this*, not 1,660 lines.
> **Governing constraints** (the four commandments, memory `project-four-commandments`): auditability is the
> north star; automation is a correctness *requirement* (manual inspection of ~20k districts / ~100k schools
> is impossible), not a luxury; cash spend must be tight; the one human's attention is the scarce resource.

## The raw sources (three questions, seven files)
- **Feedback-loop bias** (Prompt 1): `A data pipeline uses a cheap deterministic classif.md`,
  `Selective Labels Debiasing.md`, `compass_artifact_...3cd7e...md`, `deep-research-report.md`.
- **Low-volume safe-promotion** (Prompt 2): `Offline Batch ML Deployments.md`,
  `Standard ML canary_shadow deployment assumes high.md`.
- **Gate-relaxation calibration** (Prompt 3): `compass_artifact_...9aee...md`.

---

## 0. THE HEADLINE — "the illusion of improvement" is a CURRENT blind spot, not a future risk

Three files independently converge on this, and it is the most consequential finding: **when you tune the
Stage-5 filter and measure before/after only on the approved/labeled set** — which is exactly how the #108
facet-scoring measured-pass and the whole `STAGE5_FILTER_DESIGN §3a` measured-pass discipline work today —
**you are structurally blind to recall collapse.** The documents the filter wrongly rejected never enter the
measurement, so a tuning pass can certify a *regression* as a win. Standard metrics rise at the exact moment
true population recall falls.

**Root cause = determinism, not small data.** Swaminathan & Joachims: under a *deterministic* filter,
counterfactual correction is provably impossible even with infinite data. More labels will not fix this;
only **injected stochasticity** (exploration) will. Our Stage-5 gate is deterministic today.

**Consequence for the plan:** the exploration quota (top of #209) is not a "future autonomy guardrail" — it
is the fix for how we *already* measure everything, and it is the single highest-value item across both
epics. And a cross-cutting rule falls out: **every scoring measured-pass must evaluate against the
exploration cohort**, or the discipline itself can bless the illusion (retroactively touches #108).

> **SHIPPED (2026-07-12, #214).** The cross-cutting rule is now enforced in code: `harness.exploration_cohort`
> (a new scorecard section + `print_summary` line), `frontier.reject_cohort_quality` (per grid config + a
> champion→challenger reject-quality warning in `--gate`), and a `tuning_ledger` `reject_cohort_quality`
> delta + advisory `reject_quality_regressed` flag — all over the SAME reproducible audit draw the live
> quota (#211) uses. Retroactive #108 re-verify: reject-quality/TNR = 1.0 under the live config (the
> approved-set win hid no pruned-tail collapse). Detail: `STAGE5_FILTER_DESIGN.md` §5d.

---

## 1. Feedback-loop / survivorship bias — DECISIONS

**The problem, named:** the *Selective Labels Problem* (Lakkaraju et al., KDD 2017). Stage-5 approves →
only approved reps get paid Stage-7 outcomes → those outcomes tune Stage-5 → Stage-5 can entrench a wrong
rejection of a whole document class, and never see the evidence that would correct it.

**BUILD (viable at our scale/budget/one-operator):**
- **Controlled Stochastic Exploration** — the #1 intervention in every source. Route a **random** sample of
  *rejected* reps to the extractor anyway. **Random, NOT boundary-targeted** — uncertainty/active sampling
  re-introduces the bias and under-covers the confident-reject region (the region that entrenches a wrongly
  rejected class). It is the *only* technique that structurally repairs the loop; everything else models
  around it and mathematically requires it (positivity / nonzero propensity everywhere).
- **Rejection-Quality metric = TNR on the exploration cohort** — the honest recall signal our approved-set
  metrics cannot give; it finally gives the advisory recall floor a *real denominator*.
- **Weak-supervision labeling functions** — we already have them (the Stage-5 facet detectors are
  Snorkel-style LFs); they label the reject pool without spending extractor $. A cheap complement.
- **Doubly-Robust loss with a deliberately small model** (ridge-logistic / shallow tree) — a *fast-follow*
  once ~50–100 exploration labels accrue; the double-robustness buffer tolerates 440-label modeling error.
  Cannot precede exploration (needs the nonzero propensities exploration creates).

**RULE OUT (and why — for the audit trail):**
- **Reject inference / label imputation (augmentation, parceling, self-learning, EM/DCEM)** — THE TRAP, not
  the fix. Under deterministic filtering these *entrench* the boundary (self-fulfilling), and imputation can
  *reverse the bias sign*. **Never impute reject labels; only observed exploration outcomes are safe.**
- **Pure IPS / SNIPS** — near-zero propensities at n≈440 blow up weights; usable only as the inner term of
  DR, only after exploration.
- **Bayesian active learning (SEL-BALD), contextual bandits** — operationally heavy / assume online
  many-round traffic we don't have; uncertainty estimates are noise at 440 samples.

**DECIDED SPEC — the #209 exploration-quota sub-issue:**
- Random **3–5% of below-threshold (rejected)** reps + a small (~2%) hold-out of *approved* reps (to catch
  false positives), routed to Stage-7 at each re-ingest / dispatch cycle.
- Tagged as a first-class **`run_kind` = `exploration_audit`** (reuses the #147/#148 pattern; walled off
  from production/funnel stats like `batch_00000`).
- **Budget cap = a fixed COUNT, not a floating %** (≈600 calls at 20k reject-scale — negligible, known,
  cappable), recorded to the fingerprinted tuning-ledger.
- Log every draw (seed, rep key, classifier score, outcome) → an outsider can replay "you rejected class X;
  your own random audit extracted it N times; here is the boundary correction." (North star, concrete.)
- Compute **Rejection-Quality (TNR on the exploration cohort)** each cycle; surface extractor *successes*
  among rejects as new labels.

---

## 2. Safe-promotion & drift at BATCH / low-volume — DECISIONS

**The reframe both files insist on:** this is not A/B traffic-splitting; it is **paired, cluster-correlated
model comparison on a frozen corpus.** The **district is the unit of resampling and exchangeability.** No
live stream to split; a config change is applied via a full re-ingest and scored against the same held-out
corpus.

**The promotion GATE — replace the naive default.** A "1% canary" or a plain paired t-test is *invalid* at
n≈440 / ~90 districts: **DEFF = 1 + (m̄−1)·ICC ≈ 2.4** (m̄≈4.9, ICC~0.3) means naive variance is understated
~2.4× and naive SEs are off by √2.4. Gate instead on **"provably not-worse within a pre-declared margin Δ,
on held-out districts, with cluster-honest variance"** — a layered gate:
1. **Group/LOGO-CV guardrail** — entire districts to train *or* eval, never both (random k-fold leaks
   district artifacts and manufactures false wins); reject any fold degrading > Δ.
2. **Nadeau-Bengio corrected resampled t-test** (inflates SE for CV overlap; best replicability) — or
   **Wilcoxon signed-rank** (regression-shaped metrics) / **McNemar exact** (classification concordance,
   exact binomial when b+c < 25).
3. **Cluster ("cases") bootstrap** — resample *whole districts*, not rows; pseudo-count-regularized so
   precision/recall denominators don't collapse near 1.0. Or a **within-district block-permutation** test
   (validated to hold Type-I error at ~90 clusters, where parametric mixed-effects can inflate it).
4. **TOST non-inferiority** against a **pre-declared, cluster-adjusted Δ** (e.g. "≤2 pp district-level recall
   degradation"), Eliasziw-Donner / Obuchowski SE correction. Promote only if the lower CI bound stays
   above −Δ. Δ set on domain grounds *before* seeing challenger results — never reverse-engineered.
   *(A non-significant p-value is insufficient power, NEVER evidence of equivalence.)*
- Report the **ICC + DEFF** alongside every promotion so the reader sees the honest variance.

**Safe-promotion MACHINERY (no live traffic):**
- **Config-as-immutable-artifact + pointer-swap.** Every config is an immutable versioned artifact; mutable
  labels `@champion` / `@challenger` / `@fallback` *point* at versions. Promotion & rollback = **pointer
  swaps**, not redeployments. **Semver signals validation burden** (patch=param tweak → cheap gates only;
  minor/major → the full statistical gate). We already fingerprint (config × GT-version × data); the new
  parts are the label pointers + retention discipline.
- **Shadow = dry-run over the full corpus** (champion writes production, challenger writes a shadow
  partition/tagged column; both scored on the holdout before any swap) — mechanically our full re-ingest.
- **Atomic Postgres blue/green view swap** for the actuation, matching DB-is-working-store.
- **N-cycle fallback retention** — keep the prior champion as `@fallback` for a fixed number of re-ingest
  cycles; **never delete the prior artifact until the stability window closes**; rollback = re-run the swap.

**DRIFT / reality checks — cheap, batch-event, halt-and-hold (a solo operator can automate ALL of these;
the human only *adjudicates* a fired alarm, never has to fire it):**
- Schema/contract assertions (reject on missing field / out-of-type / out-of-bounds param).
- **Plausibility-gate violations** (`gross_bell_to_bell` outside 240–510) as a hard count.
- **Paired KS test (p-trigger, localized spikes) AND 1st Wasserstein distance (score-unit threshold, global
  magnitude)** on the score distribution and on times-per-page — both, because they catch different shapes.
- **Decision-mix (send/review/suppress) pp-delta** vs. baseline — the cheapest, most directly meaningful
  alarm (it's what the config change is *trying* to move).
- **Input-drift guards** (CMS-vendor mix, capture-success rate) flag "the corpus itself changed" so config
  effects aren't confounded with corpus drift.

**Budget hardening:** the research is thin here (its cost concern is compute contention, not API $).
Transferable principle: **scale the statistical-gate cost by semver** (cheap gates always; expensive
bootstrap/NI only for minor/major changes). Genuine spend-cap methodology (the OpenRouter/Bright Data cap
side) is **not covered by this research and needs its own source** — the budget governor (`common/budget.py`,
REQ-051) remains our primary lever.

---

## 3. Gate relaxation & confidence calibration — DECISIONS

**Calibration is necessary but is NOT the safety guarantee** — it is an *input* to threshold-setting.

**"Instrument now, thresholds later" is mathematically FORCED (validated).** The **rule of three**: zero
observed errors in *n* audited items → 95% upper bound on the true error ≈ **3/n**. To *certify* a 1% error
ceiling for a gate you need ~**300** clean audited items **in that gate's accept region**; 0.5% needs ~600.
You physically cannot certify thresholds you have not accrued — deferring θ is the precondition the math
imposes, not timidity. Setting provisional thresholds sooner would be the **"Naive rule"** (tune θ until
validation error < α) — which has **no guarantee** and is explicitly warned against.

**Setting θ WITH a guarantee** (when the data exists): **SGR (Selection with Guaranteed Risk)**,
**Learn-Then-Test / RCPS / conformal risk control** — each treats a candidate θ as a hypothesis and applies
a multiple-testing correction so the certificate is valid. **Certify the WORST SLICE, not the mean.**

**Selective prediction framing** (this *is* confidence-escalating-auto): the **risk-coverage curve**
(selective risk = error among auto-accepted, vs. coverage = fraction auto-accepted) is the object we reason
about per gate — "how much human time saved at what error cost." Prefer **confidence thresholds + conformal
certificates** (simple, auditable) over learned deferral (only worth it if the human is itself noisy AND we
have logged human decisions to model).

**DECIDED SPEC — the calibration-log "meter" (start NOW), a certifiable shadow-mode schema.** Logging a bare
`(proxy, override)` pair is not enough to yield a certificate later. Per human gate action, log:
- gate id, item id;
- the **continuous confidence proxy VALUE** (not a bucket — you must sweep θ post-hoc): gate@5 combiner
  `sort_score`/tier; gate@6 `n_send`/`n_verified`; gate@7 council agreement / `n_unresolved`;
- the **human's final decision** (accept / reject / modified) — the ground-truth label for that item;
- a **binary agreement/error flag** (did the human match what auto *would* have done);
- **slice keys** (state, capture path text-vs-vision, batch type, run_kind, school level) — you certify the
  worst slice, and cannot reconstruct slices you didn't log;
- a **timestamp** (for later sequential/drift monitors);
- **whether the human saw the confidence** — because an unbiased error estimate needs a **blinded**
  subsample (showing the proxy triggers automation bias and contaminates the estimate).

**DECIDED — the methodology to relax a specific gate** (per-gate, lightweight for a solo project): frame the
false-accept harm + risk target α/δ + operating domain → calibrate in the accept tail per slice → certify θ
with a proper method (not Naive) reporting the worst-slice bound → **shadow then canary** → **monitor with a
pre-committed automatic re-escalation** (CUSUM / Page-Hinkley on audited error + calibration; PSI/KL/KS
drift; an error budget that flips the gate back to manual). **"A relaxed gate without an automatic rollback
path is not safe to relax."** (YouTube 2020 + Meta both over-removed when they leaned on automation and had
to re-add human tiers — the empirical case for pre-committed re-escalation.)

**Ordering constraint (unchanged, reinforced):** gate@8's calibrated confidence gate must exist before the
supervision gates (6/7) relax — it is the last backstop before the mechanical Stage-9 LCT write.

---

## 4. The build sequence (decided)

Re-ordered by mission-value under the commandments — **not** "#200 then #209":

- **Phase 0 (now, cheap, forward-accruing):** recall-floor fix (**#208**: one canonical constant + *enforce*
  at the re-ingest actuation point, not just report) + stand up the **calibration-log meter** with the
  certifiable schema above. Every day the meter isn't running is calibration data we can never recover
  (the #108 facet-accrual lesson, now with rule-of-three arithmetic behind it).
- **Phase 1 (the reframed priority):** the **exploration quota** — fixes a *current* measurement blind spot,
  not just a future risk; highest value across both epics.
- **Phase 2:** the **group-aware non-inferiority promotion gate** + **pointer-swap safe-promotion** —
  buildable now, upgrades the `frontier`/tuning-ledger we already have, needed the moment auto-tuning starts.
- **Deferred with the stages:** drift battery (needs a baseline), Stage-9 write-boundary assertions (needs
  Stage 9), gate-transition *thresholds* (blocked on accrued calibration data + Stage 8).

**#200's dev-time items** (DB-free guard, pre-push, property/mutation tests) stay valuable + cheap — do them
opportunistically — but they are lubricant, off the mission-critical path commandments 1–2 define.

**Cross-cutting fix forced by §0:** every scoring measured-pass must evaluate against the exploration cohort
(new #209 sub-task; retroactively touches #108's re-verification).

---

## 5. What the research did NOT settle (open, for the transition-governance plan)
- The concrete per-gate risk targets (α/δ) and Δ non-inferiority margins — **deferred until the calibration
  meter accrues the data** (rule of three). These are the policy half explicitly blocked in #209.
- OpenRouter/Bright Data spend-cap methodology under full-auto — not covered; needs its own source.
- Whether/when the *structural* gates (1/5/8) ever relax — commandment reality ("as automated as tolerable")
  pushes toward yes-with-confidence, but that decision waits on the meter's evidence.
