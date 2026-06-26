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

