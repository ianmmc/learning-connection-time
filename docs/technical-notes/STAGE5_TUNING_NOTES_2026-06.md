# Stage 5 — tuning-system research notes (saved design conversations)

> **Status: RESEARCH PROVENANCE** — two saved research conversations (Perplexity, citation-backed) that
> informed the Stage-5 human-in-the-loop tuning loop (REQ-095 ledger / REQ-096 advisory frontier / REQ-097
> drift detector). Migrated + merged 2026-06-27 from the retired `docs/scratch-paper/`. This is the
> *process that got us here*, not the design — the built design lives in `STAGE5_FILTER_DESIGN_2026-06.md`
> (the tuning loop / harness / frontier / ledger). Kept for the methods + citations if we revisit tuning
> (esp. the scaling questions: hierarchical/partial-pooling shrinkage and FDR-controlled drift across
> thousands of per-vendor/per-state streams).

- **Part A** — initial system (12 groups): drift detection at small n, threshold optimization under a hard
  recall floor (Pareto frontier), guarding against overfitting (leave-one-group-out CV).
- **Part B** — follow-up: scaling 12 → ~17,000 groups (districts) nested in states + CMS-vendor clusters,
  where most groups have few/zero labels permanently — empirical-Bayes shrinkage, FDR-controlled drift,
  which grouping level a knob belongs at (variance-components / ICC).

---

## Part A — initial tuning-system research (12 groups)

<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# I'm building a human-in-the-loop tuning system for a deterministic text classifier (keyword + threshold based, no ML model). I have a small but growing labeled dataset (currently ~150 examples across 12 groups, will grow batch by batch). I tune scoring thresholds to maximize precision subject to a hard recall floor (~98%). I want: (1) a 'drift detector' that alerts when newly-added labeled data degrades my current config's performance enough to warrant retuning — what statistical tests or control-chart methods suit a small, incrementally-growing labeled set without being noisy at small n? (2) Best practices for threshold optimization with a hard recall constraint and a Pareto frontier I inspect manually — grid/coordinate search vs Bayesian optimization (Optuna/scikit-optimize), and at what dimensionality Bayesian starts to win. (3) How to guard against overfitting thresholds to a small dataset — is leave-one-group-out / k-fold cross-validation across the 12 groups the right move? Cite concrete methods and libraries.

Good, I have sufficient research to give a comprehensive, well-structured answer. Let me compose it now.

This is a well-scoped engineering question with three distinct sub-problems. Here's a precise answer to each.

***

## 1. Drift Detection for an Incrementally-Growing Labeled Set

Your core challenge is distinguishing real performance degradation from sampling noise at small $n$. Three methods compose well for this use case.

**Bernoulli CUSUM on recall and precision separately.** CUSUM accumulates deviations from a target value and is far more sensitive to small sustained shifts than a Shewhart p-chart, detecting a 1σ mean shift roughly 4× faster. For a hard recall floor of 98%, treat each labeled example as a Bernoulli trial (recalled = 1, missed = 0) and plot the lower CUSUM statistic $C^-$ against your 0.98 target. The two tuning parameters are $k$ (reference value, typically set halfway between in-control and the minimum tolerable proportion) and $h$ (decision threshold). A reasonable initialization for a binary proportion CUSUM is $k = (p_0 + p_1)/2$ and $h$ calibrated to your acceptable false-alarm rate via average run length (ARL) tables. The key practical virtue: CUSUM signals only accumulate evidence — a single new batch with 2–3 extra misses won't trip it.[^1_1][^1_2][^1_3]

**Wilson score confidence intervals as a pre-filter.** Before running CUSUM, wrap each metric in a Wilson score interval rather than a Wald interval. Wilson CIs stay within $[0,1]$, maintain accurate coverage even at extreme proportions (like 0.98), and remain valid at small $n$. At 150 examples, your 95% Wilson CI for recall will be roughly ±3–4 pp — wide enough that you should suppress alerts unless the CUSUM statistic exceeds threshold *and* the lower Wilson bound also breaches your floor. This two-gate logic dramatically reduces false alarms at small $n$.[^1_4][^1_5]

**Fisher's exact test or McNemar's test as a batch-level gate.** When a new labeled batch arrives, you effectively want to know whether the new-config error rate on the batch differs from historical baseline. McNemar's test (available in `mlxtend`) is the right tool when you're comparing two classifier configurations on the *same* examples (old thresholds vs. new thresholds). It uses only the discordant cells of the contingency table, making it efficient at small $n$. Fisher's exact test is the safer choice when comparing error counts across batches of unequal size and is exact regardless of sample size. Use these as a "should I even bother retuning?" gate — only trigger the full optimization pipeline when the test is significant at, say, $p < 0.10$ (lenient, since you want to catch degradation, not prove it beyond doubt).[^1_6][^1_7][^1_8]

