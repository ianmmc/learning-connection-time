<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# A data pipeline uses a cheap deterministic classifier to decide which candidate documents get sent to an expensive LLM extractor. The extractor's success/failure is fed back to tune the classifier. This creates survivorship bias: the classifier only ever sees outcomes for documents it already approved, so it can entrench a wrong rejection of a whole document class. At small scale (~440 labeled examples, ~20,000 target entities, no high-traffic online serving). What are the established techniques to correct for this selection bias in a human-in-the-loop-becoming-autonomous system — exploration/exploitation policies, off-policy correction, propensity weighting, selective-labels debiasing — and which are viable at this scale? Cite the literature (e.g. 'The Selective Labels Problem', counterfactual evaluation).

I now have sufficient material to write a comprehensive, well-cited answer. Let me compose it.

This is a rich, well-scoped problem that sits at the intersection of several mature literatures. Here's a structured treatment of every relevant technique family, with an honest verdict on what's viable at your scale.

***

## The Core Problem: MNAR-Induced Survivorship Bias

Your pipeline creates a textbook case of data **Missing Not At Random (MNAR)**. The classifier acts as the assignment mechanism: only approved documents ever receive extractor feedback, so the rejected class is permanently unobservable. Lakkaraju et al.'s "The Selective Labels Problem" (KDD 2017)  named and formalized exactly this structure: observed outcomes are a consequence of existing human/algorithmic decisions, and comparing model performance on that selectively-labeled data "can lead to erroneous estimates and wrong conclusions." The credit-scoring literature independently calls it **reject inference** — the challenge of inferring how rejected applicants would have behaved  — and documents that the bias is specifically MNAR: the probability of seeing an outcome depends on the unobserved outcome value itself.[^1_1][^1_2][^1_3][^1_4]

The key consequence at your scale: with ~440 labeled examples drawn exclusively from the approved set, your classifier has no gradient signal from its own mistakes. It will systematically overfit the approval region and entrench incorrect rejections.

***

## Technique Family 1: Forced Exploration / Randomized Auditing

**The idea.** The cleanest fix is also the simplest: periodically route a random sample of classifier-rejected documents to the extractor anyway, regardless of classifier score. This is the ML equivalent of a **randomized audit trail** — it ensures every region of document space has nonzero probability of being labeled (the "positivity" assumption required by all downstream corrections).

**The literature.** Wei (ICML 2021)  shows that under selective labels the optimal decision policy in the online setting is a **threshold policy that becomes more stringent as labels accumulate** — but critically, it requires an exploration phase to bootstrap. Swaminathan \& Joachims (ICML 2015) demonstrate that if the logging policy $h_0$ is deterministic or near-deterministic, counterfactual learning is provably impossible even as data grows without bound: "if $h_0$ was deterministic, or even stochastic but without full support over $Y$, it is easy to engineer examples ... that guarantee sub-optimal learning". **You need stochasticity baked into the classifier's routing decisions.**[^1_5][^1_6]

