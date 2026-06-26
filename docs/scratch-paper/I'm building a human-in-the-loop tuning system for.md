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