**What to avoid at small $n$.** The Page-Hinkley test (common in streaming concept-drift literature) assumes a Gaussian signal and can behave poorly on binary proportions. Similarly, KS/chi-squared tests in tools like Evidently AI and Alibi-Detect are designed for input distribution drift, not labeled-performance drift  — they're the wrong layer for your problem.[^1_9][^1_10][^1_11][^1_12]

**Practical library stack:**

- `mlxtend.evaluate.mcnemar` for batch comparison[^1_13]
- `statsmodels.stats.proportion.proportion_confint(method='wilson')` for CI tracking
- Roll a simple CUSUM in NumPy — it's a 10-line function; no need for a library

***

## 2. Threshold Optimization with a Hard Recall Constraint

**Grid/coordinate search at low dimensionality (≤ 5 thresholds).** With 12 groups and thresholds you're probably tuning per-group or per-feature-cluster, not per-example. If you have ≤ 5 free thresholds, grid search over a coarse grid + a fine zoom around the Pareto frontier is fully tractable and has the major advantage of producing a complete, inspectable picture of the precision–recall tradeoff surface. Coordinate descent (cycling through one threshold at a time while holding others fixed) is a good middle ground — it scales linearly with dimensionality, not exponentially, and converges quickly when thresholds are relatively independent.[^1_14]

**Bayesian optimization starts winning at ~6+ dimensions.** The general rule of thumb is that Bayesian optimization (BO) outperforms grid and random search once the search space is high-dimensional enough that exhaustive coverage becomes computationally expensive. In practice this threshold is roughly 6–10 continuous parameters; below that, a well-designed grid or coordinate search is faster and equally good. At 12 groups with one threshold each, you're at 12 dimensions — BO is appropriate.[^1_15][^1_16]

**Constrained BO in Optuna for the recall floor.** Optuna's `TPESampler` natively supports constrained optimization via `constraints_func` since v3.0. You encode the recall floor as an inequality constraint $(\text{recall} - 0.98 \leq 0)$, maximize precision as the objective, and get a feasibility-aware Pareto frontier. The newer **c-TPE** sampler (`optunahub` package `samplers/ctpe`) is the published IJCAI'23 approach specifically designed for constrained HPO and handles inequality constraints more rigorously than the base TPE. For multi-objective inspection (you want to see the full precision–recall Pareto curve, not just the constrained optimum), use `optuna.create_study(directions=["maximize", "maximize"])` with MOTPE and then filter post-hoc for runs satisfying recall ≥ 0.98.[^1_17][^1_18][^1_19][^1_20]

```python
import optuna

def objective(trial):
    # One threshold per group, 12 dimensions
    thresholds = [trial.suggest_float(f"t_{i}", 0.0, 1.0) for i in range(12)]
    precision, recall = evaluate_config(thresholds, labeled_data)
    # Store constraint for TPE
    trial.set_user_attr("recall_constraint", recall - 0.98)
    return precision  # maximize

def constraints(trial):
    return (trial.user_attrs["recall_constraint"],)  # must be ≤ 0 to be feasible

sampler = optuna.samplers.TPESampler(constraints_func=constraints)
study = optuna.create_study(direction="maximize", sampler=sampler)
study.optimize(objective, n_trials=300)
```

**Manual Pareto inspection tip.** Because your objective function is cheap (no model training, just scoring a labeled set), you can afford 500–1000 trials easily. Log all trials and use `optuna.visualization.plot_pareto_front` to inspect the feasible frontier. The human-in-the-loop step is choosing which Pareto point to deploy, not just accepting the algorithm's optimum — which is the right instinct given your hard recall floor.

***

## 3. Guarding Against Threshold Overfitting

**Yes — Leave-One-Group-Out (LOGO) is the correct choice here**, but with an important framing: you're not cross-validating to select a model, you're using it to estimate how much your tuned thresholds will *generalize* when new groups (or new examples within existing groups) are added.

`sklearn.model_selection.LeaveOneGroupOut`  gives you 12 folds, each trained on 11 groups' examples and evaluated on the held-out group. Report the variance of recall and precision across folds — high variance signals that your thresholds are over-indexed on specific groups' label distributions.[^1_21]

**Complementary: bootstrap stability analysis on the thresholds themselves.** Resample your 150 examples with replacement 200–500 times and run your optimizer each time. Report the coefficient of variation (CV) of each tuned threshold across resamples. If a threshold has CV > 0.3, it's poorly determined — that's a signal to either widen its effective range, add regularization (e.g., a soft prior toward a default), or flag it as needing more labeled examples in that group before trusting it. This is more informative than cross-validated accuracy alone because it tells you *which dimensions* of your config are fragile.[^1_22]

**Threshold regularization strategies:**

