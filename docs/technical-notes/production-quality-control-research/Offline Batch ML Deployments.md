# **Statistical Gating, Safe Promotion, and Automated Rollback for Offline Batch ML Systems with Group-Correlated Data**

Standard machine learning deployment paradigms assume continuous, high-volume streaming request environments where canary routing or shadow deployments can quickly establish statistical significance1. In offline systems where model or configuration updates are applied to a fixed corpus of approximately 940 labeled records and deployed via a full database re-ingest, no active user request stream exists to split2. Gating deployments and validating changes in these systems must rely on rigorous offline statistical validation.  
This operational constraint is compounded when the evaluation signal consists of a held-out cross-validation set of approximately 440 instances nested within approximately 90 districts3. Observations within the same district are rarely independent; they exhibit intra-cluster correlation due to shared environmental factors, regional policies, or localized demographics3. Underestimating this nesting violates the independence assumptions of classical statistical tests, deflating variance estimates and leading to high Type I error rates4. Consequently, minor configuration adjustments are easily misidentified as highly significant improvements when they are merely fitting to localized noise5.

## **Data Integration, Lineage Gates, and Ingest Architecture**

To establish a repeatable and auditable offline gating pipeline, the data ingestion architecture must bridge enterprise BI platforms, feature stores, and the machine learning model registry8. Relying on direct SQL queries of raw transactional tables introduces the risk of metric drift, where definitions like "active district" diverge between business dashboards and training features9.  
The ingestion tier mitigates this risk by utilizing Semantic Link architectures to connect gold-standard semantic models directly to Apache Spark notebooks9. Rather than querying raw tables, the ingestion pipeline invokes governed semantic definitions9. This process maintains semantic consistency across the 940-record scoring corpus and the 440-record evaluation cohort9.

\+------------------------------------------------------------+  
|                Enterprise Semantic Model                   |  
|  \- Governed Measures (e.g., Active District, Revenue)      |  
\+------------------------------------------------------------+  
                              |  
                              |  Semantic Link  
                              |  fabric.read\_table()  
                              v  
\+------------------------------------------------------------+  
|                 Apache Spark Ingest Pipeline               |  
|  \- Spark SQL / dbt Transformation Models        |  
|  \- MLflow Model Signature Enforcement            |  
\+------------------------------------------------------------+  
                              |  
                              |  MLflow Tracking  
                              |  infer\_signature()  
                              v  
\+------------------------------------------------------------+  
|                       Model Registry                       |  
|  \- Champion Configuration vs. Challenger Configuration     |  
\+------------------------------------------------------------+

To run offline batch prediction, MLflow model signatures must be declared at the point of training9. Without explicit input and output schemas populated via mlflow.models.infer\_signature, SQL-based batch prediction functions (such as the PREDICT function in modern data warehouses) fail9.  
Furthermore, running large-scale batch scoring jobs on high-capacity clusters (e.g., Fabric F64 capacity units) during peak BI refresh hours can cause resource contention, throttling critical business dashboards9. Batch scoring pipelines must therefore be scheduled during off-peak windows or routed to dedicated, isolated data science capacities9.

## **Group-Aware Offline Validation Frameworks**

When evaluating configuration changes on the 440 held-out records, standard random cross-validation splits allow data leakage7. If records from the same district are split across training and evaluation sets, the model learns district-specific artifacts rather than generalizable signals7.  
To quantify this dependency, the Intraclass Correlation Coefficient (ICC, or ![][image1]) is computed using an unconditional mixed-effects model3:  
![][image2]  
where ![][image3] represents the between-district variance and ![][image4] represents the within-district residual variance3. A non-zero ICC indicates that observations within a district are correlated, which inflates the Type I error rate of standard statistical tests3. The impact of this nesting on standard errors is measured by the Design Effect (![][image5])12:  
![][image6]  
where ![][image7] represents the average cluster size12. For the 440 held-out records grouped across 90 districts, the average cluster size is ![][image8].  
If the district-level correlation is high (e.g., ![][image9]), the design effect is:  
![][image10]  
This means that the variance of the performance estimator is 2.36 times larger than a naive, non-clustered calculation would assume4. The naive standard error is underestimated by a factor of ![][image11], which leads to false-positive significance claims4.  
To address this correlation, the validation pipeline must enforce Group K-Fold cross-validation10. This technique guarantees that entire districts are assigned strictly to either the training split or the evaluation split, but never both, providing an honest assessment of how the configuration changes generalize to unseen districts10.

## **Statistical Significance Gating**

Comparing a challenger configuration against the current production champion on a fixed validation cohort requires addressing two distinct sources of correlation: training set overlaps across cross-validation runs5 and spatial nesting within districts3.

### **The Nadeau-Bengio Variance Correction**

When models are evaluated across repeated cross-validation folds, the training sets overlap significantly, violating the independence assumption of the classical paired t-test5. The Nadeau-Bengio correction adjusts the variance estimate to account for this overlap5:  
![][image12]  
where ![][image13] is the number of cross-validation folds, ![][image14] is the number of evaluation observations per fold, ![][image15] is the number of training observations per fold, ![][image16] is the mean of the performance differences across folds, and ![][image17] is the sample variance of those differences5.  
This correction inflates the standard error to prevent false-positive promotions5. Bouckaert and Frank demonstrated that the corrected resampled t-test also provides significantly higher replicability than alternative validation tests16.

| Hypothesis Test | Core Target Metric | Minimum Sample Size (N) | Intra-Cluster Support | Replicability & Error Tradeoffs |
| :---- | :---- | :---- | :---- | :---- |
| **Naive Paired t-test** | Continuous Mean Differences | ![][image18] | None (Assumes IID) | High Type I error rate; highly sensitive to partition noise5. |
| **McNemar's Test** | Binary Classification Concordance | ![][image18] per cell | None (Requires IID)15 | Low Type I error; high Type II error; requires running algorithms only once16. |
| **5x2cv Paired t-test** | Out-of-Sample Accuracy | Fixed 5 runs, 2 folds | None (Requires IID) | Low Type I error; high Type II error; poor replicability due to high sensitivity to partition splits16. |
| **Nadeau-Bengio Corrected t-test** | Cross-Validated Metric Differences | Dependent on fold counts6 | None (Corrects for training overlaps only)6 | Gold-standard for repeated CV; balances Type I and Type II errors; high replicability6. |
| **Wilcoxon Signed-Rank Test** | Median Performance Rank | ![][image18] pairs18 | Indirect (Via rank differences) | Non-parametric; highly robust to non-normal distributions; optimal for ranking frameworks18. |

### **Clustered Bootstrapping (Cases Bootstrap)**

While the Nadeau-Bengio correction accounts for training overlaps, it does not correct for the nested correlation within the validation set itself6. To address this, the pipeline can implement a non-parametric **Cases Bootstrap**20. Instead of resampling individual rows, entire districts are sampled with replacement to preserve intra-cluster relationships20.  
For models with complex hierarchical structures, a **Random Effects Block (REB/0) Bootstrap** can be applied to uncorrelate variance components21. This procedure extracts non-parametric residual quantities, resamples the predicted random effects, and generates bootstrap responses to ensure unbiased variance estimation21.  
To minimize Type I errors when estimating metric variances (such as ![][image19]\-scores) near 1.0 or on small sample sizes, a **pseudo-count regularized bootstrap** can be integrated22. This regularization prevents the denominator of the precision and recall calculations from collapsing to zero during bootstrap resampling22.

### **Clustered Non-Inferiority Testing**

Rather than requiring absolute superiority, promotion gating can be framed as a non-inferiority test23. This ensures the challenger is "no worse than" the champion by more than a pre-defined tolerance margin23:  
![][image20]  
![][image21]  
where ![][image22] represents the non-inferiority margin23.  
Because standard non-inferiority tests assume independent observations, they require adjustment when applied to clustered matched pairs15. The standard error is adjusted using Eliasziw-Donner inflation factors or Obuchowski’s covariance corrections to account for the positive correlation within clusters15. If the lower bound of the adjusted confidence interval exceeds ![][image23], the null hypothesis is rejected, and the configuration change is approved for promotion24.

## **Configuration-as-Data Release Patterns**

Once a configuration change passes statistical gating, it must be deployed safely to the production database25. Because the system processes scoring offline, standard application-tier canary routing is not possible2. Instead, deployment safety must be managed at the database tier using **Blue-Green Database Swaps** and **Atomic Pointer Swaps**26.

### **Snowflake Database Swap Pattern**

In Snowflake, this pattern is implemented by rotating staging and production databases through the SWAP WITH command26. This operation swaps the database metadata in a single transaction, instantly routing reads to the newly validated data while preserving the previous production state for rollback26.

SQL  
\-- Create a zero-copy clone of the active production database to staging  
CREATE OR REPLACE DATABASE stage\_db CLONE analytics\_db;

\-- Execute the offline batch scoring pipeline targeting stage\_db  
\-- \[Batch scoring operations run here\]

\-- Execute post-scoring validation checks on stage\_db  
\-- If checks pass, perform an atomic database-level swap  
ALTER DATABASE analytics\_db SWAP WITH stage\_db;

### **PostgreSQL Schema Swap Pattern**

For relational engines like PostgreSQL, pointer swaps are managed via view redefinition or search path manipulation within an explicit transaction block28.

SQL  
\-- Establish schemas for the blue and green environments  
CREATE SCHEMA IF NOT EXISTS data\_blue;  
CREATE SCHEMA IF NOT EXISTS data\_green;

\-- Populate data\_green with the new configuration and scored results  
\-- \[Pipeline execution targets green schema\]

\-- Perform an atomic pointer swap using a production view  
BEGIN;  
  DROP VIEW IF EXISTS active\_production\_view;  
  CREATE VIEW active\_production\_view AS SELECT \* FROM data\_green.scored\_corpus;  
COMMIT;

This view-based pointer swap ensures that read queries are instantly routed to the validated green schema25. If a rollback is required, the transaction block can be re-run to point the view back to the blue schema25.

## **Automated Monitoring, Agentic Roles, and Rollbacks**

To govern the lifecycle of configuration changes without manual intervention, the pipeline can be structured around a **guarder multi-agent framework**30. This architecture isolates validation and deployment responsibilities into role-separated software agents30.

\+-------------------+      Evaluates performance      \+------------------+  
|  Safety-Auditor   | \<------------------------------ |    Monitor       |  
|  \- Validates CIs  |                                 |  \- Tracks drift  |  
\+-------------------+                                 \+------------------+  
          |                                                     ^  
          |  Approves promotion                                 |  Measures output  
          v                                                     |  
\+-------------------+                                 \+------------------+  
|   Orchestrator    | \------------------------------\> |    Diagnosis     |  
|  \- Swaps database |     Triggers scoring run        |  \- Evaluates     |  
\+-------------------+                                 |    regressions   |  
                                                      \+------------------+