**Viable at your scale?** Yes — this is the highest-priority intervention. Even a 5–10% random pass-through rate on classifier rejections, sustained over time, yields labeled negatives from the previously unseen region. At ~20,000 target entities, a 5% audit across rejections will generate meaningful coverage quickly. The cost is bounded (you know exactly how many extra LLM calls you're making), and it breaks the structural impossibility of learning from fully deterministic filtering. Epsilon-greedy is the degenerate-but-effective version: route documents with probability $\epsilon$ to the extractor regardless of classifier score.

***

## Technique Family 2: Inverse Propensity Scoring (IPS) and Counterfactual Risk Minimization

**The idea.** If you have the classifier's output score (or probability) at the time each document was approved, you can up-weight outcomes from low-probability approvals and down-weight outcomes from high-confidence approvals. This is **Inverse Propensity Scoring (IPS)**: reweight each observed outcome by $1/p_i$ where $p_i$ is the probability the classifier assigned to routing that document to the extractor.

**The literature.** Schnabel et al. (ICML 2016)  developed the IPS estimator for selection-biased recommendation data (MNAR ratings), deriving that $\hat{R}_{IPS} = \frac{1}{N} \sum_{i: O_i=1} \frac{\delta_i}{P_i}$ is unbiased for any probabilistic assignment mechanism, and that a **Self-Normalized IPS (SNIPS)** variant reduces variance at the cost of small bias. Joachims, Swaminathan \& Schnabel (WSDM 2017)  extended this to a propensity-weighted ranking SVM and showed robustness to propensity model misspecification. Swaminathan \& Joachims' **Counterfactual Risk Minimization (CRM)** framework  adds a variance penalty to the IPS training objective:[^1_7][^1_8][^1_9][^1_10][^1_11][^1_5]

$$
\hat{h}_{CRM} = \arg\min_{h \in \mathcal{H}} \left( \hat{R}_M(h) + \lambda \sqrt{\frac{\text{Var}_h(u)}{n}} \right)
$$

This penalizes hypotheses whose importance weights are highly variable — a critical property when $n$ is small.

**Viable at your scale?** **Partially.** IPS is viable if and only if (a) you've been logging the classifier's output probability for every document it processed (not just the approved ones), and (b) you've implemented forced exploration (above) to ensure all rejection strata have nonzero propensity. Without logged propensities on rejections, you can't compute $p_i$ for that stratum and the estimator is undefined. With 440 examples and high propensity heterogeneity, IPS variance will be large — the SNIPS variant and propensity clipping (cap extreme weights) are important mitigations. The CRM variance penalty is especially suited to your scale precisely because it discounts estimates with high uncertainty.[^1_7]

***

## Technique Family 3: Doubly Robust (DR) Estimation

**The idea.** Doubly Robust estimation combines an IPS re-weighting term with a reward/outcome model. The key property: the DR estimator is consistent if **either** the propensity model **or** the outcome model is correctly specified — not both. This redundancy is particularly valuable when either model is uncertain, as it will be with 440 examples.[^1_12]

**The literature.** Dudík, Langford \& Li (ICML 2011)  derived the DR estimator for contextual bandits and proved it "uniformly improves over existing techniques, achieving both lower variance in value estimation and better policies." The estimator takes the form:[^1_13][^1_12]

$$
\hat{R}_{DR}(h) = \frac{1}{n} \sum_i \left[ \hat{\delta}(x_i, y_i) + \frac{(\delta_i - \hat{\delta}(x_i, y_i)) \cdot \mathbf{1}[y_i = h(x_i)]}{p_i} \right]
$$

where $\hat{\delta}$ is a learned reward model. In your setting, $\hat{\delta}$ would be a learned prediction of extractor success given document features, and the IPS correction handles residuals.

**Viable at your scale?** Yes, with caveats. At 440 examples, the outcome model $\hat{\delta}$ will itself be uncertain, so DR does not give you full protection — but it is still more robust than pure IPS when propensities are near-zero for some strata. A practical implementation: fit a logistic regression to predict extractor success on your labeled set, use it as the reward model, and apply IPS correction only on the residuals. This reduces the effective weight variance.

***

## Technique Family 4: Positive-Unlabeled (PU) Learning

**The idea.** Reframe the problem: your labeled set contains confirmed positives (documents where extraction succeeded) and confirmed negatives (failures), but the **unlabeled pool** of classifier-rejected documents contains an unknown mixture of true positives (documents you wrongly rejected) and true negatives (legitimately non-extractable). PU learning treats this as a two-distribution problem and corrects for the unlabeled class.

**The literature.** Bekker \& Davis (2020)  survey the landscape. The key insight is that you can estimate the **class prior** \(\pi\$ (proportion of positives in the unlabeled pool) from the labeled positive distribution and treat the unlabeled set as a noisy negative set with known contamination rate. Hsieh, Niu \& Sugiyama (NeurIPS 2018)  specifically address the **biased negative** case — where the negatives available for training are not representative — which is precisely your situation. The nnPU (non-negative PU) estimator  stabilizes risk estimation for small labeled sets by preventing the loss from going negative during optimization.[^1_14][^1_15]

**Viable at your scale?** **Yes — this is one of the most directly applicable frameworks.** PU learning requires no propensity logging infrastructure. You need only: (1) a labeled positive set (extractor successes), (2) access to the unlabeled rejection pool's features, and (3) an estimate of the class prior. With 440 labeled examples, use the two-stage approach: first estimate $\pi$ from your positive label set's distribution (several methods require only a few hundred labeled examples), then train a PU classifier. The nnPU formulation is specifically designed for limited-label regimes.

***

## Technique Family 5: Reject Inference (Credit Scoring Analogy)

**The idea.** The credit scoring literature has studied this exact problem for decades under the name "reject inference." Standard methods include: **(a) Augmentation** — assign soft labels (expected outcomes) to rejected cases using a model, then train on the combined set; **(b) Reweighting** — up-weight accepted cases to represent the full population; **(c) Semi-supervised / EM approaches** — iteratively impute outcomes for rejected cases and re-estimate the scoring model .

**The literature.** Anderson (2012)  provides a Bayesian bound-and-collapse framework specifically for MNAR reject inference, noting that "the increase in prediction accuracy should not be considered the main goal" — the goal is correcting population representation. A Bayesian network framework  formalizes MCAR/MAR/MNAR cases and maps them to learning algorithms across epidemiology, econometrics, and clinical trials literature.

**Viable at your scale?** The **augmentation/EM variant is viable at your scale** with low implementation cost. You already have a classifier — use it to generate probabilistic "soft labels" for rejected documents, then include them in retraining with weights proportional to confidence. This is a noisy but tractable approximation. The key caveat: if the classifier is already badly miscalibrated on a document class, augmentation will propagate that error — so pair this with Platt scaling or isotonic regression to calibrate classifier probabilities first.

***

## Technique Family 6: Weak Supervision / Labeling Functions

**The idea.** Rather than relying solely on extractor feedback as the label source, define multiple **labeling functions** (LFs) — rule-based, regex-based, or heuristic functions that noisily label documents without sending them to the LLM extractor. Use these LFs to generate probabilistic training labels for the classifier on the full document corpus, including the rejection pool.

**The literature.** Ratner et al.'s Snorkel framework  provides a generative model over LF outputs that denoises conflicting signals and produces probabilistic labels. Crucially, this can be applied to the unlabeled rejection pool — breaking the feedback loop entirely by generating labels that don't depend on the extractor.

**Viable at your scale?** **Very viable.** At ~20,000 target entities with only 440 labeled examples, you almost certainly have interpretable patterns you can encode as LFs (document structure, metadata, source type). Even 3–5 LFs with 60–70% accuracy each, denoised through a label model, will substantially increase effective training set coverage. The Snorkel approach is specifically designed for exactly this "lots of unlabeled data, few true labels" regime .

***

## Technique Family 7: Active Learning on the Rejection Pool

**The idea.** Instead of random exploration, prioritize which classifier-rejected documents are routed to the extractor based on uncertainty: query the LLM extractor on the documents where the classifier is least confident. This is **uncertainty sampling** from Settles' active learning survey .

**Viable at your scale?** **Useful as a complement, not a replacement.** Active learning maximizes information per LLM call — important if extractor cost is the binding constraint — but it creates its own selection bias: it preferentially labels near-decision-boundary cases. The resulting training distribution will underrepresent high-confidence rejection regions. The correct combination is: **uncertainty sampling for most queries + forced random exploration for a fraction** to maintain coverage. At 440 examples this is a meaningful efficiency gain.

***

## Scale Viability Summary

| Technique | Core mechanism | Requires log of propensity? | Viable at 440 labels / 20K entities? | Priority |
| :-- | :-- | :-- | :-- | :-- |
| Forced random exploration | Stochastic routing, breaks MNAR | No | ✅ Yes | **Highest — implement first** |
| PU learning (nnPU) | Unlabeled pool as biased negative | No | ✅ Yes | **High** |
| Weak supervision (Snorkel LFs) | Noisy heuristic labels on rejection pool | No | ✅ Yes | **High** |
| Reject inference / EM augmentation | Soft labels via current model | No | ✅ Yes (with calibration) | Medium |
| IPS / SNIPS | Re-weight by approval propensity | ✅ Yes (must log scores) | ⚠️ High variance; clip weights | Medium |
| Doubly Robust (DR) | IPS + outcome model | ✅ Yes | ⚠️ Outcome model uncertain at 440; still better than IPS alone | Medium |
| Active learning (uncertainty sampling) | Query near decision boundary | No | ✅ Yes (pair with random exploration) | Complement |


***

## Practical Sequencing

**Immediate (no infrastructure change):** Implement forced random exploration at 5–10% of classifier rejections. Log the classifier score at routing time for every document, approved or rejected. This creates the counterfactual data infrastructure that all propensity-based methods require retroactively.

**Short-term:** Apply PU learning against the existing rejection pool using nnPU or the two-stage approach (class prior estimation → biased-negative classifier). Write 3–5 Snorkel-style labeling functions on document features and run them against the full 20K entity pool to generate probabilistic training labels independent of the extractor.

**Medium-term (once you have propensity logs):** Implement IPS/SNIPS re-weighting on the classifier's training objective with propensity clipping to manage variance. Upgrade to a doubly-robust estimator using a simple logistic regression reward model as the outcome predictor.

The Lakkaraju et al. framework's "contraction" method  — exploiting heterogeneity across decision-makers to estimate model quality without counterfactual inference — is worth reading for evaluation even if you can't implement the full correction: it gives you a bias-robust metric to tell if your de-biasing interventions are actually working.
<span style="display:none">[^1_100][^1_101][^1_102][^1_103][^1_104][^1_105][^1_106][^1_107][^1_108][^1_109][^1_110][^1_111][^1_112][^1_113][^1_114][^1_115][^1_116][^1_117][^1_118][^1_119][^1_120][^1_121][^1_122][^1_123][^1_124][^1_125][^1_126][^1_127][^1_128][^1_129][^1_130][^1_131][^1_132][^1_133][^1_134][^1_135][^1_16][^1_17][^1_18][^1_19][^1_20][^1_21][^1_22][^1_23][^1_24][^1_25][^1_26][^1_27][^1_28][^1_29][^1_30][^1_31][^1_32][^1_33][^1_34][^1_35][^1_36][^1_37][^1_38][^1_39][^1_40][^1_41][^1_42][^1_43][^1_44][^1_45][^1_46][^1_47][^1_48][^1_49][^1_50][^1_51][^1_52][^1_53][^1_54][^1_55][^1_56][^1_57][^1_58][^1_59][^1_60][^1_61][^1_62][^1_63][^1_64][^1_65][^1_66][^1_67][^1_68][^1_69][^1_70][^1_71][^1_72][^1_73][^1_74][^1_75][^1_76][^1_77][^1_78][^1_79][^1_80][^1_81][^1_82][^1_83][^1_84][^1_85][^1_86][^1_87][^1_88][^1_89][^1_90][^1_91][^1_92][^1_93][^1_94][^1_95][^1_96][^1_97][^1_98][^1_99]</span>

<div align="center">⁂</div>

[^1_1]: https://www.kdd.org/kdd2017/papers/view/the-selective-labels-problem-evaluating-algorithmic-predictions-in-the-pres

[^1_2]: https://www.hbs.edu/faculty/Pages/item.aspx?num=57970

[^1_3]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9041715/

[^1_4]: https://www.tandfonline.com/doi/full/10.1057/jors.2011.149

[^1_5]: https://www.cs.cornell.edu/people/tj/publications/swaminathan_joachims_15b.pdf

[^1_6]: https://proceedings.mlr.press/v139/wei21a.html

[^1_7]: https://www.cs.cornell.edu/~schnabts/downloads/schnabel2016mnar.pdf

[^1_8]: https://arxiv.org/abs/1608.04468

[^1_9]: https://dl.acm.org/doi/10.1145/3018661.3018699

[^1_10]: https://proceedings.mlr.press/v48/schnabel16.pdf

[^1_11]: https://dl.acm.org/doi/10.1145/2740908.2742564

[^1_12]: https://arxiv.org/abs/1103.4601

[^1_13]: https://www.semanticscholar.org/paper/Doubly-Robust-Policy-Evaluation-and-Learning-Dudík-Langford/5ccf7658018981bf492d0c8d66277d22ebaac815

[^1_14]: http://arxiv.org/pdf/1811.04820v3.pdf

[^1_15]: https://arxiv.org/pdf/2002.10261.pdf

[^1_16]: https://dl.acm.org/doi/10.1145/3097983.3098066

[^1_17]: http://proceedings.mlr.press/v139/wei21a/wei21a.pdf

[^1_18]: https://arxiv.org/pdf/1807.00905v1.pdf

[^1_19]: https://www.slideshare.net/slideshow/paperfriday-the-selective-labels-problem/120816442?nway-=

[^1_20]: https://arxiv.org/html/2306.07566v4

[^1_21]: http://ai.stanford.edu/~wzou/aggregating_main.pdf

[^1_22]: https://blondon.github.io/publication/buchholz-sigir24/

[^1_23]: https://proceedings.neurips.cc/paper_files/paper/2023/file/df927a06a0d9f5f06d9cd4a91ce58e56-Paper-Conference.pdf

[^1_24]: https://cs.stanford.edu/people/ebrun/Brunskill_RLDM_Tutorial_2019.pdf

[^1_25]: https://www.cs.cornell.edu/~adith/CfactSIGIR2016/Evaluation1.pdf

[^1_26]: https://dl.acm.org/doi/10.1145/3534678.3539295

[^1_27]: https://www.cs.cornell.edu/~adith/thesis.pdf

[^1_28]: https://www.cs.cornell.edu/home/kleinber/kdd17-selective.pdf

[^1_29]: http://jmlr.org/papers/volume24/22-067/22-067.pdf

[^1_30]: https://arxiv.org/pdf/1605.06955.pdf

[^1_31]: https://link.springer.com/article/10.1007/s10994-017-5678-9

[^1_32]: https://lirias.kuleuven.be/retrieve/709258

[^1_33]: https://arxiv.org/abs/1810.00846

[^1_34]: https://openreview.net/pdf?id=jJis-v9Pzhj

[^1_35]: https://www.cs.cornell.edu/~tj/publications/wang_etal_19a.pdf

[^1_36]: https://bigdatarepublic.nl/articles/understanding-inverse-propensity-weighting/

[^1_37]: https://arxiv.org/html/2407.06698v1

[^1_38]: https://openreview.net/pdf?id=rJzLciCqKm

[^1_39]: http://arxiv.org/pdf/1901.09503.pdf

[^1_40]: https://pmc.ncbi.nlm.nih.gov/articles/PMC11997483/

[^1_41]: https://arxiv.org/pdf/1904.10799v1.pdf

[^1_42]: https://www.sciencedirect.com/science/article/abs/pii/S0167947321002334

[^1_43]: https://pmc.ncbi.nlm.nih.gov/articles/PMC3635709/

[^1_44]: http://jmlr.org/papers/volume25/22-1233/22-1233.pdf

[^1_45]: https://arxiv.org/pdf/2411.10620.pdf

[^1_46]: https://arxiv.org/html/2204.10969v4

[^1_47]: https://pmc.ncbi.nlm.nih.gov/articles/PMC12223449/

[^1_48]: https://onlinelibrary.wiley.com/doi/10.1002/sim.5643

[^1_49]: https://matheusfacure.github.io/python-causality-handbook/12-Doubly-Robust-Estimation.html

[^1_50]: http://www2.stat.duke.edu/~fl35/teaching/640/Chap3.5_Doubly%20Robust%20Estimation.pdf

[^1_51]: https://arxiv.org/pdf/2201.07200.pdf

[^1_52]: https://openreview.net/pdf?id=SyPMT6gAb

[^1_53]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4263224/

[^1_54]: https://economics.mit.edu/sites/default/files/2024-02/Doubly Robust Inference in Causal Latent Factor Models.pdf

[^1_55]: https://arxiv.org/html/2406.00853v1

[^1_56]: https://openreview.net/pdf?id=h2ktOJbrT_4

[^1_57]: https://www.cs.cornell.edu/courses/cs7792/2020sp/lectures/03-unbiasedLTR.pdf

[^1_58]: https://www.cs.cornell.edu/courses/cs7792/2018fa/lectures/05-unbiasedLTR.pdf

[^1_59]: https://arxiv.org/html/2502.08993v1

[^1_60]: http://proceedings.mlr.press/v97/wang19n/wang19n.pdf

[^1_61]: https://dblp.org/rec/conf/wsdm/JoachimsSS17

[^1_62]: https://www.cs.cornell.edu/~schnabts/downloads/slides/schnabel2016mnar.pdf

[^1_63]: https://ir.webis.de/anthology/2017.wsdm_conference-2017.84/

[^1_64]: https://www.cs.cornell.edu/people/tj/publications/swaminathan_joachims_15c.pdf

[^1_65]: https://www.ijcai.org/proceedings/2022/0307.pdf

[^1_66]: https://arxiv.org/html/2509.00333v1

[^1_67]: https://www.cs.cornell.edu/people/tj/publications/joachims_etal_17a.pdf

[^1_68]: https://proceedings.mlr.press/v161/kalra21a.html

[^1_69]: https://arxiv.org/html/2402.00592v2

[^1_70]: https://arxiv.org/pdf/1602.08151.pdf

[^1_71]: https://jmlr.org/papers/volume24/21-0048/21-0048.pdf

[^1_72]: https://citeseerx.ist.psu.edu/document?repid=rep1\&type=pdf\&doi=2d9a81aec5a5e5fcc0c8edb1244d520933a021ff

[^1_73]: https://jair.org/index.php/jair/article/download/12610/26733/28714

[^1_74]: http://proceedings.mlr.press/v97/london19a/london19a.pdf

[^1_75]: https://openreview.net/pdf/d748f17dd4c23d2a45b79db6b5b55b715f9d3a83.pdf

[^1_76]: https://arxiv.org/html/2403.07857v1

[^1_77]: https://proceedings.mlr.press/v202/zenati23a/zenati23a.pdf

[^1_78]: https://openreview.net/pdf?id=wS1fD0ofay

[^1_79]: https://proceedings.neurips.cc/paper_files/paper/2022/file/e5aa7171449b83f8b4eec1623eac9906-Paper-Conference.pdf

[^1_80]: https://proceedings.mlr.press/v202/taori23a/taori23a.pdf

[^1_81]: https://cs229.stanford.edu/notes2020spring/weak_supervision_slides.pdf

[^1_82]: https://metricgate.com/docs/weak-supervision-snorkel/

[^1_83]: https://medium.com/@preeti.rana.ai/data-augmentation-techniques-for-imbalanced-datasets-9214374ffe44

[^1_84]: https://snorkelproject.org/use-cases/01-spam-tutorial/

[^1_85]: https://www.vldb.org/pvldb/vol11/p269-ratner.pdf

[^1_86]: https://arxiv.org/pdf/2205.02318.pdf

[^1_87]: https://cs231n.stanford.edu/slides/2018/cs231n_2018_ds07.pdf

[^1_88]: https://www.ijert.org/handling-imbalanced-data-using-up-sampling-and-data-augmentation-for-nlp

[^1_89]: https://www.cl.cam.ac.uk/~ey204/teaching/ACS/R244_2018_2019/presentation/S7/SNORKEL_Marek.pdf

[^1_90]: https://pmc.ncbi.nlm.nih.gov/articles/PMC3648438/

[^1_91]: https://www.youtube.com/watch?v=8m6p-Ed7fTM

[^1_92]: https://arxiv.org/pdf/2505.13434.pdf

[^1_93]: https://www.diva-portal.org/smash/get/diva2:1521110/FULLTEXT01.pdf

[^1_94]: https://snorkel.ai/blog/epoxy-semi-supervised-learning-weak-supervision/

[^1_95]: https://www.sciencedirect.com/science/article/pii/S2666827024000732

[^1_96]: https://www.birs.ca/workshops/2003/03w5023/files/Asterbro_Bound.pdf

[^1_97]: https://f.hubspotusercontent10.net/hubfs/4623266/solving-sample-selection-bias-in-credit-scoring-rejecting-inference.pdf

[^1_98]: https://dl.acm.org/doi/10.1145/1014052.1014085

[^1_99]: https://hal.science/hal-04141601v1/document

[^1_100]: https://www.occ.gov/publications-and-resources/publications/economics/working-papers-archived/pub-econ-working-paper-2004-5.pdf

[^1_101]: https://openreview.net/pdf/24eada87ad79fcb83265168b582cff0541afced8.pdf

[^1_102]: https://citeseerx.ist.psu.edu/document?repid=rep1\&type=pdf\&doi=aac6e00028297480e08c80d4d87155eb7feef280

[^1_103]: https://sigir-ecom.github.io/eCom25Papers/paper_9.pdf

[^1_104]: https://ijrdst.org/public/uploads/paper/350861735545269.pdf

[^1_105]: https://arxiv.org/html/2407.13009v1

[^1_106]: https://is.muni.cz/th/msp3d/BP_X.pdf

[^1_107]: https://adimajo.github.io/rejectinference.html

[^1_108]: https://arxiv.org/html/2410.20978v1

[^1_109]: https://www.esann.org/sites/default/files/proceedings/legacy/es2017-95.pdf

[^1_110]: https://arxiv.org/pdf/2102.02291.pdf

[^1_111]: http://www.gatsby.ucl.ac.uk/~gretton/papers/covariateShiftChapter.pdf

[^1_112]: https://arxiv.org/html/2210.09709

[^1_113]: https://citeseerx.ist.psu.edu/document?repid=rep1\&type=pdf\&doi=667d5cd5e3066b1bcdb2188cbefa0eed5a3d8521

[^1_114]: http://arxiv.org/pdf/1910.06324.pdf

[^1_115]: https://www.emergentmind.com/topics/covariate-shift

[^1_116]: https://www.seas.upenn.edu/~obastani/cis7000/spring2024/docs/lecture4.pdf

[^1_117]: https://arxiv.org/pdf/2305.08637v1.pdf

[^1_118]: https://arxiv.org/pdf/2007.04043.pdf

[^1_119]: https://burrsettles.com/pub/settles.activelearning.pdf

[^1_120]: https://www.cs.cmu.edu/~epxing/Class/10701-12f/Lecture/settles.active-nov14.pdf

[^1_121]: https://sfu-db.github.io/cmpt884-fall16/Lectures/884_presentation_on_active_learning.pdf

[^1_122]: https://engineersofai.com/docs/ml/ml-system-design/feedback-loops-and-data-flywheel

[^1_123]: https://pdfs.semanticscholar.org/5ccf/7658018981bf492d0c8d66277d22ebaac815.pdf

[^1_124]: https://cdn.aaai.org/ojs/11715/11715-13-15243-1-2-20201228.pdf

[^1_125]: https://papers.nips.cc/paper_files/paper/2017/file/7cce53cf90577442771720a370c3c723-Reviews.html

[^1_126]: https://proceedings.neurips.cc/paper_files/paper/2014/file/f032bc3f1eb547f716df87edb523b8f0-Paper.pdf

[^1_127]: https://ix.cs.uoregon.edu/~lowd/hammoudeh-neurips20.pdf

[^1_128]: http://proceedings.mlr.press/v48/jiang16.pdf

[^1_129]: https://github.com/usaito/CFML-papers/issues/9

[^1_130]: https://projecteuclid.org/journals/statistical-science/volume-29/issue-4/Doubly-Robust-Policy-Evaluation-and-Optimization/10.1214/14-STS500.pdf

[^1_131]: https://arxiv.org/html/2502.21194v1

[^1_132]: https://proceedings.neurips.cc/paper_files/paper/2020/file/98b297950041a42470269d56260243a1-Supplemental.pdf

[^1_133]: https://github.com/Lorenzo-Perini/Active_PU_Learning

[^1_134]: https://repository.uantwerpen.be/docstore/d:irua:3801

[^1_135]: https://icml.cc/2011/papers/554_icmlpaper.pdf