- **Soft floor:** add a penalty to the objective for thresholds that deviate far from a reasonable default (e.g., `penalty = λ * sum((t_i - t_default)²)`). This discourages the optimizer from chasing precision gains driven by overfitting to a handful of labeled examples.
- **Minimum group support:** refuse to tune a per-group threshold unless that group has at least $k$ labeled examples (e.g., $k = 10$). For groups below threshold, fall back to the global default. This is the pragmatic guard against small-group overfitting.
- **Nested CV:** outer LOGO loop evaluates generalization; inner loop (e.g., 5-fold on the 11 training groups) tunes thresholds. This is the gold standard but with 150 total examples and 12 groups, you may have too few examples per inner fold for reliable precision estimates — use with awareness of that limitation.[^1_23][^1_24]

**Library pointers:**

- `sklearn.model_selection.LeaveOneGroupOut`, `GroupKFold`[^1_25][^1_21]
- `scipy.stats.bootstrap` for threshold stability resampling
- `mlxtend.evaluate.bootstrap` as an alternative

***

## Decision Rules Summary

| Condition | Recommended approach |
| :-- | :-- |
| ≤ 5 thresholds | Coordinate descent or fine grid search |
| 6–12 thresholds | Optuna TPE with `constraints_func` (recall floor) |
| New batch arrives | Wilson CI + CUSUM gate; McNemar/Fisher to confirm |
| Threshold CV > 0.3 | Insufficient labeled support in that group; regularize or hold fixed |
| LOGO recall variance > 3 pp | Thresholds are overfit; collect more balanced data before retuning |

The two-gate drift detector (Wilson CI lower bound + CUSUM accumulation) is particularly well-suited to your incremental regime because it prevents the system from crying wolf at small $n$ while still catching sustained degradation after a few batches accumulate evidence.
<span style="display:none">[^1_26][^1_27][^1_28][^1_29][^1_30][^1_31][^1_32][^1_33][^1_34][^1_35][^1_36][^1_37][^1_38][^1_39][^1_40][^1_41][^1_42][^1_43][^1_44][^1_45][^1_46][^1_47][^1_48][^1_49][^1_50][^1_51][^1_52][^1_53][^1_54][^1_55][^1_56][^1_57][^1_58][^1_59][^1_60][^1_61][^1_62][^1_63][^1_64][^1_65][^1_66][^1_67][^1_68][^1_69][^1_70][^1_71][^1_72][^1_73][^1_74][^1_75][^1_76][^1_77][^1_78][^1_79][^1_80][^1_81][^1_82][^1_83][^1_84][^1_85][^1_86][^1_87][^1_88][^1_89][^1_90]</span>

<div align="center">⁂</div>

[^1_1]: https://www.jmp.com/en/statistics-knowledge-portal/quality-and-reliability-methods/control-charts/cusum-and-ewma-control-charts

[^1_2]: https://www.scribd.com/document/934500662/A-CUSUM-Chart-for-Monitoring-a-Proportion-When-Inspecting-Continuously

[^1_3]: https://qualitysafety.bmj.com/content/qhc/26/11/919.full.pdf

[^1_4]: https://www.youtube.com/watch?v=WMb4k3OrZf8

[^1_5]: https://stackoverflow.com/a/41168278

[^1_6]: https://medium.com/data-science/mcnemars-test-to-evaluate-machine-learning-classifiers-with-python-9f26191e1a6b

[^1_7]: https://machinelearningmastery.com/mcnemars-test-for-machine-learning/

[^1_8]: https://www.youtube.com/watch?v=nzznkiW8ulk

[^1_9]: https://dl.acm.org/doi/10.1016/j.ins.2016.03.034

[^1_10]: https://www.sciencedirect.com/science/article/pii/S1051200426004434

[^1_11]: https://arxiv.org/abs/2404.18673

[^1_12]: https://medium.com/@tanish.kandivlikar1412/comprehensive-comparison-of-ml-model-monitoring-tools-evidently-ai-alibi-detect-nannyml-a016d7dd8219

[^1_13]: https://rasbt.github.io/mlxtend/user_guide/evaluate/mcnemar/

[^1_14]: https://stackoverflow.com/questions/55849512/gridsearchcv-vs-bayesian-optimization

[^1_15]: https://towardsdatascience.com/grid-search-vs-random-search-vs-bayesian-optimization-2e68f57c3c46/

[^1_16]: https://www.linkedin.com/posts/avi-chawla_4-7xfasterhyperparametersearchformodel-activity-7384178373998206976-wXCX

[^1_17]: https://github.com/optuna/optuna/discussions/3863

[^1_18]: https://hub.optuna.org/samplers/ctpe/

[^1_19]: https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/002_multi_objective.html

[^1_20]: https://github.com/optuna/optuna/discussions/5259

[^1_21]: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.LeaveOneGroupOut.html

[^1_22]: https://metricgate.com/docs/instability-analysis-trees

[^1_23]: https://www.ncbi.nlm.nih.gov/books/NBK583970/

[^1_24]: https://arxiv.org/pdf/1905.12787.pdf

[^1_25]: https://scikit-learn.org/stable/modules/cross_validation.html

