<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Standard ML canary/shadow deployment assumes high request volume so a 1% canary yields significance in days. My system re-scores a fixed corpus of ~940 labeled records offline and applies config changes via a full re-ingest — there's no request stream to split. What safe-promotion, champion-challenger, and auto-rollback patterns work for config-as-data changes at low volume / batch scale, where held-out cross-validation on correlated groups (n≈440, grouped by ~90 districts) is the only signal? How do people gate promotion and detect regression without online traffic?

Now I have a thorough picture. Let me compose the answer.

This is a well-posed and non-trivial MLOps problem that the standard literature doesn't fully address because it conflates "batch scoring" with "low-traffic inference." Here's a systematic treatment of each concern.

***

## The Core Reframe: Batch Config-as-Data ≠ Online Canary

Standard canary/shadow deployment is traffic-splitting over an *infinite incoming stream*, relying on the law of large numbers to accumulate significance over days. Your system has no stream — it has a *fixed, versioned corpus* that gets re-scored deterministically on each re-ingest. This means your entire evaluation signal lives in the delta between two full runs on the same labeled records. The correct analogy isn't A/B testing; it's **paired model comparison with grouped observations**, which has a mature (if quieter) literature.

***

## Champion-Challenger in a Batch Re-Score Context

The key shift is that "shadow" doesn't mean routing 1% of traffic — it means **running the challenger config against the full corpus in a dry-run mode, producing predictions but not writing them to the production index**. DataRobot's implementation (and the principle behind it) makes this explicit: only one model ever writes live predictions; the challenger receives the same inputs in parallel and its output is logged for comparison. For a re-ingest architecture you'd implement this as:[^1_1]

1. **Champion** runs its scheduled re-score and writes results to the production store as normal.
2. **Challenger** runs the same corpus through the new config and writes to a *shadow store* (a separate partition or a tagged column).
3. Both result sets are evaluated against your holdout labels before any promotion decision is made.

This is purely mechanical in an offline batch context — you literally run two pipelines on the same snapshot of records.[^1_2]

***

## Versioning: Treating Config as an Immutable Artifact

Config-as-data changes should be treated identically to model artifacts. The pattern that holds up well:[^1_3][^1_2]