* **Monitor:** Continuously tracks input features and output score distributions for drift30.  
* **Diagnosis:** Evaluates regression signatures when drift or performance drops are detected30.  
* **Safety-Auditor:** Evaluates statistical significance and non-inferiority margins on the validation set, ensuring that confidence intervals are mathematically sound30.  
* **Orchestrator:** Directs the workflow, executing the database pointer swaps and coordinating automated rollbacks when quality gates fail1.

### **Pipeline Monitoring with DVC and Evidently**

The monitoring agent uses DVC and Evidently to track and version dataset changes32. The pipeline splits data into a **reference dataset** (the baseline run) and a **current dataset** (the challenger run)32. Evidently’s Regression Preset evaluates prediction behavior and logs metrics to DVCLive32.

Python  
from dvc.api import make\_checkpoint  
from evidently.report import Report  
from evidently.metric\_preset import RegressionPreset  
import dvclive

\# Initialize DVCLive logger to capture run artifacts  
with dvclive.Live(dir="reports/train") as live:  
      
    \# Load baseline and current scored datasets  
    reference\_data \= pd.read\_csv("data/reference\_scored.csv")  
    current\_data \= pd.read\_csv("data/current\_scored.csv")  
      
    \# Generate the Regression Performance Report  
    regression\_report \= Report(metrics=\[RegressionPreset()\])  
    regression\_report.run(reference\_data=reference\_data, current\_data=current\_data)  
      
    \# Log key metrics to DVCLive for tracking  
    metrics \= regression\_report.as\_dict()  
    live.log\_metric("mean\_error", metrics\["metrics"\]\[0\]\["result"\]\["mean\_error"\])

### **Post-Scoring Distribution Drift Gates**

Once batch scoring is complete on the 940 records, the newly generated distribution must be validated against the baseline32. The pipeline evaluates the output using two statistical metrics: the **1st Wasserstein Distance** and the **Kolmogorov-Smirnov (KS) Test**33.

#### **1st Wasserstein Distance**

The Wasserstein distance measures the minimum work required to transform one probability distribution into another35. For one-dimensional continuous distributions, it is calculated as the area between their respective cumulative distribution functions (CDFs)33:  
![][image24]  
where ![][image25] and ![][image26] are the empirical CDFs of the baseline and current scored datasets33.

#### **Two-Sample Kolmogorov-Smirnov Test**

The KS test evaluates the maximum vertical distance between two empirical CDFs33:  
![][image27]  
The KS test evaluates the null hypothesis that both samples are drawn from the same underlying distribution, returning a ![][image28]\-value33.

| Operational Characteristic | 1st Wasserstein Distance (W1​) | Kolmogorov-Smirnov (D) |
| :---- | :---- | :---- |
| **Mathematical Scope** | Measures global geometric shift (integrates the area between CDFs)33. | Measures the maximum localized divergence (supremum of CDF differences)33. |
| **Outlier Sensitivity** | High. Extreme outliers significantly expand the distance metric37. | Low. Only sensitive to high-density deviations37. |
| **Threshold Interpretation** | Intuitive physical scale (average shift in score units)33. | Standard statistical testing (![][image29] indicates drift)33. |
| **Behavior under Extreme Shifts** | Increases linearly with the distance between distributions37. | Satures at ![][image30], failing to differentiate extreme shifts37. |
| **Operational Trigger** | Set via static deviation thresholds (e.g., ![][image31])34. | Triggered automatically when ![][image28]\-value falls below significance33. |

Integrating both metrics allows the pipeline to detect both localized anomalies (via KS) and overall distribution shifts (via Wasserstein) before promotion33.

## **Architectural Recommendation**

To safely promote configuration changes in this offline batch environment, the pipeline must implement a structured, multi-layered gating workflow1.

\+------------------------------------------------------------+  
|                  Step 1: Ingestion & Schema Gate           |  
|  \- Check schema and configurations using Pandera \[cite: 38\].|  
|  \- REJECT if syntax or boundaries are violated \[cite: 39\].  |  
\+------------------------------------------------------------+  
                              |  
                              v  
\+------------------------------------------------------------+  
|             Step 2: Grouped Validation Engine              |  
|  \- Run Group K-Fold cross-validation on 90 districts.|  
|  \- Estimate parameters using Mixed-Effects ML.|  
\+------------------------------------------------------------+  
                              |  
                              v  
\+------------------------------------------------------------+  
|                Step 3: Statistical Significance            |  
|  \- Run Cases Bootstrap at district level.     |  
|  \- Run Non-Inferiority testing with margin.  |  
\+------------------------------------------------------------+  
                              |  
                              v  
\+------------------------------------------------------------+  
|                Step 4: Swapping & Output Verification      |  
|  \- Run scoring on Staging DB (Green schema) \[cite: 26, 29\].|  
|  \- Verify Wasserstein & KS drift metrics.   |  
|  \- Atomically swap Staging with Production.     |  
\+------------------------------------------------------------+

### **Layer 1: Ingestion and Schema Gate**

* **Action:** The Orchestrator agent pulls the configuration payload and validates it against a strict Pandera schema30. Feature definitions are extracted from governed enterprise semantic models using Semantic Link (fabric.read\_table)9.  
* **Gating Rule:** Reject the run if the configuration contains unauthorized schema modifications, out-of-bounds parameters, or violates column formats38.

### **Layer 2: Grouped Validation Engine**

* **Action:** The validation engine executes Group K-Fold cross-validation over the 90 districts10. If the data shows high district-level variation, a tree-boosted mixed-effects algorithm (such as GPBoost) is used to isolate fixed-effect updates from regional random intercepts40.  
* **Gating Rule:** Reject the run if the validation metrics exhibit high variance across the evaluation folds10.

### **Layer 3: Statistical Significance**

* **Action:** The Safety-Auditor agent runs a non-parametric Cases Bootstrap to generate a 95% confidence interval for the metric difference21. The interval is evaluated using a non-inferiority framework adjusted for clustered data15.  
* **Gating Rule:** Reject the promotion if the lower bound of the confidence interval falls below the non-inferiority margin ![][image23]24.

### **Layer 4: Swapping and Output Verification**