[^1_26]: https://www.kdd.org/kdd2016/papers/files/rpp0427-dos-reisA.pdf

[^1_27]: https://www.sciencedirect.com/science/article/abs/pii/S0360835204000683

[^1_28]: https://ceur-ws.org/Vol-3962/paper42.pdf

[^1_29]: https://onlinelibrary.wiley.com/doi/10.1002/qre.1678

[^1_30]: https://arxiv.org/html/2403.03576v3

[^1_31]: https://onlinelibrary.wiley.com/doi/full/10.1002/qre.3229

[^1_32]: https://d-nb.info/1262722780/34

[^1_33]: https://pure.uva.nl/ws/files/2418333/149586_10_1_.pdf

[^1_34]: https://sweet.ua.pt/gladys/Papers/GamaMedasCastilloRodriguesSBIA04.pdf

[^1_35]: https://pmc.ncbi.nlm.nih.gov/articles/PMC5739852/

[^1_36]: https://pdfs.semanticscholar.org/7625/0ec1a4fd4af5bebefbbb4805edd6471e57a4.pdf

[^1_37]: http://www.stat.umn.edu/hawkins/5031/Hawkins_Wu_2014.pdf

[^1_38]: https://myresearchspace.uws.ac.uk/ws/portalfiles/portal/63075556/2025_04_04_Mahmood_et_al_EWMA_final.pdf

[^1_39]: https://scientiairanica.sharif.edu/article_22060_f9c4204c41f3284405aee6ce6f8edbb0.pdf

[^1_40]: https://pure.rug.nl/ws/files/59390643/089120100561719.pdf

[^1_41]: https://scikit-optimize.github.io/stable/auto_examples/bayesian-optimization.html

[^1_42]: https://sebastianraschka.com/pdf/lecture-notes/stat479fs18/11_eval-algo_slides.pdf

[^1_43]: https://sandykuan.github.io/Szu-Chi/static/Statistical Testing for Comparing Machine Learning Algorithms.pdf

[^1_44]: https://www.cs.ubc.ca/labs/lci/robuds/docs/McCann - Statistical Tests for Comparing Classifiers.pdf

[^1_45]: https://sebastianraschka.com/pdf/lecture-notes/stat451fs20/11-eval4-algo__notes.pdf

[^1_46]: https://courses.grainger.illinois.edu/cs446/sp2015/Slides/Lecture09.pdf

[^1_47]: http://ethesis.nitrkl.ac.in/4642/1/109CS0172.pdf

[^1_48]: https://www.jmlr.org/papers/volume7/demsar06a/demsar06a.pdf

[^1_49]: https://www.scribd.com/document/225952583/9788132210375-c2

[^1_50]: https://blog.stata.com/2025/04/22/approximate-statistical-tests-for-comparing-binary-classifier-error-rates-using-h2oml/

[^1_51]: https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html

[^1_52]: https://www.cs.cmu.edu/afs/cs/Web/People/awm/tutorials/overfit10.pdf

[^1_53]: https://people.csail.mit.edu/romer/papers/CrossVal_SDM08.pdf

[^1_54]: https://arxiv.org/html/2606.09889v1

[^1_55]: https://dionysus.psych.wisc.edu/iaml_2020/unit-04.html

[^1_56]: https://github.com/optuna/optuna/issues/5291

[^1_57]: https://www.cs.tau.ac.il/~nin/Courses/NC05/pr_l13.pdf

[^1_58]: https://hub.optuna.org/optuna_versions/4.5.0/

[^1_59]: https://pmc.ncbi.nlm.nih.gov/articles/PMC12612969/table/tbl1/

[^1_60]: https://www.mwsug.org/proceedings/2008/pharma/MWSUG-2008-P08.pdf

[^1_61]: https://github.com/jacobgil/confidenceinterval/blob/main/README.md

[^1_62]: https://cran.r-project.org/web/packages/cusum/vignettes/gscusum.html

[^1_63]: https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval

[^1_64]: https://citeseerx.ist.psu.edu/document?repid=rep1\&type=pdf\&doi=881709dda9549e22748170af3c7a6f65f4dfbfac

[^1_65]: https://arxiv.org/ftp/arxiv/papers/2309/2309.14621.pdf

[^1_66]: https://ww2.amstat.org/meetings/proceedings/2012/data/assets/pdf/304331_72943.pdf

[^1_67]: https://pmc.ncbi.nlm.nih.gov/articles/PMC13051258/

[^1_68]: https://userweb.ucs.louisiana.edu/~kxk4695/com_stat_bin_07.pdf

[^1_69]: https://arxiv.org/html/2606.26422v1

[^1_70]: https://web.cs.ndsu.nodak.edu/~siludwig/Publish/papers/CEC2021.pdf

[^1_71]: https://www.youtube.com/watch?v=dmda6k0fLyI

[^1_72]: https://www.diva-portal.org/smash/get/diva2:1867280/FULLTEXT01.pdf