- Every config change produces an **immutable, versioned artifact** (commit hash or monotonic integer). Never mutate in place.[^1_4]
- Your registry (even if it's just MLflow aliases or a pointer in a config store) uses **mutable environment labels** (`@champion`, `@challenger`) that point to immutable versions. Promotion and rollback are pointer swaps, not redeployments.[^1_3]
- Tag each version with the data snapshot hash and the evaluation metrics at registration time. This is what makes rollback meaningful — you can reproduce exactly what the champion produced on any past re-ingest.[^1_5][^1_2]
- Use **semantic versioning to signal change scope**: patch for parameter tweaks within the same scoring logic, minor for new field mappings or weight changes, major for structural scoring logic changes. This informs how much validation burden to apply at promotion.[^1_6][^1_7]

***

## Promotion Gates: What Passes and What Blocks

Because you have ~90 groups (districts), group-aware evaluation is both your constraint and your asset. The gate structure that works:[^1_8][^1_9]

### Gate 1 — Regression-free on held-out districts (LOGO CV)

With n≈440 records grouped into ~90 districts, **Leave-One-Group-Out cross-validation** (LOGO) is the appropriate evaluation scheme. Each fold holds out one district entirely; no records from the held-out district appear in "training" context. This prevents the group-leakage that would make a naive k-fold CV over-optimistic — ignoring that your data is clustered can cause you to miss significant effects or manufacture false improvements.[^1_10][^1_9][^1_8]

Your promotion criterion here is not "challenger beats champion" in aggregate — it's **no fold where the challenger degrades by more than a pre-specified tolerance Δ on the held-out district**. This is a guardrail, not an optimization target.

### Gate 2 — Paired statistical test on record-level disagrement

For aggregate metric comparison (where you're asking "is the challenger reliably different from the champion?"), **McNemar's exact test** is the right tool at this N. It tests only the disagreements between models — records where champion got it right and challenger wrong (b), vs. the reverse (c). This makes it a paired test, which is appropriate because both models see the same labeled records.[^1_11][^1_12]

- When b + c < 25, use the exact binomial form, not the chi-squared approximation[^1_11]
- The null is that models perform equivalently; you need to *reject* it in the right direction to promote, or *fail to reject* it to confirm equivalence (no degradation)

For regression/ranking tasks (as opposed to classification), substitute a **Wilcoxon signed-rank test on paired per-record errors**. This is non-parametric, handles small N without normality assumptions, and gives you effect size (r) alongside p-value.[^1_13][^1_14]

For grouped data where within-district correlation inflates standard tests, use a **block permutation test** that restricts permutations to within-group swaps. This preserves the group structure as the exchangeability unit and maintains correct Type I error even with small cluster counts; parametric mixed-effects models can have inflated Type I error at your cluster N.[^1_15][^1_16]

### Gate 3 — Equivalence testing for "no worse than"

A non-significant paired test is **not evidence of equivalence** — it's only evidence of insufficient power to detect a difference. If your promotion criterion is "challenger is not worse than champion," you need to flip the burden of proof with a **TOST (two one-sided tests)** procedure:[^1_17][^1_18]

- Pre-specify a smallest effect size of interest Δ (e.g., "no more than 2 pp degradation in district-level recall") *before* seeing challenger results
- Run two one-sided tests against +Δ and −Δ; if both reject at α, the difference is within the equivalence margin
- The critical discipline is that Δ must be set on domain grounds, not reverse-engineered from observed data[^1_18]

***

## Auto-Rollback Without Online Traffic

Since there's no production traffic to monitor, rollback triggers have to be batch-event-driven:[^1_2]

1. **Post-ingest validation assertion**: after each re-ingest writes to the production store, run a set of deterministic assertions on the output distribution (score distribution drift, null rates, out-of-range values, expected class proportions). If assertions fail, the pipeline should halt and repoint `@champion` to the previous immutable version — this is a pointer swap, not a rebuild.[^1_6][^1_3]
2. **Lagged label reconciliation**: if you have any mechanism for labels to update post-ingest (e.g., ground truth becomes available after scoring), schedule a **reconciliation job** that computes retro-accuracy against the current champion's last outputs. If accuracy falls below a sliding threshold, trigger a re-evaluation cycle and hold promotion.[^1_2]
3. **Canary over time, not over traffic**: since each re-ingest is a discrete event, you can implement a "canary over N runs" pattern — promote the challenger to `@champion` but **retain the previous champion as `@fallback`** for a fixed number of re-ingest cycles (e.g., 3 runs). Monitor divergence between current champion outputs and historical baselines on the stable subset of records. If divergence exceeds threshold, swap the `@champion` pointer back to `@fallback`.[^1_1][^1_6]

The invariant that makes this work: **never delete the previous immutable artifact until the new one has been stable for a defined number of re-ingest cycles**.[^1_6][^1_3]

***

## Practical Gate Checklist

| Gate | Criterion | Blocks promotion if… |
| :-- | :-- | :-- |
| Schema/contract | Output schema matches registered spec | Any field missing or out-of-type |
| LOGO-CV regression | Per-fold metric on held-out districts | Any fold degrades > Δ vs. champion fold |
| McNemar / Wilcoxon | Paired test on full holdout (n≈440) | Challenger is significantly *worse* (one-sided test at α=0.05) |
| TOST equivalence | Challenger not worse than Δ margin | 90% CI of difference extends beyond −Δ |
| Distribution assertions | Score/label distribution on re-ingest output | KS stat or proportion drift exceeds threshold |
| Temporal stability | 3-run window post-promotion | Metric degrades vs. pre-promotion baseline |

The block-permutation and LOGO approaches are specifically validated for small cluster counts; the standard recommendation is that even with N < 50 per arm or a small number of clusters, permutation tests control Type I error better than parametric alternatives. With ~90 districts as your group unit, you're in the range where this matters.[^1_19][^1_16]
<span style="display:none">[^1_100][^1_101][^1_20][^1_21][^1_22][^1_23][^1_24][^1_25][^1_26][^1_27][^1_28][^1_29][^1_30][^1_31][^1_32][^1_33][^1_34][^1_35][^1_36][^1_37][^1_38][^1_39][^1_40][^1_41][^1_42][^1_43][^1_44][^1_45][^1_46][^1_47][^1_48][^1_49][^1_50][^1_51][^1_52][^1_53][^1_54][^1_55][^1_56][^1_57][^1_58][^1_59][^1_60][^1_61][^1_62][^1_63][^1_64][^1_65][^1_66][^1_67][^1_68][^1_69][^1_70][^1_71][^1_72][^1_73][^1_74][^1_75][^1_76][^1_77][^1_78][^1_79][^1_80][^1_81][^1_82][^1_83][^1_84][^1_85][^1_86][^1_87][^1_88][^1_89][^1_90][^1_91][^1_92][^1_93][^1_94][^1_95][^1_96][^1_97][^1_98][^1_99]</span>

<div align="center">⁂</div>

[^1_1]: https://www.datarobot.com/blog/introducing-mlops-champion-challenger-models/

[^1_2]: https://mlpipex.com/blog/mlops-pipeline-best-practices

[^1_3]: https://datarekha.com/interview/mlops/model-registry-safely-promote-to-production/

[^1_4]: https://changegamer.ai/resources/prompt-management-and-versioning.md

[^1_5]: https://mljar.com/ai-prompts/ml-engineer/model-deployment/prompt-model-registry/

[^1_6]: https://www.youtube.com/watch?v=JvFHXhivrHE

[^1_7]: https://us.fitgap.com/stack-guides/implement-cross-model-semantic-versioning-and-compatibility-guarantees-for-safer-model-updates

[^1_8]: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.LeaveOneGroupOut.html

[^1_9]: https://sklearner.com/scikit-learn-leaveonegroupout/

[^1_10]: https://medium.com/swlh/an-quick-intro-to-block-permutations-and-bootstraps-for-analyzing-hierarchical-data-d219b319ef55

[^1_11]: https://rasbt.github.io/mlxtend/user_guide/evaluate/mcnemar/

[^1_12]: https://github.com/huggingface/evaluate/blob/main/comparisons/mcnemar/mcnemar.py

[^1_13]: https://pmc.ncbi.nlm.nih.gov/articles/PMC13028424/table/pone.0343262.t014/

[^1_14]: https://rcompanion.org/handbook/F_06.html

[^1_15]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4644991/

[^1_16]: https://pmc.ncbi.nlm.nih.gov/articles/PMC5507602/

[^1_17]: https://support.sas.com/resources/papers/proceedings20/4641-2020.pdf

[^1_18]: https://r-statistics.co/tools/equivalence-noninferiority-calculator.html

[^1_19]: https://pubmed.ncbi.nlm.nih.gov/32432805/

[^1_20]: https://metricgate.com/blogs/champion-challenger-model-testing/

[^1_21]: https://ubos.tech/champion‑challenger-validation-for-openclaws-ml‑adaptive-token‑bucket-retraining/

[^1_22]: https://ubos.tech/champion‑challenger-validation-in-openclaw-pipeline/

[^1_23]: https://resilient.safeintelligence.ai/p/deploying-machine-learning-models

[^1_24]: https://www.biorxiv.org/content/10.64898/2026.03.12.711429v1.full-text

[^1_25]: https://docs.validmind.com/notebooks/tutorials/model_validation/3-developing_challenger_model.html

[^1_26]: https://www.techinterview.org/post/3233468990/lld-model-serving/

[^1_27]: https://mljar.com/ai-prompts/ml-engineer/model-deployment/

[^1_28]: https://www.lendingiq.ai/agent-catalogue/sea/model-validation-ai/articles/usecase-0001

[^1_29]: https://medium.com/@artur.fejklowicz/zero-touch-ml-model-promotion-building-a-fully-automated-champion-challenger-pipeline-on-google-aa0bb5cfc854

[^1_30]: https://modelopdocs.atlassian.net/wiki/spaces/VDP/pages/12058682/Champion+Challenger+Model+Comparison

[^1_31]: https://launchdarkly.com/docs/eu-docs/home/ai-configs/offline-evaluations

[^1_32]: https://docs.pega.com/bundle/platform/page/platform/decision-management/promoting-challenger-model.html

[^1_33]: https://www.fico.com/blogs/benefits-championchallenger-testing-decision-management

[^1_34]: https://scikit-learn.org/stable/modules/cross_validation.html

[^1_35]: https://openreview.net/pdf/eb13bf94470c741981529b7cb7abb7439becaff4.pdf

[^1_36]: https://github.com/ShiuLab/ML-Pipeline/blob/master/Feature_Selection.py

[^1_37]: https://inria.github.io/scikit-learn-mooc/python_scripts/cross_validation_grouping.html

[^1_38]: https://stackoverflow.com/questions/51873145/nest-cross-validation-for-predictions-using-groups

[^1_39]: https://github.com/WheelockLab/MachineLearning_NetworkLevelAnalysis

[^1_40]: https://pub.towardsai.net/model-versioning-in-mlops-tracking-changes-ensuring-reproducibility-and-managing-production-b41ce0311a27

[^1_41]: https://learn.microsoft.com/sk-sk/dotnet/machine-learning/how-to-guides/train-machine-learning-model-cross-validation-ml-net

[^1_42]: https://stats.stackexchange.com/questions/589855/how-to-design-cross-validation-and-testing-scheme-when-n-is-small

[^1_43]: https://alan-turing-institute.github.io/Intro-to-transparent-ML-course/05-cross-val-bootstrap/cross-validation.html

[^1_44]: https://www.youtube.com/watch?v=EpK9pWZGjbE

[^1_45]: https://aws.amazon.com/blogs/architecture/field-notes-build-a-cross-validation-machine-learning-model-pipeline-at-scale-with-amazon-sagemaker/

[^1_46]: http://people.musc.edu/~bandyopd/bmtry704.09/Rosner_clustered_signedrank.pdf

[^1_47]: https://analytical.unsw.edu.au/sites/default/files/document_related_files/Eqavalence_nonInferority%20test_Seminar_Aug2019.pdf

[^1_48]: https://www.stata.com/manuals/rsignrank.pdf

[^1_49]: https://irjs.org/api/uploads/manuscript/manuscript_1760985110.pdf

[^1_50]: https://psycnet.apa.org/fulltext/2024-25346-001.pdf

[^1_51]: https://ww2.amstat.org/meetings/proceedings/2013/data/assets/handouts/308941_81819.pdf

[^1_52]: https://statmate.org/blog/paired-t-test-vs-wilcoxon

[^1_53]: https://en.wikipedia.org/wiki/Permutation_test

[^1_54]: https://cran.r-project.org/web/packages/permuco/vignettes/permuco_tutorial.pdf

[^1_55]: https://deepblue.lib.umich.edu/bitstream/handle/2027.42/142988/biom12731_am.pdf?sequence=1

[^1_56]: https://www.youtube.com/watch?v=3bsP5DC7F14

[^1_57]: https://resiliotech.com/blog/model-registry-best-practices-versioning-lineage-promotion-workflows

[^1_58]: https://photokheecher.medium.com/building-safe-mlflow-promotion-pipelines-with-approval-gates-b2e560cafbf8

[^1_59]: https://medium.com/data-science/automate-ml-model-retraining-and-deployment-with-mlflow-in-databricks-ad29f6146f80

[^1_60]: https://us.fitgap.com/stack-guides/prevent-unauthorized-and-shadow-changes-with-automated-detection-and-reconciliation

[^1_61]: https://mlops-coding-course.fmind.dev/5. Refining/5.6. Model Registries.html

[^1_62]: https://www.dinocajic.com/robust-ai-model-governance/

[^1_63]: https://mlflow.org/docs/latest/ml/model-registry/workflow/

[^1_64]: https://medium.com/@johnthuo/experiment-tracking-and-model-registry-with-mlflow-a74c30217e8c

[^1_65]: https://mlflow.org/docs/3.6.0/ml/

[^1_66]: https://mlflow.org/docs/latest/ml/model-registry/tutorial/

[^1_67]: https://sites.ualberta.ca/~szepesva/papers/ICML2021-Botao-BootstrappingFQE.pdf

[^1_68]: https://sandykuan.github.io/Szu-Chi/static/Statistical Testing for Comparing Machine Learning Algorithms.pdf

[^1_69]: https://www.aiuniverse.xyz/holdout-set/

[^1_70]: https://github.com/marklhc/bootmlm

[^1_71]: https://jmlr.org/papers/volume19/17-370/17-370.pdf

[^1_72]: https://www.cs.utexas.edu/~pstone/Papers/bib2html-links/AAAI17-Hanna-safe-abstract.pdf

[^1_73]: https://www.youtube.com/watch?v=GJgp2I0AdDs

[^1_74]: https://www.tangle.tools/blog/self-improving-stack-evaluation-gates/

[^1_75]: https://arxiv.org/pdf/1903.06552v1.pdf

[^1_76]: https://statmodeling.stat.columbia.edu/2016/11/22/30560/

[^1_77]: https://pmc.ncbi.nlm.nih.gov/articles/PMC12190241/

[^1_78]: https://stats.stackexchange.com/questions/135438/why-isnt-the-holdout-method-splitting-data-into-training-and-testing-used-in

[^1_79]: https://arxiv.org/html/2604.00222v1

[^1_80]: https://www.math.ovgu.de/imst1_media/Publikationen/Zeitschriften/preprint_kirch07.pdf

[^1_81]: https://fsl.fmrib.ox.ac.uk/fsl/docs/statistics/randomise.html

[^1_82]: https://www.frontiersin.org/journals/neuroinformatics/articles/10.3389/fninf.2014.00072/pdf

[^1_83]: https://www.arxiv.org/pdf/2601.17734.pdf

[^1_84]: https://www.biostat.wisc.edu/~chappell/641/papers/paper24.pdf

[^1_85]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4185212/

[^1_86]: https://arxiv.org/pdf/2403.02065v2.pdf

[^1_87]: https://sites.miamioh.edu/stevens-lab/files/2018/08/Reiss-et-al.-2010-On-Distance-Based-Permutation-Tests-for-Between-Group-Comparisons.pdf

[^1_88]: https://www.academia.edu/75280149/Permutation_Test_for_Group_Comparison_in_PLS_Path_Modeling

[^1_89]: https://www.biorxiv.org/content/10.1101/2023.02.27.530244v1.full.pdf

[^1_90]: https://metricgate.com/blogs/choosing-resampling-scheme-cross-validation/

[^1_91]: https://mastmldocs.readthedocs.io/en/version_2.0/2_mastml_tutorial_logcv.html

[^1_92]: https://github.com/scikit-learn/scikit-learn/discussions/27091

[^1_93]: https://www.kaggle.com/code/phoebewongtw/k-fold-cross-validation-with-logo

[^1_94]: https://stackoverflow.com/questions/66734121/how-to-apply-leave-one-group-out-cross-validation-in-sklearn

[^1_95]: https://museotoolbox.readthedocs.io/en/latest/auto_examples/cross_validation/LeaveOneSubGroupOut.html

[^1_96]: https://stackoverflow.com/questions/41796301/combining-randomizedsearchcv-or-gridsearccv-with-leaveonegroupout-cross-valida

[^1_97]: https://metricgate.com/docs/grouped-cv-prediction/

[^1_98]: https://www.sympathyfordata.com/doc/7.0.2/Library/Nodes/Machine Learning/Partitioning and validation/CrossVal_LeaveOneGroupOut.html

[^1_99]: https://mlflow.org/articles/tags/team-communication-in-ai/

[^1_100]: https://www.sciencedirect.com/science/article/pii/S2211675324000344

[^1_101]: https://migration.minimumcd.org/docs/migrate-to-cd/pipeline/immutable-artifacts/