* **Action:** The batch scoring pipeline processes the 940 records in a staging database (e.g., Snowflake's stage\_db)26. The Monitor agent calculates the Wasserstein distance and the KS statistic to compare the output against the active baseline30.  
* **Gating Rule:** If the scored outputs show significant drift (![][image31] or ![][image32]), promotion is blocked33. If the metrics are within bounds, the Orchestrator executes an atomic database pointer swap, promoting the staging database to production and updating the model registry8. If any post-swap anomalies occur, the database swap is reversed to restore the previous state25.

#### **Works cited**

1. Quality Gates for ML: 4 Layers Between Training and Production \- StackSimplify, [https://stacksimplify.com/blog/quality-gates-for-ml/](https://stacksimplify.com/blog/quality-gates-for-ml/)  
2. AI Pipeline System Design: Data Ingestion, Training, and Serving | InfraSketch Blog, [https://infrasketch.net/blog/ai-pipeline-system-design](https://infrasketch.net/blog/ai-pipeline-system-design)  
3. Using Cluster Bootstrapping to Analyze Nested Data With a Few Clusters \- PMC \- NIH, [https://pmc.ncbi.nlm.nih.gov/articles/PMC5965657/](https://pmc.ncbi.nlm.nih.gov/articles/PMC5965657/)  
4. Clustered Standard Errors in AB Tests \- Towards Data Science, [https://towardsdatascience.com/clustered-standard-errors-in-ab-tests-a993f29b9225/](https://towardsdatascience.com/clustered-standard-errors-in-ab-tests-a993f29b9225/)  
5. Nadeau-Bengio Corrected Resampled t-Test Calculator \- MetricGate, [https://metricgate.com/docs/nadeau-bengio-corrected-resampled-t-test/](https://metricgate.com/docs/nadeau-bengio-corrected-resampled-t-test/)  
6. Corrected Paired t-Test for CV Model Comparison Calculator \- MetricGate, [https://metricgate.com/docs/cv-comparison-corrected-paired-t/](https://metricgate.com/docs/cv-comparison-corrected-paired-t/)  
7. Towards a more realistic evaluation of machine learning models for bearing fault diagnosis, [https://arxiv.org/html/2509.22267v3](https://arxiv.org/html/2509.22267v3)  
8. Model Versioning and Registry Prompt for ML Engineer | MLJAR Studio, [https://mljar.com/ai-prompts/ml-engineer/model-deployment/prompt-model-registry/](https://mljar.com/ai-prompts/ml-engineer/model-deployment/prompt-model-registry/)  
9. From Demo to Production: ML-Enriched Power BI in Microsoft Fabric \- Christopher Finlan, [https://christopherfinlan.com/2026/02/18/production-migration-checklist-power-bi-ml-microsoft-fabric/](https://christopherfinlan.com/2026/02/18/production-migration-checklist-power-bi-ml-microsoft-fabric/)  
10. Cross-Validation for Marketing Analytics Models \- growth-onomics, [https://growth-onomics.com/cross-validation-for-marketing-analytics-models/](https://growth-onomics.com/cross-validation-for-marketing-analytics-models/)  
11. Multilevel Regression \- Advanced Statistics using R, [https://advstats.psychstat.org/python/multilevel/index.php](https://advstats.psychstat.org/python/multilevel/index.php)  
12. Clustered Standard Error: Practical example \- Rohan Blog, [http://www.rohanbyanjankar.com.np/2025/02/clustered-standard-error-practical.html](http://www.rohanbyanjankar.com.np/2025/02/clustered-standard-error-practical.html)  
13. Metrics and Techniques for Model Evaluation in Machine Learning \- iMerit, [https://imerit.ai/resources/blog/machine-learning-model-evaluation/](https://imerit.ai/resources/blog/machine-learning-model-evaluation/)  
14. Exploring Machine Learning Models to Uncover Pathways in ALS Pathogenesis Using Immunohistochemical Features | medRxiv, [https://www.medrxiv.org/content/10.64898/2025.12.19.25342356v1.full-text](https://www.medrxiv.org/content/10.64898/2025.12.19.25342356v1.full-text)  
15. Non-inferiority tests for clustered matched pair data \- PMC \- NIH, [https://pmc.ncbi.nlm.nih.gov/articles/PMC2717020/](https://pmc.ncbi.nlm.nih.gov/articles/PMC2717020/)  
16. For model selection/comparison, what kind of test should I use? \- Cross Validated, [https://stats.stackexchange.com/questions/217466/for-model-selection-comparison-what-kind-of-test-should-i-use](https://stats.stackexchange.com/questions/217466/for-model-selection-comparison-what-kind-of-test-should-i-use)  
17. Statistical Significance Tests for Comparing Machine Learning Algorithms \- MachineLearningMastery.com, [https://machinelearningmastery.com/statistical-significance-tests-for-comparing-machine-learning-algorithms/](https://machinelearningmastery.com/statistical-significance-tests-for-comparing-machine-learning-algorithms/)  
18. Wilcoxon Signed Rank Test \- GeeksforGeeks, [https://www.geeksforgeeks.org/machine-learning/wilcoxon-signed-rank-test/](https://www.geeksforgeeks.org/machine-learning/wilcoxon-signed-rank-test/)  
19. Testing Rankings with Cross-Validation arXiv:2105.11939v2 \[stat.ME\] 11 Feb 2022, [https://arxiv.org/pdf/2105.11939](https://arxiv.org/pdf/2105.11939)  
20. Internal validation of risk models in clustered data: a comparison of bootstrap schemes, [https://pubmed.ncbi.nlm.nih.gov/23660796/](https://pubmed.ncbi.nlm.nih.gov/23660796/)  
21. Bootstrapping Clustered Data in R using lmeresampler \- The R Journal, [https://journal.r-project.org/articles/RJ-2023-015/](https://journal.r-project.org/articles/RJ-2023-015/)  
22. (PDF) Estimating Uncertainty in Classifier Performance with Applications to Large Language Models and Nested Data \- ResearchGate, [https://www.researchgate.net/publication/408107335\_Estimating\_Uncertainty\_in\_Classifier\_Performance\_with\_Applications\_to\_Large\_Language\_Models\_and\_Nested\_Data](https://www.researchgate.net/publication/408107335_Estimating_Uncertainty_in_Classifier_Performance_with_Applications_to_Large_Language_Models_and_Nested_Data)  
23. Sample size calculation in clinical trial using R \- PMC, [https://pmc.ncbi.nlm.nih.gov/articles/PMC10020745/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10020745/)  
24. Paired T-Test for Non-Inferiority \- NCSS, [https://www.ncss.com/wp-content/themes/ncss/pdf/Procedures/NCSS/Paired\_T-Test\_for\_Non-Inferiority.pdf](https://www.ncss.com/wp-content/themes/ncss/pdf/Procedures/NCSS/Paired_T-Test_for_Non-Inferiority.pdf)  
25. What is a Blue‑Green Deployment: Complete Guide for Cloud & Kubernetes \- Simpliaxis, [https://www.simpliaxis.com/resources/blue-green-deployment](https://www.simpliaxis.com/resources/blue-green-deployment)  
26. Blue-Green Deployment with dbt and Snowflake \- Datatonic, [https://datatonic.com/insights/blue-green-deployment-with-dbt-and-snowflake/](https://datatonic.com/insights/blue-green-deployment-with-dbt-and-snowflake/)  
27. (PDF) Noria: dynamic, partially-stateful data-flow for high-performance web applications Noria \- ResearchGate, [https://www.researchgate.net/publication/331181449\_Noria\_dynamic\_partially-stateful\_data-flow\_for\_high-performance\_web\_applications\_Noria\_dynamic\_partially-stateful\_data-flow\_for\_high-performance\_web\_applications](https://www.researchgate.net/publication/331181449_Noria_dynamic_partially-stateful_data-flow_for_high-performance_web_applications_Noria_dynamic_partially-stateful_data-flow_for_high-performance_web_applications)  
28. How to Implement Database Blue-Green with ArgoCD \- OneUptime, [https://oneuptime.com/blog/post/2026-02-26-argocd-database-blue-green/view](https://oneuptime.com/blog/post/2026-02-26-argocd-database-blue-green/view)  
29. Blue-Green Deployment for OCI PostgreSQL | by Shadab Mohammad | Oracle Developers, [https://medium.com/oracledevs/blue-green-deployment-for-oci-postgresql-1068faa8ce1c](https://medium.com/oracledevs/blue-green-deployment-for-oci-postgresql-1068faa8ce1c)  
30. Validation-Gated Multi-Agent Governance for Online Adaptation of Thermal–Hydraulic Surrogate Models under Operating-Regime Shift \- arXiv, [https://arxiv.org/html/2606.03321v1](https://arxiv.org/html/2606.03321v1)  
31. How to Build ML Pipeline Architecture \- OneUptime, [https://oneuptime.com/blog/post/2026-01-30-ml-pipeline-architecture/view](https://oneuptime.com/blog/post/2026-01-30-ml-pipeline-architecture/view)  
32. Tutorial: Automate Data Validation and Model Monitoring Pipelines with DVC and Evidently, [https://dvc.org/blog/automate-data-validation-and-model-monitoring-with-evidently-and-dvc/](https://dvc.org/blog/automate-data-validation-and-model-monitoring-with-evidently-and-dvc/)  
33. 🌊Data Drift Metrics Interactive \- Kaggle, [https://www.kaggle.com/code/ivanlydkin/data-drift-metrics-interactive](https://www.kaggle.com/code/ivanlydkin/data-drift-metrics-interactive)  
34. How to test Machine Learning Models? Numerical data drift \- Giskard, [https://www.giskard.ai/knowledge/how-to-test-ml-models-3-n-numerical-data-drift](https://www.giskard.ai/knowledge/how-to-test-ml-models-3-n-numerical-data-drift)  
35. Presenting Univariate Drift Detection Methods \- NannyML's documentation\!, [https://nannyml.readthedocs.io/en/stable/how\_it\_works/univariate\_drift\_detection.html](https://nannyml.readthedocs.io/en/stable/how_it_works/univariate_drift_detection.html)  
36. Understanding Kolmogorov-Smirnov (KS) Tests for Data Drift on Profiled Data, [https://towardsdatascience.com/understanding-kolmogorov-smirnov-ks-tests-for-data-drift-on-profiled-data-5c8317796f78/](https://towardsdatascience.com/understanding-kolmogorov-smirnov-ks-tests-for-data-drift-on-profiled-data-5c8317796f78/)  
37. Choosing Univariate Drift Detection Methods \- NannyML's documentation\! \- Read the Docs, [https://nannyml.readthedocs.io/en/v0.13.1/how\_it\_works/univariate\_drift\_comparison.html](https://nannyml.readthedocs.io/en/v0.13.1/how_it_works/univariate_drift_comparison.html)  
38. Safe ML Models with Synthetic Data: The Verification Pipeline That Prevents Disasters, [https://medium.com/@ryassminh/safe-ml-models-with-synthetic-data-the-verification-pipeline-that-prevents-disasters-8c2f1a477197](https://medium.com/@ryassminh/safe-ml-models-with-synthetic-data-the-verification-pipeline-that-prevents-disasters-8c2f1a477197)  
39. MLOps: Continuous delivery and automation pipelines in machine learning | Cloud Architecture Center, [https://docs.cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning](https://docs.cloud.google.com/architecture/mlops-continuous-delivery-and-automation-pipelines-in-machine-learning)  
40. Mixed Effect Machine Learning: a framework for predicting longitudinal change in hemoglobin A1c \- PMC, [https://pmc.ncbi.nlm.nih.gov/articles/PMC6495570/](https://pmc.ncbi.nlm.nih.gov/articles/PMC6495570/)  
41. Tree-Boosted Mixed Effects Models | Towards Data Science, [https://towardsdatascience.com/tree-boosted-mixed-effects-models-4df610b624cb/](https://towardsdatascience.com/tree-boosted-mixed-effects-models-4df610b624cb/)  
42. 95% Confidence interval for proportion with poisson distribution : r/AskStatistics \- Reddit, [https://www.reddit.com/r/AskStatistics/comments/k24he5/95\_confidence\_interval\_for\_proportion\_with/](https://www.reddit.com/r/AskStatistics/comments/k24he5/95_confidence_interval_for_proportion_with/)

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAZCAYAAADnstS2AAAAgklEQVR4XmNgGAVDArgA8X8g3gulVVGlEaCEAaIABiLR+HAgzACR4EASE4CKKSGJgcFLqAQySIGKyaKJgwUDsIihG8AQhkWQGSrmhybOcB0qkYQk9heI5yHx4QCk8DQQH4WyfwOxDooKJIDNvVhBCAOme3GCcwwkKH4IxOXogsMFAAD5Xh/kgwoBAwAAAABJRU5ErkJggg==>

[image2]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAA8CAYAAADbhOb7AAACHElEQVR4Xu3dQasOYRQH8LGhlEt8AAvZK76DPUpWUlaKcstFKYubks2Vja1kYeMT8AGUnextLHwAWSCcaZ4nz3t07yVm3uH+fvXvOeeZ6Z3taeZtpusAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHQn8i0FAICZuBxZKbVBDQBg5tab+ktZb23SAwAwsY3IrlIfihwpdb3rlnsAACbWDmKrkb1pP/cAAEzsbFOf7Ia7bL06oOUeAIAlWytrHdByDwDAkvX/Z7uyRQ8A8N/r3312Om8CADAPX8t6LvKgPVC83SYAAIzobuRqqY93f/c/Yf1vzT0AALPXDi19fb7pq3vbBACAEeWBDQCAGenfdfaqGwa1J+nY2A5HjkY+5QMAAPzQD2r1BbRTc2cPAOAXzGFQOhU5kzcBABjszxtLcD9vAAAwrf4u3ovIy1JfL/sHIxciFyPPy96f+BC5Gflc1muRfQtnAADwk93d8G636ncewR6LnNgim8nXeNMtnv8+8rTpAQB2tDw85X4Mj5v6XVkflXWK6wMA/FPaAel25EbTj+FZ5EDT1+vXj8Qb2AAAkj3d8Eh0LbKRjo0hD2S1vxRZaXoAAGaiDmjrqQcAYEb6b50+bPrXkY9NDwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACP4DrVbgNmhIaeDAAAAAElFTkSuQmCC>

[image3]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABgAAAAaCAYAAACtv5zzAAABBklEQVR4XmNgGAWjYBTQDXAA8Vcg/o8D+yCUkg4YGSCGLALiCiDeicQuA+J8hFLyAMjlTEj8H0hsdCCCLgAFougC+ADIN+hgEhD7QdnI8iDf/4Gys4C4BkkOK3BgwG4BslgCEE+HslcwQPTAADa9KOAeEB9AE3NhQNVoisQH0cjBA+LLIfExAEhBLJpYEVQcBrSR+CCaC0kOxHdH4qMAKQaIAmY0cVAqQrZAC4mPzQJYXGEF4egCDBAXIVtgjMQH0cJIciC+GhKfaIBsQQwQb4KyLwGxDZIcsjqSwEkgloCyfwIxC5QNCp43UDYobs5A2WQBfSDOY4CkfWQA4oMSAkh+FIxEAABcwjjLQnaBiwAAAABJRU5ErkJggg==>

[image4]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAaCAYAAABYQRdDAAAAxklEQVR4XmNgGGRADl2AEtADxG5AbAvE/4HYEFWaPAAySATKzoDyKQYngJgdyrZnoJKhyOA8EF9GF6QEyALxO3RBSgALEN9GF6QUHEZib0ZiYwURQPyXARL46DgRqgabPE7wmgGiYDEQL4CyQWLlQFyEUEY8WMCAaWMzFjGiASsDRLMOmngjVJwsMJUBu+Y7DNjFiQKnGLBrBol1oAsSCyoYMA1dAcS/0MRIBqBkkg/EwkC8D4jvo0qTD9SBOBJdcBSMguEKAJGjMNYSM6oiAAAAAElFTkSuQmCC>

[image5]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADEAAAAaCAYAAAAe97TpAAACHElEQVR4Xu2WO0gdQRSGjy+wsBAlIBGChVpYxcI6RYJNKtHGR2FhaxktBBFfrRYmMX0QYiE2YiWpxAcogoUoqfIQsbARo6Ki5/fM7M6ezN29e0UMuB/83Lvn/2d3dmZ3dogyMjLi6GZts3YcbbE2Wausz6yiIP1welmXRk1RK+AF65b1h/VRebGgEVTs1GpYS6b+wakXSgnJuarM73zUDoDXan6hvEEYo+NjksKLP4RPFHZqkfwzjIGzmW+sWseL5SVJw1FtOMA/0sWU4Bx/dVHxlVKOvsWOULk2HFJPrQe0x7XiuKECr5NPB32ZCpKRvWb9ZJ1E7QDb1tVyJPGv77teLAhf6KIDOosMRsnSaWrVTg2rWYNz7PKO8usUMj26mIR9kUZU3WWaJDNgjvHY4Xg8SIQrTy7mKN4HjSSZUm0kMUvSMM37sGuO91i/zP918q82FjxySTcxQckZL7qDmmYSf9ipJbXxgbx+DzSHlP6896BRru8DgP/bU0t7MeTbdVGBDGY5FfUkDce0wbwi8Ra0wayQ/yZmWG91kWR74ctrkOnXxVy0sTYoHNEfrDUj7JtQw3LZYht4QGaQVcZ6zzpjvY4kQqYo+SYqSTJx7+ajgJnsIFmZ4jhlneuiAnuzpBt9Er6YX3SuyzUchkh2rfhY7ivvyflO0nk8brlG+A2JZ2cBH9X/ij7WMeuKVRe1AuxO4IBkRjIyMp4zd49ImNn1KkPJAAAAAElFTkSuQmCC>

[image6]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAAxCAYAAABnGvUlAAACy0lEQVR4Xu3cz6uMURgH8FOUYsFC2VASWwsldiiyk6z9AQixsLFV7PxasFdKyULKgiRZyMJCFGUlJVlIikR+nNPM7Z555h23Me+9d+bez6e+dc5zZs773vcu5ul9752UAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA5s67WJgHz2IBAOBjzp+crzmfuuOSYdzJWZ2zKdR/5nwLtTasioUW/IqFObI053CoDXv9AYBFoKlBaKoNMui1g+qjanvf07Ewh77kHInF7HksAACLW1MD1FRrsjw1v/ZczpVYbEnT8UbR9n7DGNSwzec5AQBjpjRV32Mx9TYM5bHmrpwlOZeq+rGcpzn3ck5W9ROp8/5TOVurelvabmbifnu6tVep88iyjM/nbMg5m3qvwaiGadimak1rAMACVj78d8Zi6m0OdnfH5e/UtnfHU8p6aWqi2Wwq2t673u9yQ60eb8l5W81HVRq2o7GY+n/Gen4x51o1BwAWuNgYFG9yPnTHZb00MYeml3s0vb8YVG/Dv/beN0OaNO03qGEr/5xR7rRFK1L/saZS7kwOUhq247GYOsepxfOp72gCAAvY+tTfrNzOuVvN4/rBMI/rRWlQmuptaXvvuN/rnL3V/GE1jq8dVWnYmpqveJz91TiuAQALVGlCygf/75wnOS+687X1i7L7OQdyNqb+r74oX6/xI9SKCzlnYrElj1PnPEtTdSOs/a/YANXzdan3kW9ZK9erDY9SZ7+SB2GtPoerqfN7WhnqAAAzupmzLRbT5DUV9R3FcXGrGk/a9QQAxsCONH1nqFbu2n1uqE+C8iW/4+J9mE/i9QQAxsD1WOiq7wxNkmU5m2NxHqxJnUeftZdhDgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADB7/gLahYrb2kNLLwAAAABJRU5ErkJggg==>

[image7]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAaCAYAAAC6nQw6AAAA0ElEQVR4XmNgGAWjYBCCn0D8HogPQflPgfgEEP8H4h1Qsa1A/BCIfwPxd6gYCogCYgMgtmKAaPyHJKcMFXsBxGxI4iCxMCQ+GMA0zmaAKGBEktOEipkgiYEASCwRTQwOQJK/0MQWQcWRgRkWMRQAkmzHIvYDTewWVBwrkGSASPKiiYPEGrGIgYIBBPYgS4DANAZMW2ABzY4kJgsVYwFifiCejiQHBn+B+Cua2FwGTMO5oWICDJheBgMLIGZFEwPFniKaGAiADPFEFxwFo4AaAABjYC8OMKcNnQAAAABJRU5ErkJggg==>

[image8]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAKsAAAAaCAYAAADIfqzJAAAFcklEQVR4Xu2aZ6gkRRDHy5xzwBOUE1FMiFlPBUXB/EFRzoBiQlFUTCgioog5fTBgRAQFldMPYkAPExjABIKKGNB3YsCEOef+XXe5tbU1O7Pv8L13z/5BwfS/u2e7e2qqw6xIpVKpVCqVSmVErvZCpdKF670QcKUXHKt4oYW/vVBYPNkMLwas44UpwrLJzvZiCyslW8qLATO98H/jM2l2HGUXaS7ze7Ibks2WXOak/uyQlZPdHGjUvzHZeeV6rb4SmVuSfZ1sr2TPJRvrz550/kr2uhcbWFFy+fOTnSu5zzv0lch8kezFZCdILjPqyzAtOEBy55scUWkq82eye51GORxvGDjZIk6j3kUmvXvRLEcE2g/JHnbaZHGt5PZ1dVbfF/AaweAbp1FmA6dNe36UZkdU3kl2hgyWYbr2GqC94UWHr3dfoAHa8S79iEnDIUWfbJaR7KRdnXXTZL94UXL9rcs1ZUj72QrtI6dNaz5OtqgMd1ampCuSnSyDZW4LNPhSYl3ZMdkpTvtN4jpo5Nk07bFsVvQukYZ1t/b3RJdnIeozNqPALANdnXUbidthx+GCkj7QaDDsmbXyq+R11DMljSO8IPmGjxWNiPCB5LD+c9Emiz2SnVOuh3VcH0DkrPMCDd6SWFe+8oLk34nq2LbNLNdn/ZubYV2LfpzTPZ8nuybZYslWT/a25Hpr2EKF273QwqWSX0Lgnl2cFbR/P0l+Od6X/ih6Sck/yGgw7JkN5bBkW0huLDdgwaysX7RPky1pdDQ2JG2MjWjRwEf4aIV5XpW8s4XIWXlBvQY6FTbxrRcSj0pcx7ZtVrk+tZc9n9WK7iOuBQc93IuS+0fw+D7Z9pKf40uSX7iusBx6z6RpS1dnxSe0j9jd/dnz24TO+Fuanlkr6pw6LdqNw8ZFI+Rb0I522kTBGnQJk446vkmym0w6ctamqfs1iXVgytvViwXqXGzSujvWe2kw8M66atFtez1E0mGwmWOdzYt0jMtrg5fWQlu6OivLLPznVun1ldMZyx/JvjNp7W/TGHeCyjZiwZ1Ft2wXaBPFtpKnLEvUcZ+OnLXJKd+UWIcmHfQhXJXsIent/LWO5p9Z0sqaRfdO3AQz4U5eHCenJ9vTabSli7MSxe14sEHT5dB1RgeWjXMlr7lflviZjQSVLws0v+Mjsi3QDy0A2kneViKCTuUY1wzGaSXNG8/Lh055LaORZE7RPJ9IrMMrXmiB+7AcsWl7vAUbFp11+DCOlFyOl4k9Bdf2pMGyjxcaaBpPxo7rfXtFB2BsOTr0sCSxS8kI/d1xMUNy5RWcjnZhoLFkgCdsRoAOQFcbz1edLh1nLeXL6BLHg+ZfUGCaJgo2wTgRXRSmbu61nNFI32/SsH/R25jnhcTTkh1tI6MtLd3u1wR1u0RWyq3nxcRu0v/7Byfb3KSBfD6cjAu+uvgO6ubKfkbDmdBYlPOJbdg6a6KgPb7tHg7+ozJohwbaUU6DqL6i42IP93UNaXlWBpdaT0p7JMIpcMIINmhssnQcsKayXaC+P2det+iXG+1dyW33MAZ2hvbPR78UjhvWGhywWzj+8DclSqDxhSeKPhMJA8Wg6mAwRfM5z7JzsuelV4ZTDTvA+xVdo99T0r8ZUPjfQNtxEPdhhoJ7JEe8CMqxVoStStpG5MmCcRmT3lhxdDmr5LFGRnugpBW0xyUfWy0vOShwxGZhxmQDCGz+qLN2L3t02NXZHTZwKhCFeRx1by8uxHD8g3M9KL0vLx7On/3nVQ/5d0h+OXy09vAtnSOmY33GQggbSRz9Lumd1Xo4JWFj5TfHlf8AokGlMuXZUgY/r1YqU5IPvVCpTFX4Y0ulUqlUKpVKpVKptPIPMTCttqmzZqAAAAAASUVORK5CYII=>

[image9]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEsAAAAaCAYAAAD/nKG4AAACZklEQVR4Xu2XTagOURjH/z4WvorIVb5ClIUdbupuCFmIlY1QihVbpSjFQjbXrau4Uro2KBY2FpSsWBMLCx93K1JIks/n7zmHZ5458868de97mzq/+vfO8z/PmZlz5syZ5wUymUwmM54s8UZDVoimeDMw2xuBGd5oC29Fd0U7RV9Fl4vNlZwWfRAdFT0S/Rb1FzI0hz71wxwvt0lt4aVozHkczCbneWZB89YYL06E5YzxKT6Y6YWMFsEBbHTeC9Ev53m2Q/u+M96r4G0w3inRFhO3ln3Qwc10/u3g17HfxamVdRLjNFnboCd/EH7tku4FoygPjowg7XdiGbTPFeefgE7WEdEz0fliczOOoXhDe12c4k2X2vy3VzX3kL7mBaRXXAoO/ic0f71rI8ehbQtDfCDEjfetBdAO9vM5L3irjDfR3Ed6soah/iLf0IGl0D5clZbVKE868z45rxJ+EfxNHg4el3OviJPiuYi0X8cNaL9DvsHBnMbnZyKXumUs+L2E+wivOc3514Nfx2IXb0V5Il6LDpqYfEez86MPmjjf+fSeO8/zrUvt1m6VTIVed53znwS/E3FS1hpvl/HJnHD85V+G4ie0kksoP03WIo06TwC8rq/Y6Y2amNU2vXPGiwO244grkuVChKvIwxxW/LUwkWX/e+hNnIUWgHzKk0GciJUhHkK5IB2A5twxXtzQWZwSVvyM+bfJwv3rKTSfb9VH0edCRgd4wsFwvAd6ksmGf4Kvih5C951u4FvxWHQN/8sDz1zRTdEt0Q7XVkncr1g6ZGqo+lRnEnCv4lcq04DGJX4mk8lk2sMfD2OsHJUSmH8AAAAASUVORK5CYII=>

[image10]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAAxCAYAAABnGvUlAAAEsElEQVR4Xu3dW8gtYxgH8Ncxp0Qpp4uthFwoEaIULlzKjeRQUiJFDjnlkH2nlHNyIadSiBtcEYoLXLghynlLjjnknGPM08z43u/5ZtY39re29tr796u39c5/Zs16Z61d8zTvzLdLAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAtiQHN22bHG7mfswBALDlublpfzXt76b90LSfu/7Z9UYTfFra99X2bNolA/k8/J6DObg+B43tm3ZXDisxjvjesk+a9nUO52DouHfNwRo93rQ/c5g8V9rf9Zwq+65px5f2Oxv6Ltdil6b90bT384rk19IWsdum/IDSjveplAPAwnivaS+l7MumrU/ZmLGCbCyfh6n7jgJ0irH9fVzGC7b6PU9U/Tof2+/GGtrfULaxpow98huq/udV/+6mXdAtz8sxTbusWp41rv/SB4CFEiexnVJ2RZdPMbbdWD4PU/c9tWB7IQel/YwoxKYUbF9V/VwgnFwtr9XQcd/ZtN1y2Pk+B6UtQsfksR9ULff2qfqxze1dP66ATfFGad93WF4x4tiyclxDzq/6U7YHgIUydEJ7syzP3+1e87aXd1m87ttlR6Z8U8jjGDOlYItp4VyYXNy9zirYYvovxvFyWV4w5WJh7P0bY+y4n8lB5Zeq/1nVzw4vK8d+dbWcXViW7/u30k6lPtq0DVVe27nq71WWf96HVX+Wse+gF0XqmV0/xhjbx+8Yhd/QlDIAbPbiasnQCTCyq6p+nWdDWVztiPucNpWhzxwypWB7PQeN07vXWQVb3Kt1XmnHMvYdRf/eanmtxo77pxwkUVgdksPkuLJy7PdUy0Pq7c+t+m9V/dqtOWhc17QPcjjioxwMOKksFWYPlZXHBAAL552mvZjDsnRiixvaox83ka9bWv2vK5v2WA5Le+P3oTmco1kn3lOqFjeh18tDNqTlM6r+rIItFwKnVctvN+2iLo8CIqvHlNssY8c9lveOKO1DAbPEE7L5mM6qloc8XZbes0OVry9LRW8WD2PEe07NK1YR98admMMRsf9HSvtQRH1MQw+IAMBmL5/ot0tZXs7G1o3l8zJ1/1OusN3RtANz2IkpxLpgu7bqx7RxrX+yNhc98zS2v2dzUPm26q9WtI2N/aiqH3k8tRke7pb7vPdq1a9dk5afLG0BF1OXs36rero0Hmzo3di9xm+Uxx5Ts32/zgFgocTVtTiBxcn1ldKeMO9btkUrtomrJ/eX9j6nvG7IWL5W8XBATP/F/uPesdXMKgJqQ/eAxWfF50R7vsvq4/qiabuX9v63oaIgpuXqq05rEYXJa2XpuPer1t3StP2r5Vr/BGftmxxUbipLT2TGwwG9+NxLu35Mr8a/g3hQpT7umFo+obTF3Tx//yiS+9+hb73c37G0VwXr/MHSjn2PlAPAVmPsBLjalZz/y9SCbew4FsEijx0A2ITiKte6ph2d8igeHkjZIoj7zRbtfzno3ZYDAIAQf0m+vsm+t3dZPl23SOKPBS+afqoWAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAYOvwD7YqFJai6TPhAAAAAElFTkSuQmCC>

[image11]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAHYAAAAZCAYAAADkBdqeAAAEF0lEQVR4Xu2YSagVRxSGj9HEIREnxAF1YZwwOKEozolEhBBQiC5E9GEScONCcSMOiCgIoqIkCxeSjYoaiboQgjglEFGyEGecRUUQccIhwSl6/pwubvV/63bfbu97+qQ/+OHWX6frVldVV51ukbejiaqTqvN7oIIaMlV1RLX7PVBBDXnCRkHjB0/rOjYLGj+v2IjowUaVtFR9xmYFurLxjunCRgLIS0K0ZoP4RtWfzVozRzWPvMeqv1UXVK9Vd+LVFflULH6VanX0+2AsosRO1TPVCtU51al4dYMzVOw4Qp+r5SuxeAgPh/s90Q8isBgQ8x1X1JoHVL4vNkGOjmIdqeYMRtwGrzw98pZ4HjituumVb0u2Aa0l3VQnVQukNDHVMkFK10D/qNrHIsp5JA0wsbiZ2eSFbs55H5HP8LXdo7K/KLAFwWvnedvFBuVdw/1PY5xqOZsJ/CClxV5vE9tUdU31CfmhmzsTeYPJZ/AO2tMrY9HguvWehx2C28+KaxdaSXXMKDYSCN17EqMl28S63bFeJ3ah2Oqphqw37MC5w4mZawuLxP3eFotIZq/qV1ULVXPVn2JtDPKDImaq2rCZQNb7xKLBxE4Wy0k2x6tj4Ihz5J5Y3PAOscM9RDPVRbG4NDqIdQTx1eKeyq1cIaXB+9nzsFVf9spJbGIj4q7qpepbVT/Vb6qnsYh0sk7sCLH4L6LykKiML3g+eJ1EkurINbG9VNfFLj5BdY4fVXVsVgCDhSw5DxjY5+SFBm9a5CGRScNP7Ji+qqNi2XaWLdIR6lsSeK35nDyXHftw4plrYrFicW7uE2tgYLz6/7P1ilR+B/PBNudnr3lAHzDQfplvfHjkbSE/iSmqr9kMUM2u5Aj1LSsuH3Fg/DjpzDWxjvFiDfxFPs7V+eSFwHsovh07Womda0kMYEPKB4vLwG1h+8kPMUws9qrY+y9+r41FlGgrFl8tob4lgd3BTwzBAbE23Fi4NrFzYYFDKL+IfucCWzEacVscVu+NUnVFcCbsIg9nIp72SswV+y9+wnmw3Hucz5jIW0R+iH/ZUDaKXc85xX9UToP7mkYo/lLA8+kjVp/7iQWTxBr5Iyp/L+lPKxKBe6qlqsWqZao1Ut5ZnCU4fx11YjE/eZ77yuJfiwyS28KiYa8SY9mI+Fgs83T/B/H5lwb31ee4lNdxGcDzM2AGiR1i8PC8Fdiy0BC+396iuhD+wLB8Qh4+MuBjA854bNvYfjgGnBXrF2J6i8V86Qc0MIfEPmm6ezov5Z9CH0Z1/ns/jhBk48hjkNShjaRd4rBYQol28FAgh8nNDLGG8BkP2XB9M1K1R+y8rKM6H0zoMbHXMjxtjRUcT7+ofpcaPIVZwarilLvgA2CW2AfrgoKCgoKCgoKCgg+bN2IENXlI+PZQAAAAAElFTkSuQmCC>

[image12]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAABYCAYAAABI4au3AAAETklEQVR4Xu3dT6ilYxwH8Ne/QkLK1KDckpKSBalRkuTfSmKHhcQOJRtsJouxkMWUlMSQxUyyskCUxt8ViRILO9OQKPkzMTE8T+d5u8/99Z733HPn/HnPnc+nvr3P/T5nzr1nVr/e8573NA0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAkz0SAgAAAABM69WU/1IejRsAAAxHHtgAABgwAxsAwAAdLcc8rB2pNwAAWL76jNrhlOurnwEAGIB6YPN2KADAAO2v1u3AdmbVAQCwZHlI25Xyelkf2rgNAAAAAFM6kPJQLAEAGA4X3gMADFge1tqsbdwCAGAo+s6wvRaSv3tzX8pLKS9WjwMAYE5OSrkyljOwW2YWAOAE90Ysgr978lf1OAAA5qR9O/TYhnaxLpPeAAA0N8Ziwe6KBQAAw7EzFgAADMuka+gAAFiyr2IBAMCwPBiLysFYrIi3YwEAsKrWYrGN9N2MGABgZeRvSxhnOww8v8UCAGDVfBeL4vmUs2O5gt6PBQDAqrk1FkXf2bUbYjFwb8ViEy6JBQDAMqylnBzL5PGUPbGszHNge6cZndl7OeWWsLdVfcNnlzvLcdp/BwAwcwdjUeRBJX8h/TjzHNgeqNbfVOvjMe3g9VE55u9qBQBYql9jUUwacOY5sLW/+6qU0+qNDmfEYoz8nFv5PtBJ/w8AAHN3byyKvkFlR8ozKdfEjRlpf/cXzWhoa51ajn82o8fc3kwe6Fpvprwbywn+iAUAwDxdEYvk4pRTYln0DWzLdHXKwym/p+wPe33yNXlHY1nka/ieLuv2dedjGwCAhei6FuvzWFTGDSr1INM30OTBqi9d4vNuNV3y2bhxe481o73r4gYAwKJ83XQPKz/EotL1+FV2X9P/mvLwmvf/iRsAAIuQ3/LrGlbujkWl6/GrbG/Kz7FMzm82vtZj1RoAYKHyIJKv/dqs7TawfZjyXiyT05vRByh2pvwb9gAAFipfVF+fPTq3WnfpG9juKcdx16Idj8tTLmz67wG3Ffm15+cGABis+NbfC9W6S37stbFM7mjWb2x7c70xA082639j38DYyrf92KzNPB8AwNLloeWssv6x3uhwacr3sSymGaqmdaQcfynHaW7d0WcefysAwMzloeWmsn623hhj3JBTD2yH6o0ZaG/Ge1HKOSmflJ8/SDmvWR84X0n5qay/bCa/hXp/LAAAhuizlE+b0TA0acDJnkvZFcsF+zjltmY0sGX7yvFAyuGyzn9nn0lnEwEABuOCZnRW7Im40WPcWbZlyp/szNmsrpsGAwAMVh7Avo3lBLtjsULaa+EAAFZGvtdYvuv/NCbdAmSonooFAMAqmOZWGAAALEH+5CUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMAJ5X8gBe+IJ9+SigAAAABJRU5ErkJggg==>

[image13]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAwAAAAbCAYAAABIpm7EAAAAn0lEQVR4XmNgGAVDGugC8Twg5obyeYG4AYgnADETVAwO2IF4KxBHA/F/IG4G4gVQuXqoGArYC6VhGhqR5EA2YWgohdLXGDAls7GIwQFI4hea2HqoOFYAkmjHInYZTQwMJBggkiA3wwAfVEwByp+KkIJw0K1GFqsGYiUkOYa/QPwVWQAIChggGvSB+BKaHIMFELOiCzJAItQAXXAUDDwAAB7wIKu3dZmWAAAAAElFTkSuQmCC>

[image14]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACUAAAAaCAYAAAAwspV7AAABdElEQVR4Xu2UzSqFURSGF0IpYqBISQwUiYyI0RkYGCgXYGpAioGRjF2BZMKUkZkYyICBMhF3oLgA+Sn5e9/W+mqddc6Ro9MxsJ9623u9+2/t/e39iSQSiUTi17xAD9CZxXfQBfQJXWadqsk81A9Niibx4dr6zKs6b1ZuiSZQ49oGzPszuPhr8A7Mj8xFowy6o/EdXHyjiHcTvAZoMXjlsBaNUnSIJtDsvBbzeizehBqhR2hdCnc8BS0ELyfat9PiIdE5OTaOL4ALxs/kPe6uVzRpvtBVqM3ayDPUavVszI7z9q3kGLaz9OOL8g49BW9ZdIJh6Nr5p5L/+cYkf0Pn0DR0BF2Jvmz/eOLmS8KJ66MpetwjwWNSSy7mKXKhJqdaazu0Np/Ij5MqhxNoxeqzovclLtQF3bqYn5t3i2R9R62sCOOif3neMb5EwkR5B8m2lfeiP2ayB7Vb/RiagXYtrhh1kn9PMm/CxYNW8mpEeJKJxP/mC+w9RhN78HrsAAAAAElFTkSuQmCC>

[image15]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACwAAAAaCAYAAADMp76xAAABqElEQVR4Xu2VvyuFURzGv35LKFkMQgyixELIIJSJkgwGFmUgxWCS2aAsEkr+BatFBorYmAxGo5JI+f08fb8nx3HlXt101fnU03vO833Pe59zz3nfIxKJRCKRyC94gG6hA+tfQcfQG3TqbsoUJqF6qEs04KtXqzMvo3i267pouCyv1mheuqkMjd/AYI+Bt2N+yFhopMCUJH5myvAhSwm888DLh6YD78+pEA1X4nml5tVYfw0qgO6gRajKfI7tt2sPlGd+oejEeq3vaIZGrF0O9YluvVxo2N30EwwTLpPvLUC1ohPil2QeKrMaJ3YN3UDj0JP5HFvktR0NXp/1C+hEdIIkzJGQF+g+8GZFB/MfOfP8ffm6JXah5cBzYQmf479ofqgt0fGOpAK3y8dS+jRBLYHHwDOBxx+cCLwV0e/5gGgIt4WIH2pDdDUdSQVOhT1oztpDdmVgbgdHq3z+YbaroVGv79iEVr1+2gN3iJ5+3NP8YvBwuYS2RfcncS8sXyQeSqxzQoNQp9XaRLfJEXRoba40a92SZnLk8wHzHZxctrWL/UIkEvknvAMU3FPqP7CNpwAAAABJRU5ErkJggg==>

[image16]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAsAAAAYCAYAAAAs7gcTAAAApUlEQVR4XmNgoBAsAeL/OPAAAE0gfsMAsR5EEwTcDBDFpegS2ADIdJBiFnQJbGAlAwmhAFL4DV0QBkAmfQbir0A8iQGiuBZFBRT8AOK9SPwvDBDF7EhiYLAVKoEMlmERY+CCCi5HEweJHUATY0hjgEioo4mDxBzRxBhCoBLIIAVJLBWIlZDkwBKyULYGlA9T/AtKw4E8A0LBZKjYTyjfDKZoFJANAJmdLiD1Zgq/AAAAAElFTkSuQmCC>

[image17]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABIAAAAaCAYAAAC6nQw6AAAAwklEQVR4XmNgGCAghy5AKmAF4k1ALAHEz4H4Gqo08eAUEO9E4v8HYmEkPtEgGohrkPgggxyR+GQBGQaIQRQDkCHi6IKkgkdAzIkuSCrYB8SMUDYTECshyWGAYiD+CcR7GCBegGnsgvKRMU7gA8SfkfgfGCDRTjJ4D8S/kPg3GSAxRDLYxYDqdIqywyoGIsMBF5gLxB1IfJBryDIIpGk7El8dKkYy+A7E+UAsBMSJDBBDQGyyAA8QRwCxGrrEKBgF9AIA+Nco6TAYgVkAAAAASUVORK5CYII=>

[image18]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADsAAAAXCAYAAAC1Szf+AAABWklEQVR4Xu2WPy8EQRjG34SW6FUn0UnUGhLXkIhCxRcQhUhwPoFOIj6AUqGk0vlTaCQSFCLxAUgUIhGhEDzvvbPMPrfC3jLrYn7JL3fzPtm5nZuZ3RGJRCKtzCw8hWfwBPal4zrHcBfuwH04lo5bj1fnEwegEz7Aa9hNWRaXsIOLf4l7+Cw24DbKlDsufMGG2B/Xy0HZ9MMlOCw22L10XEfrzbAidu0gB2WxJR+zmSxn5ogLOZkX63eKg9D4g1tz7TmvNg1HvHYRJsX6X+AgFLwfeXavvO8/xZDYb+hnMHS/LlJNn6Z6IxXXzlrWRaiJ9TnBwW+zLY1PX33V6M3cuvahlxVhFb7AAQ5C8dmsJUtZDx1VyvKyCR9hDweh0cNCFuPSuHfzcgBvYBfVS0FnbJmLHs0OVo+d57CdgzKYEZvRZDAX6fiddbGzcCTyD0m2x3ccdddEIpFs3gBzE1F3Dg+6AAAAAABJRU5ErkJggg==>

[image19]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABUAAAAbCAYAAACTHcTmAAAA00lEQVR4XmNgGAVDEuwC4v9EYpIBPo2rgPg3uiAhwMwAMfAUugQU8ALxQXRBQqCEAWKoB5o4B5TmB+ImZAliwEcGTK9XAbEKlM0KxNxIckQB9PDUQuOTDGDhiQ2TDcoZIAb4IYnpAfFqJD4MSAHxX3RBbGA7A8RQASQxOyDORuKDwDwGSLIiygfYvKqDxocBRwZMtVgBSNEfdEEcgChDbRkgijrRJXAAvIbGMkByD8zrX4H4CBD3IivCAvAaSi4YGoYaAnE3A8RQMyDmQZUeBSMXAAB6XzyRT32hUwAAAABJRU5ErkJggg==>

[image20]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAAxCAYAAABnGvUlAAAEU0lEQVR4Xu3cWah1UxwA8CVDIcODIR48iEREhkwPJBKiiCTyJC9KUWZF4cGQlKmEL/EgU4bCg+F7MIQnUwgJichYxoT1b6/VXd/6zjn3O/ee+3Xd+/vVv73Wf+17ztn7nNr/u9Y+JyUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgGXkmxz/lviu5H5qcteVHKvbJn1iAb7OcWUaPlcAwJTiArp909+85FjdNkvD52DLfmCBfKYAYBH6C+kLOf7scqwuMcs6a4flOLtPAgDz2zsNBdvJOU7McULpH9PuNI/Y/6w+2WgLwrdy7Nf0V6LXmvZJOR5v+svdPzl275MzcH6O29L6/xwAABvg2xxvdLlpL6rzLZm1jzfusZ/KcVGfbByQ4+3SfqkdWIb649206VcP5/isTy4DP+Q4vk8u0v45Xiztem7WlKhuyXF3jttz3JzjzmYMAFa9uIBOun9t2zQUHFc3uWn1Bcw41/SJTv3bM9bJLq1TJsQ4G3q8k8amtW+fWKR30vyFeNg6rX9eatRCddz5ODPHo6V9V5Of5XkBgBWhvzj+nuPVpt+OX9K0W5MKqLjwX1/acf/Sm2lu+fS3HDfk2Kn0o2B7sLTDrzmezLFr6dfXcmrZhgdyfF/aMR6vpb3/7uc0zCLeW/oxg/RHacf+n+a4tvRn4bQ0vkBZm4bnurD0Y+z5HIeXfiwXX5HjnmY8Zpu+SkPx83HJxz4xFt/qrY8f2+NK+8sc75f2h2UsZlHj2Ke1R46/+uSUxp2PsCbHeUnBBgAj7ZPj7zRcHNeW3MulH4XAjSXXXjxvbdqt2CeWLEeJsYjTc5ybhuf4fJ095kTxEp4t25jtC21REmrBVvc/tmxrUXZZ2cYSW4iCaJs0FIjVTU17luIesHide6XhfEW7Fjzn1J2K/ri26vqflG24v2zrMbbvS9yHGKJgu6DJ94//XB3YyKLgjkI8Cs1R4vUp2ABgEb4o2/iJh2m+iFBNc/GN+5dCLcR+Kdu+8KgF2wdlW9UC7eImFzNsP5b2NK9loSY9x9Fdvz+uftse3+VlWwu39nliVi9EwXZfk+8f7+k6sAzF+1RNOocAwBhRCMTS2rTi3riYxRunLl0emuOIHK/k2DHNzSzFMt4OabiAb1e2e+a4I80Vj0fmOKi0X0/D4zyWhuIo7sGKHwZ+r7RD/QZn/BBsFH4Hl/6sTCo26tgjOQ4s/fpbZ3EvWB2PZdq4BywKzUNyHJWGL2XEscayaYh9t0hzS8jxHtWl51hCjb/bLc19Czjei49y7Fz2GeWhNOw7Kuoy8qzEbOMTTb8ee3wWoj3r9wUAGCOWQHfpkxtRW2S827SXSizhXtonl8ikwhAA4H8lZqtipq7ekL8SXJWGLxA80w8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKP9B2JA59IH3pATAAAAAElFTkSuQmCC>

[image21]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAAxCAYAAABnGvUlAAAEOElEQVR4Xu3cWaitUxwA8CVDIZEM8eANEZF5KGQoQxSRRB4kL0rxYHyg8GBIylTCTV5kylB4MNwHQ3gyhRCSiIxlTFj/vrXa66579j5n37OPe+49v1/9W2v913f23t93Tn3/s77v2ykBAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwj3+T4t8R3JfdTk7u+5GCxvs5xdRr+rgCAKcUJdLtmvHnJsbIc0idmzN8UACxCfyJ9IcefXY6V4YIc7/bJGTksx7l9EgCY315pKNhOzXFyjpPK+Nh2o3nE9uf0yUZbEL6VY99mvDF6remfkuPxZryhOCrHTX1yES7KcXta+58DAGABvs3xRpeb9qS6ZZ/otK837rWfynFpn2zsn+Pt0n+pnViG+v3dtBlXD+f4rE8uQ3fkeLJPTmm/HC+Wfj02q0pUt+a4Jw3vd0uOu5o5AFjx4gQ66f617XMc14zXRV/AjHNtn+jUnz1rjezSOm1CjLPQ/Z00N619+sQMfZ7Gr6BundY+LjVqoTrueJyd49HSv7vJz/K4AMBGoT85/p7j1S43n0kF1Ds5bij9uH/pzTQ6+f+W48YcO5VxFGwPlX74NQ2rO7uWcf2sp5c2PJjj+9KP+fgs7f13P6dhFfG+Mv4hxx+lH9t/muO6Mp6FM9L4AmV1Gt7rkjKOuedzHF7Gcbn4qhz3NvOx2vRVGoqfj0s+tom5eKq3vn60J5T+lzneL/0Py1ysosa+L9QeaTi2szDueIRVOS5MCjYAmNPeOf5Ow8lxdcm9XMZRCExz/1L8TFyynEvMRZyZ4/w0vMcXa2wxEsVLeLa0sdoX2qIk1IKtbn98aWtRdkVp4xJbiIJomzQUiNXNTX+W/knD59wzx22l/1eZO69uVPT7tVU3/qS04YHS1n1si5q4DzFEwXZxk+9f/7k6McGJafj6jVmKgjsK8Sg05xKfT8EGAOvRNCffuH8p1ELsl9L2hUct2D4obVULtMuaXKyw/Vj603yWdTXpPY7pxv1+9W27f1eWthZu7fvEql6Igu3+Jt+/3tN1Yoyl/lqPSeL3VE06hgDAGLHqMs1To1XcGxereOPUS5eH5jgixys5dkyjlaW4jLdDGk7g25Z29xx3ptHnOTLHgaX/ehpe57E0FEfxMER8MfB7pR/qE5ybpKHwO6iMZ2VSsVHnHslxQBlvVtq4F6zOx2XauAcsCs2DcxydhocyYl/jsmmIbbdIo0vIUazVS89xCTV+brc0ego4fhcf5di5bLO+xWrjE8247nv8LUR/1r8XAGCMuAS6S5/8H9V71cJSfbdYKy7hXt4nl8ikwhAAYIMSq1WxUldvyN8YXJOGBwie6ScAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgLn9B8rv29eeitY1AAAAAElFTkSuQmCC>

[image22]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAAAaCAYAAAAHfFpPAAACKklEQVR4Xu2XwUtVQRTGjyVIFoiaaIsE3YQV0iLoD3AjtJXatKhNIK4UF21btLMWBUVitGlhK7GMIBeB0CoqohYtWkSIG0EQQY1K/T5nru+88+7c97zvPejR/ODDme/Mvdc5d+6ZeSKRSCSFDmv8LzRBu9A7/5dqVI56HYq74pJAeqBFFWsUOsW9uDFo3Ld7i0ZkcAN6a80GgxM+p/qXvVcxHNxvzTrxF5q0ZhWMSvpk6Y1YM8SapN+kXpyBfkOPbSAHobpFb9maaVyTwk2+m1i96YbWodc2cAiyEpDmF8GH3/btbanggjpxDPoJfYGaTawcoYmG/AO+Qauqf1PcBayo16GnXi1qDJcsd4170BD00PenoAdqXF6OQJ+gFei4iYUITTTkH8DggOr3eS/ZEskPcUVLcwdqV/03UuZBOfkDPbFmCqGJhvx9bklpcDjFY4LoTSvvimqTV9CO8aphAdqATtlAgNBEQ/4+j6Q0+AzaMh4TcFrc2OSt2wS8FPe2qoFL/4O4qn3CxMrxXErnQuhxtabCQ4O9iH1+BprkE5mXwnibgBeSPwGt4orfR3FJyAMTxv9NH4HbvJfJLPQe6oK+iitslrOqzRvOSW0SwGdyB+LqqQVL4s4yCb+gGdXP5KqEs39etflrkUmYUB7hJGyhzGJT3O5Ray6IO0/ch06aWG4GTZ/F0C4tFkHrNTwsfFzun6X4MyD6bV8Ud3pkAi4pPxKJRCKRf5Q9pm6CgAGFIL8AAAAASUVORK5CYII=>

[image23]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACoAAAAaCAYAAADBuc72AAABQ0lEQVR4Xu2UPUoDURSFr4VYWLgHsbFIo51VmpBCyAJcgAtIFSHGRgNCQhCrNIqFjRuwcANCsLVPkSqQWPhHIuo5zBty586AzTA+yPvgg7nnzQwnL48RCQRyY80GvlGB73ACf+B3ctkfWC7mAJ6p2SuGsGxDH9mX5K56DYu+2tA3ruBMorKHZs0bWG5TXXt5BFjqWM0jl5FrpeYSdmDPzRdu7sJ+fFMWt7LYib/8dM+Qqss0NyarS/RNfVAZGZuZz5yaLDc+JF300WQsuu6yLZU/q2vC9ZbJcoMvH2RkbTWzKOHfqn9AVtGmyXLjDr6oeUXSOxwXJV/wyV0XWpSw6BHchnNYSi4niq5KVGhX/qEo4Rms2dChi5KGRKWyiuqvR+HYouRN0keE84nJCmMPTuE53FC5Pcu8j/M93FF5IBBYWn4BvlBXST9PnMEAAAAASUVORK5CYII=>

[image24]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAABBCAYAAABsOPjkAAAF3UlEQVR4Xu3dW6htVRkA4KEWplYaPomWZEQgKGJiplZbkdQuiogXEH3QMEgs9CFRlOxBqKAHRUWxByPRIvASoiLiebASRR8sFUW8QBYWXSgkFUWd/1lzssf+95xr7bP3Wuss1vk+GKwx/nlda2+YP3OMMWcpAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMvg2zkAAMDi+FL7+d6aKAAAC+OD9AkAwIKRqAEALLAnmnJPDgIAsDjcXQMAWHASNgCABfbVImEDAJbEkU3ZLQe3KPb3i6aclOLzTKD+VeZ7vB313xxYAP/PgR6HNOUTKdY9OmXIETkAALuSSEi+mdr/qNpd7JMpVvtVDjSOL2uTndjnq1V7yEfK+iQpt99M7VmJ4/4yBzdo/zLa/jNN2aspn2rb59crDXg/B+bsoLL6N9+nKYe37UluzIExIhmufTm1axc05X85CAC7krgQH121/92Ud6v2JP/JgdZLTXk8xTZy0e9bJ2ZpRsLTea2qz9KkRHWSvu8SCek4V+XABG/lwBQc1ZSfpdi3UrtP3/cd55mqfmxVz/5exid0ALD04iJ7TdW+ro113q7qfYYu0jkeSVeOZUPL42J+d4o9mdrTdlwZPp+NuL+sTXy/U9XH6TtmbHtiUz7elJvTsr71t6re58Pt54FVrM+FZX33dbiz/Yy/4dX1grL2OHFHNruprN7t68Qdv5+29e815evVMgBYWnEx/F1bf6MpZ7axcFj7Oc6zOdCqL7LRrfi3qj1kKPn4Q1NWUmxo3VfHlD9V600SdwiHjrERse2fm/JoW9+ovG7X/klZ7Zr8/Ori7Xefpi2O8VBTXm7rWXT3Zn3j6fZrP7t95H3V7ZjgUeuWRXKWtwtD+wSApRSJSXfRj7FWB5fVi2CXyIUrqnjns6V/jNe5Zf26k5xdhrfpi/fFpin2v5Vj1NtGN3MtukUjAQv5/aRDx+zGcH1sTbSUB3tiIZLt6NrsK3Gnbpz6HC6p6uG7Vb2+yzl03qFbls+z7s79WlV/rCl3tfWLm7KtrXdd93uU8ccDgKUTXVZx8asHukf7lqrd+XFqx4X/3hQLsf3tOThBNyg/i2P0xfti0xT7/3kObtBHy9rzy92h91X1SJZj/c7Q9xqK/7FMd4bulWX4WDlet/OyTsz+/EsOtuptVqp63m9O9CJJvSjFAGCpXVbWX2yj/Y0UCzlhC30X47y/Pj/IgbK63TtVfWhfQ/Fpif3HnZzNeKSMn7jRnfveZfToklr+Xvl3OKtb0Jo0xnBHxXG6MWK1A8poTFmtPtd6AkGI7tDPldHf8tA29tzq4u3q7Veqeh3v6nEn99IUy3UAWFox2PvpFBu6CPYlbHndF9vYUylei0QlbxdiJmA3s/S8sr67sLNvU27LwSmKRKPv/DbigTLaNs59W1rWGbfvvOzyMnq2WcRjIkSerZnX34r4P4j9/bOsf/xIdI/nO3nPV/X4zeLuXCcexfGFppzRlF835ftN2bNaHupzX6nqtzbllDL6DWOdU9v4K2XU3R6TF2K/Q78vAOzS+hK2epzbjjg5B5IYWH9HGY2Ty+Ooppmk9Plrmd0xjmnKOTlY+WJZ+5iVSa7NgRmKO4cHt/W+ySY78pvFxIWVql3XAYAZ2Ey3XFz8J4kEICcBu5fR3ZdZimPGLMmdJX/nISfkwBzEc+L6HpQcPl02/kaC/B1XUhsAmIF5DQL/fQ7MQCQTk2ZSzlo8b2ySeATLzhC/T9/YxVDPIh0SjzrJvpIDAADj5Ls/AAAsGAkbAMCCi1mSnd805bdl9FiJrbxXFACAKbkhtU+v6vHMtNerNgAAO0HuDq0fIBzPhvtR1QYAYE7i3Z5dojaUsJ1W1r7vEgCAObu+jF6dFG9hqEWiFuJ9n5t9VRUAADP0w6r+QpnvmwUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA240PPZBy6g9vlFwAAAABJRU5ErkJggg==>

[image25]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABIklEQVR4XmNgGAVDDUQC8RYiMUWAFYjFgfg/FIsBMTcUCwNxBJIcVQDIoD/oglBgB8QP0AXJASYMEIs60SWggBGIF6ELkgNA4Q+yiAdJTI0BEn8goAjEiUhyZANscXAHjU8VALNoBxAfQOJTFZgxQAydAMQsQCwIxGuA+CWyIiiIBeI5QDwPiOcC8Qwg7kJRgQdsZ4BYJIAkBkpl2Uh8ZFANxL+R+GwMEP3sSGJYAbZg0kHjI4MPQNyBJgbSD/IpXoAv/2AD6KkTJgbK3DiBLQNEEa78gw5A+QnZ90YMEEe6IImhAFCknmJABNtXID4CxL3IirCAAgaIemsgtgBiWVRp6oH3QDwTXZAWAOQbCXRBagJJIA5mgFhkiSY3CkbBIAIAx/RBhq+PNEQAAAAASUVORK5CYII=>

[image26]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAABSElEQVR4XmNgGAVDDUQC8RYiMUWAFYjFgfg/FIsBMTcUCwNxBJIcVQDIoD/oglBgB8QP0AXJASYMEIs60SWggBGIF6ELkgNA4Q+yiAdJTI0BEn8goAjEiUhyZANscXAHjU8VALNoBxAfQOJTFZgxQAydAMQsQCwIxGuA+CWyIjRQBcQ/GCD6pqDJ4QTbGSAaBJDEQKksG4kPAyIMELUcSGIgdZ+R+DgBtmDSQePDAEgdyNfoACQOyo94AUgRrvyDDN4D8WJ0QSgAmeGNLogMbBkginDlH2SA7mtkAJIDxS0GiAXiUwyIYPsKxEeAuBdZERJIYcBtESiYccmRDIIZcBv2loGElEcIMDMgLAoC4ltQthsQv4KyqQY2MEDyVz6UvwuItyKkqQtAVUg5A6TcewgV40NI0wbAEtFzdAlqgwogvoguOAqoAgCbs0w0frLT6gAAAABJRU5ErkJggg==>

[image27]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAmwAAAA5CAYAAACLSXdIAAADoUlEQVR4Xu3dS+htUxwH8DUQ5ZUYSG63m5EJE/J2HWakGJkwkZKUmRTFzIAMmFz3DgykW1KKQhl4DeQRkpKUEkqUyEzKY6322lr/39l7/8++53/7n5PPp37ttb5rP1bnP9ir89j/lAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAgP+zy2Jwgl6PwYCvY7CPHorBgKH5/hMDAGC7lJv5XbV9ce0v/hvdTFfHIDuQurmfneuMXJfW/pipsWjOvqu6KNdfuc7KdWaua9P0dV6IwYSbQ3/qvADAFhi6mQ9lm+SaGGSXp+V53xr6rWdiMGHOYmlVD+a6JWRPhX6vLEDniK9D7AMAW2boZj6UbZLrYpD9nuvD2r63bu+u2+iXGOyD9jU+XrfPN1lr7t/ji9CfezwAsEGO5Pojhmlvb/Dlo8pef96nm/ZjTfvC2v471zm5juX6rY61ro9B6o4rHy/27Slx/Pxcl+R6oI4dSsvvdj0c+uvq53Ba0x4Tx3ebb3kHsp1vPB4A2CLlRr6IYdrbG/zLuc6t7fYdr/YaY+2hfnFDDFK33ym5Dud6KYxF8Zyf1+2VdftZrtNru/da6K+rzOHUXHfkuj+MRXPnWxaB7Xzj8QDAFhm6kZfsxhiu6dHUnXdsYTbWHuoXi9Av7yYN7TdmbN+xvHg7Bmt4M3U/OIg+rtsXc53X5GPzGsvLQrCd79h+AMCGO5SWb+Sv5nojZOt6p2n/2bTHFmlxTrFfLEK/7PNEyKbEc/b9mLceicEaynXiLzlb5XEjUwu23eZ7Vdo537H9AIANVhZR5SZeviv2Qa6Par/9vtleeTd131O7IC0vzMr31L6v7V+b/IfUPWLkp1zP1by1aNqfpu6Y8kOCt5p8Sjl/66tcr+T6NtfBXO/tHN4z5WPL8nFmme93qXv0yJD+I89eXHDtNt/ymrTi8QAAa1llcbGIwUzlMRmPx3DC0RicRP0vPMt38XpXNO1VxNcw9gEA1rLK4mIRgwnlESC3xTCtdp3enH3X8WTqrjV0vTmLxttDf+h8AAAn1dBjPU7EKg/E/TEG++ieGAwYmq8FGwAAAAAAAAAAwLJnc/2c6/1c34QxAAA2xH11e9OOFACAjVD+F2b/C8ZP2gEAADZD+X+Xd+b6Mg4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAc/wLDNGwnXHQ6rgAAAAASUVORK5CYII=>

[image28]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAkAAAAXCAYAAADZTWX7AAAAmElEQVR4XmNgGAVUB1+B+C0QnwFiQSD+D8SXoDQLSIEbEDsDsRJU8AFIEAqOAvE/EOMLVKCLAaIIGXSji/1GFwCCh+hiIM50ZAGoGFwRN5QjCZdmYGCHiuXDBNqhAsjgERB/QxaAuecDA8TUjUD8ClkBCIAUzAJiZiAOA2J+VGmIAEiRLLoEMpjEgOkeDADzJgibo8lRGQAAez4nzZtaa9kAAAAASUVORK5CYII=>

[image29]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEIAAAAXCAYAAAC/F5msAAABK0lEQVR4XmNgGAWjYBSMglEwqEAAEF9CFxxJIBeI/wNxNLrESAGdDJAAcESXGClgKRD/BmINdImhAL4C8VsgPgPEggyQmATlZxDNgqQOHzgAxB+AWAxNfMgANyB2BmIlBojHHyDJHQXif0h8bOAkED8BYk50iaEGvkDpLgZIQCCDbixi2MB8Bkh20EKXGIoA5BF0Tz/EIoYPtDFA1DugiQ8pAPLAdCxipAQEDGQxQPRFoUsMdsDNAHG4JJIYO1QsH0mMVODHADGjGF1isIJ2BsyYfwTE39DEyAVGQPwXiMvRJQYbgJUPoOoPlDo2AvErFBUjBIACYRYQMwNxGBDzo0qPDADyNCggZNElRhqYxIBZPpACQGUJrHYhhEGNr0ELkB1qjiY3CkbBCAUA/f9GFj5+T1MAAAAASUVORK5CYII=>

[image30]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABcAAAAWCAYAAAArdgcFAAAA60lEQVR4Xu2QvwqBURjGn2Ji4TLMbkNGZTP7k5iVm7C5ADIY7JTFBSAZTSalZPAn8b7nO1++3t4TJyWDXz3D+T3nPMMB/vwKMSneJC1FCA+2KHdKWXSvuFI6lAKC95VouaYMKXlb+ozfKH3heCMlnMFnPI7gvoTdUkrGZ7wLfXwH3XuNb6CP8Ddr3mv8DH1kAd0bWZXSwQX6yBy6N7ImpQPXyAq6N7IupYMB9JEtdG9kQ0oHGegj7E5SMlw0pbRwt1dcUXGl8NCmTClHW3BmlHF4wRJ2UXLWJe15Qjk8689JUHqUESUruj9f5AGE1UTzwF9wUwAAAABJRU5ErkJggg==>

[image31]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFwAAAAaCAYAAAA67jspAAADPElEQVR4Xu2YW6hNURSGh1uuodwe3OPNJSUipeRBUqQ8KJTyhBeUjiihlOQWJSKdUnJLXhBCbg9EuZQk6QjJi0JuEcZvztkZ+z9zrb32PqvOOTW/+mvNf8y19lpjzTnWnFskkUgkEh2dB6prqkuqG6qH3u+puuv9i6rrXoELqtveu6laZmLthaFsFKSLV4zebHh6sJHHX6+JHJDm2CjyO6nuiYtNoVhb80HcgJin+q46XBnOZIC451mtWuuPR1T0ENnqfei3OeZ+ubwRd1KMcMEYr9hoB7xUNZGH+59GXgz0G2faeGH87Nu8F4SX27WiRwFQUnByd/IxirMSPlC1n80aQbk6x2Yrwb3yjHuu+kMes1LizwlvkWlvVs0y7brAlOO3C96pnvkY84uNOummeqF6KnWMFGKJuHvF98dy1vt5ZA0seG9Ne5OUkPD14i4833jDVTvE1ULEBpnYHNVc0y6LO+KmaH8OFKRR4kk7JHHfkpdw628Ul/BV4gbJHhMrzEJxF11nvDAFD/jYdBMra3RncVr1QzWGA1W4LPGkhWfgkW/hxAbYb/DtMACxOkO7ptk5QdxJB317sWqmP17jY0t9e5+4+p1FvaMzBhKFF881OYsrEk8avjXwh3DAwIkNsD9WWr44xD+Tl0svcSdd9W2MrgDKDGJbfBv1lumrOi+u306KlcF9iSeDCYllMJBivoUTG8jyLUX6tAAnNKmOiktgAB9SxI6Lq1l5YANUZsI3iPvtBRzIAHUV/XnTcsL7eWQljX0shZebNkCJjZ2bS7jwE/KxVISPpdURijFlJRxlC6VkKgeq0FncvY4n/5H38zgl8T7wtvvjPr79tTn8H34phcg7KS9maW3Cz6i+qUZyoAZwn7yzhNdo2tgVwsMqLBCSaWdHP+9ZYgsG9MHfIDWBk/ay6UHMLv6zQMJ3sVkA/CfzXipLWb2EZI72bTwTb3pmiOuD747lluqjaf8UV2ItK1SPVcNUg1WfVF8qehQEu80swse0Gkj4bjZzwPIPJYxrbmvBDvmYuD/jZlOsGpPE7YDxAc5ajWHknxQ3I7EnaTOQ8KxZkiiZyarX4moZRkkikUgkEolEokPwDxpw3ulC4FupAAAAAElFTkSuQmCC>

[image32]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAF8AAAAaCAYAAADR2YAqAAAC/UlEQVR4Xu2YS+hNURTGP+/XACWiKEykpBgwIH+JkhIThSikUCL/gcRIIY8oeWWilIEMvDL0GKCUgUyVEJE88yrv9bXPZt119z7n3nN1dG/7V1/37G+tfe7Z6969z9kHSCQSiUSiMxlgjQYZaI0Iva3RiSwS3bdmhJ6iX6LtojXZ8ayajDhT4PJXinaJfor61WQ4Bosuw+V2LBvhBrjcBnJg/jrVHpF5RfSAy9PF3i/6rtrkveiY6CgaO2/bsRduYLNtoICJCBeE3hFrGs4i3ne4NYUtCOe3LWdE30QTbKBBHiBcEHohXxPLocfrspQu/ifRa9Fd0VC4k3BN5ef/uIncEL1D+B/WDHkFDPkaxlkXC/1n1kTJ4s8TzRGNg+v8SMVuwd1kquKO6CnKP5VYYkWO+RrG31oT8b6liv8x+9yH+s68wdCbLjqUtQ+K1mbxGVn7gGhV5pEroi+im3CPaZNUrIhTcEsN1+tWiRUq5msqKb6HA7adHxvPxslXUV/Vfijqr9qf0VzxPbvhvq/L+M0QK1TM1zD+wZqI/ygtFZ8djwe8vOK/MW1ic7islSm+ZwPcOZfZQAO8RP31EDuuELEceretiRaKPwiu40jl8fmW3ibl6ZO/Usca5nDt1oQ2Js2yEO7c3TaQw3qEC0KP97M8niPed6410ULx96C+4xO4JUPjc7jRsPmeUXAxr/m14ZbhrvOHaKsNROA1jAl4Y1V7ceYtUB4fQuwYZwY8T+ni+/Wej3ecBRfhpqyFOfxR/DE3IjEmiy7B5XXVhirF/7G4YyW8fvtqgq8emLPZ+C9E97LjPnA5fNWguQo3i/yfjQ8a10XbdFIe7HRS1Eu0BO5dRQj9y/r9wDDlkdWmfQL1g60aLqfnRadF402sCM6Ga6Kd+HePwH9goVnE0TYQwE6rcwGPu0oNp+8F4yUyDqO+gJYhcG8CmbcCf9dQvy5yZzw18/ws8nBJ81O+CC4JfvoWyd7U2xI9oGkmVgbecMlS0Q4dSCQSiUQikaic31QB4tbV7RF3AAAAAElFTkSuQmCC>