[^1_73]: https://medium.com/@pacosun/the-tuners-toolbox-grid-search-random-search-and-bayesian-optimization-unpacked-648abd7a8ff6

[^1_74]: https://bigdatarepublic.nl/articles/using-bayesian-optimization-to-reduce-the-time-spent-on-hyperparameter-tuning/

[^1_75]: https://pdeep.xyz/documents/Bayesian_Optimization_Report.pdf

[^1_76]: https://en.wikipedia.org/wiki/Hyperparameter_optimization

[^1_77]: https://keylabs.ai/blog/hyperparameter-tuning-grid-search-random-search-and-bayesian-optimization/

[^1_78]: https://businessanalyticsinstitute.com/grid-search-vs-bayesian-optimization-hyperparameter-tuning/

[^1_79]: https://uu.diva-portal.org/smash/get/diva2:443740/FULLTEXT01.pdf

[^1_80]: https://www.fuzzylabs.ai/blog-post/evidently-vs-alibi-detect-comparing-model-monitoring-tools

[^1_81]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4784504/

[^1_82]: https://docs.evidentlyai.com/metrics/explainer_drift

[^1_83]: https://vaclab.unc.edu/publication/compstats_2019_yu/compstats_2019_yu.pdf

[^1_84]: https://arxiv.org/pdf/2606.01566.pdf

[^1_85]: https://www.youtube.com/watch?v=GCaznqhO1Hk

[^1_86]: http://compdiag.molgen.mpg.de/ngfn/docs/2004/mar/resampling.pdf

[^1_87]: https://deploy.seldon.io/en/v2.2/contents/product-tour/data-drift-detection/index.html

[^1_88]: https://irjs.org/api/uploads/manuscript/manuscript_1760985595.pdf

[^1_89]: http://arxiv.org/pdf/2405.09511.pdf

[^1_90]: https://en.wikipedia.org/wiki/Bootstrapping_(statistics)



---

## Part B — follow-up: scaling to ~17,000 groups

<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Follow-up on a human-in-the-loop threshold-tuning system for a deterministic classifier. It will scale from 12 groups to ~17,000 groups (US school districts) nested in ~50 states and a handful of CMS-vendor clusters, where MOST groups will have few or zero labeled examples permanently. Questions: (1) When per-group thresholds are mostly unsupported, what's the right hierarchical/partial-pooling or empirical-Bayes shrinkage structure — global default → CMS-cluster → state → per-group-only-where-supported? Concrete methods/libraries. (2) For drift detection across thousands of simultaneous metric streams (per-CMS, per-state), how do I control false-discovery rate so I'm not flooded with spurious 'retune' alerts — Benjamini-Hochberg over per-stream CUSUM/Wilson signals, or a hierarchical drift detector? (3) Is there a principled way to decide WHICH grouping level (vendor vs state vs district) a given knob should live at, driven by where the labeled variance actually concentrates (e.g., variance-components / ICC analysis)? Cite concrete methods and libraries.

Good, I have strong material across all three questions. Let me compose the answer.

This is a legitimately hard scale-up problem — the 12-group answers from before break in three specific ways at 17K groups: the shrinkage structure needs to be nested and data-adaptive, the drift detection becomes a multiple-testing problem, and the "which level" question requires an empirical decomposition rather than intuition. Here's a precise answer to each.

***

## 1. Hierarchical Shrinkage for Mostly-Unsupported Groups

The intuition is correct: you want a cascade `global → CMS-vendor → state → district`, where each level shrinks toward its parent in proportion to how little local data you have. The formal machinery is **hierarchical partial pooling** (Bayesian multilevel models), which is exactly what Stan's repeated-binary-trials case study demonstrates.[^1]

### The model structure

Model each district's threshold $\theta_j$ as drawn from its state distribution, which is drawn from its CMS-cluster distribution, which is drawn from a global prior:

$$
\theta_j \sim \text{Normal}(\mu_{s[j]},\ \sigma_s)
$$

$$
\mu_s \sim \text{Normal}(\mu_{c[s]},\ \sigma_c)
$$

$$
\mu_c \sim \text{Normal}(\mu_{\text{global}},\ \sigma_{\text{global}})
$$

The variance hyperparameters $\sigma_s, \sigma_c, \sigma_{\text{global}}$ are themselves estimated from data. This is the key property: when a state has many labeled districts, $\sigma_s$ will be estimated with confidence and state-level shrinkage will be strong. When it has few, the posterior on $\sigma_s$ will be wide and the model will fall back further toward CMS-cluster or global.[^2]

**Shrinkage factor.** For a district with $n_j$ labeled examples, the effective shrinkage toward its state mean is approximately $\kappa_j \approx \sigma_s^2 / (\sigma_s^2 + \sigma_j^2/n_j)$, where $\sigma_j^2$ is within-district variance. Districts with $n_j = 0$ get $\kappa_j = 0$ — they receive the state posterior mean as their threshold, which is itself shrunk toward the CMS-cluster mean. This is exactly the behavior you want.[^3]

### Lightweight vs. full Bayes

| Approach | When to use | Library |
| :-- | :-- | :-- |
| **Empirical Bayes (closed-form Beta-Binomial)** | Fast, no MCMC; works when the likelihood is binary (recall hit/miss) | `scipy.stats`, `statsmodels` |
| **Bambi** (high-level PyMC wrapper) | Mixed-effects models with R-style formula syntax, medium complexity | `pip install bambi` [^4] |
| **PyMC directly** | Full 3-level nesting, custom priors, posterior predictive checks | `pymc` [^5][^6] |
| **Stan via CmdStanPy** | Fastest MCMC for large hierarchical models; best for 17K groups | `cmdstanpy` [^1] |

For 17K districts, full MCMC on every retuning cycle will be expensive. The practical path is **empirical Bayes**: estimate the hyperparameters $(\mu_c, \sigma_c, \mu_s, \sigma_s)$ by maximizing the marginal likelihood (or method-of-moments), then use those as fixed priors to get closed-form posterior means per district. `statsmodels` `MixedLM` can handle the two-level case; for three levels, use Bambi or a custom PyMC model.[^7]

### Districts with zero labeled examples

For a zero-support district, the posterior mean threshold is simply its state's posterior mean, with a credible interval derived entirely from the state-level hyperparameters. Critically, you should **not expose these thresholds to the Optuna optimizer** — they're not free parameters during tuning. Only districts with enough local data (e.g., $n_j \geq 10$) get a district-specific offset; all others inherit the state estimate. This separates the "estimation" problem (hierarchical model) from the "optimization" problem (Optuna).

***

## 2. FDR Control Across Thousands of Simultaneous Drift Streams

At 17K per-district streams plus ~50 state streams plus a handful of CMS streams, naively running CUSUM/Wilson at each level and alerting on any exceedance will flood you with false positives. This is a multiple-testing problem with a hierarchical structure, and there are two principled solutions.

### Option A: Online FDR control (best for your use case)

Standard Benjamini-Hochberg assumes all p-values are available simultaneously, but your labeled batches arrive over time — so you need **online FDR**, where hypotheses arrive sequentially and you must decide whether to reject each one as it arrives without looking at future data. The key algorithms are:[^8]

- **LORD** (Levels based On Recent Discovery): adjusts the per-test significance level based on the "wealth" accumulated from past discoveries. Maintains FDR control under independence and positive dependence.[^9]
- **ADDIS** (Adaptive Discarding): extends LORD to discard trivially non-significant tests early, improving power when most streams are in-control (which is your common case).[^10][^9]
- **SAFFRON**: adaptive variant that estimates the fraction of true nulls online, further improving power.

The `online-fdr` Python package implements all of these (`pip install online-fdr`) with a clean `test_one(p_value)` interface per arriving batch. The R `onlineFDR` Bioconductor package is the canonical reference implementation.[^11][^10][^9]

```python
from online_fdr.p_values import Addis

detector = Addis(alpha=0.05, wealth=0.025, lambda_=0.25, tau=0.5)
# Each time a new labeled batch arrives for stream k:
p_val = compute_drift_pvalue(stream_k_data)  # Fisher exact or CUSUM p-value
should_alert = detector.test_one(p_val)
```


### Option B: Hierarchical (p-filter) for structured alerts

If you want to simultaneously control FDR at *multiple levels* — e.g., "alert at the state level only if enough districts in that state signal drift" — use the **p-filter** (Barber \& Ramdas, JRSS-B 2017). It takes p-values and $M \geq 1$ partitions of the hypothesis set and provably controls group FDR simultaneously for all partitions. This is the principled way to say "flag Texas for retuning only if ≥ 5 Texas districts exceed the district-level threshold." The R `structSSI` package implements `hFDR.adjust` for the Benjamini-Yekutieli hierarchical FDR procedure.[^12][^13][^14]

### Recommended two-layer architecture

1. **District layer**: ADDIS online FDR over the per-district CUSUM p-values as batches arrive. This handles the 17K streams sequentially.
2. **State/CMS layer**: Aggregate district-level rejections per state; use a simple Bonferroni or BH correction over the ~50 state-level tests (small enough for batch BH). Flag a state for retuning when ≥ $k$ of its districts are flagged.
3. **Human gate**: Only the state/CMS-level alerts reach the human-in-the-loop — districts trigger automated re-estimation of state hyperparameters, not manual review.

The key insight from  is that sequential FDR procedures control both FDR *and* FNR simultaneously, which matters for your recall floor: you want to catch real degradation (FNR control) just as much as you want to suppress false alarms (FDR control).[^15]

***

## 3. Variance-Components Analysis to Assign Parameters to Levels

This is the most principled part of the design. The question "should this knob live at the vendor level or the state level?" is equivalent to asking "does most of its variance concentrate between vendors or between states within vendors?" That's exactly what **variance-component / ICC analysis** answers.

### The method: nested ANOVA / VPC decomposition

Fit a null variance-components model (no fixed effects, only random effects for each grouping level) to your labeled performance data. The **Variance Partition Coefficient (VPC)** at each level is the fraction of total variance attributable to that level:[^16]

$$
\text{VPC}_{\text{state}} = \frac{\sigma_{\text{state}}^2}{\sigma_{\text{global}}^2 + \sigma_{\text{CMS}}^2 + \sigma_{\text{state}}^2 + \sigma_{\text{district}}^2}
$$

If $\text{VPC}_{\text{CMS}} \approx 0.60$ and $\text{VPC}_{\text{state}} \approx 0.05$, the knob belongs at the CMS-cluster level — states within a vendor behave similarly. If $\text{VPC}_{\text{state}} \approx 0.40$, you need state-level parameters.

**ICC interpretation heuristics:** ICC < 0.1 means the grouping level explains almost nothing — no point adding a parameter there. ICC > 0.3 suggests meaningful clustering — a level-specific parameter is worth estimating. ICC > 0.7 means nearly all variance is between groups — a single group-level parameter suffices and within-group data adds little.[^17]

### Python implementation

```python
import pingouin as pg
import pandas as pd

# labeled_df: one row per labeled example
# columns: precision_score, recall_score, cms_vendor, state, district_id

# Two-level ICC: how much variance is between states?
icc_state = pg.intraclass_corr(
    data=labeled_df,
    targets='district_id',
    raters='state',      # grouping factor
    ratings='precision_score'
)

# For nested structure, use statsmodels MixedLM or bambi
import bambi as bmb
model = bmb.Model(
    "precision_score ~ 1 + (1|cms_vendor) + (1|cms_vendor:state) + (1|cms_vendor:state:district_id)",
    data=labeled_df
)
results = model.fit(draws=1000, chains=2)
# Inspect variance components in results summary
```

`pingouin.intraclass_corr` returns six ICC variants with F-statistics and 95% CIs. For the fully nested three-level case, use Bambi's crossed/nested random effects syntax or `statsmodels.MixedLM` with group-within-group structure.[^18][^4][^7]

### Decision rules from VPC

| VPC at level | Action |
| :-- | :-- |
| > 0.3 | Assign a free parameter at this level; tune it |
| 0.1 – 0.3 | Use as a covariate / offset, not a free threshold |
| < 0.1 | Pool fully; don't waste optimization budget here |

Run this analysis on whatever labeled data you have now (150 examples), and re-run it each time you accumulate a new batch — the VPC estimates will stabilize as coverage grows. This is your empirical basis for deciding the hierarchy structure rather than assuming it, and it will likely show that CMS-vendor membership explains far more variance than state, since curriculum/product decisions are vendor-driven rather than geography-driven.

***

## Integrated System Architecture

The three pieces compose cleanly:

1. **Estimation layer** (hierarchical model): produces posterior mean thresholds for all 17K districts, including zero-support ones. Re-run after each labeled batch.
2. **Detection layer** (ADDIS online FDR): flags streams where the current config's performance has degraded. Rolls up via BH at the state/CMS level.
3. **Scope layer** (VPC): determines which levels get free parameters in the next optimization run, and therefore the dimensionality Optuna sees. A finding that CMS explains 60% of variance means you have ~handful of free CMS-level thresholds plus state offsets only where VPC_state > 0.1 — keeping the optimization tractable.
<span style="display:none">[^19][^20][^21][^22][^23][^24][^25][^26][^27][^28][^29][^30][^31][^32][^33][^34][^35][^36][^37][^38][^39][^40][^41][^42][^43][^44][^45][^46][^47][^48][^49][^50][^51][^52][^53][^54][^55][^56][^57][^58][^59][^60]</span>

<div align="center">⁂</div>

[^1]: https://mc-stan.org/learn-stan/case-studies/pool-binary-trials.html

[^2]: https://mc-stan.org/docs/2_28/stan-users-guide/multilevel-regression-and-poststratification.html

[^3]: https://metricgate.com/docs/bayesian-hierarchical-poisson/

[^4]: https://bambinos.github.io/bambi/

[^5]: https://www.pymc.io/projects/examples/en/latest/case_studies/hierarchical_partial_pooling.html

[^6]: https://github.com/pymc-devs/pymc-examples/blob/main/examples/case_studies/hierarchical_partial_pooling.ipynb

[^7]: https://thestippe.github.io/statistics/bambi_multilevel

[^8]: https://pmc.ncbi.nlm.nih.gov/articles/PMC7615519/

[^9]: https://rdrr.io/github/dsrobertson/onlineFDR/man/

[^10]: https://github.com/OliverHennhoefer/online-fdr/blob/main/README.md

[^11]: https://bioconductor.statistik.tu-dortmund.de/packages/3.22/bioc/manuals/onlineFDR/man/onlineFDR.pdf

[^12]: https://cran.rstudio.org/web/packages/structSSI/structSSI.pdf

[^13]: https://academic.oup.com/jrsssb/article/79/4/1247/7040694

[^14]: https://rdrr.io/cran/structSSI/man/hFDR.adjust.html

[^15]: https://pmc.ncbi.nlm.nih.gov/articles/PMC7993061/

[^16]: https://pubmed.ncbi.nlm.nih.gov/32309962/

[^17]: https://mcpanalytics.ai/articles/intraclass-correlation-icc-practical-guide-for-data-driven-decisions

[^18]: https://pingouin-stats.org/build/html/generated/pingouin.intraclass_corr.html

[^19]: https://metricgate.com/docs/hierarchical-bayesian-models/

[^20]: https://www.youtube.com/watch?v=Jb9eklfbDyg

[^21]: https://openreview.net/pdf?id=FpP8BwJiX0

[^22]: https://vasishth.github.io/IntroBayesSMLP2021/slides/04HLMAdditionalNotesShrinkage.pdf

[^23]: https://projecteuclid.org/journals/electronic-journal-of-statistics/volume-17/issue-1/Intuitive-joint-priors-for-Bayesian-linear-multilevel-models--The/10.1214/23-EJS2136.pdf

[^24]: https://www.pymc.io/projects/docs/en/v3.11.4/pymc-examples/examples/generalized_linear_models/GLM-hierarchical.html

[^25]: https://sesen.ai/blog/hierarchical-bayesian-regression-pymc

[^26]: https://jrnold.github.io/bayesian_notes/shrinkage-and-hierarchical-models.html

[^27]: https://tesi.luiss.it/43547/1/781201_ROMANO_MARTINA.pdf

[^28]: https://metricgate.com/blogs/bayesian-hierarchical-models-explained/

[^29]: http://www.math.tau.ac.il/~yekutiel/papers/JASA FDR trees.pdf

[^30]: https://escholarship.org/uc/item/33s3r5nk

[^31]: https://arxiv.org/pdf/2105.10839.pdf

[^32]: https://www.youtube.com/watch?v=K8LQSvtjcEo

[^33]: https://scholarshare.temple.edu/server/api/core/bitstreams/335ba45e-9866-402d-8f08-1e291a64809c/content

[^34]: https://arxiv.org/pdf/2509.15444.pdf

[^35]: https://arxiv.org/abs/1612.04467

[^36]: https://pdfs.semanticscholar.org/7e4d/2b9f1ba787c799bdabf8ed10ddd820a64ba7.pdf

[^37]: https://web.njit.edu/~wguo/Lynch \& Guo_2016.pdf

[^38]: https://faculty.washington.edu/yenchic/21Sp_stat542/Lec11_FDR.pdf

[^39]: https://wenku.csdn.net/answer/94a88791b343485daba7eee650a1d79c

[^40]: https://rowannicholls.github.io/python/statistics/agreement/intraclass_correlation.html

[^41]: https://www.statology.org/intraclass-correlation-coefficient-python/

[^42]: https://kiaraacademy.com/intraclass-correlation-coefficient-in-python/

[^43]: https://keptune.ai/tools/icc-calculator

[^44]: https://gist.github.com/clane9/964c52650f41540c1ad21dad1f247e6f

[^45]: https://www.codecamp.ru/blog/intraclass-correlation-coefficient-python/

[^46]: https://stackoverflow.com/questions/40965579/intraclass-correlation-in-python-module

[^47]: https://scales.arabpsychology.com/stats/how-to-calculate-intraclass-correlation-coefficient-in-python/

[^48]: https://users.ssc.wisc.edu/~behansen/papers/er_16.pdf

[^49]: https://www.unige.ch/math/folks/sardy/Papers/smoothSJS.pdf

[^50]: https://ben-br.github.io/stat-460/assets/class-sheets/class-15.pdf

[^51]: https://www2.stat.duke.edu/~pdh10/Teaching/732/Notes/shrinkage.pdf

[^52]: http://arxiv.org/pdf/1402.0302.pdf

[^53]: https://nobel.web.unc.edu/wp-content/uploads/sites/13591/2025/12/James-Stein.pdf

[^54]: https://en.wikipedia.org/wiki/James–Stein_estimator

[^55]: https://www.math.fsu.edu/~kercheva/papers/JS_preprint.pdf

[^56]: https://pdfs.semanticscholar.org/a963/83fac15e6065325f32d609023de31f7a42c1.pdf

[^57]: https://theorempath.com/topics/shrinkage-estimation-james-stein

[^58]: http://www.stat.yale.edu/~hz68/680/BookAugust29-2011.pdf

[^59]: https://www.econometrics.blog/post/not-quite-the-james-stein-estimator/

[^60]: https://arxiv.org/pdf/1503.06910.pdf

